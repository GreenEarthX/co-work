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
        sensitivity = self._build_sensitivity_rows(base_dscr)
        breakevens = self._build_breakevens(base_dscr)
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

    def _build_heatmap(
        self,
        base_dscr: float,
        total_revenue: Decimal,
        total_opex: Decimal,
        total_ds: Decimal,
    ) -> list[HeatmapCell]:
        power_deltas = [-20, -10, 0, 10, 20]
        eff_deltas = [5.0, 2.5, 0.0, -2.5, -5.0]
        cells = []

        for pd in power_deltas:
            for ed in eff_deltas:
                if total_ds > ZERO and total_revenue != ZERO:
                    price_factor = Decimal(1) + Decimal(str(pd)) / Decimal(100)
                    eff_factor = Decimal(1) + Decimal(str(ed)) / Decimal(100)
                    stressed_rev = total_revenue * price_factor * eff_factor
                    stressed_cfads = stressed_rev + total_opex
                    dscr = float(stressed_cfads / total_ds)
                else:
                    power_effect = (pd / 10) * (-0.07)
                    eff_effect = (ed / 2.5) * 0.06
                    dscr = max(0.60, base_dscr + power_effect + eff_effect)

                cells.append(HeatmapCell(
                    power_delta=pd,
                    eff_delta=ed,
                    dscr=round(max(0.60, dscr), 2),
                ))

        return cells

    # ── Sensitivity rows ──────────────────────────────────────────

    def _build_sensitivity_rows(self, base: float) -> list[SensitivityRow]:
        elasticities = {
            "power_price":    (
                "Power Price", "€/MWh",
                ["-20%", "-10%", "Base", "+10%", "+20%"],
                [-0.14, -0.07, 0, 0.07, 0.14],
            ),
            "efficiency":     (
                "System Efficiency", "%",
                ["-5pp", "-2.5pp", "Base", "+2.5pp", "+5pp"],
                [0.18, 0.09, 0, -0.06, -0.10],
            ),
            "capex":          (
                "CapEx", "€M",
                ["-20%", "-10%", "Base", "+10%", "+20%"],
                [0.12, 0.06, 0, -0.07, -0.15],
            ),
            "cod_delay":      (
                "COD Delay", "months",
                ["-6m", "-3m", "Base", "+3m", "+6m"],
                [0.05, 0.02, 0, -0.06, -0.13],
            ),
            "curtailment":    (
                "Curtailment", "%",
                ["-20%", "-10%", "Base", "+10%", "+20%"],
                [0.08, 0.04, 0, -0.05, -0.10],
            ),
            "logistics_cost": (
                "Logistics Cost", "€/kg",
                ["-20%", "-10%", "Base", "+10%", "+20%"],
                [0.04, 0.02, 0, -0.04, -0.08],
            ),
            "interest_rate":  (
                "Interest Rate", "bps",
                ["-150bps", "-75bps", "Base", "+75bps", "+150bps"],
                [0.16, 0.08, 0, -0.08, -0.17],
            ),
        }

        rows = []
        for factor, (label, unit, delta_labels, deltas) in elasticities.items():
            rows.append(SensitivityRow(
                factor=factor,
                label=label,
                unit=unit,
                delta_labels=delta_labels,
                values=[round(max(0.60, base + d), 2) for d in deltas],
            ))
        return rows

    # ── Breakeven metrics ─────────────────────────────────────────

    def _build_breakevens(self, base: float) -> list[BreakevenMetric]:
        floor = float(self.covenant_floor)
        headroom = base - floor
        breached = base < floor

        dscr_per_pct_power = 0.007
        dscr_per_pp_eff = 0.02
        dscr_per_pct_capex = 0.015
        dscr_per_bps = 0.08 / 75

        max_power_pct = headroom / dscr_per_pct_power if not breached else 0
        base_power = 65.0
        floor_power = base_power * (1 + max_power_pct / 100)

        min_eff_drop = headroom / dscr_per_pp_eff if not breached else 0
        base_eff = 72.0
        min_eff = base_eff - min_eff_drop

        max_capex_pct = headroom / dscr_per_pct_capex if not breached else 0
        max_rate_bps = int(headroom / dscr_per_bps) if not breached else 0

        return [
            BreakevenMetric(
                label="Floor power price",
                value=f"€{floor_power:.1f}/MWh",
                description=f"Max power price before DSCR < {floor}x",
                breached=breached,
            ),
            BreakevenMetric(
                label="Min system efficiency",
                value=f"{min_eff:.1f}%",
                description=f"Minimum efficiency before DSCR < {floor}x",
                breached=breached,
            ),
            BreakevenMetric(
                label="Max CapEx overrun",
                value=f"+{max_capex_pct:.0f}%" if not breached else "Already breached",
                description=f"Maximum CapEx overrun before DSCR < {floor}x",
                breached=breached,
            ),
            BreakevenMetric(
                label="Max rate rise",
                value=f"+{max_rate_bps}bps" if not breached else "Already breached",
                description=f"Maximum rate increase before DSCR < {floor}x",
                breached=breached,
            ),
        ]

    # ── Monthly series ────────────────────────────────────────────

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
