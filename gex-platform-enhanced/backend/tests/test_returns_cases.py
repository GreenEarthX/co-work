"""
Published returns cases (handoff v4, tasks 8 and 10; Part C tests 10, 11, 12, 13, 16).

Each test states its business rule and builds its own inputs. Isolated: the
entitlement store, the project record, the case store and the PF engine are
faked; the engine fake returns a fixed result, so what is tested is that a
reader's permissions change what is SHOWN, never what was COMPUTED.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tests.test_devex_brief_routes import FakeStore

OWNER_TENANT = "t_owner_0042"
OWNER_CFO = {"user_id": "u_cfo", "company_id": OWNER_TENANT, "business_function": "FINANCE_TREASURY"}
OWNER_ENGINEER = {"user_id": "u_eng", "company_id": OWNER_TENANT, "business_function": "ENGINEERING"}
BANKER = {"user_id": "u_bank", "company_id": "north_bank", "service_type": "BANK"}
INSURER = {"user_id": "u_ins", "company_id": "safe_ins", "service_type": "INSURER"}

INPUTS = {"fci_eur": 100.0, "operating_years": 10, "revenue_y1_eur": 30.0, "opex_y1_eur": 10.0,
          "tax_rate": 0.25, "depreciation_years": 10, "pre_fid_spend_eur": [4.0, 6.0], "cost_of_equity": 0.12}


def engine_result(boundary: str, scenario: str) -> dict:
    """Shaped like the PF engine's returns result: pre-FID periods -2 and -1."""
    full = boundary == "FULL_PROJECT"
    return {
        "model_version": "1.3.0", "valuation_boundary": boundary, "scenario": scenario,
        "unlevered_irr": 0.091 if full else 0.104, "levered_irr": 0.15 if full else 0.17,
        "devex_eur": 10.0 if full else 0.0, "total_investment_eur": 110.0 if full else 100.0,
        "equity_invested_eur": 50.0, "npv_unlevered_eur": 3.2,
        "flows": {"first_period": -2 if full else 0,
                  "unlevered": ([-4.0, -6.0] if full else []) + [-100.0] + [17.0] * 10,
                  "levered": ([-4.0, -6.0] if full else []) + [-40.0] + [9.0] * 10},
        "timeline": ([{"period": -2, "phase": "PRE_FID"}, {"period": -1, "phase": "PRE_FID"}] if full else [])
                    + [{"period": 0, "phase": "CONSTRUCTION"}],
        "downside": {"rows": [{"id": "CAPEX_PLUS_10", "unlevered_irr": 0.08}]},
        "provenance": {"inputs": dict(INPUTS), "inputs_sha256": "abc", "validation_checks": []},
    }


@pytest.fixture
def client(monkeypatch):
    import app.api.v1.routes_returns_cases as rr
    import app.api.v1.routes_finance_model as rfm
    import app.api.v1.routes_bankability_proxy as proxy
    import app.core.pre_fid_access as pfa
    import app.core.readiness as readiness
    from app.core.devex_share import section_of

    store, cases = FakeStore(), []
    state = {"fingerprint": "fp-1", "calls": 0}
    record = {"project_id": "P1", "project_name": "Project One", "owner_tenant_id": OWNER_TENANT}
    monkeypatch.setattr(rr, "ent", store)
    monkeypatch.setattr(pfa, "_owner_record", lambda pid: record if pid == "P1" else None)
    monkeypatch.setattr(pfa, "_active_sections", lambda user, pid: [
        section_of(r["capability"]) for r in store.list_entitlements(user_id=user, project_id=pid)
        if section_of(r["capability"]) and r["status"] == "active"])
    monkeypatch.setattr(pfa, "_audit", lambda **kw: store.log_access(**kw))
    monkeypatch.setattr(rr, "_versions", lambda pid, tenant: [copy.deepcopy(c) for c in cases if c["project_id"] == pid])
    monkeypatch.setattr(rr, "_insert", lambda tenant, rec: (cases.append(
        {**json.loads(json.dumps(rec)), "published_at": "2026-11-17T10:00:00+00:00"}) or copy.deepcopy(cases[-1])))
    monkeypatch.setattr(rr, "_current_tea_claim", lambda pid, tenant: None)
    withdrawals = {}
    monkeypatch.setattr(rr, "_withdrawals", lambda pid, tenant: {k: copy.deepcopy(v) for k, v in withdrawals.items()
                                                                 if v["project_id"] == pid})
    monkeypatch.setattr(rr, "_insert_withdrawal", lambda tenant, row: withdrawals.__setitem__(
        row["version_id"], {**row, "withdrawn_at": "2026-11-18T16:00:00+00:00"}))

    async def fake_call(path, method="GET", json_data=None, request=None):
        state["calls"] += 1
        return {"returns": engine_result(json_data["valuation_boundary"], json_data["scenario"])}

    async def fake_current(pid):
        return {"current_state": "SPECULATIVE"}, "2026-11-17", {
            "status": "CURRENT", "rules_version": "4.8.0", "evidence_fingerprint": state["fingerprint"],
            "evaluated_at": "2026-11-17"}

    async def fake_rules():
        return {"rules_version": "4.8.0"}

    monkeypatch.setattr(rfm, "_call_model", fake_call)
    monkeypatch.setattr(readiness, "current", fake_current)
    monkeypatch.setattr(readiness, "current_fingerprint", lambda pid: state["fingerprint"])
    monkeypatch.setattr(proxy, "engine_rules", fake_rules)

    app = FastAPI()

    @app.middleware("http")
    async def bind_payload(request: Request, call_next):
        raw = request.headers.get("x-test-payload")
        request.state.user_payload = json.loads(raw) if raw else None
        return await call_next(request)

    app.include_router(rr.router)
    tc = TestClient(app)
    tc.store, tc.cases, tc.state = store, cases, state
    tc.as_ = lambda who: {"x-test-payload": json.dumps(who)}
    return tc


def publish(client, name="Base case", scenario="BASE", boundary="FULL_PROJECT", who=OWNER_CFO):
    return client.post("/api/v1/returns-cases/P1", headers=client.as_(who), json={
        "case_name": name, "scenario": scenario, "valuation_boundary": boundary, "inputs": INPUTS})


def share(client, **target):
    return client.post("/api/v1/returns-cases/P1/shares", headers=client.as_(OWNER_CFO),
                       json={"user_id": BANKER["user_id"], **target})


def test_only_the_owners_finance_publishes_and_a_version_is_identified_and_hashed(client):
    """Rule: returns cases are published by the owner (finance or executive). A version
    carries its identity — project, scenario, boundary, model and rules versions,
    evidence snapshot, publication — and a content hash."""
    assert publish(client, who=BANKER).status_code == 403
    assert publish(client, who=OWNER_ENGINEER).status_code == 403
    r = publish(client)
    assert r.status_code == 201
    ident = r.json()["identity"]
    assert ident["version_number"] == 1 and ident["scenario"] == "BASE"
    assert ident["valuation_boundary"] == "FULL_PROJECT" and ident["model_version"] == "1.3.0"
    assert ident["rules_version"] == "4.8.0" and ident["evidence_fingerprint"] == "fp-1"
    assert re.fullmatch(r"[0-9a-f]{64}", ident["content_sha256"])


def test_a_new_version_supersedes_and_the_old_one_stays_as_it_was(client):
    """Rule: a published version is immutable; a new one names what it supersedes."""
    v1 = publish(client).json()
    v2 = publish(client).json()
    assert v2["identity"]["version_number"] == 2
    assert v2["identity"]["supersedes_version_id"] == v1["identity"]["version_id"]
    again = client.get(f"/api/v1/returns-cases/P1/versions/{v1['identity']['version_id']}", headers=client.as_(OWNER_CFO))
    assert again.json()["identity"] == v1["identity"] and again.json()["results"] == v1["results"]


def test_base_downside_and_from_fid_are_distinguishable_everywhere(client):
    """Rule (test 10): base, downside and FROM_FID are different cases, identified as such."""
    publish(client)
    publish(client, name="Downside", scenario="DOWNSIDE")
    publish(client, name="From FID", boundary="FROM_FID")
    listing = client.get("/api/v1/returns-cases/P1", headers=client.as_(OWNER_CFO)).json()["versions"]
    keys = {(v["case_id"], v["scenario"], v["valuation_boundary"]) for v in listing}
    assert len(keys) == 3
    from_fid = next(v for v in listing if v["valuation_boundary"] == "FROM_FID")
    assert "NOT a full-project return" in from_fid["valuation_boundary_label"]


def test_a_reader_without_a_share_sees_no_returns_of_the_project(client):
    """Rule (task 8): a reader with neither FUNDING nor RETURNS sees no returns of that project."""
    v1 = publish(client).json()["identity"]["version_id"]
    assert client.get("/api/v1/returns-cases/P1", headers=client.as_(BANKER)).status_code == 403
    assert client.get(f"/api/v1/returns-cases/P1/versions/{v1}", headers=client.as_(BANKER)).status_code == 403


def test_returns_share_shows_the_owners_figures_without_dated_pre_fid_data(client):
    """Rule (test 11): a bank with RETURNS for a FULL_PROJECT case sees the same IRR as the
    owner, and no dated pre-FID figure. No reader's permissions produce a different case."""
    owner_view = publish(client).json()
    vid = owner_view["identity"]["version_id"]
    share(client, version_id=vid)
    bank = client.get(f"/api/v1/returns-cases/P1/versions/{vid}", headers=client.as_(BANKER)).json()
    assert bank["results"]["unlevered_irr"] == owner_view["results"]["unlevered_irr"]
    assert bank["results"]["levered_irr"] == owner_view["results"]["levered_irr"]
    assert bank["identity"]["content_sha256"] == owner_view["identity"]["content_sha256"]
    assert bank["results"]["flows"]["first_period"] >= 0
    assert all(row["period"] >= 0 for row in bank["results"]["timeline"])
    assert "pre_fid_spend_eur" not in bank["provenance"]["inputs"]
    assert "devex_eur" not in bank["results"]          # DEVEX totals need SUMMARY
    assert client.state["calls"] == 1                  # the reader's request computed nothing


def test_returns_opens_no_pre_fid_section_and_summary_opens_no_return(client):
    """Rule (test 12): RETURNS does not open FUNDING, PACKAGES or EVIDENCE; SUMMARY generates no return."""
    vid = publish(client).json()["identity"]["version_id"]
    share(client, version_id=vid)
    from app.core import pre_fid_access
    from starlette.requests import Request as R
    import app.core.request_tenant as rt
    # The DEVEX decision for the banker: no DEVEX section opened by a RETURNS share.
    rows = client.store.list_entitlements(user_id=BANKER["user_id"], project_id="P1")
    assert all(r["capability"].startswith("RETURNS_SHARE:") for r in rows)
    from app.core.devex_share import section_of
    assert [section_of(r["capability"]) for r in rows] == [None]
    # A SUMMARY-only reader gets no return.
    client.store.grant_entitlement(user_id=INSURER["user_id"], project_id="P1", granted_by="u_cfo",
                                   capability="DEVEX_SHARE:SUMMARY", reason=None, expires_at=None)
    assert client.get("/api/v1/returns-cases/P1", headers=client.as_(INSURER)).status_code == 403
    assert client.get(f"/api/v1/returns-cases/P1/versions/{vid}", headers=client.as_(INSURER)).status_code == 403


def test_summary_with_returns_shows_the_devex_total_but_never_dated_spend(client):
    vid = publish(client).json()["identity"]["version_id"]
    share(client, version_id=vid)
    client.store.grant_entitlement(user_id=BANKER["user_id"], project_id="P1", granted_by="u_cfo",
                                   capability="DEVEX_SHARE:SUMMARY", reason=None, expires_at=None)
    bank = client.get(f"/api/v1/returns-cases/P1/versions/{vid}", headers=client.as_(BANKER)).json()
    assert bank["results"]["devex_eur"] == 10.0
    assert bank["results"]["flows"]["first_period"] >= 0


def test_a_version_share_does_not_open_later_versions_unless_chosen(client):
    v1 = publish(client).json()["identity"]
    v2 = publish(client).json()["identity"]
    share(client, version_id=v1["version_id"])
    assert client.get(f"/api/v1/returns-cases/P1/versions/{v2['version_id']}", headers=client.as_(BANKER)).status_code == 403
    share(client, case_id=v1["case_id"])
    assert client.get(f"/api/v1/returns-cases/P1/versions/{v2['version_id']}", headers=client.as_(BANKER)).status_code == 200


def test_revocation_closes_every_path_on_the_next_request(client):
    """Rule (test 12): revoking a share closes it on every path at the next request."""
    vid = publish(client).json()["identity"]["version_id"]
    eid = share(client, version_id=vid).json()["share"]["entitlement_id"]
    paths = ["/api/v1/returns-cases/P1", f"/api/v1/returns-cases/P1/versions/{vid}",
             f"/api/v1/returns-cases/P1/versions/{vid}/export"]
    assert all(client.get(p, headers=client.as_(BANKER)).status_code == 200 for p in paths)
    assert client.delete(f"/api/v1/returns-cases/P1/shares/{eid}", headers=client.as_(OWNER_CFO)).status_code == 200
    assert all(client.get(p, headers=client.as_(BANKER)).status_code == 403 for p in paths)


def test_every_response_is_no_store(client):
    """Rule (test 12): responses carrying a returns case are never cached."""
    vid = publish(client).json()["identity"]["version_id"]
    for path in ("/api/v1/returns-cases/P1", f"/api/v1/returns-cases/P1/versions/{vid}",
                 f"/api/v1/returns-cases/P1/versions/{vid}/export"):
        assert client.get(path, headers=client.as_(OWNER_CFO)).headers["cache-control"] == "no-store"


def test_screen_and_export_show_identical_figures_and_identity(client):
    """Rule (test 10): every screen and export citing a version shows the same figures."""
    vid = publish(client).json()["identity"]["version_id"]
    screen = client.get(f"/api/v1/returns-cases/P1/versions/{vid}", headers=client.as_(OWNER_CFO)).json()
    export = client.get(f"/api/v1/returns-cases/P1/versions/{vid}/export", headers=client.as_(OWNER_CFO)).json()
    assert export["identity"] == screen["identity"] and export["results"] == screen["results"]


def test_changed_evidence_flags_needs_review_without_changing_the_case(client):
    """Rule (test 10): if the evidence behind a published case changes, the case is
    flagged "needs review", it is not changed, and no new figure replaces it."""
    first = publish(client).json()
    vid = first["identity"]["version_id"]
    assert first["review"]["needs_review"] is False
    client.state["fingerprint"] = "fp-2"
    later = client.get(f"/api/v1/returns-cases/P1/versions/{vid}", headers=client.as_(OWNER_CFO)).json()
    assert later["review"]["needs_review"] is True
    assert [c["what"] for c in later["review"]["changes"]] == ["EVIDENCE"]
    assert later["results"] == first["results"] and later["identity"] == first["identity"]


def test_templates_grant_nothing():
    """Rule (test 13): a recipient whose party type matches a template, with no share,
    sees nothing the template lists. Templates are proposals only."""
    from app.core.audience_templates import suggestions
    s = suggestions()
    assert s["grants_access"] is False and "PROPOSED" in s["status"]


def test_templates_grant_nothing_on_the_routes(client):
    vid = publish(client).json()["identity"]["version_id"]
    from app.core.audience_templates import TEMPLATES
    assert TEMPLATES["SENIOR_LENDER"]["returns"] is True        # the lender template lists returns …
    assert client.get(f"/api/v1/returns-cases/P1/versions/{vid}", headers=client.as_(BANKER)).status_code == 403
    assert client.get("/api/v1/returns-cases/P1/audience-templates", headers=client.as_(BANKER)).status_code == 403


def test_validity_language_travels_with_every_case(client):
    """Rule (test 16): no case is described as an assured outcome."""
    body = publish(client).json()
    assert "does not mean the forecast outcome is assured" in body["validity"]


VALIDITY_PATTERN = re.compile(
    r"(verified|published)[ -](base[ -])?case[^.\n]{0,80}\b(guarantee[sd]?|assure[sd]?|certain(ty)?|will (achieve|deliver))",
    re.IGNORECASE)
NEGATED = re.compile(r"(does not|doesn't|never|not)\s+(mean|imply|claim|describe|guarantee|assure)", re.IGNORECASE)


def test_no_screen_report_or_export_text_describes_a_case_as_an_assured_outcome():
    """Rule (test 16): scan the application's own text (backend app, frontend src) for a
    verified or published case described as assured, guaranteed or certain."""
    root = Path(__file__).resolve().parents[2]
    offenders = []
    for base, exts in ((root / "backend" / "app", (".py",)), (root / "frontend" / "src", (".ts", ".tsx"))):
        for f in base.rglob("*"):
            if f.suffix not in exts or "__tests__" in f.parts or "node_modules" in f.parts:
                continue
            for line_no, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if VALIDITY_PATTERN.search(line) and not NEGATED.search(line):
                    offenders.append(f"{f.relative_to(root)}:{line_no}: {line.strip()[:120]}")
    assert offenders == []


# ── Withdrawal from reliance (migration 125; JML 18 Nov 2026) ──────────────────

def _withdraw(client, vid, who=OWNER_CFO, reason="TEA priced another plant boundary"):
    return client.post(f"/api/v1/returns-cases/P1/versions/{vid}/withdraw", headers=client.as_(who),
                       json={"reason": reason})


def test_withdrawal_revokes_the_share_and_closes_every_reader_path(client):
    v1 = publish(client).json()["identity"]["version_id"]
    assert share(client, version_id=v1).status_code == 201
    assert client.get(f"/api/v1/returns-cases/P1/versions/{v1}", headers=client.as_(BANKER)).status_code == 200
    r = _withdraw(client, v1)
    assert r.status_code == 201, r.text
    assert [s["user_id"] for s in r.json()["withdrawal"]["shares_revoked"]] == [BANKER["user_id"]]
    assert client.get(f"/api/v1/returns-cases/P1/versions/{v1}", headers=client.as_(BANKER)).status_code == 403
    assert client.get("/api/v1/returns-cases/P1", headers=client.as_(BANKER)).status_code == 403


def test_a_case_share_does_not_reopen_a_withdrawn_version(client):
    body = publish(client).json()["identity"]
    assert share(client, case_id=body["case_id"]).status_code == 201
    _withdraw(client, body["version_id"])
    assert client.get(f"/api/v1/returns-cases/P1/versions/{body['version_id']}",
                      headers=client.as_(BANKER)).status_code == 403
    v2 = publish(client).json()["identity"]["version_id"]           # the later version stays shared
    assert client.get(f"/api/v1/returns-cases/P1/versions/{v2}", headers=client.as_(BANKER)).status_code == 200


def test_the_owner_still_reads_a_withdrawn_version_unchanged_and_marked(client):
    v = publish(client).json()
    _withdraw(client, v["identity"]["version_id"])
    read = client.get(f"/api/v1/returns-cases/P1/versions/{v['identity']['version_id']}", headers=client.as_(OWNER_CFO)).json()
    assert read["withdrawal"]["reason"] == "TEA priced another plant boundary"
    assert read["identity"]["content_sha256"] == v["identity"]["content_sha256"]
    assert read["results"] == v["results"]


def test_withdrawal_is_the_owners_finance_only_once_and_a_withdrawn_version_cannot_be_shared(client):
    vid = publish(client).json()["identity"]["version_id"]
    assert _withdraw(client, vid, who=BANKER).status_code == 403
    assert _withdraw(client, vid, reason="short").status_code == 422
    assert _withdraw(client, vid).status_code == 201
    assert _withdraw(client, vid).status_code == 409
    assert share(client, version_id=vid).status_code == 409
