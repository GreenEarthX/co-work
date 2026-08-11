"""
Token lifecycle guardrails — the anti-double-count invariant.
=============================================================
GEX's quality proposition is transparency and accountability away from
greenwashing. That reduces to one machine-checkable property:

    a green claim is made exactly once, and nothing can put it back.

The green certificate is not separable from the molecule token — it travels as
an attribute of the token — so "the claim is spent" and "the token is RETIRED"
are the same fact. These tests hold that fact against future edits.

Deliberately written as REACHABILITY over the transition graph, not as
assertions about specific table entries: a future contributor may add states
or edges, and the invariant must survive that rather than be silently widened.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.api.v1 import tokens_sqlite as T
from app.api.v1.tokens_sqlite import (
    CLAIMABLE_STATES,
    TERMINAL_STATES,
    TOKEN_TRANSITIONS,
    TokenLifecycleState as S,
)


def _reachable(start: S) -> set[S]:
    """Every state reachable from `start`, transitively."""
    seen: set[S] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        for nxt in TOKEN_TRANSITIONS.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


# ── The core invariant ──────────────────────────────────────────────────────

def test_no_path_from_retired_returns_a_claim_to_circulation():
    """
    THE guarantee. Retirement means the green attribute was claimed. If any
    path — direct or transitive — leads from RETIRED back to a state in which
    the claim is live, the same molecule can be claimed twice and every
    downstream assertion GEX makes about double-counting is false.
    """
    offenders = _reachable(S.RETIRED) & CLAIMABLE_STATES
    assert not offenders, (
        f"RETIRED can reach claimable state(s) {sorted(s.value for s in offenders)} — "
        "a retired green claim can be returned to circulation."
    )


def test_annulment_is_terminal_and_not_claimable():
    """
    Annulment corrects the record; it does not restore the claim. If ANNULLED
    ever gains an exit, the invariant above can be defeated in two hops.
    """
    assert TOKEN_TRANSITIONS[S.ANNULLED] == []
    assert S.ANNULLED not in CLAIMABLE_STATES


def test_every_state_is_in_the_transition_table():
    """No state may be implicitly terminal through omission."""
    missing = [s for s in S if s not in TOKEN_TRANSITIONS]
    assert not missing, f"states absent from TOKEN_TRANSITIONS: {missing}"


def test_terminal_states_have_no_exits():
    for s in TERMINAL_STATES:
        assert TOKEN_TRANSITIONS[s] == [], f"{s.value} is declared terminal but has exits"


def test_claimable_and_terminal_are_disjoint():
    assert not (CLAIMABLE_STATES & TERMINAL_STATES)


# ── VOID semantics: pre-delivery only ───────────────────────────────────────

def test_void_is_unreachable_once_the_molecule_has_settled():
    """
    VOIDED means "issued in error, never valid". Once a molecule is delivered
    that statement is false, so VOID must not be reachable from SETTLED or
    beyond — otherwise a real delivery can be erased rather than annulled.
    """
    for state in (S.SETTLED, S.RETIRED):
        assert S.VOIDED not in TOKEN_TRANSITIONS[state], (
            f"{state.value} -> VOIDED would erase a delivery that actually happened"
        )


def test_void_remains_available_before_delivery():
    """The correction path for a genuine mis-issue must not be closed off."""
    for state in (S.MINTED, S.RESERVED, S.MATCHED):
        assert S.VOIDED in TOKEN_TRANSITIONS[state]


def test_retirement_is_reachable_only_from_settled():
    """A claim cannot be made on a molecule that was never delivered."""
    sources = [s for s, nxt in TOKEN_TRANSITIONS.items() if S.RETIRED in nxt]
    assert sources == [S.SETTLED]


# ── Accountability: no anonymous actor on the claim-bearing object ──────────

@pytest.mark.parametrize("fn_name", ["transition_token", "create_token"])
def test_lifecycle_endpoints_take_no_anonymous_actor_default(fn_name):
    """
    Regression guard: both endpoints previously carried `user_id: str = "system"`,
    so any caller could move a token and the ledger recorded "system". A state
    change on the object carrying the green claim is attributable or it does
    not happen.
    """
    sig = inspect.signature(getattr(T, fn_name))
    assert "user_id" not in sig.parameters, (
        f"{fn_name} accepts a caller-supplied user_id — identity must come from "
        "the authenticated request, not the request body or query string"
    )
    assert "request" in sig.parameters, f"{fn_name} must derive its actor from the request"


def test_actor_identity_refuses_an_unauthenticated_request():
    class _State:
        user_payload = None

    class _Req:
        state = _State()

    with pytest.raises(Exception) as exc:
        T._actor_identity(_Req())
    assert getattr(exc.value, "status_code", None) == 401


# ── Claim-touching guards ───────────────────────────────────────────────────

def test_retirement_requires_consumption_evidence():
    with pytest.raises(Exception) as exc:
        T._guard_retirement(T.TokenTransition(new_state="RETIRED"))
    assert getattr(exc.value, "status_code", None) == 422
    assert exc.value.detail["error"] == "retirement_evidence_required"

    # With evidence it passes.
    T._guard_retirement(
        T.TokenTransition(new_state="RETIRED", consumption_evidence_ref="EVD-001")
    )


_GOOD_ANNULMENT = dict(
    new_state="ANNULLED",
    justification="Retirement booked against the wrong delivery lot; corrected under BR-2026-14.",
    annulment_authority_ref="BR-2026-14",
)
_EXEC = {"business_function": "EXECUTIVE"}


def test_annulment_requires_named_authority():
    with pytest.raises(Exception) as exc:
        T._guard_annulment(
            T.TokenTransition(**_GOOD_ANNULMENT),
            {"business_function": "COMMERCIAL"}, "alice", "bob",
        )
    assert getattr(exc.value, "status_code", None) == 403
    assert exc.value.detail["error"] == "annulment_authority_required"


def test_annulment_requires_a_written_rationale():
    payload = dict(_GOOD_ANNULMENT, justification="oops")
    with pytest.raises(Exception) as exc:
        T._guard_annulment(T.TokenTransition(**payload), _EXEC, "alice", "bob")
    assert exc.value.detail["error"] == "annulment_rationale_required"


def test_annulment_requires_an_authority_reference():
    payload = dict(_GOOD_ANNULMENT, annulment_authority_ref=None)
    with pytest.raises(Exception) as exc:
        T._guard_annulment(T.TokenTransition(**payload), _EXEC, "alice", "bob")
    assert exc.value.detail["error"] == "annulment_authority_ref_required"


def test_annulment_enforces_segregation_of_duties():
    """The party that made the claim may not be the party that unmakes it."""
    with pytest.raises(Exception) as exc:
        T._guard_annulment(T.TokenTransition(**_GOOD_ANNULMENT), _EXEC, "alice", "alice")
    assert getattr(exc.value, "status_code", None) == 403
    assert exc.value.detail["error"] == "annulment_segregation_of_duties"


def test_well_formed_annulment_by_a_second_authorised_actor_passes():
    T._guard_annulment(T.TokenTransition(**_GOOD_ANNULMENT), _EXEC, "alice", "bob")


# ── Documentation guard ─────────────────────────────────────────────────────

def test_every_lifecycle_state_is_defined_in_the_enum_docstring():
    """
    VOIDED previously had no definition anywhere in the codebase, which is how
    it became a universal escape hatch — including out of RETIRED. Every state
    must state what it asserts about the claim.
    """
    doc = S.__doc__ or ""
    # Must be a DEFINITION line ("NAME — meaning"), not an incidental mention:
    # a cross-reference elsewhere in the prose must not satisfy this.
    undefined = [
        s.value for s in S
        if not re.search(rf"^\s*{s.value}\s+—\s+\S", doc, re.MULTILINE)
    ]
    assert not undefined, f"lifecycle states with no stated meaning: {undefined}"
