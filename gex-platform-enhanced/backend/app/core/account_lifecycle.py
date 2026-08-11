"""
Account lifecycle — vetting before trust.
=========================================
Product-policy ruling (2026-08-07, user):

    "A new user is not automatically trusted just because they created
     credentials or entered data through the UI. Registration should only
     create a pending account. A GEX employee must complete the onboarding
     process, including at least one final telephone verification and the
     exchange/signature of the software usage agreement. Only after that
     should the user or organisation become active."

This module is the ONLY definition of that policy. It lives in the backend on
purpose: RLS and Supabase are persistence and defence-in-depth, but *who is
trusted* is a product decision, not a row-level filter.

What this replaced
------------------
`auth_users` shipped with `kyc_status TEXT NOT NULL DEFAULT 'VERIFIED'` and
`is_active INTEGER NOT NULL DEFAULT 1`. Any row that existed was, by
construction, a fully trusted verified user — and login checked only
`is_active`, never `kyc_status`. There was no registration endpoint at all, so
nothing had yet exercised that default; this closes it before anything does.

The two-key rule
----------------
ACTIVE requires BOTH pieces of human work to be recorded, each naming the GEX
employee who did it:
  · a telephone verification  (phone_verified_at + phone_verified_by)
  · a signed usage agreement  (agreement_signed_at + agreement_ref)
Neither is inferable from anything the applicant can do through the UI. That is
the point — self-asserted data can never advance an account.
"""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger("gex.account_lifecycle")


class AccountState(str, Enum):
    """
    PENDING   — registered, credentials exist, NOTHING is trusted. Cannot log in.
    IN_VETTING — a GEX employee has picked the application up. Still cannot log in.
    ACTIVE    — telephone-verified AND agreement signed, activated by a named
                GEX employee. May log in (then subject to role/project checks).
    SUSPENDED — was ACTIVE, access withdrawn. Reversible by re-activation.
    REJECTED  — vetting failed. Terminal; a new application must start over.
    """

    PENDING = "PENDING"
    IN_VETTING = "IN_VETTING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"


#: The ONLY state in which credentials are accepted. Everything else — including
#: the state a self-service registration produces — is refused at login.
LOGIN_PERMITTED_STATES: frozenset[AccountState] = frozenset({AccountState.ACTIVE})

#: Terminal — a rejected application is not re-opened, it is re-submitted.
TERMINAL_STATES: frozenset[AccountState] = frozenset({AccountState.REJECTED})

ACCOUNT_TRANSITIONS: dict[AccountState, list[AccountState]] = {
    AccountState.PENDING: [AccountState.IN_VETTING, AccountState.REJECTED],
    AccountState.IN_VETTING: [AccountState.ACTIVE, AccountState.REJECTED, AccountState.PENDING],
    AccountState.ACTIVE: [AccountState.SUSPENDED],
    AccountState.SUSPENDED: [AccountState.ACTIVE, AccountState.REJECTED],
    AccountState.REJECTED: [],
}

#: Evidence of human vetting that must be on the record before ACTIVE. Keys are
#: `auth_users` columns; the value is what a GEX employee must have done.
ACTIVATION_REQUIREMENTS: dict[str, str] = {
    "phone_verified_at": "a telephone verification must be recorded",
    "phone_verified_by": "the GEX employee who made the call must be named",
    "agreement_signed_at": "the software usage agreement must be signed",
    "agreement_ref": "the signed agreement must be referenced",
}


class AccountLifecycleError(Exception):
    """Policy refusal. Callers map this to 403/409 — it is never a 500."""


def can_login(state: str | AccountState) -> bool:
    try:
        return AccountState(state) in LOGIN_PERMITTED_STATES
    except ValueError:
        # Unknown/legacy value — fail closed. A state we cannot interpret is
        # not a state we trust.
        logger.warning("unknown account_state %r — refusing login", state)
        return False


def assert_transition_allowed(current: AccountState, target: AccountState) -> None:
    allowed = ACCOUNT_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise AccountLifecycleError(
            f"Invalid account transition {current.value} -> {target.value}. "
            f"Valid: {[s.value for s in allowed]}"
        )


def assert_activation_evidence(record: dict) -> None:
    """
    Refuse ACTIVE unless every piece of human vetting is on the record.

    Deliberately checks the *stored* row, not the request: an activation call
    cannot carry its own proof. The evidence must already have been written by
    the endpoints that record the call and the signature.
    """
    missing = [
        reason
        for column, reason in ACTIVATION_REQUIREMENTS.items()
        if not str(record.get(column) or "").strip()
    ]
    if missing:
        raise AccountLifecycleError(
            "Account cannot be activated — vetting incomplete: " + "; ".join(missing)
        )


def assert_activator_is_gex_staff(actor: dict) -> None:
    """
    Only GEX staff activate accounts. A customer — however senior, however
    EXECUTIVE their business_function — cannot vet their own organisation.
    """
    if not actor.get("is_platform_admin"):
        raise AccountLifecycleError(
            "Only a GEX platform administrator may activate an account. "
            f"Actor {actor.get('user_id') or actor.get('email')!r} is not GEX staff."
        )


def assert_separation_of_duties(record: dict, activator_id: str) -> None:
    """
    The employee who made the verification call may not also be the one who
    flips the account to ACTIVE. Two pairs of eyes on the only step that grants
    access to the platform.
    """
    caller = record.get("phone_verified_by")
    if caller and caller == activator_id:
        raise AccountLifecycleError(
            "The GEX employee who performed the telephone verification may not "
            "also activate the account (separation of duties)."
        )
