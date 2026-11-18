"""
One readiness authority (handoff v4, task 1; Part C tests 1 and 2).

Each test states its business rule and builds its own inputs. The gate engine is
never called: one stored snapshot is pinned, and an engine call fails the test,
so a reader that evaluated on its own would be caught.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core import readiness

GATES = ["G0_SITE_RIGHTS", "G1_GRID_UTILITIES_REALITY", "G2_CERTIFICATION_PATH_LOCKED", "G3_INPUTS_SECURED",
         "G4_OFFTAKE_BANKABLE", "G5_EPC_RISK_PRICED", "G6_IE_SIGNOFF", "G7_INSURANCE_BOUND",
         "G8_AUDIT_GRADE_MODEL", "G9_PERMITS_SAFE", "G10_FINANCIAL_CLOSE_CP", "G11_COD_STABILIZATION"]
DETERMINATIONS = ["SATISFIED", "SATISFIED", "INCOMPLETE", "BLOCKED"] + ["INCOMPLETE"] * 8
SNAPSHOT = {
    "project_id": "P1", "current_state": "TECHNICALLY_PLAUSIBLE", "rules_version": "4.8.0",
    "next_state": "COMMERCIALLY_PLAUSIBLE", "evaluated_at": "2026-11-17T09:00:00+00:00",
    readiness.FINGERPRINT_KEY: "fp-1",
    "gate_evaluations": [{"gate_id": g, "gate_name": g, "determination": d, "completion_pct": 50.0,
                          "is_complete": d == "SATISFIED", "blocking_items": [], "evidence_detail": [],
                          "verified_count": 1, "total_evidence": 2}
                         for g, d in zip(GATES, DETERMINATIONS)],
    "capital_unlocks": [], "overall_completion_pct": 40.0,
}
RULES = {"rules_version": "4.8.0", "persona_gates": {"EXECUTIVE": GATES, "FINANCE": GATES[4:11],
                                                     "PRODUCER": GATES}, "state_requirements": {}}


@pytest.fixture
def pinned(monkeypatch):
    import app.api.v1.routes_bankability_proxy as proxy

    async def no_engine(*a, **kw):
        raise AssertionError("a readiness reader called the gate engine instead of the authority")

    async def rules():
        return RULES

    monkeypatch.setattr(proxy, "_call_engine", no_engine)
    monkeypatch.setattr(proxy, "engine_rules", rules)
    monkeypatch.setattr(proxy, "stored_snapshot", lambda pid: (json.loads(json.dumps(SNAPSHOT)), "2026-11-17 09:00"))
    monkeypatch.setattr(readiness, "current_fingerprint", lambda pid: "fp-1")
    monkeypatch.setattr(proxy, "_inputs_moved", lambda pid, snap: False)
    monkeypatch.setattr(proxy, "_load_evidence", lambda pid: [])
    monkeypatch.setattr(proxy, "_require_actor", lambda auth: {"user_id": "u1", "is_platform_admin": True})
    monkeypatch.setattr(proxy, "_attach_assignments", lambda view, *a, **kw: view)
    return proxy


def _decisions(view: dict) -> dict:
    return {g.get("gate_id") or g.get("id"): g.get("determination")
            for g in view.get("gate_evaluations") or view.get("gates") or []}


def test_every_readiness_endpoint_returns_the_same_state_and_gate_decisions(pinned, monkeypatch):
    """Rule (test 1): for one project, snapshot and rules version, every readiness
    endpoint returns the same state and gate decisions, with the same identity."""
    proxy = pinned
    from app.api.v1 import routes_projects
    from app.core.engine_view import bankability_view

    persona = asyncio.run(proxy._persona_view("P1", None, "Bearer x"))
    projects_view = asyncio.run(routes_projects._engine_bankability("P1", {"is_platform_admin": True}, "owner"))
    _, _, stamp = asyncio.run(readiness.current("P1"))

    class Rows:
        def execute(self, *a, **kw):
            return self
        def fetchall(self):
            return [{"project_id": "P1", "current_state": "SPECULATIVE", "snapshot_json": "{}"}]
        def close(self):
            pass
    monkeypatch.setattr(proxy, "_get_db", lambda: Rows())
    monkeypatch.setattr(proxy, "_ensure_tables", lambda conn: None)
    portfolio = asyncio.run(proxy.get_executive_portfolio())["projects"][0]

    states = {persona["current_state"], projects_view["state"], stamp["state"], portfolio["current_state"]}
    assert states == {"TECHNICALLY_PLAUSIBLE"}
    assert _decisions(persona) == _decisions(projects_view) == _decisions(portfolio) == dict(zip(GATES, DETERMINATIONS))
    for s in (persona["readiness"], projects_view["readiness"], portfolio["readiness"]):
        assert (s["evaluated_at"], s["rules_version"], s["evidence_fingerprint"], s["status"]) == \
               ("2026-11-17 09:00", "4.8.0", "fp-1", "CURRENT")
        assert s["project_id"] == "P1" and s["scenario"] == readiness.SCENARIO


def test_structuring_reads_the_same_snapshot(pinned, monkeypatch):
    from app.core import structuring_context as sc

    async def current(pid):
        snap, at = pinned.stored_snapshot(pid)
        return snap, at, readiness.stamp(pid, snap, at, current_fingerprint="fp-1", current_rules_version="4.8.0")

    monkeypatch.setattr(readiness, "current", current)
    snap, at, stamp = asyncio.run(readiness.current("P1"))
    ctx = sc.build_context("P1", identity={"project_id": "P1", "country": "DE", "molecule": "H2", "capex_eur": 1},
                           snapshot=snap, evaluated_at=at, record={"payload": {}}, readiness=stamp)
    assert ctx["stage"] == "TECHNICALLY_PLAUSIBLE" and ctx["readiness"]["evidence_fingerprint"] == "fp-1"


# ── Test 2: freshness ────────────────────────────────────────────────────────

def test_changed_evidence_makes_a_result_stale_and_unjudgeable():
    """Rule (test 2): after evidence changes, results on the old snapshot are stale and
    support no pass/fail judgement."""
    s = readiness.stamp("P1", SNAPSHOT, "t", current_fingerprint="fp-2", current_rules_version="4.8.0")
    assert s["status"] == "STALE" and s["stale_reasons"] == ["EVIDENCE_CHANGED"]
    assert s["supports_judgement"] is False and "no pass/fail" in s["message"]


def test_a_rules_change_makes_a_result_stale():
    s = readiness.stamp("P1", SNAPSHOT, "t", current_fingerprint="fp-1", current_rules_version="4.9.0")
    assert s["status"] == "STALE" and s["stale_reasons"] == ["RULES_CHANGED"] and not s["supports_judgement"]


def test_a_project_with_no_evaluation_shows_not_evaluated_and_no_figure():
    s = readiness.stamp("P1", None, None, current_fingerprint="fp-1", current_rules_version="4.8.0")
    assert s["status"] == "NOT_EVALUATED" and s["state"] is None and s["supports_judgement"] is False
    from app.core.engine_view import bankability_view
    view = bankability_view(None, "EXECUTIVE", RULES["persona_gates"], readiness=s)
    assert view["evaluated"] is False and view["overall_completion"] is None and view["gates"] == []


def test_a_snapshot_with_unknown_inputs_is_never_current():
    snap = {k: v for k, v in SNAPSHOT.items() if k != readiness.FINGERPRINT_KEY}
    s = readiness.stamp("P1", snap, "t", current_fingerprint="fp-1", current_rules_version="4.8.0")
    assert s["status"] == "STALE" and "INPUTS_UNKNOWN" in s["stale_reasons"]


def test_the_fingerprint_moves_with_what_moves_a_gate_and_not_with_assignments():
    ev = [{"key": "k1", "status": "SUBMITTED", "maturity": "AGREED", "valid_until": None,
           "verified_at": None, "document_hash": None, "assignee_user_id": "a", "notes": "x"}]
    base = readiness.inputs_fingerprint(ev, {"power_model": "GRID"})
    assert readiness.inputs_fingerprint([{**ev[0], "assignee_user_id": "b", "notes": "y"}], {"power_model": "GRID"}) == base
    assert readiness.inputs_fingerprint([{**ev[0], "status": "VERIFIED"}], {"power_model": "GRID"}) != base
    assert readiness.inputs_fingerprint(ev, {"power_model": "OFF_GRID_BTM"}) != base


def test_fresh_snapshot_re_evaluates_when_inputs_moved(monkeypatch):
    """A stored state whose inputs moved is re-evaluated before it is read; if the
    engine cannot answer, the reader gets it STALE (test above), never as current."""
    import app.api.v1.routes_bankability_proxy as proxy

    calls = []

    async def rules():
        return RULES

    async def reevaluate(pid, *, reason, actor=None, evidence=None):
        calls.append(reason)
        return {"snapshot": SNAPSHOT, "changes": {}}

    monkeypatch.setattr(proxy, "engine_rules", rules)
    monkeypatch.setattr(proxy, "stored_snapshot", lambda pid: (dict(SNAPSHOT), "t"))
    monkeypatch.setattr(proxy, "_inputs_moved", lambda pid, snap: True)
    monkeypatch.setattr(proxy, "reevaluate", reevaluate)
    asyncio.run(proxy.fresh_snapshot("P1"))
    assert calls == ["inputs changed"]
