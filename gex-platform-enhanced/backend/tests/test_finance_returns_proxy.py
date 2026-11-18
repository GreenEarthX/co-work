"""
Returns proxy (/api/v1/finance-model/returns).
==============================================
The IRR, NPV, ROI, ROE and hurdle-rate maths live in gex_pf_engine
core/returns.py and are tested there. This pins what the platform adds: the
call reaches the right engine path, the answer carries a governance stamp, and
a release-gated call may not use an FCI unrelated to the verified cost basis.

Isolated: the engine call and the release gate are stubbed.
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

# Illustrative figures, not a project's and not the Breizh reference case.
BODY = {"fci_eur": 300e6, "operating_years": 20, "revenue_y1_eur": 60e6, "opex_y1_eur": 24e6,
        "tax_rate": 0.25, "depreciation_years": 20, "cost_of_equity": 0.12}


@pytest.fixture
def client(monkeypatch):
    import app.api.v1.routes_finance_model as fm

    calls: list = []
    state = {"gate": {"gate": "UNGATED_NO_PROJECT"}}

    async def fake_call_model(path, method="GET", json_data=None, request=None):
        calls.append({"path": path, "method": method, "json": json_data})
        return {"success": True, "returns": {"unlevered_irr": 0.088, "levered_irr": 0.157}}

    async def fake_gate(project_id):
        return state["gate"]

    monkeypatch.setattr(fm, "_call_model", fake_call_model)
    monkeypatch.setattr(fm, "_require_release_ready", fake_gate)

    app = FastAPI()
    app.include_router(fm.router, prefix="/api/v1/finance-model")
    tc = TestClient(app)
    tc.calls, tc.state = calls, state
    return tc


def test_forwards_to_the_engine_and_stamps_the_answer(client):
    r = client.post("/api/v1/finance-model/returns", json=BODY)
    assert r.status_code == 200, r.text
    assert client.calls[-1] == {"path": "/returns/calculate", "method": "POST", "json": BODY}
    body = r.json()
    assert body["returns"]["unlevered_irr"] == 0.088
    assert body["governance"]["basis"] == "ILLUSTRATIVE_INPUTS"
    assert "Not for credit decisions" in body["governance"]["note"]


def test_release_gated_call_must_use_the_verified_fci(client):
    client.state["gate"] = {"gate": "RELEASE_READY", "base_case_claim": "c",
                            "cost_basis_hash": "h", "capex_eur": 300e6,
                            "opex_eur_per_year": 24e6}
    ok = client.post("/api/v1/finance-model/returns?project_id=P1", json=BODY)
    assert ok.status_code == 200
    assert ok.json()["governance"]["basis"] == "RELEASE_READY_BASE_CASE"

    drifted = client.post("/api/v1/finance-model/returns?project_id=P1",
                          json={**BODY, "fci_eur": 200e6})
    assert drifted.status_code == 409 and "fci_eur" in drifted.json()["detail"]
