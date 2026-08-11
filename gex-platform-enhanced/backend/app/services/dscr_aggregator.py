"""
DSCR Aggregator — transforms trading book cashflow projections into
the DSCR heatmap input consumed by DSCRHeatmap.tsx and the CFO Report.

Location: backend/app/services/dscr_aggregator.py

Computation:
    CFADS  = Revenue + Opex (already signed by the cashflow generator)
    DSCR   = CFADS / Debt_Service   (per period)

    The trading book's cashflow rows are pre-signed:
        revenue  → +  (cash in)
        opex     → -  (cash out)
        debt_service → -  (cash out, NOT from trading — see note below)
        capex    → -  (cash out, NOT from trading — see note below)

    CFADS = sum(allocated_amount) for revenue + opex lines only.
    Debt service is separated: DSCR = CFADS / abs(sum(debt_service lines)).

    If no debt_service lines exist (pre-financial-close project), we use
    a synthetic debt service derived from the project's financing assumptions
    stored in the bankability evidence or financial model.

NOTE: debt_service and capex line items are NOT trading cashflows.
    They exist in the PFLineItemType enum so that lender facilities and
    EPC milestone payments can share the same period grid for DSCR
    computation. The trading book proper only originates revenue and opex
    from Buy/Sell contracts for physical tokenised products + derivatives.

Sensitivity stress grid:
    The heatmap stresses DSCR across two axes (matching DSCRHeatmap.tsx):
        X-axis: power/commodity price shocks (-20% to +20%)
        Y-axis: production efficiency shocks (-5pp to +5pp)
    Each cell = DSCR under that joint shock. The stressed CFADS is:
        stressed_revenue = base_revenue × (1 + price_shock) × (1 + eff_shock)
        stressed_CFADS   = stressed_revenue + opex  (opex stays fixed for B1)
        stressed_DSCR    = stressed_CFADS / debt_service
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from app.services.cashflow_client import CashflowProjectionDTO


ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────
# Output models
# ─────────────────────────────────────────────────────────────────


@dataclass
class PeriodDSCR:
    period_start: date
    period_end: date
    revenue: Decimal
    opex: Decimal
    cfads: Decimal
    debt_service: Decimal
    dscr: Optional[Decimal]
    is_estimate: bool


@dataclass
class HeatmapCell:
    power_delta: int
    eff_delta: float
    dscr: float


@dataclass
class SensitivityRow:
    factor: str
    label: str
    unit: str
    delta_labels: list[str]
    values: list[float]


@dataclass
class BreakevenMetric:
    label: str
    value: str
    description: str
    breached: bool


@dataclass
class DSCRResult:
    project_asset_id: str
    project_name: str
    from_date: date
    to_date: date
    base_dscr: float
    min_dscr: float
    avg_dscr: float
    periods: list[PeriodDSCR]
    heatmap_cells: list[HeatmapCell]
    sensitivity_rows: list[SensitivityRow]
    breakeven_metrics: list[BreakevenMetric]
    monthly_series: list[dict]
    has_estimates: bool
    estimate_period_count: int
    debt_service_source: str


# ─────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────


class DSCRAggregator:
    """Pure computation — no I/O. Takes a CashflowProjectionDTO and produces
    the DSCR structure the frontend and CFO Report need."""

    def __init__(
        self,
        annual_debt_service: Optional[Decimal] = None,
        covenant_floor: Decimal = Decimal("1.20"),
    ):
        self.annual_debt_service = annual_debt_service
        self.covenant_floor = covenant_floor

    def compute(self, projection: CashflowProjectionDTO) -> DSCRResult:
        periods = self._aggregate_periods(projection)
        dscr_values = [
            float(p.dscr) for p in periods
            if p.dscr is not None and p.dscr > ZERO
        ]

        base_dscr = sum(dscr_values) / len(dscr_values) if dscr_values else 0.0
        min_dscr = min(dscr_values) if dscr_values else 0.0
        avg_dscr = base_dscr

        total_revenue = sum(p.revenue for p in periods)
        total_opex = sum(p.opex for p in periods)
        total_cfads = sum(p.cfads for p in periods)
        total_ds = sum(p.debt_service for p in periods)

        heatmap = self._build_heatmap(base_dscr, total_revenue, total_opex, total_ds)
        sensitivity = self._build_sensitivity_rows(
            base_dscr, total_revenue, total_opex, total_ds)
        breakevens = self._build_breakevens(
            base_dscr, total_revenue, total_opex, total_ds)
        monthly = self._build_monthly_series(periods)

        ds_source = "contract_lines"
        if total_ds == ZERO and self.annual_debt_service:
            ds_source = "synthetic_assumption"
        elif total_ds == ZERO:
            ds_source = "none_pre_financial_close"

        return DSCRResult(
            project_asset_id=projection.project_asset_id,
            project_name=projection.project_name,
            from_date=projection.from_date,
            to_date=projection.to_date,
            base_dscr=round(base_dscr, 2),
            min_dscr=round(min_dscr, 2),
            avg_dscr=round(avg_dscr, 2),
            periods=periods,
            heatmap_cells=heatmap,
            sensitivity_rows=sensitivity,
            breakeven_metrics=breakevens,
            monthly_series=monthly,
            has_estimates=projection.has_estimates,
            estimate_period_count=projection.estimate_period_count,
            debt_service_source=ds_source,
        )

    # ── Period aggregation ────────────────────────────────────────

    def _aggregate_periods(self, projection: CashflowProjectionDTO) -> list[PeriodDSCR]:
        buckets: dict[tuple[date, date], dict] = {}

        for row in projection.rows:
            key = (row.period_start, row.period_end)
            if key not in buckets:
                buckets[key] = {
                    "revenue": ZERO,
                    "opex": ZERO,
                    "debt_service": ZERO,
                    "capex": ZERO,
                    "is_estimate": False,
                }
            b = buckets[key]
            amt = row.allocated_amount or ZERO

            if row.line_item_type == "revenue":
                b["revenue"] += amt
            elif row.line_item_type == "opex":
                b["opex"] += amt
            elif row.line_item_type == "debt_service":
                b["debt_service"] += amt
            elif row.line_item_type == "capex":
                b["capex"] += amt

            if row.is_estimate:
                b["is_estimate"] = True

        monthly_ds = self._monthly_debt_service()
        periods: list[PeriodDSCR] = []

        for (ps, pe), b in sorted(buckets.items()):
            revenue = b["revenue"]
            opex = b["opex"]
            cfads = revenue + opex

            ds = abs(b["debt_service"])
            if ds == ZERO and monthly_ds:
                ds = monthly_ds

            dscr: Optional[Decimal] = None
            if ds > ZERO:
                dscr = cfads / ds

            periods.append(PeriodDSCR(
                period_start=ps,
                period_end=pe,
                revenue=revenue,
                opex=opex,
                cfads=cfads,
                debt_service=ds,
                dscr=dscr,
                is_estimate=b["is_estimate"],
            ))

        return periods

    def _monthly_debt_service(self) -> Optional[Decimal]:
        if self.annual_debt_service and self.annual_debt_service > ZERO:
            return self.annual_debt_service / Decimal("12")
        return None

    # ── Heatmap grid ──────────────────────────────────────────────

    # ── Sensitivity: delegated to the single shared model ─────────
    # These three builders previously carried their own additive grid and two
    # hand-tuned elasticity tables whose power-price sign disagreed with the
    # grid's. Everything now derives from app/services/dscr_sensitivity.py so
    # the rows are literally slices of the surface.

    def _sensitivity_params(
        self,
        total_revenue: Decimal,
        total_opex: Decimal,
        total_ds: Decimal,
    ) -> dict:
        """
        Map real cashflow aggregates onto the sensitivity model's terms.

        `total_opex` arrives negative in the projection convention; the model
        wants positive cost terms. The power/non-power split is an assumption
        (power dominates e-fuel OPEX) and is surfaced as `power_opex_share` so a
        caller can override it rather than discover it by reading this code.
        """
        from app.services.dscr_sensitivity import normalise_params

        opex_total = abs(float(total_opex))
        power_share = float(getattr(self, "power_opex_share", 0.73))
        return normalise_params({
            "revenue": float(total_revenue),
            "opex_power": opex_total * power_share,
            "opex_other": opex_total * (1.0 - power_share),
            "debt_service": float(total_ds),
        })

    def _build_heatmap(
        self,
        base_dscr: float,
        total_revenue: Decimal,
        total_opex: Decimal,
        total_ds: Decimal,
    ) -> list[HeatmapCell]:
        from app.services.dscr_sensitivity import surface

        if total_ds <= ZERO or total_revenue == ZERO:
            # No cashflow basis: return nothing rather than a plausible-looking
            # grid. A fabricated surface is what a credit analyst cannot detect.
            return []

        p = self._sensitivity_params(total_revenue, total_opex, total_ds)
        return [
            HeatmapCell(
                power_delta=c["powerDelta"],
                eff_delta=c["effDelta"],
                dscr=round(c["dscr"], 2),
            )
            for c in surface(p)
        ]

    def _build_sensitivity_rows(
        self,
        base: float,
        total_revenue: Decimal = ZERO,
        total_opex: Decimal = ZERO,
        total_ds: Decimal = ZERO,
    ) -> list[SensitivityRow]:
        from app.services.dscr_sensitivity import single_factor_rows

        if total_ds <= ZERO or total_revenue == ZERO:
            return []

        p = self._sensitivity_params(total_revenue, total_opex, total_ds)
        return [
            SensitivityRow(
                factor=r["factor"],
                label=r["label"],
                unit=r["unit"],
                delta_labels=r["deltaLabels"],
                values=[round(v, 2) for v in r["values"]],
            )
            for r in single_factor_rows(p)
        ]

    # ── Breakeven metrics ─────────────────────────────────────────

    def _build_breakevens(
        self,
        base: float,
        total_revenue: Decimal = ZERO,
        total_opex: Decimal = ZERO,
        total_ds: Decimal = ZERO,
    ) -> list[BreakevenMetric]:
        """
        Break-evens are SOLVED against the same model, not derived from assumed
        'DSCR per unit' coefficients. The old constants (0.007/pct power,
        0.02/pp efficiency…) encoded a linear world and disagreed with the grid.
        """
        from app.services.dscr_sensitivity import break_even_metrics

        if total_ds <= ZERO or total_revenue == ZERO:
            return []

        p = self._sensitivity_params(total_revenue, total_opex, total_ds)
        return [
            BreakevenMetric(
                label=m["label"],
                value=m["value"],
                description=m["description"],
                breached=m["breached"],
            )
            for m in break_even_metrics(p, float(self.covenant_floor))
        ]

    def _build_monthly_series(self, periods: list[PeriodDSCR]) -> list[dict]:
        return [
            {
                "month": i + 1,
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "dscr": round(float(p.dscr), 2) if p.dscr else None,
                "cfads": str(p.cfads),
                "debt_service": str(p.debt_service),
                "is_estimate": p.is_estimate,
            }
            for i, p in enumerate(periods)
        ]
