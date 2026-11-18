"""
Chain of custody to RED III grade — accounting periods (migration 097, GreenMesh Step 2).

    opening + inputs x conversion - withdrawals = closing

Runs in the throwaway database of conftest.pg_store, through the real router, as the
project owner (another company where a test says so). Every test opens its own period on
its own facility, because the module shares one database.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

OWNER = "test_coc_period_owner"
TEST_USER = "usr_test_custody"
OTHER = "test_coc_period_other"
PROJECT = "proj_TEST_coc_periods"
CAPACITY = "cap_TEST_coc_periods"
BASE = "/api/v1/chain-of-custody"
PATHWAY = "PEM_ELECTROLYSIS"
SCHEME = "TEST_SCHEME"


def _superuser(pg_url: str):
    """gex_user on the throwaway database: RLS and grants do not bind it."""
    from pg_support import connect_dsn

    admin = os.environ["ALEMBIC_DATABASE_URL"]
    return connect_dsn(admin.rsplit("/", 1)[0] + "/" + pg_url.rsplit("/", 1)[1])


@pytest.fixture(scope="module")
def seeded(pg_store):
    conn = _superuser(pg_store)
    try:
        cur = conn.cursor()
        for company in (OWNER, OTHER):
            cur.execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'PRODUCER') "
                        "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
        cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) "
                    "VALUES (%s, 'TEST custody periods', %s, 'H2') ON CONFLICT DO NOTHING", (PROJECT, OWNER))
        cur.execute("INSERT INTO capacities (id, project_name, molecule, capacity_mtpd, project_id) "
                    "VALUES (%s, 'TEST custody periods', 'H2', 10, %s) ON CONFLICT DO NOTHING", (CAPACITY, PROJECT))
        conn.commit()
    finally:
        conn.close()
    return pg_store


@pytest.fixture
def client(seeded, monkeypatch):
    import app.core.projects_store as ps
    from app.api.v1.mass_balance import router
    from app.core.request_tenant import (reset_current_company, reset_current_user,
                                         set_current_company, set_current_user)

    monkeypatch.setattr(ps, "fetch_project", lambda pid: {"project_id": pid, "project_name": "TEST"})
    app = FastAPI()
    app.include_router(router)

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


def _token(seeded, state: str = "MINTED") -> str:
    tid = f"TKN-TEST-COC-{uuid.uuid4().hex[:8]}"
    conn = _superuser(seeded)
    try:
        conn.cursor().execute("INSERT INTO tokens (id, capacity_id, molecule, lifecycle_state) "
                              "VALUES (%s, %s, 'H2', %s)", (tid, CAPACITY, state))
        conn.commit()
    finally:
        conn.close()
    return tid


def _period(client, facility=None, start="2026-01-01", end="2026-03-31", scheme=SCHEME, **over):
    body = {"project_id": PROJECT, "facility_id": facility or f"FAC-{uuid.uuid4().hex[:8]}",
            "molecule": "H2", "pathway": PATHWAY, "scheme": scheme, "period_start": start,
            "period_end": end, "opened_by": "test", **over}
    r = client.post(f"{BASE}/periods", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _factor(client, facility, input_type="ELECTRICITY", value=55.0, unit="kWh/kg", tol=None,
            valid_from="2026-01-01"):
    r = client.post(f"{BASE}/conversion-factors", json={
        "project_id": PROJECT, "facility_id": facility, "pathway": PATHWAY, "molecule": "H2",
        "input_type": input_type, "value": value, "unit": unit, "tolerance_fraction": tol,
        "valid_from": valid_from, "source": "TEST — not a real engineer's report", "recorded_by": "test"})
    assert r.status_code == 201, r.text
    return r.json()


def _input(client, period_id, qty=55.0, unit="MWh", status="CERTIFIED", input_type="ELECTRICITY",
           on="2026-02-01", expect=201):
    r = client.post(f"{BASE}/periods/{period_id}/inputs", json={
        "input_type": input_type, "quantity": qty, "unit": unit, "sustainability_status": status,
        "received_on": on, "evidence_kind": "PPA", "evidence_ref": "PPA-TEST-1", "recorded_by": "test"})
    assert r.status_code == expect, r.text
    return r.json()


def _chars(**over):
    c = {"ghg_intensity_gco2e_mj": 3.2, "pathway": PATHWAY, "scheme": SCHEME,
         "certificate_id": "CERT-TEST-1", "country_of_origin": "DE",
         "production_window_start": "2026-02-01", "production_window_end": "2026-02-28",
         "rfnbo": True, "additionality_basis": "PPA"}
    c.update(over)
    return c


def _lot(client, period_id, kg, expect=201, **over):
    body = {"project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
            "total_volume_kg": kg, "certification_pathway": "RFNBO", "created_by": "test",
            "period_id": period_id, "characteristics": _chars(), **over}
    r = client.post(f"{BASE}/lots", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def _alloc(client, lot_id, token, kg, expect=201):
    r = client.post(f"{BASE}/allocate", json={"lot_id": lot_id, "token_id": token,
                                              "volume_kg": kg, "allocated_by": "test"})
    assert r.status_code == expect, r.text
    return r.json()


# ── the statement ─────────────────────────────────────────────────────────────

def test_the_period_statement_closes_the_identity(client, seeded):
    """opening + certified inputs x conversion - withdrawals = closing, from the rows."""
    p = _period(client)
    fac, pid = p["facility_id"], p["period_id"]
    _factor(client, fac)                              # 55 kWh per kg H2 = 0.055 MWh/kg
    _input(client, pid, qty=110.0)                    # 110 MWh certified -> 2000 kg
    _input(client, pid, qty=55.0, status="NON_CERTIFIED")   # +1000 kg physical, no credit
    lot = _lot(client, pid, 2500)
    assert lot["custody_grade"] == "PERIOD" and lot["conversion_check"] == "WITHIN_INPUTS"
    _alloc(client, lot["lot_id"], _token(seeded), 1500)

    r = client.post(f"{BASE}/periods/{pid}/close", json={"closed_by": "test"})
    assert r.status_code == 200, r.text
    st = r.json()["position"]
    assert st["opening_balance_kg"] == 0.0
    assert st["conversion"]["credit_kg"] == pytest.approx(2000.0)
    assert st["conversion"]["supported_output_kg"] == pytest.approx(3000.0)
    assert st["withdrawals_kg"] == 1500.0
    assert st["closing_balance_kg"] == pytest.approx(500.0)
    assert st["closing_balance_kg"] == pytest.approx(
        st["opening_balance_kg"] + st["conversion"]["credit_kg"] - st["withdrawals_kg"])
    assert r.json()["status"] == "CLOSED" and r.json()["statement_hash"]
    assert any("No confirmed rule" in n for n in st["notes"])
    assert client.get(f"{BASE}/periods/{pid}/verify").json()["valid"] is True


def test_a_withdrawal_beyond_the_period_balance_is_refused(client, seeded):
    p = _period(client)
    _factor(client, p["facility_id"])
    _input(client, p["period_id"], qty=55.0)          # credit 1000 kg
    lot = _lot(client, p["period_id"], 5000)          # the lot holds more than the balance
    token = _token(seeded)
    _alloc(client, lot["lot_id"], token, 800)
    r = _alloc(client, lot["lot_id"], token, 300, expect=409)
    assert "COC_PERIOD_BALANCE" in r["detail"]
    _alloc(client, lot["lot_id"], token, 200)         # exactly the remaining balance


def test_no_factor_means_no_credit_and_nothing_to_withdraw(client, seeded):
    p = _period(client)
    _input(client, p["period_id"], qty=55.0)
    lot = _lot(client, p["period_id"], 100)
    assert lot["conversion_check"] == "NO_FACTOR"
    _alloc(client, lot["lot_id"], _token(seeded), 1, expect=409)


# ── the conversion check ──────────────────────────────────────────────────────

def test_a_lot_beyond_inputs_x_conversion_is_flagged_not_refused(client):
    p = _period(client)
    _factor(client, p["facility_id"], tol=0.05)
    _input(client, p["period_id"], qty=55.0)          # supports 1000 kg (+5% = 1050)
    within = _lot(client, p["period_id"], 1040)
    assert within["conversion_check"] == "WITHIN_INPUTS"
    over = _lot(client, p["period_id"], 20)           # cumulative 1060 > 1050
    assert over["conversion_check"] == "EXCEEDS_INPUTS"
    assert over["conversion_detail"]["declared_production_kg"] == pytest.approx(1060)
    assert over["conversion_detail"]["supported_output_kg"] == pytest.approx(1000)


def test_a_new_factor_version_applies_from_its_date(client):
    p = _period(client)
    fac = p["facility_id"]
    _factor(client, fac, value=55.0, valid_from="2026-01-01")
    _factor(client, fac, value=50.0, valid_from="2026-02-15")
    _input(client, p["period_id"], qty=55.0, on="2026-02-01")   # / 0.055 -> 1000 kg
    _input(client, p["period_id"], qty=50.0, on="2026-03-01")   # / 0.050 -> 1000 kg
    pos = client.get(f"{BASE}/periods/{p['period_id']}").json()["position"]
    assert pos["conversion"]["credit_kg"] == pytest.approx(2000.0)


def test_the_scarcest_input_sets_the_credit(client):
    p = _period(client)
    fac = p["facility_id"]
    _factor(client, fac, "ELECTRICITY", 55.0, "kWh/kg")
    _factor(client, fac, "WATER", 9.0, "kg/kg")
    _input(client, p["period_id"], qty=110.0)                                   # 2000 kg
    _input(client, p["period_id"], qty=9.0, unit="t", input_type="WATER")       # 1000 kg
    pos = client.get(f"{BASE}/periods/{p['period_id']}").json()["position"]
    assert pos["conversion"]["credit_kg"] == pytest.approx(1000.0)
    assert pos["conversion"]["required_input_types"] == ["ELECTRICITY", "WATER"]


# ── closed means closed ───────────────────────────────────────────────────────

def test_a_closed_period_takes_nothing_more(client, seeded):
    p = _period(client)
    _factor(client, p["facility_id"])
    _input(client, p["period_id"], qty=55.0)
    lot = _lot(client, p["period_id"], 100)
    assert client.post(f"{BASE}/periods/{p['period_id']}/close", json={"closed_by": "t"}).status_code == 200

    _input(client, p["period_id"], expect=409)
    _lot(client, p["period_id"], 10, expect=409)
    assert "COC_PERIOD_CLOSED" in _alloc(client, lot["lot_id"], _token(seeded), 1, expect=409)["detail"]
    again = client.post(f"{BASE}/periods/{p['period_id']}/close", json={"closed_by": "t"})
    assert again.status_code == 409


def test_a_closed_period_is_immutable_in_the_database(client, seeded):
    """Not only the application: the runtime role cannot rewrite a closed period."""
    from pg_support import connect_dsn

    p = _period(client)
    assert client.post(f"{BASE}/periods/{p['period_id']}/close", json={"closed_by": "t"}).status_code == 200
    conn = connect_dsn(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = %s", (OWNER,))
        with pytest.raises(Exception, match="COC_PERIOD_CLOSED"):
            cur.execute("UPDATE coc_period SET closing_balance_kg = 1e9 WHERE period_id = %s", (p["period_id"],))
        conn.rollback()
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(Exception, match="COC_PERIOD_KEPT|permission denied"):
            cur.execute("DELETE FROM coc_period WHERE period_id = %s", (p["period_id"],))
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("table", ["coc_input", "coc_conversion_factor", "mass_balance_allocations"])
def test_the_runtime_cannot_rewrite_an_append_only_record(seeded, table):
    from pg_support import connect_dsn

    conn = connect_dsn(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(Exception, match="permission denied"):
            cur.execute(f"UPDATE {table} SET project_id = project_id" if table != "mass_balance_allocations"
                        else f"UPDATE {table} SET volume_kg = volume_kg")
    finally:
        conn.rollback()
        conn.close()


def test_tampering_with_an_input_breaks_the_chain(client, seeded):
    p = _period(client)
    _factor(client, p["facility_id"])
    first = _input(client, p["period_id"], qty=55.0)
    _input(client, p["period_id"], qty=11.0)
    assert client.get(f"{BASE}/periods/{p['period_id']}/verify").json()["valid"] is True
    conn = _superuser(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SET session_replication_role = replica")     # what only a superuser can do
        cur.execute("UPDATE coc_input SET quantity_normalised = 550 WHERE input_id = %s", (first["input_id"],))
        conn.commit()
    finally:
        conn.close()
    v = client.get(f"{BASE}/periods/{p['period_id']}/verify").json()
    assert v["valid"] is False and v["broken_at"] == first["input_id"]


# ── characteristics ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("over, why", [
    ({"ghg_intensity_gco2e_mj": -1}, "ghg_intensity"),
    ({"country_of_origin": "Germany"}, "country_of_origin"),
    ({"certificate_id": None}, "certificate_id"),
    ({"additionality_basis": "NOT_CLAIMED"}, "additionality"),
    ({"additionality_basis": "TRUST_ME"}, "additionality_basis"),
    ({"production_window_end": "2026-01-15"}, "production_window"),
    ({"production_window_end": "2026-04-30"}, "outside the accounting period"),
    ({"pathway": "SMR"}, "pathway"),
    ({"scheme": "OTHER"}, "scheme"),
    ({"colour": "green"}, "colour"),
])
def test_invalid_characteristics_are_refused(client, over, why):
    p = _period(client)
    r = client.post(f"{BASE}/lots", json={
        "project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
        "total_volume_kg": 10, "created_by": "test", "period_id": p["period_id"],
        "characteristics": _chars(**over)})
    assert r.status_code == 422, r.text
    assert why in r.text


def test_a_period_lot_needs_characteristics_and_keeps_the_old_column_readable(client):
    p = _period(client)
    bare = client.post(f"{BASE}/lots", json={
        "project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
        "total_volume_kg": 10, "created_by": "test", "period_id": p["period_id"]})
    assert bare.status_code == 422
    lot = _lot(client, p["period_id"], 10)
    assert lot["carbon_intensity_gco2e_mj"] == 3.2
    assert lot["characteristics"]["certificate_id"] == "CERT-TEST-1"
    conflicting = _lot(client, p["period_id"], 10, expect=422, carbon_intensity_gco2e_mj=9.9)
    assert "disagrees" in conflicting["detail"]


def test_a_lot_without_a_period_still_works_and_says_so(client, seeded):
    lot = client.post(f"{BASE}/lots", json={
        "project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
        "total_volume_kg": 10, "created_by": "test", "carbon_intensity_gco2e_mj": 5.0}).json()
    assert lot["custody_grade"] == "NO_PERIOD" and lot["period_id"] is None
    _alloc(client, lot["lot_id"], _token(seeded), 4)


# ── inputs, periods, scheme rules ─────────────────────────────────────────────

def test_inputs_are_normalised_and_a_volume_unit_is_refused(client):
    p = _period(client)
    kwh = _input(client, p["period_id"], qty=1500.0, unit="kWh")
    assert kwh["quantity_normalised"] == pytest.approx(1.5) and kwh["normalised_unit"] == "MWh"
    r = client.post(f"{BASE}/periods/{p['period_id']}/inputs", json={
        "input_type": "WATER", "quantity": 3, "unit": "m3", "sustainability_status": "CERTIFIED",
        "received_on": "2026-02-01", "evidence_kind": "SUPPLIER_INVOICE", "evidence_ref": "INV-1",
        "recorded_by": "test"})
    assert r.status_code == 422
    _input(client, p["period_id"], on="2026-05-01", expect=409)     # outside the period


def test_periods_of_one_facility_never_overlap(client):
    p = _period(client)
    r = client.post(f"{BASE}/periods", json={
        "project_id": PROJECT, "facility_id": p["facility_id"], "molecule": "H2", "pathway": PATHWAY,
        "scheme": SCHEME, "period_start": "2026-03-01", "period_end": "2026-04-30", "opened_by": "t"})
    assert r.status_code == 409 and "COC_PERIOD_OVERLAP" in r.text


def test_without_a_confirmed_rule_nothing_is_carried_forward(client, seeded):
    first = _period(client)
    _factor(client, first["facility_id"])
    _input(client, first["period_id"], qty=55.0)
    client.post(f"{BASE}/periods/{first['period_id']}/close", json={"closed_by": "t"})
    nxt = _period(client, facility=first["facility_id"], start="2026-04-01", end="2026-06-30")
    assert nxt["opening_balance_kg"] == 0.0
    assert nxt["opening_basis"].startswith("NO_CARRY_FORWARD")


def test_a_confirmed_carry_forward_rule_carries_the_closing_balance(client, seeded):
    scheme = f"TEST_CF_{uuid.uuid4().hex[:6]}"
    conn = _superuser(seeded)
    try:
        conn.cursor().execute("INSERT INTO coc_scheme_rule (scheme, max_period_days, carry_forward_allowed, source) "
                              "VALUES (%s, 92, true, 'TEST — not a certifier')", (scheme,))
        conn.commit()
    finally:
        conn.close()
    first = _period(client, scheme=scheme)
    fac = first["facility_id"]
    _factor(client, fac)
    _input(client, first["period_id"], qty=55.0)       # 1000 kg
    client.post(f"{BASE}/periods/{first['period_id']}/close", json={"closed_by": "t"})
    nxt = _period(client, facility=fac, scheme=scheme, start="2026-04-01", end="2026-06-30")
    assert nxt["opening_balance_kg"] == pytest.approx(1000.0)
    assert nxt["opening_basis"] == f"CARRIED_FROM:{first['period_id']}"
    too_long = client.post(f"{BASE}/periods", json={
        "project_id": PROJECT, "facility_id": fac, "molecule": "H2", "pathway": PATHWAY, "scheme": scheme,
        "period_start": "2026-07-01", "period_end": "2026-12-31", "opened_by": "t"})
    assert too_long.status_code == 422 and "92 days" in too_long.text


# ── tenancy and tokens ────────────────────────────────────────────────────────

def test_another_company_neither_reads_nor_writes_a_period(client):
    p = _period(client)
    other = {"x-test-company": OTHER}
    assert client.get(f"{BASE}/periods/{p['period_id']}", headers=other).status_code == 404
    r = client.post(f"{BASE}/periods", headers=other, json={
        "project_id": PROJECT, "facility_id": "FAC-OTHER", "molecule": "H2", "pathway": PATHWAY,
        "scheme": SCHEME, "period_start": "2027-01-01", "period_end": "2027-03-31", "opened_by": "t"})
    assert r.status_code == 403


def test_an_allocation_links_the_token_and_respects_its_state(client, seeded):
    p = _period(client)
    _factor(client, p["facility_id"])
    _input(client, p["period_id"], qty=55.0)
    lot = _lot(client, p["period_id"], 500)
    token = _token(seeded)
    _alloc(client, lot["lot_id"], token, 100)
    conn = _superuser(seeded)
    try:
        cur = conn.cursor()
        cur.execute("SELECT mass_balance_lot_id FROM tokens WHERE id = %s", (token,))
        assert cur.fetchone()["mass_balance_lot_id"] == lot["lot_id"]
    finally:
        conn.close()
    assert _alloc(client, lot["lot_id"], _token(seeded, "RETIRED"), 1, expect=409)
    assert _alloc(client, lot["lot_id"], "TKN-DOES-NOT-EXIST", 1, expect=404)
    other_lot = _lot(client, p["period_id"], 50)
    assert "already backed" in _alloc(client, other_lot["lot_id"], token, 1, expect=409)["detail"]


# ── G-20: the actor is the signed-in user, never the request body ─────────────

def test_every_custody_actor_is_the_signed_in_user_not_the_body(client, seeded):
    """The helpers still send `*_by: "test"` (accepted for compatibility). What is recorded,
    in every custody table, is the user the request is signed in as."""
    me = "usr_test_real_actor"
    client.headers.update({"x-test-user": me})
    try:
        p = _period(client)
        f = _factor(client, p["facility_id"])
        i = _input(client, p["period_id"])
        lot = _lot(client, p["period_id"], 100)
        a = _alloc(client, lot["lot_id"], _token(seeded), 10)
        closed = client.post(f"{BASE}/periods/{p['period_id']}/close", json={"closed_by": "someone_else"})
        assert closed.status_code == 200, closed.text
        zone = client.post(f"{BASE}/facility-profiles", json={
            "project_id": PROJECT, "facility_id": p["facility_id"], "bidding_zone": "DE-LU",
            "source": "TEST", "recorded_by": "someone_else"})
        assert zone.status_code == 201, zone.text
    finally:
        client.headers.pop("x-test-user", None)
    assert a["allocated_by"] == me
    conn = _superuser(seeded)
    try:
        cur = conn.cursor()
        recorded = {}
        for table, col, key, val in (
                ("coc_period", "opened_by", "period_id", p["period_id"]),
                ("coc_period", "closed_by", "period_id", p["period_id"]),
                ("coc_conversion_factor", "recorded_by", "factor_id", f["factor_id"]),
                ("coc_input", "recorded_by", "input_id", i["input_id"]),
                ("mass_balance_lots", "created_by", "lot_id", lot["lot_id"]),
                ("mass_balance_allocations", "allocated_by", "allocation_id", a["allocation_id"]),
                ("coc_facility_profile", "recorded_by", "facility_id", p["facility_id"])):
            cur.execute(f"SELECT {col} FROM {table} WHERE {key} = %s", (val,))
            row = cur.fetchone()
            recorded[f"{table}.{col}"] = row[col] if isinstance(row, dict) else row[0]
    finally:
        conn.close()
    assert set(recorded.values()) == {me}, recorded


def test_a_custody_write_without_a_signed_in_user_is_refused(client):
    """No attributable actor, no custody record — whatever the body claims."""
    client.headers.update({"x-test-user": ""})
    try:
        r = client.post(f"{BASE}/periods", json={
            "project_id": PROJECT, "facility_id": f"FAC-{uuid.uuid4().hex[:8]}", "molecule": "H2",
            "pathway": PATHWAY, "scheme": SCHEME, "period_start": "2026-01-01",
            "period_end": "2026-03-31", "opened_by": "a_name_typed_in_the_body"})
    finally:
        client.headers.pop("x-test-user", None)
    assert r.status_code == 401, r.text


# ── 101: hydrogen taken as an input names its source lot, and is never used twice ──

def _h2_input(client, period_id, kg, source_lot_id=None, expect=201, input_type="H2"):
    body = {"input_type": input_type, "quantity": kg, "unit": "kg", "sustainability_status": "CERTIFIED",
            "received_on": "2026-02-20", "evidence_kind": "POS", "evidence_ref": "POS-TEST-H2"}
    if source_lot_id:
        body["source_lot_id"] = source_lot_id
    r = client.post(f"{BASE}/periods/{period_id}/inputs", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def test_hydrogen_used_downstream_is_not_available_to_tokens_and_vice_versa(client, seeded):
    up = _period(client)
    _factor(client, up["facility_id"])
    _input(client, up["period_id"], qty=55.0)                # 1000 kg of credit in the upstream period
    lot = _lot(client, up["period_id"], 1000)
    down = _period(client, molecule="NH3")
    _h2_input(client, down["period_id"], 800, source_lot_id=lot["lot_id"])
    # 200 kg left: a token may not take 300, an input may not take 300 either
    assert "Exhaustion guard" in _alloc(client, lot["lot_id"], _token(seeded), 300, expect=400)["detail"]
    assert "COC_SOURCE_LOT_EXHAUSTED" in _h2_input(client, down["period_id"], 300, lot["lot_id"],
                                                    expect=409)["detail"]
    _alloc(client, lot["lot_id"], _token(seeded), 200)
    assert "COC_SOURCE_LOT_EXHAUSTED" in _h2_input(client, down["period_id"], 1, lot["lot_id"], expect=409)["detail"]


def test_a_source_lot_is_hydrogen_of_a_period_and_only_hydrogen_names_one(client):
    up = _period(client)
    lot = _lot(client, up["period_id"], 100)
    down = _period(client, molecule="NH3")
    assert "only a hydrogen" in _h2_input(client, down["period_id"], 1, lot["lot_id"], expect=422,
                                          input_type="CO2")["detail"]
    assert "not found" in _h2_input(client, down["period_id"], 1, "no-such-lot", expect=422)["detail"]
    old = client.post(f"{BASE}/lots", json={"project_id": PROJECT, "molecule": "H2", "production_date": "2026-02-15",
                                            "total_volume_kg": 50})
    assert old.status_code == 201, old.text
    assert "no accounting period" in _h2_input(client, down["period_id"], 1, old.json()["lot_id"],
                                               expect=422)["detail"]


def test_the_source_lot_is_in_the_input_chain_and_older_chains_still_verify(client, seeded):
    up = _period(client)
    lot = _lot(client, up["period_id"], 100)
    down = _period(client, molecule="NH3")
    _input(client, down["period_id"])                       # no source: payload as before 101
    i = _h2_input(client, down["period_id"], 10, lot["lot_id"])
    assert i["source_lot_id"] == lot["lot_id"]
    assert client.get(f"{BASE}/periods/{down['period_id']}/verify").json()["valid"] is True
    conn = _superuser(seeded)                               # re-point the input at another lot
    try:
        cur = conn.cursor()
        other = _lot(client, up["period_id"], 5)["lot_id"]
        cur.execute("SET session_replication_role = replica")
        cur.execute("UPDATE coc_input SET source_lot_id = %s WHERE input_id = %s", (other, i["input_id"]))
        conn.commit()
    finally:
        conn.close()
    assert client.get(f"{BASE}/periods/{down['period_id']}/verify").json()["valid"] is False
