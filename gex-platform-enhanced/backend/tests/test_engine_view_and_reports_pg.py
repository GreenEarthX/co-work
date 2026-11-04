"""
Gate figures from the engine only; re-evaluation and reports (JML, 2026-10-28).

  1. What a caller sees about gates is the engine's snapshot, scoped to a
     persona derived from the TOKEN (it was a query parameter), with the
     scope stated. Hand-typed profile assessments are never served.
  2. A gate whose checks cannot run is UNRESOLVED (engine 4.2.0); the open-items
     overview lists every open item of every gate side by side.
  3. Every change re-evaluates; a failed re-evaluation withdraws the stored
     state; a change that moves something notifies the designated executives.

Unit tests need nothing; the PostgreSQL ones run in the throwaway database.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.core import engine_view as ev

PERSONA_GATES = {"EXECUTIVE": ["G0", "G1", "G4", "G8"], "PRODUCER": ["G0", "G1"],
                 "FINANCE": ["G4", "G8"], "OFFTAKER": ["G4"], "REGULATOR": ["G1"]}


def _snapshot(**over):
    gates = [
        {"gate_id": "G0", "gate_name": "Site", "determination": "SATISFIED", "completion_pct": 100.0,
         "total_evidence": 1, "verified_count": 1, "is_complete": True, "blocking_items": [], "unlocks_state": "T"},
        {"gate_id": "G1", "gate_name": "Power", "determination": "INCOMPLETE", "completion_pct": 0.0,
         "total_evidence": 1, "verified_count": 0, "is_complete": False, "blocking_items": ["grid_study"],
         "unlocks_state": "T", "evidence_detail": [
             {"key": "grid_study", "applicable": True, "label": "Grid study", "severity": "deal_killer",
              "status": "NOT_STARTED", "owner_function": "ENGINEERING", "blocked_action": "Connection"}]},
        {"gate_id": "G4", "gate_name": "Offtake", "determination": "BLOCKED", "completion_pct": 100.0,
         "total_evidence": 1, "verified_count": 1, "is_complete": False, "blocking_items": [],
         "blocked_reasons": ["C2 failed: Contracted 60,000 t/yr against 45,000"], "unlocks_state": "B"},
        {"gate_id": "G8", "gate_name": "Model", "determination": "UNRESOLVED", "completion_pct": 100.0,
         "total_evidence": 1, "verified_count": 1, "is_complete": False, "blocking_items": [],
         "unresolved_reasons": ["C10 cannot be checked: missing model.debt_tenor_years"], "unlocks_state": "C"},
    ]
    snap = {"current_state": "TECHNICALLY_PLAUSIBLE", "state_label": "x", "rules_version": "4.2.0",
            "overall_completion_pct": 75.0, "gate_evaluations": gates, "gates_blocking_next_state": ["G1"],
            "capital_unlocks": [{"capital_type": "GRANTS_TA", "label": "Grants", "decision_eligible": True,
                                 "gating_gates": ["G0"], "best_progress_pct": 100.0}]}
    snap.update(over)
    return snap


# ── 1. persona from the token ───────────────────────────────────────────────

@pytest.mark.parametrize("payload,owner,expected", [
    ({"is_platform_admin": True}, "own_co", "EXECUTIVE"),
    ({"company_id": "own_co", "business_function": "EXECUTIVE"}, "own_co", "EXECUTIVE"),
    ({"company_id": "own_co", "business_function": "ENGINEERING"}, "own_co", "PRODUCER"),
    ({"company_id": "buyer", "company_type": "OFFTAKER", "business_function": "EXECUTIVE"}, "own_co", "OFFTAKER"),
    ({"company_id": "bank", "service_type": "BANK", "business_function": "EXECUTIVE"}, "own_co", "FINANCE"),
])
def test_the_persona_comes_from_who_the_caller_is(payload, owner, expected):
    assert ev.persona_for(payload, owner) == expected


def test_a_requested_persona_may_narrow_but_never_widen():
    assert ev.narrower_or_equal("OFFTAKER", "FINANCE", PERSONA_GATES)
    assert not ev.narrower_or_equal("EXECUTIVE", "FINANCE", PERSONA_GATES)


def test_the_view_shows_only_the_personas_gates_and_states_the_scope():
    view = ev.bankability_view(_snapshot(), "FINANCE", PERSONA_GATES)
    assert [g["id"] for g in view["gates"]] == ["G4", "G8"]
    assert view["scope"]["visible_gates"] == 2 and view["scope"]["total_gates"] == 4
    assert "all 4 gates" in view["scope"]["note"]
    assert view["state"] == "TECHNICALLY_PLAUSIBLE" and view["source"] == "engine"


def test_capital_is_eligibility_never_money_moved():
    view = ev.bankability_view(_snapshot(), "EXECUTIVE", PERSONA_GATES)
    assert {c["commitment_status"] for c in view["capital_status"]} <= {"DECISION_ELIGIBLE", "NOT_YET_ELIGIBLE"}


def test_no_snapshot_means_not_evaluated_and_no_figure():
    view = ev.bankability_view(None, "EXECUTIVE", PERSONA_GATES)
    assert view["evaluated"] is False and view["overall_completion"] is None and view["gates"] == []


def test_the_served_profile_carries_no_assessment(monkeypatch):
    """Negative-verified 2026-10-28: removing "bankability" from
    _PROFILE_ASSESSMENT_KEYS serves the hand-typed block again."""
    from app.api.v1 import routes_projects as rp
    from app.core import projects_store

    monkeypatch.setattr(projects_store, "fetch_project", lambda pid: {"project_name": "P", "status": "development"})
    monkeypatch.setattr(projects_store, "fetch_project_profile", lambda pid: {"profile": {
        "lat": 1.0, "description": "d", "bankability": {"overall_completion": 52}, "risk_alerts": ["x"]},
        "verification_state": "UNVERIFIED"})
    monkeypatch.setattr(rp, "get_effective_context", lambda pid: None)
    profile = type("P", (), {"project_id": "p", "owner_company_name": "O", "associated_company_names": (),
                             "jurisdiction": "DE"})()
    vp = rp._profile_to_visible(profile)
    assert vp.profile == {"lat": 1.0, "description": "d"}


# ── 2. open items, side by side ─────────────────────────────────────────────

def test_the_overview_lists_every_open_item_of_every_gate_with_its_kind():
    rows = [{"key": "grid_study", "assignee_user_id": None, "due_date": "2026-01-01"}]
    out = ev.open_items(_snapshot(), "EXECUTIVE", PERSONA_GATES, rows, today="2026-10-28")
    kinds = {(i["gate_id"], i["kind"]) for i in out["items"]}
    assert kinds == {("G1", "evidence"), ("G4", "contradiction"), ("G8", "missing_data")}
    assert out["summary"]["overdue"] == 1 and out["summary"]["unassigned"] == 1
    assert out["items"][0]["severity"] == "deal_killer"


# ── 3. re-evaluation, withdrawal, notification (PostgreSQL) ─────────────────

OWNER, PID = "test_er_owner", "proj_TEST_engine_reports"


@pytest.fixture(scope="module")
def seeded(pg_store):
    from pg_support import connect_dsn

    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, 'TEST er', 'PRODUCER') "
                "ON CONFLICT DO NOTHING", (OWNER,))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST er plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    for uid, fn in (("u_er_exec", "EXECUTIVE"), ("u_er_eng", "ENGINEERING")):
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, 'TEST er', 'PRODUCER', "
                    "%s, %s, 'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", OWNER, fn, uid))
    conn.commit()
    conn.close()
    from app.db import session

    saved = session._sync_engine
    session._sync_engine = None
    yield pg_store
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _as(company, user):
    from app.core.request_tenant import set_current_company, set_current_user
    return set_current_company(company), set_current_user(user)


def _reset(tokens):
    from app.core.request_tenant import reset_current_company, reset_current_user
    reset_current_company(tokens[0])
    reset_current_user(tokens[1])


def test_a_change_that_moves_the_state_notifies_the_owners_executives(seeded, monkeypatch):
    from app.api.v1 import routes_bankability_proxy as proxy
    from app.core import bankability_reports as br, project_registry

    monkeypatch.setattr(project_registry, "get_project_profile", lambda pid: type(
        "P", (), {"owner_company_id": OWNER, "stakeholder_company_ids": {OWNER}})())
    states = iter(["SPECULATIVE", "TECHNICALLY_PLAUSIBLE"])

    async def engine(path, method="GET", json_data=None):
        return {"current_state": next(states), "rules_version": "t", "gate_evaluations": [
            {"gate_id": "G0", "gate_name": "Site", "determination": "SATISFIED"}]}
    monkeypatch.setattr(proxy, "_call_engine", engine)
    t = _as(OWNER, "u_er_exec")
    try:
        first = asyncio.run(proxy.reevaluate(PID, reason="first"))
        second = asyncio.run(proxy.reevaluate(PID, reason="premise financing_model"))
    finally:
        _reset(t)
    assert first["changes"]["first_evaluation"] and second["changes"]["state_changed"]
    assert br.recipients.__name__  # default recipients: the owner's EXECUTIVE accounts only
    t = _as(OWNER, "u_er_exec")
    try:
        mine = br.my_notifications()
    finally:
        _reset(t)
    assert [(n["from_state"], n["to_state"]) for n in mine] == [("SPECULATIVE", "TECHNICALLY_PLAUSIBLE")]
    t = _as(OWNER, "u_er_eng")
    try:
        assert br.my_notifications() == []        # not an executive: not a default recipient
        assert br.mark_read(mine[0]["id"]) is False   # and cannot mark another's notification
    finally:
        _reset(t)


def test_a_failed_reevaluation_withdraws_the_stored_state(seeded, monkeypatch):
    """Negative-verified 2026-10-28: without _drop_snapshot the old state stands."""
    from fastapi import HTTPException

    from app.api.v1 import routes_bankability_proxy as proxy

    async def down(path, method="GET", json_data=None):
        raise HTTPException(status_code=503, detail="engine down")
    monkeypatch.setattr(proxy, "_call_engine", down)
    t = _as(OWNER, "u_er_exec")
    try:
        assert proxy.stored_snapshot(PID)[0] is not None
        with pytest.raises(HTTPException):
            asyncio.run(proxy.reevaluate(PID, reason="terms offtake"))
        assert proxy.stored_snapshot(PID) == (None, None)
    finally:
        _reset(t)


def test_no_screen_reads_the_profiles_bankability_any_more():
    hook = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "hooks" / "useVisibleProjects.ts").read_text()
    assert "profile.bankability" not in hook and "sp.bankability" in hook


def test_no_screen_lock_and_no_caller_asserted_rating_come_back():
    """Negative-verified 2026-10-28: restoring a `<GatedRoute` in App.tsx fails this."""
    import re

    src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    banned = ("GatedRoute", "useGateAccess", "GateLock", "/project-ratings", "useProjectRating",
              "gate_prerequisite")
    hits = []
    for f in src.rglob("*.ts*"):
        if not f.is_file() or ".test." in f.name:
            continue
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", f.read_text(), flags=re.S)
        hits += [(f.name, w) for w in banned if w in code]
    assert not hits, f"screen locks or the asserted rating are back: {hits}"
    main = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "routes_project_ratings" not in re.sub(r"#[^\n]*", "", main)


def test_screen_gate_map_is_information_with_one_copy():
    """A screen may feed several gates (a list, never one overwriting another), every
    gate id is the engine's, and the menu carries no second copy (gate_prerequisite,
    banned above). Negative-verified 2026-10-28: restoring the str-valued map fails."""
    import asyncio

    from app.api.v1.routes_gate_registry import GATE_SCREENS, get_screen_gate_map
    from app.core.bankability_engine import GATE_REGISTRY

    m = asyncio.run(get_screen_gate_map())
    assert all(isinstance(v, list) and v for v in m.values())
    assert set(GATE_SCREENS) == {g.id for g in GATE_REGISTRY}
    assert sum(len(v) for v in m.values()) == sum(len(v) for v in GATE_SCREENS.values())
    assert "/projects" not in m, "the project list is not a gate's work screen"


def test_a_submitted_count_reaches_the_screens_beside_the_verified_count():
    """Negative-verified 2026-10-31: dropping the pass-through in bankability_view hides the assertions."""
    from app.core.engine_view import bankability_view

    snap = {"rules_version": "t", "current_state": "SPECULATIVE", "overall_completion_pct": 10.0, "capital_unlocks": [],
            "gate_evaluations": [{"gate_id": "G0_SITE_RIGHTS", "gate_name": "Site", "verified_count": 1,
                                  "submitted_count": 3, "total_evidence": 4, "completion_pct": 25.0}]}
    view = bankability_view(snap, "EXECUTIVE", {"EXECUTIVE": ["G0_SITE_RIGHTS"]}, "2026-10-31")
    assert view["gates"][0]["verified_count"] == 1 and view["gates"][0]["submitted_count"] == 3
