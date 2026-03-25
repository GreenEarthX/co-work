"""
GEX Demand Aggregation Service
File: app/core/demand_aggregation.py

Tracks offtake demand signals, LOI pipeline, and aggregates
smaller buyers into bankable volume commitments.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("gex.demand_aggregation")


@dataclass
class DemandSignal:
    signal_id: str
    project_id: str
    buyer_company_id: str
    buyer_name: str
    molecule: str
    volume_tonnes_year: int
    max_price_eur_unit: float
    min_tenor_years: int
    credit_rating: str
    delivery_location: str
    status: str  # EOI | LOI | BINDING_TERM_SHEET | CONTRACT_EXECUTED
    source: str  # DIRECT | H2GLOBAL | PLATFORM_MATCHING | BROKER
    timestamp: str
    notes: str = ""

    @property
    def is_firm(self) -> bool:
        return self.status in ("BINDING_TERM_SHEET", "CONTRACT_EXECUTED")

    @property
    def is_investment_grade(self) -> bool:
        ig_ratings = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"]
        return self.credit_rating.upper() in ig_ratings


@dataclass
class CoverageMetrics:
    project_id: str
    total_production_tonnes: int
    total_demand_tonnes: int
    contracted_pct: float
    loi_pct: float
    eoi_pct: float
    firm_coverage_pct: float
    gap_tonnes: int
    weighted_credit_quality: str
    weighted_tenor_years: float
    signal_count: int
    buyer_count: int
    anchor_buyer: str
    bankable_threshold_met: bool


@dataclass
class AggregationSuggestion:
    group_id: str
    buyer_names: list[str]
    combined_volume_tonnes: int
    combined_coverage_pct: float
    blended_credit: str
    blended_tenor: float
    anchor: str
    rationale: str


@dataclass
class AggregationPlan:
    project_id: str
    suggestions: list[AggregationSuggestion]
    total_aggregated_coverage_pct: float
    meets_threshold: bool
    recommendation: str


class DemandAggregationService:

    def __init__(self):
        self._signals: dict[str, list[DemandSignal]] = {}

    def add_signal(self, signal: DemandSignal) -> None:
        if signal.project_id not in self._signals:
            self._signals[signal.project_id] = []
        self._signals[signal.project_id].append(signal)

    def get_pipeline(self, project_id: str) -> list[DemandSignal]:
        return sorted(
            self._signals.get(project_id, []),
            key=lambda s: {"CONTRACT_EXECUTED": 0, "BINDING_TERM_SHEET": 1, "LOI": 2, "EOI": 3}[s.status],
        )

    def compute_coverage(
        self,
        project_id: str,
        total_production_tonnes: int,
    ) -> CoverageMetrics:
        signals = self._signals.get(project_id, [])
        if not signals or total_production_tonnes == 0:
            return CoverageMetrics(
                project_id=project_id, total_production_tonnes=total_production_tonnes,
                total_demand_tonnes=0, contracted_pct=0, loi_pct=0, eoi_pct=0,
                firm_coverage_pct=0, gap_tonnes=total_production_tonnes,
                weighted_credit_quality="N/A", weighted_tenor_years=0,
                signal_count=0, buyer_count=0, anchor_buyer="None",
                bankable_threshold_met=False,
            )

        contracted = sum(s.volume_tonnes_year for s in signals if s.status == "CONTRACT_EXECUTED")
        binding = sum(s.volume_tonnes_year for s in signals if s.status == "BINDING_TERM_SHEET")
        loi = sum(s.volume_tonnes_year for s in signals if s.status == "LOI")
        eoi = sum(s.volume_tonnes_year for s in signals if s.status == "EOI")
        total = contracted + binding + loi + eoi
        firm = contracted + binding

        # Weighted credit (simplified — use highest firm buyer)
        firm_signals = [s for s in signals if s.is_firm]
        anchor = max(firm_signals, key=lambda s: s.volume_tonnes_year).buyer_name if firm_signals else "None"
        best_credit = firm_signals[0].credit_rating if firm_signals else "N/A"

        # Weighted tenor
        total_vol = sum(s.volume_tonnes_year for s in signals)
        weighted_tenor = sum(s.volume_tonnes_year * s.min_tenor_years for s in signals) / total_vol if total_vol > 0 else 0

        firm_pct = firm / total_production_tonnes
        bankable = firm_pct >= 0.70

        return CoverageMetrics(
            project_id=project_id,
            total_production_tonnes=total_production_tonnes,
            total_demand_tonnes=total,
            contracted_pct=contracted / total_production_tonnes,
            loi_pct=loi / total_production_tonnes,
            eoi_pct=eoi / total_production_tonnes,
            firm_coverage_pct=firm_pct,
            gap_tonnes=max(0, int(total_production_tonnes * 0.70) - firm),
            weighted_credit_quality=best_credit,
            weighted_tenor_years=round(weighted_tenor, 1),
            signal_count=len(signals),
            buyer_count=len(set(s.buyer_company_id for s in signals)),
            anchor_buyer=anchor,
            bankable_threshold_met=bankable,
        )

    def suggest_aggregation(
        self,
        project_id: str,
        total_production_tonnes: int,
        target_coverage_pct: float = 0.70,
    ) -> AggregationPlan:
        signals = self._signals.get(project_id, [])
        coverage = self.compute_coverage(project_id, total_production_tonnes)

        if coverage.bankable_threshold_met:
            return AggregationPlan(
                project_id=project_id,
                suggestions=[],
                total_aggregated_coverage_pct=coverage.firm_coverage_pct,
                meets_threshold=True,
                recommendation="Offtake coverage already meets bankable threshold. No aggregation needed.",
            )

        # Group non-firm signals by compatible characteristics
        non_firm = [s for s in signals if not s.is_firm]
        firm = [s for s in signals if s.is_firm]

        suggestions = []
        if non_firm:
            combined_vol = sum(s.volume_tonnes_year for s in non_firm)
            combined_with_firm = sum(s.volume_tonnes_year for s in firm) + combined_vol
            combined_pct = combined_with_firm / total_production_tonnes

            # Find anchor
            anchor = max(non_firm, key=lambda s: s.volume_tonnes_year * (2 if s.is_investment_grade else 1))

            suggestions.append(AggregationSuggestion(
                group_id="AGG-001",
                buyer_names=[s.buyer_name for s in non_firm],
                combined_volume_tonnes=combined_vol,
                combined_coverage_pct=round(combined_pct, 2),
                blended_credit=anchor.credit_rating,
                blended_tenor=round(sum(s.min_tenor_years for s in non_firm) / len(non_firm), 1),
                anchor=anchor.buyer_name,
                rationale=(
                    f"Pool {len(non_firm)} buyers ({combined_vol:,}t/yr) via GreenMesh aggregation. "
                    f"Anchor: {anchor.buyer_name} ({anchor.credit_rating}). "
                    f"Combined with firm offtake: {combined_pct:.0%} coverage."
                ),
            ))

        total_agg = coverage.firm_coverage_pct + sum(
            s.combined_coverage_pct - coverage.firm_coverage_pct for s in suggestions
        ) if suggestions else coverage.firm_coverage_pct

        meets = total_agg >= target_coverage_pct
        rec = (
            f"Aggregation of {len(non_firm)} buyers brings coverage to {total_agg:.0%}. "
            + ("Threshold met." if meets else f"Still {target_coverage_pct - total_agg:.0%} short. Need additional buyers.")
        )

        return AggregationPlan(
            project_id=project_id,
            suggestions=suggestions,
            total_aggregated_coverage_pct=round(total_agg, 2),
            meets_threshold=meets,
            recommendation=rec,
        )

    def update_signal_status(self, project_id: str, signal_id: str, new_status: str) -> bool:
        for signal in self._signals.get(project_id, []):
            if signal.signal_id == signal_id:
                signal.status = new_status
                signal.timestamp = datetime.now(timezone.utc).isoformat()
                return True
        return False


# ── Singleton ──

_service: Optional[DemandAggregationService] = None

def get_demand_aggregation() -> DemandAggregationService:
    global _service
    if _service is None:
        _service = DemandAggregationService()
    return _service
