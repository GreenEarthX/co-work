"""
GEX Platform — Gate Registry API
=================================
Exposes the canonical gate definitions with prerequisites, phases,
and linked screens so the frontend can enforce workflow progression
without hardcoding gate knowledge.

Mount:
    from app.api.v1.routes_gate_registry import router as gate_registry_router
    app.include_router(gate_registry_router, prefix="/api/v1/gates", tags=["Gates"])
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.bankability_engine import GATE_REGISTRY, GateDefinition

router = APIRouter()


# ── Phase mapping: which project phase each gate belongs to ──

GATE_PHASE: dict[str, str] = {
    "G0_SITE_RIGHTS":              "ADVISORY",
    "G1_GRID_UTILITIES_REALITY":   "ADVISORY",
    "G2_CERTIFICATION_PATH_LOCKED":"ADVISORY",
    "G3_INPUTS_SECURED":           "ADVISORY",
    "G4_OFFTAKE_BANKABLE":         "COMMERCIAL",
    "G5_EPC_RISK_PRICED":          "STRUCTURING",
    "G6_IE_SIGNOFF":               "STRUCTURING",
    "G7_INSURANCE_BOUND":          "STRUCTURING",
    "G8_AUDIT_GRADE_MODEL":        "STRUCTURING",
    "G9_PERMITS_SAFE":             "ADVISORY",
    "G10_FINANCIAL_CLOSE_CP":      "FINANCIAL_CLOSE",
    "G11_COD_STABILIZATION":       "OPERATIONS",
}

# ── Prerequisites: which gates must be ≥ threshold before this gate is actionable ──

GATE_PREREQUISITES: dict[str, list[str]] = {
    "G0_SITE_RIGHTS":              [],
    "G1_GRID_UTILITIES_REALITY":   [],
    "G2_CERTIFICATION_PATH_LOCKED":[],
    "G3_INPUTS_SECURED":           [],
    "G4_OFFTAKE_BANKABLE":         ["G0_SITE_RIGHTS", "G1_GRID_UTILITIES_REALITY", "G3_INPUTS_SECURED"],
    "G5_EPC_RISK_PRICED":          ["G4_OFFTAKE_BANKABLE"],
    "G6_IE_SIGNOFF":               ["G5_EPC_RISK_PRICED"],
    "G7_INSURANCE_BOUND":          ["G5_EPC_RISK_PRICED"],
    "G8_AUDIT_GRADE_MODEL":        ["G6_IE_SIGNOFF"],
    "G9_PERMITS_SAFE":             [],
    "G10_FINANCIAL_CLOSE_CP":      ["G4_OFFTAKE_BANKABLE", "G5_EPC_RISK_PRICED", "G6_IE_SIGNOFF", "G7_INSURANCE_BOUND", "G8_AUDIT_GRADE_MODEL", "G9_PERMITS_SAFE"],
    "G11_COD_STABILIZATION":       ["G10_FINANCIAL_CLOSE_CP"],
}

# ── Screen linkage: which frontend routes are gated by each gate ──

GATE_SCREENS: dict[str, list[str]] = {
    "G0_SITE_RIGHTS":              ["/projects"],
    "G1_GRID_UTILITIES_REALITY":   ["/projects"],
    "G2_CERTIFICATION_PATH_LOCKED":["/cert-readiness"],
    "G3_INPUTS_SECURED":           ["/offtaker-supply"],
    "G4_OFFTAKE_BANKABLE":         ["/offtake-quality", "/term-sheet", "/contracts"],
    "G5_EPC_RISK_PRICED":          ["/capital-stack", "/finance-gaps", "/finance-instruments", "/finance-package"],
    "G6_IE_SIGNOFF":               ["/evidence-hierarchy", "/stage-gates"],
    "G7_INSURANCE_BOUND":          ["/insurance-schedule", "/insurance-coverage", "/insurance-assets"],
    "G8_AUDIT_GRADE_MODEL":        ["/dscr-sensitivity", "/covenants", "/bankability-snapshot"],
    "G9_PERMITS_SAFE":             ["/regulator-dashboard"],
    "G10_FINANCIAL_CLOSE_CP":      ["/ic-pack", "/approval-queue", "/commitment-signing", "/data-room"],
    "G11_COD_STABILIZATION":       ["/production", "/plant-data", "/capacity"],
}


class GateRegistryEntry(BaseModel):
    id: str
    name: str
    phase: str
    required_evidence: list[str]
    owners: list[str]
    prerequisites: list[str]
    linked_screens: list[str]
    unlocks_capital: list[str]
    min_completion_for_next: float


def _build_entry(gate: GateDefinition) -> GateRegistryEntry:
    return GateRegistryEntry(
        id=gate.id,
        name=gate.name,
        phase=GATE_PHASE.get(gate.id, "UNKNOWN"),
        required_evidence=gate.required_evidence,
        owners=[o.value for o in gate.owners],
        prerequisites=GATE_PREREQUISITES.get(gate.id, []),
        linked_screens=GATE_SCREENS.get(gate.id, []),
        unlocks_capital=[c.value for c in gate.unlocks_capital],
        min_completion_for_next=60.0,
    )


@router.get("/registry")
async def get_gate_registry() -> list[GateRegistryEntry]:
    """Full gate registry with prerequisites, phases, and linked screens."""
    return [_build_entry(g) for g in GATE_REGISTRY]


@router.get("/registry/{gate_id}")
async def get_gate(gate_id: str) -> GateRegistryEntry:
    """Single gate definition by ID (accepts short form like 'G4')."""
    for g in GATE_REGISTRY:
        if g.id == gate_id or g.id.startswith(gate_id + "_"):
            return _build_entry(g)
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Gate {gate_id} not found")


@router.get("/screen-gates")
async def get_screen_gate_map() -> dict[str, str]:
    """Reverse map: screen path -> gate ID that must be satisfied."""
    result: dict[str, str] = {}
    for gate_id, screens in GATE_SCREENS.items():
        for screen in screens:
            result[screen] = gate_id
    return result
