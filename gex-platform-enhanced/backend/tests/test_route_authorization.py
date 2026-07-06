"""
Route-level authorization tests (Ticket 1a / CI gate, hardened).

Proves sensitive endpoints reject unauthorized callers with 403 on a direct URL
call that bypasses the menu — and that role eligibility alone is NOT enough
(a Bank is allowed only on a project it is related to).

Run from backend/:  python -m pytest tests/test_route_authorization.py -q
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("GEX_PLATFORM_DB_PATH", os.path.join(tempfile.mkdtemp(), "route_auth.db"))

from fastapi import FastAPI                        # noqa: E402
from fastapi.testclient import TestClient          # noqa: E402

from app.core import entitlements as ent           # noqa: E402
from app.core.project_registry import company_slug # noqa: E402
from app.api.v1 import routes_finance_model as fm   # noqa: E402
from app.api.v1 import routes_pricing_proxy as pp   # noqa: E402

ent.init_entitlements_db()

app = FastAPI()
app.include_router(fm.router, prefix="/api/v1/finance-model")
app.include_router(pp.router, prefix="/api/v1/pricing")
client = TestClient(app)

PECOS = "proj_etf_pecos1"   # ING Capital is associated
BREMEN = "proj_bremen_h2"   # ING Capital is NOT associated
ING = company_slug("ING Capital")
RANDOM = company_slug("Unrelated Capital Ltd")


def H(user, *, company=None, fn=None, svc=None, caps=None):
    h = {"x-demo-user": user}
    if company: h["x-demo-company"] = company
    if fn: h["x-demo-function"] = fn
    if svc: h["x-demo-service-type"] = svc
    if caps: h["x-demo-capabilities"] = ",".join(caps)
    return h


def dscr(headers, asset):
    return client.get(f"/api/v1/finance-model/dscr-heatmap/{asset}", headers=headers).status_code

def decomp(headers, project):
    return client.post(f"/api/v1/pricing/decomposition?project_id={project}", headers=headers, json={"molecule": "H2"}).status_code


# ── DSCR endpoint: role eligibility ≠ project authorization ──────────────────
def test_unauthorized_role_403():
    # rt_ prefix avoids user-id collisions with the logic-test suite (shared DB).
    assert dscr(H("rt_log1", svc="LOGISTICS"), PECOS) == 403
    assert dscr(H("rt_eng_unauth", fn="ENGINEERING"), PECOS) == 403

def test_bank_allowed_only_on_related_project():
    assert dscr(H("bk", company=ING, svc="BANK"), PECOS) != 403    # related → passes guard
    assert dscr(H("bk", company=ING, svc="BANK"), BREMEN) == 403   # not related → 403
    assert dscr(H("bk2", company=RANDOM, svc="BANK"), PECOS) == 403  # unrelated bank → 403

def test_finance_role_no_company_denied():
    # qualified role but no company relationship resolvable → 403
    assert dscr(H("pf", fn="FINANCE_TREASURY"), PECOS) == 403

def test_grant_scopes_to_project():
    ent.grant_entitlement(user_id="eng_g", project_id=PECOS, granted_by="ciso")
    assert dscr(H("eng_g", company=RANDOM, fn="ENGINEERING"), PECOS) != 403
    assert dscr(H("eng_g", company=RANDOM, fn="ENGINEERING"), BREMEN) == 403

def test_revoked_403():
    rec = ent.grant_entitlement(user_id="eng_r", project_id=PECOS, granted_by="ciso")
    assert dscr(H("eng_r", fn="ENGINEERING"), PECOS) != 403
    ent.revoke_entitlement(rec["entitlement_id"], revoked_by="ciso")
    assert dscr(H("eng_r", fn="ENGINEERING"), PECOS) == 403

def test_expired_403():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ent.grant_entitlement(user_id="eng_e", project_id=PECOS, granted_by="ciso", expires_at=past)
    assert dscr(H("eng_e", fn="ENGINEERING"), PECOS) == 403

def test_unknown_project_403_for_bank():
    assert dscr(H("bk", company=ING, svc="BANK"), "proj_nope") == 403


# ── Pricing decomposition (Gabillon) endpoint ────────────────────────────────
def test_decomposition_unauthorized_403():
    assert decomp(H("log2", svc="LOGISTICS"), PECOS) == 403

def test_decomposition_bank_related_ok_unrelated_403():
    assert decomp(H("bk", company=ING, svc="BANK"), PECOS) != 403
    assert decomp(H("bk", company=ING, svc="BANK"), BREMEN) == 403

def test_decomposition_grant_scopes():
    ent.grant_entitlement(user_id="eng_d", project_id=PECOS, granted_by="ciso")
    assert decomp(H("eng_d", company=RANDOM, fn="ENGINEERING"), PECOS) != 403
    assert decomp(H("eng_d", company=RANDOM, fn="ENGINEERING"), BREMEN) == 403


# ── Drawdown / Financial Close timeline (R1 — sensitive layer endpoint) ──────
def dlt(headers, project):
    return client.get(f"/api/v1/finance-model/drawdown-timeline/{project}", headers=headers)

def test_drawdown_unauthorized_403():
    assert dlt(H("rt_log_dd", svc="LOGISTICS"), PECOS).status_code == 403
    assert dlt(H("rt_eng_dd", fn="ENGINEERING"), PECOS).status_code == 403

def test_drawdown_bank_related_ok_unrelated_403():
    ok = dlt(H("bk", company=ING, svc="BANK"), PECOS)
    assert ok.status_code == 200
    # Sensitive layer is served by the backend (so it need not ship in the bundle).
    assert "financial_close" in ok.json() and "drawdowns" in ok.json()
    assert dlt(H("bk", company=ING, svc="BANK"), BREMEN).status_code == 403

def test_drawdown_grant_scopes_A_not_B():
    ent.grant_entitlement(user_id="eng_dd2", project_id=PECOS, granted_by="ciso")
    assert dlt(H("eng_dd2", company=RANDOM, fn="ENGINEERING"), PECOS).status_code == 200
    assert dlt(H("eng_dd2", company=RANDOM, fn="ENGINEERING"), BREMEN).status_code == 403

def test_drawdown_revoked_and_expired_403():
    rec = ent.grant_entitlement(user_id="eng_dd3", project_id=PECOS, granted_by="ciso")
    assert dlt(H("eng_dd3", fn="ENGINEERING"), PECOS).status_code == 200
    ent.revoke_entitlement(rec["entitlement_id"], revoked_by="ciso")
    assert dlt(H("eng_dd3", fn="ENGINEERING"), PECOS).status_code == 403
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ent.grant_entitlement(user_id="eng_dd4", project_id=PECOS, granted_by="ciso", expires_at=past)
    assert dlt(H("eng_dd4", fn="ENGINEERING"), PECOS).status_code == 403

def test_drawdown_unknown_project_403():
    assert dlt(H("bk", company=ING, svc="BANK"), "proj_nope").status_code == 403
