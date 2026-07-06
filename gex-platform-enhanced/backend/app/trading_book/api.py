"""
gex_platform/trading_book/api.py

FastAPI router for B1 trading book endpoints.

Mounted by the main app as:
    app.include_router(trading_book.router, prefix="/api/v1/trading-book")

The cashflow endpoint is the actual B1 unblock for gex_pf_engine —
once it's live, the DSCR heatmap and CFO Report stop citing plug numbers.

Dependencies:
    `get_db` — yields a SQLAlchemy Session. The placeholder here pulls a
    DATABASE_URL from env. In the wider gex-platform-enhanced project,
    replace with `from gex_platform.db import get_db`.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker, selectinload

from app.trading_book.cashflows import (
    CashflowProjection,
    generate_cashflows_for_project,
)
from app.trading_book.models import (
    Asset,
    Contract,
    FixedPriceContract,
    IndexHistory,
    IndexLinkedContract,
    ProjectFinanceLink,
)


# ──────────────────────────────────────────────────────────────────────
# DB dependency (placeholder — swap for project-wide get_db in gex_platform)
# ──────────────────────────────────────────────────────────────────────

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://localhost/gex",
        )
        _engine = create_engine(url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_db() -> Iterator[Session]:
    """Default DB session dependency. Override in main app via:
        app.dependency_overrides[get_db] = your_get_db
    """
    _get_engine()
    assert _SessionLocal is not None
    with _SessionLocal() as session:
        yield session


# ──────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["trading-book"])


@router.get("/health", summary="Trading book module health check")
def health() -> dict:
    return {"status": "ok", "module": "trading_book", "phase": "B1"}


@router.get(
    "/projects/{asset_id}/cashflows",
    response_model=CashflowProjection,
    summary="Project cashflow projection (B1 unblock for gex_pf_engine)",
)
def get_project_cashflows(
    asset_id: uuid.UUID,
    from_date: Optional[date] = Query(
        default=None,
        description="Start of projection window. Defaults to today.",
    ),
    to_date: Optional[date] = Query(
        default=None,
        description="End of projection window. Defaults to from_date + 20 years.",
    ),
    granularity: str = Query(default="monthly", pattern="^monthly$"),
    db: Session = Depends(get_db),
) -> CashflowProjection:
    """Return the cashflow projection for one project asset.

    For each ProjectFinanceLink on the asset, expands the linked Contract
    into monthly cashflow rows over [from_date, to_date], applying:
      - sign convention from line_item_type
      - floor/cap collar on IndexLinkedContract
      - forward-extrapolation for periods beyond IndexHistory (flagged)
      - allocation_share at the link level

    `gex_pf_engine` consumes this for DSCR rollup and the heatmap stress.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        # 20-year default window — covers most green-fuels offtake tenors.
        to_date = date(from_date.year + 20, from_date.month, from_date.day)
    if to_date < from_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="to_date must be on or after from_date",
        )

    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Fetch links + their contracts. selectinload pulls contracts in one query.
    links = db.execute(
        select(ProjectFinanceLink)
        .where(ProjectFinanceLink.project_asset_id == asset_id)
        .options(selectinload(ProjectFinanceLink.contract))
    ).scalars().all()

    # For each link, fetch the contract polymorphically (so we get the right
    # subtype) plus relevant IndexHistory if it's an IndexLinkedContract.
    triples: list[tuple[ProjectFinanceLink, Contract, list[IndexHistory]]] = []
    for link in links:
        # Reload contract polymorphically — the selectinload above gives us
        # the parent row; we need the subtype for isinstance checks.
        contract = db.get(Contract, link.contract_id)
        if contract is None:
            continue

        history: list[IndexHistory] = []
        if isinstance(contract, IndexLinkedContract):
            history = db.execute(
                select(IndexHistory)
                .where(IndexHistory.index_definition_id == contract.index_definition_id)
                .order_by(IndexHistory.observation_date)
            ).scalars().all()

        triples.append((link, contract, history))

    return generate_cashflows_for_project(
        asset=asset,
        links_with_contracts=triples,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )


@router.get(
    "/projects/{asset_id}/contracts",
    summary="List contracts attached to a project (via ProjectFinanceLink)",
)
def list_project_contracts(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lightweight listing — full contract reads via /contracts/{id}."""
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    links = db.execute(
        select(ProjectFinanceLink).where(ProjectFinanceLink.project_asset_id == asset_id)
    ).scalars().all()

    out: list[dict] = []
    for link in links:
        contract = db.get(Contract, link.contract_id)
        if contract is None:
            continue
        out.append(
            {
                "link_id": str(link.id),
                "contract_id": str(contract.id),
                "contract_number": contract.contract_number,
                "contract_type": contract.contract_type,
                "fuel_type": contract.fuel_type,
                "line_item_type": link.line_item_type.value,
                "allocation_share": str(link.allocation_share),
                "effective_date": contract.effective_date.isoformat(),
                "termination_date": contract.termination_date.isoformat(),
                "notional_quantity": str(contract.notional_quantity),
                "quantity_unit": contract.quantity_unit,
                "currency": contract.currency,
                "status": contract.status.value,
            }
        )
    return out


__all__ = ["router", "get_db"]
