"""
GEX Engine — Bankability Routes
=================================
Mount in gex_pf_engine/backend/app/main.py:

    from app.api.routes_bankability import router as bankability_router
    app.include_router(bankability_router, prefix="/api/v1/bankability", tags=["Bankability"])

These routes are called by the platform proxy (port 8000),
NOT directly by the frontend.
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

# Import from wherever bankability_engine.py lands in your project.
# Adjust this import path to match your engine structure:
try:
    from app.core.bankability_engine import evaluate, evaluate_for_persona, get_gates, get_rules
except ImportError:
    # Fallback: engine file in same directory or parent
    try:
        from core.bankability_engine import evaluate, evaluate_for_persona, get_gates, get_rules
    except ImportError:
        from bankability_engine import evaluate, evaluate_for_persona, get_gates, get_rules

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class EvaluateRequest(BaseModel):
    project_id: str = "default"
    evidence: list[dict] = []
    previous_state: Optional[str] = None

class PersonaEvaluateRequest(BaseModel):
    project_id: str = "default"
    evidence: list[dict] = []
    persona: str = "EXECUTIVE"
    previous_state: Optional[str] = None

class RegressionCheckRequest(BaseModel):
    project_id: str = "default"
    evidence: list[dict] = []
    previous_state: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/evaluate")
async def evaluate_endpoint(request: EvaluateRequest):
    """Full bankability evaluation. Called by platform proxy."""
    return evaluate(
        project_id=request.project_id,
        evidence=request.evidence,
        previous_state=request.previous_state,
    )


@router.post("/evaluate/persona")
async def evaluate_persona_endpoint(request: PersonaEvaluateRequest):
    """Persona-scoped evaluation. Called by platform proxy."""
    return evaluate_for_persona(
        project_id=request.project_id,
        evidence=request.evidence,
        persona=request.persona,
        previous_state=request.previous_state,
    )


@router.get("/gates")
async def gates_endpoint():
    """Return all 12 gate definitions."""
    return get_gates()


@router.get("/rules")
async def rules_endpoint():
    """Return state machine rules."""
    return get_rules()


@router.post("/regression/check")
async def regression_check_endpoint(request: RegressionCheckRequest):
    """Explicit regression check."""
    snapshot = evaluate(
        project_id=request.project_id,
        evidence=request.evidence,
        previous_state=request.previous_state,
    )
    return {
        "project_id": request.project_id,
        "regression": snapshot.get("regression"),
        "current_state": snapshot["current_state"],
        "previous_state": request.previous_state,
    }


@router.get("/health")
async def health_endpoint():
    """Engine health check."""
    return {"status": "healthy", "engine": "bankability", "gates": 12}
