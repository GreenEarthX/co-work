"""
The economics read model serves an APPROVED claim, or nothing.

`GET /api/v1/economics/snapshot/{project_id}` is increment 1 of
`docs/tea-report-scope.md`. Its whole reason for existing is that a report must
carry the numbers that passed IE/CFO approval — so the interesting tests are the
refusals, not the happy path: an unapproved base case must yield no figures at
all, and a superseded one must never win over the live claim.

Claims are written straight into the tables here. Going through `/tea/compute`
would need the :8002 engine, and the point under test is the read, not the run.
Uses `isolated_store`, so nothing touches the development database.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_economics as econ
from app.api.v1 import routes_tea as tea
from app.core import entitlements as ent

PROJECT = "proj_econ_test"
USER = "econ_user"


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    tea.DB_PATH = isolated_store          # the bridge caches the path at import
    econ.router  # noqa: B018 — import side effects only
    tea.init_db()
    ent.init_entitlements_db()
    ent.grant_entitlement(user_id=USER, project_id=PROJECT, granted_by="test")


@pytest.fixture()
def client() -> TestClient:
    api = FastAPI()
    api.include_router(econ.router, prefix="/api/v1/economics")
    return TestClient(api)


@pytest.fixture(autouse=True)
def _clean():
    conn = sqlite3.connect(tea.DB_PATH)
    try:
        conn.execute("DELETE FROM model_base_case")
        conn.execute("DELETE FROM pathway_claims")
        conn.commit()
    finally:
        conn.close()


def _base_case(state: str = "verified", *, project_id: str = PROJECT,
               pathway_id: str = "pw_1", valid_to: str | None = None,
               lcop: float = 4617.0, created_at: str = "2026-09-18T10:00:00Z") -> str:
    claim_id = f"CLM-MBC-{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(tea.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO model_base_case (claim_id, project_id, pathway_id, state, engine,"
            " cost_basis_hash, capex_eur, opex_eur_per_year, lcop, nameplate_capacity,"
            " nameplate_unit, run_evidence_id, approved_by, approval_decision_id,"
            " valid_from, valid_to, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (claim_id, project_id, pathway_id, state, "openpytea",
             f"hash_{claim_id}", 201_000_000.0, 131_000_000.0, lcop, 40_000.0,
             "t_per_year", "EV-1", "ie@example.com" if state == "verified" else None,
             "DEC-1" if state == "verified" else None,
             created_at, valid_to, created_at))
        conn.commit()
    finally:
        conn.close()
    return claim_id


def _ghg_claim(claim_type: str, value: float, state: str, method: str = "Annex VI"):
    conn = sqlite3.connect(tea.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO pathway_claims (claim_id, project_id, pathway_id, subject_node,"
            " claim_type, value_type, value, unit, state, method, evidence_id,"
            " approved_by, valid_from, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"CLM-{uuid.uuid4().hex[:8]}", PROJECT, "pw_1", "ghg_lca", claim_type,
             "numeric", value, "gCO2e/MJ" if claim_type == "g_co2e_per_mj" else "fraction",
             state, method, "EV-2", "ie@example.com" if state == "verified" else None,
             "2026-09-18T10:00:00Z", "2026-09-18T10:00:00Z"))
        conn.commit()
    finally:
        conn.close()


def _get(client: TestClient, project_id: str = PROJECT, user: str = USER):
    return client.get(f"/api/v1/economics/snapshot/{project_id}",
                      headers={"x-demo-user": user})


# ── the refusals, which are the point ───────────────────────────────────────

def test_an_unapproved_base_case_yields_no_figures(client):
    _base_case(state="submitted")
    r = _get(client)
    assert r.status_code == 409, r.text
    body = r.text
    assert "BASE_CASE_NOT_APPROVED" in body and "submitted" in body
    # The refusal must not leak the provisional numbers it is refusing to serve.
    for leaked in ("201000000", "131000000", "4617"):
        assert leaked not in body.replace(".0", "")


def test_no_base_case_is_a_404_not_an_empty_shape(client):
    # Entitled to the project, but nothing has been computed for it yet.
    ent.grant_entitlement(user_id=USER, project_id="proj_empty", granted_by="test")
    assert _get(client, project_id="proj_empty").status_code == 404


def test_an_unentitled_caller_cannot_learn_whether_a_project_exists(client):
    """403 before 404, deliberately: if a missing project answered 404 and a real
    one answered 403, the status code would enumerate the portfolio."""
    _base_case(state="verified")                      # PROJECT exists
    exists = _get(client, project_id=PROJECT, user="stranger_no_grant")
    missing = _get(client, project_id="proj_no_such_thing", user="stranger_no_grant")
    assert exists.status_code == missing.status_code == 403


def test_a_superseded_claim_never_wins_over_the_live_one(client):
    _base_case(state="superseded", lcop=9999.0, created_at="2026-09-18T12:00:00Z")
    _base_case(state="verified", lcop=4617.0, created_at="2026-09-18T11:00:00Z")
    r = _get(client)
    assert r.status_code == 200, r.text
    assert r.json()["economics"]["lcop"] == 4617.0


def test_a_closed_claim_valid_to_is_not_served(client):
    _base_case(state="verified", valid_to="2026-09-18T11:00:00Z")
    assert _get(client).status_code == 404


# ── the approved read ───────────────────────────────────────────────────────

def test_an_approved_claim_is_served_with_its_own_identity(client):
    claim_id = _base_case(state="verified")
    r = _get(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claim"]["claim_id"] == claim_id
    assert body["claim"]["approved_by"] == "ie@example.com"
    # The hash travels with the figures: two reports with one hash are one run.
    assert body["basis"]["cost_basis_hash"] == f"hash_{claim_id}"
    assert body["economics"]["lcop"] == 4617.0
    assert body["economics"]["capex_eur"] == 201_000_000.0
    assert body["basis"]["nameplate_unit"] == "t_per_year"


def test_every_response_carries_the_provisional_disclaimer(client):
    _base_case(state="verified")
    body = _get(client).json()
    assert body["integrity"]["ascertained"] is False
    assert "verifier-signed" in body["integrity"]["note"]


def test_what_is_not_persisted_is_named_rather_than_omitted(client):
    _base_case(state="verified")
    missing = _get(client).json()["not_available"]
    assert set(missing) >= {"cost_stack", "regime", "sensitivity_tornado", "why"}
    assert "recomput" in missing["why"].lower()


# ── the GHG claims follow the same approval rule ────────────────────────────

def test_an_approved_ghg_claim_contributes_its_value(client):
    _base_case(state="verified")
    _ghg_claim("g_co2e_per_mj", 9.9, "verified")
    lca = _get(client).json()["lca"]
    assert lca["g_co2e_per_mj"]["value"] == 9.9
    assert lca["g_co2e_per_mj"]["unit"] == "gCO2e/MJ"
    assert lca["g_co2e_per_mj"]["approved"] is True


def test_an_unapproved_ghg_claim_contributes_its_state_and_not_its_value(client):
    _base_case(state="verified")
    _ghg_claim("g_co2e_per_mj", 9.9, "submitted")
    entry = _get(client).json()["lca"]["g_co2e_per_mj"]
    assert entry["approved"] is False and entry["state"] == "submitted"
    assert "value" not in entry


def test_a_greet_method_carries_the_approximation_note(client):
    _base_case(state="verified")
    _ghg_claim("g_co2e_per_mj", 4.0, "verified", method="GREET 45V")
    lca = _get(client).json()["lca"]
    assert "approximation" in lca["method_note"]
    assert "not the licensed ANL model" in lca["method_note"]


def test_no_ghg_claim_reads_as_absent_not_as_zero(client):
    _base_case(state="verified")
    assert _get(client).json()["lca"]["g_co2e_per_mj"] is None


# ── project scoping ─────────────────────────────────────────────────────────

def test_a_caller_without_an_entitlement_is_refused(client):
    _base_case(state="verified")
    r = _get(client, user="stranger_no_grant")
    assert r.status_code == 403, r.text


def test_the_route_is_registered_against_a_domain():
    """A route with no domain fails test_every_api_route_maps_to_a_domain; this
    says which domain it is, so the answer is deliberate rather than inherited."""
    from app.core.domain_authorization import domain_for_path

    assert domain_for_path("/api/v1/economics/snapshot/proj_x") == "finance"
