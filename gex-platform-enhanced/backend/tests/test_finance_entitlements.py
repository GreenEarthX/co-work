"""
Project-scoped finance entitlement tests (Ticket 1a, hardened).

Authorization rule under test:
    allowed = active project-scoped FINANCE_REVIEW grant
              OR (qualified finance role AND relationship to THIS project)
              OR DEV-ONLY global FINANCE_REVIEW

Role ELIGIBILITY alone never grants access. A Bank/DFI/Insurer/Finance user is
authorised only for projects it owns / is associated with / is a mandated
lender-insurer for, or where it holds an explicit grant.

Run from backend/:  python -m pytest tests/test_finance_entitlements.py -q
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("GEX_PLATFORM_DB_PATH", os.path.join(tempfile.mkdtemp(), "ent_test.db"))

from app.core import entitlements as ent                       # noqa: E402
from app.core.project_registry import company_slug             # noqa: E402

ent.init_entitlements_db()

# Real projects from the registry:
PECOS = "proj_etf_pecos1"      # owner ETFuels SA; associated: ING Capital, BNP Paribas CIB, Maersk
BREMEN = "proj_bremen_h2"      # owner HeliosNord GmbH; associated Allianz, Siemens; mandated insurer Allianz

ING = company_slug("ING Capital")
ETFUELS = company_slug("ETFuels SA")
ALLIANZ = company_slug("Allianz")
RANDOM = company_slug("Unrelated Capital Ltd")


def chk(user, *, company=None, project=None, fn=None, svc=None, caps=None):
    return ent.check_finance_access(
        user_id=user, company_id=company, project_id=project,
        business_function=fn, service_type=svc, capabilities=caps or [],
    )[:2]


# ── Role eligibility ≠ project authorization ─────────────────────────────────
def test_bank_allowed_only_on_related_project():
    assert chk("u", company=ING, project=PECOS, svc="BANK") == (True, "role+relationship")   # ING is associated
    assert chk("u", company=ING, project=BREMEN, svc="BANK") == (False, "none")              # ING not on Bremen
    assert chk("u", company=RANDOM, project=PECOS, svc="BANK") == (False, "none")            # unrelated bank


def test_owner_finance_allowed_on_own_project_only():
    assert chk("u", company=ETFUELS, project=PECOS, fn="FINANCE_TREASURY") == (True, "role+relationship")
    assert chk("u", company=ETFUELS, project=BREMEN, fn="FINANCE_TREASURY") == (False, "none")


def test_mandated_insurer_allowed_on_mandated_project_only():
    assert chk("u", company=ALLIANZ, project=BREMEN, svc="INSURER") == (True, "role+relationship")
    assert chk("u", company=ALLIANZ, project=PECOS, svc="INSURER") == (False, "none")


def test_non_finance_role_denied_even_with_relationship():
    # Owner company but ENGINEERING function → not a finance role → needs explicit grant.
    assert chk("u", company=ETFUELS, project=PECOS, fn="ENGINEERING") == (False, "none")


def test_unknown_project_denied_for_qualified_role():
    assert chk("u", company=ING, project="proj_does_not_exist", svc="BANK") == (False, "none")


def test_missing_project_denied():
    assert chk("u", company=ING, project=None, svc="BANK") == (False, "none")


# ── Project-scoped grant (works for anyone, overrides lack of relationship) ───
def test_grant_allows_only_that_project():
    ent.grant_entitlement(user_id="eng1", project_id=PECOS, granted_by="ciso", reason="finance review")
    assert chk("eng1", company=RANDOM, project=PECOS, fn="ENGINEERING") == (True, "project_entitlement")
    assert chk("eng1", company=RANDOM, project=BREMEN, fn="ENGINEERING") == (False, "none")


def test_revoked_grant_fails():
    rec = ent.grant_entitlement(user_id="eng2", project_id=PECOS, granted_by="ciso")
    assert chk("eng2", company=RANDOM, project=PECOS, fn="ENGINEERING") == (True, "project_entitlement")
    ent.revoke_entitlement(rec["entitlement_id"], revoked_by="ciso")
    assert chk("eng2", company=RANDOM, project=PECOS, fn="ENGINEERING") == (False, "none")


def test_expired_grant_fails():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ent.grant_entitlement(user_id="eng3", project_id=PECOS, granted_by="ciso", expires_at=past)
    assert chk("eng3", company=RANDOM, project=PECOS, fn="ENGINEERING") == (False, "none")


def test_future_expiry_active():
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    ent.grant_entitlement(user_id="eng4", project_id=PECOS, granted_by="ciso", expires_at=future)
    assert chk("eng4", company=RANDOM, project=PECOS, fn="ENGINEERING") == (True, "project_entitlement")


# ── Dev-only global fallback ─────────────────────────────────────────────────
def test_global_finance_review_off_by_default():
    os.environ.pop("GEX_DEV_GLOBAL_FINANCE_REVIEW", None)
    os.environ["GEX_ENV"] = "development"
    assert chk("eng5", company=RANDOM, project=PECOS, fn="ENGINEERING", caps=["FINANCE_REVIEW"]) == (False, "none")


def test_global_finance_review_on_in_dev():
    os.environ["GEX_ENV"] = "development"
    os.environ["GEX_DEV_GLOBAL_FINANCE_REVIEW"] = "1"
    assert chk("eng6", company=RANDOM, project=BREMEN, fn="ENGINEERING", caps=["FINANCE_REVIEW"]) == (True, "dev_global")
    os.environ.pop("GEX_DEV_GLOBAL_FINANCE_REVIEW", None)


def test_global_finance_review_blocked_in_production():
    os.environ["GEX_ENV"] = "production"
    os.environ["GEX_DEV_GLOBAL_FINANCE_REVIEW"] = "1"
    assert chk("eng7", company=RANDOM, project=BREMEN, fn="ENGINEERING", caps=["FINANCE_REVIEW"]) == (False, "none")
    os.environ.pop("GEX_DEV_GLOBAL_FINANCE_REVIEW", None)
    os.environ["GEX_ENV"] = "development"


def test_status_lifecycle():
    rec = ent.grant_entitlement(user_id="eng8", project_id=PECOS, granted_by="ciso")
    assert ent.get_entitlement(rec["entitlement_id"])["status"] == "active"
    ent.revoke_entitlement(rec["entitlement_id"], revoked_by="ciso")
    assert ent.get_entitlement(rec["entitlement_id"])["status"] == "revoked"
