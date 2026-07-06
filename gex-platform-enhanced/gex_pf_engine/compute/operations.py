"""Post-COD operations compute.

Distinct from pre-COD: this is governed by operating cashflow ratios
(DSCR, LLCR, ICR) and a cash waterfall with lock-up and cash-sweep
behaviour. Tranches that began drawing in construction now repay; tranches
that draw in operations (e.g. take-out bond) refinance the construction
stack at COD.

This is where most of the "TS finance lib is good enough" functions live
in their Python form. Implementations agree numerically with the TS
versions on golden test cases — see tests/test_compute.py — so the live
preview and the authoritative compute do not drift.

Cash waterfall (senior, then mezz, then sponsor):
  1. Revenue (offtake-resolved) - opex      → operating cashflow
  2. - tax                                  → CFADS
  3. - senior interest + principal          → senior debt service
  4. top up DSRA to target months           → reserve
  5. above sweep threshold, % sweep         → prepay senior
  6. - mezz/sub debt service                → junior service
  7. lock-up test: if DSCR < threshold, trap cash
  8. remainder → distributions to equity
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from gex_pf_engine.compute.pre_cod import PreCODState
from gex_pf_engine.compute.ratios import annuity_payment, compute_dscr, compute_llcr
from gex_pf_engine.models import (
    DealInputs, DebtTranche, PeriodRow, ComputeWarning,
    RepaymentProfile, TrancheType,
)


# ---------------------------------------------------------------------------
# Revenue resolution from offtake contracts
# ---------------------------------------------------------------------------

# Volume-unit → base-unit conversion. Prices in price_formula are quoted
# in EUR per BASE unit (per tonne, per MWh, per m³). Volumes carried on
# offtake_contracts.volume_per_year must be scaled to base units before
# multiplying by price. Sourced from industry convention: SAF contracts
# price per tonne, hydrogen often per kg or per MWh-LHV, methanol per t.
VOLUME_UNIT_TO_BASE_MULTIPLIER = {
    "t_per_year":   1.0,        # base: tonne
    "kt_per_year":  1_000.0,    # 1 kt = 1,000 t
    "GWh_per_year": 1_000.0,    # 1 GWh = 1,000 MWh — assumes price in EUR/MWh
    "m3_per_year":  1.0,        # base: m³
    "kg_per_year":  1.0,        # base: kg
    "Nm3_per_year": 1.0,        # base: Nm³ (hydrogen industry standard)
}


def resolve_period_revenue(
    inputs: DealInputs,
    period_index_from_cod: int,
    revenue_by_offtake_out: dict[str, float],
) -> float:
    """Sum revenue across active offtake contracts in this operations period.
    Handles ramp-up profiles, fixed/indexed/take-or-pay/cfd pricing,
    allocation_pct, and volume-unit conversion to base units."""

    total = 0.0
    for off in inputs.offtakes:
        # Active in this period?
        start_period = off.start_year_offset_months // 12
        end_period = start_period + off.tenor_years
        if not (start_period <= period_index_from_cod < end_period):
            continue

        f = off.price_formula
        allocation = off.allocation_pct / 100.0

        # ---------------- determine volume in NAMEPLATE units ----------------
        # ramp_up_profile entries supersede each other; pick the most recent
        # stage whose year_offset has been reached.
        ramp_pct = 1.0
        if off.ramp_up_profile:
            year_offset = period_index_from_cod - start_period
            for stage in off.ramp_up_profile:
                if int(stage.get("year_offset", 0)) <= year_offset:
                    ramp_pct = float(stage["pct_of_nameplate"]) / 100.0

        # take_or_pay overrides volume with the contracted minimum
        if off.price_type.value == "take_or_pay":
            minimum_pct = float(f.get("fixed_minimum_pct", 0.85))
            volume_nameplate_units = off.volume_per_year * minimum_pct * allocation
        else:
            volume_nameplate_units = off.volume_per_year * ramp_pct * allocation

        # Convert to BASE units (tonnes / MWh / m³ / kg / Nm³) for pricing
        unit_multiplier = VOLUME_UNIT_TO_BASE_MULTIPLIER.get(off.volume_unit, 1.0)
        volume_base_units = volume_nameplate_units * unit_multiplier

        # ---------------- determine price in EUR / base unit -----------------
        if off.price_type.value == "fixed":
            price = float(f.get("price_eur_per_unit", 0.0))
        elif off.price_type.value == "indexed":
            base = float(f.get("base", 0.0))
            share = float(f.get("share", 1.0))
            # Sprint 2: index movement = 0%. Sprint 3 will read the Gabillon
            # two-factor curve from the curve service.
            index_delta_pct = 0.0
            price = base + share * base * index_delta_pct
            floor = f.get("floor")
            cap = f.get("cap")
            if floor is not None and price < float(floor):
                price = float(floor)
            if cap is not None and price > float(cap):
                price = float(cap)
        elif off.price_type.value == "take_or_pay":
            price = float(f.get("price_eur_per_unit", 0.0))
        elif off.price_type.value == "cfd":
            # Contract-for-difference: the strike IS the realised price
            price = float(f.get("strike", 0.0))
        elif off.price_type.value == "floor_collar":
            base_p = float(f.get("base", 0.0))
            price = max(float(f.get("floor", base_p)),
                        min(float(f.get("cap", base_p)), base_p))
        else:
            price = float(f.get("price_eur_per_unit", 0.0))

        revenue = volume_base_units * price
        revenue_by_offtake_out[off.id] = revenue
        total += revenue

    return total


# ---------------------------------------------------------------------------
# Per-tranche operations debt service
# ---------------------------------------------------------------------------

def operations_debt_service(
    tranche: DebtTranche,
    outstanding_at_period_start: float,
    period_index_from_cod: int,
) -> tuple[float, float, float]:
    """Returns (interest, principal, debt_service) for this period.

    Handles:
      - grace period (interest-only)
      - annuity, bullet, sculpted, custom profiles
      - tenor_years applies post-COD for construction-and-operations tranches
    """
    if tranche.is_equity or outstanding_at_period_start <= 0:
        return 0.0, 0.0, 0.0

    annual_rate = tranche.effective_rate_pct() / 100.0
    grace = int(tranche.grace_years)
    tenor = int(tranche.tenor_years)
    amort_years = max(1, tenor - grace)

    if period_index_from_cod >= tenor:
        return 0.0, 0.0, 0.0

    interest = outstanding_at_period_start * annual_rate

    if period_index_from_cod < grace:
        return interest, 0.0, interest

    if tranche.repayment_profile == RepaymentProfile.ANNUITY:
        # Annuity computed on the construction-end balance, paid down over amort_years
        annuity = annuity_payment(outstanding_at_period_start, annual_rate, amort_years - (period_index_from_cod - grace))
        principal = max(0.0, min(outstanding_at_period_start, annuity - interest))
        return interest, principal, interest + principal

    if tranche.repayment_profile == RepaymentProfile.BULLET:
        if period_index_from_cod == tenor - 1:
            return interest, outstanding_at_period_start, interest + outstanding_at_period_start
        return interest, 0.0, interest

    if tranche.repayment_profile == RepaymentProfile.SCULPTED and tranche.sculpted_schedule:
        # Sculpted schedule indexed by period_index_from_cod
        for entry in tranche.sculpted_schedule:
            if int(entry.get("year", -1)) == period_index_from_cod:
                principal = float(entry.get("principal_eur", 0.0))
                principal = min(principal, outstanding_at_period_start)
                return interest, principal, interest + principal
        return interest, 0.0, interest

    # Custom / unknown → linear
    principal = outstanding_at_period_start / max(1, amort_years - (period_index_from_cod - grace))
    principal = min(principal, outstanding_at_period_start)
    return interest, principal, interest + principal


# ---------------------------------------------------------------------------
# Cash waterfall
# ---------------------------------------------------------------------------

@dataclass
class WaterfallResult:
    """The decomposition of operating cashflow through the waterfall."""
    cfads: float
    senior_service_paid: float
    dsra_topup: float
    cash_swept: float
    junior_service_paid: float
    distributions: float
    lockup_active: bool
    new_dsra_balance: float


def waterfall(
    cfads: float,
    senior_service_due: float,
    junior_service_due: float,
    dsra_current: float,
    dsra_target: float,
    sweep_active: bool,
    sweep_pct: float,
    lockup_active_input: bool,
) -> WaterfallResult:
    """Process operating cashflow through the standard PF waterfall."""

    cash = cfads
    # Tier 1: senior debt service
    senior_paid = min(cash, senior_service_due)
    cash -= senior_paid

    # Tier 2: DSRA top-up
    dsra_gap = max(0.0, dsra_target - dsra_current)
    dsra_topup = min(cash, dsra_gap)
    cash -= dsra_topup
    new_dsra = dsra_current + dsra_topup

    # Tier 3: cash sweep (applied to senior — would prepay in next period)
    cash_swept = 0.0
    if sweep_active and cash > 0:
        cash_swept = cash * sweep_pct
        cash -= cash_swept

    # Tier 4: junior debt service
    junior_paid = min(cash, junior_service_due)
    cash -= junior_paid

    # Tier 5: lock-up test
    if lockup_active_input:
        # Cash trapped; no distributions
        return WaterfallResult(
            cfads=cfads,
            senior_service_paid=senior_paid,
            dsra_topup=dsra_topup,
            cash_swept=cash_swept + cash,  # everything above swept into trap
            junior_service_paid=junior_paid,
            distributions=0.0,
            lockup_active=True,
            new_dsra_balance=new_dsra,
        )

    # Tier 6: distributions
    distributions = max(0.0, cash)
    return WaterfallResult(
        cfads=cfads,
        senior_service_paid=senior_paid,
        dsra_topup=dsra_topup,
        cash_swept=cash_swept,
        junior_service_paid=junior_paid,
        distributions=distributions,
        lockup_active=False,
        new_dsra_balance=new_dsra,
    )


# ---------------------------------------------------------------------------
# Operations runner
# ---------------------------------------------------------------------------

@dataclass
class OperationsOutput:
    period_rows: list[PeriodRow]
    min_dscr: Optional[float]
    avg_dscr: Optional[float]
    llcr: Optional[float]
    breach_periods: list[int]
    warnings: list[ComputeWarning]


def run_operations(
    inputs: DealInputs,
    pre_cod_state: PreCODState,
) -> OperationsOutput:
    """Walk operating periods. Annual granularity is fine for Sprint 2;
    Sprint 3 will support semi-annual covenant testing if needed."""

    deal = inputs.deal
    plant = inputs.plant
    warnings: list[ComputeWarning] = []

    # Initial conditions handed over from construction
    outstanding = dict(pre_cod_state.outstanding_by_tranche_at_cod)
    # Operations-only tranches start drawing now — treat them as drawn fully at COD
    for tr in inputs.tranches:
        if tr.drawdown_phase.value == "operations":
            outstanding[tr.id] = outstanding.get(tr.id, 0.0) + tr.commitment_eur

    cash_account = pre_cod_state.cash_at_cod_eur

    # DSRA target: pull from covenants if specified
    dsra_target_months = _find_dsra_target_months(inputs)
    dsra_balance = 0.0

    # Lock-up + sweep thresholds
    dscr_lockup_threshold = _find_covenant_value(inputs, "dscr_lockup") or 1.2
    dscr_sweep_threshold = _find_covenant_value(inputs, "dscr_sweep") or 1.4
    sweep_pct = (_find_covenant_value(inputs, "cash_sweep_pct") or 50.0) / 100.0
    dscr_floor = _find_covenant_value(inputs, "dscr_floor") or 1.05

    rows: list[PeriodRow] = []
    breach_periods: list[int] = []

    # Operating period span — annual rows
    n_years = int(deal.operating_period_years)
    # Period index in the full schedule starts after pre-COD rows; here we
    # number from 0 within operations
    start_date = deal.actual_cod_date or deal.scheduled_cod_date
    accumulated_dep = 0.0

    senior_tranches = [
        t for t in inputs.debt_tranches() if t.seniority_rank == 1
    ]
    junior_tranches = [
        t for t in inputs.debt_tranches() if t.seniority_rank > 1
    ]

    for y in range(n_years):
        period_start = date(start_date.year + y, start_date.month, start_date.day)
        revenue_by_offtake: dict[str, float] = {}
        revenue = resolve_period_revenue(inputs, y, revenue_by_offtake)
        opex = plant.opex_eur_per_year
        ebitda = revenue - opex

        # Per-tranche debt service
        debt_service_by_tranche: dict[str, float] = {}
        interest_by_tranche: dict[str, float] = {}
        principal_by_tranche: dict[str, float] = {}
        outstanding_by_tranche_snapshot: dict[str, float] = {}

        senior_service_due = 0.0
        junior_service_due = 0.0
        total_interest = 0.0
        total_principal = 0.0

        for tr in inputs.debt_tranches():
            i, p, ds = operations_debt_service(tr, outstanding.get(tr.id, 0.0), y)
            interest_by_tranche[tr.id] = i
            principal_by_tranche[tr.id] = p
            debt_service_by_tranche[tr.id] = ds
            total_interest += i
            total_principal += p
            if tr.seniority_rank == 1:
                senior_service_due += ds
            else:
                junior_service_due += ds

        # Tax: simple model — pay tax on EBITDA − depreciation − interest
        # (interest deductible). Real engines model NOL carryforward.
        depreciation = plant.capex_eur / deal.depreciation_years if y < deal.depreciation_years else 0.0
        accumulated_dep += depreciation
        ebit = ebitda - depreciation
        taxable_income = ebit - total_interest
        tax = max(0.0, taxable_income) * (deal.tax_rate_pct / 100.0)

        cfads = ebitda - tax  # working-capital + maint capex omitted in Sprint 2
        total_debt_service = senior_service_due + junior_service_due

        # DSCR (operations-only)
        dscr_val = compute_dscr(cfads=cfads, debt_service=total_debt_service)
        icr = ebit / total_interest if total_interest > 0 else None

        # Determine lock-up + sweep state for THIS period before waterfall runs
        lockup_active_input = dscr_val is not None and dscr_val < dscr_lockup_threshold
        sweep_active = dscr_val is not None and dscr_val > dscr_sweep_threshold

        # DSRA target snapshot
        dsra_target = (dsra_target_months / 12.0) * total_debt_service if dsra_target_months else 0.0

        # Run waterfall
        wf = waterfall(
            cfads=cfads,
            senior_service_due=senior_service_due,
            junior_service_due=junior_service_due,
            dsra_current=dsra_balance,
            dsra_target=dsra_target,
            sweep_active=sweep_active,
            sweep_pct=sweep_pct,
            lockup_active_input=lockup_active_input,
        )
        dsra_balance = wf.new_dsra_balance

        # Apply principal to outstanding balances
        for tr in inputs.debt_tranches():
            outstanding[tr.id] = max(0.0, outstanding.get(tr.id, 0.0) - principal_by_tranche[tr.id])
            outstanding_by_tranche_snapshot[tr.id] = outstanding[tr.id]

        # Apply cash sweep: prepay senior tranches proportionally
        if wf.cash_swept > 0 and senior_tranches:
            senior_outstanding_total = sum(outstanding.get(t.id, 0.0) for t in senior_tranches)
            if senior_outstanding_total > 0:
                for t in senior_tranches:
                    share = outstanding.get(t.id, 0.0) / senior_outstanding_total
                    prepay = min(outstanding[t.id], wf.cash_swept * share)
                    outstanding[t.id] -= prepay
                    outstanding_by_tranche_snapshot[t.id] = outstanding[t.id]

        if dscr_val is not None and dscr_val < dscr_floor:
            breach_periods.append(y)
            warnings.append(ComputeWarning(
                code="dscr_below_floor",
                message=f"Period {y}: DSCR {dscr_val:.2f} below floor {dscr_floor:.2f}",
                severity="error",
            ))

        rows.append(PeriodRow(
            period_index=y,
            period_start_date=period_start,
            phase="operations",
            revenue_eur=revenue,
            revenue_by_offtake=revenue_by_offtake,
            opex_eur=opex,
            ebitda_eur=ebitda,
            depreciation_eur=depreciation,
            ebit_eur=ebit,
            interest_expense_eur=total_interest,
            tax_eur=tax,
            net_income_eur=ebit - total_interest - tax,
            debt_service_by_tranche=debt_service_by_tranche,
            outstanding_by_tranche=outstanding_by_tranche_snapshot,
            cfads_eur=cfads,
            total_debt_service_eur=total_debt_service,
            dsra_balance_eur=dsra_balance,
            cash_swept_eur=wf.cash_swept,
            lockup_active=wf.lockup_active,
            free_cash_flow_eur=cfads - total_debt_service,
            distributions_eur=wf.distributions,
            dscr=dscr_val,
            icr=icr,
        ))

    # Aggregate DSCR
    dscrs = [r.dscr for r in rows if r.dscr is not None]
    min_dscr = min(dscrs) if dscrs else None
    avg_dscr = sum(dscrs) / len(dscrs) if dscrs else None

    # LLCR computed against the senior outstanding at COD
    senior_outstanding_cod = sum(
        pre_cod_state.outstanding_by_tranche_at_cod.get(t.id, 0.0)
        for t in senior_tranches
    )
    senior_rate = senior_tranches[0].effective_rate_pct() / 100.0 if senior_tranches else 0.05
    cfads_stream = [r.cfads_eur for r in rows if r.cfads_eur is not None]
    llcr = compute_llcr(cfads_stream, senior_rate, senior_outstanding_cod) if senior_outstanding_cod > 0 else None

    return OperationsOutput(
        period_rows=rows,
        min_dscr=min_dscr,
        avg_dscr=avg_dscr,
        llcr=llcr,
        breach_periods=breach_periods,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_dsra_target_months(inputs: DealInputs) -> Optional[float]:
    for c in inputs.covenants:
        if c.covenant_type == "debt_service_reserve_months" and c.value is not None:
            return float(c.value)
    return 6.0  # market default


def _find_covenant_value(inputs: DealInputs, covenant_type: str) -> Optional[float]:
    for c in inputs.covenants:
        if c.covenant_type == covenant_type and c.value is not None:
            return float(c.value)
    return None
