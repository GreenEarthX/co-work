"""
Declared against metered (migration 098, GreenMesh Phase 1 Step 3).

Meter readings arrive through the real ingest route (`/api/v1/plant-data/ingest`) and
lots through the real chain-of-custody routes, in the throwaway database of
conftest.pg_store. Every test meters its own facility through its own gateway.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

OWNER = "test_meter_owner"
TEST_USER = "usr_test_custody"
OTHER_PROJECT = "proj_TEST_meter_other"
PROJECT = "proj_TEST_meter"
BASE = "/api/v1/chain-of-custody"
INGEST = "/api/v1/plant-data/ingest"
PATHWAY = "PEM_ELECTROLYSIS"
SCHEME = "TEST_SCHEME"
FEB = ("2026-02-01", "2026-02-28")
WEEKS = [("2026-02-01", "2026-02-08"), ("2026-02-08", "2026-02-15"),
         ("2026-02-15", "2026-02-22"), ("2026-02-22", "2026-03-01")]


def _superuser(pg_url: str):
    from pg_support import connect_dsn

    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = _superuser(pg_store)
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, 'TEST meter owner', "
                    "'PRODUCER') ON CONFLICT DO NOTHING", (OWNER,))
        for pid in (PROJECT, OTHER_PROJECT):
            cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                        "VALUES (%s, 'TEST metering', %s, 'H2') ON CONFLICT DO NOTHING", (pid, OWNER))
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


def _gateway(seeded, facility: str | None, project: str = PROJECT) -> str:
    gid = f"GW-TEST-{uuid.uuid4().hex[:8]}"
    conn = _superuser(seeded)
    try:
        conn.cursor().execute("INSERT INTO gateway_registry (id, project_id, gateway_name, active, facility_id, "
                              "ip_allowlist) VALUES (%s, %s, 'TEST meter', 1, %s, '[]')", (gid, project, facility))
        conn.commit()
    finally:
        conn.close()
    return gid


def _push(client, gw, data_type, payload, project=PROJECT):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return client.post(INGEST, json={
        "gateway_id": gw, "project_id": project, "data_type": data_type, "payload": payload,
        "sha256_hash": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()})


def _produced(client, gw, kg, start, end, unit="kg", qty=None):
    r = _push(client, gw, "PRODUCTION_VOLUME", {
        "quantity": kg if qty is None else qty, "unit": unit, "molecule": "H2",
        "interval_start": f"{start}T00:00:00+00:00", "interval_end": f"{end}T00:00:00+00:00"})
    assert r.status_code == 200, r.text
    return r.json()


def _setup(client, seeded, meter_weeks=WEEKS, kg_per_week=250.0):
    """A facility with a period, a factor and inputs ample for the lot, and its meter."""
    fac = f"FAC-{uuid.uuid4().hex[:8]}"
    gw = _gateway(seeded, fac)
    p = client.post(f"{BASE}/periods", json={
        "project_id": PROJECT, "facility_id": fac, "molecule": "H2", "pathway": PATHWAY, "scheme": SCHEME,
        "period_start": "2026-01-01", "period_end": "2026-03-31", "opened_by": "test"}).json()
    for s, e in meter_weeks:
        _produced(client, gw, kg_per_week, s, e)
    return fac, gw, p


def _lot(client, period_id, kg, window=FEB, expect=201):
    r = client.post(f"{BASE}/lots", json={
        "project_id": PROJECT, "molecule": "H2", "production_date": window[0], "total_volume_kg": kg,
        "created_by": "test", "period_id": period_id, "characteristics": {
            "ghg_intensity_gco2e_mj": 3.0, "pathway": PATHWAY, "scheme": SCHEME, "certificate_id": "CERT-T",
            "country_of_origin": "DE", "production_window_start": window[0],
            "production_window_end": window[1], "rfnbo": True, "additionality_basis": "PPA"}})
    assert r.status_code == expect, r.text
    return r.json()


# ── the three outcomes ────────────────────────────────────────────────────────

def test_a_lot_matching_its_meters_is_reconciled(client, seeded):
    _, _, p = _setup(client, seeded)
    lot = _lot(client, p["period_id"], 1000)
    assert lot["meter_check"] == "RECONCILED"
    assert lot["meter_reconciliation"]["status"] == "RECONCILED"
    assert lot["meter_detail"]["metered"] == pytest.approx(1000) and lot["meter_detail"]["meter_readings"] == 4


def test_a_lot_beyond_its_meters_shows_a_variance_with_zero_tolerance_by_default(client, seeded):
    _, _, p = _setup(client, seeded)
    lot = _lot(client, p["period_id"], 1001)
    assert lot["meter_check"] == "VARIANCE"
    assert lot["meter_detail"]["difference"] == pytest.approx(1)
    assert lot["meter_detail"]["tolerance_source"].startswith("none agreed")


def test_an_agreed_tolerance_absorbs_a_small_difference(client, seeded):
    fac, _, p = _setup(client, seeded)
    r = client.post(f"{BASE}/meter-tolerances", json={
        "project_id": PROJECT, "facility_id": fac, "measure": "PRODUCTION", "molecule": "H2",
        "tolerance_fraction": 0.02, "valid_from": "2026-01-01",
        "source": "TEST — not a real certifier", "recorded_by": "test"})
    assert r.status_code == 201, r.text
    assert _lot(client, p["period_id"], 1015)["meter_check"] == "RECONCILED"


def test_no_meter_readings_leaves_a_lot_unverified(client, seeded):
    _, _, p = _setup(client, seeded, meter_weeks=[])
    lot = _lot(client, p["period_id"], 1000)
    assert lot["meter_check"] == "UNVERIFIED"
    assert "no meter readings" in lot["meter_detail"]["reason"]


def test_partial_meter_coverage_is_unverified_not_a_variance(client, seeded):
    _, _, p = _setup(client, seeded, meter_weeks=WEEKS[:3])
    lot = _lot(client, p["period_id"], 750)
    assert lot["meter_check"] == "UNVERIFIED"
    assert "cover" in lot["meter_detail"]["reason"]


def test_a_reading_straddling_the_window_is_reported_not_prorated(client, seeded):
    fac, gw, p = _setup(client, seeded, meter_weeks=WEEKS[:3])
    _produced(client, gw, 400, "2026-02-22", "2026-03-08")             # straddles 1 March
    lot = _lot(client, p["period_id"], 750)
    assert lot["meter_check"] == "UNVERIFIED"
    assert lot["meter_detail"]["straddling_readings"] == 1


def test_overlapping_lot_windows_cannot_be_attributed(client, seeded):
    _, _, p = _setup(client, seeded)
    _lot(client, p["period_id"], 500, window=("2026-02-01", "2026-02-14"))
    lot = _lot(client, p["period_id"], 500)                             # 1..28 Feb overlaps 1..14
    assert lot["meter_check"] == "UNVERIFIED" and lot["meter_detail"]["overlapping_lots"]


def test_lots_of_the_same_window_are_added_together(client, seeded):
    _, _, p = _setup(client, seeded)
    first = _lot(client, p["period_id"], 600)
    assert first["meter_check"] == "VARIANCE"                           # 600 of 1000 so far
    second = _lot(client, p["period_id"], 400)
    assert second["meter_check"] == "RECONCILED"
    live = client.get(f"{BASE}/lots/{first['lot_id']}").json()["meter_reconciliation"]
    assert live["status"] == "RECONCILED" and live["declared"] == pytest.approx(1000)


def test_the_stored_check_is_fixed_while_the_live_status_follows_the_meters(client, seeded):
    _, gw, p = _setup(client, seeded, meter_weeks=[])
    lot = _lot(client, p["period_id"], 1000)
    assert lot["meter_check"] == "UNVERIFIED"
    for s, e in WEEKS:
        _produced(client, gw, 250, s, e)
    now = client.get(f"{BASE}/lots/{lot['lot_id']}").json()
    assert now["meter_check"] == "UNVERIFIED"                           # what was known at creation
    assert now["meter_reconciliation"]["status"] == "RECONCILED"        # what the meters say now


def test_a_lot_without_a_period_is_unverified_and_says_why(client):
    lot = client.post(f"{BASE}/lots", json={
        "project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
        "total_volume_kg": 10, "created_by": "test"}).json()
    assert lot["meter_check"] is None
    assert lot["meter_reconciliation"]["status"] == "UNVERIFIED"
    assert "no facility" in lot["meter_reconciliation"]["reason"]


def test_the_period_statement_reconciles_production_and_electricity(client, seeded):
    fac, gw, p = _setup(client, seeded, meter_weeks=[("2026-01-01", "2026-04-01")], kg_per_week=1000.0)
    client.post(f"{BASE}/conversion-factors", json={
        "project_id": PROJECT, "facility_id": fac, "pathway": PATHWAY, "molecule": "H2",
        "input_type": "ELECTRICITY", "value": 55, "unit": "kWh/kg", "valid_from": "2026-01-01",
        "source": "TEST", "recorded_by": "test"})
    client.post(f"{BASE}/periods/{p['period_id']}/inputs", json={
        "input_type": "ELECTRICITY", "quantity": 55, "unit": "MWh", "sustainability_status": "CERTIFIED",
        "received_on": "2026-02-01", "evidence_kind": "PPA", "evidence_ref": "PPA-T", "recorded_by": "test"})
    r = _push(client, gw, "POWER_CONSUMPTION", {"quantity": 60, "unit": "MWh",
                                                "interval_start": "2026-01-01T00:00:00+00:00",
                                                "interval_end": "2026-04-01T00:00:00+00:00"})
    assert r.status_code == 200, r.text
    _lot(client, p["period_id"], 1000)
    closed = client.post(f"{BASE}/periods/{p['period_id']}/close", json={"closed_by": "test"})
    assert closed.status_code == 200, closed.text
    m = closed.json()["position"]["meter_reconciliation"]
    assert m["production"]["status"] == "RECONCILED"
    assert m["electricity"]["status"] == "VARIANCE"                     # 55 declared vs 60 metered
    assert m["electricity"]["metered"] == pytest.approx(60)
    assert any("electricity" in n for n in closed.json()["position"]["notes"])
    assert client.get(f"{BASE}/periods/{p['period_id']}/verify").json()["valid"] is True


# ── ingest: explicit units, the gateway's project and facility ────────────────

@pytest.mark.parametrize("payload, why", [
    ({"quantity": 5, "unit": "m3/h"}, "pressure and temperature"),      # an actual volume: never
    ({"quantity": 5, "unit": "Nm3"}, "no APPROVED hydrogen density"),   # G-22: none approved here
    ({"quantity": 5, "unit": "litres"}, "not accepted"),
    ({"quantity": 5}, "explicit unit"),
    ({"quantity": -1, "unit": "kg"}, "quantity"),
    ({"quantity": 5, "unit": "kg", "interval_start": "2026-02-01T00:00:00"}, "UTC offset"),
    ({"quantity": 5, "unit": "kg", "interval_end": "2026-01-31T00:00:00+00:00"}, "after interval_start"),
    ({"quantity": 5, "unit": "kg", "molecule": None}, "molecule"),
])
def test_a_metered_reading_without_a_known_unit_or_interval_is_refused(client, seeded, payload, why):
    gw = _gateway(seeded, f"FAC-{uuid.uuid4().hex[:8]}")
    body = {"molecule": "H2", "interval_start": "2026-02-01T00:00:00+00:00",
            "interval_end": "2026-02-02T00:00:00+00:00", **payload}
    if body.get("molecule") is None:
        body.pop("molecule")
    r = _push(client, gw, "PRODUCTION_VOLUME", body)
    assert r.status_code == 422, r.text
    assert why in r.json()["detail"]["reason"]


def test_rates_are_multiplied_by_the_interval_and_stored_normalised(client, seeded):
    fac = f"FAC-{uuid.uuid4().hex[:8]}"
    gw = _gateway(seeded, fac)
    _produced(client, gw, None, "2026-02-01", "2026-02-03", unit="t/d", qty=1.5)     # 2 days x 1.5 t
    r = _push(client, gw, "POWER_CONSUMPTION", {"quantity": 2, "unit": "MW",
                                                "interval_start": "2026-02-01T00:00:00+00:00",
                                                "interval_end": "2026-02-01T06:00:00+00:00"})
    assert r.status_code == 200, r.text
    rows = client.get(f"/api/v1/plant-data/data/{PROJECT}").json()["records"]
    mine = {x["data_type"]: x for x in rows if x["gateway_id"] == gw}
    assert mine["PRODUCTION_VOLUME"]["quantity_normalised"] == pytest.approx(3000)
    assert mine["PRODUCTION_VOLUME"]["normalised_unit"] == "kg"
    assert mine["POWER_CONSUMPTION"]["quantity_normalised"] == pytest.approx(12)
    assert mine["POWER_CONSUMPTION"]["facility_id"] == fac


def test_a_gateway_reports_only_for_its_own_project_and_facility(client, seeded):
    gw = _gateway(seeded, "FAC-X", project=OTHER_PROJECT)
    r = _push(client, gw, "PRODUCTION_VOLUME", {"quantity": 1, "unit": "kg", "molecule": "H2",
                                                "interval_start": "2026-02-01T00:00:00+00:00",
                                                "interval_end": "2026-02-02T00:00:00+00:00"})
    assert r.status_code == 403 and "another project" in r.json()["detail"]["reason"]
    no_facility = _gateway(seeded, None)
    r = _push(client, no_facility, "PRODUCTION_VOLUME", {"quantity": 1, "unit": "kg", "molecule": "H2",
                                                         "interval_start": "2026-02-01T00:00:00+00:00",
                                                         "interval_end": "2026-02-02T00:00:00+00:00"})
    assert r.status_code == 403 and "names no facility" in r.json()["detail"]["reason"]


def test_a_reading_overlapping_one_already_recorded_is_refused(client, seeded):
    gw = _gateway(seeded, f"FAC-{uuid.uuid4().hex[:8]}")
    _produced(client, gw, 100, "2026-02-01", "2026-02-03")
    r = _push(client, gw, "PRODUCTION_VOLUME", {"quantity": 100, "unit": "kg", "molecule": "H2",
                                                "interval_start": "2026-02-02T00:00:00+00:00",
                                                "interval_end": "2026-02-04T00:00:00+00:00"})
    assert r.status_code == 409 and "PLANT_DATA_OVERLAP" in r.json()["detail"]["reason"]


def test_the_database_refuses_a_reading_for_another_project_and_any_rewrite(seeded):
    from pg_support import connect_dsn

    gw = _gateway(seeded, "FAC-DB")
    conn = connect_dsn(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(Exception, match="PLANT_DATA_PROJECT"):
            cur.execute("INSERT INTO plant_data (id, project_id, gateway_id, data_type, payload_json, sha256_hash) "
                        "VALUES ('pd-t', %s, %s, 'PLANT_STATUS', '{}', 'x')", (OTHER_PROJECT, gw))
        conn.rollback()
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(Exception, match="permission denied"):
            cur.execute("UPDATE plant_data SET quantity_normalised = 0")
    finally:
        conn.rollback()
        conn.close()


def test_store_plant_data_raises_instead_of_pretending(seeded):
    """It used to log and return a record id for a reading that was never written."""
    from app.core.ot_boundary import store_plant_data
    from app.core.request_tenant import (reset_current_company, reset_current_user,
                                         set_current_company, set_current_user)

    gw = _gateway(seeded, None)                      # no facility: the database refuses the reading
    token = set_current_company(OWNER)
    try:
        with pytest.raises(Exception, match="ck_plant_data_metered|PLANT_DATA_FACILITY"):
            store_plant_data(gw, PROJECT, "PRODUCTION_VOLUME",
                             {"quantity": 1, "unit": "kg", "molecule": "H2",
                              "interval_start": "2026-02-01T00:00:00+00:00",
                              "interval_end": "2026-02-02T00:00:00+00:00"}, "sha256:x")
    finally:
        reset_current_company(token)


def test_the_route_answers_503_when_the_store_fails(client, seeded, monkeypatch):
    import app.api.v1.routes_plant_data as routes

    def _broken(**_k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(routes, "store_plant_data", _broken)
    gw = _gateway(seeded, f"FAC-{uuid.uuid4().hex[:8]}")
    r = _push(client, gw, "PRODUCTION_VOLUME", {"quantity": 1, "unit": "kg", "molecule": "H2",
                                                "interval_start": "2026-02-01T00:00:00+00:00",
                                                "interval_end": "2026-02-02T00:00:00+00:00"})
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["reason"].startswith("Reading not stored")


# ── G-22 (Phase 2 Step 1): hydrogen Nm3 converts only with an APPROVED density row ──

def _density_row(seeded, state: str, value: float = 0.0899) -> str:
    """A reference row written as the superuser; the registry lifecycle is tested elsewhere."""
    rid = f"ref-TEST-h2dens-{uuid.uuid4().hex[:8]}"
    approved = state == "approved"
    conn = _superuser(seeded)
    try:
        conn.cursor().execute(
            "INSERT INTO reference_parameter (ref_id, parameter_key, pathway, region, value_base, unit, "
            "source_class, source_name, retrieved_at, valid_from, state, proposed_by, proposed_at, "
            "approved_by, approved_at) VALUES (%s, 'h2_density_normal_0c_101325pa', 'H2', 'ANY', %s, 'kg/m3', "
            "'public_source', 'TEST', '2026-01-01', '2020-01-01', %s, 'test', now(), %s, %s)",
            (rid, value, state, "test_approver" if approved else None, "2026-01-02" if approved else None))
        conn.commit()
    finally:
        conn.close()
    return rid


def _drop_density_rows(seeded):
    conn = _superuser(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SET session_replication_role = replica")     # past the registry's guard
        cur.execute("UPDATE plant_data SET conversion_ref_id = NULL WHERE conversion_ref_id LIKE 'ref-TEST-h2dens-%%'")
        cur.execute("DELETE FROM reference_parameter WHERE ref_id LIKE 'ref-TEST-h2dens-%%'")
        conn.commit()
    finally:
        conn.close()


def _nm3(client, gw, qty, unit="Nm3/h", molecule="H2"):
    return _push(client, gw, "PRODUCTION_VOLUME", {
        "quantity": qty, "unit": unit, "molecule": molecule,
        "interval_start": "2026-02-01T00:00:00+00:00", "interval_end": "2026-02-01T10:00:00+00:00"})


def test_a_proposed_density_converts_nothing(client, seeded):
    _density_row(seeded, "proposed")
    try:
        r = _nm3(client, _gateway(seeded, f"FAC-{uuid.uuid4().hex[:8]}"), 100)
        assert r.status_code == 422 and "no APPROVED hydrogen density" in r.json()["detail"]["reason"], r.text
    finally:
        _drop_density_rows(seeded)


def test_hydrogen_nm3_converts_with_the_approved_density_and_keeps_its_row(client, seeded):
    rid = _density_row(seeded, "approved", 0.0899)
    try:
        gw = _gateway(seeded, f"FAC-{uuid.uuid4().hex[:8]}")
        r = _nm3(client, gw, 100)                                      # 100 Nm3/h for 10 h
        assert r.status_code == 200, r.text
        conn = _superuser(seeded)
        try:
            cur = conn.cursor()
            cur.execute("SELECT quantity_normalised AS q, normalised_unit AS u, conversion_ref_id AS ref "
                        "FROM plant_data WHERE gateway_id = %s", (gw,))
            row = cur.fetchone()
        finally:
            conn.close()
        assert row["q"] == pytest.approx(100 * 10 * 0.0899) and row["u"] == "kg" and row["ref"] == rid
        other = _nm3(client, _gateway(seeded, f"FAC-{uuid.uuid4().hex[:8]}"), 100, molecule="NH3")
        assert other.status_code == 422 and "only for hydrogen" in other.json()["detail"]["reason"]
    finally:
        _drop_density_rows(seeded)


def test_the_catalogue_names_the_reference_conditions():
    from app.core.reference_catalog import PARAMETERS, UNIT_FAMILIES

    d = PARAMETERS["h2_density_normal_0c_101325pa"]
    assert d.family == "DENSITY_MASS" and UNIT_FAMILIES["DENSITY_MASS"] == ("kg/m3",)
    assert "0 °C" in d.description and "101.325 kPa" in d.description
