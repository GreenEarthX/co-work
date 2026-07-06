"""Pre-COD compute logic.

This module is the structural answer to "DSCR is a category error pre-COD."
During construction, projects are governed by completion risk and milestone
gating, not by operating cashflow ratios. The ratios that matter are:

  - Cost-to-complete coverage: (cash + undrawn debt + undrawn equity) /
    remaining capex. Must stay ≥ threshold (typ. 1.0–1.10) at every drawdown.

  - Pari-passu ratio: equity_drawn / debt_drawn at any point should match
    the agreed final D/E split. Sponsors cannot be allowed to backload their
    equity contribution behind the debt.

  - Equity-drawn ratio: equity_drawn / equity_committed. Used to test that
    the sponsor is performing on its commitment schedule.

  - Sponsor-support headroom: cost-overrun guarantee cap − utilised. If
    the project hits an overrun, can the sponsor absorb it under the
    completion guarantee?

  - Physical progress vs schedule: measured by Independent Engineer
    certification, not by accounting. Surfaces in drawdown_events.

IDC (Interest During Construction):
  - capitalised_from_drawings: each period's accrued interest is added to
    the principal, paid via additional debt drawdowns. The loan balance
    grows during construction. Most common for green-field PF.
  - capitalised_from_bridge: a separate equity-bridge loan funds IDC,
    repaid at COD from long-term debt or from sponsor equity.
  - capitalised_from_equity: sponsor tops up equity to fund IDC directly.
  - paid_current: requires interim revenue (rare for green-field).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from gex_pf_engine.models import (
    DealInputs, DebtTranche, IDCTreatment, DrawdownPhase,
    PreCODSummary, PreCODRatioPoint, ComputeWarning, TrancheType,
)


# ---------------------------------------------------------------------------
# Period stepping — quarterly by default for construction. Annual is too
# coarse for pre-COD because milestones cluster.
# ---------------------------------------------------------------------------

@dataclass
class ConstructionPeriod:
    index: int
    start: date
    end: date          # exclusive
    months: float


def construction_periods(
    start: date,
    cod: date,
    period_months: int = 3,
) -> list[ConstructionPeriod]:
    """Quarterly periods covering [start, cod). The last period is truncated
    if the construction window isn't a clean multiple of period_months."""
    out: list[ConstructionPeriod] = []
    idx = 0
    cursor = start
    while cursor < cod:
        # Step forward by period_months whole months
        next_year = cursor.year + (cursor.month - 1 + period_months) // 12
        next_month = (cursor.month - 1 + period_months) % 12 + 1
        # Clamp to month-end to avoid 31->28 edge cases
        try:
            nxt = date(next_year, next_month, cursor.day)
        except ValueError:
            # day-of-month doesn't exist; fall back to last day of next_month
            from calendar import monthrange
            last = monthrange(next_year, next_month)[1]
            nxt = date(next_year, next_month, min(cursor.day, last))
        if nxt > cod:
            nxt = cod
        days_in_period = (nxt - cursor).days
        months = days_in_period / 30.4375  # average month length
        out.append(ConstructionPeriod(idx, cursor, nxt, months))
        cursor = nxt
        idx += 1
    return out


# ---------------------------------------------------------------------------
# Drawdown schedule resolution.
# A tranche carries an optional drawdown_schedule:
#   [{"date": "2026-09-30", "amount_eur": 50000000, "milestone_ref": "..."}]
# If absent, we synthesise a smooth schedule: equal drawdowns each construction
# period, prorated for partial periods. This is what most modellers do when
# drawdowns haven't been negotiated yet.
# ---------------------------------------------------------------------------

def resolve_drawdown_schedule(
    tranche: DebtTranche,
    periods: list[ConstructionPeriod],
) -> dict[int, float]:
    """Return {period_index: amount_drawn_in_period}. Sum equals commitment."""
    if tranche.drawdown_phase == DrawdownPhase.OPERATIONS:
        return {}

    if tranche.drawdown_schedule:
        # Map provided dates to periods
        result: dict[int, float] = {}
        for entry in tranche.drawdown_schedule:
            d = date.fromisoformat(entry["date"])
            amount = float(entry["amount_eur"])
            # Find the period containing this date
            for p in periods:
                if p.start <= d < p.end:
                    result[p.index] = result.get(p.index, 0.0) + amount
                    break
            else:
                # Date past COD; ignore — covered by drawdown_phase='both' in operations
                if d < periods[0].start:
                    # Date before construction starts; bucket into first period
                    result[0] = result.get(0, 0.0) + amount
        return result

    # Synthetic: equal weights by period.months
    total_months = sum(p.months for p in periods)
    if total_months == 0:
        return {}
    return {
        p.index: tranche.commitment_eur * (p.months / total_months)
        for p in periods
    }


# ---------------------------------------------------------------------------
# IDC computation — period interest on the average outstanding balance.
# ---------------------------------------------------------------------------

def period_idc(
    outstanding_at_start: float,
    drawn_this_period: float,
    annual_rate_pct: float,
    period_months: float,
) -> float:
    """Approximate IDC: interest on the AVERAGE balance during the period.
    For exact-match with bank models, use mid-period drawing convention."""
    average_balance = outstanding_at_start + drawn_this_period / 2.0
    return average_balance * (annual_rate_pct / 100.0) * (period_months / 12.0)


# ---------------------------------------------------------------------------
# Pre-COD ratios
# ---------------------------------------------------------------------------

def cost_to_complete_coverage(
    cash_on_hand_eur: float,
    undrawn_debt_eur: float,
    undrawn_equity_eur: float,
    contingent_equity_available_eur: float,
    cost_remaining_eur: float,
) -> Optional[float]:
    """(available funds) / (cost remaining). >= 1.0 typical, >= 1.10 strict."""
    if cost_remaining_eur <= 0:
        return None
    available = (
        cash_on_hand_eur
        + undrawn_debt_eur
        + undrawn_equity_eur
        + contingent_equity_available_eur
    )
    return available / cost_remaining_eur


def equity_drawn_ratio(equity_drawn_eur: float, equity_committed_eur: float) -> Optional[float]:
    if equity_committed_eur <= 0:
        return None
    return equity_drawn_eur / equity_committed_eur


def pari_passu_ratio(equity_drawn_eur: float, debt_drawn_eur: float) -> Optional[float]:
    """Equity drawn as a fraction of total funded amount. Should track the
    deal's final D/E split throughout construction — a high ratio early
    means sponsors are doing their share; a low ratio means equity is
    being backloaded behind debt."""
    total = equity_drawn_eur + debt_drawn_eur
    if total <= 0:
        return None
    return equity_drawn_eur / total


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

@dataclass
class PreCODState:
    """Mutable state accumulated through the construction period.
    Returned to the orchestrator so post-COD compute knows initial conditions."""

    summary: PreCODSummary
    # Per-tranche outstanding at COD — what operations starts with
    outstanding_by_tranche_at_cod: dict[str, float]
    cash_at_cod_eur: float
    warnings: list[ComputeWarning]


def run_pre_cod(inputs: DealInputs) -> PreCODState:
    """Walk construction quarter by quarter. Returns the state at COD."""

    deal = inputs.deal
    plant = inputs.plant
    warnings: list[ComputeWarning] = []

    periods = construction_periods(deal.construction_start_date, deal.scheduled_cod_date)
    if not periods:
        warnings.append(ComputeWarning(
            code="precod_zero_length",
            message="Construction period has zero length",
            severity="error",
        ))
        return PreCODState(
            summary=PreCODSummary(),
            outstanding_by_tranche_at_cod={t.id: 0.0 for t in inputs.tranches},
            cash_at_cod_eur=0.0,
            warnings=warnings,
        )

    # Build per-tranche drawdown schedules
    schedules: dict[str, dict[int, float]] = {
        t.id: resolve_drawdown_schedule(t, periods) for t in inputs.tranches
    }

    # Per-period capex demand. If the plant declares a construction profile in
    # plant.data, use it; otherwise spread capex evenly across periods.
    total_capex = plant.capex_eur
    capex_per_period: list[float] = [
        total_capex * (p.months / sum(q.months for q in periods))
        for p in periods
    ]

    # Per-tranche running state
    outstanding: dict[str, float] = {t.id: 0.0 for t in inputs.tranches}
    drawn_total: dict[str, float] = {t.id: 0.0 for t in inputs.tranches}
    idc_accumulated_by_tranche: dict[str, float] = {t.id: 0.0 for t in inputs.tranches}

    # Aggregated deal-level state
    cash_account: float = 0.0  # excess drawings minus capex paid
    total_idc: float = 0.0
    capex_remaining = total_capex
    cost_to_complete_threshold = _find_cost_to_complete_threshold(inputs)
    pari_passu_target = _find_pari_passu_target(inputs)

    period_rows: list[PreCODRatioPoint] = []
    worst_coverage: Optional[float] = None
    worst_breach: Optional[str] = None

    for p in periods:
        # 1) Drawings for this period
        period_drawn_total = 0.0
        for tr in inputs.tranches:
            amount = schedules[tr.id].get(p.index, 0.0)
            if amount <= 0:
                continue
            outstanding[tr.id] += amount
            drawn_total[tr.id] += amount
            cash_account += amount
            period_drawn_total += amount

        # 2) IDC accrual on debt tranches
        period_idc_total = 0.0
        for tr in inputs.debt_tranches():
            if tr.idc_treatment in (None, IDCTreatment.NOT_APPLICABLE):
                continue
            rate = tr.effective_rate_pct()
            # period-opening balance before this period's drawings already in outstanding
            # — but we already added drawings above; subtract them back for average
            opening = outstanding[tr.id] - schedules[tr.id].get(p.index, 0.0)
            idc = period_idc(opening, schedules[tr.id].get(p.index, 0.0), rate, p.months)
            period_idc_total += idc
            idc_accumulated_by_tranche[tr.id] += idc

            if tr.idc_treatment == IDCTreatment.CAPITALISED_FROM_DRAWINGS:
                # Adds to outstanding principal
                outstanding[tr.id] += idc
            # capitalised_from_bridge / from_equity / paid_current handled at
            # the cash-account level — they don't grow the long-term tranche.
            # (Bridge facility modelling lives in a contingent_equity-class tranche.)

        total_idc += period_idc_total

        # 3) Pay out capex
        capex_due = capex_per_period[p.index]
        cash_account -= capex_due
        capex_remaining -= capex_due

        if cash_account < 0:
            warnings.append(ComputeWarning(
                code="precod_cash_negative",
                message=f"Period {p.index}: cash account negative "
                        f"({cash_account:,.0f} EUR). Drawdowns insufficient to "
                        f"meet capex demand of {capex_due:,.0f} EUR.",
                severity="error",
            ))

        # 4) Compute pre-COD ratios at the end of this period
        equity_drawn = sum(drawn_total[t.id] for t in inputs.equity_tranches())
        debt_drawn   = sum(drawn_total[t.id] for t in inputs.debt_tranches())
        equity_committed = inputs.total_equity_commitment_eur()
        undrawn_debt   = sum(t.commitment_eur - drawn_total[t.id] for t in inputs.debt_tranches())
        undrawn_equity = sum(t.commitment_eur - drawn_total[t.id] for t in inputs.equity_tranches())
        contingent_equity_avail = sum(
            t.commitment_eur - drawn_total[t.id]
            for t in inputs.tranches
            if t.tranche_type == TrancheType.CONTINGENT_EQUITY
        )

        ctc = cost_to_complete_coverage(
            cash_on_hand_eur=max(0.0, cash_account),
            undrawn_debt_eur=undrawn_debt,
            undrawn_equity_eur=undrawn_equity,
            contingent_equity_available_eur=contingent_equity_avail,
            cost_remaining_eur=capex_remaining,
        )
        edr = equity_drawn_ratio(equity_drawn, equity_committed)
        ppr = pari_passu_ratio(equity_drawn, debt_drawn)

        breaches: list[str] = []
        if ctc is not None and cost_to_complete_threshold is not None \
           and ctc < cost_to_complete_threshold:
            breaches.append(
                f"cost_to_complete_coverage {ctc:.2f} < threshold "
                f"{cost_to_complete_threshold:.2f}"
            )
        if ppr is not None and pari_passu_target is not None \
           and ppr < pari_passu_target - 0.02:
            breaches.append(
                f"pari_passu_ratio {ppr:.2%} below target "
                f"{pari_passu_target:.2%} (sponsor equity behind schedule)"
            )

        if ctc is not None and (worst_coverage is None or ctc < worst_coverage):
            worst_coverage = ctc
            if breaches:
                worst_breach = breaches[0]

        period_rows.append(PreCODRatioPoint(
            period_index=p.index,
            period_start_date=p.start,
            cost_to_complete_coverage=ctc,
            equity_drawn_ratio=edr,
            pari_passu_ratio=ppr,
            breaches=breaches,
        ))

    summary = PreCODSummary(
        period_rows=period_rows,
        total_idc_capitalised_eur=total_idc,
        final_construction_loan_eur=sum(
            outstanding[t.id] for t in inputs.debt_tranches()
        ),
        worst_cost_to_complete_coverage=worst_coverage,
        worst_breach=worst_breach,
    )

    return PreCODState(
        summary=summary,
        outstanding_by_tranche_at_cod=dict(outstanding),
        cash_at_cod_eur=max(0.0, cash_account),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Threshold extraction from declared pre-COD tests + covenants
# ---------------------------------------------------------------------------

def _find_cost_to_complete_threshold(inputs: DealInputs) -> Optional[float]:
    for t in inputs.precod:
        if t.test_type == "cost_to_complete_coverage" and t.threshold is not None:
            return float(t.threshold)
    return 1.0  # conservative default


def _find_pari_passu_target(inputs: DealInputs) -> Optional[float]:
    """Inferred from the deal's final D/E split: equity / (equity + debt)."""
    eq = inputs.total_equity_commitment_eur()
    dt = inputs.total_debt_commitment_eur()
    total = eq + dt
    if total <= 0:
        return None
    return eq / total
