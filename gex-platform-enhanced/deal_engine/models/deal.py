"""Pydantic models mirroring the Sprint 2 SQL schema.

These are the contract between the engine and the GEX platform. The engine
reads rows from the platform, validates them into these models, runs compute, and
writes a DealOutput row back.

Naming convention: snake_case fields matching column names exactly, so
that a row-as-dict payload can be passed straight to model_validate().
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enums — mirror the SQL CHECK constraints exactly.
# ---------------------------------------------------------------------------

class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUBMITTED  = "SUBMITTED"
    CONFIRMED  = "CONFIRMED"
    AUDITED    = "AUDITED"


class TrancheType(str, Enum):
    SENIOR_BANK        = "senior_bank"
    SENIOR_BOND        = "senior_bond"
    MEZZANINE          = "mezzanine"
    SHAREHOLDER_LOAN   = "shareholder_loan"
    EQUITY_BRIDGE      = "equity_bridge"
    EQUITY             = "equity"
    CONTINGENT_EQUITY  = "contingent_equity"


class DrawdownPhase(str, Enum):
    CONSTRUCTION = "construction"
    OPERATIONS   = "operations"
    BOTH         = "both"


class IDCTreatment(str, Enum):
    CAPITALISED_FROM_DRAWINGS = "capitalised_from_drawings"
    CAPITALISED_FROM_EQUITY   = "capitalised_from_equity"
    CAPITALISED_FROM_BRIDGE   = "capitalised_from_bridge"
    PAID_CURRENT              = "paid_current"
    NOT_APPLICABLE            = "not_applicable"


class RepaymentProfile(str, Enum):
    ANNUITY  = "annuity"
    BULLET   = "bullet"
    SCULPTED = "sculpted"
    CUSTOM   = "custom"
    EQUITY   = "equity"


class CovenantPhase(str, Enum):
    CONSTRUCTION = "construction"
    OPERATIONS   = "operations"
    AT_COD_TEST  = "at_cod_test"


class PriceType(str, Enum):
    FIXED        = "fixed"
    INDEXED      = "indexed"
    FLOOR_COLLAR = "floor_collar"
    TAKE_OR_PAY  = "take_or_pay"
    CFD          = "cfd"
    SPOT         = "spot"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

class DealStructure(BaseModel):
    """Top-level deal — what the user is structuring."""
    model_config = ConfigDict(extra="ignore")

    id:                       str
    plant_id:                 str
    user_id:                  str
    name:                     str
    version:                  int
    status:                   str
    construction_start_date:  date
    scheduled_cod_date:       date
    actual_cod_date:          Optional[date] = None
    operating_period_years:   float
    discount_rate_pct:        float
    tax_rate_pct:             float
    depreciation_years:       float
    verification_state:       VerificationState = VerificationState.UNVERIFIED
    deal_killer_flag:         bool = False

    @model_validator(mode="after")
    def _cod_after_start(self) -> "DealStructure":
        if self.scheduled_cod_date <= self.construction_start_date:
            raise ValueError("scheduled_cod_date must be after construction_start_date")
        return self

    @property
    def construction_period_months(self) -> int:
        """Whole-month construction window length."""
        a, b = self.construction_start_date, self.scheduled_cod_date
        return (b.year - a.year) * 12 + (b.month - a.month)


class DebtTranche(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:                       str
    deal_structure_id:        str
    seniority_rank:           int
    tranche_type:             TrancheType
    lender_class:             Optional[str] = None
    lender_name:              Optional[str] = None
    commitment_eur:           float = Field(ge=0)
    currency:                 str = "EUR"
    fx_hedge_pct:             float = 0.0
    rate_type:                Literal["fixed", "floating"]
    base_rate_pct:            Optional[float] = None
    spread_bps:               Optional[float] = None
    fixed_rate_pct:           Optional[float] = None
    upfront_fee_bps:          float = 0.0
    commitment_fee_bps:       float = 0.0
    tenor_years:              float
    grace_years:              float = 0.0
    repayment_profile:        RepaymentProfile
    sculpted_schedule:        Optional[list[dict[str, Any]]] = None
    drawdown_phase:           DrawdownPhase
    drawdown_schedule:        Optional[list[dict[str, Any]]] = None
    conditions_precedent:     Optional[list[dict[str, Any]]] = None
    idc_treatment:            Optional[IDCTreatment] = None
    conversion_at_cod_terms:  Optional[dict[str, Any]] = None
    verification_state:       VerificationState = VerificationState.UNVERIFIED

    @property
    def is_equity(self) -> bool:
        return self.tranche_type in (
            TrancheType.EQUITY,
            TrancheType.CONTINGENT_EQUITY,
        )

    @property
    def is_debt(self) -> bool:
        return not self.is_equity

    def effective_rate_pct(self) -> float:
        """Resolve to a single effective rate for compute. Floating is
        approximated as base+spread; production should pass scenario curves."""
        if self.rate_type == "fixed":
            return self.fixed_rate_pct or 0.0
        base = self.base_rate_pct or 0.0
        spread = (self.spread_bps or 0.0) / 100.0
        return base + spread


class OfftakeContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:                       str
    plant_id:                 str
    counterparty_name:        str
    counterparty_class:       Optional[str] = None
    molecule:                 str
    volume_per_year:          float = Field(gt=0)
    volume_unit:              str
    price_type:               PriceType
    price_formula:            dict[str, Any]
    currency:                 str = "EUR"
    tenor_years:              float = Field(gt=0)
    start_year_offset_months: int = 0
    ramp_up_profile:          Optional[list[dict[str, Any]]] = None
    status:                   str
    signed_date:              Optional[date] = None
    verification_state:       VerificationState = VerificationState.UNVERIFIED
    deal_killer_flag:         bool = False
    allocation_pct:           float = 100.0  # from deal_structure_offtake


class Covenant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:                       str
    deal_structure_id:        str
    phase:                    CovenantPhase
    covenant_type:            str
    value:                    Optional[float] = None
    value_text:               Optional[str] = None
    basis:                    Optional[str] = None
    test_frequency:           str
    applies_to_tranche_id:    Optional[str] = None


class PreCODTest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:                       str
    deal_structure_id:        str
    test_type:                str
    threshold:                Optional[float] = None
    threshold_text:           Optional[str] = None
    comparison:               str = "gte"
    test_frequency:           str
    breach_consequence:       str


class PlantSummary(BaseModel):
    """Subset of plant data the engine needs. Read from public.plants."""
    model_config = ConfigDict(extra="ignore")

    id:                       str
    capex_eur:                float = Field(ge=0)
    opex_eur_per_year:        float = Field(ge=0)
    nameplate_capacity:       Optional[float] = None
    nameplate_unit:            Optional[str] = None
    verification_state:       VerificationState = VerificationState.UNVERIFIED
    deal_killer_flag:         bool = False
    latest_engine_run_status: Optional[str] = None  # from v_latest_engine_run


class DealInputs(BaseModel):
    """The full input bundle the engine assembles from the platform per request."""
    model_config = ConfigDict(extra="ignore")

    deal:        DealStructure
    plant:       PlantSummary
    tranches:    list[DebtTranche]
    offtakes:    list[OfftakeContract]
    covenants:   list[Covenant]
    precod:      list[PreCODTest]

    def equity_tranches(self) -> list[DebtTranche]:
        return [t for t in self.tranches if t.is_equity]

    def debt_tranches(self) -> list[DebtTranche]:
        return [t for t in self.tranches if t.is_debt]

    def total_equity_commitment_eur(self) -> float:
        return sum(t.commitment_eur for t in self.equity_tranches())

    def total_debt_commitment_eur(self) -> float:
        return sum(t.commitment_eur for t in self.debt_tranches())

    def covenants_for_phase(self, phase: CovenantPhase) -> list[Covenant]:
        return [c for c in self.covenants if c.phase == phase]


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

class PeriodRow(BaseModel):
    """One period (annual, or finer) of the cashflow schedule."""
    model_config = ConfigDict(extra="ignore")

    period_index:           int
    period_start_date:      date
    phase:                  Literal["construction", "operations"]

    # Revenue (operations only)
    revenue_eur:            float = 0.0
    revenue_by_offtake:     dict[str, float] = Field(default_factory=dict)

    # Costs
    opex_eur:               float = 0.0
    capex_invested_eur:     float = 0.0  # construction only

    # P&L
    ebitda_eur:             float = 0.0
    depreciation_eur:       float = 0.0
    ebit_eur:               float = 0.0
    interest_expense_eur:   float = 0.0
    tax_eur:                float = 0.0
    net_income_eur:         float = 0.0

    # Debt — by tranche id
    drawn_by_tranche:       dict[str, float] = Field(default_factory=dict)
    debt_service_by_tranche: dict[str, float] = Field(default_factory=dict)
    outstanding_by_tranche: dict[str, float] = Field(default_factory=dict)
    idc_capitalised_eur:    float = 0.0

    # Cash mechanics
    cfads_eur:              Optional[float] = None  # None during construction
    total_debt_service_eur: float = 0.0
    dsra_balance_eur:       float = 0.0
    cash_swept_eur:         float = 0.0
    lockup_active:          bool = False
    free_cash_flow_eur:     float = 0.0
    distributions_eur:      float = 0.0

    # Ratios — operations period only; None during construction
    dscr:                   Optional[float] = None
    icr:                    Optional[float] = None    # interest coverage


class PreCODRatioPoint(BaseModel):
    period_index:                   int
    period_start_date:              date
    cost_to_complete_coverage:      Optional[float] = None
    equity_drawn_ratio:             Optional[float] = None
    pari_passu_ratio:               Optional[float] = None
    physical_progress_pct:          Optional[float] = None
    sponsor_support_headroom_eur:   Optional[float] = None
    breaches:                       list[str] = Field(default_factory=list)


class PreCODSummary(BaseModel):
    period_rows:               list[PreCODRatioPoint] = Field(default_factory=list)
    total_idc_capitalised_eur: float = 0.0
    final_construction_loan_eur: float = 0.0
    worst_cost_to_complete_coverage: Optional[float] = None
    worst_breach: Optional[str] = None


class CODTestSummary(BaseModel):
    """Snapshot of the COD test evaluation at compute time. This is a
    projection if actual_cod_date is null, or a record if it has passed."""
    capacity_demonstration_pct:    Optional[float] = None
    permits_in_force:              Optional[bool] = None
    offtake_unconditional:         Optional[bool] = None
    dsra_funded:                   Optional[bool] = None
    lookforward_dscr_p90:          Optional[float] = None
    lookforward_llcr_p90:          Optional[float] = None
    lookforward_dscr_threshold:    Optional[float] = None
    projected_passed:              Optional[bool] = None
    blocking_conditions:           list[str] = Field(default_factory=list)


class TaghizadehHesaryAssessment(BaseModel):
    """Bank vs bond mix commentary. Taghizadeh-Hesary (2022) — optimal
    split for renewable energy infrastructure projects."""
    current_bank_pct:             float
    current_bond_pct:             float
    optimal_bank_pct:             float = 56.0
    optimal_bond_pct:             float = 44.0
    deviation_bps:                float
    interpretation:               str


class ComputeWarning(BaseModel):
    code:                         str
    message:                      str
    severity:                     Literal["info", "warning", "error"] = "warning"


class ComputeOutput(BaseModel):
    """The full result. Written to deal_outputs."""
    model_config = ConfigDict(extra="ignore")

    deal_structure_id:            str
    inputs_hash:                  str
    engine_version:               str
    cashflow_schedule:            list[PeriodRow]
    precod_summary:               Optional[PreCODSummary] = None
    cod_test_summary:             Optional[CODTestSummary] = None

    # Post-COD summary
    project_irr:                  Optional[float] = None
    equity_irr:                   Optional[float] = None
    npv_eur:                      Optional[float] = None
    min_dscr_operations:          Optional[float] = None
    avg_dscr_operations:          Optional[float] = None
    llcr:                         Optional[float] = None
    rating_band:                  Optional[str] = None
    binding_constraint:           Optional[str] = None
    covenant_breach_periods:      list[int] = Field(default_factory=list)

    warnings:                     list[ComputeWarning] = Field(default_factory=list)
    errors:                       list[ComputeWarning] = Field(default_factory=list)
    taghizadeh_hesary_assessment: Optional[TaghizadehHesaryAssessment] = None
