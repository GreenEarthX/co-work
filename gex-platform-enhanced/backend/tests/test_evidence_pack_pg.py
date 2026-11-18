"""
The lender evidence pack (GreenMesh Phase 1, Step 5) and the Phase 1 GATE.

Gate: one synthetic RFNBO project -> metered production -> lot -> token -> contract ->
settlement -> evidence pack whose COMPLIANCE section holds no DECLARED and no MISSING item.

Custody, meters, PPAs and correlation run through the real routes. The GATE test also runs
the contract and the settlement through the real market engine (listing -> RFQ -> proposal ->
both accept -> four-eye confirmation -> settlement -> payee confirms), on the token allocated
from the custody lot. The other tests keep a synthetic contract row (a hashed event) because
they probe the pack, not the market. Throwaway database (pg_store).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

OWNER = "test_pack_owner"
TEST_USER = "usr_test_custody"
OTHER = "test_pack_other"
PROJECT = "proj_TEST_pack"
CAPACITY = "cap_TEST_pack"
BASE = "/api/v1/chain-of-custody"
FEB = ("2026-02-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00")


def _superuser(pg_url: str):
    from pg_support import connect_dsn

    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


def _su(seeded, sql, params=()):
    conn = _superuser(seeded)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="module")
def seeded(pg_store):
    for company in (OWNER, OTHER):
        _su(pg_store, "INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                      "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
    _su(pg_store, "INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                  "(%s, 'TEST evidence pack (synthetic)', %s, 'H2') ON CONFLICT DO NOTHING", (PROJECT, OWNER))
    _su(pg_store, "INSERT INTO capacities (id, project_name, molecule, capacity_mtpd, project_id) VALUES "
                  "(%s, 'TEST', 'H2', 100000, %s) ON CONFLICT DO NOTHING", (CAPACITY, PROJECT))   # 115: room for every scenario's 50 MTPD token
    return pg_store


@pytest.fixture
def client(seeded, monkeypatch):
    import app.core.projects_store as ps
    from app.api.v1.mass_balance import router as custody
    from app.api.v1.routes_evidence_pack import router as pack
    from app.api.v1.routes_plant_data import router as plant
    from app.core.request_tenant import (reset_current_company, reset_current_user,
                                         set_current_company, set_current_user)

    monkeypatch.setattr(ps, "fetch_project", lambda pid: {"project_id": pid, "project_name": "TEST"})
    app = FastAPI()
    for r in (custody, pack):
        app.include_router(r)
    app.include_router(plant, prefix="/api/v1/plant-data")

    @app.middleware("http")
    async def _as_company(request, call_next):
        token = set_current_company(request.headers.get("x-test-company", OWNER))
        # The signed-in user, as ABACMiddleware binds it: custody actors come from it (G-20).
        utoken = set_current_user(request.headers.get("x-test-user", TEST_USER))
        try:
            return await call_next(request)
        finally:
            reset_current_user(utoken)
            reset_current_company(token)

    return TestClient(app)


def _ok(r, code=201):
    assert r.status_code == code, r.text
    return r.json()


def _push(client, gw, data_type, payload, project=PROJECT):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    _ok(client.post("/api/v1/plant-data/ingest", json={
        "gateway_id": gw, "project_id": project, "data_type": data_type, "payload": payload,
        "sha256_hash": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()}), 200)


def scenario(client, seeded, *, close=True, link_token=True, generation_mwh=60.0, project=PROJECT,
             capacity=CAPACITY, synthetic=True) -> dict:
    PROJECT = project; CAPACITY = capacity  # noqa: E702,N806  (the gate runs on its own project)
    fac, gw = f"FAC-{uuid.uuid4().hex[:8]}", f"GW-TEST-{uuid.uuid4().hex[:8]}"
    token = f"TKN-TEST-PACK-{uuid.uuid4().hex[:8]}"
    _su(seeded, "INSERT INTO gateway_registry (id, project_id, gateway_name, active, facility_id, ip_allowlist) "
                "VALUES (%s, %s, 'TEST', 1, %s, '[]')", (gw, PROJECT, fac))
    _su(seeded, "INSERT INTO tokens (id, capacity_id, molecule, lifecycle_state, tokenised_mtpd, delivery_start, "
                "delivery_end, correlation_id, carbon_intensity_gco2e_mj) VALUES (%s, %s, 'H2', 'MINTED', 50, "
                "'2027-01-01', '2027-12-31', %s, 3.0)", (token, CAPACITY, f"CAP-{token[-8:]}"))
    _ok(client.post(f"{BASE}/facility-profiles", json={
        "project_id": PROJECT, "facility_id": fac, "bidding_zone": "DE-LU",
        "electrolyser_commissioning_date": "2026-01-01", "source": "TEST", "recorded_by": "test"}))
    ppa = _ok(client.post(f"{BASE}/ppas", json={
        "project_id": PROJECT, "facility_id": fac, "ppa_ref": f"PPA-{fac}", "generator_id": "GEN-T",
        "generator_bidding_zone": "DE-LU", "generator_commissioning_date": "2025-06-01",
        "evidence_ref": "PPA-CONTRACT-TEST", "recorded_by": "test"}))["ppa_ref"]
    _ok(client.post(f"{BASE}/conversion-factors", json={
        "project_id": PROJECT, "facility_id": fac, "pathway": "PEM", "molecule": "H2", "input_type": "ELECTRICITY",
        "value": 55, "unit": "kWh/kg", "valid_from": "2026-01-01", "source": "TEST", "recorded_by": "test"}))
    period = _ok(client.post(f"{BASE}/periods", json={
        "project_id": PROJECT, "facility_id": fac, "molecule": "H2", "pathway": "PEM", "scheme": "TEST",
        "period_start": "2026-02-01", "period_end": "2026-02-28", "opened_by": "test"}))["period_id"]
    _ok(client.post(f"{BASE}/periods/{period}/inputs", json={
        "input_type": "ELECTRICITY", "quantity": 55, "unit": "MWh", "sustainability_status": "CERTIFIED",
        "received_on": "2026-02-01", "evidence_kind": "PPA", "evidence_ref": ppa, "recorded_by": "test"}))
    window = {"interval_start": FEB[0], "interval_end": FEB[1]}
    _push(client, gw, "PRODUCTION_VOLUME", {"quantity": 1000, "unit": "kg", "molecule": "H2", **window}, PROJECT)
    _push(client, gw, "POWER_CONSUMPTION", {"quantity": 55, "unit": "MWh", **window}, PROJECT)
    _push(client, gw, "PPA_GENERATION", {"quantity": generation_mwh, "unit": "MWh", "ppa_ref": ppa, **window}, PROJECT)
    lot = _ok(client.post(f"{BASE}/lots", json={
        "project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-01", "total_volume_kg": 1000,
        "created_by": "test", "period_id": period, "characteristics": {
            "ghg_intensity_gco2e_mj": 3.0, "pathway": "PEM", "scheme": "TEST", "certificate_id": "CERT-T",
            "country_of_origin": "DE", "production_window_start": "2026-02-01",
            "production_window_end": "2026-02-28", "rfnbo": True, "additionality_basis": "PPA"}}))
    assert lot["meter_check"] == "RECONCILED", lot
    if link_token:
        _ok(client.post(f"{BASE}/allocate", json={"lot_id": lot["lot_id"], "token_id": token,
                                                  "volume_kg": 1000, "allocated_by": "test"}))
    if close:
        _ok(client.post(f"{BASE}/periods/{period}/close", json={"closed_by": "test"}), 200)

    if not synthetic:
        return {"period": period, "token": token}

    # Synthetic contract and settlement (the older tests; the GATE uses the market engine).
    from app.trading_book import record

    cid, ref = str(uuid.uuid4()), f"TEST-PACK-{uuid.uuid4().hex[:8]}"
    at = datetime.now(timezone.utc)
    _su(seeded, "INSERT INTO tb_contract (id, contract_type, contract_ref, kind, project_id, owner_company_id, "
                "verification_state, created_at, updated_at) VALUES (%s, 'terms', %s, 'offtake', %s, %s, "
                "'UNVERIFIED', now(), now())", (cid, ref, PROJECT, OWNER))
    digest = record.event_hash(contract_ref=ref, seq=1, event_type="MIGRATED", version=None, sub_leg=None,
                               terms_hash=None, actor="test", company=OWNER, note="TEST synthetic", at=at, prev=None)
    _su(seeded, "INSERT INTO tb_contract_event (contract_id, seq, event_type, actor, company_id, note, at, "
                "prev_hash, event_hash, hash_scheme) VALUES (%s, 1, 'MIGRATED', 'test', %s, 'TEST synthetic', %s, "
                "NULL, %s, '2')", (cid, OWNER, at, digest))
    _su(seeded, "INSERT INTO settlement_events (settlement_id, contract_id, project_id, token_id, "
                "counterparty_buyer_id, counterparty_seller_id, settlement_type, settlement_status, volume_kg, "
                "price_per_kg, total_amount, currency, audit_hash, version, created_at, updated_at) VALUES "
                "(%s, %s, %s, %s, 'BUYER-T', %s, 'SPOT', 'CONFIRMED', 1000, 5.0, 5000, 'EUR', 'h', 1, %s, %s)",
        (f"STL-TEST-{uuid.uuid4().hex[:8]}", cid, PROJECT, token, OWNER, at.isoformat(), at.isoformat()))
    return {"contract_id": cid, "period": period, "token": token}


def _pack(client, cid, **kw):
    return _ok(client.get(f"/api/v1/evidence-pack/contract/{cid}", **kw), 200)


GSELLER, GBUYER = "TEST Pack Gate Seller", "TEST Pack Gate Buyer"
GPROJECT, GCAP = "proj_TEST_pack_gate", "cap_TEST_pack_gate"
# D-B (JML 2026-11-14): Commercial acts, the CEO approves the trade confirmation.
GUSERS = {"g_seller": (GSELLER, "COMMERCIAL"), "g_seller2": (GSELLER, "EXECUTIVE"),
          "g_buyer": (GBUYER, "COMMERCIAL"), "g_buyer2": (GBUYER, "EXECUTIVE")}


def _gtoken(uid):
    from app.core.auth import create_access_token

    company, function = GUSERS[uid]
    from app.core import project_registry as reg

    return create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": reg.company_slug(company),
        "company_name": company, "company_type": "PRODUCER", "service_type": None, "business_function": function,
        "user_name": f"TEST {uid}", "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED",
        "nda_signed_with": [], "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": False})[0]


def _market_flow(seeded, token_id, monkeypatch, rfq_mtpd: float = 40) -> dict:
    """Listing -> RFQ -> proposal -> both accept -> four-eye confirmations -> settlement -> payee confirms."""
    from app.api.v1 import routes_approvals, routes_market
    from app.core import abac_middleware as mw
    from app.core import market_engine as me
    from app.core import project_registry as reg
    from app.core.abac_middleware import ABACMiddleware
    from app.core.config import settings
    from app.db import session

    profile = reg.ProjectAccessProfile(project_id=GPROJECT, project_name="TEST pack gate plant",
                                       owner_company_name=GSELLER, associated_company_names=(), jurisdiction="DE")
    look = lambda pid: profile if reg.normalize_project_id(pid) == GPROJECT else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", look)
    monkeypatch.setattr(reg, "get_project_profile", look)
    for uid, (company, function) in GUSERS.items():
        _su(seeded, "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state, is_active) VALUES (%s,%s,'x',%s,%s,'PRODUCER',%s,%s,"
                    "'ACTIVE',1) ON CONFLICT DO NOTHING",
            (uid, f"{uid}@test.invalid", reg.company_slug(company), company, function, f"TEST {uid}"))
    api = FastAPI()
    api.include_router(routes_market.router, prefix="/api/v1/market")
    api.include_router(routes_approvals.router, prefix="/api/v1/approvals")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    mk = TestClient(api)
    h = lambda uid: {"Authorization": f"Bearer {_gtoken(uid)}"}  # noqa: E731

    saved = session._sync_engine
    session._sync_engine = None            # account lookups read the throwaway database
    try:
        conn = _superuser(seeded)
        try:
            cur = conn.cursor()
            cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
            cur.execute("SELECT t.*, c.molecule, c.project_id AS capacity_project_id FROM tokens t "
                        "JOIN capacities c ON c.id = t.capacity_id WHERE t.id = %s", (token_id,))
            tok = dict(cur.fetchone())
        finally:
            conn.close()
        seller = me.Party(business_function="COMMERCIAL", user_id="g_seller", company_id=reg.company_slug(GSELLER), company_name=GSELLER)
        offer = me.create_listing(seller, tok, volume_mtpd=50, price_eur_kg=5.0, delivery_start="2027-01-01",
                                  delivery_end="2027-12-31", location="TEST pack gate")["id"]
        _ok(mk.post(f"/api/v1/market/offers/{offer}/open", headers=h("g_seller")), 200)
        rfq = _ok(mk.post("/api/v1/market/rfqs", headers=h("g_buyer"), json={
            "molecule": "H2", "volume_mtpd": rfq_mtpd, "max_price_eur_kg": 6.0, "delivery_start": "2027-01-01",
            "delivery_end": "2027-12-31"}))["id"]
        _ok(mk.post("/api/v1/market/matches", headers=h("g_buyer"), json={
            "offer_id": offer, "rfq_id": rfq, "delivery_terms": "TEST FOB", "payment_terms": "TEST 30 days"}))
        match = mk.get("/api/v1/market/matches/mine", headers=h("g_buyer")).json()["matches"][0]["id"]
        assert _ok(mk.post(f"/api/v1/market/matches/{match}/accept", headers=h("g_seller")), 200)["status"] == "accepted"
        cid = _ok(mk.post("/api/v1/market/contracts", headers=h("g_buyer"), json={"match_id": match}))["id"]
        for first, second in (("g_seller", "g_seller2"), ("g_buyer", "g_buyer2")):
            req = _ok(mk.post(f"/api/v1/market/contracts/{cid}/confirm", headers=h(first)))["request_id"]
            done = _ok(mk.post(f"/api/v1/market/contracts/{cid}/confirm/{req}/approve", headers=h(second)), 200)
        assert done["trade_status"] == "confirmed"
        stl = _ok(mk.post("/api/v1/market/settlements", headers=h("g_buyer"), json={
            "contract_id": cid, "settlement_type": "SPOT", "volume_kg": 1000}))["settlement_id"]
        out = _ok(mk.post(f"/api/v1/market/settlements/{stl}/confirm", headers=h("g_seller"),
                          json={"payment_reference": "TEST-GATE-001"}), 200)
        assert out["settlement_status"] == "CONFIRMED"
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved
    from pg_support import connect_dsn
    conn = connect_dsn(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        cur.execute("SELECT vt.token_id FROM tb_contract_version_token vt JOIN tb_contract_version v ON v.id = vt.version_id "
                    "WHERE v.contract_id = %s ORDER BY v.version DESC LIMIT 1", (cid,))
        carried = cur.fetchone()["token_id"]
    finally:
        conn.close()
    return {"contract_id": cid, "settlement_id": stl, "token_id": carried}


def test_the_phase_1_gate_every_compliance_item_is_verified_from_data(client, seeded, monkeypatch):
    """The GATE, with the contract and the settlement made by the real market engine on the
    token that was allocated from the custody lot."""
    from app.core import project_registry as reg

    seller = reg.company_slug(GSELLER)
    for company in (GSELLER, GBUYER):
        _su(seeded, "INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (reg.company_slug(company), company))
    _su(seeded, "INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST pack gate plant', %s, 'H2') ON CONFLICT DO NOTHING", (GPROJECT, seller))
    _su(seeded, "INSERT INTO capacities (id, project_name, molecule, capacity_mtpd, project_id) VALUES "
                "(%s, 'TEST', 'H2', 100000, %s) ON CONFLICT DO NOTHING", (GCAP, GPROJECT))   # 115: room for every scenario's 50 MTPD token
    client.headers.update({"x-test-company": seller})
    try:
        s = scenario(client, seeded, project=GPROJECT, capacity=GCAP, synthetic=False)
        flow = _market_flow(seeded, s["token"], monkeypatch)
        pack = _pack(client, flow["contract_id"])
    finally:
        client.headers.pop("x-test-company", None)
    comp = pack["sections"]["compliance"]["items"]
    assert {i["item"] for i in comp} == {"custody_period", "conversion", "metered_production", "metered_electricity",
                                         "temporal_correlation", "geographic_correlation", "additionality"}
    assert [(i["item"], i["label"], i["result"]) for i in comp if (i["label"], i["result"]) != ("VERIFIED", "PASS")] == []
    assert pack["summary"]["compliance"] == {"VERIFIED": 7, "DECLARED": 0, "MISSING": 0, "FAIL": 0}
    assert pack["summary"]["compliance_complete"] is True
    lineage = pack["sections"]["tokens"]["items"][0]
    # The buyer took 40 of the token's 50 MTPD for 2027 (alembic 114, discovery F13): the contract
    # carries a carved child holding 40/50 of the lot's 1000 kg, traced back to the allocated token.
    assert (lineage["label"], lineage["result"], lineage["allocated_kg"]) == ("VERIFIED", "PASS", 800)
    assert lineage["token_id"] != s["token"] and lineage["allocated_to"] == s["token"]
    assert [v["reason"] for v in lineage["via_splits"]] == ["market_acceptance"]
    chain = next(i for i in pack["sections"]["contract"]["items"] if i["item"] == "event_chain")
    assert (chain["label"], chain["result"]) == ("VERIFIED", "PASS")
    assert pack["sections"]["settlement"]["items"], "the real settlement is in the pack"


def test_declared_values_are_never_shown_as_verified(client, seeded):
    pack = _pack(client, scenario(client, seeded)["contract_id"])
    assert {i["label"] for i in pack["sections"]["declared_characteristics"]["items"]} == {"DECLARED"}
    assert {i["label"] for i in pack["sections"]["settlement"]["items"]} == {"DECLARED"}
    assert {i["label"] for i in pack["sections"]["custody"]["items"]} == {"DECLARED"}


def test_an_open_period_makes_the_compliance_section_declared(client, seeded):
    pack = _pack(client, scenario(client, seeded, close=False)["contract_id"])
    assert {i["label"] for i in pack["sections"]["compliance"]["items"]} == {"DECLARED"}
    assert pack["summary"]["compliance_complete"] is False


def test_a_token_backed_by_no_lot_is_missing(client, seeded):
    pack = _pack(client, scenario(client, seeded, link_token=False)["contract_id"])
    assert pack["sections"]["tokens"]["items"][0]["label"] == "MISSING"
    assert pack["summary"]["compliance_complete"] is False


def test_a_failing_computed_check_is_verified_but_fails(client, seeded):
    pack = _pack(client, scenario(client, seeded, generation_mwh=40.0)["contract_id"])
    temporal = next(i for i in pack["sections"]["compliance"]["items"] if i["item"] == "temporal_correlation")
    assert (temporal["label"], temporal["result"]) == ("VERIFIED", "FAIL")
    assert pack["summary"]["compliance"]["FAIL"] == 1 and pack["summary"]["compliance_complete"] is False


def test_the_manifest_is_stable_and_moves_with_the_records(client, seeded):
    s = scenario(client, seeded)
    one, two = _pack(client, s["contract_id"]), _pack(client, s["contract_id"])
    assert one["manifest"] == two["manifest"]
    _su(seeded, "UPDATE settlement_events SET volume_kg = 999 WHERE contract_id = %s", (s["contract_id"],))
    three = _pack(client, s["contract_id"])
    assert three["manifest"]["sections"]["settlement"] != one["manifest"]["sections"]["settlement"]
    assert three["manifest"]["pack_sha256"] != one["manifest"]["pack_sha256"]
    assert three["manifest"]["sections"]["compliance"] == one["manifest"]["sections"]["compliance"]


def test_a_company_that_cannot_read_the_contract_gets_no_pack(client, seeded):
    s = scenario(client, seeded)
    r = client.get(f"/api/v1/evidence-pack/contract/{s['contract_id']}", headers={"x-test-company": OTHER})
    assert r.status_code == 404
