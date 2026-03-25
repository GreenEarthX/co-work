"""
GEX Deal Structuring Engine
File: app/core/structuring_engine.py

THE ACTIVE BRAIN OF THE WORKBENCH.

Takes a project's current bankability state and produces a recommended
de-risking package that moves the project toward FID.

Pipeline: gaps → instruments → package → allocation → timeline → recommendation

This is the service that transforms GEX from passive tracking
to active deal structuring.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("gex.structuring_engine")


# ── Data Classes ──

@dataclass
class Gap:
    gap_id: str
    gap_type: str  # OFFTAKE | CERTIFICATION | EPC_WRAP | INSURANCE | FINANCIAL_MODEL | GRID | PERMITS | CAPITAL | REGULATORY
    severity: str  # BLOCKING | DEGRADING | ADVISORY
    description: str
    current_value: str
    required_value: str
    delta: str
    affected_gates: list[str]
    affected_metrics: list[str]  # DSCR | LLCR | WACC | COVERAGE
    risk_category: str  # maps to RiskCategory


@dataclass
class InstrumentMatch:
    gap_id: str
    instrument_id: str
    instrument_name: str
    instrument_type: str
    relevance_score: int  # 0-100
    estimated_wacc_impact_bps: int
    estimated_dscr_impact: float
    estimated_cost_bps: int
    rationale: str


@dataclass
class PackageItem:
    instrument_id: str
    instrument_name: str
    instrument_type: str
    provider: str
    coverage_pct: float
    cost_bps: int
    rate_reduction_bps: int
    gaps_addressed: list[str]
    application_deadline: str
    status: str  # RECOMMENDED | APPLIED | APPROVED | ACTIVE


@dataclass
class DeRiskingPackage:
    package_id: str
    project_id: str
    items: list[PackageItem]
    total_cost_bps: int
    total_rate_reduction_bps: int
    before_wacc_pct: float
    after_wacc_pct: float
    before_dscr: float
    after_dscr: float
    before_state: str
    projected_state: str
    gaps_remaining: list[str]
    stackability_warnings: list[str]
    created_at: str


@dataclass
class RiskAllocationEntry:
    risk_name: str
    risk_category: str
    probability: str  # HIGH | MEDIUM | LOW
    impact: str  # HIGH | MEDIUM | LOW
    bearer: str  # SPONSOR | LENDER | INSURER | DFI | GOVERNMENT | EPC | OEM
    instrument_mitigating: str  # instrument_id or "NONE"
    instrument_name: str
    residual_risk: str  # HIGH | MEDIUM | LOW | NEGLIGIBLE
    residual_cost_bps: int
    allocated_to: str  # who holds residual


@dataclass
class RiskAllocationMatrix:
    project_id: str
    entries: list[RiskAllocationEntry]
    total_mitigated_risks: int
    total_residual_bps: int
    unmitigated_blocking_risks: list[str]


@dataclass
class TimelineItem:
    instrument_id: str
    instrument_name: str
    action: str  # APPLY | NEGOTIATE | EXECUTE | ACTIVATE
    target_date: str
    deadline: str
    dependencies: list[str]  # other instrument_ids that must come first
    owner: str  # who is responsible
    status: str  # PLANNED | IN_PROGRESS | DONE


@dataclass
class StructuringRecommendation:
    project_id: str
    summary: str
    gaps: list[Gap]
    matched_instruments: list[InstrumentMatch]
    package: DeRiskingPackage
    risk_allocation: RiskAllocationMatrix
    timeline: list[TimelineItem]
    before_metrics: dict
    after_metrics: dict
    workflow_state: str  # always starts as DRAFT
    created_at: str


# ── The Engine ──

class StructuringEngine:

    def __init__(self, instrument_registry, risk_pricing_db, demand_aggregation=None):
        self._registry = instrument_registry
        self._pricing = risk_pricing_db
        self._demand = demand_aggregation

    def analyze_gaps(
        self,
        project_id: str,
        gate_scores: dict[str, int],
        bankability_state: str,
        dscr_p50: float,
        dscr_p90: float,
        llcr: float,
        wacc: float,
        offtake_coverage_pct: float,
        cert_readiness: int,
        epc_status: str,
        insurance_status: str,
        grid_status: str,
        jurisdiction: str,
    ) -> list[Gap]:
        gaps = []

        # Offtake gap
        if offtake_coverage_pct < 0.70:
            gaps.append(Gap(
                gap_id="GAP_OFFTAKE",
                gap_type="OFFTAKE",
                severity="BLOCKING",
                description=f"Offtake coverage {offtake_coverage_pct:.0%} below 70% minimum",
                current_value=f"{offtake_coverage_pct:.0%}",
                required_value="70-85%",
                delta=f"{0.70 - offtake_coverage_pct:.0%} shortfall",
                affected_gates=["G4"],
                affected_metrics=["DSCR", "COVERAGE"],
                risk_category="OFFTAKE",
            ))

        # DSCR gap
        if dscr_p50 < 1.30:
            severity = "BLOCKING" if dscr_p50 < 1.20 else "DEGRADING"
            gaps.append(Gap(
                gap_id="GAP_DSCR",
                gap_type="CAPITAL",
                severity=severity,
                description=f"DSCR P50 {dscr_p50:.2f}x below 1.30x target",
                current_value=f"{dscr_p50:.2f}x",
                required_value="1.30x (P50) / 1.20x (P90)",
                delta=f"{1.30 - dscr_p50:.2f}x shortfall",
                affected_gates=["G8", "G10"],
                affected_metrics=["DSCR"],
                risk_category="INTEREST_RATE",
            ))

        # WACC gap
        if wacc > 0.080:
            gaps.append(Gap(
                gap_id="GAP_WACC",
                gap_type="CAPITAL",
                severity="DEGRADING",
                description=f"WACC {wacc:.1%} above 8.0% target — compressing returns",
                current_value=f"{wacc:.1%}",
                required_value="<8.0%",
                delta=f"+{(wacc - 0.080)*10000:.0f}bps above target",
                affected_gates=["G6", "G8", "G10"],
                affected_metrics=["WACC", "DSCR"],
                risk_category="INTEREST_RATE",
            ))

        # Certification gap
        if cert_readiness < 80:
            gaps.append(Gap(
                gap_id="GAP_CERTIFICATION",
                gap_type="CERTIFICATION",
                severity="BLOCKING" if cert_readiness < 60 else "DEGRADING",
                description=f"Certification readiness {cert_readiness}/100 below 80 threshold",
                current_value=f"{cert_readiness}/100",
                required_value="80/100",
                delta=f"{80 - cert_readiness} points shortfall",
                affected_gates=["G2"],
                affected_metrics=["DSCR"],
                risk_category="CERTIFICATION",
            ))

        # EPC gap
        if epc_status in ["NOT_STARTED", "PENDING", "SHORTLISTING"]:
            gaps.append(Gap(
                gap_id="GAP_EPC",
                gap_type="EPC_WRAP",
                severity="BLOCKING" if epc_status == "NOT_STARTED" else "DEGRADING",
                description=f"EPC status: {epc_status} — no performance guarantees available",
                current_value=epc_status,
                required_value="CONTRACT_EXECUTED",
                delta="EPC contract + performance guarantees required",
                affected_gates=["G5", "G6"],
                affected_metrics=["DSCR"],
                risk_category="CONSTRUCTION",
            ))

        # Insurance gap
        if insurance_status not in ["PLACED", "BOUND"]:
            gaps.append(Gap(
                gap_id="GAP_INSURANCE",
                gap_type="INSURANCE",
                severity="DEGRADING",
                description=f"Insurance status: {insurance_status} — G7 incomplete",
                current_value=insurance_status,
                required_value="PLACED",
                delta="CAR/DSU + performance + marine required",
                affected_gates=["G7"],
                affected_metrics=["DSCR"],
                risk_category="CONSTRUCTION",
            ))

        # Grid gap
        if grid_status not in ["CONNECTED", "FIRM_OFFER"]:
            gaps.append(Gap(
                gap_id="GAP_GRID",
                gap_type="GRID",
                severity="BLOCKING" if grid_status == "NOT_APPLIED" else "DEGRADING",
                description=f"Grid status: {grid_status}",
                current_value=grid_status,
                required_value="FIRM_OFFER or CONNECTED",
                delta="Grid connection required for COD",
                affected_gates=["G1"],
                affected_metrics=["DSCR"],
                risk_category="GRID",
            ))

        # Regulatory risk (jurisdiction-based)
        reg_premium = self._pricing.get_regulatory_risk_premium(jurisdiction)
        if reg_premium > 30:
            gaps.append(Gap(
                gap_id="GAP_REGULATORY",
                gap_type="REGULATORY",
                severity="DEGRADING" if reg_premium < 80 else "BLOCKING",
                description=f"Jurisdiction {jurisdiction} carries +{reg_premium}bps regulatory risk premium",
                current_value=f"+{reg_premium}bps",
                required_value="<30bps for investment-grade jurisdictions",
                delta=f"+{reg_premium - 30}bps above threshold",
                affected_gates=["G8", "G10"],
                affected_metrics=["WACC"],
                risk_category="REGULATORY",
            ))

        gaps.sort(key=lambda g: {"BLOCKING": 0, "DEGRADING": 1, "ADVISORY": 2}[g.severity])
        return gaps

    def match_instruments(
        self,
        project_id: str,
        gaps: list[Gap],
        jurisdiction: str,
        molecule: str,
        stage: str,
        project_size_eur: int,
    ) -> list[InstrumentMatch]:
        eligible = self._registry.get_eligible_for_project(
            jurisdiction, molecule, stage, project_size_eur,
        )
        matches = []

        for gap in gaps:
            gap_risk = gap.risk_category
            for inst in eligible:
                if not inst.addresses_risk(getattr(__import__('app.core.instrument_registry', fromlist=['RiskCategory']).RiskCategory, gap_risk, None) or gap_risk):
                    # Fallback: string match on risk category
                    if gap_risk not in [r.value for r in inst.risks_addressed]:
                        continue

                relevance = self._compute_relevance(gap, inst)
                if relevance < 30:
                    continue

                matches.append(InstrumentMatch(
                    gap_id=gap.gap_id,
                    instrument_id=inst.id,
                    instrument_name=inst.name,
                    instrument_type=inst.type.value,
                    relevance_score=relevance,
                    estimated_wacc_impact_bps=inst.effective_rate_reduction_bps,
                    estimated_dscr_impact=round(inst.effective_rate_reduction_bps * 0.0008, 3),
                    estimated_cost_bps=inst.cost_bps,
                    rationale=self._explain_match(gap, inst),
                ))

        matches.sort(key=lambda m: m.relevance_score, reverse=True)
        return matches

    def _compute_relevance(self, gap: Gap, inst) -> int:
        score = 50  # base
        if gap.severity == "BLOCKING":
            score += 20
        if inst.effective_rate_reduction_bps > 60:
            score += 15
        if inst.cost_bps == 0:
            score += 10
        if inst.max_coverage_pct > 0.50:
            score += 5
        return min(score, 100)

    def _explain_match(self, gap: Gap, inst) -> str:
        return (
            f"{inst.name} addresses {gap.gap_type} gap ({gap.severity}). "
            f"Estimated rate reduction: -{inst.effective_rate_reduction_bps}bps at "
            f"{inst.cost_bps}bps cost. Coverage up to {inst.max_coverage_pct:.0%}."
        )

    def assemble_package(
        self,
        project_id: str,
        selected_instrument_ids: list[str],
        current_wacc: float,
        current_dscr: float,
        current_state: str,
        gaps: list[Gap],
    ) -> DeRiskingPackage:
        from app.core.instrument_registry import get_instrument_registry
        registry = get_instrument_registry()

        stackability = registry.check_stackability(selected_instrument_ids)
        items = []
        total_cost = 0
        total_reduction = 0
        gaps_addressed = set()

        for inst_id in selected_instrument_ids:
            inst = registry.get(inst_id)
            if not inst:
                continue

            addressed = [g.gap_id for g in gaps if g.risk_category in [r.value for r in inst.risks_addressed]]
            gaps_addressed.update(addressed)

            items.append(PackageItem(
                instrument_id=inst.id,
                instrument_name=inst.name,
                instrument_type=inst.type.value,
                provider=inst.provider,
                coverage_pct=inst.max_coverage_pct,
                cost_bps=inst.cost_bps,
                rate_reduction_bps=inst.effective_rate_reduction_bps,
                gaps_addressed=addressed,
                application_deadline=inst.application_window,
                status="RECOMMENDED",
            ))
            total_cost += inst.cost_bps
            total_reduction += int(inst.effective_rate_reduction_bps * inst.max_coverage_pct)

        # Compute after-metrics (simplified — production would call PF Engine)
        after_wacc = current_wacc - (total_reduction / 10000)
        after_dscr = current_dscr + (total_reduction * 0.0008)

        # Project state transition
        projected_state = current_state
        if after_dscr >= 1.30 and len([g for g in gaps if g.severity == "BLOCKING" and g.gap_id not in gaps_addressed]) == 0:
            state_map = {
                "BUILDABLE": "STRUCTURALLY_BANKABLE",
                "STRUCTURALLY_BANKABLE": "CREDIT_APPROVED",
                "COMMERCIALLY_PLAUSIBLE": "BUILDABLE",
            }
            projected_state = state_map.get(current_state, current_state)

        remaining = [g.gap_id for g in gaps if g.gap_id not in gaps_addressed]

        return DeRiskingPackage(
            package_id=f"PKG-{project_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
            project_id=project_id,
            items=items,
            total_cost_bps=total_cost,
            total_rate_reduction_bps=total_reduction,
            before_wacc_pct=round(current_wacc * 100, 2),
            after_wacc_pct=round(after_wacc * 100, 2),
            before_dscr=current_dscr,
            after_dscr=round(after_dscr, 3),
            before_state=current_state,
            projected_state=projected_state,
            gaps_remaining=remaining,
            stackability_warnings=stackability.warnings,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def allocate_risks(
        self,
        project_id: str,
        package: DeRiskingPackage,
        gaps: list[Gap],
    ) -> RiskAllocationMatrix:
        entries = []

        # Standard project risks
        standard_risks = [
            ("Construction delay", "CONSTRUCTION", "HIGH", "HIGH", "EPC"),
            ("Technology underperformance", "TECHNOLOGY", "MEDIUM", "HIGH", "OEM"),
            ("Offtake volume shortfall", "OFFTAKE", "MEDIUM", "HIGH", "SPONSOR"),
            ("Power price volatility", "MARKET", "HIGH", "MEDIUM", "SPONSOR"),
            ("Interest rate increase", "INTEREST_RATE", "MEDIUM", "HIGH", "LENDER"),
            ("Currency fluctuation", "FX", "MEDIUM", "MEDIUM", "SPONSOR"),
            ("Regulatory change", "REGULATORY", "LOW", "HIGH", "GOVERNMENT"),
            ("Political risk", "POLITICAL", "LOW", "HIGH", "SPONSOR"),
            ("Certification failure", "CERTIFICATION", "LOW", "HIGH", "SPONSOR"),
            ("Environmental incident", "ENVIRONMENTAL", "LOW", "MEDIUM", "INSURER"),
            ("Grid connection delay", "GRID", "MEDIUM", "HIGH", "SPONSOR"),
            ("Counterparty default", "COUNTERPARTY", "LOW", "HIGH", "LENDER"),
        ]

        instrument_map = {}
        for item in package.items:
            inst = self._registry.get(item.instrument_id)
            if inst:
                for risk in inst.risks_addressed:
                    instrument_map[risk.value] = (item.instrument_id, item.instrument_name)

        for risk_name, category, prob, impact, default_bearer in standard_risks:
            mitigation = instrument_map.get(category, ("NONE", "No instrument"))
            inst_id, inst_name = mitigation

            if inst_id != "NONE":
                residual = "LOW" if impact == "HIGH" else "NEGLIGIBLE"
                residual_bps = 10 if residual == "LOW" else 0
                bearer = "INSURER" if "INSURANCE" in inst_name.upper() else ("DFI" if "DFI" in inst_name.upper() or "EIB" in inst_name.upper() else default_bearer)
            else:
                residual = prob
                residual_bps = 30 if prob == "HIGH" else (15 if prob == "MEDIUM" else 5)
                bearer = default_bearer

            entries.append(RiskAllocationEntry(
                risk_name=risk_name,
                risk_category=category,
                probability=prob,
                impact=impact,
                bearer=bearer,
                instrument_mitigating=inst_id,
                instrument_name=inst_name,
                residual_risk=residual,
                residual_cost_bps=residual_bps,
                allocated_to="SPONSOR" if residual != "NEGLIGIBLE" else "N/A",
            ))

        mitigated = sum(1 for e in entries if e.instrument_mitigating != "NONE")
        total_residual = sum(e.residual_cost_bps for e in entries)
        unmitigated_blocking = [
            e.risk_name for e in entries
            if e.instrument_mitigating == "NONE" and e.impact == "HIGH" and e.probability in ["HIGH", "MEDIUM"]
        ]

        return RiskAllocationMatrix(
            project_id=project_id,
            entries=entries,
            total_mitigated_risks=mitigated,
            total_residual_bps=total_residual,
            unmitigated_blocking_risks=unmitigated_blocking,
        )

    def sequence_timeline(
        self,
        project_id: str,
        package: DeRiskingPackage,
    ) -> list[TimelineItem]:
        timeline = []
        base_date = datetime.now(timezone.utc)

        # Sort by application lead time (longest first — start those earliest)
        sorted_items = sorted(package.items, key=lambda i: self._get_lead_time(i.instrument_id), reverse=True)

        for i, item in enumerate(sorted_items):
            inst = self._registry.get(item.instrument_id)
            lead_weeks = inst.application_lead_time_weeks if inst else 12

            apply_date = base_date + timedelta(weeks=max(2 * i, 1))
            decision_date = apply_date + timedelta(weeks=lead_weeks)

            # Dependencies: grants/DFI first, then commercial instruments
            deps = []
            if inst and inst.provider_type.value in ["COMMERCIAL"]:
                dfi_items = [it for it in sorted_items if self._registry.get(it.instrument_id) and self._registry.get(it.instrument_id).provider_type.value in ["DFI", "MDB"]]
                deps = [it.instrument_id for it in dfi_items[:1]]

            timeline.append(TimelineItem(
                instrument_id=item.instrument_id,
                instrument_name=item.instrument_name,
                action="APPLY",
                target_date=apply_date.strftime("%Y-%m-%d"),
                deadline=item.application_deadline,
                dependencies=deps,
                owner="Finance / Legal",
                status="PLANNED",
            ))
            timeline.append(TimelineItem(
                instrument_id=item.instrument_id,
                instrument_name=item.instrument_name,
                action="DECISION_EXPECTED",
                target_date=decision_date.strftime("%Y-%m-%d"),
                deadline="",
                dependencies=[],
                owner="Provider",
                status="PLANNED",
            ))

        return timeline

    def _get_lead_time(self, instrument_id: str) -> int:
        inst = self._registry.get(instrument_id)
        return inst.application_lead_time_weeks if inst else 12

    def recommend(
        self,
        project_id: str,
        jurisdiction: str,
        molecule: str,
        stage: str,
        project_size_eur: int,
        gate_scores: dict[str, int],
        dscr_p50: float,
        dscr_p90: float,
        llcr: float,
        wacc: float,
        offtake_coverage_pct: float,
        cert_readiness: int,
        epc_status: str,
        insurance_status: str,
        grid_status: str,
    ) -> StructuringRecommendation:
        """
        The full pipeline: gaps → instruments → package → allocation → timeline.
        Returns a single, governed recommendation.
        """
        # Step 1: Gap analysis
        gaps = self.analyze_gaps(
            project_id, gate_scores, stage, dscr_p50, dscr_p90,
            llcr, wacc, offtake_coverage_pct, cert_readiness,
            epc_status, insurance_status, grid_status, jurisdiction,
        )

        # Step 2: Match instruments
        matches = self.match_instruments(
            project_id, gaps, jurisdiction, molecule, stage, project_size_eur,
        )

        # Step 3: Auto-select top instrument per gap (analyst can override)
        selected_ids = []
        seen_gaps = set()
        for match in matches:
            if match.gap_id not in seen_gaps and match.relevance_score >= 50:
                selected_ids.append(match.instrument_id)
                seen_gaps.add(match.gap_id)

        # Deduplicate
        selected_ids = list(dict.fromkeys(selected_ids))

        # Step 4: Assemble package
        package = self.assemble_package(
            project_id, selected_ids, wacc, dscr_p50, stage, gaps,
        )

        # Step 5: Risk allocation
        allocation = self.allocate_risks(project_id, package, gaps)

        # Step 6: Timeline
        timeline = self.sequence_timeline(project_id, package)

        # Step 7: Summary
        blocking_count = sum(1 for g in gaps if g.severity == "BLOCKING")
        summary = (
            f"Project has {len(gaps)} gaps ({blocking_count} blocking). "
            f"Recommended package of {len(package.items)} instruments "
            f"reduces WACC from {package.before_wacc_pct:.1f}% to {package.after_wacc_pct:.1f}%, "
            f"improves DSCR from {package.before_dscr:.2f}x to {package.after_dscr:.2f}x"
        )
        if package.projected_state != package.before_state:
            summary += f", advancing project from {package.before_state} to {package.projected_state}"
        summary += "."

        if package.gaps_remaining:
            summary += f" {len(package.gaps_remaining)} gaps remain unaddressed."

        return StructuringRecommendation(
            project_id=project_id,
            summary=summary,
            gaps=gaps,
            matched_instruments=matches,
            package=package,
            risk_allocation=allocation,
            timeline=timeline,
            before_metrics={
                "wacc_pct": round(wacc * 100, 2),
                "dscr_p50": dscr_p50,
                "dscr_p90": dscr_p90,
                "llcr": llcr,
                "state": stage,
            },
            after_metrics={
                "wacc_pct": package.after_wacc_pct,
                "dscr_p50": package.after_dscr,
                "dscr_p90": round(dscr_p90 + (package.total_rate_reduction_bps * 0.0006), 3),
                "llcr": round(llcr + (package.total_rate_reduction_bps * 0.0005), 3),
                "state": package.projected_state,
            },
            workflow_state="DRAFT",
            created_at=datetime.now(timezone.utc).isoformat(),
        )


# ── Singleton ──

_engine: Optional[StructuringEngine] = None

def get_structuring_engine() -> StructuringEngine:
    global _engine
    if _engine is None:
        from app.core.instrument_registry import get_instrument_registry
        from app.core.risk_pricing import get_risk_pricing_db
        _engine = StructuringEngine(
            instrument_registry=get_instrument_registry(),
            risk_pricing_db=get_risk_pricing_db(),
        )
    return _engine
