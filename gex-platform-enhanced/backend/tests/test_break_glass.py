"""
Break-glass: the only way staff reach another user's work, and it leaves a mark.
================================================================================
Migration 050 gives canvas, plants and equations an owner-only policy with no
admin clause, so support, deletion requests and offboarding need a deliberate
exception. `app/core/break_glass.py` is it.

The property that matters is not "an admin can get in" — it is that getting in
is impossible to do quietly. These tests hold that shape in place:

  · a subject must be named (there is no "all owners" call to make)
  · a reason is mandatory and a purpose must be one of the three
  · THE RECORD IS COMMITTED BEFORE THE CONNECTION EXISTS, so an access that
    then fails is still on the record
  · the connection that comes back is scoped to the SUBJECT, not widened
"""
from __future__ import annotations

import pytest

from app.core import break_glass
from app.core.break_glass import BreakGlassRefused, open_owner_workspace
from app.core.db_backend import workspace_is_postgres
from tests.pg_support import pg_connect, requires_pg

ACTOR = "admin_greenearthx_com"
SUBJECT = "thierry_groell_etfuels_com"
REASON = "ticket GEX-4471: user cannot open their own canvas"


def _admin_log_rows(subject: str) -> list[dict]:
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute(
            "SELECT admin_user_id, action, target_user_id, justification "
            "FROM admin_log WHERE action = %s AND target_user_id = %s "
            "ORDER BY id DESC", (break_glass.ACTION, subject))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


@pytest.fixture
def audit_cleanup():
    """Remove exactly the audit rows this test creates, and nothing else.

    Break-glass commits its record on purpose, so these tests really do write
    the development `admin_log`. Left alone they would add two rows per run —
    the same slow pollution the `isolated_store` fixture exists to prevent,
    which `isolated_store` cannot help with here because these tests must reach
    PostgreSQL to mean anything. Deletion is bounded by the highest id that
    existed before the test, so a real audit row can never be caught by it.
    """
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM admin_log")
        watermark = cur.fetchone()[0]
    finally:
        conn.close()

    yield

    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("DELETE FROM admin_log WHERE id > %s AND action = %s",
                    (watermark, break_glass.ACTION))
        conn.commit()
    finally:
        conn.close()


# ── Refusals: each one is a way of getting in quietly, closed ───────────────

@pytest.mark.parametrize("kwargs, why", [
    (dict(actor_user_id="", subject_user_id=SUBJECT, purpose="SUPPORT", reason=REASON),
     "anonymous actor"),
    (dict(actor_user_id=ACTOR, subject_user_id="", purpose="SUPPORT", reason=REASON),
     "no subject — there is no 'everyone' call"),
    (dict(actor_user_id=ACTOR, subject_user_id=SUBJECT, purpose="SUPPORT", reason="   "),
     "empty reason"),
    (dict(actor_user_id=ACTOR, subject_user_id=SUBJECT, purpose="SUPPORT", reason="because"),
     "reason too short to act on later"),
    (dict(actor_user_id=ACTOR, subject_user_id=SUBJECT, purpose="CURIOSITY", reason=REASON),
     "purpose outside the three that justified this path"),
    (dict(actor_user_id=ACTOR, subject_user_id=ACTOR, purpose="SUPPORT", reason=REASON),
     "actor is the subject — that is not break-glass"),
])
def test_it_refuses(kwargs, why):
    with pytest.raises(BreakGlassRefused):
        open_owner_workspace(**kwargs)


def test_a_refused_call_writes_no_record():
    """A refusal is not an access, so it must not leave an audit row implying
    one. The log is for what actually happened."""
    requires_pg()
    before = len(_admin_log_rows(SUBJECT))
    with pytest.raises(BreakGlassRefused):
        open_owner_workspace(actor_user_id=ACTOR, subject_user_id=SUBJECT,
                             purpose="CURIOSITY", reason=REASON)
    assert len(_admin_log_rows(SUBJECT)) == before


# ── The granted path ────────────────────────────────────────────────────────

def test_it_records_before_it_opens_and_scopes_to_the_subject(audit_cleanup):
    requires_pg()
    if workspace_is_postgres() is False:
        pytest.skip("WORKSPACE_DB_BACKEND is sqlite — break-glass refuses there")

    before = len(_admin_log_rows(SUBJECT))
    conn = open_owner_workspace(
        actor_user_id=ACTOR, subject_user_id=SUBJECT,
        purpose="SUPPORT", reason=REASON, context={"ticket": "GEX-4471"})
    try:
        rows = conn.execute(
            "SELECT COUNT(DISTINCT owner_user_id) AS n FROM canvas_blobs").fetchone()["n"]
        owner = conn.execute(
            "SELECT DISTINCT owner_user_id AS o FROM canvas_blobs").fetchone()
    finally:
        conn.close()

    after = _admin_log_rows(SUBJECT)
    assert len(after) == before + 1, "the access was not recorded"
    entry = after[0]
    assert entry["admin_user_id"] == ACTOR
    assert entry["target_user_id"] == SUBJECT
    assert "GEX-4471" in entry["justification"] and "[SUPPORT]" in entry["justification"]

    # Scoped to the subject: one owner's rows, and that owner is the subject.
    assert rows <= 1, f"break-glass exposed {rows} owners — it must name one"
    if owner is not None:
        assert owner["o"] == SUBJECT


def test_the_record_survives_an_access_that_fails(audit_cleanup):
    """The reason the audit row is committed first.

    A log written after the read would only ever contain successful accesses —
    the half that needs auditing least. Here the read raises, and the record
    must still be there.
    """
    requires_pg()
    if workspace_is_postgres() is False:
        pytest.skip("WORKSPACE_DB_BACKEND is sqlite — break-glass refuses there")

    before = len(_admin_log_rows(SUBJECT))
    conn = open_owner_workspace(
        actor_user_id=ACTOR, subject_user_id=SUBJECT,
        purpose="OFFBOARDING", reason="leaver GEX-9002: export then delete")
    try:
        with pytest.raises(Exception):
            conn.execute("SELECT * FROM a_table_that_does_not_exist").fetchone()
    finally:
        conn.close()

    after = _admin_log_rows(SUBJECT)
    assert len(after) == before + 1, (
        "an access that failed left no record — the audit row is being written "
        "after the read instead of before it")
    assert "[OFFBOARDING]" in after[0]["justification"]
