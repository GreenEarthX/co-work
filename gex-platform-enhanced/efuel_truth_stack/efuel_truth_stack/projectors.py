"""
projectors.py — fold the ledger into Claim and Node projections.

The JSON specifies the data model and the legal claim_state transitions, but not
the *fold algorithm*. The convention below is an implementation decision (it
changes no enum and no rule):

  - A claim-bearing ledger row carries `payload["claim_id"]`. The first such row
    also carries the descriptive fields: `claim_type`, `subject_node`,
    `value_type`, optional `value/unit/period/authority_rule`.
  - Each row may carry `payload["to_state"]`: the claim_state it drives the claim
    toward. If absent it is inferred from the row's entry_type/outcome.
  - Folding processes a claim's rows in transaction-time (recorded_at) order,
    starting at `asserted`, advancing along the LEGAL transition path
    (asserted -> submitted -> verified -> satisfied), with `waived`/`rejected`/
    `expired`/`failed`/`superseded` as authorised jumps. An illegal transition
    raises ProjectionError — `claim_state.transitions` is enforced, not advisory.
  - `value` is taken from the latest fact row carrying one (authority_rule is
    recorded for auditability; a fuller conflict-resolver can use it later).

Node rollup is worst-of: a node is green iff every required claim is present,
terminal_valid, and time-valid at the query's valid_time.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .enums import (
    CLAIM_STATE_TRANSITIONS, ClaimState, EntryType, LedgerKind, ValueType,
    can_transition, is_terminal_valid,
)
from .ledger import Ledger
from .models import Claim, EvidenceLink, Node
from .spec import NODES


class ProjectionError(ValueError):
    """Raised when the ledger folds into an illegal claim transition."""


_HAPPY_PATH = [ClaimState.ASSERTED, ClaimState.SUBMITTED, ClaimState.VERIFIED, ClaimState.SATISFIED]


def _infer_target(entry) -> Optional[ClaimState]:
    if "to_state" in entry.payload:
        return ClaimState(entry.payload["to_state"])
    et = entry.entry_type
    if et == EntryType.REJECTION:
        return ClaimState.REJECTED
    if et == EntryType.WAIVER:
        return ClaimState.WAIVED
    if et == EntryType.RELEASE_DECISION:
        # v0.3 §3.5: the legitimate path to SATISFIED — a decision-kind entry
        # from an authorised actor, replacing the to_state backdoor (§3.4).
        return ClaimState.SATISFIED
    if et == EntryType.APPROVAL_DECISION:
        outcome = entry.payload.get("outcome")
        if outcome in ("approve", "approve_with_conditions"):
            return ClaimState.VERIFIED
        if outcome == "reject":
            return ClaimState.REJECTED
        return None
    if entry.kind == LedgerKind.FACT:
        return ClaimState.SUBMITTED
    return None


def _advance(state: ClaimState, target: ClaimState, claim_id: str) -> ClaimState:
    """Move state -> target along the legal path; raise on illegal transitions."""
    if target == state:
        return state
    # waiver is an authorised override to a terminal-valid state.
    if target == ClaimState.WAIVED:
        return ClaimState.WAIVED
    # Walk the linear happy-path forward, step by step (each hop is legal).
    if state in _HAPPY_PATH and target in _HAPPY_PATH:
        si, ti = _HAPPY_PATH.index(state), _HAPPY_PATH.index(target)
        if ti > si:
            cur = state
            for nxt in _HAPPY_PATH[si + 1:ti + 1]:
                if not can_transition(cur, nxt):
                    raise ProjectionError(f"illegal transition {cur} -> {nxt} (claim {claim_id})")
                cur = nxt
            return cur
    # Otherwise a single authorised hop (e.g. verified -> expired/superseded).
    if can_transition(state, target):
        return target
    raise ProjectionError(f"illegal claim transition {state} -> {target} (claim {claim_id})")


def fold_claims(ledger: Ledger,
                transaction_time: Optional[datetime] = None,
                project_id: Optional[str] = None,
                evidence_links: Optional[list[EvidenceLink]] = None) -> dict[str, Claim]:
    """Fold live ledger rows into Claim projections keyed by claim_id.

    evidence_links (v0.3 §3.6): many-to-many hash-pinned claim↔entry links —
    one certificate may back N claims, which payload.claim_id (one-entry-one-
    claim) cannot express. Links are merged into each claim's evidence_refs,
    deduplicated by (ledger_entry_id, claim_id). A link whose pinned hash does
    not match the entry's current content hash raises ProjectionError —
    tampering must fail the fold, not decorate it."""
    rows = sorted(
        (e for e in ledger.live(transaction_time, project_id) if e.payload.get("claim_id")),
        key=lambda e: (e.recorded_at, e.id),
    )
    groups: dict[str, list] = {}
    for e in rows:
        groups.setdefault(e.payload["claim_id"], []).append(e)

    claims: dict[str, Claim] = {}
    for cid, grp in groups.items():
        head = grp[0]
        p0 = head.payload
        state = ClaimState.ASSERTED
        value, unit, authority_rule = None, p0.get("unit"), p0.get("authority_rule", "")
        evidence: list[EvidenceLink] = []
        for e in grp:
            target = _infer_target(e)
            if target is not None:
                # v0.3: an INFERRED fact target (no explicit to_state) is a
                # floor, never a demotion — later evidence appended to an
                # already-verified claim (e.g. a validity-narrowing correction)
                # must not crash the fold or regress state. Explicit to_state
                # keeps strict transition semantics.
                inferred_fact_floor = (
                    e.kind == LedgerKind.FACT
                    and "to_state" not in e.payload
                    and target == ClaimState.SUBMITTED
                    and state in _HAPPY_PATH
                    and _HAPPY_PATH.index(state) >= _HAPPY_PATH.index(ClaimState.SUBMITTED)
                )
                if not inferred_fact_floor:
                    state = _advance(state, target, cid)
            if e.kind == LedgerKind.FACT:
                if "value" in e.payload:
                    value = e.payload["value"]
                evidence.append(EvidenceLink(ledger_entry_id=e.id, evidence_hash=e.hash, claim_id=cid))
            if "supersedes_claim" in e.payload:  # this row replaces an earlier claim version
                old = claims.get(e.payload["supersedes_claim"])
                if old is not None:
                    claims[old.id] = old.model_copy(update={"state": ClaimState.SUPERSEDED, "superseded_by": cid})

        claims[cid] = Claim(
            id=cid,
            subject_node=p0.get("subject_node", ""),
            claim_type=p0.get("claim_type", ""),
            value_type=ValueType(p0.get("value_type", "numeric")),
            value=value,
            unit=unit,
            state=state,
            period=p0.get("period"),
            valid_from=head.valid_from,
            valid_to=_latest_valid_to(grp),
            evidence_refs=evidence,
            authority_rule=authority_rule,
        )

    # v0.3 §3.6 — merge explicit evidence_links (many-to-many), hash-verified.
    if evidence_links:
        by_id = {e.id: e for e in ledger.live(transaction_time, project_id)}
        for link in evidence_links:
            if not link.claim_id or link.claim_id not in claims:
                continue
            entry = by_id.get(link.ledger_entry_id)
            if entry is None:
                continue  # link to a non-live entry: not visible at this time
            if link.evidence_hash != entry.hash:
                raise ProjectionError(
                    f"evidence link {link.ledger_entry_id} -> claim {link.claim_id}: "
                    f"pinned hash does not match entry content hash — possible tampering."
                )
            claim = claims[link.claim_id]
            if not any(r.ledger_entry_id == link.ledger_entry_id
                       for r in claim.evidence_refs):
                claims[link.claim_id] = claim.model_copy(update={
                    "evidence_refs": claim.evidence_refs + [link],
                })
    return claims


def _latest_valid_to(grp: list) -> Optional[date]:
    """The valid_to of the most recently recorded row wins (supports de-cert)."""
    return sorted(grp, key=lambda e: (e.recorded_at, e.id))[-1].valid_to


# severity rank: terminal_invalid worst, non-terminal middle, terminal_valid best.
def _rank(state: ClaimState) -> int:
    if is_terminal_valid(state):
        return 2
    if state in (ClaimState.ASSERTED, ClaimState.SUBMITTED):
        return 1
    return 0  # terminal_invalid


def rollup_nodes(claims: dict[str, Claim],
                 valid_time: Optional[date] = None) -> dict[str, Node]:
    """Roll claims up into Node projections (node = worst-of required claims)."""
    by_node_type: dict[tuple[str, str], list[Claim]] = {}
    for c in claims.values():
        by_node_type.setdefault((c.subject_node, c.claim_type), []).append(c)

    nodes: dict[str, Node] = {}
    for nid, nd in NODES.items():
        required = nd.get("required_claims", [])
        states: list[ClaimState] = []
        missing: list[str] = []
        for ct in required:
            cand = by_node_type.get((nid, ct), [])
            if valid_time is not None:
                cand = [c for c in cand if c.valid_from <= valid_time and (c.valid_to is None or valid_time < c.valid_to)]
            if not cand:
                missing.append(ct)
                continue
            # the most-valid available claim represents this requirement
            states.append(max(cand, key=lambda c: _rank(c.state)).state)
        rolled = None if (missing or not states) else min(states, key=_rank)
        nodes[nid] = Node(
            id=nid,
            layer=nd["layer"],
            label=nd.get("label", nid),
            depends_on=nd.get("depends_on", []),
            required_claims=required,
            rolled_up_state=rolled,
            missing_claims=missing,
        )
    return nodes


def node_is_green(node: Node) -> bool:
    """Green iff nothing missing and the worst required-claim state is terminal_valid."""
    return (not node.missing_claims) and node.rolled_up_state is not None and is_terminal_valid(node.rolled_up_state)
