"""
Part 3 of "project data out of code" (JML, 2026-10-25): the per-project data the
FRONTEND held — banker snapshots, capital stacks, certification and insurance
schedules, term sheets, timelines, drawdowns, plant presets … — lives in
project_dataset (alembic 069/071) and reaches the screens through
GET /api/v1/projects/{id}/datasets/{kind}, read in the caller's tenant.

PostgreSQL parts run in the throwaway database (conftest.pg_store). The last
tests guard the screens and the mover's key resolution.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from pg_support import connect_dsn

OWNER, OTHER, PID = "test_fd_owner", "test_fd_other", "proj_TEST_frontend_datasets"
ROOT = Path(__file__).resolve().parents[2]
SCREENS = ROOT / "frontend" / "src"


@pytest.fixture(scope="module")
def client(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, OTHER):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                    "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                "VALUES (%s, 'TEST datasets plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    cur.execute("INSERT INTO project_dataset (project_id, kind, payload, source) VALUES (%s, 'term_sheet', %s, 'TEST') "
                "ON CONFLICT DO NOTHING", (PID, json.dumps([{"term": "TEST price", "status": "AGREED"}])))
    conn.commit()
    conn.close()

    from app.api.v1.routes_projects import router

    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(router, prefix="/api/v1/projects")
    from app.db import session

    saved = session._sync_engine
    session._sync_engine = None
    try:
        yield TestClient(app)
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved


def _get(client, kind, company):
    h = {"x-test-payload": json.dumps({"user_id": "u_test", "company_id": company})} if company else {}
    return client.get(f"/api/v1/projects/{PID}/datasets/{kind}", headers=h)


def test_the_projects_company_reads_its_dataset_marked_unverified(client):
    r = _get(client, "term_sheet", OWNER)
    assert r.status_code == 200, r.text
    assert r.json()["payload"] == [{"term": "TEST price", "status": "AGREED"}]
    assert r.json()["verification_state"] == "UNVERIFIED"


def test_another_company_gets_not_recorded_and_nothing_else(client):
    r = _get(client, "term_sheet", OTHER)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "NOT_RECORDED"


def test_unrecorded_kind_unknown_kind_and_no_caller(client):
    assert _get(client, "insurance_schedule", OWNER).json()["detail"]["code"] == "NOT_RECORDED"
    assert _get(client, "deal_inputs", OWNER).status_code == 404       # backend kinds are not served raw
    assert _get(client, "term_sheet", None).status_code == 401


def _mover():
    spec = importlib.util.spec_from_file_location(
        "mover", ROOT / "backend" / "scripts" / "move_frontend_datasets_20261025.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_mover_resolves_aliases_keeps_the_current_id_and_drops_defaults():
    rows, notes = _mover().plan(
        [{"kind": "capital_stack", "from": "TEST", "data": {
            "proj_old": {"v": "alias"}, "proj_new": {"v": "current"}, "default": {"v": "d"}, "proj_none": {}}}],
        projects={"proj_new"}, aliases={"proj_old": "proj_new"})
    assert [(r[0], r[2]) for r in rows] == [("proj_new", {"v": "current"})]
    assert any("default" in n for n in notes) and any("proj_none" in n for n in notes)


REMOVED = ("SNAPSHOT_DATA", "CAPITAL_DATA", "CERT_DATA", "V45_DATA", "OFFTAKE_DATA", "SCHEDULE_DATA",
           "TRANSFER_DATA", "PROJECT_CONFIGS", "READINESS_OVERRIDES", "PROJECT_BUYERS", "MOCK_DFI", "MOCK_SPEND",
           "MOCK_TRANCHES", "MOCK_MILESTONES", "generateTimelineData", "buildTerms", "deriveOfftakeData",
           "generatePackHash", "fakeHash", "PORTFOLIO_ROWS", "DEMO_CONTEXT", "DEMO_REQUESTS", "DEMO_KILLERS",
           "SEED_COMPATIBILITY", "FALLBACK_PROJECT_ID", "SEED_TEAM", "loadBreizh", "breizh-reference",
           "proj_breizh_saf", "usr_bp_01", "plant-data/demo", "Math.random() * 0.6")


def test_the_screens_hold_no_per_project_constants_any_more():
    """Negative-verified 2026-10-25: re-adding `const MOCK_SPEND = {}` to SpendWaveView fails this."""
    def code(f: Path) -> str:   # comments say what was removed; only code counts
        return re.sub(r"/\*.*?\*/|//[^\n]*", "", f.read_text(), flags=re.S)

    hits = [(str(f.relative_to(SCREENS)), w) for f in SCREENS.rglob("*.ts*")
            if f.is_file() and "/test/" not in str(f) and ".test." not in f.name
            for w in REMOVED if w in code(f)]
    assert not hits, f"per-project data is back in the frontend: {hits}"
