"""
Projects API — visible project list for authenticated users.

GET /api/v1/projects/visible
  Returns the set of projects the requesting user is permitted to see,
  based on their JWT claims. Guest sessions receive an empty list.
  Falls back to project_registry when no JWT is present (dev only).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.capacity_units import capacity_mtpd_to_mt_year
from app.core.project_registry import (
    PROJECT_ACCESS_PROFILES,
    ProjectAccessProfile,
    company_slug,
    get_effective_context,
    visible_project_ids_for_company,
)

router = APIRouter()

# ── Static metadata that mirrors the frontend CUSTOMER_PROJECTS shape ───────
# Extend this as projects are added to PROJECT_ACCESS_PROFILES.

_PROJECT_META: dict[str, dict] = {
    # ── ETFuels SA portfolio ─────────────────────────────────────────────
    "proj_etf_pecos1": {
        "name": "ETFuels Pecos I",
        "molecule": "e-Methanol",
        "location": "Pecos County, Texas",
        "country": "US",
        "lat": 31.42, "lng": -103.49,
        "capacity_mtpd": 329,
        "capex_eur": 562_000_000,
        "status": "construction",
        "phase": "FEED Class 3 — Structurally Bankable",
        "completion_date": "2027-Q4",
        "description": "340 MW wind, 150 MW PEM electrolysis, 120,000 t/yr e-methanol.",
    },
    "etfuels_us_tx_rattlesnake_gap": {
        "name": "Rattlesnake Gap",
        "molecule": "e-Methanol",
        "location": "West Texas (Christoval / Schleicher County)",
        "country": "US",
        "lat": 31.20, "lng": -100.50,
        "capacity_mtpd": 342,
        "capex_eur": 0,
        "status": "development",
        "phase": "FEED underway — FID target end-2026",
        "completion_date": "2030-Q1",
        "description": "500 MW behind-the-meter wind+solar, 125,000 t/yr e-methanol. Public-source seed.",
    },
    "etfuels_fi_ranua_naataaapa": {
        "name": "Ranua Näätäaapa e-Methanol",
        "molecule": "e-Methanol",
        "location": "Ranua, Lapland",
        "country": "FI",
        "lat": 65.93, "lng": 26.13,
        "capacity_mtpd": 301,
        "capex_eur": 800_000_000,
        "status": "development",
        "phase": "Pre-FEED — tax credit awarded",
        "completion_date": "2031-Q4",
        "description": "300 MW wind, 110,000 t/yr e-methanol. Business Finland tax credit €118.6M.",
    },
    "etfuels_uk_skyfuel_teesside": {
        "name": "Project SkyFuel Teesside",
        "molecule": "SAF",
        "location": "Redcar, Teesside",
        "country": "GB",
        "lat": 54.62, "lng": -1.07,
        "capacity_mtpd": 90,
        "capex_eur": 0,
        "status": "development",
        "phase": "AFF-supported development — FEED progressing",
        "completion_date": "2032-Q4",
        "description": "33,000 t/yr e-SAF via Methanol-to-Jet. £5M UK AFF grant. Public-source seed.",
    },
    # ── Other companies ──────────────────────────────────────────────────
    "proj_rheinwerk_prosumer": {
        "name": "RheinWerk Duisburg H₂ (Prosumer)",
        "molecule": "H2",
        "location": "Duisburg, NRW",
        "country": "DE",
        "lat": 51.43, "lng": 6.76,
        "capacity_mtpd": 55,
        "capex_eur": 210_000_000,
        "status": "development",
        "phase": "Corporate FID preparation — balance-sheet funded",
        "completion_date": "2028-Q2",
        "description": "Industrial prosumer: 120 MW electrolysis for own steel-finishing decarbonisation. HYBRID power, balance-sheet funded, internal self-offtake.",
    },
    "proj_bremen_h2": {
        "name": "Bremen Green Hydrogen Plant",
        "molecule": "H2",
        "location": "Bremen, Germany",
        "country": "DE",
        "lat": 53.0793, "lng": 8.8017,
        "capacity_mtpd": 120,
        "capex_eur": 220_000_000,
        "status": "construction",
        "phase": "Construction",
        "completion_date": "2027-Q2",
        "description": "Grid-scale green hydrogen for Bremerhaven industrial corridor.",
    },
    "proj_rotterdam_nh3": {
        "name": "Rotterdam Green Ammonia Terminal",
        "molecule": "NH3",
        "location": "Rotterdam, Netherlands",
        "country": "NL",
        "lat": 51.9244, "lng": 4.4777,
        "capacity_mtpd": 300,
        "capex_eur": 380_000_000,
        "status": "development",
        "phase": "Advisory",
        "completion_date": "2028-Q4",
        "description": "Export-grade green ammonia hub, Maasvlakte II.",
    },
    "proj_sansebastian_emethanol": {
        "name": "Project Helios e-Methanol",
        "molecule": "e-Methanol",
        "location": "San Sebastian, Spain",
        "country": "ES",
        "lat": 43.3183, "lng": -1.9812,
        "capacity_mtpd": 80,
        "capex_eur": 165_000_000,
        "status": "construction",
        "phase": "Commercial",
        "completion_date": "2026-Q4",
        "description": "Basque Country e-methanol for maritime bunkering.",
    },
    "proj_wales_saf": {
        "name": "Celtic Green SAF Complex",
        "molecule": "SAF",
        "location": "Neath Port Talbot, Wales",
        "country": "GB",
        "lat": 51.6598, "lng": -3.8025,
        "capacity_mtpd": 200,
        "capex_eur": 290_000_000,
        "status": "development",
        "phase": "Advisory",
        "completion_date": "2029-Q1",
        "description": "UK SAF mandate-aligned facility targeting Heathrow uplift.",
    },
    "proj_lehavre_eng": {
        "name": "Le Havre e-Gas Hub",
        "molecule": "e-NG",
        "location": "Le Havre, France",
        "country": "FR",
        "lat": 49.4944, "lng": 0.1079,
        "capacity_mtpd": 150,
        "capex_eur": 195_000_000,
        "status": "operating",
        "phase": "Operations",
        "completion_date": "2025-Q1",
        "description": "Normandy offshore wind-to-gas pilot, now in operations.",
    },
    "proj_hamburgone_emethanol": {
        "name": "HamburgOne e-Methanol Plant",
        "molecule": "e-Methanol",
        "location": "Hamburg, Germany",
        "country": "DE",
        "lat": 53.5753, "lng": 10.0153,
        "capacity_mtpd": 90,
        "capex_eur": 185_000_000,
        "status": "development",
        "phase": "Structuring",
        "completion_date": "2027-Q3",
        "description": "Port of Hamburg e-methanol for North Sea shipping lanes.",
    },
    "proj_madrid2_sansebastian": {
        "name": "Madrid2 San-Sebastian e-Methanol",
        "molecule": "e-Methanol",
        "location": "San Sebastian, Spain",
        "country": "ES",
        "lat": 43.3000, "lng": -2.0000,
        "capacity_mtpd": 75,
        "capex_eur": 155_000_000,
        "status": "development",
        "phase": "Advisory",
        "completion_date": "2028-Q2",
        "description": "Madrid2 Iberian e-methanol export corridor.",
    },
}

_PROJECT_PROFILE_INTELLIGENCE: dict[str, dict] = {
    "proj_etf_pecos1": {
        "record_id": "profile_intel_proj_etf_pecos1_public_v1",
        "narrative": (
            "340 MW wind, 150 MW PEM electrolysis, 120,000 t/yr e-methanol. "
            "Primary offtake: RFOcean (binding 10-year fixed-price from 2030, bankable contract). "
            "Secondary: ETFuels SA (5-year ToP, 70,000 t/yr, CIF Rotterdam — related-party, unverified). "
            "Indicative: Lufthansa Cargo SAF pool (30,000 t/yr — non-binding). "
            "Certification: 45V active (Tier 1 pathway), RFNBO under temporal correlation review. "
            "IRA incentives: ~$1.5B secured. Construction start 2027, production 2030."
        ),
        "source_scope": "GEX_PUBLIC_PREFILL",
        "access_tier": "STAKEHOLDER",
        "backend_store": "project_profile_intelligence",
        "linked_records": [
            "project:proj_etf_pecos1",
            "offtake:rfocean_2030_fixed_10y",
            "offtake:etfuels_sa_related_party",
            "certification:45v_tier1",
        ],
        "updated_at": "2026-05-21",
    }
}


class VisibleProject(BaseModel):
    id: str
    name: str
    molecule: str
    location: str
    country: str
    # Optional because runtime-created projects (the /projects/new on-ramp)
    # never collected coordinates or a blurb. Returning null is honest — a
    # default of 0.0/0.0 would drop a map pin in the Gulf of Guinea.
    lat: Optional[float] = None
    lng: Optional[float] = None
    capacity_mtpd: float
    capacity_mt_year: int
    capex_eur: float
    status: str
    phase: str
    completion_date: str = ""
    description: str = ""
    owner_company: str
    associated_companies: list[str]
    jurisdiction: str


class ProjectProfileIntelligence(BaseModel):
    project_id: str
    record_id: str
    narrative: str
    source_scope: str
    access_tier: str
    backend_store: str
    linked_records: list[str]
    updated_at: str


def _profile_to_visible(profile: ProjectAccessProfile) -> VisibleProject | None:
    """
    Render a project for the map/list.

    Static demo projects come from _PROJECT_META. Runtime projects have no
    entry there — before the collision was resolved they were simply dropped,
    so a project created through /projects/new never appeared in the very list
    it was created for. They are now built from the canonical PostgreSQL row,
    which carries name/molecule/location/country/capacity/capex/status.
    """
    meta = _PROJECT_META.get(profile.project_id)
    if meta:
        return VisibleProject(
            id=profile.project_id,
            owner_company=profile.owner_company_name,
            associated_companies=list(profile.associated_company_names),
            jurisdiction=profile.jurisdiction,
            capacity_mt_year=capacity_mtpd_to_mt_year(meta["capacity_mtpd"]),
            **meta,
        )

    from app.core.projects_store import fetch_project

    row = fetch_project(profile.project_id)
    if not row:
        return None
    capacity = float(row.get("capacity_mtpd") or 0.0)
    ctx = get_effective_context(profile.project_id)
    return VisibleProject(
        id=profile.project_id,
        name=row["project_name"],
        molecule=row.get("molecule") or "",
        location=row.get("location") or "",
        country=row.get("country") or "",
        capacity_mtpd=capacity,
        capacity_mt_year=capacity_mtpd_to_mt_year(capacity),
        capex_eur=float(row.get("capex_eur") or 0.0),
        status=row.get("status") or "development",
        phase=ctx.phase if ctx else "development",
        owner_company=profile.owner_company_name,
        associated_companies=list(profile.associated_company_names),
        jurisdiction=profile.jurisdiction,
    )


def _visible_ids_from_jwt(payload: dict) -> list[str]:
    """Derive visible project IDs from a decoded JWT payload."""
    company_name = payload.get("company_name", "")
    company_type = payload.get("company_type", "")
    capabilities = payload.get("capabilities") or []
    is_platform_admin = payload.get("is_platform_admin", False)

    if is_platform_admin:
        return list(PROJECT_ACCESS_PROFILES.keys())

    company_id = company_slug(company_name)
    visible: list[str] = []
    for pid, profile in PROJECT_ACCESS_PROFILES.items():
        is_owner = profile.owner_company_id == company_id
        is_associated = company_id in profile.shared_with_company_ids

        if company_type == "PRODUCER" or "PRODUCE" in capabilities:
            if is_owner:
                visible.append(pid)
                continue
        if is_associated:
            visible.append(pid)

    # Runtime-created projects owned by this company. The loop above only walks
    # the STATIC registry, so without this a project created through the
    # on-ramp was invisible to its own creator.
    from app.core.projects_store import project_ids_owned_by

    for pid in project_ids_owned_by(company_id):
        if pid not in visible:
            visible.append(pid)

    return visible


@router.get("/{project_id}/risk-flags")
async def get_project_risk_flags(
    project_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Structured risk flags for one project, ABAC-filtered server-side.

    Visibility per flag = classification × caller stakeholding × clearance:
      PUBLIC → any project viewer · STAKEHOLDER → owner + associated companies
      · CONFIDENTIAL → owner company · RESTRICTED → owner EXEC/FINANCE.
    Hidden flags are silently omitted (no leaked counts). 404 when the caller
    cannot see the project at all.
    """
    from app.core.auth import get_user_payload_from_token
    from app.core.risk_flags import visible_risk_flags

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = get_user_payload_from_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    flags = visible_risk_flags(project_id, payload)
    if flags is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Merge the lifecycle overlay: transitions made via PATCH supersede the
    # seeded status (the seed registry is never mutated).
    overlay = _risk_flag_status_overlay(project_id)
    out = []
    for f in flags:
        d = f.to_dict()
        if d["id"] in overlay:
            d["status"] = overlay[d["id"]]
        out.append(d)

    return {
        "project_id": project_id,
        "flags": out,
        "total_visible": len(out),
    }


# ── Risk flag lifecycle — flags are resolvable, not just displayable ─────────

_FLAG_TRANSITIONS: dict[str, list[str]] = {
    "OPEN": ["ACKNOWLEDGED", "RESOLVED"],
    "ACKNOWLEDGED": ["WAIVED", "RESOLVED", "OPEN"],
    "WAIVED": ["OPEN"],          # waivers are reversible
    "RESOLVED": [],              # resolution is terminal — open a new flag instead
}


def _ensure_flag_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_flag_status (
            project_id TEXT NOT NULL,
            flag_id TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, flag_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_flag_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            flag_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            actor TEXT NOT NULL,
            note TEXT,
            at TEXT NOT NULL
        )
    """)
    conn.commit()


def _risk_flag_status_overlay(project_id: str) -> dict[str, str]:
    import sqlite3
    from app.core.project_registry import _DB_PATH
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        _ensure_flag_tables(conn)
        rows = conn.execute(
            "SELECT flag_id, status FROM risk_flag_status WHERE project_id = ?", (project_id,)
        ).fetchall()
        conn.close()
        return {r["flag_id"]: r["status"] for r in rows}
    except sqlite3.Error:
        return {}


class RiskFlagPatch(BaseModel):
    status: str       # ACKNOWLEDGED | WAIVED | RESOLVED | OPEN
    note: str | None = None


@router.patch("/{project_id}/risk-flags/{flag_id}")
async def patch_risk_flag(
    project_id: str,
    flag_id: str,
    body: RiskFlagPatch,
    authorization: str | None = Header(default=None),
):
    """
    Transition a risk flag's lifecycle status. Allowed transitions:
    OPEN→ACKNOWLEDGED/RESOLVED, ACKNOWLEDGED→WAIVED/RESOLVED/OPEN,
    WAIVED→OPEN. RESOLVED is terminal. Caller must be able to SEE the flag
    (same ABAC as listing) and belong to the owner company with the flag's
    owner_function or EXECUTIVE — or be platform admin. Every transition is
    written to the append-only risk_flag_events audit table.
    """
    import sqlite3
    from datetime import datetime, timezone
    from app.core.project_registry import _DB_PATH, get_project_profile
    from app.core.risk_flags import visible_risk_flags

    payload = _require_user(authorization)
    visible = visible_risk_flags(project_id, payload)
    if visible is None:
        raise HTTPException(status_code=404, detail="Project not found")
    flag = next((f for f in visible if f.id == flag_id), None)
    if flag is None:
        raise HTTPException(status_code=404, detail="Risk flag not found")

    profile = get_project_profile(project_id)
    company_id = company_slug(payload.get("company_name", ""))
    is_admin = bool(payload.get("is_platform_admin"))
    is_owner = profile is not None and company_id == profile.owner_company_id
    bf = payload.get("business_function", "")
    if not (is_admin or (is_owner and bf in (flag.owner_function, "EXECUTIVE"))):
        raise HTTPException(status_code=403, detail="Flag owner function or executive at owner company required")

    overlay = _risk_flag_status_overlay(project_id)
    current = overlay.get(flag_id, flag.status)
    target = body.status
    if target not in ("OPEN", "ACKNOWLEDGED", "WAIVED", "RESOLVED"):
        raise HTTPException(status_code=422, detail="Invalid status")
    if target not in _FLAG_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=409,
            detail=f"Invalid transition {current} → {target}. Allowed: {_FLAG_TRANSITIONS.get(current, [])}",
        )
    if target == "WAIVED" and not (body.note and body.note.strip()):
        raise HTTPException(status_code=422, detail="A waiver requires a justification note")

    actor = payload.get("email", "unknown")
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_flag_tables(conn)
    conn.execute(
        """INSERT INTO risk_flag_status (project_id, flag_id, status, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(project_id, flag_id) DO UPDATE SET
             status=excluded.status, updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
        (project_id, flag_id, target, actor, now),
    )
    conn.execute(
        "INSERT INTO risk_flag_events (project_id, flag_id, old_status, new_status, actor, note, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, flag_id, current, target, actor, body.note, now),
    )
    conn.commit()
    conn.close()

    return {"project_id": project_id, "flag_id": flag_id, "old_status": current, "status": target, "updated_by": actor, "updated_at": now}


@router.get("/{project_id}/risk-flags/{flag_id}/events")
async def get_risk_flag_events(
    project_id: str,
    flag_id: str,
    authorization: str | None = Header(default=None),
):
    """Append-only transition history for one risk flag (same visibility as the flag)."""
    import sqlite3
    from app.core.project_registry import _DB_PATH
    from app.core.risk_flags import visible_risk_flags

    payload = _require_user(authorization)
    visible = visible_risk_flags(project_id, payload)
    if visible is None or not any(f.id == flag_id for f in visible):
        raise HTTPException(status_code=404, detail="Risk flag not found")

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_flag_tables(conn)
    rows = conn.execute(
        "SELECT old_status, new_status, actor, note, at FROM risk_flag_events WHERE project_id = ? AND flag_id = ? ORDER BY id DESC",
        (project_id, flag_id),
    ).fetchall()
    conn.close()
    return {"project_id": project_id, "flag_id": flag_id, "events": [dict(r) for r in rows]}


# ── Project context: power model + phase + financing model as DATA ──────────
# Onboarding/updating a project's physical and financing premise is an API
# call with an audit trail, not a source-code edit.

class ProjectContextPatch(BaseModel):
    power_model: str | None = None      # OFF_GRID_BTM | GRID_CONNECTED | HYBRID
    phase: str | None = None            # development | construction | commissioning | operating
    financing_model: str | None = None  # PROJECT_FINANCE | BALANCE_SHEET


def _require_user(authorization: str | None) -> dict:
    from app.core.auth import get_user_payload_from_token
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return get_user_payload_from_token(authorization.split(" ", 1)[1].strip())
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("/{project_id}/context")
async def get_project_context(project_id: str, authorization: str | None = Header(default=None)):
    """Effective project context (DB override > seed). Stakeholders only."""
    from app.core.project_registry import get_effective_context, get_project_profile

    payload = _require_user(authorization)
    profile = get_project_profile(project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Project not found")
    company_id = company_slug(payload.get("company_name", ""))
    is_admin = bool(payload.get("is_platform_admin"))
    if not is_admin and company_id not in profile.stakeholder_company_ids and company_id != profile.owner_company_id:
        raise HTTPException(status_code=404, detail="Project not found")

    ctx = get_effective_context(project_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="No context declared for project")
    return {
        "project_id": project_id,
        "power_model": ctx.power_model,
        "phase": ctx.phase,
        "financing_model": ctx.financing_model,
    }


@router.patch("/{project_id}/context")
async def patch_project_context(
    project_id: str,
    body: ProjectContextPatch,
    authorization: str | None = Header(default=None),
):
    """
    Update project context. Owner-company EXECUTIVE or platform admin only.
    Every field change is written to the append-only project_context_events
    audit table (who, what, old → new, when).
    """
    from app.core.project_registry import (
        VALID_FINANCING_MODELS, VALID_PHASES, VALID_POWER_MODELS,
        get_effective_context, get_project_profile,
        normalize_project_id,
    )

    payload = _require_user(authorization)
    profile = get_project_profile(project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Project not found")
    company_id = company_slug(payload.get("company_name", ""))
    is_admin = bool(payload.get("is_platform_admin"))
    is_owner_exec = (
        company_id == profile.owner_company_id
        and payload.get("business_function") == "EXECUTIVE"
    )
    if not (is_admin or is_owner_exec):
        raise HTTPException(status_code=403, detail="Owner executive or platform admin required")

    updates: dict[str, str] = {}
    if body.power_model is not None:
        if body.power_model not in VALID_POWER_MODELS:
            raise HTTPException(status_code=422, detail=f"power_model must be one of {VALID_POWER_MODELS}")
        updates["power_model"] = body.power_model
    if body.phase is not None:
        if body.phase not in VALID_PHASES:
            raise HTTPException(status_code=422, detail=f"phase must be one of {VALID_PHASES}")
        updates["phase"] = body.phase
    if body.financing_model is not None:
        if body.financing_model not in VALID_FINANCING_MODELS:
            raise HTTPException(status_code=422, detail=f"financing_model must be one of {VALID_FINANCING_MODELS}")
        updates["financing_model"] = body.financing_model
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    current = get_effective_context(project_id)
    normalized = normalize_project_id(project_id)
    actor = payload.get("email", "unknown")
    new_ctx = {
        "power_model": updates.get("power_model", current.power_model if current else "GRID_CONNECTED"),
        "phase": updates.get("phase", current.phase if current else "development"),
        "financing_model": updates.get("financing_model", current.financing_model if current else "PROJECT_FINANCE"),
    }

    # Canonical store (PostgreSQL, migration 033). The state write and its
    # audit events commit together — see projects_store.update_context.
    from app.core.projects_store import update_context

    changes = [
        (field, getattr(current, field, None) if current else None, new_value)
        for field, new_value in updates.items()
        if (getattr(current, field, None) if current else None) != new_value
    ]
    now = update_context(
        project_id=normalized,
        power_model=new_ctx["power_model"],
        phase=new_ctx["phase"],
        financing_model=new_ctx["financing_model"],
        actor=actor,
        changes=changes,
    )

    return {"project_id": project_id, **new_ctx, "updated_by": actor, "updated_at": now}


@router.get("/{project_id}/context/events")
async def get_project_context_events(project_id: str, authorization: str | None = Header(default=None)):
    """Append-only audit trail of context changes. Owner company + admin only."""
    from app.core.project_registry import get_project_profile, normalize_project_id

    payload = _require_user(authorization)
    profile = get_project_profile(project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Project not found")
    company_id = company_slug(payload.get("company_name", ""))
    if not (bool(payload.get("is_platform_admin")) or company_id == profile.owner_company_id):
        raise HTTPException(status_code=404, detail="Project not found")

    from app.core.projects_store import fetch_context_events

    events = fetch_context_events(normalize_project_id(project_id))
    return {"project_id": project_id, "events": events}


# ── Project on-ramp: create a real project (the bridge's first stop) ─────────
# A new customer's project begins here. Create persists the project_id, owner
# company (the caller's), and the physical/financing premise so every later
# bridge stop — gates, evidence, packages, finance, capital — operates on it.

class ProjectCreate(BaseModel):
    name: str
    molecule: str
    location: str
    country: str
    capacity_mtpd: float
    capex_eur: float
    power_model: str       # OFF_GRID_BTM | GRID_CONNECTED | HYBRID
    financing_model: str   # PROJECT_FINANCE | BALANCE_SHEET
    phase: str             # development | construction | commissioning | operating


@router.post("", response_model=VisibleProject, status_code=201)
async def create_project_endpoint(
    body: ProjectCreate,
    authorization: str | None = Header(default=None),
) -> VisibleProject:
    """
    Create a new project owned by the caller's company and seed its context.

    Any authenticated user with a company may create a project; the owner is the
    caller's company (you cannot create a project for someone else). The physical
    and financing premise is validated and seeded so the project is a first-class
    bridge citizen immediately. Returns the created project in VisibleProject shape.
    """
    from app.core.project_registry import (
        VALID_FINANCING_MODELS, VALID_PHASES, VALID_POWER_MODELS, create_project,
    )

    payload = _require_user(authorization)
    company_name = (payload.get("company_name") or "").strip()
    if not company_name:
        raise HTTPException(status_code=403, detail="A company is required to create a project")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name is required")
    if body.power_model not in VALID_POWER_MODELS:
        raise HTTPException(status_code=422, detail=f"power_model must be one of {VALID_POWER_MODELS}")
    if body.financing_model not in VALID_FINANCING_MODELS:
        raise HTTPException(status_code=422, detail=f"financing_model must be one of {VALID_FINANCING_MODELS}")
    if body.phase not in VALID_PHASES:
        raise HTTPException(status_code=422, detail=f"phase must be one of {VALID_PHASES}")
    if body.capacity_mtpd < 0 or body.capex_eur < 0:
        raise HTTPException(status_code=422, detail="capacity_mtpd and capex_eur must be non-negative")

    project_id = create_project(
        name=name,
        molecule=body.molecule.strip(),
        location=body.location.strip(),
        country=body.country.strip().upper(),
        capacity_mtpd=body.capacity_mtpd,
        capex_eur=body.capex_eur,
        owner_company_name=company_name,
        power_model=body.power_model,
        financing_model=body.financing_model,
        phase=body.phase,
        created_by=payload.get("email", "unknown"),
    )

    return VisibleProject(
        id=project_id,
        name=name,
        molecule=body.molecule.strip(),
        location=body.location.strip(),
        country=body.country.strip().upper(),
        # lat/lng omitted deliberately: the on-ramp does not collect
        # coordinates, and 0.0/0.0 is a map pin in the Gulf of Guinea.

        capacity_mtpd=body.capacity_mtpd,
        capacity_mt_year=capacity_mtpd_to_mt_year(body.capacity_mtpd),
        capex_eur=body.capex_eur,
        status=body.phase,
        phase=body.phase,
        completion_date="",
        description="",
        owner_company=company_name,
        associated_companies=[],
        jurisdiction=body.country.strip().upper(),
    )


def _runtime_visible_projects(company_id: str, is_admin: bool) -> list[VisibleProject]:
    """
    Runtime-created projects (the /projects/new on-ramp) as VisibleProject rows.

    Reads the CANONICAL PostgreSQL `projects` table. This previously queried the
    SQLite copy and swallowed sqlite3.Error into an empty list — so after that
    table was retired, every runtime project silently vanished from the list it
    had just been created for, with no error anywhere. The store logs its own
    failures; this no longer hides them.
    """
    from app.core.project_registry import get_effective_context
    from app.core.projects_store import list_projects

    out: list[VisibleProject] = []
    for r in list_projects(owner_tenant_id=None if is_admin else company_id):
        cap = float(r.get("capacity_mtpd") or 0.0)
        ctx = get_effective_context(r["project_id"])
        out.append(VisibleProject(
            id=r["project_id"],
            name=r["project_name"],
            molecule=r.get("molecule") or "",
            location=r.get("location") or "",
            country=r.get("country") or "",
            # lat/lng stay None: the on-ramp never collected coordinates. The
            # old code sent 0.0/0.0, which puts a map pin in the Gulf of Guinea.
            capacity_mtpd=cap,
            capacity_mt_year=capacity_mtpd_to_mt_year(cap),
            capex_eur=float(r.get("capex_eur") or 0.0),
            status=r.get("status") or "development",
            phase=ctx.phase if ctx else (r.get("status") or "development"),
            owner_company=r.get("owner_company_name") or "",
            associated_companies=[],
            jurisdiction=r.get("country") or "",
        ))
    return out


@router.get("/visible", response_model=list[VisibleProject])
async def get_visible_projects(
    authorization: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None, alias="x-demo-user"),
) -> list[VisibleProject]:
    """
    Return projects visible to the authenticated user.

    Auth: Bearer JWT, with the same demo header fallback used by ABAC middleware.
    Falls back to empty list for unauthenticated requests.
    """
    from app.core.auth import get_user_payload_by_email, get_user_payload_from_token
    from app.core.config import settings

    payload: dict | None = None
    bearer_token_invalid = False

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = get_user_payload_from_token(token)
        except ValueError:
            bearer_token_invalid = True

    # Anchor: keep local demo sessions aligned with ABAC middleware identity.
    if payload is None and x_demo_user:
        if not settings.GEX_DEMO_MODE:
            raise HTTPException(
                status_code=401,
                detail="Authentication required — demo headers disabled in production",
            )
        payload = get_user_payload_by_email(x_demo_user.strip().lower())
        if payload is None:
            raise HTTPException(status_code=401, detail="Unknown demo user")

    if payload is None:
        if bearer_token_invalid:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return []

    visible_ids = _visible_ids_from_jwt(payload)
    result: list[VisibleProject] = []
    seen: set[str] = set()
    for pid in visible_ids:
        profile = PROJECT_ACCESS_PROFILES.get(pid)
        if profile:
            vp = _profile_to_visible(profile)
            if vp:
                result.append(vp)
                seen.add(pid)

    # Runtime-created projects (the on-ramp) — owned by the caller's company.
    company_id = company_slug(payload.get("company_name", ""))
    is_admin = bool(payload.get("is_platform_admin"))
    for vp in _runtime_visible_projects(company_id, is_admin):
        if vp.id not in seen:
            result.append(vp)
            seen.add(vp.id)
    return result


@router.get("/{project_id}/profile-intelligence", response_model=ProjectProfileIntelligence)
async def get_project_profile_intelligence(
    project_id: str,
    authorization: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None, alias="x-demo-user"),
) -> ProjectProfileIntelligence:
    """Return backend-linked general project intelligence for the profile page."""
    from app.core.auth import get_user_payload_by_email, get_user_payload_from_token
    from app.core.config import settings

    payload: dict | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = get_user_payload_from_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if payload is None and x_demo_user:
        if not settings.GEX_DEMO_MODE:
            raise HTTPException(status_code=401, detail="Authentication required — demo headers disabled in production")
        payload = get_user_payload_by_email(x_demo_user.strip().lower())

    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if project_id not in _visible_ids_from_jwt(payload):
        raise HTTPException(status_code=403, detail="Project not visible for this user")

    intel = _PROJECT_PROFILE_INTELLIGENCE.get(project_id)
    if not intel:
        raise HTTPException(status_code=404, detail="Project profile intelligence not found")
    return ProjectProfileIntelligence(project_id=project_id, **intel)


