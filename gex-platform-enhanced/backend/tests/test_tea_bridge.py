"""
TEA bridge propagation (routes_tea.py).
========================================
G1/G2 close the loop into the finance gate: the TEA integrity verdict
(result_status) is carried onto the model_base_case, and a basis the engine
flagged IMPLAUSIBLE (a unit/scale error) cannot be promoted to `verified`. Since
the P1 release gate opens only on `verified`, blocking promotion here keeps a
physically broken number out of every release-gated PF/DSCR compute. A SCREENING
basis still verifies — an IE reviews it; a rejection is always allowed.

Isolated deliberately: the bridge DB is a per-test temp file (NEVER the dev DB,
per the repo rule), and the evidence/canonical collaborators are stubbed — they
carry their own coverage. This pins the result_status storage and the promotion
block, nothing else.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def client(isolated_store, monkeypatch):
    import app.api.v1.routes_tea as rt

    # 1) isolate the bridge DB, then create its tables there. `isolated_store`,
    #    not a monkeypatched `rt.DB_PATH`: that attribute is gone, because the
    #    module now follows DOMAIN_DB_BACKEND and resolves its store per call.
    #    A test that patched a module path would have written the development
    #    database the moment that switch said `postgres`.
    rt.init_db()

    # 2) controlled TEA response: a pathway containing 'implausible' comes back
    #    IMPLAUSIBLE with a flag; anything else is a clean SCREENING run.
    calls: list = []
    paths: list = []

    async def fake_call_tea(path, payload, auth):
        calls.append(payload)
        paths.append(path)
        if path == "/monte-carlo":
            return {"engine": "openpytea", "mc_hash": "sha256:mc", "cost_basis_hash": "sha256:t",
                    "lcop": {"p10": 1.7, "p50": 2.2, "p90": 2.9}}
        imp = "implausible" in payload.get("pathway_id", "")
        return {
            "engine": "openpytea",
            "cost_basis_hash": "sha256:t-" + payload["pathway_id"][:8],
            "lcop": 49.7 if imp else 2.4,
            "plant_summary": {
                "capex_eur": 6.4e9 if imp else 1.8e8, "opex_eur_per_year": 4.1e7,
                "nameplate_capacity": 50000.0, "nameplate_unit": "t_per_year",
                "verification_state": "UNVERIFIED"},
            "result_status": "IMPLAUSIBLE" if imp else "SCREENING",
            "plausibility": (["specific_capex out of band — unit/scale error"] if imp else []),
            "note": "test",
        }

    # 3) stub the collaborators (own coverage elsewhere) so this test needs no
    #    evidence_ledger / canonical_ledger tables and no Matrix.
    def fake_evidence(ev, db):
        return {"evidence_id": f"ev-{uuid.uuid4().hex[:8]}"}

    monkeypatch.setattr(rt, "_call_tea", fake_call_tea)
    monkeypatch.setattr(rt, "append_evidence", fake_evidence)
    monkeypatch.setattr(rt, "_canonical", lambda *a, **k: {"entry_id": "canon-test"})
    monkeypatch.setattr(rt, "notify_approval_requested", lambda *a, **k: None)
    monkeypatch.setattr(rt, "notify_approval_decided", lambda *a, **k: None)

    app = FastAPI()

    # The real ABAC middleware sets request.state.auth_user_payload; the minimal test
    # app has none, so inject it from a test header (JSON) to exercise the CFO gate.
    @app.middleware("http")
    async def _inject_payload(request, call_next):
        import json as _json
        raw = request.headers.get("x-test-payload")
        if raw:
            request.state.auth_user_payload = _json.loads(raw)
        return await call_next(request)

    app.include_router(rt.router, prefix="/api/v1/tea")
    tc = TestClient(app)
    tc.tea_calls = calls   # payloads the bridge forwarded to :8002 (assert resolution)
    tc.tea_paths = paths   # which :8002 route each payload went to
    return tc


def _compute(client, project, pathway):
    r = client.post(
        f"/api/v1/tea/compute/{project}",
        json={"pathway_id": pathway, "fuel_id": "E_METHANOL",
              "nameplate_capacity": 50000, "nameplate_unit": "t_per_year"})
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, claim, outcome="approve"):
    return client.post(
        f"/api/v1/tea/base-case/{claim}/approve",
        headers={"x-demo-user": "ie@x.test"},
        json={"approved_by": "ie@x.test", "outcome": outcome,
              "approver_role": "independent_engineer"})


def test_result_status_is_stored_on_the_base_case(client):
    body = _compute(client, "P-OK", "adv-ok")
    assert body["result_status"] == "SCREENING"
    assert body["base_case"]["result_status"] == "SCREENING"
    assert body["plausibility"] == []


def test_screening_basis_can_be_verified(client):
    body = _compute(client, "P-OK", "adv-ok")
    r = _approve(client, body["base_case"]["claim_id"])
    assert r.status_code == 200, r.text
    assert r.json()["base_case"]["state"] == "verified"


def test_implausible_basis_cannot_be_promoted(client):
    body = _compute(client, "P-IMP", "adv-implausible")
    assert body["result_status"] == "IMPLAUSIBLE"
    assert body["plausibility"]  # non-empty flag carried through

    r = _approve(client, body["base_case"]["claim_id"])
    assert r.status_code == 422
    assert "IMPLAUSIBLE" in r.json()["detail"]

    # it stays submitted -> the P1 release gate can never open on it
    g = client.get("/api/v1/tea/base-case/P-IMP").json()
    assert g["state"] == "submitted"
    assert g["is_release_ready"] is False


def test_implausible_basis_may_still_be_rejected(client):
    """The block is on PROMOTION to verified only — a rejection is always allowed."""
    body = _compute(client, "P-IMP2", "adv-implausible")
    r = _approve(client, body["base_case"]["claim_id"], outcome="reject")
    assert r.status_code == 200, r.text
    assert r.json()["base_case"]["state"] == "rejected"


def _fx_body(**over):
    b = {"pathway_id": "adv-ok", "fuel_id": "E_METHANOL",
         "nameplate_capacity": 50000, "nameplate_unit": "t_per_year"}
    b.update(over)
    return b


def test_fx_override_requires_finance_authority(client):
    """Increment 3: an FX override with no finance authority is refused (403)."""
    r = client.post("/api/v1/tea/compute/P-FX",
                    json=_fx_body(fx_usd_to_eur=0.90, fx_override_reason="conservative"))
    assert r.status_code == 403 and "authority" in r.json()["detail"].lower()


def test_fx_override_requires_a_recorded_reason(client):
    import json
    h = {"x-test-payload": json.dumps({"business_function": "EXECUTIVE", "user_id": "cfo@x"})}
    r = client.post("/api/v1/tea/compute/P-FX", headers=h, json=_fx_body(fx_usd_to_eur=0.90))
    assert r.status_code == 422 and "reason" in r.json()["detail"].lower()


def test_cfo_fx_override_is_authorised_and_recorded(client):
    import json
    h = {"x-test-payload": json.dumps({"business_function": "FINANCE_TREASURY", "user_id": "cfo@x"})}
    r = client.post("/api/v1/tea/compute/P-FX", headers=h,
                    json=_fx_body(fx_usd_to_eur=0.90, fx_override_reason="conservative haircut"))
    assert r.status_code == 201
    ov = r.json()["fx_override"]
    assert ov["rate"] == 0.90 and ov["approved_by"] == "cfo@x" and "conservative" in ov["reason"]


def test_project_currency_get_set_and_validation(client):
    import json
    assert client.get("/api/v1/tea/project/P-NEW/currency").json() == {
        "project_id": "P-NEW", "base_currency": "EUR", "is_default": True}
    h = {"x-test-payload": json.dumps({"user_id": "u@x"})}
    p = client.put("/api/v1/tea/project/P-NEW/currency", headers=h, json={"base_currency": "usd"})
    assert p.status_code == 200 and p.json()["base_currency"] == "USD" and p.json()["set_by"] == "u@x"
    g = client.get("/api/v1/tea/project/P-NEW/currency").json()
    assert g["base_currency"] == "USD" and g["is_default"] is False
    assert client.put("/api/v1/tea/project/P-NEW/currency",
                      json={"base_currency": "GBP"}).status_code == 422


def test_compute_uses_persisted_project_currency(client):
    client.put("/api/v1/tea/project/P-CCY/currency", json={"base_currency": "USD"})
    assert client.post("/api/v1/tea/compute/P-CCY", json=_fx_body()).status_code == 201
    assert client.tea_calls[-1]["base_currency"] == "USD"   # resolved from the project setting


def test_explicit_request_currency_overrides_project_setting(client):
    client.put("/api/v1/tea/project/P-CCY2/currency", json={"base_currency": "USD"})
    client.post("/api/v1/tea/compute/P-CCY2", json=_fx_body(base_currency="EUR"))
    assert client.tea_calls[-1]["base_currency"] == "EUR"   # explicit request wins


def test_monte_carlo_proxy_forwards_inputs_and_resolved_currency(client):
    client.put("/api/v1/tea/project/P-MC/currency", json={"base_currency": "USD"})
    r = client.post("/api/v1/tea/monte-carlo/P-MC",
                    json=_fx_body(num_samples=500, seed=7, target_lcop=2.0))
    assert r.status_code == 200 and r.json()["lcop"]["p50"] == 2.2
    assert client.tea_paths[-1] == "/monte-carlo"
    sent = client.tea_calls[-1]
    assert sent["base_currency"] == "USD"            # same resolution as /compute
    assert sent["num_samples"] == 500 and sent["seed"] == 7 and sent["target_lcop"] == 2.0


def test_monte_carlo_proxy_enforces_the_cfo_fx_gate(client):
    r = client.post("/api/v1/tea/monte-carlo/P-MC",
                    json=_fx_body(fx_usd_to_eur=0.90, fx_override_reason="conservative"))
    assert r.status_code == 403


def test_monte_carlo_is_analysis_not_a_claim(client):
    """A Monte Carlo run creates or supersedes no base case."""
    assert client.post("/api/v1/tea/monte-carlo/P-MC2", json=_fx_body()).status_code == 200
    assert client.get("/api/v1/tea/base-case/P-MC2").status_code == 404


def test_missing_result_status_does_not_block(client, monkeypatch):
    """Back-compat: an old TEA engine returns no result_status -> stored None,
    promotion is not blocked (a NULL verdict is not IMPLAUSIBLE)."""
    import app.api.v1.routes_tea as rt

    async def legacy_tea(path, payload, auth):
        return {"engine": "openpytea", "cost_basis_hash": "sha256:legacy",
                "lcop": 2.4, "plant_summary": {"capex_eur": 1.8e8,
                "opex_eur_per_year": 4.1e7, "nameplate_capacity": 50000.0,
                "nameplate_unit": "t_per_year", "verification_state": "UNVERIFIED"},
                "note": "legacy — no result_status"}
    monkeypatch.setattr(rt, "_call_tea", legacy_tea)

    body = _compute(client, "P-LEGACY", "adv-legacy")
    assert body["result_status"] is None
    r = _approve(client, body["base_case"]["claim_id"])
    assert r.status_code == 200, r.text
    assert r.json()["base_case"]["state"] == "verified"
