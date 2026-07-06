"""TEA compute routes (port 8002). Upstream of the PF engine (port 8001).

The PF engine reserves /deals/{id}/sensitivity for Sprint 3 — its cost axis
should fan out to POST /tea/sensitivity here rather than re-implementing
tornado/Monte-Carlo.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from tea_engine.auth.gex_jwt import AuthenticatedUser, get_current_user
from tea_engine.compute import run_sensitivity, run_tea
from tea_engine.models import TEAComputeRequest, TEAResult, TEASensitivityResult
import tea_engine.regimes as regimes
from tea_engine.lca import LCAInput, LCAResult, compute_lca

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tea", tags=["TEA Engine"])


@router.post("/compute", response_model=TEAResult)
def compute(
    request: TEAComputeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> TEAResult:
    """Run techno-economics for a pathway's engineering layer.

    Returns a PROVISIONAL cost basis (model_claim_state='submitted') plus the
    evidence entry the backend should append to the ledger. It does NOT promote
    the result to a verified model_base_case.
    """
    logger.info("tea/compute project=%s pathway=%s user=%s",
                request.project_id, request.pathway_id, user.user_id)
    try:
        return run_tea(request)
    except ValueError as e:        # undefined / scaffold-only process function
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


@router.get("/regime/{fuel_id}")
def regime_for(fuel_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """The regulatory-regime fork for a molecule: certification gate (required vs
    waived claims), GHG method, and subsidy — keyed on the fuel's pathway_class.
    Consumed by the certification-gate evaluator, the GHG engine, and the capital
    layer so all three fork on one source of truth."""
    try:
        return {"regime": regimes.as_dict(regimes.regime_for_fuel(fuel_id)),
                "certification_gate": regimes.certification_gate(fuel_id)}
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.get("/regimes")
def list_regimes(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """All regulatory regimes GEX recognises (RFNBO / advanced biofuel / crop / RCF / low-carbon)."""
    return {pc: regimes.as_dict(r) for pc, r in regimes.REGIMES.items()}


@router.post("/lca/compute", response_model=LCAResult)
def lca_compute(inp: LCAInput, user: AuthenticatedUser = Depends(get_current_user)) -> LCAResult:
    """Compute regime-correct GHG (gCO2e/MJ + saving vs fossil) for a molecule.
    If ghg_method is omitted it is auto-selected from the fuel's pathway_class
    (RFNBO→Annex VI, biofuel→Annex V). Produces the g_co2e_per_mj and ghg_saving
    claims the certification gate checks — regime → LCA method → GHG claim → gate."""
    if not inp.ghg_method:
        inp.ghg_method = regimes.ghg_method_key(regimes.regime_for_fuel(inp.fuel_id).pathway_class)
    try:
        return compute_lca(inp)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.post("/certification-gate/{fuel_id}")
def certification_gate_eval(
    fuel_id: str,
    claim_states: dict[str, str],
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """ENFORCE the regime fork: given the project's {claim_type: state}, decide
    whether the certification gate (G2/G6) is open for this fuel's pathway_class.
    RFNBO checks additionality/temporal/geo/rfnbo_issued; a biofuel checks
    feedstock_sustainability/annex_ix/land_criteria/ghg_saving — each waiving the
    other's claims. Body: {"additionality_passed":"verified", ...}."""
    try:
        return regimes.evaluate_certification_gate(fuel_id, claim_states)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post("/sensitivity", response_model=TEASensitivityResult)
def sensitivity(
    request: TEAComputeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> TEASensitivityResult:
    """One-way tornado over the load-bearing economic drivers."""
    logger.info("tea/sensitivity project=%s user=%s", request.project_id, user.user_id)
    try:
        return run_sensitivity(request)
    except ValueError as e:        # undefined / scaffold-only process function
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
