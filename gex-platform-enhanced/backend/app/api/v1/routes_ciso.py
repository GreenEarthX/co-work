"""
GEX Platform — CISO Workspace API
===================================
Endpoints for client-company Chief Information Security Officers.
Each client's CISO can:
  • View their organisation's users and ABAC attributes
  • Update user clearance levels, actor-type assignments and NDA partners
  • Monitor real-time ABAC access events (ALLOW / DENY feed)
  • View compliance posture (ISO 27001, SOC 2, GDPR, ABAC phases)
  • Run policy simulations to preview access decisions

Demo mode: company is resolved from the `x-demo-company` request header
(default: "bp_global_energy").  In production this comes from the JWT claim.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

# Security extension imports (Domain 3, 4, 5)
try:
    from app.core.drpl import (
        check_residency, get_policies as drpl_get_policies,
        upsert_policy as drpl_upsert_policy, get_residency_audit, init_drpl_db,
        DataCategory,
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

# ─────────────────────────────────────────────────────────────────────────────
# Reference data
# ─────────────────────────────────────────────────────────────────────────────

ACTOR_TYPES = [
    "PRODUCER", "OFFTAKER", "COMMERCIAL_BANKER", "DFI", "INSURER",
    "REGULATOR", "GOV_AGENCY", "CERTIFIER", "EPC_CONTRACTOR",
    "LOGISTICS_OPERATOR", "TECHNOLOGY_PROVIDER", "EXECUTIVE",
]

CLEARANCE_LEVELS = ["STANDARD", "CONFIDENTIAL", "RESTRICTED"]

CERTIFICATIONS = ["ISO_27001", "SOC2_TYPE_II", "GDPR_DPO", "ISO_14064", "RED_III"]

GEX_PROJECTS = [
    {"id": "proj_bremen_h2",           "name": "Bremen Green Hydrogen Plant",   "molecule": "H2",        "location": "Bremen, DE"},
    {"id": "proj_rotterdam_nh3",        "name": "Rotterdam Green Ammonia",       "molecule": "NH3",       "location": "Rotterdam, NL"},
    {"id": "proj_sansebastian_emethanol","name": "Project Helios e-Methanol",    "molecule": "e-Methanol","location": "San Sebastián, ES"},
    {"id": "proj_wales_saf",            "name": "Celtic Green SAF Complex",      "molecule": "SAF",       "location": "Neath Port Talbot, GB"},
    {"id": "proj_lehavre_eng",          "name": "Le Havre e-Gas Hub",            "molecule": "e-NG",      "location": "Le Havre, FR"},
]

# Simulated users for the demo company
_BP_USERS = [
    {
        "user_id": "usr_bp_01",
        "name": "Sophie Hartmann",
        "email": "s.hartmann@bp-energy.com",
        "role": "Head of Trading — Green Fuels",
        "clearance_level": "CONFIDENTIAL",
        "actor_type_per_project": {
            "proj_bremen_h2": "OFFTAKER",
            "proj_rotterdam_nh3": "OFFTAKER",
            "proj_lehavre_eng": "OFFTAKER",
        },
        "nda_signed_with": ["GreenEarthX_Admin", "proj_bremen_operator"],
        "certifications": ["ISO_27001"],
        "last_active": "2026-03-16T08:14:22Z",
        "kyc_status": "VERIFIED",
        "mfa_enabled": True,
    },
    {
        "user_id": "usr_bp_02",
        "name": "Liam Donovan",
        "email": "l.donovan@bp-energy.com",
        "role": "Project Finance Manager",
        "clearance_level": "RESTRICTED",
        "actor_type_per_project": {
            "proj_wales_saf": "COMMERCIAL_BANKER",
            "proj_sansebastian_emethanol": "DFI",
        },
        "nda_signed_with": ["GreenEarthX_Admin", "proj_wales_operator", "proj_helios_operator"],
        "certifications": ["ISO_27001", "SOC2_TYPE_II"],
        "last_active": "2026-03-15T17:45:01Z",
        "kyc_status": "VERIFIED",
        "mfa_enabled": True,
    },
    {
        "user_id": "usr_bp_03",
        "name": "Priya Nair",
        "email": "p.nair@bp-energy.com",
        "role": "Regulatory Affairs Specialist",
        "clearance_level": "STANDARD",
        "actor_type_per_project": {
            "proj_bremen_h2": "REGULATOR",
            "proj_sansebastian_emethanol": "CERTIFIER",
        },
        "nda_signed_with": ["GreenEarthX_Admin"],
        "certifications": ["ISO_14064", "RED_III"],
        "last_active": "2026-03-16T09:02:55Z",
        "kyc_status": "VERIFIED",
        "mfa_enabled": False,
    },
    {
        "user_id": "usr_bp_04",
        "name": "Marcus Johansson",
        "email": "m.johansson@bp-energy.com",
        "role": "SAF Production Lead",
        "clearance_level": "CONFIDENTIAL",
        "actor_type_per_project": {
            "proj_wales_saf": "PRODUCER",
            "proj_lehavre_eng": "PRODUCER",
        },
        "nda_signed_with": ["GreenEarthX_Admin", "proj_wales_operator"],
        "certifications": ["ISO_14064"],
        "last_active": "2026-03-14T11:30:00Z",
        "kyc_status": "PENDING",
        "mfa_enabled": True,
    },
    {
        "user_id": "usr_bp_05",
        "name": "Aisha Al-Farsi",
        "email": "a.alfarsi@bp-energy.com",
        "role": "IT Security Analyst",
        "clearance_level": "RESTRICTED",
        "actor_type_per_project": {},
        "nda_signed_with": ["GreenEarthX_Admin"],
        "certifications": ["ISO_27001", "SOC2_TYPE_II", "GDPR_DPO"],
        "last_active": "2026-03-16T10:00:00Z",
        "kyc_status": "VERIFIED",
        "mfa_enabled": True,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _company_from_header(x_demo_company: Optional[str]) -> str:
    return x_demo_company or "bp_global_energy"


def _gen_access_events(company_id: str, count: int = 50):
    """Generate deterministic-looking ABAC event log for the given company."""
    users = [u for u in _BP_USERS]
    resource_types = ["EVIDENCE", "FINANCIAL_MODEL", "CONTRACT", "PLANT_TECHNICAL", "MARKETPLACE"]
    actions = ["READ", "WRITE", "EXPORT", "VERIFY", "SHARE"]
    rules = ["R1", "R3", "R4", "R5", "R6"]
    denial_reasons = [
        "User is not a stakeholder on this project",
        "Evidence sensitivity=CONFIDENTIAL, company not in shared_with",
        "Not a mandated lender/insurer or data owner",
        "Only assigned certifiers can verify evidence",
        "Clearance STANDARD insufficient for sensitivity RESTRICTED",
    ]

    events = []
    base = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)

    random.seed(42)
    for i in range(count):
        user = users[i % len(users)]
        project = GEX_PROJECTS[i % len(GEX_PROJECTS)]
        action = actions[i % len(actions)]
        is_deny = (i % 5 == 3)  # ~20 % deny rate
        rule = rules[i % len(rules)] if is_deny else None
        events.append({
            "id": f"evt_{1000 + i}",
            "timestamp": (base - timedelta(minutes=i * 3)).isoformat(),
            "user_id": user["user_id"],
            "user_name": user["name"],
            "company_id": company_id,
            "project_id": project["id"],
            "project_name": project["name"],
            "resource_type": resource_types[i % len(resource_types)],
            "action": action,
            "decision": "DENY" if is_deny else "ALLOW",
            "rule_triggered": rule,
            "denial_reason": denial_reasons[rules.index(rule)] if is_deny else None,
        })
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_ciso_overview(x_demo_company: Optional[str] = Header(default=None)):
    """
    Security posture KPIs for the client company's CISO dashboard.
    """
    company_id = _company_from_header(x_demo_company)
    events = _gen_access_events(company_id, 50)
    deny_events = [e for e in events if e["decision"] == "DENY"]
    last_24h = events[:28]  # ~last 24 h (every 3 min, 28 × 3 min ≈ 84 min window)

    # MFA adoption
    mfa_on  = sum(1 for u in _BP_USERS if u["mfa_enabled"])
    mfa_pct = round(mfa_on / len(_BP_USERS) * 100)

    # KYC
    kyc_ok  = sum(1 for u in _BP_USERS if u["kyc_status"] == "VERIFIED")

    # ABAC coverage: users with at least one actor_type assignment
    abac_assigned = sum(1 for u in _BP_USERS if u["actor_type_per_project"])

    # Compute a simple security score
    mfa_score       = mfa_pct * 0.30
    kyc_score       = (kyc_ok / len(_BP_USERS)) * 100 * 0.25
    abac_score      = (abac_assigned / len(_BP_USERS)) * 100 * 0.25
    deny_rate       = len(deny_events) / max(len(events), 1)
    vigilance_score = min(deny_rate * 500, 20)  # up to 20 pts for having denials (means policy is active)
    total_score     = round(mfa_score + kyc_score + abac_score + vigilance_score)

    return {
        "company_id": company_id,
        "company_name": "BP Global Energy",
        "security_score": total_score,
        "score_label": "Good" if total_score >= 75 else ("Fair" if total_score >= 50 else "At Risk"),
        "kpis": {
            "total_users": len(_BP_USERS),
            "mfa_enabled_pct": mfa_pct,
            "kyc_verified": kyc_ok,
            "kyc_pending": len(_BP_USERS) - kyc_ok,
            "abac_assigned": abac_assigned,
            "abac_unassigned": len(_BP_USERS) - abac_assigned,
        },
        "events_24h": {
            "total": len(last_24h),
            "allow": len([e for e in last_24h if e["decision"] == "ALLOW"]),
            "deny":  len([e for e in last_24h if e["decision"] == "DENY"]),
            "deny_rate_pct": round(len([e for e in last_24h if e["decision"] == "DENY"]) / max(len(last_24h), 1) * 100, 1),
        },
        "abac_phase": {
            "current": 2,
            "phases": [
                {"phase": 1, "label": "R1–R3: Stakeholder + Evidence", "status": "active"},
                {"phase": 2, "label": "R4–R6: Financial + Export + Write", "status": "active"},
                {"phase": 3, "label": "Context: State, jurisdiction, time-windows", "status": "planned"},
            ],
        },
        "alerts": [
            {
                "id": "alert_001",
                "severity": "high",
                "message": f"{mfa_pct}% MFA adoption — {len(_BP_USERS) - mfa_on} user(s) without MFA",
                "ts": "2026-03-16T06:00:00Z",
            },
            {
                "id": "alert_002",
                "severity": "medium",
                "message": "1 user with KYC status PENDING (Marcus Johansson)",
                "ts": "2026-03-15T14:00:00Z",
            },
            {
                "id": "alert_003",
                "severity": "low",
                "message": "ABAC Phase 3 (context attributes) not yet enabled",
                "ts": "2026-03-14T09:00:00Z",
            },
        ],
    }


@router.get("/access-log")
def get_access_log(
    limit: int = 50,
    decision: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Paginated ABAC access event log for the client company.
    Filterable by decision (ALLOW / DENY), user_id, project_id.
    """
    company_id = _company_from_header(x_demo_company)
    events = _gen_access_events(company_id, 120)

    if decision:
        events = [e for e in events if e["decision"] == decision.upper()]
    if user_id:
        events = [e for e in events if e["user_id"] == user_id]
    if project_id:
        events = [e for e in events if e["project_id"] == project_id]

    total = len(events)
    events = events[:limit]

    return {
        "total": total,
        "returned": len(events),
        "events": events,
    }


@router.get("/users")
def list_users(x_demo_company: Optional[str] = Header(default=None)):
    """List all users of the client company with their ABAC attributes."""
    _company_from_header(x_demo_company)
    return {
        "users": _BP_USERS,
        "projects": GEX_PROJECTS,
    }


class UserAttributeUpdate(BaseModel):
    clearance_level: Optional[str] = None
    actor_type_per_project: Optional[dict] = None
    nda_signed_with: Optional[list] = None
    certifications: Optional[list] = None


@router.patch("/users/{user_id}/attributes")
def update_user_attributes(
    user_id: str,
    body: UserAttributeUpdate,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Update ABAC attributes for a specific user.
    Only the client's CISO (same company) may call this endpoint.
    """
    _company_from_header(x_demo_company)

    user = next((u for u in _BP_USERS if u["user_id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # Validate values
    if body.clearance_level and body.clearance_level not in CLEARANCE_LEVELS:
        raise HTTPException(status_code=422, detail=f"clearance_level must be one of {CLEARANCE_LEVELS}")
    if body.actor_type_per_project:
        for pid, atype in body.actor_type_per_project.items():
            if atype not in ACTOR_TYPES:
                raise HTTPException(status_code=422, detail=f"Unknown actor_type: {atype}")

    # Apply (in-memory only for demo)
    updated = dict(user)
    if body.clearance_level is not None:
        updated["clearance_level"] = body.clearance_level
    if body.actor_type_per_project is not None:
        updated["actor_type_per_project"] = body.actor_type_per_project
    if body.nda_signed_with is not None:
        updated["nda_signed_with"] = body.nda_signed_with
    if body.certifications is not None:
        updated["certifications"] = body.certifications

    return {
        "status": "updated",
        "user": updated,
        "audit_entry": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changed_by": "ciso_session",
            "changes": body.model_dump(exclude_none=True),
        },
    }


@router.get("/compliance")
def get_compliance(x_demo_company: Optional[str] = Header(default=None)):
    """
    Compliance posture across ISO 27001, SOC 2 Type II, GDPR and ABAC phases.
    """
    _company_from_header(x_demo_company)

    return {
        "overall_score": 74,
        "frameworks": [
            {
                "id": "iso_27001",
                "name": "ISO 27001:2022",
                "description": "Information Security Management System",
                "score": 81,
                "status": "certified",
                "cert_expiry": "2027-06-30",
                "domains": [
                    {"domain": "A.5 — Policies",              "score": 100, "controls": 2,  "passed": 2},
                    {"domain": "A.6 — Organisation",          "score": 90,  "controls": 7,  "passed": 6},
                    {"domain": "A.7 — HR Security",           "score": 85,  "controls": 6,  "passed": 5},
                    {"domain": "A.8 — Asset Management",      "score": 78,  "controls": 10, "passed": 8},
                    {"domain": "A.9 — Access Control",        "score": 88,  "controls": 14, "passed": 12},
                    {"domain": "A.10 — Cryptography",         "score": 100, "controls": 2,  "passed": 2},
                    {"domain": "A.12 — Operations Security",  "score": 75,  "controls": 14, "passed": 11},
                    {"domain": "A.13 — Communications",       "score": 80,  "controls": 7,  "passed": 6},
                    {"domain": "A.14 — System Dev",           "score": 70,  "controls": 13, "passed": 9},
                    {"domain": "A.18 — Compliance",           "score": 65,  "controls": 8,  "passed": 5},
                ],
            },
            {
                "id": "soc2",
                "name": "SOC 2 Type II",
                "description": "Trust Services Criteria (AICPA)",
                "score": 72,
                "status": "in_progress",
                "cert_expiry": None,
                "domains": [
                    {"domain": "CC1 — Control Environment",     "score": 90, "controls": 5,  "passed": 5},
                    {"domain": "CC2 — Communication & Info",    "score": 80, "controls": 5,  "passed": 4},
                    {"domain": "CC3 — Risk Assessment",         "score": 75, "controls": 4,  "passed": 3},
                    {"domain": "CC6 — Logical Access",          "score": 65, "controls": 8,  "passed": 5},
                    {"domain": "CC7 — System Operations",       "score": 60, "controls": 5,  "passed": 3},
                    {"domain": "CC9 — Risk Mitigation",         "score": 70, "controls": 3,  "passed": 2},
                ],
            },
            {
                "id": "gdpr",
                "name": "GDPR / EU Data Protection",
                "description": "Regulation (EU) 2016/679",
                "score": 68,
                "status": "partial",
                "cert_expiry": None,
                "domains": [
                    {"domain": "Art. 5 — Data Principles",     "score": 90, "controls": 6,  "passed": 5},
                    {"domain": "Art. 12-14 — Transparency",    "score": 80, "controls": 3,  "passed": 2},
                    {"domain": "Art. 15-22 — Data Subject Rts","score": 70, "controls": 8,  "passed": 6},
                    {"domain": "Art. 25 — Privacy by Design",  "score": 60, "controls": 2,  "passed": 1},
                    {"domain": "Art. 32 — Security Measures",  "score": 65, "controls": 4,  "passed": 3},
                    {"domain": "Art. 33-34 — Breach Reporting","score": 50, "controls": 2,  "passed": 1},
                    {"domain": "Art. 37 — DPO Appointment",    "score": 50, "controls": 1,  "passed": 0},
                ],
            },
            {
                "id": "abac",
                "name": "GEX ABAC Policy",
                "description": "Attribute-Based Access Control implementation",
                "score": 67,
                "status": "partial",
                "cert_expiry": None,
                "domains": [
                    {"domain": "R1 — Stakeholder Gate",          "score": 100, "controls": 1, "passed": 1},
                    {"domain": "R2 — Gate Visibility Matrix",    "score": 100, "controls": 1, "passed": 1},
                    {"domain": "R3 — Evidence Sensitivity",      "score": 100, "controls": 1, "passed": 1},
                    {"domain": "R4 — Financial Model Protection","score": 100, "controls": 1, "passed": 1},
                    {"domain": "R5 — Write Permissions",         "score": 100, "controls": 1, "passed": 1},
                    {"domain": "R6 — Export & Share Control",    "score": 100, "controls": 1, "passed": 1},
                    {"domain": "Phase 3 — Context Attributes",   "score": 0,   "controls": 3, "passed": 0},
                    {"domain": "MFA Enforcement",                "score": 60,  "controls": 5, "passed": 3},
                    {"domain": "Audit Trail Completeness",       "score": 55,  "controls": 4, "passed": 2},
                ],
            },
        ],
    }


@router.get("/policy-matrix")
def get_policy_matrix(x_demo_company: Optional[str] = Header(default=None)):
    """
    Returns the ABAC GATE_VISIBILITY matrix — which gates each actor type can access.
    Used by the CISO to understand what each role can see before assigning it.
    """
    _company_from_header(x_demo_company)

    return {
        "gate_visibility": {
            "PRODUCER":           ["G0_SITE_RIGHTS", "G1_GRID_WATER", "G3_FEEDSTOCK_LOGISTICS", "G5_EPC", "G9_PERMITS", "G11_COD"],
            "OFFTAKER":           ["G4_OFFTAKE"],
            "COMMERCIAL_BANKER":  ["G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE", "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE"],
            "DFI":                ["G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE", "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE"],
            "INSURER":            ["G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE"],
            "REGULATOR":          ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
            "GOV_AGENCY":         ["G0_SITE_RIGHTS", "G1_GRID_WATER", "G2_CERTIFICATION", "G3_FEEDSTOCK_LOGISTICS", "G4_OFFTAKE", "G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE", "G8_MODEL_AUDIT", "G9_PERMITS", "G10_FINANCIAL_CLOSE", "G11_COD"],
            "CERTIFIER":          ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
            "EPC_CONTRACTOR":     ["G5_EPC", "G11_COD"],
            "LOGISTICS_OPERATOR": ["G3_FEEDSTOCK_LOGISTICS"],
            "TECHNOLOGY_PROVIDER":["G5_EPC", "G11_COD"],
            "EXECUTIVE":          ["G0_SITE_RIGHTS", "G1_GRID_WATER", "G2_CERTIFICATION", "G3_FEEDSTOCK_LOGISTICS", "G4_OFFTAKE", "G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE", "G8_MODEL_AUDIT", "G9_PERMITS", "G10_FINANCIAL_CLOSE", "G11_COD"],
        },
        "sensitivity_clearance_map": {
            "PUBLIC":       "Any clearance",
            "SHARED":       "STANDARD+",
            "CONFIDENTIAL": "CONFIDENTIAL+",
            "RESTRICTED":   "RESTRICTED only",
        },
        "actor_types": ACTOR_TYPES,
        "clearance_levels": CLEARANCE_LEVELS,
        "certifications": CERTIFICATIONS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Domain 3: Information Barriers
# ─────────────────────────────────────────────────────────────────────────────

# Seeded demo barriers for bp_global_energy
_DEMO_BARRIERS = [
    {
        "id": "IB-01",
        "company_id": "bp_global_energy",
        "side_a": "TRADING",
        "side_b": "ORIGINATION",
        "barrier_type": "HARD",
        "applies_to_data": ["FINANCIAL_MODEL", "CONTRACT"],
        "description": "Trading desk is firewalled from project origination to prevent front-running",
        "active": True,
        "created_at": "2026-01-15T00:00:00Z",
    },
    {
        "id": "IB-02",
        "company_id": "bp_global_energy",
        "side_a": "TREASURY",
        "side_b": "RISK",
        "barrier_type": "SOFT",
        "applies_to_data": ["FINANCIAL_MODEL"],
        "description": "Treasury and Risk share financial models but access is logged (Chinese Wall variant)",
        "active": True,
        "created_at": "2026-01-15T00:00:00Z",
    },
    {
        "id": "IB-03",
        "company_id": "bp_global_energy",
        "side_a": "LEGAL",
        "side_b": "TRADING",
        "barrier_type": "HARD",
        "applies_to_data": ["CONTRACT", "CERTIFICATION"],
        "description": "Legal dept. may not share draft contracts with trading prior to execution",
        "active": True,
        "created_at": "2026-02-01T00:00:00Z",
    },
]


@router.get("/barriers")
def list_barriers(x_demo_company: Optional[str] = Header(default=None)):
    """
    List information barriers configured for the client company (Domain 3).
    Returns barrier definitions, types (HARD/SOFT/CHINESE_WALL), and data categories covered.
    """
    company_id = _company_from_header(x_demo_company)
    barriers = [b for b in _DEMO_BARRIERS if b["company_id"] == company_id]
    return {"company_id": company_id, "total": len(barriers), "barriers": barriers}


@router.get("/barriers/{barrier_id}")
def get_barrier(
    barrier_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Get a single information barrier by ID."""
    company_id = _company_from_header(x_demo_company)
    barrier = next((b for b in _DEMO_BARRIERS if b["id"] == barrier_id and b["company_id"] == company_id), None)
    if not barrier:
        raise HTTPException(status_code=404, detail=f"Barrier {barrier_id} not found")
    # Simulate a recent access log for this barrier
    barrier_with_log = dict(barrier)
    barrier_with_log["recent_violations"] = [
        {
            "id": f"{barrier_id}-viol-001",
            "user_id": "usr_bp_01",
            "user_name": "Sophie Hartmann",
            "attempted_at": "2026-03-15T14:22:00Z",
            "outcome": "BLOCKED",
            "resource_id": "contract_wales_saf_001",
        }
    ] if barrier_id == "IB-01" else []
    return barrier_with_log


class BarrierCreate(BaseModel):
    side_a: str
    side_b: str
    barrier_type: str = "HARD"  # HARD | SOFT | CHINESE_WALL
    applies_to_data: list[str] = []
    description: Optional[str] = None


@router.post("/barriers")
def create_barrier(
    body: BarrierCreate,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Create a new information barrier (CISO only). Demo: returns created object."""
    company_id = _company_from_header(x_demo_company)
    new_id = f"IB-{len(_DEMO_BARRIERS) + 1:02d}"
    new_barrier = {
        "id": new_id,
        "company_id": company_id,
        "side_a": body.side_a,
        "side_b": body.side_b,
        "barrier_type": body.barrier_type,
        "applies_to_data": body.applies_to_data,
        "description": body.description,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"status": "created", "barrier": new_barrier}


# ─────────────────────────────────────────────────────────────────────────────
# Domain 5: Data Residency Policies
# ─────────────────────────────────────────────────────────────────────────────

_DEMO_RESIDENCY_POLICIES = [
    {
        "id": "drp-001", "company_id": "bp_global_energy",
        "data_category": "PERSONAL", "required_jurisdiction": "EU",
        "storage_zone": "eu-west-1", "note": "GDPR Art. 44 — no transfer outside EU without adequacy", "active": True,
    },
    {
        "id": "drp-002", "company_id": "bp_global_energy",
        "data_category": "CONTRACT", "required_jurisdiction": "EU",
        "storage_zone": "eu-west-1", "note": "Contract data within EU to meet eIDAS requirements", "active": True,
    },
    {
        "id": "drp-003", "company_id": "bp_global_energy",
        "data_category": "FINANCIAL_MODEL", "required_jurisdiction": "EU",
        "storage_zone": "eu-west-1", "note": "Model sensitivity RESTRICTED — EU jurisdiction only", "active": True,
    },
    {
        "id": "drp-004", "company_id": "bp_global_energy",
        "data_category": "AUDIT_LOG", "required_jurisdiction": "EU",
        "storage_zone": "eu-west-1", "note": "Audit logs ALWAYS_EU per GEX Security Arch §5.3", "active": True,
    },
    {
        "id": "drp-005", "company_id": "bp_global_energy",
        "data_category": "COMMS_METADATA", "required_jurisdiction": "EU",
        "storage_zone": "eu-west-1", "note": "Matrix room metadata ALWAYS_EU — ISO 27001 A.12.4", "active": True,
    },
    {
        "id": "drp-006", "company_id": "bp_global_energy",
        "data_category": "PLANT_DATA", "required_jurisdiction": "EU",
        "storage_zone": "eu-west-1", "note": "OT telemetry stored in-region per NIS2 directive", "active": True,
    },
]


@router.get("/residency/policies")
def list_residency_policies(x_demo_company: Optional[str] = Header(default=None)):
    """
    List DRPL (Data Residency Policy Layer) rules for the client company.
    Returns per data-category jurisdiction constraints.
    """
    company_id = _company_from_header(x_demo_company)
    if HAS_DRPL:
        policies = drpl_get_policies(company_id)
    else:
        policies = [p for p in _DEMO_RESIDENCY_POLICIES if p["company_id"] == company_id]
    return {
        "company_id": company_id,
        "total": len(policies),
        "policies": policies,
        "always_eu_categories": ["AUDIT_LOG", "COMMS_METADATA"],
        "zones": {
            "eu-west-1":   "EU (GDPR + eIDAS)",
            "ch-zurich-1": "CH (FADP 2023)",
            "gb-london-1": "GB (UK GDPR)",
        },
    }


class ResidencyPolicyUpdate(BaseModel):
    data_category: str
    required_jurisdiction: str  # EU | CH | GB | US
    storage_zone: str
    note: Optional[str] = None


@router.post("/residency/policies")
def upsert_residency_policy(
    body: ResidencyPolicyUpdate,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    Create or update a DRPL policy for a data category.
    ALWAYS_EU categories (AUDIT_LOG, COMMS_METADATA) cannot be changed.
    """
    company_id = _company_from_header(x_demo_company)
    always_eu = {"AUDIT_LOG", "COMMS_METADATA"}
    if body.data_category in always_eu:
        raise HTTPException(
            status_code=422,
            detail=f"{body.data_category} is ALWAYS_EU — jurisdiction cannot be changed per GEX Security Arch §5.3"
        )
    if HAS_DRPL:
        result = drpl_upsert_policy(
            company_id=company_id,
            data_category=body.data_category,
            required_jurisdiction=body.required_jurisdiction,
            storage_zone=body.storage_zone,
        )
        return {"status": "updated", "policy": result}
    # Demo fallback
    return {
        "status": "updated",
        "policy": {
            "company_id": company_id,
            "data_category": body.data_category,
            "required_jurisdiction": body.required_jurisdiction,
            "storage_zone": body.storage_zone,
            "note": body.note,
            "active": True,
        }
    }


@router.get("/residency/audit")
def get_residency_audit_log(x_demo_company: Optional[str] = Header(default=None)):
    """Residency check audit log for the client company (last 100 checks)."""
    company_id = _company_from_header(x_demo_company)
    if HAS_DRPL:
        return get_residency_audit(company_id)
    # Demo data
    return {
        "company_id": company_id,
        "recent_checks": [
            {
                "id": "rc-001", "data_category": "PERSONAL",
                "requested_zone": "eu-west-1", "outcome": "ALLOWED",
                "required_jurisdiction": "EU", "checked_at": "2026-03-16T09:14:00Z",
            },
            {
                "id": "rc-002", "data_category": "FINANCIAL_MODEL",
                "requested_zone": "us-east-1", "outcome": "BLOCKED",
                "required_jurisdiction": "EU",
                "reason": "US zone does not meet EU jurisdiction requirement",
                "checked_at": "2026-03-16T08:55:00Z",
            },
            {
                "id": "rc-003", "data_category": "PLANT_DATA",
                "requested_zone": "eu-west-1", "outcome": "ALLOWED",
                "required_jurisdiction": "EU", "checked_at": "2026-03-16T08:30:00Z",
            },
        ],
        "blocked_count_24h": 1,
        "allowed_count_24h": 12,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Domain 4: OT/IT Gateway Status (CISO monitoring view)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/gateways")
def ciso_list_gateways(
    project_id: Optional[str] = None,
    x_demo_company: Optional[str] = Header(default=None),
):
    """
    CISO view of all registered OT gateways with health and last-seen status.
    Proxies to ot_boundary.get_gateways() when available, otherwise returns demo data.
    """
    _company_from_header(x_demo_company)
    if HAS_OT:
        gws = ot_get_gateways(project_id)
        return {"total": len(gws), "gateways": gws}
    # Demo fallback
    gateways = [
        {
            "id": "gw-breizh-001",
            "name": "Breizh SAF Plant — Primary Gateway",
            "project_id": "proj_breizh_saf",
            "location": "Brest, Bretagne, FR",
            "allowed_ips": ["10.12.0.1"],
            "allowed_data_types": ["PRODUCTION_VOLUME", "ELECTROLYSER_EFFICIENCY", "GHG_MEASUREMENT", "PLANT_STATUS"],
            "cert_fingerprint": None,
            "active": True,
            "last_seen_at": "2026-03-17T08:01:00Z",
            "registered_at": "2026-01-10T00:00:00Z",
            "status": "ONLINE",
        },
        {
            "id": "gw-wales-001",
            "name": "Celtic SAF Complex — Gateway A",
            "project_id": "proj_wales_saf",
            "location": "Neath Port Talbot, GB",
            "allowed_ips": ["10.14.0.5"],
            "allowed_data_types": ["PRODUCTION_VOLUME", "POWER_CONSUMPTION", "PLANT_STATUS", "ALARM_EVENT"],
            "cert_fingerprint": None,
            "active": True,
            "last_seen_at": "2026-03-16T22:15:00Z",
            "registered_at": "2026-02-01T00:00:00Z",
            "status": "ONLINE",
        },
        {
            "id": "gw-rotterdam-001",
            "name": "Rotterdam NH3 — SCADA Gateway",
            "project_id": "proj_rotterdam_nh3",
            "location": "Rotterdam, NL",
            "allowed_ips": [],
            "allowed_data_types": ["PRODUCTION_VOLUME", "QUALITY_CERTIFICATE", "METERED_DELIVERY"],
            "cert_fingerprint": None,
            "active": False,
            "last_seen_at": "2026-03-10T06:00:00Z",
            "registered_at": "2025-11-20T00:00:00Z",
            "status": "OFFLINE",
        },
    ]
    if project_id:
        gateways = [g for g in gateways if g["project_id"] == project_id]
    return {
        "total": len(gateways),
        "online": sum(1 for g in gateways if g["status"] == "ONLINE"),
        "offline": sum(1 for g in gateways if g["status"] == "OFFLINE"),
        "gateways": gateways,
    }
