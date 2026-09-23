"""
Reading another user's owner-scoped work — the exception, made visible.
=======================================================================
Migration 050 put canvas documents, user plants and equipment equations under
an OWNER-only policy with **no admin clause**: `is_platform_admin` grants
nothing here, and neither does being the table owner (the tables are FORCE ROW
LEVEL SECURITY). Normal operation cannot read another person's work at all.

Support, deletion requests and offboarding are real needs, so this module is
the deliberate exception. It is not a bypass of the policy — it uses the same
policy, with `app.current_user_id` set to the ONE person whose data is being
acted on. There is no "all owners" mode and no escalation to a wildcard,
because the point of the policy is that such a thing should not exist.

WHAT MAKES THIS DIFFERENT FROM A STANDING GRANT
-----------------------------------------------
· ONE user per call. A subject must be named; a request for "everyone" cannot
  be expressed.
· A REASON IS MANDATORY, and it is not free decoration: `admin_log.justification`
  is NOT NULL and this refuses an empty or whitespace reason.
· THE RECORD IS WRITTEN FIRST. The `admin_log` row is committed BEFORE the
  connection is handed over, so an access that then fails, hangs or raises is
  still on the record. A log written afterwards is a log of successful accesses
  only, which is the wrong half.
· It is not wired into any route. Nothing a browser can reach calls this; it is
  for a named operator running a named procedure.

The audit row lands in `admin_log` — an existing 044 table with exactly the
columns this needs (`admin_user_id`, `action`, `target_user_id`,
`justification`) rather than a new table nobody else reads.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.db_backend import (
    domain_connection,
    workspace_connection,
    workspace_is_postgres,
)

logger = logging.getLogger("gex.break_glass")

ACTION = "workspace.break_glass"

# What an operator may be doing. A free-text purpose would drift into
# "investigation" and "checking something"; these are the three cases that
# justified the path existing, and adding a fourth should be a conversation.
PURPOSES = ("SUPPORT", "DELETION_REQUEST", "OFFBOARDING")


class BreakGlassRefused(RuntimeError):
    """Raised instead of opening a connection. Never downgraded to a warning:
    a refused break-glass must fail the operator's procedure, not proceed with
    less access than they believe they have."""


def _audit(actor_user_id: str, subject_user_id: str, purpose: str,
           reason: str, context: Optional[dict] = None) -> None:
    """Write the record and COMMIT it, before any data is read."""
    conn = domain_connection(company_id="PLATFORM_ADMIN")
    try:
        conn.execute(
            "INSERT INTO admin_log (timestamp, admin_user_id, action, "
            "target_user_id, justification, before_state, after_state) "
            "VALUES (?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), actor_user_id, ACTION,
             subject_user_id, f"[{purpose}] {reason}",
             json.dumps(context or {}, sort_keys=True), None),
        )
        conn.commit()
    finally:
        conn.close()


def open_owner_workspace(*, actor_user_id: str, subject_user_id: str,
                         purpose: str, reason: str,
                         context: Optional[dict] = None) -> Any:
    """Open a connection scoped to `subject_user_id`'s owner-scoped tables.

    Every argument is required and none has a default — an operator has to say
    who they are, whose data they are opening, under which of the three
    purposes, and why. The record is written and committed before the
    connection exists.

    Returns a connection whose `app.current_user_id` is the SUBJECT, so 050's
    policies admit exactly that person's rows and nothing else. Close it when
    done; it is not a context the rest of the app shares.
    """
    for name, value in (("actor_user_id", actor_user_id),
                        ("subject_user_id", subject_user_id),
                        ("reason", reason)):
        if not (value or "").strip():
            raise BreakGlassRefused(
                f"{name} is required — break-glass access is not anonymous")

    if purpose not in PURPOSES:
        raise BreakGlassRefused(
            f"purpose must be one of {', '.join(PURPOSES)}, not {purpose!r}")

    if len(reason.strip()) < 12:
        # A reason nobody can act on later is the same as no reason. This is a
        # floor on effort, not a quality check — it cannot tell a real ticket
        # reference from twelve characters of noise, and does not pretend to.
        raise BreakGlassRefused(
            "reason must say what this access is for (at least 12 characters); "
            f"got {reason.strip()!r}")

    if actor_user_id == subject_user_id:
        raise BreakGlassRefused(
            "actor and subject are the same user — your own workspace is "
            "readable without break-glass, and logging it as one would put "
            "noise in the audit trail")

    if not workspace_is_postgres():
        # On SQLite there is no policy to work within: the file has no RLS, so
        # this would hand over unrestricted access while writing a record that
        # implies it was scoped. Refuse rather than imply.
        raise BreakGlassRefused(
            "break-glass is meaningful only against PostgreSQL, where 050's "
            "owner policy binds. WORKSPACE_DB_BACKEND is currently sqlite")

    _audit(actor_user_id, subject_user_id, purpose, reason, context)
    logger.warning(
        "BREAK-GLASS: %s opened %s's workspace (%s). Recorded in admin_log.",
        actor_user_id, subject_user_id, purpose,
    )
    return workspace_connection(user_id=subject_user_id)
