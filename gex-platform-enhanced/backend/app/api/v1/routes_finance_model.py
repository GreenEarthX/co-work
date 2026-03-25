"""
GEX Platform — Finance Model Proxy Routes
==========================================
Proxies financial modeling requests from the platform frontend to gex_pf_engine (port 8001).

Mount in main.py:

    from app.api.v1.routes_finance_model import router as finance_model_router
    app.include_router(finance_model_router, prefix="/api/v1/finance-model", tags=["Finance Model"])

Architecture:
    Frontend (React) -> Platform Backend (8000) /api/v1/finance-model/* -> Engine (8001) /api/v1/model/*
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

MODEL_ENGINE_URL = os.getenv("GEX_ENGINE_URL", "http://localhost:8001")
ENGINE_TIMEOUT = 30.0


async def _call_model(path: str, method: str = "GET", json_data=None):
    url = f"{MODEL_ENGINE_URL}/api/v1/model{path}"
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            resp = await (client.post(url, json=json_data) if method == "POST" else client.get(url))
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Model engine error: {resp.text}")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Finance model engine unavailable (port 8001)")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Finance model engine timeout")


@router.get("/health")
async def health():
    return await _call_model("/health")


@router.post("/cfads")
async def calculate_cfads(body: dict):
    """
    Calculate Cash Flow Available for Debt Service.

    Body: { production_mtpd, offtake_price_eur_kg, subsidies?, opex_eur_kg, maintenance_capex?, period_days? }
    """
    return await _call_model("/cfads/calculate", method="POST", json_data=body)


@router.post("/lifetime")
async def model_lifetime(body: dict):
    """
    Full 15–25 year project lifetime model.

    Body: { capacity_mtpd, price_eur_kg, opex_eur_kg, total_capex,
            senior_debt_amount, interest_rate, tenor_years, operations_start_year? }
    """
    return await _call_model("/model/lifetime", method="POST", json_data=body)


@router.post("/covenants")
async def check_covenants(body: dict):
    """
    Check financial covenant compliance.

    Body: { dscr, dsra_funded, completion_guarantee, covenant_requirements }
    """
    return await _call_model("/covenants/check", method="POST", json_data=body)


@router.post("/waterfall")
async def execute_waterfall(body: dict):
    """
    Distribute CFADS across reserve accounts, debt tranches, and equity.

    Body: { cfads, senior_debt_service, junior_debt_service?, mezzanine_service?, dsra_required?, maintenance_reserve? }
    """
    return await _call_model("/waterfall/execute", method="POST", json_data=body)


@router.post("/metrics")
async def calculate_metrics(body: dict):
    """
    Calculate core project financial metrics (CFADS, DSCR, covenant status).

    Body: { revenue, opex, capex, debt_service, period }
    """
    return await _call_model("/metrics/calculate", method="POST", json_data=body)
