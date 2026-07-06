"""
gex_platform/trading_book/schemas.py

Pydantic v2 request/response schemas for B1 trading book.

Design principle: the DB stays loose for the deliberately-extensible fields
(provider, fuel_type, technology, quantity_unit). Validation lives here, in
one place, against KNOWN_* sets that are easy to extend without touching
migrations. Unknown values are accepted today (advisory only) and can be
upgraded to strict rejection later by changing one line per validator.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.trading_book.models import (
    ContractStatus,
    PFLineItemType,
)


# ──────────────────────────────────────────────────────────────────────
# Known-value sets (advisory; not DB-enforced)
# ──────────────────────────────────────────────────────────────────────
#
# These exist to centralize the controlled-vocabulary check for fields
# stored as free strings in the DB. To make any of them strict (reject
# unknown values), change the validator below from a pass to a raise.

KNOWN_INDEX_PROVIDERS: set[str] = {
    "Argus", "Platts", "ICIS", "OPIS", "EEX", "ICE", "CME",
    "Bilateral", "Other",
}

KNOWN_FUEL_TYPES: set[str] = {
    "GREEN_H2", "BLUE_H2", "GREY_H2",
    "GREEN_NH3", "BLUE_NH3",
    "ESAF", "BIOSAF", "HEFA_SAF",
    "EMETHANOL", "BIOMETHANOL",
    "EDIESEL", "EKEROSENE",
    "OTHER",
}

KNOWN_QUANTITY_UNITS: set[str] = {"MWh", "GWh", "TWh", "t", "kt", "Mt", "m3", "kg"}

KNOWN_TECHNOLOGIES: set[str] = {
    "PEM_ELECTROLYSIS", "AEM_ELECTROLYSIS", "SOEC", "ALKALINE_ELECTROLYSIS",
    "BIOMASS_TO_LIQUID", "POWER_TO_LIQUID", "POWER_TO_METHANOL",
    "HABER_BOSCH", "AUTOTHERMAL_REFORMING", "STEAM_METHANE_REFORMING",
    "OTHER",
}

KNOWN_FIXING_RULES: set[str] = {
    "month_avg", "spot_at_settlement", "5_day_avg_prior",
    "5_day_avg_around", "quarterly_avg", "custom",
}

KNOWN_PRICE_BASES: set[str] = {
    "flat", "escalating_cpi", "escalating_fixed",
    "step_up", "step_down", "custom",
}


# ──────────────────────────────────────────────────────────────────────
# Asset
# ──────────────────────────────────────────────────────────────────────


class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    country_code: str = Field(min_length=2, max_length=2)
    technology: str = Field(min_length=1, max_length=100)
    capacity_mw: Decimal = Field(gt=0)
    cod_date: Optional[date] = None
    is_active: bool = True

    @field_validator("country_code")
    @classmethod
    def _country_upper(cls, v: str) -> str:
        v = v.upper()
        if not v.isalpha():
            raise ValueError("country_code must be ISO 3166-1 alpha-2 letters")
        return v

    @field_validator("technology")
    @classmethod
    def _technology_known(cls, v: str) -> str:
        # Advisory: accept unknown values for now, log at app layer.
        # To make strict: raise ValueError if v not in KNOWN_TECHNOLOGIES.
        return v


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, min_length=1, max_length=200)
    country_code: Optional[str] = Field(default=None, min_length=2, max_length=2)
    technology: Optional[str] = Field(default=None, min_length=1, max_length=100)
    capacity_mw: Optional[Decimal] = Field(default=None, gt=0)
    cod_date: Optional[date] = None
    is_active: Optional[bool] = None


class AssetRead(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Counterparty
# ──────────────────────────────────────────────────────────────────────


class CounterpartyBase(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    lei: Optional[str] = Field(default=None, min_length=20, max_length=20)
    country_code: str = Field(min_length=2, max_length=2)
    is_active: bool = True

    @field_validator("country_code")
    @classmethod
    def _country_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("lei")
    @classmethod
    def _lei_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper()
        if not v.isalnum():
            raise ValueError("LEI must be 20 alphanumeric characters")
        return v


class CounterpartyCreate(CounterpartyBase):
    pass


class CounterpartyUpdate(BaseModel):
    legal_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    lei: Optional[str] = Field(default=None, min_length=20, max_length=20)
    country_code: Optional[str] = Field(default=None, min_length=2, max_length=2)
    is_active: Optional[bool] = None


class CounterpartyRead(CounterpartyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────
# IndexDefinition / IndexHistory
# ──────────────────────────────────────────────────────────────────────


class IndexDefinitionBase(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    index_code: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    currency: str = Field(min_length=3, max_length=3)
    unit_basis: str = Field(min_length=1, max_length=20)
    frequency: str = Field(default="daily", max_length=20)
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str) -> str:
        v = v.upper()
        if not v.isalpha():
            raise ValueError("currency must be ISO 4217 letters")
        return v

    @field_validator("provider")
    @classmethod
    def _provider_known(cls, v: str) -> str:
        # Advisory only — list is non-exhaustive per spec.
        return v


class IndexDefinitionCreate(IndexDefinitionBase):
    pass


class IndexDefinitionUpdate(BaseModel):
    """Only safe-to-change fields are exposed.

    DECISION: provider, index_code, currency, and unit_basis are intentionally
    NOT updatable — changing them would silently invalidate IndexHistory rows.
    To replace an index, deactivate the old one and create a new one.
    """
    description: Optional[str] = Field(default=None, max_length=500)
    frequency: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None


class IndexDefinitionRead(IndexDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class IndexHistoryBase(BaseModel):
    index_definition_id: uuid.UUID
    observation_date: date
    value: Decimal
    source_ref: Optional[str] = Field(default=None, max_length=100)


class IndexHistoryCreate(IndexHistoryBase):
    pass


class IndexHistoryRead(IndexHistoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ingested_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Contract — common base + subtype variants
# ──────────────────────────────────────────────────────────────────────


class _ContractCommonFields(BaseModel):
    """Shared by both subtype create schemas."""
    contract_number: str = Field(min_length=1, max_length=50)
    buy_side_id: uuid.UUID
    sell_side_id: uuid.UUID
    fuel_type: str = Field(min_length=1, max_length=50)
    trade_date: date
    effective_date: date
    termination_date: date
    notional_quantity: Decimal = Field(gt=0)
    quantity_unit: str = Field(min_length=1, max_length=10)
    currency: str = Field(min_length=3, max_length=3)
    status: ContractStatus = ContractStatus.DRAFT

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("fuel_type")
    @classmethod
    def _fuel_type_norm(cls, v: str) -> str:
        # Advisory: accept unknown, normalize to upper-snake.
        return v.upper().replace("-", "_").replace(" ", "_")

    @field_validator("quantity_unit")
    @classmethod
    def _quantity_unit_check(cls, v: str) -> str:
        # Advisory.
        return v

    @model_validator(mode="after")
    def _check_dates(self) -> "_ContractCommonFields":
        if self.trade_date > self.effective_date:
            raise ValueError("trade_date must be on or before effective_date")
        if self.effective_date > self.termination_date:
            raise ValueError("effective_date must be on or before termination_date")
        return self

    @model_validator(mode="after")
    def _check_sides_distinct(self) -> "_ContractCommonFields":
        if self.buy_side_id == self.sell_side_id:
            raise ValueError("buy_side and sell_side must be different counterparties")
        return self


class FixedPriceContractCreate(_ContractCommonFields):
    fixed_price: Decimal = Field(gt=0)
    price_basis: str = Field(default="flat", max_length=50)


class IndexLinkedContractCreate(_ContractCommonFields):
    index_definition_id: uuid.UUID
    spread: Decimal = Decimal("0")
    floor: Optional[Decimal] = None
    cap: Optional[Decimal] = None
    fixing_rule: str = Field(default="month_avg", max_length=50)

    @model_validator(mode="after")
    def _check_floor_cap(self) -> "IndexLinkedContractCreate":
        if (
            self.floor is not None
            and self.cap is not None
            and self.floor > self.cap
        ):
            raise ValueError("floor must be <= cap")
        return self


class ContractStatusUpdate(BaseModel):
    """B1 lifecycle update. B3 will replace this with explicit transition
    endpoints (advance_to_proposed, advance_to_committed, etc.) wired to the
    seven-step decision chain.
    """
    status: ContractStatus


class FixedPriceContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_number: str
    contract_type: str
    buy_side_id: uuid.UUID
    sell_side_id: uuid.UUID
    fuel_type: str
    trade_date: date
    effective_date: date
    termination_date: date
    notional_quantity: Decimal
    quantity_unit: str
    currency: str
    status: ContractStatus
    fixed_price: Decimal
    price_basis: str
    created_at: datetime
    updated_at: datetime


class IndexLinkedContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_number: str
    contract_type: str
    buy_side_id: uuid.UUID
    sell_side_id: uuid.UUID
    fuel_type: str
    trade_date: date
    effective_date: date
    termination_date: date
    notional_quantity: Decimal
    quantity_unit: str
    currency: str
    status: ContractStatus
    index_definition_id: uuid.UUID
    spread: Decimal
    floor: Optional[Decimal]
    cap: Optional[Decimal]
    fixing_rule: str
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────
# ProjectFinanceLink
# ──────────────────────────────────────────────────────────────────────


class ProjectFinanceLinkBase(BaseModel):
    project_asset_id: uuid.UUID
    contract_id: uuid.UUID
    line_item_type: PFLineItemType
    pf_engine_ref: Optional[str] = Field(default=None, max_length=100)
    allocation_share: Decimal = Field(default=Decimal("1.0"), gt=0, le=1)
    notes: Optional[str] = None


class ProjectFinanceLinkCreate(ProjectFinanceLinkBase):
    pass


class ProjectFinanceLinkUpdate(BaseModel):
    """Only the engine-ref and allocation-related fields are mutable."""
    line_item_type: Optional[PFLineItemType] = None
    pf_engine_ref: Optional[str] = Field(default=None, max_length=100)
    allocation_share: Optional[Decimal] = Field(default=None, gt=0, le=1)
    notes: Optional[str] = None


class ProjectFinanceLinkRead(ProjectFinanceLinkBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


__all__ = [
    # known-value sets
    "KNOWN_INDEX_PROVIDERS",
    "KNOWN_FUEL_TYPES",
    "KNOWN_QUANTITY_UNITS",
    "KNOWN_TECHNOLOGIES",
    "KNOWN_FIXING_RULES",
    "KNOWN_PRICE_BASES",
    # Asset
    "AssetCreate", "AssetUpdate", "AssetRead",
    # Counterparty
    "CounterpartyCreate", "CounterpartyUpdate", "CounterpartyRead",
    # Index
    "IndexDefinitionCreate", "IndexDefinitionUpdate", "IndexDefinitionRead",
    "IndexHistoryCreate", "IndexHistoryRead",
    # Contracts
    "FixedPriceContractCreate", "FixedPriceContractRead",
    "IndexLinkedContractCreate", "IndexLinkedContractRead",
    "ContractStatusUpdate",
    # PF Link
    "ProjectFinanceLinkCreate", "ProjectFinanceLinkUpdate", "ProjectFinanceLinkRead",
]
