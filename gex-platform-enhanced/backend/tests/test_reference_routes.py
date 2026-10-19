"""
/api/v1/reference routes on PostgreSQL — reads, and the staff-only gate on writes.

Reads are SELECTs against live development data. The write routes are exercised
only as far as their gate: a non-staff caller is refused before any SQL runs, so
nothing is written. The write path itself is covered, inside a rolled-back
transaction, by tests/test_reference_registry_pg.py.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import capital_bridge, routes_reference
from tests.pg_support import requires_pg


@pytest.fixture(scope="module", autouse=True)
def _postgres_only() -> None:
    from app.core import reference_registry as reg

    requires_pg()
    if not reg.registry_available():
        pytest.skip("FUELREF_DB_BACKEND is not postgres")


def _client(payload: dict | None) -> TestClient:
    """The routers, with `payload` bound as the verified caller (see
    test_capital_bridge_projects_routes._client for why it binds in middleware)."""
    from app.core.request_tenant import (company_from_payload, reset_current_company,
                                         set_current_company)

    api = FastAPI()

    @api.middleware("http")
    async def _bind(request, call_next):
        request.state.user_payload = payload
        token = set_current_company(company_from_payload(payload))
        try:
            return await call_next(request)
        finally:
            reset_current_company(token)

    api.include_router(routes_reference.router, prefix="/api/v1/reference")
    api.include_router(capital_bridge.router)
    return TestClient(api)


TENANT = {"user_id": "usr_test_tenant", "company_id": "etfuels_sa"}


def _skip_without_061(resp):
    if resp.status_code == 500:
        pytest.skip("migration 061 not applied")


def test_a_tenant_reads_values_in_force():
    r = _client(TENANT).get("/api/v1/reference/parameters",
                            params={"key": "electrolyser_system_sec"})
    _skip_without_061(r)
    assert r.status_code == 200
    rows = r.json()
    assert rows and all(x["state"] in ("approved", "superseded") for x in rows)


def test_resolve_falls_back_and_says_how_far():
    r = _client(TENANT).get("/api/v1/reference/resolve", params={
        "key": "electrolyser_system_sec", "pathway": "H2_PEM", "region": "DE"})
    _skip_without_061(r)
    assert r.status_code == 200
    body = r.json()
    assert (body["matched_pathway"], body["matched_region"]) == ("H2_PEM", "ANY")


def test_resolve_404s_rather_than_inventing_a_value():
    r = _client(TENANT).get("/api/v1/reference/resolve", params={
        "key": "offtake_price_base", "pathway": "SAF"})
    _skip_without_061(r)
    assert r.status_code == 404


def test_the_latest_version_is_readable():
    r = _client(TENANT).get("/api/v1/reference/versions/latest")
    _skip_without_061(r)
    assert r.status_code == 200 and r.json()["version_number"] >= 1


@pytest.mark.parametrize("path", [
    "/api/v1/reference/parameters",
    "/api/v1/reference/parameters/any-ref/approve",
    "/api/v1/reference/parameters/any-ref/reject",
])
def test_writes_are_staff_only(path):
    body = {"parameter_key": "h2_price_grey", "value_base": 2.0, "unit": "EUR/kg",
            "currency": "EUR", "price_base_date": "2025-01-01",
            "source_class": "public_source", "source_name": "x"}
    r = _client(TENANT).post(path, json=body)
    assert r.status_code == 403


def test_fuel_defaults_come_through_the_registry_and_change_no_number():
    """No approved row matches a fuel-default key yet, so every number is the
    code constant and every field says model_default. WP1 moves the source,
    not the values."""
    r = _client(TENANT).get("/api/v1/capital-bridge/fuels/defaults")
    assert r.status_code == 200
    rows = {x["fuel_type"]: x for x in r.json()}
    assert set(rows) == {f.value for f in capital_bridge.FuelType}
    for fuel, row in rows.items():
        prov = row.pop("provenance")
        row.pop("fuel_type")
        assert row == capital_bridge.FUEL_DEFAULTS[capital_bridge.FuelType(fuel)]
        assert {p["source_class"] for p in prov.values()} == {"model_default"}
