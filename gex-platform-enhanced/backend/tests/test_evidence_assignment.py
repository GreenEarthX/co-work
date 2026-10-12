"""
Evidence requests belong to named people (migration 055).

An evidence item used to have an owner FUNCTION and no owner. The assign
endpoint names the person, within the company that owns the project only, and
every reassignment reaches the append-only audit trail.

Runs against the isolated SQLite store; never touches the development database.
The account directory is stubbed so the tests do not depend on seed accounts.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1 import routes_bankability_proxy as proxy

PROJECT = "proj_assign_test"
OWNER = "acme_fuels"
KEY = "binding_offtake_contract_executed"

PEOPLE = {
    "u_exec": {"name": "Ada Exec", "business_function": "EXECUTIVE", "company_id": OWNER, "account_state": "ACTIVE"},
    "u_eng": {"name": "Eli Eng", "business_function": "ENGINEERING", "company_id": OWNER, "account_state": "ACTIVE"},
    "u_left": {"name": "Lee Left", "business_function": "ENGINEERING", "company_id": OWNER, "account_state": "SUSPENDED"},
    "u_other": {"name": "Oz Other", "business_function": "EXECUTIVE", "company_id": "rival_co", "account_state": "ACTIVE"},
}


@pytest.fixture
def wired(isolated_store, monkeypatch):
    from app.core.bankability_engine import GATE_REGISTRY

    live = {k for g in GATE_REGISTRY for k in g.required_evidence}
    assert KEY in live, "test key is no longer a live evidence item"
    monkeypatch.setattr(proxy, "_account_directory",
                        lambda ids: {u: PEOPLE[u] for u in ids if u in PEOPLE})
    monkeypatch.setattr(proxy, "_project_owner", lambda pid: OWNER if pid == PROJECT else None)
    actor = {"user_id": "u_exec", "company_id": OWNER, "is_platform_admin": False}
    monkeypatch.setattr(proxy, "_require_actor", lambda authorization: actor)
    return actor


def _assign(assignee, key=KEY, project=PROJECT):
    return asyncio.run(proxy.assign_evidence(
        proxy.EvidenceAssignRequest(project_id=project, evidence_key=key, assignee_user_id=assignee),
        authorization="Bearer x"))


def _commit(due, key=KEY, project=PROJECT):
    return asyncio.run(proxy.commit_evidence(
        proxy.EvidenceCommitRequest(project_id=project, evidence_key=key, due_date=due),
        authorization="Bearer x"))


def _in(days):
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days)).isoformat()


def _events(key=KEY):
    conn = proxy._get_db()
    rows = conn.execute("SELECT old_assignee, new_assignee, new_status, actor, old_due_date, new_due_date "
                        "FROM evidence_events "
                        "WHERE project_id = ? AND evidence_key = ? ORDER BY id", (PROJECT, key)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _code(exc):
    return exc.value.detail["code"]


def test_assigning_an_item_with_no_row_creates_an_uncommitted_request(wired):
    out = _assign("u_eng")
    assert out["status"] == "NOT_STARTED" and out["commitment"] == "NOT_COMMITTED"
    (item,) = [e for e in proxy._load_evidence(PROJECT) if e["key"] == KEY]
    assert item["assignee_user_id"] == "u_eng" and item["due_date"] is None
    last = _events()[-1]
    assert (last["old_assignee"], last["new_assignee"], last["new_status"], last["actor"]) == \
        (None, "u_eng", "NOT_STARTED", "u_exec")


def test_reassignment_is_audited_and_keeps_the_status(wired):
    proxy._upsert_evidence(PROJECT, KEY, "IN_PROGRESS", actor="u_eng")
    _assign("u_exec")
    last = _events()[-1]
    assert (last["old_assignee"], last["new_assignee"], last["new_status"]) == ("u_eng", "u_exec", "IN_PROGRESS")


def test_assigning_the_same_person_again_changes_nothing(wired):
    _assign("u_exec")
    before = len(_events())
    _assign("u_exec")
    assert len(_events()) == before


def test_another_company_cannot_assign(wired):
    wired.update(company_id="rival_co", user_id="u_other")
    with pytest.raises(HTTPException) as exc:
        _assign("u_eng")
    assert exc.value.status_code == 403 and _code(exc) == "NOT_PROJECT_OWNER"


def test_a_platform_admin_can_assign(wired):
    wired.update(company_id="greenearthx", user_id="u_admin", is_platform_admin=True)
    assert _assign("u_eng")["assignee_user_id"] == "u_eng"


@pytest.mark.parametrize("assignee", ["u_other", "u_left", "u_nobody"])
def test_only_an_active_account_of_the_owner_can_be_assigned(wired, assignee):
    """Routing a request to another tenant would disclose the project to it."""
    with pytest.raises(HTTPException) as exc:
        _assign(assignee)
    assert _code(exc) == "ASSIGNEE_NOT_AN_ACTIVE_ACCOUNT_OF_THE_OWNER"


def test_a_project_without_an_owner_cannot_be_assigned(wired):
    with pytest.raises(HTTPException) as exc:
        _assign("u_eng", project="default")
    assert _code(exc) == "PROJECT_HAS_NO_OWNER"


def test_a_retired_key_cannot_be_assigned(wired):
    with pytest.raises(HTTPException) as exc:
        _assign("u_eng", key="eia_submission")
    assert _code(exc) == "EVIDENCE_KEY_RETIRED"


# ── Commitment: the assignee accepts by committing to a date (057) ──────────

def test_the_assignee_commits_and_the_change_is_audited(wired):
    _assign("u_exec")
    out = _commit(_in(30))
    assert out["commitment"] == "COMMITTED" and out["committed_by"] == "u_exec"
    last = _events()[-1]
    assert (last["old_due_date"], last["new_due_date"]) == (None, _in(30))


def test_only_the_assignee_can_commit_not_even_a_platform_admin(wired):
    _assign("u_eng")
    with pytest.raises(HTTPException) as exc:
        _commit(_in(10))                                  # actor is u_exec
    assert _code(exc) == "ONLY_THE_ASSIGNEE_CAN_COMMIT"
    wired.update(user_id="u_admin", company_id="greenearthx", is_platform_admin=True)
    with pytest.raises(HTTPException) as exc:
        _commit(_in(10))
    assert _code(exc) == "ONLY_THE_ASSIGNEE_CAN_COMMIT"


def test_a_date_in_the_past_cannot_be_committed_to(wired):
    _assign("u_exec")
    with pytest.raises(HTTPException) as exc:
        _commit(_in(-1))
    assert _code(exc) == "DUE_DATE_INVALID"


def test_a_malformed_date_is_refused(wired):
    _assign("u_exec")
    with pytest.raises(HTTPException) as exc:
        _commit("30/11/2026")
    assert _code(exc) == "DUE_DATE_INVALID"


def test_an_unassigned_request_cannot_be_committed(wired):
    _assign(None)
    with pytest.raises(HTTPException) as exc:
        _commit(_in(5))
    assert _code(exc) == "NOT_ASSIGNED"


def test_moving_a_committed_date_is_recorded_as_a_slip(wired):
    _assign("u_exec")
    _commit(_in(5))
    out = _commit(_in(20))
    assert out["moved_from"] == _in(5)
    last = _events()[-1]
    assert (last["old_due_date"], last["new_due_date"]) == (_in(5), _in(20))


def test_reassignment_clears_the_date_because_it_was_the_previous_persons_word(wired):
    _assign("u_exec")
    _commit(_in(15))
    _assign("u_eng")
    (item,) = [e for e in proxy._load_evidence(PROJECT) if e["key"] == KEY]
    assert item["due_date"] is None and item["committed_at"] is None
    assert _events()[-1]["old_due_date"] == _in(15)


def test_unassigning_is_allowed_and_audited(wired):
    _assign("u_eng")
    _assign(None)
    assert _events()[-1]["new_assignee"] is None


def test_my_requests_put_uncommitted_first_and_hide_verified(wired):
    _assign("u_exec", key="offtake_credit_assessment")
    _assign("u_exec", key=KEY)
    proxy._upsert_evidence(PROJECT, KEY, "VERIFIED", actor="reviewer")
    out = asyncio.run(proxy.list_my_evidence_requests(authorization="Bearer x"))
    keys = {r["evidence_key"] for r in out["requests"]}
    assert "offtake_credit_assessment" in keys and KEY not in keys
    assert all(r["gate_id"] for r in out["requests"])


def test_gate_views_carry_owner_commitment_and_what_the_caller_may_do(wired):
    evidence = [
        {"key": KEY, "status": "IN_PROGRESS", "assignee_user_id": "u_eng", "due_date": _in(-3),
         "committed_at": "2026-09-01 10:00:00", "notes": "n"},
        {"key": "take_or_pay_floor", "status": "NOT_STARTED", "assignee_user_id": "u_exec",
         "due_date": None, "committed_at": None},
    ]
    snap = {"gate_evaluations": [{"gate_id": "G4", "evidence_detail": [
        {"key": KEY, "status": "IN_PROGRESS"}, {"key": "take_or_pay_floor", "status": "NOT_STARTED"},
        {"key": "other"}]}]}
    gate = proxy._attach_assignments(snap, evidence, wired, PROJECT)["gate_evaluations"][0]
    late, mine, other = gate["evidence_detail"]
    assert (late["assignee_name"], late["commitment"], late["days_overdue"]) == ("Eli Eng", "OVERDUE", 3)
    assert late["can_commit"] is False and late["can_assign"] is True      # caller is u_exec, owner
    assert mine["commitment"] == "NOT_COMMITTED" and mine["can_commit"] is True
    assert (gate["overdue_count"], gate["uncommitted_count"]) == (1, 1)
    assert "assignee_user_id" not in other


def test_another_company_sees_no_reassign_control(wired):
    wired.update(company_id="rival_co", user_id="u_other")
    evidence = [{"key": KEY, "status": "NOT_STARTED", "assignee_user_id": "u_eng"}]
    snap = {"gate_evaluations": [{"evidence_detail": [{"key": KEY, "status": "NOT_STARTED"}]}]}
    (item,) = proxy._attach_assignments(snap, evidence, wired, PROJECT)["gate_evaluations"][0]["evidence_detail"]
    assert item["can_assign"] is False and item["can_commit"] is False


def test_assignable_accounts_are_the_owners_only(wired, monkeypatch):
    wired.update(company_id="rival_co", user_id="u_other")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(proxy.list_assignable_accounts(project_id=PROJECT, authorization="Bearer x"))
    assert exc.value.status_code == 403


# ── Requests on items the project does not need ─────────────────────────────
# The 2026-09-26 conversion raised six requests for items that do not apply to
# their project's power model — four of them asking HamburgOne people for
# behind-the-meter generation evidence on a grid-connected plant — because the
# platform could not tell. The gate screen then counted them as open work.

BTM_KEY = "btm_generation_asset_evidence"   # OFF_GRID_BTM / HYBRID only


def _premise(power_model, financing_model):
    return lambda pid: {"power_model": power_model, "project_phase": None, "financing_model": financing_model}


@pytest.fixture
def grid_connected(wired, monkeypatch):
    monkeypatch.setattr(proxy, "_physical_payload", _premise("GRID_CONNECTED", "PROJECT_FINANCE"))
    conn = proxy._get_db()
    proxy._ensure_tables(conn)   # a refused write never creates them; _events() reads them
    conn.close()
    return wired


def _raise_request(key, assignee):
    """A request row as the conversion left it, before any applicability check.
    The store is shared by the whole module (isolated_store is module-scoped),
    so any earlier row for the key is replaced."""
    conn = proxy._get_db()
    proxy._ensure_tables(conn)
    conn.execute("DELETE FROM bankability_evidence WHERE project_id = ? AND evidence_key = ?", (PROJECT, key))
    conn.execute("INSERT INTO bankability_evidence (project_id, evidence_key, status, assignee_user_id, "
                 "updated_at) VALUES (?, ?, 'NOT_STARTED', ?, datetime('now'))", (PROJECT, key, assignee))
    conn.commit()
    conn.close()


def test_nobody_can_be_asked_for_evidence_the_project_does_not_need(grid_connected):
    with pytest.raises(HTTPException) as exc:
        _assign("u_eng", key=BTM_KEY)
    assert exc.value.status_code == 422 and _code(exc) == "ITEM_NOT_APPLICABLE"
    assert exc.value.detail["reason"] == "POWER_MODEL"
    assert _events(BTM_KEY) == []


def test_lender_protection_is_not_requested_of_a_balance_sheet_project(grid_connected, monkeypatch):
    monkeypatch.setattr(proxy, "_physical_payload", _premise("GRID_CONNECTED", "BALANCE_SHEET"))
    with pytest.raises(HTTPException) as exc:
        _assign("u_eng", key="step_in_rights")
    assert exc.value.detail["reason"] == "FINANCING_MODEL"
    assert _assign("u_eng")["commitment"] == "NOT_COMMITTED"     # a commercial item still can be


def test_such_a_request_cannot_be_committed_to_but_can_be_withdrawn(grid_connected):
    _raise_request(BTM_KEY, "u_exec")
    with pytest.raises(HTTPException) as exc:
        _commit(_in(10), key=BTM_KEY)
    assert exc.value.status_code == 409 and _code(exc) == "ITEM_NOT_APPLICABLE"
    assert _assign(None, key=BTM_KEY)["commitment"] == "UNASSIGNED"
    assert _events(BTM_KEY)[-1]["new_assignee"] is None


def test_the_gate_view_does_not_count_it_as_open_work(grid_connected):
    evidence = [{"key": BTM_KEY, "status": "NOT_STARTED", "assignee_user_id": "u_eng", "due_date": _in(-5),
                 "committed_at": "2026-09-01 10:00:00"},
                {"key": KEY, "status": "NOT_STARTED", "assignee_user_id": "u_eng"}]
    snap = {"gate_evaluations": [{"evidence_detail": [
        {"key": BTM_KEY, "status": "NOT_APPLICABLE"}, {"key": KEY, "status": "NOT_STARTED"}]}]}
    gate = proxy._attach_assignments(snap, evidence, grid_connected, PROJECT)["gate_evaluations"][0]
    na, live = gate["evidence_detail"]
    assert na["commitment"] == "NOT_REQUIRED" and na["assignee_name"] == "Eli Eng"
    assert na["can_commit"] is False and na["can_assign"] is False and na["can_withdraw"] is True
    assert (gate["overdue_count"], gate["uncommitted_count"]) == (0, 1)   # the past date is not "overdue"
    assert live["can_assign"] is True


def test_my_requests_list_it_apart_and_count_it_nowhere(grid_connected):
    live_key = "offtake_seller_obligations"   # applies to every premise
    _raise_request(BTM_KEY, "u_exec")
    _raise_request(live_key, "u_exec")
    out = asyncio.run(proxy.list_my_evidence_requests(authorization="Bearer x"))
    open_keys = {r["evidence_key"] for r in out["requests"]}
    assert live_key in open_keys and BTM_KEY not in open_keys
    assert out["count"] == len(out["requests"])
    assert out["not_committed"] == sum(r["commitment"] == "NOT_COMMITTED" for r in out["requests"])
    assert (BTM_KEY, "POWER_MODEL") in {(r["evidence_key"], r["not_applicable_reason"]) for r in out["not_required"]}
