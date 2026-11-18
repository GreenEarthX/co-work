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
    gap_type: str  # OFFTAKE | CERTIFICATION | EPC_WRAP | INSURANCE | GRID | CAPITAL | REGULATORY
    severity: str  # BLOCKING | DEGRADING | ADVISORY | NOT_JUDGED
    description: str
    current_value: str
    required_value: str
    delta: str
    affected_gates: list[str]
    affected_metrics: list[str]  # DSCR | WACC | COVERAGE
    risk_category: str  # maps to RiskCategory
    # What the gap concerns (task 3, one mapping table: GAP_MAPPING below).
    kind: str = "REQUIREMENT"            # REQUIREMENT | COMMITMENT | DECISION_TEST
    requirement_key: Optional[str] = None
    requirement_label: Optional[str] = None
    gate_id: Optional[str] = None
    gate_name: Optional[str] = None
    gate_remaining_requirements: list[str] = field(default_factory=list)
    decision_test: Optional[dict] = None
    capital_decisions: list[str] = field(default_factory=list)


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
    before_dscr: Optional[float]
    after_dscr: Optional[float]
    current_state: Optional[str]          # the engine's, unchanged by any package
    conditional_outcome: dict             # what would have to complete; never achieved
    estimates: dict                       # after-figures: ESTIMATE, with the method
    gaps_targeted: list[str]
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

    def analyze_gaps(self, project_id: str, context: dict, policies: Optional[dict] = None) -> list[Gap]:
        """Gaps, each following what it concerns (tasks 2 and 3).

        REQUIREMENT  one per open requirement of G1, G2, G4, G5, G7, in the engine's
                     words. It closes only when that requirement is verified; the
                     gate stays incomplete until all its applicable requirements are.
        COMMITMENT   a gate's open commitment or coherence reason (engine words).
        DECISION_TEST  DSCR, WACC, offtake coverage, regulatory premium: a metric
                     against an attributed policy value. It feeds the capital
                     decision it affects, never a gate. No approved value: NOT_JUDGED.
        """
        from app.core import decision_policy as dp

        snapshot = context.get("_snapshot") or {}
        gaps: list[Gap] = []
        for gate in snapshot.get("gate_evaluations", []):
            mapping = GAP_MAPPING["requirements"].get(gate["gate_id"])
            if not mapping or gate.get("determination") in ("SATISFIED", "WAIVED"):
                continue
            short = gate["gate_id"].split("_")[0]
            details = {d["key"]: d for d in gate.get("evidence_detail", [])}
            open_keys = [k for k in gate.get("blocking_items") or []
                         if details.get(k, {}).get("applicable", True)]
            remaining = [details.get(k, {}).get("label") or k for k in open_keys]
            for key in open_keys:
                d = details.get(key, {})
                gaps.append(Gap(
                    gap_id=f"GAP_{short}_{key}", gap_type=mapping["gap_type"],
                    severity=_SEVERITY.get(d.get("severity"), "DEGRADING"),
                    description=f"{gate['gate_name']}: {d.get('label') or key} — {d.get('status') or 'NOT_STARTED'}",
                    current_value=d.get("status") or "NOT_STARTED",
                    required_value=("VERIFIED" + (f" at {d['required_maturity']}" if d.get("required_maturity") else "")),
                    delta="Requirement not yet verified",
                    affected_gates=[short], affected_metrics=[], risk_category=mapping["risk_category"],
                    kind="REQUIREMENT", requirement_key=key, requirement_label=d.get("label") or key,
                    gate_id=gate["gate_id"], gate_name=gate["gate_name"],
                    gate_remaining_requirements=remaining,
                ))
            for i, reason in enumerate(gate.get("blocked_reasons") or []):
                gaps.append(Gap(
                    gap_id=f"GAP_{short}_REASON_{i}", gap_type=mapping["gap_type"], severity="BLOCKING",
                    description=f"{gate['gate_name']}: {reason}", current_value=reason,
                    required_value="Resolved in the engine's evaluation", delta=reason,
                    affected_gates=[short], affected_metrics=[], risk_category=mapping["risk_category"],
                    kind="COMMITMENT", gate_id=gate["gate_id"], gate_name=gate["gate_name"],
                    gate_remaining_requirements=remaining,
                ))

        # Decision tests: the metric is always shown; judged only against an approved value.
        policies = policies or {}
        reg_premium = self._pricing.get_regulatory_risk_premium(context.get("jurisdiction") or "")
        metrics = {
            "DSCR_P50": context.get("dscr_p50"), "DSCR_P90": context.get("dscr_p90"),
            "WACC": context.get("wacc"), "OFFTAKE_COVERAGE": context.get("offtake_coverage_pct"),
            "REGULATORY_PREMIUM": (reg_premium / 10_000.0) if reg_premium is not None else None,
        }
        g4 = next((g for g in snapshot.get("gate_evaluations", []) if g["gate_id"] == "G4_OFFTAKE_BANKABLE"), None)
        g4_open = list((g4 or {}).get("blocking_items") or [])
        for test_id, value in metrics.items():
            spec = GAP_MAPPING["decision_tests"][test_id]
            result = dp.evaluate(test_id, value, policy=policies.get(dp.DECISION_TESTS[test_id]["policy_key"]))
            if result["outcome"] == dp.PASS:
                continue
            severity = {dp.FAIL: "BLOCKING", dp.NO_THRESHOLD: "NOT_JUDGED",
                        dp.NOT_ASSESSABLE: "NOT_JUDGED"}[result["outcome"]]
            gaps.append(Gap(
                gap_id=f"GAP_TEST_{test_id}", gap_type=spec["gap_type"], severity=severity,
                description=f"{result['label']}: {result['message']}",
                current_value="missing" if value is None else f"{value:g}",
                required_value=(f"{result['comparator']} {result['policy']['value']:g} "
                                f"({result['policy']['status']})" if result.get("policy") else result["message"]),
                delta=result["message"], affected_gates=[], affected_metrics=spec["metrics"],
                risk_category=spec["risk_category"], kind="DECISION_TEST", decision_test=result,
                capital_decisions=result["capital_decisions"],
                # Offtake coverage stays a recorded figure; its gap names the G4 requirements it concerns.
                gate_remaining_requirements=g4_open if test_id == "OFFTAKE_COVERAGE" else [],
            ))
        order = {"BLOCKING": 0, "DEGRADING": 1, "ADVISORY": 2, "NOT_JUDGED": 3}
        gaps.sort(key=lambda g: order[g.severity])
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

    def assemble_package(self, project_id: str, selected_instrument_ids: list[str],
                         current_wacc: Optional[float], current_dscr: Optional[float],
                         context: dict, gaps: list[Gap]) -> DeRiskingPackage:
        """A package of instruments. It changes no state, closes no gap, completes no
        requirement and passes no decision test (task 4): its after-figures are
        ESTIMATES with the method shown, and the next state is conditional."""
        from app.core.instrument_registry import get_instrument_registry
        registry = get_instrument_registry()

        stackability = registry.check_stackability(selected_instrument_ids)
        items, total_cost, total_reduction, targeted = [], 0, 0, set()
        for inst_id in selected_instrument_ids:
            inst = registry.get(inst_id)
            if not inst:
                continue
            addressed = [g.gap_id for g in gaps if g.risk_category in [r.value for r in inst.risks_addressed]]
            targeted.update(addressed)
            items.append(PackageItem(
                instrument_id=inst.id, instrument_name=inst.name, instrument_type=inst.type.value,
                provider=inst.provider, coverage_pct=inst.max_coverage_pct, cost_bps=inst.cost_bps,
                rate_reduction_bps=inst.effective_rate_reduction_bps, gaps_addressed=addressed,
                application_deadline=inst.application_window, status="RECOMMENDED"))
            total_cost += inst.cost_bps
            total_reduction += int(inst.effective_rate_reduction_bps * inst.max_coverage_pct)

        estimates = package_estimates(current_wacc, current_dscr, context.get("dscr_p90"), total_reduction)
        snapshot = context.get("_snapshot") or {}
        return DeRiskingPackage(
            package_id=f"PKG-{project_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
            project_id=project_id, items=items, total_cost_bps=total_cost,
            total_rate_reduction_bps=total_reduction,
            before_wacc_pct=None if current_wacc is None else round(current_wacc * 100, 2),
            after_wacc_pct=estimates["wacc_pct"]["value"],
            before_dscr=current_dscr, after_dscr=estimates["dscr_p50"]["value"],
            current_state=snapshot.get("current_state"),
            conditional_outcome=conditional_outcome(snapshot, context.get("rules")),
            estimates=estimates,
            gaps_targeted=sorted(targeted),
            gaps_remaining=[g.gap_id for g in gaps],
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

    def recommend(self, project_id: str, context: dict, policies: Optional[dict] = None) -> StructuringRecommendation:
        """gaps -> instruments -> package -> allocation -> timeline. The state stays the engine's."""
        gaps = self.analyze_gaps(project_id, context, policies)
        matches = self.match_instruments(project_id, gaps, context.get("jurisdiction"), context.get("molecule"),
                                         context.get("stage"), context.get("project_size_eur") or 0)
        selected_ids, seen = [], set()
        for match in matches:
            if match.gap_id not in seen and match.relevance_score >= 50:
                selected_ids.append(match.instrument_id)
                seen.add(match.gap_id)
        selected_ids = list(dict.fromkeys(selected_ids))
        package = self.assemble_package(project_id, selected_ids, context.get("wacc"), context.get("dscr_p50"),
                                        context, gaps)
        allocation = self.allocate_risks(project_id, package, gaps)
        timeline = self.sequence_timeline(project_id, package)
        blocking = sum(1 for g in gaps if g.severity == "BLOCKING")
        not_judged = sum(1 for g in gaps if g.severity == "NOT_JUDGED")
        summary = (f"{len(gaps)} gaps ({blocking} blocking, {not_judged} not judged for want of an approved "
                   f"threshold or an input). {len(package.items)} instruments targeted. The state stays "
                   f"{package.current_state or 'not evaluated'} until the engine finds the requirements verified; "
                   f"the after-figures are estimates.")
        return StructuringRecommendation(
            project_id=project_id, summary=summary, gaps=gaps, matched_instruments=matches,
            package=package, risk_allocation=allocation, timeline=timeline,
            before_metrics={"wacc": context.get("wacc"), "dscr_p50": context.get("dscr_p50"),
                            "dscr_p90": context.get("dscr_p90"), "llcr": None,
                            "state": package.current_state},
            after_metrics=package.estimates,
            workflow_state="DRAFT", created_at=datetime.now(timezone.utc).isoformat(),
        )


# ── One mapping table (task 3; documented in docs/structuring_gap_mapping.md) ──
# Requirement gaps follow the gate whose evidence they concern. Metric gaps are
# decision tests and follow the capital decision they affect (decision_policy).
GAP_MAPPING = {
    "requirements": {
        "G1_GRID_UTILITIES_REALITY":    {"gap_type": "GRID", "risk_category": "GRID"},
        "G2_CERTIFICATION_PATH_LOCKED": {"gap_type": "CERTIFICATION", "risk_category": "CERTIFICATION"},
        "G4_OFFTAKE_BANKABLE":          {"gap_type": "OFFTAKE", "risk_category": "OFFTAKE"},
        "G5_EPC_RISK_PRICED":           {"gap_type": "EPC_WRAP", "risk_category": "CONSTRUCTION"},
        "G7_INSURANCE_BOUND":           {"gap_type": "INSURANCE", "risk_category": "CONSTRUCTION"},
    },
    "decision_tests": {
        "DSCR_P50": {"gap_type": "CAPITAL", "risk_category": "INTEREST_RATE", "metrics": ["DSCR"]},
        "DSCR_P90": {"gap_type": "CAPITAL", "risk_category": "INTEREST_RATE", "metrics": ["DSCR"]},
        "WACC": {"gap_type": "CAPITAL", "risk_category": "INTEREST_RATE", "metrics": ["WACC"]},
        "OFFTAKE_COVERAGE": {"gap_type": "OFFTAKE", "risk_category": "OFFTAKE", "metrics": ["COVERAGE"]},
        "REGULATORY_PREMIUM": {"gap_type": "REGULATORY", "risk_category": "REGULATORY", "metrics": ["WACC"]},
    },
}
_SEVERITY = {"deal_killer": "BLOCKING", "warning": "DEGRADING", "advisory": "ADVISORY"}

ESTIMATE_METHOD = ("ESTIMATE, not a PF-engine result: WACC less the package's coverage-weighted "
                   "rate reduction; DSCR raised by 0.0008x per bp (P50) and 0.0006x per bp (P90), linear "
                   "proxies with no cash-flow model. An estimate never changes a state, closes a gap, "
                   "completes a requirement or passes a decision test.")


def package_estimates(wacc: Optional[float], dscr_p50: Optional[float], dscr_p90: Optional[float],
                      reduction_bps: int) -> dict:
    def est(value, label):
        return {"value": value, "basis": "ESTIMATE" if value is not None else "NOT_ASSESSABLE", "label": label}
    return {
        "method": ESTIMATE_METHOD,
        "wacc_pct": est(None if wacc is None else round((wacc - reduction_bps / 10_000) * 100, 2), "WACC after package"),
        "dscr_p50": est(None if dscr_p50 is None else round(dscr_p50 + reduction_bps * 0.0008, 3), "DSCR P50 after package"),
        "dscr_p90": est(None if dscr_p90 is None else round(dscr_p90 + reduction_bps * 0.0006, 3), "DSCR P90 after package"),
        "llcr": {"value": None, "basis": "UNAVAILABLE",
                 "label": "LLCR is computed by the PF engine on a returns case; no estimate is shown"},
    }


def conditional_outcome(snapshot: dict, rules: Optional[dict] = None) -> dict:
    """What the next state would need, in the engine's words. Never achieved."""
    if not snapshot:
        return {"label": "conditional — not achieved", "status": "NOT_EVALUATED", "gates": []}
    nxt = snapshot.get("next_state")
    required = (rules or {}).get("state_requirements", {}).get(nxt) if nxt else None
    gate_ids = required if required is not None else (snapshot.get("gates_blocking_next_state") or [])
    gates = []
    for g in snapshot.get("gate_evaluations", []):
        if g["gate_id"] in gate_ids and g.get("determination") not in ("SATISFIED", "WAIVED"):
            details = {d["key"]: d for d in g.get("evidence_detail", [])}
            gates.append({"gate_id": g["gate_id"], "gate_name": g["gate_name"],
                          "open_requirements": [details.get(k, {}).get("label") or k
                                                for k in g.get("blocking_items") or []],
                          "open_reasons": list(g.get("blocked_reasons") or [])})
    return {
        "label": "conditional — not achieved",
        "current_state": snapshot.get("current_state"),
        "would_follow": nxt, "would_follow_label": snapshot.get("next_state_label"),
        "state_requirements_source": "engine /rules state_requirements" if required is not None else
                                     "engine snapshot gates_blocking_next_state",
        "gates": gates,
        "commitments": list(snapshot.get("commitments_blocking_next_state") or []),
    }


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
