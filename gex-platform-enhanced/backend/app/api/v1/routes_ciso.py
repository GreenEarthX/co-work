"""
GEX Platform — CISO Workspace API (/api/v1/ciso)
================================================
A client company's CISO sees its own organisation's security posture.

REAL DATA ONLY (JML, 2026-10-25). Until then this module served a seeded demo:
invented user rosters (BP, HamburgOne, NordLB, BremenThree), a randomly
generated access-event feed, invented ISO 27001 / SOC 2 scores, sample barriers,
residency and gateway fallbacks — and it took the company from a request header
defaulting to "bp_global_energy", and an attribute PATCH that saved nothing.
Now every figure comes from PostgreSQL, or says it is not recorded:

  users / projects   auth_users, auth_user_project_roles, projects + project_access
  access log         auth_login_history — real sign-in attempts. Access DECISIONS
                     (ABAC allow/deny) are not recorded anywhere yet.
  compliance         not recorded: no certification store exists
  MFA                not recorded: accounts carry no MFA attribute
  barriers           information_barrier (alembic 070)
  residency          data_residency_policies through core/drpl (no fallback)
  gateways           core/ot_boundary (no fallback)
  policy matrix      the live rule, app.core.abac.GATE_VISIBILITY

The company is the signed-in account's. GEX staff (platform admin) may look at
a client by naming it in the x-ciso-company header (not x-demo-company, which the frontend fetch bridge stamps on every request); anyone else naming another
company is refused. Attribute changes are account administration, which is GEX's
(accounts are vetted, not self-served): they are written to auth_users by GEX
staff only and recorded in the event ledger.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.abac import ActorType, GATE_VISIBILITY

try:
    from app.core.drpl import (
        get_policies as drpl_get_policies, get_residency_audit, upsert_policy as drpl_upsert_policy, init_drpl_db,
    )
    init_drpl_db()
    HAS_DRPL = True
except Exception:
    HAS_DRPL = False

try:
    from app.core.ot_boundary import get_gateways as ot_get_gateways, init_ot_db
    init_ot_db()
    HAS_OT = True
except Exception:
    HAS_OT = False

router = APIRouter()

# ── Vocabulary of the access rules (rules live in code; data does not) ──────
ACTOR_TYPES = [a.value for a in ActorType]
CAPABILITIES = ["OFFTAKE", "PRODUCE", "SELL", "TRADE", "CERTIFY", "FINANCE", "INSURE"]
CLEARANCE_LEVELS = ["STANDARD", "CONFIDENTIAL", "RESTRICTED"]
CREDIT_RATINGS = [
    "NR", "D", "C", "CC", "CCC-", "CCC", "CCC+", "B-", "B", "B+", "BB-", "BB", "BB+",
    "BBB-", "BBB", "BBB+", "A-", "A", "A+", "AA-", "AA", "AA+", "AAA",
    "GEX-1", "GEX-2", "GEX-3", "GEX-4", "GEX-5",
]
ALWAYS_EU = {"AUDIT_LOG", "COMMS_METADATA"}
NOT_RECORDED = "not recorded"


# ── Who is asking, and about which company ──────────────────────────────────

def _caller(request: Request) -> dict:
    payload = getattr(request.state, "user_payload", None) or {}
    if not (payload.get("user_id") or payload.get("sub")):
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def _company(request: Request, header: Optional[str]) -> tuple[str, dict]:
    """The signed-in company; GEX staff may name a client company instead."""
    caller = _caller(request)
    own = caller.get("company_id")
    if header and header != own:
        if not caller.get("is_platform_admin"):
            raise HTTPException(status_code=403, detail={
                "code": "OTHER_COMPANY", "message": "A CISO sees its own company only."})
        return header, caller
    if not own:
        raise HTTPException(status_code=403, detail="Your account belongs to no company.")
    return own, caller


def _rows(sql: str, params: dict, company_id: Optional[str] = None) -> list[dict]:
    """Account tables carry no RLS; the caller's company is checked by _company first.
    Pass company_id to read a tenant-scoped table under its own policy."""
    from app.core.projects_store import PLATFORM_ADMIN, _rows as rows
    return rows(sql, params, company_id or PLATFORM_ADMIN)


def _company_name(company_id: str) -> str:
    r = _rows("SELECT company_name FROM tenants WHERE company_id = :c", {"c": company_id})
    return r[0]["company_name"] if r else company_id


def _users(company_id: str) -> list[dict]:
    """The company's real accounts, their access attributes and project roles."""
    users = _rows(
        "SELECT user_id, email, user_name, business_function, clearance_level, kyc_status, account_state, "
        "nda_signed_with_json, capabilities_json, credit_rating, credit_rating_source, export_licenses_json, "
        "token_ready, transformation_license, aggregation_limit_mt, is_active, created_at "
        "FROM auth_users WHERE company_id = :c ORDER BY user_name", {"c": company_id})
    roles = _rows("SELECT r.user_id, r.project_id, r.actor_type FROM auth_user_project_roles r "
                  "JOIN auth_users u ON u.user_id = r.user_id WHERE u.company_id = :c", {"c": company_id})
    by_user: dict[str, dict[str, list[str]]] = {}
    for r in roles:
        by_user.setdefault(r["user_id"], {}).setdefault(r["project_id"], []).append(r["actor_type"])

    def js(v, default):
        if v is None:
            return default
        return v if isinstance(v, (list, dict)) else json.loads(v)

    return [{
        "user_id": u["user_id"], "name": u["user_name"], "email": u["email"],
        "role": u["business_function"], "clearance_level": u["clearance_level"],
        "kyc_status": u["kyc_status"], "account_state": u["account_state"], "is_active": u["is_active"],
        "actor_type_per_project": by_user.get(u["user_id"], {}),
        "nda_signed_with": js(u["nda_signed_with_json"], []),
        "capabilities": js(u["capabilities_json"], []),
        "credit_rating": u["credit_rating"], "credit_rating_source": u["credit_rating_source"],
        "export_licenses": js(u["export_licenses_json"], []),
        "token_ready": bool(u["token_ready"]), "transformation_license": bool(u["transformation_license"]),
        "aggregation_limit_mt": u["aggregation_limit_mt"],
        "mfa_enabled": None,   # no MFA attribute is recorded on accounts
    } for u in users]


def _projects(company_id: str) -> list[dict]:
    from app.core.project_registry import all_project_profiles
    from app.core.projects_store import list_projects

    visible = {p.project_id for p in all_project_profiles() if company_id in p.stakeholder_company_ids}
    return [{"id": r["project_id"], "name": r["project_name"], "molecule": r.get("molecule"),
             "location": r.get("location")} for r in list_projects() if r["project_id"] in visible]


def _sign_ins(company_id: str, since: Optional[datetime] = None, limit: int = 500) -> list[dict]:
    """Real sign-in attempts by the company's accounts (auth_login_history)."""
    where, params = "u.company_id = :c", {"c": company_id, "lim": limit}
    if since:
        where += " AND h.timestamp >= :since"
        params["since"] = since.isoformat()
    rows = _rows(
        "SELECT h.id, h.user_id, u.user_name, h.event_type, h.ip_address, h.timestamp, h.success "
        f"FROM auth_login_history h JOIN auth_users u ON u.user_id = h.user_id WHERE {where} "
        "ORDER BY h.timestamp DESC LIMIT :lim", params)
    return [{
        "id": f"login_{r['id']}", "timestamp": str(r["timestamp"]), "user_id": r["user_id"],
        "user_name": r["user_name"], "company_id": company_id, "project_id": None, "project_name": None,
        "resource_type": "SIGN_IN", "action": (r["event_type"] or "LOGIN").upper(),
        "decision": "ALLOW" if r["success"] else "DENY", "rule_triggered": None,
        "denial_reason": None if r["success"] else "Sign-in refused",
        "ip_address": r["ip_address"],
    } for r in rows]


# ── Companies a caller may open ─────────────────────────────────────────────

@router.get("/companies")
def list_companies(request: Request):
    """GEX staff: every registered company. Anyone else: their own."""
    caller = _caller(request)
    if caller.get("is_platform_admin"):
        rows = _rows("SELECT company_id, company_name, company_type FROM tenants ORDER BY company_name", {})
    else:
        rows = _rows("SELECT company_id, company_name, company_type FROM tenants WHERE company_id = :c",
                     {"c": caller.get("company_id") or ""})
    return {"companies": rows, "own_company_id": caller.get("company_id"),
            "is_platform_admin": bool(caller.get("is_platform_admin"))}


# ── Overview ────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_ciso_overview(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    """The company's posture from its real accounts and sign-ins. No composite score:
    its weights and its MFA input were never data."""
    from app.core.config import settings

    company_id, _ = _company(request, x_ciso_company)
    users = _users(company_id)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = _sign_ins(company_id, since=since)
    kyc_ok = sum(1 for u in users if u["kyc_status"] == "VERIFIED")
    assigned = sum(1 for u in users if u["actor_type_per_project"])
    pending = [u for u in users if u["account_state"] != "ACTIVE"]

    alerts = []
    if users and kyc_ok < len(users):
        alerts.append({"id": "kyc", "severity": "medium",
                       "message": f"{len(users) - kyc_ok} account(s) without verified KYC"})
    if pending:
        alerts.append({"id": "state", "severity": "medium",
                       "message": f"{len(pending)} account(s) not active: " + ", ".join(u["name"] for u in pending)})
    if users and assigned < len(users):
        alerts.append({"id": "roles", "severity": "low",
                       "message": f"{len(users) - assigned} account(s) with no project role"})
    failed = sum(1 for e in recent if e["decision"] == "DENY")
    if failed:
        alerts.append({"id": "signin", "severity": "high" if failed >= 5 else "medium",
                       "message": f"{failed} refused sign-in(s) in the last 24 hours"})

    return {
        "company_id": company_id,
        "company_name": _company_name(company_id),
        "security_score": None,
        "score_label": NOT_RECORDED,
        "kpis": {
            "total_users": len(users),
            "mfa_enabled_pct": None,
            "kyc_verified": kyc_ok,
            "kyc_pending": len(users) - kyc_ok,
            "abac_assigned": assigned,
            "abac_unassigned": len(users) - assigned,
        },
        "events_24h": {
            "kind": "sign-ins",
            "total": len(recent),
            "allow": len(recent) - failed,
            "deny": failed,
            "deny_rate_pct": round(failed / len(recent) * 100, 1) if recent else 0.0,
        },
        "abac_phase": {"current": settings.ABAC_PHASE},
        "alerts": alerts,
    }


@router.get("/access-log")
def get_access_log(
    request: Request,
    limit: int = 50,
    decision: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    x_ciso_company: Optional[str] = Header(default=None),
):
    """Real sign-in attempts by the company's accounts. Access decisions are not
    recorded yet, so a project filter matches nothing."""
    company_id, _ = _company(request, x_ciso_company)
    events = _sign_ins(company_id, limit=1000)
    if decision:
        events = [e for e in events if e["decision"] == decision.upper()]
    if user_id:
        events = [e for e in events if e["user_id"] == user_id]
    if project_id:
        events = []
    return {"total": len(events), "returned": min(len(events), limit), "events": events[:limit],
            "kind": "sign-ins",
            "note": "Sign-in attempts from the account history. Access decisions are not recorded yet."}


@router.get("/users")
def list_users(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    return {"users": _users(company_id), "projects": _projects(company_id)}


class UserAttributeUpdate(BaseModel):
    clearance_level: Optional[str] = None
    nda_signed_with: Optional[list] = None
    capabilities: Optional[list] = None
    credit_rating: Optional[str] = None
    credit_rating_source: Optional[str] = None
    export_licenses: Optional[list] = None
    token_ready: Optional[bool] = None
    transformation_license: Optional[bool] = None
    aggregation_limit_mt: Optional[float] = None
    # Not editable here: project roles are appointments (reviewer flow, GEX
    # administration) and certifications have no store.
    actor_type_per_project: Optional[dict] = None
    certifications: Optional[list] = None


@router.patch("/users/{user_id}/attributes")
def update_user_attributes(user_id: str, body: UserAttributeUpdate, request: Request,
                           x_ciso_company: Optional[str] = Header(default=None)):
    """Write an account's access attributes — GEX staff only, recorded in the ledger."""
    company_id, caller = _company(request, x_ciso_company)
    if not caller.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail={
            "code": "GEX_ADMINISTERS_ACCOUNTS",
            "message": "Accounts are vetted and administered by GEX; ask GEX staff to change these attributes."})
    if body.actor_type_per_project is not None or body.certifications is not None:
        raise HTTPException(status_code=422, detail={
            "code": "NOT_EDITABLE_HERE",
            "message": "Project roles are changed through appointments; certifications have no store."})
    if body.clearance_level and body.clearance_level not in CLEARANCE_LEVELS:
        raise HTTPException(status_code=422, detail=f"clearance_level must be one of {CLEARANCE_LEVELS}")
    for cap in body.capabilities or []:
        if cap not in CAPABILITIES:
            raise HTTPException(status_code=422, detail=f"Unknown capability: {cap}")
    if body.credit_rating and body.credit_rating not in CREDIT_RATINGS:
        raise HTTPException(status_code=422, detail=f"Unknown credit_rating: {body.credit_rating}")
    if body.credit_rating_source and body.credit_rating_source not in ("GEX", "S&P", "HOUSE_BANK"):
        raise HTTPException(status_code=422, detail="credit_rating_source must be GEX, S&P, or HOUSE_BANK")

    columns = {"clearance_level": body.clearance_level, "credit_rating": body.credit_rating,
               "credit_rating_source": body.credit_rating_source, "token_ready": body.token_ready,
               "transformation_license": body.transformation_license,
               "aggregation_limit_mt": body.aggregation_limit_mt,
               "nda_signed_with_json": None if body.nda_signed_with is None else json.dumps(body.nda_signed_with),
               "capabilities_json": None if body.capabilities is None else json.dumps(body.capabilities),
               "export_licenses_json": None if body.export_licenses is None else json.dumps(body.export_licenses)}
    changes = {k: v for k, v in columns.items() if v is not None}
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to change.")

    from app.core.db_backend import auth_connection
    conn = auth_connection()
    try:
        row = conn.execute("SELECT user_id FROM auth_users WHERE user_id = ? AND company_id = ?",
                           (user_id, company_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found in company {company_id}")
        sets = ", ".join(f"{k} = ?" for k in changes)
        conn.execute(f"UPDATE auth_users SET {sets}, updated_at = ? WHERE user_id = ?",
                     (*changes.values(), datetime.now(timezone.utc).isoformat(), user_id))
        conn.commit()
    finally:
        conn.close()

    from app.core.event_store import append_event
    actor = caller.get("user_id") or caller.get("sub")
    append_event(event_type="account.attributes_changed", aggregate_type="auth_user", aggregate_id=user_id,
                 data={"company_id": company_id, "changes": body.model_dump(exclude_none=True)},
                 user_id=actor)
    user = next(u for u in _users(company_id) if u["user_id"] == user_id)
    return {"status": "updated", "user": user, "changed_by": actor}


# ── Compliance and policy ───────────────────────────────────────────────────

@router.get("/compliance")
def get_compliance(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    """No certification or control-assessment store exists, so nothing is scored."""
    company_id, _ = _company(request, x_ciso_company)
    return {"company_id": company_id, "overall_score": None, "frameworks": [], "recorded": False,
            "note": "Certifications and control assessments are not recorded on the platform yet."}


@router.get("/policy-matrix")
def get_policy_matrix(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    """The live access rule (app.core.abac), not a copy of it."""
    _company(request, x_ciso_company)
    return {
        "gate_visibility": {a.value: gates for a, gates in GATE_VISIBILITY.items()},
        "sensitivity_clearance_map": {
            "PUBLIC": "Any clearance", "SHARED": "STANDARD+",
            "CONFIDENTIAL": "CONFIDENTIAL+", "RESTRICTED": "RESTRICTED only",
        },
        "trade_policy": {
            "R7_capability_map": {"BUY": "OFFTAKE", "SELL": "SELL", "PRODUCE": "PRODUCE", "TRANSFORM": "PRODUCE"},
            "R8_credit_ratings": CREDIT_RATINGS,
            "R9_constraints": ["export_licenses (geofence)", "token_ready", "aggregation_limit_mt",
                               "transformation_license"],
        },
        "actor_types": ACTOR_TYPES,
        "capabilities": CAPABILITIES,
        "clearance_levels": CLEARANCE_LEVELS,
        "certifications": [],
        "credit_ratings": CREDIT_RATINGS,
    }


# ── Information barriers (alembic 070) ──────────────────────────────────────

class BarrierCreate(BaseModel):
    side_a: str
    side_b: str
    barrier_type: str = "HARD"  # HARD | SOFT | CHINESE_WALL
    applies_to_data: list[str] = []
    description: Optional[str] = None


def _barrier_rows(company_id: str, barrier_id: Optional[str] = None) -> list[dict]:
    where, params = "company_id = :c", {"c": company_id}
    if barrier_id:
        where += " AND id::text = :id"
        params["id"] = barrier_id
    rows = _rows("SELECT id, company_id, side_a, side_b, barrier_type, applies_to_data, description, active, "
                 f"created_by, created_at FROM information_barrier WHERE {where} ORDER BY created_at", params,
                 company_id=company_id)
    return [{**r, "id": str(r["id"]), "created_at": str(r["created_at"]),
             "applies_to_data": list(r["applies_to_data"] or [])} for r in rows]


@router.get("/barriers")
def list_barriers(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    barriers = _barrier_rows(company_id)
    return {"company_id": company_id, "total": len(barriers), "barriers": barriers}


@router.get("/barriers/{barrier_id}")
def get_barrier(barrier_id: str, request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    rows = _barrier_rows(company_id, barrier_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Barrier {barrier_id} not found")
    return {**rows[0], "recent_violations": [], "violations_recorded": False}


@router.post("/barriers", status_code=201)
def create_barrier(body: BarrierCreate, request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    company_id, caller = _company(request, x_ciso_company)
    if body.barrier_type not in ("HARD", "SOFT", "CHINESE_WALL"):
        raise HTTPException(status_code=422, detail="barrier_type must be HARD, SOFT or CHINESE_WALL")
    if body.side_a.strip() == body.side_b.strip():
        raise HTTPException(status_code=422, detail="A barrier separates two different sides.")
    from app.core.db_backend import governance_connection, governance_is_postgres, require_postgres
    require_postgres(governance_is_postgres(), "information barriers", "GOVERNANCE_DB_BACKEND")
    conn = governance_connection(company_id="PLATFORM_ADMIN" if caller.get("is_platform_admin") else company_id)
    try:
        conn.execute("INSERT INTO information_barrier (company_id, side_a, side_b, barrier_type, applies_to_data, "
                     "description, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (company_id, body.side_a.strip(), body.side_b.strip(), body.barrier_type,
                      body.applies_to_data, body.description, caller.get("user_id") or caller.get("sub")))
        conn.commit()
    finally:
        conn.close()
    return {"status": "created", "barrier": _barrier_rows(company_id)[-1]}


# ── Data residency (core/drpl; no fallback) ─────────────────────────────────

def _require_drpl() -> None:
    if not HAS_DRPL:
        raise HTTPException(status_code=503, detail="The data-residency store is unavailable.")


@router.get("/residency/policies")
def list_residency_policies(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    _require_drpl()
    policies = drpl_get_policies(company_id)
    return {
        "company_id": company_id, "total": len(policies), "policies": policies,
        "always_eu_categories": sorted(ALWAYS_EU),
        "zones": {"eu-west-1": "EU (GDPR + eIDAS)", "ch-zurich-1": "CH (FADP 2023)",
                  "gb-london-1": "GB (UK GDPR)"},
    }


class ResidencyPolicyUpdate(BaseModel):
    data_category: str
    required_jurisdiction: str  # EU | CH | GB | US
    storage_zone: str
    note: Optional[str] = None


@router.post("/residency/policies")
def upsert_residency_policy(body: ResidencyPolicyUpdate, request: Request,
                            x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    if body.data_category in ALWAYS_EU:
        raise HTTPException(status_code=422, detail=(
            f"{body.data_category} is ALWAYS_EU — jurisdiction cannot be changed per GEX Security Arch §5.3"))
    _require_drpl()
    result = drpl_upsert_policy(company_id=company_id, data_category=body.data_category,
                                required_jurisdiction=body.required_jurisdiction, storage_zone=body.storage_zone)
    if "error" in result:
        raise HTTPException(status_code=500, detail="The residency policy was not saved.")
    return {"status": "updated", "policy": result}


@router.get("/residency/audit")
def get_residency_audit_log(request: Request, x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    _require_drpl()
    return get_residency_audit(company_id)


# ── Trade policy simulation (R7–R9) against a REAL account ──────────────────

class TradePolicySimRequest(BaseModel):
    user_id: str
    action: str           # BUY | SELL | PRODUCE | TRANSFORM
    molecule: str = ""
    destination: str = ""
    required_rating: str = "NR"
    volume_mt: float = 0
    is_tokenized: bool = False


@router.post("/simulate-trade-policy")
def simulate_trade_policy(body: TradePolicySimRequest, request: Request,
                          x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    user = next((u for u in _users(company_id) if u["user_id"] == body.user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {body.user_id} not found in company {company_id}")

    from app.core.abac import (
        Capability, ClearanceLevel, TradeAction, TradeContext, UserAttributes, evaluate_trade_policy,
    )

    attrs = UserAttributes(
        user_id=user["user_id"], company_id=company_id, actor_type_per_project={},
        clearance_level=ClearanceLevel(user["clearance_level"] or "STANDARD"),
        capabilities={Capability(c) for c in user["capabilities"] if c in Capability.__members__},
        credit_rating=user["credit_rating"] or "NR",
        credit_rating_source=user["credit_rating_source"] or "GEX",
        export_licenses=user["export_licenses"], token_ready=user["token_ready"],
        transformation_license=user["transformation_license"],
        aggregation_limit_mt=user["aggregation_limit_mt"],
    )
    ctx = TradeContext(action=TradeAction(body.action), molecule=body.molecule, destination=body.destination,
                       required_rating=body.required_rating, volume_mt=body.volume_mt,
                       is_tokenized=body.is_tokenized)
    decision = evaluate_trade_policy(attrs, ctx)
    return {"user_id": body.user_id, "user_name": user["name"], "decision": decision.decision.value,
            "rules_evaluated": decision.rules_evaluated, "denial_reason": decision.denial_reason,
            "attributes_snapshot": decision.attributes_snapshot}


# ── OT/IT gateways (core/ot_boundary; no fallback) ──────────────────────────

@router.get("/gateways")
def ciso_list_gateways(request: Request, project_id: Optional[str] = None,
                       x_ciso_company: Optional[str] = Header(default=None)):
    company_id, _ = _company(request, x_ciso_company)
    if not HAS_OT:
        raise HTTPException(status_code=503, detail="The OT gateway registry is unavailable.")
    mine = {p["id"] for p in _projects(company_id)}
    gws = [g for g in ot_get_gateways(project_id) if g.get("project_id") in mine]
    return {"total": len(gws), "gateways": gws}
