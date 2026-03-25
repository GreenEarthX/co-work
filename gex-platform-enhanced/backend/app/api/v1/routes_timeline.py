"""
GEX Bankability — Funding Timeline & Milestones API (v2.0)

Endpoints:
  GET   /api/v1/timeline/{project_id}
  POST  /api/v1/timeline/{project_id}/milestones
  PATCH /api/v1/timeline/{project_id}/milestones/{milestone_id}
  POST  /api/v1/timeline/{project_id}/initialize
  GET   /api/v1/timeline/{project_id}/drawdown-schedule
  GET   /api/v1/timeline/templates
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date

router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────────────

class Milestone(BaseModel):
    id: Optional[str] = None
    project_id: str
    phase: str                          # ADVISORY | BUILD | FIN_CLOSE | CONSTRUCTION | OPERATIONS
    milestone_name: str
    target_date: Optional[str] = None  # ISO date
    actual_date: Optional[str] = None
    status: str = "PLANNED"            # PLANNED | IN_PROGRESS | COMPLETED | DELAYED | BLOCKED
    gate_dependency: Optional[str] = None
    owner_actor: Optional[str] = None
    funding_trigger: bool = False
    drawdown_amount_eur: Optional[float] = None
    notes: Optional[str] = None
    version: int = 1

class MilestoneUpdate(BaseModel):
    status: Optional[str] = None
    actual_date: Optional[str] = None
    notes: Optional[str] = None

class InitializeRequest(BaseModel):
    molecule: str                       # H2 | NH3 | SAF | E_METHANOL | E_NG


# ── Demo milestone templates ──────────────────────────────────────────────────

_TEMPLATES = {
    "H2": [
        {"phase":"ADVISORY","milestone_name":"PPA term sheet","status":"PLANNED","gate_dependency":"G2","owner_actor":"Commercial","funding_trigger":False},
        {"phase":"ADVISORY","milestone_name":"DFI mandate letter","status":"PLANNED","gate_dependency":None,"owner_actor":"CFO","funding_trigger":False},
        {"phase":"ADVISORY","milestone_name":"Offtake ≥70% binding","status":"PLANNED","gate_dependency":"G4","owner_actor":"Commercial","funding_trigger":False},
        {"phase":"BUILD","milestone_name":"EPC contract executed","status":"PLANNED","gate_dependency":"G5","owner_actor":"PM","funding_trigger":False},
        {"phase":"BUILD","milestone_name":"Insurance CAR/DSU placed","status":"PLANNED","gate_dependency":"G7","owner_actor":"Risk","funding_trigger":False},
        {"phase":"FIN_CLOSE","milestone_name":"IE final signoff","status":"PLANNED","gate_dependency":"G6","owner_actor":"IE","funding_trigger":False},
        {"phase":"FIN_CLOSE","milestone_name":"Term sheet executed","status":"PLANNED","gate_dependency":None,"owner_actor":"CFO","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"FIN_CLOSE","milestone_name":"FID decision","status":"PLANNED","gate_dependency":"G10","owner_actor":"Board","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"CONSTRUCTION","milestone_name":"NTP issued","status":"PLANNED","gate_dependency":None,"owner_actor":"PM","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"CONSTRUCTION","milestone_name":"Electrolyser delivery","status":"PLANNED","gate_dependency":None,"owner_actor":"PM","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"CONSTRUCTION","milestone_name":"COD commissioning","status":"PLANNED","gate_dependency":"G11","owner_actor":"PM","funding_trigger":False},
        {"phase":"OPERATIONS","milestone_name":"Commercial operations","status":"PLANNED","gate_dependency":None,"owner_actor":"Operations","funding_trigger":False},
        {"phase":"OPERATIONS","milestone_name":"First GoO issuance","status":"PLANNED","gate_dependency":None,"owner_actor":"Certification","funding_trigger":False},
    ],
    "SAF": [
        {"phase":"ADVISORY","milestone_name":"F-T EPC pre-FEED","status":"PLANNED","gate_dependency":"G5","owner_actor":"PM","funding_trigger":False},
        {"phase":"ADVISORY","milestone_name":"Airline offtake LOI → binding","status":"PLANNED","gate_dependency":"G4","owner_actor":"Commercial","funding_trigger":False},
        {"phase":"BUILD","milestone_name":"SAF certification pre-audit","status":"PLANNED","gate_dependency":"G2","owner_actor":"Certifier","funding_trigger":False},
        {"phase":"BUILD","milestone_name":"EPC wrap secured","status":"PLANNED","gate_dependency":"G5","owner_actor":"PM","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"FIN_CLOSE","milestone_name":"FID","status":"PLANNED","gate_dependency":"G10","owner_actor":"Board","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"CONSTRUCTION","milestone_name":"F-T unit delivery","status":"PLANNED","gate_dependency":None,"owner_actor":"PM","funding_trigger":True,"drawdown_amount_eur":0},
        {"phase":"OPERATIONS","milestone_name":"ASTM D7566 certification","status":"PLANNED","gate_dependency":None,"owner_actor":"Certifier","funding_trigger":False},
    ],
}
# Reuse H2 template for NH3, E_METHANOL, E_NG with minor name changes
_TEMPLATES["NH3"] = _TEMPLATES["H2"]
_TEMPLATES["E_METHANOL"] = _TEMPLATES["H2"]
_TEMPLATES["E_NG"] = _TEMPLATES["H2"]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}")
async def get_timeline(project_id: str):
    """Full timeline with milestones for a project."""
    template = _TEMPLATES.get("H2", [])
    milestones = [
        {**m, "id": f"ms-{project_id}-{i:03d}", "project_id": project_id}
        for i, m in enumerate(template)
    ]
    return {
        "project_id": project_id,
        "milestones": milestones,
        "total": len(milestones),
        "phases": ["ADVISORY", "BUILD", "FIN_CLOSE", "CONSTRUCTION", "OPERATIONS"],
    }


@router.post("/{project_id}/milestones")
async def create_milestone(project_id: str, milestone: Milestone):
    """Add a milestone to the project timeline."""
    milestone.project_id = project_id
    milestone.id = f"ms-{project_id}-new"
    return {"created": True, "milestone": milestone}


@router.patch("/{project_id}/milestones/{milestone_id}")
async def update_milestone(project_id: str, milestone_id: str, update: MilestoneUpdate):
    """Update milestone status, actual date, or notes."""
    return {
        "updated": True,
        "milestone_id": milestone_id,
        "changes": update.model_dump(exclude_none=True),
    }


@router.post("/{project_id}/initialize")
async def initialize_timeline(project_id: str, request: InitializeRequest):
    """Initialize timeline from molecule-specific template."""
    template = _TEMPLATES.get(request.molecule.upper(), _TEMPLATES["H2"])
    milestones = [
        {**m, "id": f"ms-{project_id}-{i:03d}", "project_id": project_id}
        for i, m in enumerate(template)
    ]
    return {
        "initialized": True,
        "molecule": request.molecule,
        "milestones_created": len(milestones),
        "milestones": milestones,
    }


@router.get("/{project_id}/drawdown-schedule")
async def get_drawdown_schedule(project_id: str):
    """Funding milestones only, with cumulative drawdown curve."""
    # Demo drawdown events — replace with DB query
    events = [
        {"quarter": "Q3-2026", "milestone": "Term Sheet", "amount_eur": 0, "cumulative_eur": 0, "phase": "FIN_CLOSE"},
        {"quarter": "Q3-2026", "milestone": "Facility Agreement", "amount_eur": 42_000_000, "cumulative_eur": 42_000_000, "phase": "FIN_CLOSE"},
        {"quarter": "Q4-2026", "milestone": "NTP + First Drawdown", "amount_eur": 85_000_000, "cumulative_eur": 127_000_000, "phase": "CONSTRUCTION"},
        {"quarter": "Q1-2027", "milestone": "Electrolyser Delivery", "amount_eur": 55_000_000, "cumulative_eur": 182_000_000, "phase": "CONSTRUCTION"},
        {"quarter": "Q3-2027", "milestone": "Civil Works Complete", "amount_eur": 28_000_000, "cumulative_eur": 210_000_000, "phase": "CONSTRUCTION"},
    ]
    return {
        "project_id": project_id,
        "funding_events": events,
        "total_drawdown_eur": 210_000_000,
    }


@router.get("/templates")
async def get_templates():
    """Available timeline templates by molecule."""
    return {
        "templates": [
            {"molecule": mol, "name": f"{mol} Standard Timeline", "milestone_count": len(tmpl)}
            for mol, tmpl in _TEMPLATES.items()
        ]
    }
