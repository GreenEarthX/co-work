"""
DEVEX brief routes (/api/v1/devex-brief). The policy is tested in
test_devex_share.py and test_pre_fid_access.py; this pins the wiring: the
caller comes from the verified token, a refusal is a 403 and is audited, data
is read in the owner's tenant taken from the project record, a failed read is
503 and not an empty brief, and only the owner's finance or executive shares.

Isolated: the entitlement store, the project record and both readers are faked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_devex_share import PACKAGES, WAVE  # noqa: E402

OWNER_TENANT = "t_owner_0042"       # the tenant id on the project record; not a slug of the name
OWNER_CFO = {"user_id": "u_cfo", "company_id": OWNER_TENANT, "business_function": "FINANCE_TREASURY"}
BANKER = {"user_id": "u_bank", "company_id": "north_bank", "service_type": "BANK"}


class FakeStore:
    def __init__(self):
        self.rows, self.audit = [], []

    def list_entitlements(self, *, user_id=None, project_id=None):
        return [r for r in self.rows if (not user_id or r["user_id"] == user_id)
                and (not project_id or r["project_id"] == project_id)]

    def grant_entitlement(self, **kw):
        row = {"entitlement_id": f"e{len(self.rows) + 1}", "granted_at": "2026-11-16T00:00:00+00:00",
               "revoked_at": None, "revoked_by": None, "status": "active", **kw}
        self.rows.append(row)
        return row

    def get_entitlement(self, entitlement_id):
        return next((r for r in self.rows if r["entitlement_id"] == entitlement_id), None)

    def revoke_entitlement(self, entitlement_id, *, revoked_by):
        row = self.get_entitlement(entitlement_id)
        row.update(status="revoked", revoked_at="2026-11-17T00:00:00+00:00", revoked_by=revoked_by)
        return row

    def log_access(self, **kw):
        self.audit.append(kw)


@pytest.fixture
def client(monkeypatch):
    import app.api.v1.routes_devex_brief as rd
    import app.core.pre_fid_access as pfa

    store, reads = FakeStore(), []
    record = {"project_id": "P1", "project_name": "Project One", "owner_tenant_id": OWNER_TENANT}
    monkeypatch.setattr(rd, "ent", store)
    monkeypatch.setattr(pfa, "_owner_record", lambda pid: record if pid == "P1" else None)
    monkeypatch.setattr(pfa, "_active_sections", lambda user, pid: [
        rd.section_of(r["capability"]) for r in store.list_entitlements(user_id=user, project_id=pid)
        if rd.section_of(r["capability"]) and r["status"] == "active"])
    monkeypatch.setattr(pfa, "_audit", lambda **kw: store.log_access(**kw))
    monkeypatch.setattr(rd, "_read_packages", lambda pid, tenant: reads.append(tenant) or PACKAGES)
    monkeypatch.setattr(rd, "_read_spend_wave", lambda pid, tenant: (WAVE, "UNVERIFIED"))

    app = FastAPI()

    @app.middleware("http")
    async def bind_payload(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(rd.router)
    tc = TestClient(app)
    tc.store, tc.reads = store, reads
    tc.as_ = lambda who: {"x-test-payload": json.dumps(who)}
    return tc


def test_no_token_is_401_and_unknown_project_is_404(client):
    assert client.get("/api/v1/devex-brief/P1").status_code == 401
    assert client.get("/api/v1/devex-brief/NOPE", headers=client.as_(OWNER_CFO)).status_code == 404


def test_producer_finance_reads_everything_in_its_own_tenant(client):
    r = client.get("/api/v1/devex-brief/P1", headers=client.as_(OWNER_CFO))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["basis"] == "owner" and body["can_manage_shares"] is True
    assert body["sections"] == ["SUMMARY", "BREAKDOWN", "FUNDING", "PACKAGES"]
    assert client.reads == [OWNER_TENANT]


def test_a_bank_with_a_finance_role_but_no_share_is_refused_and_audited(client):
    client.store.grant_entitlement(user_id="u_bank", project_id="P1", granted_by="admin",
                                   capability="FINANCE_REVIEW", reason=None, expires_at=None)
    r = client.get("/api/v1/devex-brief/P1", headers=client.as_(BANKER))
    assert r.status_code == 403
    assert client.reads == []                                   # nothing was read for a refused caller
    assert client.store.audit[-1]["allowed"] is False and client.store.audit[-1]["route"] == "devex_brief"


def test_owner_shares_two_sections_and_the_bank_reads_only_those_as_the_owner_tenant(client):
    made = client.post("/api/v1/devex-brief/P1/shares", headers=client.as_(OWNER_CFO),
                       json={"user_id": "u_bank", "sections": ["FUNDING", "SUMMARY"], "expires_at": "2099-01-31"})
    assert made.status_code == 201, made.text
    assert [s["section"] for s in made.json()["shares"]] == ["SUMMARY", "FUNDING"]
    assert made.json()["shares"][0]["expires_at"] == "2099-01-31T00:00:00+00:00"

    r = client.get("/api/v1/devex-brief/P1", headers=client.as_(BANKER))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["basis"], body["read_only"], body["can_manage_shares"]) == ("share", True, False)
    assert body["sections"] == ["SUMMARY", "FUNDING"]
    assert "packages" not in body and "breakdown" not in body
    assert client.reads == [OWNER_TENANT]                       # read in the owner's tenant, from the record

    again = client.post("/api/v1/devex-brief/P1/shares", headers=client.as_(OWNER_CFO),
                        json={"user_id": "u_bank", "sections": ["SUMMARY"]})
    assert again.json()["shares"] == [] and again.json()["already_shared"] == ["SUMMARY"]


def test_revoking_a_section_closes_it(client):
    client.post("/api/v1/devex-brief/P1/shares", headers=client.as_(OWNER_CFO),
                json={"user_id": "u_bank", "sections": ["SUMMARY"]})
    share_id = client.get("/api/v1/devex-brief/P1/shares", headers=client.as_(OWNER_CFO)).json()["shares"][0]["entitlement_id"]
    assert client.delete(f"/api/v1/devex-brief/P1/shares/{share_id}", headers=client.as_(OWNER_CFO)).json()["status"] == "revoked"
    assert client.get("/api/v1/devex-brief/P1", headers=client.as_(BANKER)).status_code == 403


def test_an_associated_company_and_an_owner_engineer_are_not_sent_the_brief(client):
    associated = {"user_id": "u_assoc", "company_id": "co_sponsor", "business_function": "FINANCE_TREASURY"}
    assert client.get("/api/v1/devex-brief/P1", headers=client.as_(associated)).status_code == 403
    engineer = {**OWNER_CFO, "user_id": "u_eng", "business_function": "ENGINEERING"}
    assert client.get("/api/v1/devex-brief/P1", headers=client.as_(engineer)).status_code == 403
    client.post("/api/v1/devex-brief/P1/shares", headers=client.as_(OWNER_CFO),
                json={"user_id": "u_assoc", "sections": ["SUMMARY"]})
    shared = client.get("/api/v1/devex-brief/P1", headers=client.as_(associated))
    assert shared.status_code == 200 and shared.json()["sections"] == ["SUMMARY"]


def test_a_failed_read_is_503_not_an_empty_brief(client, monkeypatch):
    import app.api.v1.routes_devex_brief as rd
    import app.core.pre_fid_access as pfa

    def down(*_a, **_k):
        raise RuntimeError("database is down")

    monkeypatch.setattr(rd, "_read_packages", down)
    r = client.get("/api/v1/devex-brief/P1", headers=client.as_(OWNER_CFO))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "PRE_FID_DATA_UNAVAILABLE"
    monkeypatch.setattr(pfa, "_owner_record", down)
    assert client.get("/api/v1/devex-brief/P1", headers=client.as_(OWNER_CFO)).status_code == 503


def test_only_the_owner_manages_shares_and_bad_requests_are_422(client):
    for who in (BANKER, {**OWNER_CFO, "business_function": "ENGINEERING"},
                {**OWNER_CFO, "company_id": "acme_fuels"}):
        assert client.get("/api/v1/devex-brief/P1/shares", headers=client.as_(who)).status_code == 403
        assert client.post("/api/v1/devex-brief/P1/shares", headers=client.as_(who),
                           json={"user_id": "u_bank", "sections": ["SUMMARY"]}).status_code == 403
    bad = client.post("/api/v1/devex-brief/P1/shares", headers=client.as_(OWNER_CFO),
                      json={"user_id": "u_bank", "sections": ["RETURNS"]})
    assert bad.status_code == 422 and "unknown section" in bad.json()["detail"]
    assert client.delete("/api/v1/devex-brief/P1/shares/nope", headers=client.as_(OWNER_CFO)).status_code == 404
