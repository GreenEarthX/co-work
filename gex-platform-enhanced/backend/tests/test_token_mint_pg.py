"""
Minting a token — POST /api/v1/tokens/ (discovery review, 13 Nov 2026, Phase 0).

The isolated probes (tests/probe_discovery_pg.py) OBSERVED, on this route:
  F06  the caller's `verification_state` was stored (CONFIRMED -> shown as "Verified");
  F09  the token was written and the caller got HTTP 500 (`created_at` was never set);
  F10  read-then-insert with no lock: 120 MTPD minted on a 100 MTPD capacity;
  F11  the capacity check summed every token's rate whatever its delivery window;
  F30  a non-owner's mint failed as a 500 carrying the database's RLS message;
  and a refused mint still left a `token.minted` event (the event was written first).

These tests pin the fixes. Real ABAC middleware and the real route, in the throwaway
PostgreSQL database built by the migrations (conftest.pg_store).
"""
from __future__ import annotations

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import tokens_sqlite
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings
from pg_support import connect_dsn

PID = "proj_TEST_token_mint"
OWNER, VIEWER = "TEST Mint Owner", "TEST Mint Stakeholder"
O_ID, V_ID = reg.company_slug(OWNER), reg.company_slug(VIEWER)
CAP = "cap_TEST_mint"
PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST mint plant", owner_company_name=OWNER,
                                   associated_company_names=(VIEWER,), jurisdiction="DE")
USERS = {"m_owner": (OWNER, "PRODUCER"), "m_viewer": (VIEWER, "OFFTAKER")}
DSN: dict = {}


def _auth(uid):
    company, ctype = USERS[uid]
    return {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company),
        "company_name": company, "company_type": ctype, "service_type": None, "business_function": "COMMERCIAL",
        "user_name": uid, "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": False})[0]}


def _q(sql, params=(), company="PLATFORM_ADMIN"):
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


def _total(cap=CAP):
    return float(_q("SELECT COALESCE(SUM(tokenised_mtpd), 0) AS s FROM tokens WHERE capacity_id = %s "
                    "AND lifecycle_state NOT IN ('SPLIT', 'VOIDED')", (cap,))[0]["s"])


def _minted_events():
    return int(_q("SELECT count(*) AS n FROM platform_events WHERE event_type = 'token.minted'")[0]["n"])


def _capacity(cap, mtpd=100):
    _q("INSERT INTO capacities (id, project_id, project_name, molecule, capacity_mtpd, correlation_id) "
       "VALUES (%s, %s, 'TEST mint plant', 'e-Methanol', %s, %s) ON CONFLICT DO NOTHING",
       (cap, PID, mtpd, "CAP-" + cap[-8:].upper()))


@pytest.fixture(scope="module", autouse=True)
def _store(pg_store):
    from app.db import session
    DSN["url"] = pg_store
    for company, ctype in ((OWNER, "PRODUCER"), (VIEWER, "OFFTAKER")):
        _q("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES (%s,%s,%s,'DE') "
           "ON CONFLICT DO NOTHING", (reg.company_slug(company), company, ctype))
    _q("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES (%s,'TEST mint plant',%s,"
       "'e-Methanol') ON CONFLICT DO NOTHING", (PID, O_ID))
    _q("INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by) VALUES "
       "(%s,%s,'OFFTAKER','STAKEHOLDER','TEST') ON CONFLICT DO NOTHING", (PID, V_ID))
    _capacity(CAP)
    saved = session._sync_engine
    session._sync_engine = None
    yield
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def client(monkeypatch):
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    api = FastAPI()
    api.include_router(tokens_sqlite.router, prefix="/api/v1/tokens")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api, raise_server_exceptions=False)


def _mint(client, uid="m_owner", cap=CAP, mtpd=10.0, start="2028-01-01", end="2028-12-31", **extra):
    return client.post("/api/v1/tokens/", headers=_auth(uid), json={
        "capacity_id": cap, "tokenised_mtpd": mtpd, "delivery_start": start, "delivery_end": end, **extra})


@pytest.mark.parametrize("state", ["CONFIRMED", "AUDITED", "SUBMITTED"])
def test_a_minter_cannot_declare_its_token_verified(client, state):
    before, events = _total(), _minted_events()
    r = _mint(client, verification_state=state)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "VERIFICATION_NOT_DECLARABLE"
    assert _total() == before and _minted_events() == events


def test_a_successful_mint_answers_201_unverified_with_its_event(client):
    events = _minted_events()
    r = _mint(client, mtpd=5, verification_state="UNVERIFIED")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verification_state"] == "UNVERIFIED" and body["created_at"]
    stored = _q("SELECT verification_state FROM tokens WHERE id = %s", (body["id"],))
    assert stored and stored[0]["verification_state"] == "UNVERIFIED"
    assert _minted_events() == events + 1


def test_a_stakeholder_cannot_mint_on_the_owners_capacity(client):
    before, events = _total(), _minted_events()
    r = _mint(client, uid="m_viewer", mtpd=1)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "NOT_YOUR_CAPACITY"
    assert "row-level security" not in r.text
    assert _total() == before and _minted_events() == events     # no orphan token.minted event


def test_capacity_is_counted_per_delivery_window(client):
    """Rate on each day, not a lifetime sum: the same plant can fill 2030 and 2031 separately."""
    cap = "cap_TEST_mint_win"
    _capacity(cap, mtpd=100)
    assert _mint(client, cap=cap, mtpd=100, start="2030-01-01", end="2030-12-31").status_code == 201
    assert _mint(client, cap=cap, mtpd=100, start="2031-01-01", end="2031-12-31").status_code == 201
    r = _mint(client, cap=cap, mtpd=1, start="2030-12-01", end="2031-01-31")
    assert r.status_code == 409 and r.json()["detail"]["free_mtpd"] == 0
    assert _mint(client, cap=cap, mtpd=50, start="2032-01-01", end="2032-06-30").status_code == 201


def test_voided_and_split_parents_do_not_consume_capacity(client):
    cap = "cap_TEST_mint_void"
    _capacity(cap, mtpd=100)
    for tid, state in (("tok_TEST_void", "VOIDED"), ("tok_TEST_split", "SPLIT")):
        _q("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
           "lifecycle_state, correlation_id) VALUES (%s, %s, 100, '2028-01-01', '2028-12-31', 'e-Methanol', %s, "
           "'CAP-VOID')", (tid, cap, state))
    assert _mint(client, cap=cap, mtpd=100).status_code == 201


def test_two_concurrent_mints_never_exceed_the_capacity(client):
    """The F10 race, deterministically: another transaction holds the capacity lock with a 60 MTPD
    mint in flight; the API's 60 MTPD mint must wait for it, then be refused."""
    cap = "cap_TEST_mint_race"
    _capacity(cap, mtpd=100)
    locked, release = threading.Event(), threading.Event()

    def other_mint():
        conn = connect_dsn(DSN["url"])
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (O_ID,))
        cur.execute("SELECT id FROM capacities WHERE id = %s FOR UPDATE", (cap,))
        cur.execute("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
                    "lifecycle_state, correlation_id) VALUES ('tok_TEST_race_other', %s, 60, '2028-01-01', "
                    "'2028-12-31', 'e-Methanol', 'MINTED', 'CAP-RACE')", (cap,))
        locked.set()
        release.wait(5)
        conn.commit()
        conn.close()

    t = threading.Thread(target=other_mint)
    t.start()
    assert locked.wait(5)
    timer = threading.Timer(1.0, release.set)      # commit the other mint while the API waits on the lock
    timer.start()
    t0 = time.monotonic()
    r = _mint(client, cap=cap, mtpd=60)
    waited = time.monotonic() - t0
    t.join(5)
    assert r.status_code == 409, r.text
    assert waited >= 0.8, "the API did not wait for the capacity lock"
    assert _total(cap) == 60


def test_a_writer_that_skips_the_lock_is_refused_by_the_database(client):
    """115: the capacity rule is the database's, not only the route's. A raw insert that never
    takes the capacity lock (probe 06 after Phase 0: 120 MTPD on 100) is refused at its commit."""
    import psycopg2

    cap = "cap_TEST_mint_raw"
    _capacity(cap, mtpd=100)
    raw = connect_dsn(DSN["url"])
    try:
        cur = raw.cursor()
        cur.execute("SET app.current_company_id = %s", (O_ID,))
        cur.execute("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
                    "lifecycle_state, correlation_id) VALUES ('tok_TEST_raw', %s, 60, '2028-01-01', '2028-12-31', "
                    "'e-Methanol', 'MINTED', 'CAP-RAW')", (cap,))           # no lock taken, not committed
        assert _mint(client, cap=cap, mtpd=60).status_code == 201       # the API sees nothing committed yet
        with pytest.raises(psycopg2.Error, match="CAPACITY_EXCEEDED"):
            raw.commit()
    finally:
        raw.rollback()
        raw.close()
    assert _total(cap) == 60


def test_one_transaction_cannot_over_tokenise_either():
    import psycopg2

    cap = "cap_TEST_mint_one"
    _capacity(cap, mtpd=100)
    conn = connect_dsn(DSN["url"])
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        for i, (a, b) in enumerate((("2028-01-01", "2028-06-30"), ("2028-06-01", "2028-12-31"))):
            cur.execute("INSERT INTO tokens (id, capacity_id, tokenised_mtpd, delivery_start, delivery_end, molecule, "
                        "lifecycle_state, correlation_id) VALUES (%s, %s, 60, %s, %s, 'e-Methanol', 'MINTED', 'CAP-ONE')",
                        (f"tok_TEST_one_{i}", cap, a, b))                # June: 120 MTPD on one day
        with pytest.raises(psycopg2.Error, match="CAPACITY_EXCEEDED"):
            conn.commit()
    finally:
        conn.rollback()
        conn.close()
    assert _total(cap) == 0
