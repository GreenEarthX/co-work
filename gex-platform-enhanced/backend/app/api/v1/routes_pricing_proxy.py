"""
GEX Platform — Pricing Proxy Routes
====================================
Proxies molecule pricing requests from the platform frontend to gex_pf_engine (port 8001).

Frontend pricingAPI calls /api/v1/pricing/* → this proxy → Engine /api/v1/pricing/*

Mount in main.py:
    from app.api.v1.routes_pricing_proxy import router as pricing_proxy_router
    app.include_router(pricing_proxy_router, prefix="/api/v1/pricing", tags=["Pricing Proxy"])
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.routes_entitlements import require_finance_entitlement

router = APIRouter()

ENGINE_URL = os.getenv("PF_ENGINE_URL", os.getenv("GEX_ENGINE_URL", "http://localhost:8001"))
ENGINE_TIMEOUT = 30.0


async def _call_engine(path: str, method: str = "GET", json_data=None):
    url = f"{ENGINE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            if method == "POST":
                resp = await client.post(url, json=json_data)
            else:
                resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Pricing engine error: {resp.text}")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Pricing engine unavailable (port 8001)")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Pricing engine timeout")


async def _call_pricing(path: str, method: str = "GET", json_data=None):
    return await _call_engine(f"/api/v1/pricing{path}", method=method, json_data=json_data)


async def _call_pf(path: str, json_data=None):
    result = await _call_engine(f"/pf{path}", method="POST", json_data=json_data)
    return _with_verification(result)


def _with_verification(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    provenance = result.get("provenance")
    if isinstance(provenance, dict):
        result["verification"] = {
            key: _verification_for_status(key, value)
            for key, value in provenance.items()
            if not key.startswith("_")
        }
    if "fit" in result:
        result["curve_input_contradiction"] = _curve_inputs_inconsistent(result["fit"])
    return result


def _verification_for_status(key: str, status: str) -> dict[str, str]:
    if status == "calibrated":
        return {
            "state": "CONFIRMED",
            "banner": "LCOF-anchored, not market",
        }
    if status == "contract_terms":
        return {
            "state": "SUBMITTED",
            "banner": "Contract term submitted; confirm against uploaded term sheet",
        }
    if status in {"assumed", "input"}:
        return {
            "state": "UNVERIFIED" if status == "assumed" else "SUBMITTED",
            "banner": f"{key} is {status}",
        }
    return {"state": "SUBMITTED", "banner": f"{key} provenance: {status}"}


def _curve_inputs_inconsistent(fit: dict[str, Any]) -> bool:
    return (
        fit.get("r2_vs_fundamental", 0) < 0
        or bool(fit.get("params_on_bound"))
    )


async def _emit_calibration_event(request: Request, project_id: str, result: dict[str, Any]) -> None:
    bus = getattr(request.app.state, "event_bus", None)
    if not bus:
        return
    try:
        await bus.publish(
            event_type="pricing.calibration_completed",
            project_id=project_id,
            payload={
                "fit": result.get("fit", {}),
                "curve_input_contradiction": result.get("curve_input_contradiction", False),
                "progress": "completed",
            },
        )
    except Exception:
        return


@router.get("/molecules")
async def list_molecules():
    """Available molecules for pricing."""
    return await _call_pricing("/molecules")


@router.get("/spot/{molecule}")
async def spot_price(molecule: str):
    """Current spot price for a molecule."""
    return await _call_pricing(f"/spot/{molecule}")


@router.get("/term-curve/{molecule}")
async def term_curve(molecule: str):
    """Gabillon term structure curve for a molecule."""
    return await _call_pricing(f"/term-curve/{molecule}")


@router.post(
    "/decomposition",
    dependencies=[Depends(require_finance_entitlement("price_decomposition"))],
)
async def price_decomposition(body: dict, project_id: str | None = Query(default=None)):
    """
    Decompose a delivered price into cost components (capex, opex, financing,
    insurance, certification, margin) for a single tenor.

    RESTRICTED (Ticket 1a): the full Gabillon decomposition exposes model
    internals (risk premium, volatility, basis, margin). Requires a finance
    role or project-scoped FINANCE_REVIEW; `project_id` is mandatory for the
    project-scoped check. Unauthorized callers receive 403.
    """
    return await _call_pricing("/decomposition", method="POST", json_data=body)


@router.post(
    "/decomposition/multi-tenor",
    dependencies=[Depends(require_finance_entitlement("price_decomposition_multi_tenor"))],
)
async def price_decomposition_multi_tenor(body: dict, project_id: str | None = Query(default=None)):
    """
    Multi-tenor price decomposition (6M, 1Y, 3Y, 5Y, 10Y, 15Y). RESTRICTED — see
    /decomposition. Requires finance role or project-scoped FINANCE_REVIEW.
    """
    return await _call_pricing("/decomposition/multi-tenor", method="POST", json_data=body)


@router.post("/curve/calibrate")
@router.post("/pf/curve/calibrate")
async def calibrate_curve(body: dict, request: Request):
    """Proxy Gabillon calibration to PF engine and emit pricing progress."""
    result = await _call_pf("/curve/calibrate", json_data=body)
    await _emit_calibration_event(request, body.get("project_id", ""), result)
    return result


@router.post("/curve/pricing")
@router.post("/pf/curve/pricing")
async def pricing_curve(body: dict):
    """Proxy Q pricing curve generation to PF engine."""
    return await _call_pf("/curve/pricing", json_data=body)


@router.post("/curve/forecast")
@router.post("/pf/curve/forecast")
async def forecast_cone(body: dict):
    """Proxy P forecast cone generation to PF engine."""
    return await _call_pf("/curve/forecast", json_data=body)


@router.get("/curve/{project_id}/memory")
@router.get("/pf/curve/{project_id}/memory")
async def calibration_memory(project_id: str):
    """Proxy project-scoped calibration audit history."""
    return await _call_engine(f"/pf/curve/{project_id}/memory")


@router.post("/offtake/value")
@router.post("/pf/offtake/value")
async def offtake_value(body: dict):
    """Proxy offtake valuation to PF engine."""
    return await _call_pf("/offtake/value", json_data=body)


@router.post("/offtake/rollup")
@router.post("/pf/offtake/rollup")
async def greenmesh_rollup(body: dict):
    """Proxy GreenMesh rollup to PF engine."""
    return await _call_pf("/offtake/rollup", json_data=body)
