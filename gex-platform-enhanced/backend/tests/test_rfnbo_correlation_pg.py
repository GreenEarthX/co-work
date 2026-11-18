"""
RFNBO correlation computed from meters and PPAs (migration 099, GreenMesh Phase 1 Step 4).

Meter and PPA readings arrive through the real ingest route, periods and PPAs through
the chain-of-custody routes, in the throwaway database of conftest.pg_store.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

OWNER = "test_rfnbo_owner"
TEST_USER = "usr_test_custody"
PROJECT = "proj_TEST_rfnbo"
BASE = "/api/v1/chain-of-custody"
ZONE = "DE-LU"


def _superuser(pg_url: str):
    from pg_support import connect_dsn

    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = _superuser(pg_store)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, 'TEST rfnbo', "
                    "'PRODUCER') ON CONFLICT DO NOTHING", (OWNER,))
        cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                    "VALUES (%s, 'TEST rfnbo', %s, 'H2') ON CONFLICT DO NOTHING", (PROJECT, OWNER))
        conn.commit()
    finally:
        conn.close()
    return pg_store


@pytest.fixture
def client(seeded, monkeypatch):
    import app.core.projects_store as ps
    from app.api.v1.mass_balance import router as custody
    from app.api.v1.routes_plant_data import router as plant
    from app.core.request_tenant import (reset_current_company, reset_current_user,
                                         set_current_company, set_current_user)

    monkeypatch.setattr(ps, "fetch_project", lambda pid: {"project_id": pid, "project_name": "TEST"})
    app = FastAPI()
    app.include_router(custody)
    app.include_router(plant, prefix="/api/v1/plant-data")

    @app.middleware("http")
    async def _as_owner(request, call_next):
        token = set_current_company(OWNER)
        # The signed-in user, as ABACMiddleware binds it: custody actors come from it (G-20).
        utoken = set_current_user(request.headers.get("x-test-user", TEST_USER))
        try:
            return await call_next(request)
        finally:
            reset_current_user(utoken)
            reset_current_company(token)

    return TestClient(app)


class Plant:
    """One facility: its gateway, profile, period and PPAs."""

    def __init__(self, client, seeded, start="2026-02-01", end="2026-02-28", elec="2026-01-01", profile=True):
        self.c, self.fac = client, f"FAC-{uuid.uuid4().hex[:8]}"
        self.gw = f"GW-TEST-{uuid.uuid4().hex[:8]}"
        conn = _superuser(seeded)
        try:
            conn.cursor().execute("INSERT INTO gateway_registry (id, project_id, gateway_name, active, facility_id, "
                                  "ip_allowlist) VALUES (%s, %s, 'TEST', 1, %s, '[]')", (self.gw, PROJECT, self.fac))
            conn.commit()
        finally:
            conn.close()
        if profile:
            r = client.post(f"{BASE}/facility-profiles", json={
                "project_id": PROJECT, "facility_id": self.fac, "bidding_zone": ZONE,
                "electrolyser_commissioning_date": elec, "source": "TEST", "recorded_by": "test"})
            assert r.status_code == 201, r.text
        r = client.post(f"{BASE}/periods", json={
            "project_id": PROJECT, "facility_id": self.fac, "molecule": "H2", "pathway": "PEM", "scheme": "TEST",
            "period_start": start, "period_end": end, "opened_by": "test"})
        assert r.status_code == 201, r.text
        self.period = r.json()["period_id"]

    def ppa(self, ref="PPA-1", zone=ZONE, commissioned="2025-06-01"):
        r = self.c.post(f"{BASE}/ppas", json={
            "project_id": PROJECT, "facility_id": self.fac, "ppa_ref": f"{ref}-{self.fac}", "generator_id": "GEN-T",
            "generator_bidding_zone": zone, "generator_commissioning_date": commissioned,
            "evidence_ref": "PPA-CONTRACT-TEST", "recorded_by": "test"})
        assert r.status_code == 201, r.text
        return r.json()["ppa_ref"]

    def push(self, data_type, mwh, start, end, ppa_ref=None, expect=200):
        payload = {"quantity": mwh, "unit": "MWh", "interval_start": start, "interval_end": end}
        if ppa_ref:
            payload["ppa_ref"] = ppa_ref
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        r = self.c.post("/api/v1/plant-data/ingest", json={
            "gateway_id": self.gw, "project_id": PROJECT, "data_type": data_type, "payload": payload,
            "sha256_hash": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()})
        assert r.status_code == expect, r.text
        return r

    def correlation(self):
        r = self.c.get(f"{BASE}/periods/{self.period}/rfnbo-correlation")
        assert r.status_code == 200, r.text
        return r.json()


FEB = ("2026-02-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00")


def test_the_rules_are_dated_data_not_code(seeded):
    from pg_support import connect_dsn

    from app.api.v1.mass_balance import _refuse  # noqa: F401 — module imports cleanly
    from app.core.rfnbo_correlation import granularity_on

    class _C:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, params=()):
            from app.core.db_backend import _PgCursor, _to_pg

            cur = self.conn.cursor()
            cur.execute(_to_pg(sql), tuple(params))
            return _PgCursor(cur)

    conn = connect_dsn(seeded)
    try:
        assert granularity_on(_C(conn), date(2029, 12, 31))[0] == "MONTHLY"
        assert granularity_on(_C(conn), date(2030, 1, 1))[0] == "HOURLY"
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(Exception, match="permission denied"):
            cur.execute("UPDATE rfnbo_rule SET valid_to = NULL")
    finally:
        conn.rollback()
        conn.close()


def test_monthly_matching_passes_when_generation_covers_consumption(client, seeded):
    p = Plant(client, seeded)
    ref = p.ppa()
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", 120, *FEB, ppa_ref=ref)
    r = p.correlation()
    assert r["basis"] == "COMPUTED" and r["status"] == "PASS", r
    assert r["temporal"]["buckets"]["2026-02"]["granularity"] == "MONTHLY"
    assert "rfnbo-temporal-monthly" in r["rules_used"]


def test_monthly_matching_fails_when_generation_falls_short(client, seeded):
    p = Plant(client, seeded)
    ref = p.ppa()
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", 80, *FEB, ppa_ref=ref)
    r = p.correlation()
    assert r["temporal"]["status"] == "FAIL" and r["status"] == "FAIL"
    assert r["temporal"]["matched_fraction"] == pytest.approx(0.8)


def test_from_2030_matching_is_hourly(client, seeded):
    p = Plant(client, seeded, start="2030-01-01", end="2030-01-31", elec="2027-06-01")
    ref = p.ppa(commissioned="2027-01-01")
    p.push("POWER_CONSUMPTION", 10, "2030-01-05T00:00:00+00:00", "2030-01-05T01:00:00+00:00")
    p.push("PPA_GENERATION", 10, "2030-01-05T00:00:00+00:00", "2030-01-05T01:00:00+00:00", ppa_ref=ref)
    r = p.correlation()
    assert r["temporal"]["status"] == "PASS" and "rfnbo-temporal-hourly" in r["rules_used"]
    assert list(r["temporal"]["buckets"]) == ["2030-01-05T00"]


def test_a_monthly_reading_cannot_satisfy_hourly_matching(client, seeded):
    p = Plant(client, seeded, start="2030-01-01", end="2030-01-31", elec="2027-06-01")
    ref = p.ppa(commissioned="2027-01-01")
    p.push("POWER_CONSUMPTION", 100, "2030-01-01T00:00:00+00:00", "2030-02-01T00:00:00+00:00")
    p.push("PPA_GENERATION", 200, "2030-01-01T00:00:00+00:00", "2030-02-01T00:00:00+00:00", ppa_ref=ref)
    r = p.correlation()
    assert r["temporal"]["status"] == "UNVERIFIED" and "straddle" in r["temporal"]["reason"]


def test_a_ppa_in_another_bidding_zone_is_not_counted(client, seeded):
    p = Plant(client, seeded)
    ref = p.ppa(zone="FR")
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", 200, *FEB, ppa_ref=ref)
    r = p.correlation()
    assert r["geographic"]["status"] == "FAIL" and r["geographic"]["ppas_not_counted_other_zone"] == [ref]
    assert r["temporal"]["status"] == "FAIL" and r["status"] == "FAIL"


def test_an_old_generator_fails_additionality_after_the_transition(client, seeded):
    p = Plant(client, seeded, start="2030-01-01", end="2030-01-31", elec="2029-06-01")
    ref = p.ppa(commissioned="2025-01-01")                 # 53 months before the electrolyser
    p.push("POWER_CONSUMPTION", 10, "2030-01-05T00:00:00+00:00", "2030-01-05T01:00:00+00:00")
    p.push("PPA_GENERATION", 10, "2030-01-05T00:00:00+00:00", "2030-01-05T01:00:00+00:00", ppa_ref=ref)
    r = p.correlation()
    assert r["additionality"]["status"] == "FAIL" and r["status"] == "FAIL"


def test_the_transitional_exemption_applies_to_an_early_electrolyser(client, seeded):
    p = Plant(client, seeded, elec="2026-01-01")
    ref = p.ppa(commissioned="2015-01-01")
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", 100, *FEB, ppa_ref=ref)
    r = p.correlation()
    assert r["additionality"]["status"] == "PASS"
    assert "transitional" in r["additionality"]["per_ppa"][ref]["reason"]


def test_without_a_facility_profile_or_meters_nothing_is_passed(client, seeded):
    p = Plant(client, seeded, profile=False)
    r = p.correlation()
    assert r["status"] == "UNVERIFIED"
    assert r["geographic"]["status"] == "UNVERIFIED" and r["temporal"]["status"] == "UNVERIFIED"


def test_generation_for_an_unregistered_ppa_is_refused(client, seeded):
    p = Plant(client, seeded)
    r = p.push("PPA_GENERATION", 10, *FEB, ppa_ref="NOT-A-PPA", expect=422)
    assert "not registered" in r.json()["detail"]["reason"]


def test_the_closed_statement_records_the_computed_result(client, seeded):
    p = Plant(client, seeded)
    ref = p.ppa()
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", 120, *FEB, ppa_ref=ref)
    closed = client.post(f"{BASE}/periods/{p.period}/close", json={"closed_by": "test"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["position"]["rfnbo_correlation"]["status"] == "PASS"
    assert p.correlation()["basis"] == "COMPUTED"
    assert client.get(f"{BASE}/periods/{p.period}/verify").json()["valid"] is True


def test_the_declared_path_says_declared_and_monthly_expires_in_2030(seeded):
    from app.core.decision_twin import DecisionTwin
    from app.core.request_tenant import (reset_current_company, reset_current_user,
                                         set_current_company, set_current_user)

    token = set_current_company(OWNER)
    try:
        twin = DecisionTwin(project_id=PROJECT)
        now = twin.evaluate_red_iii("H2", 0.35, 100, temporal_matching="monthly",
                                    geographical_correlation=True, as_of=date(2026, 6, 1))
        later = twin.evaluate_red_iii("H2", 0.35, 100, temporal_matching="monthly",
                                      geographical_correlation=True, as_of=date(2030, 6, 1))
    finally:
        reset_current_company(token)
    t_now = next(c for c in now["checks"] if c["check"] == "Temporal Matching")
    t_later = next(c for c in later["checks"] if c["check"] == "Temporal Matching")
    assert now["basis"] == "DECLARED" and t_now["basis"] == "DECLARED"
    assert t_now["passed"] is True and t_now["rule_id"] == "rfnbo-temporal-monthly"
    assert t_later["passed"] is False and t_later["rule_id"] == "rfnbo-temporal-hourly"
    assert later["status"] == "ineligible"


# ── 101: a downstream period carries the correlation of the hydrogen it takes ──

def _chars_h2():
    return {"ghg_intensity_gco2e_mj": 3.0, "pathway": "PEM", "scheme": "TEST", "certificate_id": "CERT-T",
            "country_of_origin": "DE", "production_window_start": "2026-02-01",
            "production_window_end": "2026-02-28", "rfnbo": True, "additionality_basis": "PPA"}


def _hydrogen_lot(client, seeded, generation=120, close=True):
    p = Plant(client, seeded)
    ref = p.ppa()
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", generation, *FEB, ppa_ref=ref)
    r = client.post(f"{BASE}/lots", json={"project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
                                          "total_volume_kg": 1000, "period_id": p.period,
                                          "characteristics": _chars_h2()})
    assert r.status_code == 201, r.text
    if close:
        assert client.post(f"{BASE}/periods/{p.period}/close", json={}).status_code == 200
    return p, r.json()["lot_id"]


def _ammonia_period(client, source_lot_id=None, kg=500):
    r = client.post(f"{BASE}/periods", json={
        "project_id": PROJECT, "facility_id": f"NH3-{uuid.uuid4().hex[:8]}", "molecule": "NH3",
        "pathway": "HABER_BOSCH", "scheme": "TEST", "period_start": "2026-03-01", "period_end": "2026-03-31"})
    assert r.status_code == 201, r.text
    pid = r.json()["period_id"]
    body = {"input_type": "H2", "quantity": kg, "unit": "kg", "sustainability_status": "CERTIFIED",
            "received_on": "2026-03-05", "evidence_kind": "POS", "evidence_ref": "POS-H2-T"}
    if source_lot_id:
        body["source_lot_id"] = source_lot_id
    assert client.post(f"{BASE}/periods/{pid}/inputs", json=body).status_code == 201
    corr = client.get(f"{BASE}/periods/{pid}/rfnbo-correlation")
    assert corr.status_code == 200, corr.text
    return pid, corr.json()


def test_ammonia_from_a_passing_hydrogen_period_passes(client, seeded):
    up, lot = _hydrogen_lot(client, seeded)
    _, c = _ammonia_period(client, lot)
    assert c["basis"] == "COMPUTED" and c["status"] == "PASS", c
    assert c["upstream_hydrogen"]["status"] == "PASS"
    assert c["upstream_hydrogen"]["inputs"][0]["upstream_period_id"] == up.period
    for k in ("temporal", "geographic", "additionality"):
        assert c[k]["status"] == "NOT_APPLICABLE", (k, c[k])


def test_ammonia_from_a_failing_hydrogen_period_fails(client, seeded):
    _, lot = _hydrogen_lot(client, seeded, generation=50)          # generation short of consumption
    _, c = _ammonia_period(client, lot)
    assert c["upstream_hydrogen"]["status"] == "FAIL" and c["status"] == "FAIL", c


@pytest.mark.parametrize("case", ["no source lot", "upstream still open"])
def test_hydrogen_that_cannot_be_traced_is_never_assumed_rfnbo(client, seeded, case):
    lot = _hydrogen_lot(client, seeded, close=(case != "upstream still open"))[1]
    _, c = _ammonia_period(client, None if case == "no source lot" else lot)
    assert c["upstream_hydrogen"]["status"] == "UNVERIFIED" and c["status"] == "UNVERIFIED", c


def test_a_hydrogen_period_is_judged_exactly_as_before(client, seeded):
    p = Plant(client, seeded)
    ref = p.ppa()
    p.push("POWER_CONSUMPTION", 100, *FEB)
    p.push("PPA_GENERATION", 120, *FEB, ppa_ref=ref)
    c = p.correlation()
    assert c["status"] == "PASS" and c["upstream_hydrogen"]["status"] == "NOT_APPLICABLE"


def test_the_pack_shows_the_upstream_check_and_no_inapplicable_item(client, seeded):
    from app.core.custody_ledger import period_row
    from app.core.db_backend import domain_connection
    from app.core.evidence_pack import _compliance_items
    from app.core.request_tenant import reset_current_company, set_current_company

    _, lot = _hydrogen_lot(client, seeded)
    pid, _ = _ammonia_period(client, lot)
    assert client.post(f"{BASE}/periods/{pid}/close", json={}).status_code == 200
    token = set_current_company(OWNER)
    try:
        conn = domain_connection()
        try:
            items = {i["item"]: i for i in _compliance_items(conn, period_row(conn, pid))}
        finally:
            conn.close()
    finally:
        reset_current_company(token)
    assert items["upstream_hydrogen"]["label"] == "VERIFIED" and items["upstream_hydrogen"]["result"] == "PASS"
    assert not {"temporal_correlation", "geographic_correlation", "additionality"} & set(items), sorted(items)
