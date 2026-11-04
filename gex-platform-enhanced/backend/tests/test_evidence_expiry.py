"""
Evidence expiry on the write path (rules 4.5.0; migration 079).

A validity date is a restriction, so it follows the maker/checker split the maturity axis uses:
the submitter declares it, a reviewer may add one or shorten it and never extend it, and a date
already past is refused. A new submission is a new document and carries its own validity; every
change reaches the append-only audit trail. A stored evaluation whose next_expiry has passed is
stale though nothing was written, and is re-evaluated when read.

Runs against the isolated SQLite store; never touches the development database.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.api.v1 import routes_bankability_proxy as proxy

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_YEAR = (date.today() + timedelta(days=365)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _code(exc: pytest.ExceptionInfo) -> str:
    assert exc.value.status_code == 422
    return exc.value.detail["code"]


def test_a_date_that_is_not_a_date_is_refused():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_valid_until("next spring", "SUBMITTED", None)
    assert _code(exc) == "VALID_UNTIL_INVALID"


def test_evidence_that_expired_before_it_was_filed_is_refused():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_valid_until(YESTERDAY, "SUBMITTED", None)
    assert _code(exc) == "VALID_UNTIL_IN_THE_PAST"


def test_the_submitter_may_declare_any_future_date_and_none_at_all():
    proxy._validate_valid_until(NEXT_YEAR, "SUBMITTED", TOMORROW)
    proxy._validate_valid_until(None, "SUBMITTED", TOMORROW)


def test_a_reviewer_may_add_or_shorten_a_validity_but_never_extend_it():
    """Negative-verified 2026-10-30: removing the extension check lets a reviewer lengthen a permit."""
    proxy._validate_valid_until(TOMORROW, "VERIFIED", None)            # adding one restricts
    proxy._validate_valid_until(TOMORROW, "VERIFIED", NEXT_YEAR)       # shortening
    proxy._validate_valid_until(NEXT_YEAR, "VERIFIED", NEXT_YEAR)      # confirming
    with pytest.raises(HTTPException) as exc:
        proxy._validate_valid_until(NEXT_YEAR, "VERIFIED", TOMORROW)
    assert _code(exc) == "VERIFICATION_CANNOT_EXTEND_VALIDITY"


def _events(project_id: str, key: str) -> list[dict]:
    conn = proxy._get_db()
    rows = conn.execute("SELECT old_valid_until, new_valid_until FROM evidence_events "
                        "WHERE project_id = ? AND evidence_key = ? ORDER BY id", (project_id, key)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _row(project_id: str, key: str) -> dict:
    return next(e for e in proxy._load_evidence(project_id) if e["key"] == key)


def test_validity_is_stored_and_returned_to_the_engine(isolated_store):
    proxy._upsert_evidence("p-exp-1", "eia_permit_granted", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED", valid_until=NEXT_YEAR)
    assert _row("p-exp-1", "eia_permit_granted")["valid_until"] == NEXT_YEAR


def test_a_verification_keeps_the_date_and_a_reviewer_can_shorten_it(isolated_store):
    proxy._upsert_evidence("p-exp-2", "eia_permit_granted", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED", valid_until=NEXT_YEAR)
    proxy._upsert_evidence("p-exp-2", "eia_permit_granted", "VERIFIED", actor="checker@test")
    assert _row("p-exp-2", "eia_permit_granted")["valid_until"] == NEXT_YEAR
    proxy._upsert_evidence("p-exp-2", "eia_permit_granted", "VERIFIED", actor="checker@test",
                           valid_until=TOMORROW)
    assert _row("p-exp-2", "eia_permit_granted")["valid_until"] == TOMORROW


def test_a_new_submission_is_a_new_document_with_its_own_validity(isolated_store):
    """Renewing a permit must not inherit the old one's date — nor lose the new one's."""
    proxy._upsert_evidence("p-exp-3", "eia_permit_granted", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED", valid_until=TOMORROW)
    proxy._upsert_evidence("p-exp-3", "eia_permit_granted", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED", valid_until=NEXT_YEAR)
    assert _row("p-exp-3", "eia_permit_granted")["valid_until"] == NEXT_YEAR
    proxy._upsert_evidence("p-exp-3", "eia_permit_granted", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED")
    assert _row("p-exp-3", "eia_permit_granted")["valid_until"] is None


def test_every_change_of_validity_is_audited_and_an_unchanged_write_adds_nothing(isolated_store):
    proxy._upsert_evidence("p-exp-4", "dsra_funded", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED", valid_until=NEXT_YEAR)
    proxy._upsert_evidence("p-exp-4", "dsra_funded", "SUBMITTED", actor="producer@test",
                           maturity="EXECUTED", valid_until=TOMORROW)
    assert _events("p-exp-4", "dsra_funded")[-1] == {"old_valid_until": NEXT_YEAR, "new_valid_until": TOMORROW}
    before = len(_events("p-exp-4", "dsra_funded"))
    proxy._upsert_evidence("p-exp-4", "dsra_funded", "IN_PROGRESS", actor="producer@test")
    assert len(_events("p-exp-4", "dsra_funded")) == before + 1      # a status change is still an event
    assert _events("p-exp-4", "dsra_funded")[-1] == {"old_valid_until": TOMORROW, "new_valid_until": TOMORROW}


def _stale_run(monkeypatch, next_expiry):
    calls: list[dict] = []
    snap = {"rules_version": "t", "next_expiry": next_expiry, "current_state": "BUILDABLE"}

    async def rules():
        return {"rules_version": "t"}

    async def reeval(project_id, **kw):
        calls.append({"project_id": project_id, **kw})
        return {}

    monkeypatch.setattr(proxy, "stored_snapshot", lambda pid: (snap, "2026-10-01"))
    monkeypatch.setattr(proxy, "engine_rules", rules)
    monkeypatch.setattr(proxy, "reevaluate", reeval)
    asyncio.run(proxy.fresh_snapshot("p-exp-5"))
    return calls


def test_a_stored_evaluation_whose_next_expiry_has_passed_is_reevaluated_on_read(monkeypatch):
    """Negative-verified 2026-10-30: without the next_expiry branch in fresh_snapshot, an expired
    permit keeps the project BUILDABLE until someone happens to upload something."""
    calls = _stale_run(monkeypatch, YESTERDAY)
    assert len(calls) == 1 and calls[0]["reason"] == "evidence expired"


def test_a_stored_evaluation_is_left_alone_until_its_next_expiry_passes(monkeypatch):
    assert _stale_run(monkeypatch, TOMORROW) == []
    assert _stale_run(monkeypatch, None) == []
    assert _stale_run(monkeypatch, date.today().isoformat()) == [], "the last valid day is still valid"
