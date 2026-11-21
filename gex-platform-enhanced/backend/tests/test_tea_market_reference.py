"""The product's Gabillon price beside the TEA's required price, and the two read-only
parameter screens for GEX administrators (20 Nov 2026).

No database: the reference is pure arithmetic on the run's breakdown and the PF engine's
answers, and the two console routes are refused before they read anything.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import tea_market_reference as tmr

BD = {"currency": "EUR", "years": [
    {"year": 0, "production_kg": 0, "discount_factor": 1.0},
    {"year": 1, "production_kg": 25e6, "discount_factor": 1 / 1.08},
    {"year": 2, "production_kg": 50e6, "discount_factor": 1 / 1.08 ** 2},
    {"year": 3, "production_kg": 50e6, "discount_factor": 1 / 1.08 ** 3},
]}
PARAMS = {"molecule": "E_METHANOL", "calibration_status": "SEED",
          "params": {"n_observations": 0, "last_calibrated": "2026-03-22"}}
DECK = {"spot_eur_t": 800.0, "long_term_equilibrium_eur_t": 800.0, "capex_floor_eur_t": 600,
        "mean_reversion_half_life_months": 12.8,
        "annual_prices": [{"year": i + 1, "price_eur_t": 830.0 + i, "price_real_eur_t": p}
                          for i, p in enumerate((825.0, 816.0, 804.0))]}


def test_the_gabillon_price_is_levelised_like_the_lcop():
    r = tmr.build(BD, 2.62, "E_METHANOL", PARAMS, DECK, "€/t")
    assert r["applies"] and r["unit"] == "EUR/kg"
    q = [25e6, 50e6, 50e6]
    d = [1 / 1.08, 1 / 1.08 ** 2, 1 / 1.08 ** 3]
    p = [0.825, 0.816, 0.804]
    expect = sum(a * b * c for a, b, c in zip(p, q, d)) / sum(b * c for b, c in zip(q, d))
    assert r["levelised_price"] == pytest.approx(expect, rel=1e-12)
    assert r["difference"] == pytest.approx(2.62 - expect)
    assert [y["operating_year"] for y in r["years"]] == [1, 2, 3]   # construction year skipped
    assert r["years"][0]["price_real"] == 0.825                      # the REAL deck, not nominal


def test_a_seed_curve_says_it_is_not_a_market_quote():
    r = tmr.build(BD, 2.62, "E_METHANOL", PARAMS, DECK, "€/t")
    assert r["calibration_status"] == "SEED" and "not a market quote" in r["standing"]


@pytest.mark.parametrize("bd, unit, word", [
    (BD, "€/MWh", "energy content"),
    ({**BD, "currency": "USD"}, "€/t", "USD"),
    ({**BD, "years": BD["years"] * 3}, "€/t", "does not cover"),
])
def test_what_cannot_be_compared_is_refused_with_its_reason(bd, unit, word):
    r = tmr.build(bd, 2.62, "E_METHANE", PARAMS, DECK, unit)
    assert r["applies"] is False and word in r["reason"]
    assert "levelised_price" not in r


def test_an_engine_failure_is_recorded_never_zero(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1 import routes_pricing_proxy as rp

    async def down(path, method="GET", json_data=None):
        raise HTTPException(503, "Pricing engine unavailable (port 8001)")

    monkeypatch.setattr(rp, "_call_pricing", down)
    r = asyncio.run(tmr.fetch("E_METHANOL", BD, 2.62))
    assert r["applies"] is False and "8001" in r["reason"]


@pytest.fixture(scope="module")
def console():
    from app.api.v1 import routes_gex_console
    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(routes_gex_console.router, prefix="/api/v1/gex-console")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/api/v1/gex-console/gabillon", "/api/v1/gex-console/tea-parameters"])
def test_the_parameter_screens_are_for_gex_administrators_only(console, path):
    assert console.get(path).status_code == 401
    member = {"user_id": "u1", "company_id": "hamburgone_com", "is_platform_admin": False}
    r = console.get(path, headers={"x-test-payload": json.dumps(member)})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "GEX_STAFF_ONLY"
