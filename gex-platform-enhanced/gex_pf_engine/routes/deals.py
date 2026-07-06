"""Sprint 2 deal-compute routes. Replaces the Sprint 1 stub /deals/{id}/compute.

The endpoints in this module use the phased compute orchestrator. Sprint 3
will refactor request shape to pull inputs from the GEX platform API;
in Sprint 2 the client passes inputs in the request body for fast iteration.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from gex_pf_engine.auth.gex_jwt import (
    AuthenticatedUser,
    get_current_user_or_service,
)
from gex_pf_engine.compute import compute_deal
from gex_pf_engine.models import DealInputs, ComputeOutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deals", tags=["deals"])


class ComputeRequest(BaseModel):
    inputs: DealInputs
    scenario: str = "base"  # 'worst' | 'base' | 'best'


@router.post("/{deal_structure_id}/compute", response_model=ComputeOutput)
def compute_endpoint(
    deal_structure_id: str,
    request: ComputeRequest,
    user: AuthenticatedUser = Depends(get_current_user_or_service),
) -> ComputeOutput:
    """Run the phased compute on a deal structure.

    Access model (multi-party, not single-owner): a direct end-user token must
    match the deal owner (defence-in-depth over RLS). A service-role token — the
    GEX platform backend, which enforces ABAC party-to-deal itself — may compute
    on behalf of any authorized participant (lender, IE, co-sponsor), which the
    old owner-only check made impossible."""
    if request.inputs.deal.id != deal_structure_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"deal_structure_id mismatch: URL={deal_structure_id} "
                f"vs body={request.inputs.deal.id}"
            ),
        )

    if not user.is_service_role and request.inputs.deal.user_id != user.user_id:
        # Defence-in-depth — RLS already prevents reading another user's deal,
        # but the engine ALSO refuses if the body claims a different owner.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_id in deal does not match authenticated user "
                   "(non-owner parties access deals via the GEX backend, "
                   "which enforces ABAC party-to-deal)",
        )

    logger.info(
        "compute deal=%s user=%s scenario=%s",
        deal_structure_id, user.user_id, request.scenario,
    )
    output = compute_deal(request.inputs)
    return output


# Sprint 3 will add:
#   POST /deals/{id}/optimize       — scipy-based debt-stack optimisation
#   POST /deals/{id}/sensitivity    — tornado / scenario sweep
#   GET  /prices/curves             — Gabillon two-factor curve service
