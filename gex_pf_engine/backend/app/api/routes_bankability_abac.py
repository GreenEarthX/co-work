"""
ABAC-Driven Gate Evaluation — PF Engine Adapter
=================================================
Replaces the hardcoded PERSONA_GATES dict with a dynamic approach:
the Platform computes visible_gates via ABAC and passes them to this endpoint.

Location: gex_pf_engine/backend/app/api/routes_bankability_abac.py

This is ADDITIVE — the existing routes_bankability.py persona endpoints
continue to work during migration. New ABAC endpoint runs in parallel.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from app.core.bankability_engine import evaluate, get_gates, GATES

router = APIRouter()


class ABACEvaluationRequest(BaseModel):
    """
    ABAC-driven evaluation request.
    The Platform computes visible_gates from user attributes (ABAC Rule 2)
    and passes them here. The PF Engine no longer needs to know about personas.
    """
    project_id: str
    evidence: list[dict]
    visible_gates: List[str]  # Computed by Platform ABAC, e.g. ["G0_SITE_RIGHTS", "G4_OFFTAKE"]
    previous_state: Optional[str] = None
    requesting_company_id: Optional[str] = None  # For audit trail
    requesting_actor_type: Optional[str] = None  # For audit trail


@router.post("/evaluate/abac")
async def evaluate_abac(request: ABACEvaluationRequest):
    """
    Evaluate bankability with ABAC-filtered gate visibility.

    Instead of:
        POST /evaluate/persona  { persona: "FINANCE" }  → hardcoded gates

    Now:
        POST /evaluate/abac  { visible_gates: ["G4", "G6", "G7", "G8", "G10"] }
        → gates computed by Platform ABAC policy, not by PF Engine

    Benefits:
        - New actor types added via ABAC policy rules, not PF Engine code
        - BP can see PRODUCER gates on Project A and OFFTAKER gates on Project B
        - Same endpoint, different visible_gates per request
    """
    # Run full evaluation first
    full_result = evaluate(
        project_id=request.project_id,
        evidence=request.evidence,
        previous_state=request.previous_state,
    )

    # Validate requested gates exist
    valid_gate_ids = {g["gate_id"] for g in GATES}
    requested_gates = set(request.visible_gates)
    invalid_gates = requested_gates - valid_gate_ids
    if invalid_gates:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid gate IDs: {sorted(invalid_gates)}. Valid: {sorted(valid_gate_ids)}",
        )

    # Filter to visible gates only
    full_result["gate_evaluations"] = [
        g for g in full_result["gate_evaluations"]
        if g["gate_id"] in requested_gates
    ]

    # Filter capital unlocks to only those gated by visible gates
    full_result["capital_unlocks"] = [
        cu for cu in full_result["capital_unlocks"]
        if any(gg in requested_gates for gg in cu["gating_gates"])
    ]

    # Add ABAC metadata
    full_result["abac"] = {
        "visible_gates": sorted(request.visible_gates),
        "total_gates_in_system": len(GATES),
        "gates_visible_to_user": len(request.visible_gates),
        "requesting_company_id": request.requesting_company_id,
        "requesting_actor_type": request.requesting_actor_type,
    }

    return full_result


@router.get("/gates/for-actor/{actor_type}")
async def get_gates_for_actor(actor_type: str):
    """
    Utility: return which gates a given actor type can see.
    This is a READ-ONLY reference — the actual access decision
    is made by the Platform's ABAC engine, not by this endpoint.

    Useful for:
    - Frontend to pre-filter UI before calling evaluate/abac
    - CISO dashboard to display the gate visibility matrix
    - Testing and debugging ABAC configuration
    """
    from app.core.bankability_engine import PERSONA_GATES

    # First check legacy persona mapping
    if actor_type.upper() in PERSONA_GATES:
        return {
            "actor_type": actor_type.upper(),
            "visible_gates": PERSONA_GATES[actor_type.upper()],
            "source": "legacy_persona_mapping",
            "note": "In production, visible_gates are computed by Platform ABAC, not this endpoint.",
        }

    # Extended mapping for the 11 actor types (matches ABAC GATE_VISIBILITY)
    EXTENDED_GATE_VISIBILITY = {
        "PRODUCER": ["G0_SITE_RIGHTS", "G1_GRID_WATER", "G3_FEEDSTOCK_LOGISTICS",
                     "G5_EPC", "G9_PERMITS", "G11_COD"],
        "OFFTAKER": ["G4_OFFTAKE"],
        "COMMERCIAL_BANKER": ["G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE",
                              "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE"],
        "DFI": ["G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE",
                "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE"],
        "INSURER": ["G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE"],
        "REGULATOR": ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
        "GOV_AGENCY": [g["gate_id"] for g in get_gates()],  # All gates
        "CERTIFIER": ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
        "EPC_CONTRACTOR": ["G5_EPC", "G11_COD"],
        "LOGISTICS_OPERATOR": ["G3_FEEDSTOCK_LOGISTICS"],
        "TECHNOLOGY_PROVIDER": ["G5_EPC", "G11_COD"],
        "EXECUTIVE": [g["gate_id"] for g in get_gates()],  # All gates
    }

    actor_upper = actor_type.upper()
    if actor_upper in EXTENDED_GATE_VISIBILITY:
        return {
            "actor_type": actor_upper,
            "visible_gates": EXTENDED_GATE_VISIBILITY[actor_upper],
            "source": "extended_abac_mapping",
        }

    raise HTTPException(
        status_code=404,
        detail=f"Unknown actor type: {actor_type}. "
               f"Valid: {sorted(EXTENDED_GATE_VISIBILITY.keys())}",
    )
