"""
gex_platform/trading_book/models.py

B1 (Bankability Phase 1) trading book — SQLAlchemy 2.0 ORM models.

Five conceptual entities (8 tables) on the critical path for
Snapshot + DSCR Heatmap + CFO Report:

    1. Asset                  - the project being financed
    2. Counterparty           - offtaker / supplier legal entities
    3. IndexDefinition + IndexHistory
    4. Contract (FixedPriceContract | IndexLinkedContract)  via JTI
    5. ProjectFinanceLink     - bridge to gex_pf_engine

Out of scope for B1 (lands in B2/B3):
    - Physical Delivery / Route / TransportMode
    - Flow hierarchy (PhysicalFuelFlow / FixedCashFlow / FloatCashFlow)
    - Order / Account spot-trade overlay
    - ABAC/SoD/DRPL/WAE enforcement (status field is in place; chain hooks later)
    - CashflowSchedule for amortizing / step-up / take-or-pay structures
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Declarative base for trading_book models.

    NOTE: if gex_platform already exposes a project-wide DeclarativeBase,
    swap this for `from gex_platform.db import Base` so all migrations share
    a single MetaData. Kept local here to make the file self-contained.
    """
    pass


# ──────────────────────────────────────────────────────────────────────
# Enums (DB-enforced)
# ──────────────────────────────────────────────────────────────────────


class ContractStatus(str, enum.Enum):
    """Simplified lifecycle for B1.

    DECISION (override-candidate): kept to 5 states for B1. The full seven-step
    decision chain (ABAC → SoD → DRPL → WAE → CSS → DB Write → Event Bus)
    lands in B3; at that point a row only persists with status='committed'
    after the chain completes, and intermediate states (abac_passed,
    sod_pending, sod_approved, drpl_validated, wae_signed) become
    additional values here.
    """
    DRAFT = "draft"
    PROPOSED = "proposed"
    COMMITTED = "committed"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class PFLineItemType(str, enum.Enum):
    """How a contract's cashflows roll up into a project's financial model.

    REVENUE and OPEX originate from actual Buy/Sell contracts in the trading
    book (physical tokenised products + derivatives).

    DEBT_SERVICE and CAPEX are NOT trading cashflows. They exist so that
    non-trading cashflow sources (lender facilities, EPC milestone payments)
    can share the same period grid for DSCR computation. The DSCR aggregator
    needs all four line types in one pass to compute net cash available for
    debt service.
    """
    REVENUE = "revenue"
    OPEX = "opex"
    DEBT_SERVICE = "debt_service"
    CAPEX = "capex"


# ──────────────────────────────────────────────────────────────────────
# Asset
# ──────────────────────────────────────────────────────────────────────


class Asset(Base):
    """A producing facility / project being financed.

    Examples: a 100 MW PEM electrolyzer project in Rotterdam, an e-methanol
    plant in Spain, a green-ammonia bunker site in Singapore.

    NEW vs the 2019 PDF: this entity didn't exist in the freight book because
    containers are fungible; for green molecules the producing facility
    determines GHG intensity, certification path, and which project's debt
    service a cashflow line ultimately funds. This is the anchor entity for
    B1 — every DSCR rollup starts from an Asset.
    """
    __tablename__ = "tb_asset"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    # ^^^ ISO 3166-1 alpha-2. DECISION: stored uppercase, validated at
    # Pydantic layer; not FK'd to a country reference table.

    technology: Mapped[str] = mapped_column(String(100), nullable=False)
    # ^^^ DECISION (override-candidate): free string, not an enum.
    # Tech taxonomy is evolving (PEM, AEM, SOEC, alkaline, biomass-to-liquid,
    # power-to-methanol, Haber-Bosch variants). Validate at Pydantic layer
    # against a known-list; refactor to a ref table in B2 if reporting
    # needs a controlled vocabulary.

    capacity_mw: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    cod_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # ^^^ Commercial operations date. Nullable for pre-FID projects.

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    pf_links: Mapped[List["ProjectFinanceLink"]] = relationship(
        back_populates="project_asset", cascade="all, delete-orphan"
    )
    # Convenience: Asset.contracts traverses the link table.
    contracts: AssociationProxy[List["Contract"]] = association_proxy(
        "pf_links", "contract"
    )


# ──────────────────────────────────────────────────────────────────────
# Counterparty
# ──────────────────────────────────────────────────────────────────────


class Counterparty(Base):
    """Legal entity that can sit on either side of a contract.

    Examples: BP plc, TOTSA, Siemens Energy, an SPV.

    DECISION (override-candidate): role (offtaker / supplier / lender / EPC)
    is NOT stored on Counterparty. The same legal entity can be offtaker on
    one contract and supplier on another. Role is implicit from buy_side /
    sell_side on Contract, and from line_item_type on ProjectFinanceLink.
    """
    __tablename__ = "tb_counterparty"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    lei: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True)
    # ^^^ ISO 17442 Legal Entity Identifier. Nullable: SPVs and small
    # entities may not have one.

    country_code: Mapped[str] = mapped_column(String(2), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ──────────────────────────────────────────────────────────────────────
# Index layer
# ──────────────────────────────────────────────────────────────────────


class IndexDefinition(Base):
    """A price index used by floating-rate contracts.

    Provider list is deliberately open per spec — Argus, Platts, ICIS, OPIS,
    EEX, bilateral assessments, etc. are all valid. Validation lives at the
    Pydantic layer (advisory, not blocking).
    """
    __tablename__ = "tb_index_definition"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # ^^^ DECISION (per spec): non-exhaustive list, no enum, no FK to
    # provider ref table. App-layer warns on unknown providers but accepts.

    index_code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    # ^^^ DECISION (override-candidate): stored as a single string
    # ("EUR/MWh", "USD/t"). If the engine needs to do unit arithmetic across
    # contracts later, refactor to (currency, quantity_unit) pair in B2.

    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    history: Mapped[List["IndexHistory"]] = relationship(
        back_populates="index_definition", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("provider", "index_code", name="uq_index_provider_code"),
    )


class IndexHistory(Base):
    """One observation of an index value at a given date.

    `ingested_at` is intentionally separate from `observation_date` for audit:
    the observation belongs to a business day, but the row was written at a
    real wall-clock time. Future B3 audit triggers will rely on this split.
    """
    __tablename__ = "tb_index_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4
    )
    index_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("tb_index_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # ^^^ Provider's internal tick / publication ID. Audit traceability.

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    index_definition: Mapped["IndexDefinition"] = relationship(back_populates="history")

    __table_args__ = (
        UniqueConstraint(
            "index_definition_id", "observation_date", name="uq_idx_hist_def_date"
        ),
        Index("ix_idx_hist_obs_date", "observation_date"),
    )


# ──────────────────────────────────────────────────────────────────────
# Contract layer (Joined-Table Inheritance)
# ──────────────────────────────────────────────────────────────────────


class Contract(Base):
    """Abstract base for green-fuel contracts.

    JTI: tb_contract holds shared columns; tb_contract_fixed_price and
    tb_contract_index_linked hold subtype-specific columns and join on PK.
    Discriminator: `contract_type` ("fixed_price" | "index_linked").

    NOVATION (B2/B3 scope): an offtake novated to a third party (A→B to A→C)
    needs trade ledger recognition. B1 only has buy_side/sell_side as FKs.
    B2 will add: (1) status=TERMINATED on original, (2) new contract with
    incoming counterparty, (3) NovationChain audit record linking them.

    DECISION (override-candidate): no direct project_asset_id on Contract.
    A contract is just a contract; project-finance allocation is a SEPARATE
    concern handled by ProjectFinanceLink. This keeps paper hedges (with no
    project link) and portfolio allocations (one contract → multiple projects
    in B2) clean.
    """
    __tablename__ = "tb_contract"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4
    )
    contract_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # ^^^ Human-readable identifier (e.g. "GEX-2026-NH3-001"). App layer
    # generates; uniqueness enforced at DB.

    buy_side_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("tb_counterparty.id"), nullable=False
    )
    sell_side_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("tb_counterparty.id"), nullable=False
    )

    fuel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # ^^^ DECISION (override-candidate): free string, validated at Pydantic
    # layer. e.g. "GREEN_H2", "GREEN_NH3", "ESAF", "EMETHANOL". Not an enum
    # because the green-fuels taxonomy is still settling (e- vs bio- vs
    # blue-, certification variants).

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date] = mapped_column(Date, nullable=False)
    # ^^^ Three dates, not one. Trade date = when agreed; effective date =
    # when delivery/cashflow obligations start; termination date = when they
    # end. The 2019 PDF only had `time` — that was a known weakness.

    notional_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(10), nullable=False)
    # ^^^ "MWh", "GWh", "t", "kt", "m3". Validated at Pydantic.
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus, name="contract_status_enum"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )

    contract_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # ^^^ JTI discriminator. Set automatically by polymorphic_identity.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    buy_side: Mapped["Counterparty"] = relationship(foreign_keys=[buy_side_id])
    sell_side: Mapped["Counterparty"] = relationship(foreign_keys=[sell_side_id])
    pf_links: Mapped[List["ProjectFinanceLink"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )

    __mapper_args__ = {
        "polymorphic_on": "contract_type",
        "polymorphic_identity": "contract",
    }

    __table_args__ = (
        Index("ix_contract_status", "status"),
        Index("ix_contract_termination", "termination_date"),
        Index("ix_contract_buy_side", "buy_side_id"),
        Index("ix_contract_sell_side", "sell_side_id"),
    )


class FixedPriceContract(Contract):
    """Contract with a fixed price per quantity_unit, for the whole tenor."""
    __tablename__ = "tb_contract_fixed_price"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("tb_contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fixed_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price_basis: Mapped[str] = mapped_column(
        String(50), nullable=False, default="flat"
    )
    # ^^^ DECISION (override-candidate): "flat" only is honored by the B1
    # cashflow generator. Values like "escalating_cpi", "step_up" are
    # accepted (forward-compat) but the engine treats them as flat until B2
    # adds the schedule expander.

    __mapper_args__ = {
        "polymorphic_identity": "fixed_price",
    }


class IndexLinkedContract(Contract):
    """Contract priced as (index value at fixing) + spread, optionally with
    floor and cap collar.
    """
    __tablename__ = "tb_contract_index_linked"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("tb_contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    index_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("tb_index_definition.id"), nullable=False
    )
    spread: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    floor: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    fixing_rule: Mapped[str] = mapped_column(
        String(50), nullable=False, default="month_avg"
    )
    # ^^^ "month_avg", "spot_at_settlement", "5_day_avg_prior",
    # "5_day_avg_around", "quarterly_avg". The fixing engine (B2) will
    # implement these; B1's CFO Report uses month_avg as the default.

    index_definition: Mapped["IndexDefinition"] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "index_linked",
    }


# ──────────────────────────────────────────────────────────────────────
# Bankability bridge
# ──────────────────────────────────────────────────────────────────────


class ProjectFinanceLink(Base):
    """Bridge: classifies how a contract feeds gex_pf_engine's cashflow model.

    The same Contract carries the row data; this entity carries the project-
    finance classification (revenue vs opex vs debt service vs capex).

    DECISION (override-candidate): NOT unique on contract_id alone. Allows
    one contract to allocate across multiple projects in B2 (portfolio
    offtake) by adding rows with different project_asset_id and
    allocation_share. For B1, app layer enforces "one row per contract"
    until portfolio allocation is needed.
    """
    __tablename__ = "tb_project_finance_link"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid.uuid4
    )
    project_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("tb_asset.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("tb_contract.id", ondelete="CASCADE"), nullable=False
    )
    line_item_type: Mapped[PFLineItemType] = mapped_column(
        SAEnum(PFLineItemType, name="pf_line_item_type_enum"), nullable=False
    )
    pf_engine_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # ^^^ Optional: gex_pf_engine's internal line-item ID once the engine
    # has registered this contract. Lets the engine reverse-lookup. Set by
    # the engine via PATCH after rollup.

    allocation_share: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("1.000000")
    )
    # ^^^ Defaults to 100%. For B2 portfolio allocation across projects,
    # multiple rows for the same contract_id with shares summing to <= 1.0.

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project_asset: Mapped["Asset"] = relationship(back_populates="pf_links")
    contract: Mapped["Contract"] = relationship(back_populates="pf_links")

    __table_args__ = (
        Index("ix_pf_link_project", "project_asset_id"),
        Index("ix_pf_link_contract", "contract_id"),
        Index("ix_pf_link_type", "line_item_type"),
        UniqueConstraint(
            "project_asset_id", "contract_id", "line_item_type",
            name="uq_pf_link_project_contract_type",
        ),
    )


__all__ = [
    "Base",
    "ContractStatus",
    "PFLineItemType",
    "Asset",
    "Counterparty",
    "IndexDefinition",
    "IndexHistory",
    "Contract",
    "FixedPriceContract",
    "IndexLinkedContract",
    "ProjectFinanceLink",
]
