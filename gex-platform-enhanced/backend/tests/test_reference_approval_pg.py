"""An on-screen approval reaches the registry through its REAL row-level policies (20 Nov 2026).

The staff console's Approve button posts /reference/parameters/{id}/approve as a GEX staff
account, whose company is `greenearthx`, not PLATFORM_ADMIN. The registry's write policies
(061) admit only PLATFORM_ADMIN, so under the caller's own tenant the approval's UPDATE matched
0 rows in silence and its version insert was refused: no approval made on screen was ever
recorded. test_reference_routes only reached the staff gate, so nothing caught it. Here the
whole write runs on a throwaway database built by the migrations (pg_store).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_reference

STAFF_PROPOSER = {"user_id": "usr_test_ref_proposer", "company_id": "greenearthx", "is_platform_admin": True}
STAFF_APPROVER = {"user_id": "usr_test_ref_approver", "company_id": "greenearthx", "is_platform_admin": True}
BODY = {"parameter_key": "h2_price_grey", "pathway": "ANY", "region": "XA",
        "value_base": 2.0, "unit": "EUR/kg", "currency": "EUR", "price_base_date": "2025-01-01",
        "source_class": "public_source", "source_name": "TEST fixture", "valid_from": "2026-01-01"}


def _client(payload: dict) -> TestClient:
    from app.core.request_tenant import company_from_payload, reset_current_company, set_current_company
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
    return TestClient(api)


def _propose(pg_store, region: str) -> str:
    r = _client(STAFF_PROPOSER).post("/api/v1/reference/parameters", json={**BODY, "region": region})   # XA-XC: ISO user-assigned, never a real country
    assert r.status_code == 201, r.text
    return r.json()["ref_id"]


def test_a_staff_approval_on_screen_is_recorded(pg_store):
    from app.core import reference_registry as reg
    ref = _propose(pg_store, "XA")
    before = _client(STAFF_APPROVER).get("/api/v1/reference/versions/latest")
    n0 = before.json()["version_number"] if before.status_code == 200 else 0
    r = _client(STAFF_APPROVER).post(f"/api/v1/reference/parameters/{ref}/approve")
    assert r.status_code == 200, r.text
    conn = reg._connection()
    try:
        row = reg.get_row(conn, ref)
    finally:
        conn.close()
    assert row["state"] == "approved" and row["approved_by"] == "usr_test_ref_approver"
    assert r.json()["version"]["version_number"] == n0 + 1
    again = _client(STAFF_APPROVER).post(f"/api/v1/reference/parameters/{ref}/approve")
    assert again.status_code == 409


def test_the_proposer_cannot_approve_and_a_rejection_is_recorded(pg_store):
    ref = _propose(pg_store, "XB")
    assert _client(STAFF_PROPOSER).post(f"/api/v1/reference/parameters/{ref}/approve").status_code == 403
    r = _client(STAFF_APPROVER).post(f"/api/v1/reference/parameters/{ref}/reject")
    assert r.status_code == 200 and r.json()["state"] == "rejected"


def test_a_decision_that_changes_no_row_is_refused_not_reported(pg_store):
    """The silent no-op itself: on a connection the policies do not let write, approve raises."""
    from app.core import reference_registry as reg
    from app.core.db_backend import fuelref_connection
    ref = _propose(pg_store, "XC")
    conn = fuelref_connection(company_id="greenearthx")
    try:
        with pytest.raises(reg.RegistryError, match="0 rows changed"):
            reg.approve(conn, ref, "usr_test_ref_approver")
        conn.rollback()
    finally:
        conn.close()


def _staff_token(uid: str) -> dict:
    from app.core.auth import create_access_token
    return {"Authorization": "Bearer " + create_access_token({
        "user_id": uid, "email": f"{uid}@test.invalid", "company_id": "greenearthx", "company_name": "GreenEarthX",
        "company_type": "PLATFORM", "service_type": "PLATFORM", "business_function": "EXECUTIVE", "user_name": uid,
        "clearance_level": "STANDARD", "jurisdiction": "DE", "kyc_status": "VERIFIED", "nda_signed_with": [],
        "assigned_audits": [], "actor_type_per_project": {}, "is_platform_admin": True})[0]}


def test_the_whole_app_records_a_staff_approval(pg_store):
    """The same call through the FULL middleware stack (ABAC, domain authorization, CSRF), as the
    console's click takes it; the tests above mount the router alone."""
    from app.core import reference_registry as reg
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/reference/parameters", json={**BODY, "region": "XD"}, headers=_staff_token("usr_test_ref_p2"))
    assert r.status_code == 201, r.text
    ref = r.json()["ref_id"]
    a = c.post(f"/api/v1/reference/parameters/{ref}/approve", headers=_staff_token("usr_test_ref_a2"))
    assert a.status_code == 200, a.text
    conn = reg._connection()
    try:
        assert reg.get_row(conn, ref)["state"] == "approved"
    finally:
        conn.close()
