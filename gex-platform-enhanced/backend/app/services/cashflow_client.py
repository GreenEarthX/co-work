"""
Cashflow Consumer — HTTP client for the B1 trading book cashflow endpoint.

Location: backend/app/services/cashflow_client.py

Pulls per-project cashflow projections from the trading book API and
transforms them into the CFADS / DSCR structure that gex_pf_engine needs
for the heatmap stress and CFO Report.

Architecture:
    DSCRHeatmap.tsx  →  /api/v1/finance-model/dscr-heatmap/{asset_id}
                           ↓
                    routes_finance_model.py (proxy)
                           ↓
                    CashflowClient.fetch_projection()
                        → GET /api/v1/trading-book/projects/{asset_id}/cashflows
                           ↓
                    DSCRAggregator.compute()
                        → CFADS per period, DSCR per period, heatmap grid
                           ↓
                    response to frontend

NOTE on DEBT_SERVICE and CAPEX in PFLineItemType:
    These are NOT trading cashflows. They exist because the project cashflow
    table aggregates ALL sources of cash for DSCR computation. A lender facility
    (debt_service) or EPC milestone payment (capex) shares the same period grid
    as offtake revenue so the engine can compute net cash and DSCR in one pass.
    The trading book proper only originates revenue and opex lines from actual
    Buy/Sell contracts for physical tokenised products and their derivatives.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("gex.cashflow_client")

TRADING_BOOK_URL = os.getenv(
    "GEX_TRADING_BOOK_URL",
    "http://localhost:8000/api/v1/trading-book",
)
# When trading_book is co-located on the platform backend (port 8000),
# this client calls self. If trading_book is later split into a separate
# service, update GEX_TRADING_BOOK_URL to point to that service.
REQUEST_TIMEOUT = 30.0


# ─────────────────────────────────────────────────────────────────
# Response models (mirror the trading book's CashflowProjection)
# ─────────────────────────────────────────────────────────────────


class CashflowRowDTO(BaseModel):
    period_start: date
    period_end: date
    line_item_type: str
    contract_id: str
    contract_number: str
    currency: str
    quantity: Decimal
    quantity_unit: str
    price: Optional[Decimal]
    gross_amount: Optional[Decimal]
    sign: int
    allocation_share: Decimal
    allocated_amount: Optional[Decimal]
    is_estimate: bool
    notes: Optional[str] = None


class PeriodSummaryDTO(BaseModel):
    period_start: date
    period_end: date
    by_line_item: dict[str, Decimal]
    net: Decimal


class CashflowProjectionDTO(BaseModel):
    project_asset_id: str
    project_name: str
    from_date: date
    to_date: date
    granularity: str
    rows: list[CashflowRowDTO]
    summary_by_line_item: dict[str, Decimal] = Field(default_factory=dict)
    summary_by_period: list[PeriodSummaryDTO] = Field(default_factory=list)
    has_estimates: bool = False
    estimate_period_count: int = 0


# ─────────────────────────────────────────────────────────────────
# HTTP Client
# ─────────────────────────────────────────────────────────────────


class CashflowClient:
    """Async HTTP client that fetches cashflow projections from the trading book."""

    def __init__(self, base_url: str = TRADING_BOOK_URL):
        self.base_url = base_url

    async def fetch_projection(
        self,
        asset_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        granularity: str = "monthly",
    ) -> CashflowProjectionDTO:
        params: dict = {"granularity": granularity}
        if from_date:
            params["from_date"] = from_date.isoformat()
        if to_date:
            params["to_date"] = to_date.isoformat()

        url = f"{self.base_url}/projects/{asset_id}/cashflows"
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return CashflowProjectionDTO(**resp.json())
            except httpx.ConnectError:
                logger.error("Trading book unreachable at %s", self.base_url)
                raise
            except httpx.HTTPStatusError as e:
                logger.error("Trading book HTTP %s: %s", e.response.status_code, e.response.text[:200])
                raise

    async def fetch_contracts(self, asset_id: str) -> list[dict]:
        url = f"{self.base_url}/projects/{asset_id}/contracts"
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
            except Exception:
                return {"status": "unreachable"}


cashflow_client = CashflowClient()
