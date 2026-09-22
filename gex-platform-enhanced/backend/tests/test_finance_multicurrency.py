"""
Multi-currency CFADS proxy (increment 4).
=========================================
Each revenue/opex stream carries its OWN currency and its CONTRACT-SPECIFIED fx_rate
to the project base currency — not the platform's dated benchmark. The proxy refuses a
foreign-currency stream that lacks a contract rate, resolves the base currency from the
project's persisted setting, gates on a verified base case, and governs the result.

Isolated: the PF engine call and the release gate are stubbed, so no :8001 / DB / base
case is needed — this pins the proxy's contract-rate enforcement and resolution only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def client(monkeypatch):
    import app.api.v1.routes_finance_model as fm

    calls: list = []

    async def fake_call_model(path, method="GET", json_data=None, request=None):
        calls.append({"path": path, "json": json_data})
        return {"success": True, "cfads": {"cfads": 79_790_000.0,
                "base_currency": (json_data or {}).get("base_currency"),
                "fx_exposure": {"currencies": ["EUR", "USD"], "natural_hedge_ratio": 27.4}}}

    async def fake_gate(project_id):
        return {"gate": "RELEASE_READY", "base_case_claim": "c", "cost_basis_hash": "h",
                "capex_eur": 1.0, "opex_eur_per_year": 1.0}

    monkeypatch.setattr(fm, "_call_model", fake_call_model)
    monkeypatch.setattr(fm, "_require_release_ready", fake_gate)

    app = FastAPI()
    app.include_router(fm.router, prefix="/api/v1/finance-model")
    tc = TestClient(app)
    tc.calls = calls
    return tc


def _streams():
    return {"revenue_streams": [{"label": "eur", "amount": 100e6, "currency": "EUR", "fx_rate": 1.0},
                                {"label": "usd", "amount": 50e6, "currency": "USD", "fx_rate": 0.92}],
            "opex_streams": [{"label": "power", "amount": 40e6, "currency": "EUR"}]}


def test_foreign_stream_without_contract_rate_is_refused(client):
    body = {"revenue_streams": [{"label": "usd", "amount": 50e6, "currency": "USD"}],  # no fx_rate
            "opex_streams": []}
    r = client.post("/api/v1/finance-model/cfads-multi-currency?project_id=P1", json=body)
    assert r.status_code == 422 and "contract-specified fx_rate" in r.json()["detail"]


def test_contract_rates_forward_and_are_governed(client):
    r = client.post("/api/v1/finance-model/cfads-multi-currency?project_id=P1",
                    json={**_streams(), "base_currency": "EUR"})
    assert r.status_code == 200
    fwd = client.calls[-1]
    assert fwd["path"] == "/cfads/calculate-multi-currency"
    assert fwd["json"]["base_currency"] == "EUR" and len(fwd["json"]["revenue_streams"]) == 2
    assert r.json()["governance"]["basis"] == "RELEASE_READY_BASE_CASE"


def test_base_currency_resolves_from_the_project(client, monkeypatch):
    import app.api.v1.routes_tea as rt
    monkeypatch.setattr(rt, "_project_currency", lambda pid: "USD")
    # a USD stream needs no fx_rate once the base currency is USD
    body = {"revenue_streams": [{"label": "usd", "amount": 50e6, "currency": "USD"}], "opex_streams": []}
    r = client.post("/api/v1/finance-model/cfads-multi-currency?project_id=P1", json=body)
    assert r.status_code == 200 and client.calls[-1]["json"]["base_currency"] == "USD"
