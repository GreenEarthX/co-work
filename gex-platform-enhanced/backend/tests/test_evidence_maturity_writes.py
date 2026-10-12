"""
Evidence write path under rules 3.0.0 — maturity, retirement and the
maker/checker split.

The engine now counts a VERIFIED item only when its declared maturity meets the
item's requirement. That is only a control if the write path refuses to let the
wrong party set maturity, and refuses writes the engine could only misread:

  * a retired key (e.g. eia_submission) — no gate scores it any more, so
    accepting it would record evidence that looks filed and counts for nothing;
  * an unknown key or status — the same, silently;
  * a reviewer RAISING maturity — verification confirms what an instrument is,
    it must never turn a term sheet into a contract (Ambition Gap standard, §4.6).

And every maturity change must reach the append-only audit trail, including one
that leaves the status alone — otherwise the most consequential edit is the only
invisible one.

Runs against the isolated SQLite store; never touches the development database.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1 import routes_bankability_proxy as proxy


def _code(exc: pytest.ExceptionInfo) -> str:
    assert exc.value.status_code == 422
    return exc.value.detail["code"]


# ── Refused writes ────────────────────────────────────────────────────────────

def test_a_retired_key_is_refused_and_names_its_replacement():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_evidence_write("eia_submission", "SUBMITTED", None, None)
    assert _code(exc) == "EVIDENCE_KEY_RETIRED"
    assert exc.value.detail["replaced_by"] == "eia_permit_granted"


def test_every_retired_key_is_refused():
    from app.core.bankability_engine import RETIRED_EVIDENCE

    for key in RETIRED_EVIDENCE:
        with pytest.raises(HTTPException) as exc:
            proxy._validate_evidence_write(key, "SUBMITTED", None, None)
        assert _code(exc) == "EVIDENCE_KEY_RETIRED", key


def test_an_unknown_key_is_refused():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_evidence_write("offtake_vibes_positive", "SUBMITTED", None, None)
    assert _code(exc) == "EVIDENCE_KEY_UNKNOWN"


def test_a_misspelt_status_is_refused_rather_than_stored_and_never_counted():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_evidence_write("eia_permit_granted", "VERIFED", None, None)
    assert _code(exc) == "EVIDENCE_STATUS_UNKNOWN"


def test_an_unknown_maturity_is_refused():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_evidence_write("eia_permit_granted", "SUBMITTED", "SIGNED", None)
    assert _code(exc) == "MATURITY_UNKNOWN"


# ── Maker / checker ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["NOT_STARTED", "IN_PROGRESS", "SUBMITTED"])
def test_the_producer_side_may_declare_and_raise_maturity(status):
    proxy._validate_evidence_write("binding_offtake_contract_executed", status, "EXECUTED", None)
    proxy._validate_evidence_write("binding_offtake_contract_executed", status, "EXECUTED", "INDICATIVE")


@pytest.mark.parametrize("status", ["UNDER_REVIEW", "VERIFIED", "REJECTED", "EXPIRED"])
def test_the_reviewer_side_cannot_raise_maturity(status):
    with pytest.raises(HTTPException) as exc:
        proxy._validate_evidence_write("binding_offtake_contract_executed", status, "EXECUTED", "INDICATIVE")
    assert _code(exc) == "VERIFICATION_CANNOT_RAISE_MATURITY"


def test_the_reviewer_side_cannot_introduce_maturity_the_submitter_never_declared():
    with pytest.raises(HTTPException) as exc:
        proxy._validate_evidence_write("binding_offtake_contract_executed", "VERIFIED", "EXECUTED", None)
    assert _code(exc) == "MATURITY_MUST_BE_DECLARED_AT_SUBMISSION"


def test_the_reviewer_side_may_confirm_or_lower_maturity():
    proxy._validate_evidence_write("binding_offtake_contract_executed", "VERIFIED", "EXECUTED", "EXECUTED")
    proxy._validate_evidence_write("binding_offtake_contract_executed", "VERIFIED", "INDICATIVE", "EXECUTED")


def test_verifying_without_touching_maturity_is_always_allowed():
    proxy._validate_evidence_write("binding_offtake_contract_executed", "VERIFIED", None, None)


# ── Persistence and audit ─────────────────────────────────────────────────────

def _events(project_id: str, key: str) -> list[dict]:
    conn = proxy._get_db()
    rows = conn.execute(
        "SELECT old_status, new_status, old_maturity, new_maturity FROM evidence_events "
        "WHERE project_id = ? AND evidence_key = ? ORDER BY id",
        (project_id, key),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def test_maturity_is_stored_and_returned_to_the_engine(isolated_store):
    proxy._upsert_evidence("p-mat-1", "binding_offtake_contract_executed", "SUBMITTED",
                           actor="producer@test", maturity="EXECUTED")
    row = next(e for e in proxy._load_evidence("p-mat-1")
               if e["key"] == "binding_offtake_contract_executed")
    assert row["maturity"] == "EXECUTED"


def test_a_status_change_without_maturity_keeps_the_declared_maturity(isolated_store):
    proxy._upsert_evidence("p-mat-2", "eia_permit_granted", "SUBMITTED",
                           actor="producer@test", maturity="EXECUTED")
    proxy._upsert_evidence("p-mat-2", "eia_permit_granted", "VERIFIED", actor="checker@test")
    row = next(e for e in proxy._load_evidence("p-mat-2") if e["key"] == "eia_permit_granted")
    assert (row["status"], row["maturity"]) == ("VERIFIED", "EXECUTED")


def test_a_maturity_change_with_no_status_change_is_still_audited(isolated_store):
    proxy._upsert_evidence("p-mat-3", "credit_support_package", "SUBMITTED",
                           actor="producer@test", maturity="INDICATIVE")
    proxy._upsert_evidence("p-mat-3", "credit_support_package", "SUBMITTED",
                           actor="producer@test", maturity="EXECUTED")
    events = _events("p-mat-3", "credit_support_package")
    assert events[-1] == {
        "old_status": "SUBMITTED", "new_status": "SUBMITTED",
        "old_maturity": "INDICATIVE", "new_maturity": "EXECUTED",
    }


def test_an_unchanged_write_adds_no_audit_noise(isolated_store):
    proxy._upsert_evidence("p-mat-4", "dsra_funded", "SUBMITTED",
                           actor="producer@test", maturity="EXECUTED")
    before = len(_events("p-mat-4", "dsra_funded"))
    proxy._upsert_evidence("p-mat-4", "dsra_funded", "SUBMITTED", actor="producer@test")
    assert len(_events("p-mat-4", "dsra_funded")) == before
