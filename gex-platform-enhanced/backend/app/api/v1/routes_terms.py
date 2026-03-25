"""
GEX Bankability — Term Sheet Tracker API (v2.0)

Endpoints:
  GET   /api/v1/terms/{project_id}
  POST  /api/v1/terms/{project_id}/items
  PATCH /api/v1/terms/{project_id}/items/{item_id}
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class TermItem(BaseModel):
    term_name: str
    group: str
    status: str = "PENDING"         # AGREED | PENDING | DISPUTED
    party: str = "Both"             # Buyer | Seller | Both
    notes: Optional[str] = None

class TermUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    party: Optional[str] = None


_PRESET_TERMS = [
    # Financial Terms
    {"id": "t-001", "group": "Financial Terms",    "term_name": "Pricing & Indexation",       "party": "Both",   "status": "AGREED"},
    {"id": "t-002", "group": "Financial Terms",    "term_name": "Floor Price Mechanism",       "party": "Seller", "status": "PENDING"},
    {"id": "t-003", "group": "Financial Terms",    "term_name": "Price Cap",                   "party": "Buyer",  "status": "PENDING"},
    {"id": "t-004", "group": "Financial Terms",    "term_name": "Escalation Formula",          "party": "Both",   "status": "AGREED"},
    # Delivery Terms
    {"id": "t-005", "group": "Delivery Terms",     "term_name": "Volume Commitment (ToP %)",  "party": "Buyer",  "status": "PENDING"},
    {"id": "t-006", "group": "Delivery Terms",     "term_name": "Make-Good Clause",            "party": "Both",   "status": "PENDING"},
    {"id": "t-007", "group": "Delivery Terms",     "term_name": "Outage Protocol",             "party": "Seller", "status": "PENDING"},
    {"id": "t-008", "group": "Delivery Terms",     "term_name": "Delivery Point",              "party": "Both",   "status": "AGREED"},
    # Risk Allocation
    {"id": "t-009", "group": "Risk Allocation",    "term_name": "Force Majeure Definition",   "party": "Both",   "status": "AGREED"},
    {"id": "t-010", "group": "Risk Allocation",    "term_name": "Change-in-Law Clause",        "party": "Both",   "status": "PENDING"},
    {"id": "t-011", "group": "Risk Allocation",    "term_name": "Curtailment Compensation",    "party": "Seller", "status": "DISPUTED"},
    {"id": "t-012", "group": "Risk Allocation",    "term_name": "Environmental Indemnity",     "party": "Both",   "status": "PENDING"},
    # Security Package
    {"id": "t-013", "group": "Security Package",   "term_name": "Step-In Rights",             "party": "Buyer",  "status": "AGREED"},
    {"id": "t-014", "group": "Security Package",   "term_name": "Cut-Through Provisions",      "party": "Both",   "status": "PENDING"},
    {"id": "t-015", "group": "Security Package",   "term_name": "Assignment Consent",          "party": "Seller", "status": "PENDING"},
    {"id": "t-016", "group": "Security Package",   "term_name": "Charge Over Accounts",        "party": "Both",   "status": "PENDING"},
    # Operational
    {"id": "t-017", "group": "Operational",        "term_name": "M&V Protocol",               "party": "Both",   "status": "AGREED"},
    {"id": "t-018", "group": "Operational",        "term_name": "Audit Rights",                "party": "Buyer",  "status": "AGREED"},
    {"id": "t-019", "group": "Operational",        "term_name": "Regulatory Reporting",        "party": "Seller", "status": "PENDING"},
]


@router.get("/{project_id}")
async def get_term_sheet(project_id: str):
    """All term sheet items for a project with status."""
    agreed  = sum(1 for t in _PRESET_TERMS if t["status"] == "AGREED")
    pending = sum(1 for t in _PRESET_TERMS if t["status"] == "PENDING")
    disputed= sum(1 for t in _PRESET_TERMS if t["status"] == "DISPUTED")
    return {
        "project_id": project_id,
        "terms": [{**t, "project_id": project_id} for t in _PRESET_TERMS],
        "summary": {"agreed": agreed, "pending": pending, "disputed": disputed, "total": len(_PRESET_TERMS)},
        "convergence_pct": round(agreed / len(_PRESET_TERMS) * 100),
    }


@router.post("/{project_id}/items")
async def add_term(project_id: str, item: TermItem):
    """Add a custom term to the tracker."""
    return {
        "created": True,
        "item_id": f"t-{project_id}-custom",
        "project_id": project_id,
        "term": item,
    }


@router.patch("/{project_id}/items/{item_id}")
async def update_term(project_id: str, item_id: str, update: TermUpdate):
    """Update status or notes for a term item."""
    return {
        "updated": True,
        "item_id": item_id,
        "changes": update.model_dump(exclude_none=True),
    }
