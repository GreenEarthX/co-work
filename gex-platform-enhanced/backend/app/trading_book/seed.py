"""
gex_platform/trading_book/seed.py

B1 seed fixture: one realistic green-H2 project end-to-end.

Creates:
    - Asset:           Rotterdam H2 Hub Phase 1 (NL, 100 MW PEM, COD 2027-06-01)
    - Counterparties:  BP plc (offtaker), Rotterdam H2 Hub OpCo BV (supplier/SPV)
    - IndexDefinition: Argus Green H2 NWE daily (EUR/MWh)
    - IndexHistory:    30 days of synthetic observations around €95-110/MWh
    - Contract:        15-year IndexLinkedContract, BP buys 7.5M MWh total
                       (≈500k MWh/yr) from OpCo, EUR, spread €15.50/MWh,
                       collar [€80, €250]/MWh, month_avg fixing
    - ProjectFinanceLink: REVENUE for the project, 100% allocation

After seeding, GET /api/v1/trading-book/projects/{asset_id}/cashflows
should return ~180 monthly rows, with the first ~1 month using actual
IndexHistory and the rest forward-extrapolated (is_estimate=True).

Usage:
    DATABASE_URL=postgresql+psycopg://localhost/gex python -m app.trading_book.seed

Or as a function:
    from app.trading_book.seed import seed
    seed(session)
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.trading_book.models import (
    Asset,
    Base,
    Contract,
    ContractStatus,
    Counterparty,
    IndexDefinition,
    IndexHistory,
    IndexLinkedContract,
    PFLineItemType,
    ProjectFinanceLink,
)


# Reference assessment date — set to a recent fixed date so seed is reproducible.
SEED_AS_OF = date(2026, 4, 30)
HISTORY_DAYS = 30


def _make_history_values(seed_value: int = 42) -> list[Decimal]:
    """30 daily observations around €100/MWh with mild noise. Reproducible."""
    rng = random.Random(seed_value)
    base = Decimal("100.00")
    out: list[Decimal] = []
    for i in range(HISTORY_DAYS):
        # gentle sinusoid-ish drift +/- 8 EUR, plus +/- 1.5 EUR noise
        from math import sin, pi
        drift = Decimal(str(round(8 * sin(2 * pi * i / 30), 2)))
        noise = Decimal(str(round(rng.uniform(-1.5, 1.5), 2)))
        out.append(base + drift + noise)
    return out


def seed(db: Session, *, recreate: bool = False) -> dict:
    """Run the B1 seed. Returns ids of the created objects.

    If recreate=True, deletes any existing rows for the seed counterparty/asset
    names first. Otherwise raises if seed objects already exist.
    """
    # Idempotency: check for existing seed asset by name
    existing = db.execute(
        select(Asset).where(Asset.name == "Rotterdam H2 Hub Phase 1")
    ).scalar_one_or_none()
    if existing is not None:
        if not recreate:
            raise RuntimeError(
                "Seed already applied (Asset 'Rotterdam H2 Hub Phase 1' exists). "
                "Pass recreate=True to wipe and reseed."
            )
        # cascade through PFLink + Contract (FK cascades handle the rest)
        for link in db.execute(
            select(ProjectFinanceLink).where(ProjectFinanceLink.project_asset_id == existing.id)
        ).scalars().all():
            db.delete(link)
        db.flush()
        # Delete contracts that referenced this project (none directly, but clean any orphan)
        # then the asset.
        db.delete(existing)
        # Also drop seed counterparties + index if they exist
        for legal_name in ("BP plc", "Rotterdam H2 Hub OpCo BV"):
            cp = db.execute(
                select(Counterparty).where(Counterparty.legal_name == legal_name)
            ).scalar_one_or_none()
            if cp is not None:
                db.delete(cp)
        seed_idx = db.execute(
            select(IndexDefinition).where(
                IndexDefinition.provider == "Argus",
                IndexDefinition.index_code == "AGH2-NWE-DLY",
            )
        ).scalar_one_or_none()
        if seed_idx is not None:
            db.delete(seed_idx)
        db.flush()

    # ── 1. Asset ──
    asset = Asset(
        name="Rotterdam H2 Hub Phase 1",
        location="Port of Rotterdam, NL",
        country_code="NL",
        technology="PEM_ELECTROLYSIS",
        capacity_mw=Decimal("100.000"),
        cod_date=date(2027, 6, 1),
        is_active=True,
    )
    db.add(asset)

    # ── 2. Counterparties ──
    bp = Counterparty(
        legal_name="BP plc",
        lei="213800LBLHAQRPVZRC97",
        country_code="GB",
        is_active=True,
    )
    spv = Counterparty(
        legal_name="Rotterdam H2 Hub OpCo BV",
        lei=None,
        country_code="NL",
        is_active=True,
    )
    db.add_all([bp, spv])

    # ── 3. Index definition ──
    idx = IndexDefinition(
        provider="Argus",
        index_code="AGH2-NWE-DLY",
        description="Argus Green Hydrogen Northwest Europe daily assessment",
        currency="EUR",
        unit_basis="EUR/MWh",
        frequency="daily",
        is_active=True,
    )
    db.add(idx)
    db.flush()  # assign idx.id

    # ── 4. IndexHistory ──
    values = _make_history_values()
    start = SEED_AS_OF - timedelta(days=HISTORY_DAYS - 1)
    history_rows = []
    for i, v in enumerate(values):
        history_rows.append(
            IndexHistory(
                index_definition_id=idx.id,
                observation_date=start + timedelta(days=i),
                value=v,
                source_ref=f"argus-seed-{i:03d}",
            )
        )
    db.add_all(history_rows)

    # ── 5. IndexLinkedContract ──
    contract = IndexLinkedContract(
        contract_number="GEX-2026-H2-ROT-001",
        buy_side_id=bp.id if bp.id else None,
        sell_side_id=spv.id if spv.id else None,
        # ^^^ flush below assigns ids
        fuel_type="GREEN_H2",
        trade_date=date(2026, 5, 4),
        effective_date=date(2027, 6, 1),
        termination_date=date(2042, 5, 31),
        notional_quantity=Decimal("7500000"),  # 500k MWh/yr × 15 yr
        quantity_unit="MWh",
        currency="EUR",
        status=ContractStatus.COMMITTED,
        index_definition_id=idx.id,
        spread=Decimal("15.50"),
        floor=Decimal("80"),
        cap=Decimal("250"),
        fixing_rule="month_avg",
    )
    # Need counterparty ids — flush first
    db.flush()
    contract.buy_side_id = bp.id
    contract.sell_side_id = spv.id
    db.add(contract)
    db.flush()

    # ── 6. ProjectFinanceLink ──
    pf_link = ProjectFinanceLink(
        project_asset_id=asset.id,
        contract_id=contract.id,
        line_item_type=PFLineItemType.REVENUE,
        pf_engine_ref=None,
        allocation_share=Decimal("1.000000"),
        notes="B1 seed: full offtake to BP, 100% allocated to Rotterdam Phase 1",
    )
    db.add(pf_link)
    db.commit()

    return {
        "asset_id": str(asset.id),
        "counterparty_buy_side_id": str(bp.id),
        "counterparty_sell_side_id": str(spv.id),
        "index_definition_id": str(idx.id),
        "index_history_count": len(history_rows),
        "contract_id": str(contract.id),
        "pf_link_id": str(pf_link.id),
        "as_of_date": SEED_AS_OF.isoformat(),
        "history_window": [
            (SEED_AS_OF - timedelta(days=HISTORY_DAYS - 1)).isoformat(),
            SEED_AS_OF.isoformat(),
        ],
    }


def main(database_url: Optional[str] = None, recreate: bool = False) -> None:
    url = database_url or os.environ.get("DATABASE_URL")
    if url is None:
        raise SystemExit(
            "DATABASE_URL not set and no url provided. "
            "Example: DATABASE_URL=postgresql+psycopg://localhost/gex python -m app.trading_book.seed"
        )
    engine = create_engine(url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as db:
        result = seed(db, recreate=recreate)
        print("Seed complete:")
        for k, v in result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    recreate = "--recreate" in sys.argv
    main(recreate=recreate)
