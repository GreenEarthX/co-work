"""
Projects API — visible project list for authenticated users.

GET /api/v1/projects/visible
  Returns the set of projects the requesting user is permitted to see,
  based on their JWT claims. Guest sessions receive an empty list.
  Falls back to project_registry when no JWT is present (dev only).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.capacity_units import capacity_mtpd_to_mt_year
from app.core.db_backend import domain_connection, domain_is_postgres
from app.core.project_registry import (
    ProjectAccessProfile,
    all_project_profiles,
    company_slug,
    get_effective_context,
)

router = APIRouter()

# Project data comes from PostgreSQL only: `projects` for the headline fields,
# `project_profile` (alembic 068) for the rest. The _PROJECT_META dictionary
# that stood here — a second, disagreeing copy of the frontend's data — was
# deleted on 2026-10-25 (JML: PostgreSQL is the reference).



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
    # The rest of the project record (project_profile.profile) and its state.
    profile: Optional[dict] = None
    profile_verification: Optional[str] = None
    # Gates, state and capital eligibility — from the ENGINE only, scoped to the
    # caller's persona (app/core/engine_view.py). Never from the profile.
    bankability: Optional[dict] = None


class ProjectProfileIntelligence(BaseModel):
    project_id: str
    record_id: str
    narrative: str
    source_scope: str
    access_tier: str
    backend_store: str
    linked_records: list[str]
    updated_at: str


# Keys of a profile that state an ASSESSMENT (gates, completion, capital
# status, readiness). Assessments come from the engine; these are never served.
_PROFILE_ASSESSMENT_KEYS = frozenset({"bankability", "risk_alerts", "unlocked_capital", "capital_status",
                                      "overall_completion", "gates", "next_milestone"})


def _profile_to_visible(profile: ProjectAccessProfile) -> VisibleProject | None:
    """
    Render a project for the map/list from PostgreSQL: the `projects` row for
    the headline fields, `project_profile` for the rest. A project with no
    profile (one created through /projects/new) still renders: lat/lng stay
    None rather than 0/0, which would drop a pin in the Gulf of Guinea.
    """
    from app.core.projects_store import fetch_project, fetch_project_profile

    row = fetch_project(profile.project_id)
    if not row:
        return None
    record = fetch_project_profile(profile.project_id)
    # Gate figures are the engine's alone (JML 2026-10-28). Any assessment still
    # held in a profile is withheld, so no screen can read it.
    extra = {k: v for k, v in ((record or {}).get("profile") or {}).items()
             if k not in _PROFILE_ASSESSMENT_KEYS}
    capacity = float(row.get("capacity_mtpd") or 0.0)
    ctx = get_effective_context(profile.project_id)
    return VisibleProject(
        id=profile.project_id,
        name=row["project_name"],
        molecule=row.get("molecule") or "",
        location=row.get("location") or "",
        country=row.get("country") or "",
        lat=extra.get("lat"),
        lng=extra.get("lng"),
        capacity_mtpd=capacity,
        capacity_mt_year=capacity_mtpd_to_mt_year(capacity),
        capex_eur=float(row.get("capex_eur") or 0.0),
        status=row.get("status") or "development",
        phase=extra.get("phase") or (ctx.phase if ctx else "development"),
        completion_date=str(row.get("completion_date") or ""),
        description=extra.get("description") or "",
        owner_company=profile.owner_company_name,
        associated_companies=list(profile.associated_company_names),
        jurisdiction=profile.jurisdiction,
        profile=extra or None,
        profile_verification=(record or {}).get("verification_state"),
    )


def _visible_ids_from_jwt(payload: dict) -> list[str]:
    """Visible project ids for a decoded JWT: GEX sees all; a company sees the
    projects it owns and those it is a stakeholder of (PostgreSQL only)."""
    profiles = all_project_profiles()
    if payload.get("is_platform_admin", False):
        return [p.project_id for p in profiles]
    company_id = company_slug(payload.get("company_name", ""))
    return [p.project_id for p in profiles if company_id in p.stakeholder_company_ids]


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
    if domain_is_postgres():
        # 044 owns risk_flag_status / risk_flag_events and their policies.
        # `id` is an identity column there, so the inserts below (which never
        # name `id`) behave the same on both stores.
        return
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
    try:
        conn = domain_connection()
        _ensure_flag_tables(conn)
        rows = conn.execute(
            "SELECT flag_id, status FROM risk_flag_status WHERE project_id = ?", (project_id,)
        ).fetchall()
        conn.close()
        return {r["flag_id"]: r["status"] for r in rows}
    except Exception:
        # Fails soft to "no overlay" on purpose — an unreadable status table
        # must not blank the risk flags themselves. Widened from sqlite3.Error
        # when this moved to DOMAIN_DB_BACKEND: psycopg2 raises its own types,
        # and an RLS-filtered read is not an error at all.
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
    from datetime import datetime, timezone
    from app.core.project_registry import get_project_profile
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
    conn = domain_connection()
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
    from app.core.risk_flags import visible_risk_flags

    payload = _require_user(authorization)
    visible = visible_risk_flags(project_id, payload)
    if visible is None or not any(f.id == flag_id for f in visible):
        raise HTTPException(status_code=404, detail="Risk flag not found")

    conn = domain_connection()
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
    # A premise change that removes evidence from the bar goes through
    # /api/v1/premises: a document and a second party (JML 2026-10-28).
    from app.core.premises import removes_items
    removing = [f for f in ("financing_model", "power_model")
                if f in updates and removes_items(f, getattr(current, f, None), updates[f])]
    if removing:
        raise HTTPException(status_code=409, detail={
            "code": "PREMISE_NEEDS_DOCUMENT_AND_SECOND_PARTY", "fields": removing,
            "message": "This change removes evidence from the bar. Propose it at /api/v1/premises/"
                       f"{project_id} with its supporting document; a second party confirms it."})
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
    reevaluation = None
    if changes:
        # A premise decides which items apply: re-evaluate now (JML 2026-10-28).
        from app.api.v1.routes_bankability_proxy import reevaluate

        fields = ", ".join(f"{f} {o} -> {n}" for f, o, n in changes)
        try:
            reevaluation = (await reevaluate(normalized, reason=f"premise {fields}",
                                             actor=payload.get("user_id")))["changes"]
        except HTTPException as exc:
            reevaluation = {"error": exc.detail, "state_withdrawn": True}
    return {"project_id": project_id, **new_ctx, "updated_by": actor, "updated_at": now,
            "reevaluation": reevaluation}


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

    by_id = {p.project_id: p for p in all_project_profiles()}
    result: list[VisibleProject] = []
    for pid in _visible_ids_from_jwt(payload):
        vp = _profile_to_visible(by_id[pid]) if pid in by_id else None
        if vp:
            vp.bankability = await _engine_bankability(pid, payload, by_id[pid].owner_company_id)
            result.append(vp)
    return result


async def _engine_bankability(project_id: str, payload: dict, owner_company_id: str | None) -> dict:
    """The engine's view of a project for this caller; `evaluated: False` when
    the engine has not evaluated it and cannot now — never a stored guess."""
    from fastapi import HTTPException as _HTTPException

    from app.api.v1.routes_bankability_proxy import engine_rules, fresh_snapshot
    from app.core.engine_view import bankability_view, persona_for

    persona = persona_for(payload, owner_company_id)
    try:
        persona_gates = (await engine_rules()).get("persona_gates", {})
    except _HTTPException:
        view = bankability_view(None, persona, {})
        view["unavailable"] = "The bankability engine is not answering."
        return view
    snapshot, evaluated_at = await fresh_snapshot(project_id)
    return bankability_view(snapshot, persona, persona_gates, evaluated_at)


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

    # From PostgreSQL (project_profile_intelligence); the dictionary in code that
    # held the one record was moved there on 2026-10-25.
    from app.core.projects_store import _rows

    rows = _rows("SELECT record_id, narrative, source_scope, access_tier, backend_store, linked_records, "
                 "updated_at FROM project_profile_intelligence WHERE project_id = :pid "
                 "ORDER BY updated_at DESC LIMIT 1", {"pid": project_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Project profile intelligence not found")
    intel = rows[0]
    return ProjectProfileIntelligence(project_id=project_id, **{**intel, "updated_at": str(intel["updated_at"])[:10],
                                                                "linked_records": intel["linked_records"] or []})




# ── Per-project datasets the screens read (alembic 069/071) ─────────────────

# The kinds the frontend reads. The backend kinds (deal_inputs, …) reach the
# screens through their engines, not raw.
SCREEN_DATASET_KINDS = frozenset({
    "bankers_snapshot", "capital_stack", "cert_readiness", "cert_45v", "offtake_quality",
    "insurance_schedule", "transfer_readiness", "ic_pack_config", "ic_pack_readiness", "demand_buyers",
    "spend_wave", "drawdown_tranches", "drawdown_milestones", "term_sheet", "project_timeline", "plant_builder_preset",
})


@router.get("/{project_id}/datasets/{kind}")
def get_project_dataset(project_id: str, kind: str, request: Request):
    """One recorded dataset of a project, read in the caller's tenant (RLS: GEX
    and the companies that can see the project). 404 NOT_RECORDED when there is
    none — the screens show that; there is no default any more (2026-10-25)."""
    from app.core.projects_store import _rows, resolve_alias
    from app.core.request_tenant import company_from_payload, payload_from_request

    tenant = company_from_payload(payload_from_request(request))
    if not tenant:
        raise HTTPException(status_code=401, detail="Authentication required")
    if kind not in SCREEN_DATASET_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown dataset kind: {kind}")
    pid = resolve_alias(project_id) or project_id
    rows = _rows("SELECT payload, verification_state, verified_by, verified_at, source FROM project_dataset "
                 "WHERE project_id = :pid AND kind = :kind", {"pid": pid, "kind": kind}, company_id=tenant)
    if not rows:
        raise HTTPException(status_code=404, detail={
            "code": "NOT_RECORDED", "message": "Nothing is recorded for this project yet."})
    r = rows[0]
    return {"project_id": pid, "kind": kind, "payload": r["payload"],
            "verification_state": r["verification_state"], "verified_by": r["verified_by"],
            "verified_at": str(r["verified_at"]) if r["verified_at"] else None, "source": r["source"]}
