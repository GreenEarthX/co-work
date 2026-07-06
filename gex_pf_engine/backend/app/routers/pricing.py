"""Pricing endpoints for Gabillon curves and offtake contracts."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.pricing.gabillon.schemas import (
    CalibrationResponse,
    ForecastConeResponse,
    GabillonConfig,
    PricingCurveRequest,
    PricingCurveResponse,
)
from app.pricing.gabillon.service import GabillonService
from app.pricing.offtake.schemas import (
    GreenmeshRollupResponse,
    OfftakeConfig,
    OfftakeValueResponse,
    RollupRequest,
)
from app.pricing.offtake.service import OfftakeService

router = APIRouter(prefix="/pf", tags=["Gabillon — Project Calibration & Offtake (per project)"])

curve_service = GabillonService()
offtake_service = OfftakeService(curve_service)


@router.post(
    "/curve/calibrate",
    response_model=CalibrationResponse,
    summary="Calibrate a project-scoped Gabillon curve",
)
def calibrate_curve(payload: GabillonConfig) -> dict[str, Any]:
    """
    Fit Gabillon parameters for ONE project against its fundamental anchor
    (LCOF from the financial model), not against a molecule market.

    The result is stored in the project's calibration memory and stamped
    with provenance (`free_params`, `target_source`, `warm_started`, `seed`,
    `provenance_note`) so every later curve can be traced to the calibration
    run that produced it. Re-calibrating appends to the audit history —
    see `GET /pf/curve/{project_id}/memory`.
    """
    return curve_service.calibrate(payload.engine_config())


@router.post(
    "/curve/pricing",
    response_model=PricingCurveResponse,
    summary="Q-measure pricing curve (forwards at requested tenors)",
)
def pricing_curve(payload: PricingCurveRequest) -> dict[str, Any]:
    """
    Generate the risk-neutral (Q-measure) forward curve for a calibrated
    project at the requested tenors `taus` (in YEARS, default
    0.25–10y). Use this curve to price contracts.

    Returns 409 if the project has not been calibrated yet — call
    `POST /pf/curve/calibrate` first.
    """
    try:
        return curve_service.pricing_curve(payload.engine_config(), payload.taus)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/curve/forecast",
    response_model=ForecastConeResponse,
    summary="P-measure forecast cone (real-world quantiles)",
)
def forecast_cone(payload: GabillonConfig) -> dict[str, Any]:
    """
    Generate the real-world (P-measure) price forecast cone: mean path plus
    quantile bands (`quantile_levels` × `cone`) per tenor. Use for risk and
    scenario views — NOT for pricing (use `/pf/curve/pricing` for that).

    Returns 409 if the project has not been calibrated yet.
    """
    try:
        return curve_service.forecast_cone(payload.engine_config())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/curve/{project_id}/memory",
    summary="Calibration audit history for a project",
)
def calibration_memory(project_id: str) -> dict[str, Any]:
    """
    Full calibration history for the project — one entry per calibration run
    with parameters, fit quality, and provenance. This is the audit trail
    that answers "which calibration produced the curve this deal was
    priced on?".
    """
    return {"project_id": project_id, "history": curve_service.history(project_id)}


@router.post(
    "/offtake/value",
    response_model=OfftakeValueResponse,
    summary="Value an offtake contract against the project curve",
)
def value_offtake(payload: OfftakeConfig) -> dict[str, Any]:
    """
    Mark an offtake contract (volumes, fixed/indexed price terms) against the
    project's calibrated Q-curve. Returns contract value and per-period
    detail. 409 if the underlying curve is not calibrated.
    """
    try:
        return offtake_service.value_contract(payload.engine_config(), payload.curve_config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/offtake/rollup",
    response_model=GreenmeshRollupResponse,
    summary="GreenMesh portfolio rollup of offtake contracts",
)
def greenmesh_rollup(payload: RollupRequest) -> dict[str, Any]:
    """
    Aggregate multiple offtake contracts into a portfolio (GreenMesh) view:
    template terms applied across `contracts`, valued on the same project
    curve, with portfolio-level totals. 409 if the curve is not calibrated.
    """
    try:
        return offtake_service.greenmesh_rollup(
            payload.template_config(),
            payload.contracts,
            payload.curve_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
