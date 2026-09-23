"""
Account vetting guardrails — credentials are not trust.
=======================================================
Policy (user ruling, 2026-08-07): registration creates a PENDING account only.
A GEX employee must complete a telephone verification AND exchange/sign the
software usage agreement before the account becomes ACTIVE.

The property that matters: **nothing an applicant can do through the UI can
advance their own account.** Every test below is an attempt to violate that.

Guarded regression: `auth_users` shipped with `kyc_status DEFAULT 'VERIFIED'`
and `is_active DEFAULT 1`, so any row was trusted by construction.
"""
from __future__ import annotations

import pytest

from app.core.account_lifecycle import (
    ACCOUNT_TRANSITIONS,
    ACTIVATION_REQUIREMENTS,
    LOGIN_PERMITTED_STATES,
    AccountLifecycleError,
    AccountState,
    assert_activation_evidence,
    assert_activator_is_gex_staff,
    assert_separation_of_duties,
    assert_transition_allowed,
    can_login,
)


def _reachable(start: AccountState) -> set[AccountState]:
    seen, stack = set(), [start]
    while stack:
        for nxt in ACCOUNT_TRANSITIONS.get(stack.pop(), []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


# ── The core property ───────────────────────────────────────────────────────

def test_only_active_may_log_in():
    assert LOGIN_PERMITTED_STATES == frozenset({AccountState.ACTIVE})
    for state in AccountState:
        assert can_login(state) is (state is AccountState.ACTIVE), state


def test_a_freshly_registered_account_cannot_log_in():
    """The state registration produces must never be a login-permitted state."""
    assert not can_login(AccountState.PENDING)


def test_unknown_or_missing_state_fails_closed():
    """A state we cannot interpret is not a state we trust."""
    for junk in ("VERIFIED", "", None, "active", "ok"):
        assert can_login(junk) is False, junk


def test_registration_cannot_reach_active_without_passing_through_vetting():
    """
    PENDING -> ACTIVE must not be a legal single hop: the intermediate state is
    where the human work is recorded. A direct edge would let an activation call
    succeed on an account with no evidence on file.
    """
    assert AccountState.ACTIVE not in ACCOUNT_TRANSITIONS[AccountState.PENDING]


def test_rejected_is_terminal():
    assert ACCOUNT_TRANSITIONS[AccountState.REJECTED] == []
    assert not _reachable(AccountState.REJECTED)


def test_every_state_is_in_the_transition_table():
    missing = [s for s in AccountState if s not in ACCOUNT_TRANSITIONS]
    assert not missing, missing


# ── Activation requires recorded human work ─────────────────────────────────

_COMPLETE = {
    "phone_verified_at": "2026-08-07T10:00:00Z",
    "phone_verified_by": "gex_alice",
    "agreement_signed_at": "2026-08-07",
    "agreement_ref": "GEX-SUA-2026-0042",
}


def test_activation_evidence_accepts_a_complete_record():
    assert_activation_evidence(_COMPLETE)


@pytest.mark.parametrize("missing", sorted(ACTIVATION_REQUIREMENTS))
def test_activation_refused_when_any_single_piece_is_missing(missing):
    record = dict(_COMPLETE)
    record.pop(missing)
    with pytest.raises(AccountLifecycleError) as e:
        assert_activation_evidence(record)
    assert "vetting incomplete" in str(e.value)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_evidence_does_not_count_as_evidence(blank):
    """A whitespace agreement_ref is not a signed agreement."""
    record = dict(_COMPLETE, agreement_ref=blank)
    with pytest.raises(AccountLifecycleError):
        assert_activation_evidence(record)


def test_both_telephone_and_agreement_are_required_not_either():
    """The policy is conjunctive — one piece of vetting is not enough."""
    phone_only = {k: v for k, v in _COMPLETE.items() if k.startswith("phone")}
    paper_only = {k: v for k, v in _COMPLETE.items() if k.startswith("agreement")}
    for partial in (phone_only, paper_only):
        with pytest.raises(AccountLifecycleError):
            assert_activation_evidence(partial)


# ── Only GEX staff, and never the same pair of eyes ─────────────────────────

def test_only_gex_staff_may_activate():
    with pytest.raises(AccountLifecycleError):
        assert_activator_is_gex_staff({"user_id": "u1", "business_function": "EXECUTIVE"})
    assert_activator_is_gex_staff({"user_id": "gex1", "is_platform_admin": True})


def test_a_customer_executive_cannot_vet_their_own_organisation():
    """
    Seniority inside the applicant's company is irrelevant — EXECUTIVE,
    CONFIDENTIAL clearance and every capability still cannot self-activate.
    """
    with pytest.raises(AccountLifecycleError):
        assert_activator_is_gex_staff({
            "user_id": "cust_ceo", "business_function": "EXECUTIVE",
            "clearance_level": "CONFIDENTIAL", "company_type": "PRODUCER",
            "capabilities": ["OFFTAKE", "PRODUCE", "SELL"], "is_platform_admin": False,
        })


def test_the_employee_who_made_the_call_cannot_activate():
    with pytest.raises(AccountLifecycleError) as e:
        assert_separation_of_duties(_COMPLETE, "gex_alice")
    assert "separation of duties" in str(e.value)


def test_a_different_employee_may_activate():
    assert_separation_of_duties(_COMPLETE, "gex_bob")


# ── Transition legality ─────────────────────────────────────────────────────

def test_illegal_transitions_are_refused():
    for current, target in [
        (AccountState.PENDING, AccountState.ACTIVE),
        (AccountState.ACTIVE, AccountState.PENDING),
        (AccountState.REJECTED, AccountState.ACTIVE),
        (AccountState.REJECTED, AccountState.PENDING),
    ]:
        with pytest.raises(AccountLifecycleError):
            assert_transition_allowed(current, target)


def test_the_vetting_and_recovery_paths_are_legal():
    assert_transition_allowed(AccountState.PENDING, AccountState.IN_VETTING)
    assert_transition_allowed(AccountState.IN_VETTING, AccountState.ACTIVE)
    assert_transition_allowed(AccountState.ACTIVE, AccountState.SUSPENDED)
    assert_transition_allowed(AccountState.SUSPENDED, AccountState.ACTIVE)


# ── The schema default that started this ────────────────────────────────────

def test_new_accounts_default_to_pending_in_the_sqlite_schema(monkeypatch):
    """
    The column default is load-bearing: any code path that inserts an
    auth_users row without naming account_state must produce an untrusted
    account, not a trusted one.

    Forces the SQLite backend regardless of AUTH_DB_BACKEND — this asserts the
    SQLite DDL specifically. The Postgres equivalent is the next test, because
    on Postgres the schema is owned by alembic and _ensure_tables is a no-op.
    """
    import sqlite3
    import tempfile
    from pathlib import Path

    from app.core import auth as auth_mod

    monkeypatch.setenv("AUTH_DB_BACKEND", "sqlite")

    # _ensure_tables takes its connection as an argument, so no store path needs
    # redirecting (auth.py no longer has a module-level DB_PATH to swap).
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "t.db")
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        try:
            auth_mod._ensure_tables(conn)
            conn.execute(
                "INSERT INTO auth_users (user_id,email,password_hash,company_id,"
                "company_name,company_type,business_function,user_name) "
                "VALUES ('u','e@x.io','h','c','C','PRODUCER','EXECUTIVE','U')"
            )
            conn.commit()
            row = conn.execute("SELECT account_state FROM auth_users").fetchone()
            assert row["account_state"] == AccountState.PENDING.value
            assert not can_login(row["account_state"])
        finally:
            conn.close()


def test_new_accounts_default_to_pending_in_the_postgres_schema():
    """
    Same property, other backend. Read from the alembic revision that owns the
    Postgres schema, so the two stores cannot drift into disagreeing about
    whether a brand-new account is trusted.
    """
    from pathlib import Path

    revision = (
        Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "030_auth_slice.py"
    ).read_text()

    assert 'sa.Column("account_state", sa.Text(), nullable=False, server_default="PENDING")' in revision, (
        "the Postgres schema must default account_state to PENDING"
    )
    # The two defaults that made every SQLite row trusted must not be
    # reintroduced on the Postgres side.
    assert 'server_default="VERIFIED"' not in revision
    assert 'sa.Column("is_active", sa.Integer(), nullable=False, server_default="0")' in revision


# ── kyc_status must not default to a claim of verification ──────────────────

def test_no_store_defaults_kyc_status_to_verified():
    """A default is a claim nobody made.

    `auth_users.kyc_status` defaulted to 'VERIFIED' in the SQLite DDL and in the
    seeder, so any row created without an explicit value asserted a KYC check
    that had never happened — measured 2026-09-23, 19 of 20 rows did, while the
    KYC record itself was still sitting in a browser. PostgreSQL's default
    (migration 030) was already UNVERIFIED.

    Matched against the source rather than a live database so it runs with
    PostgreSQL stopped, and covers both stores' DDL in one place.
    """
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]

    auth_src = (backend / "app" / "core" / "auth.py").read_text()
    ddl = re.search(r"kyc_status\s+TEXT\s+NOT NULL\s+DEFAULT\s+'([A-Z_]+)'", auth_src)
    assert ddl, "could not find the kyc_status column definition in auth.py"
    assert ddl.group(1) != "VERIFIED", (
        "the SQLite auth_users DDL defaults kyc_status to VERIFIED again — every "
        "row created without an explicit value would claim a KYC check nobody ran"
    )

    seeder = re.search(r'seed\.get\("kyc_status",\s*"([A-Z_]+)"\)', auth_src)
    assert seeder, "could not find the seeder's kyc_status fallback"
    assert seeder.group(1) != "VERIFIED", (
        "the demo seeder writes VERIFIED again — a seeded account that cannot be "
        "told apart from a vetted one makes the vetting meaningless"
    )

    migration = (backend / "alembic" / "versions" / "030_auth_slice.py").read_text()
    pg = re.search(r'"kyc_status".*?server_default="([A-Z_]+)"', migration)
    assert pg and pg.group(1) != "VERIFIED", (
        "the PostgreSQL column default for kyc_status is now VERIFIED"
    )


def test_no_auth_path_treats_a_missing_kyc_claim_as_verified():
    """An absent claim is not a passed check.

    Five places in the auth path defaulted a missing `kyc_status` to VERIFIED:
    the `UserAttributes` dataclass, both paths that build it
    (`abac_middleware`, `tenant_context`), the permission context, and the
    payload rebuilt from JWT claims. A token that said nothing about KYC was
    therefore treated as verified by `requires_kyc:VERIFIED`.

    Source-matched so it runs with the database stopped. SEED is permitted —
    demo mode uses it deliberately, and it does not satisfy the gate either.
    """
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    patterns = [
        ("app/core/abac.py", r"kyc_status: str = \"([A-Z_]+)\""),
        ("app/core/abac_middleware.py", r'getattr\(user, "kyc_status", "([A-Z_]+)"\)'),
        ("app/core/abac_middleware.py", r'kyc_status=payload\.get\("kyc_status", "([A-Z_]+)"\)'),
        ("app/core/tenant_context.py", r'kyc_status=payload\.get\("kyc_status", "([A-Z_]+)"\)'),
        ("app/core/auth.py", r'"kyc_status": claims\.get\("kyc_status", "([A-Z_]+)"\)'),
    ]
    offenders = []
    for rel, pat in patterns:
        src = (backend / rel).read_text()
        m = re.search(pat, src)
        assert m, f"{rel}: the kyc_status fallback this guards has moved — re-point it"
        if m.group(1) == "VERIFIED":
            offenders.append(f"{rel} defaults a missing kyc_status to VERIFIED")
    assert not offenders, (
        "fail-open kyc_status defaults are back:\n" + "\n".join(offenders))
