# ════════════════════════════════════════════════════════════
# routes_instruments.py — Instrument Registry API
# Prefix: /api/v1/instruments
# ════════════════════════════════════════════════════════════

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.core.deal_killers import DealKillerEngine, KillerSeverity, KillerStatus
from app.core.project_truth import build_deal_killer_project_data

instruments_router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


@instruments_router.get("/")
async def list_instruments(
    jurisdiction: Optional[str] = None,
    molecule: Optional[str] = None,
    instrument_type: Optional[str] = None,
):
    from app.core.instrument_registry import get_instrument_registry, InstrumentType
    registry = get_instrument_registry()
    types = [InstrumentType(instrument_type)] if instrument_type else None
    results = registry.search(
        jurisdiction=jurisdiction, molecule=molecule,
        instrument_types=types,
    )
    return {"count": len(results), "instruments": [vars(i) for i in results]}


@instruments_router.get("/eligible/{project_id}")
async def eligible_instruments(project_id: str):
    from app.core.instrument_registry import get_instrument_registry
    registry = get_instrument_registry()
    ctx = _get_demo_context(project_id)
    results = registry.get_eligible_for_project(
        ctx["jurisdiction"], ctx["molecule"], ctx["stage"], ctx["project_size_eur"],
    )
    return {"project_id": project_id, "eligible_count": len(results),
            "instruments": [{"id": i.id, "name": i.name, "type": i.type.value,
                            "provider": i.provider, "rate_reduction_bps": i.effective_rate_reduction_bps,
                            "cost_bps": i.cost_bps, "coverage": i.max_coverage_pct,
                            "risks_addressed": [r.value for r in i.risks_addressed]}
                           for i in results]}


@instruments_router.post("/stack-check")
async def stack_check(instrument_ids: list[str]):
    from app.core.instrument_registry import get_instrument_registry
    registry = get_instrument_registry()
    result = registry.check_stackability(instrument_ids)
    return vars(result)


@instruments_router.get("/compatibility/{project_id}")
async def instrument_compatibility(project_id: str):
    """
    Instrument Compatibility Panel — shows ALL instrument families with
    eligibility status (eligible / ineligible + reason) for the current project state.

    BRIDGE 1: Deal Killers → Instrument Compatibility
      Active deal killers block specific instruments based on gate→risk mapping.
      Each instrument entry includes `blocked_by_killers` with root-cause detail.

    BRIDGE 2: Price Lineage → Instrument Remedy
      Each eligible instrument includes `remedy_eur_t` — how much it would reduce
      the molecule cost based on forward price and the instrument's bps reduction.
    """
    from app.core.instrument_registry import (
        get_instrument_registry, InstrumentType, RiskCategory, ProceedsType,
    )
    registry = get_instrument_registry()

    # Import demo context from structuring routes
    from app.api.v1.routes_structuring import _get_demo_context
    ctx = _get_demo_context(project_id)

    stage = ctx["stage"]
    jurisdiction = ctx["jurisdiction"]
    molecule = ctx["molecule"]
    size = ctx["project_size_eur"]

    # ── BRIDGE 1: Evaluate deal killers for this project ─────────────────
    dk_engine = DealKillerEngine()
    dk_project_data = build_deal_killer_project_data(project_id)
    all_killers = dk_engine.evaluate(dk_project_data)
    active_killers = [dk for dk in all_killers if dk.current_status == KillerStatus.ACTIVE]
    active_killer_ids = {dk.id for dk in active_killers}

    committee_result = dk_engine.committee_ready(dk_project_data)

    # Map deal killer gates to risk categories they block
    KILLER_BLOCKS_RISKS: dict[str, list[RiskCategory]] = {
        "DK_G4_NO_OFFTAKE": [RiskCategory.OFFTAKE, RiskCategory.MARKET],
        "DK_G5_NO_EPC": [RiskCategory.CONSTRUCTION, RiskCategory.TECHNOLOGY],
        "DK_G7_NO_INSURANCE": [RiskCategory.CONSTRUCTION],
        "DK_G2_CERT_FAIL": [RiskCategory.CERTIFICATION, RiskCategory.REGULATORY],
        "DK_G1_NO_GRID": [RiskCategory.GRID],
    }

    # Map deal killer gates to instrument types they block
    KILLER_BLOCKS_TYPES: dict[str, list[InstrumentType]] = {
        "DK_G4_NO_OFFTAKE": [InstrumentType.OFFTAKE_GUARANTEE, InstrumentType.CFD],
        "DK_G5_NO_EPC": [InstrumentType.PERFORMANCE_GUARANTEE, InstrumentType.CAR_INSURANCE],
        "DK_DSCR_BELOW_FLOOR": [
            InstrumentType.GREEN_BOND, InstrumentType.GREEN_PROJECT_BOND,
            InstrumentType.GREEN_REVENUE_BOND, InstrumentType.GREEN_SECURITIZED_BOND,
        ],
    }

    # Map deal killer gates to required audit nodes they block
    KILLER_BLOCKS_AUDIT_NODES: dict[str, str] = {
        "DK_G6_NO_IE": "IE",
        "DK_G8_NO_AUDIT_MODEL": "MODEL_AUDITOR",
    }

    # Map deal killer gates to certifications they block
    KILLER_BLOCKS_CERTS: dict[str, list[str]] = {
        "DK_G2_CERT_FAIL": ["RFNBO", "RED_III"],
    }

    def _killer_detail(dk):
        return {
            "id": dk.id,
            "gate": dk.gate,
            "severity": dk.severity.value,
            "plain_language": dk.plain_language,
            "resolution_action": dk.resolution_action,
            "resolution_page": dk.resolution_page,
        }

    def _get_blocking_killers(inst) -> list[dict]:
        """Check which active killers block this instrument."""
        blockers = []
        inst_risks = set(inst.risks_addressed)
        inst_audit_nodes = set(getattr(inst, "required_audit_nodes", []))
        inst_certs = set(getattr(inst, "required_certifications", []))

        for dk in active_killers:
            blocked = False

            # Check risk category overlap
            blocked_risks = KILLER_BLOCKS_RISKS.get(dk.id, [])
            if blocked_risks and inst_risks.intersection(blocked_risks):
                blocked = True

            # Check instrument type match
            blocked_types = KILLER_BLOCKS_TYPES.get(dk.id, [])
            if blocked_types and inst.type in blocked_types:
                blocked = True

            # Check audit node requirement
            blocked_node = KILLER_BLOCKS_AUDIT_NODES.get(dk.id)
            if blocked_node and blocked_node in inst_audit_nodes:
                blocked = True

            # Check certification requirement
            blocked_certs = KILLER_BLOCKS_CERTS.get(dk.id, [])
            if blocked_certs and inst_certs.intersection(blocked_certs):
                blocked = True

            if blocked:
                blockers.append(_killer_detail(dk))

        return blockers

    # ── BRIDGE 2: Price context for remedy calculation ───────────────────
    PRICE_CONTEXTS = {
        "H2":         {"forward_price_eur_t": 5620, "financing_spread_eur_t": 148},
        "NH3":        {"forward_price_eur_t": 1200, "financing_spread_eur_t": 85},
        "SAF":        {"forward_price_eur_t": 2800, "financing_spread_eur_t": 112},
        "E_METHANOL": {"forward_price_eur_t": 1050, "financing_spread_eur_t": 62},
        "E_NG":       {"forward_price_eur_t": 95,   "financing_spread_eur_t": 8},
    }
    # Normalize molecule key: demo contexts may use "e-Methanol" etc.
    _molecule_key_map = {
        "h2": "H2", "nh3": "NH3", "saf": "SAF",
        "e-methanol": "E_METHANOL", "e_methanol": "E_METHANOL",
        "e-ng": "E_NG", "e_ng": "E_NG", "eng": "E_NG",
    }
    price_key = _molecule_key_map.get(molecule.lower(), molecule)
    price_ctx = PRICE_CONTEXTS.get(price_key, PRICE_CONTEXTS["H2"])

    # ── Evaluate each instrument ─────────────────────────────────────────
    all_instruments = registry.get_all(active_only=True)
    eligible = set()
    ineligible_reasons: dict[str, list[str]] = {}
    instrument_blockers: dict[str, list[dict]] = {}

    for inst in all_instruments:
        reasons = []
        if not inst.active:
            reasons.append("Instrument inactive")
        if jurisdiction not in inst.jurisdictions and "GLOBAL" not in inst.jurisdictions:
            reasons.append(f"Jurisdiction {jurisdiction} not covered")
        if molecule not in inst.eligible_molecules and "ALL" not in inst.eligible_molecules:
            reasons.append(f"Molecule {molecule} not supported")
        if stage not in inst.eligible_stages and "ALL" not in inst.eligible_stages:
            next_eligible = [s for s in inst.eligible_stages if s != "ALL"]
            reasons.append(f"Stage {stage} not eligible — requires: {', '.join(next_eligible[:3])}")
        if size < inst.min_project_size_eur:
            reasons.append(f"Project size €{size:,.0f} below minimum €{inst.min_project_size_eur:,.0f}")

        # Check required certifications against project context
        if hasattr(inst, 'required_certifications') and inst.required_certifications:
            cert_readiness = ctx.get("cert_readiness", 0)
            if cert_readiness < 80:
                reasons.append(f"Certification readiness {cert_readiness}% — needs ≥80% for {', '.join(inst.required_certifications)}")

        # Check required audit nodes against project context
        if hasattr(inst, 'required_audit_nodes') and inst.required_audit_nodes:
            if "IE" in inst.required_audit_nodes and ctx.get("gate_scores", {}).get("G6", 0) < 50:
                reasons.append("Missing: Independent Engineer sign-off (G6)")
            if "MODEL_AUDITOR" in inst.required_audit_nodes and ctx.get("gate_scores", {}).get("G8", 0) < 80:
                reasons.append("Missing: Audit-grade financial model (G8)")

        # BRIDGE 1: Check deal killer blocking
        blockers = _get_blocking_killers(inst)
        instrument_blockers[inst.id] = blockers

        # If killers block this instrument, add root-cause reasons
        for blocker in blockers:
            reasons.append(
                f"Blocked by {blocker['id']} ({blocker['gate']}): {blocker['plain_language']}"
            )

        if not reasons:
            eligible.add(inst.id)
        else:
            ineligible_reasons[inst.id] = reasons

    # Group by instrument family
    families = {}
    FAMILY_MAP = {
        InstrumentType.GRANT: "Grants & Subsidies",
        InstrumentType.TAX_CREDIT: "Grants & Subsidies",
        InstrumentType.CFD: "Offtake & Revenue Support",
        InstrumentType.OFFTAKE_GUARANTEE: "Offtake & Revenue Support",
        InstrumentType.CONCESSIONAL_LOAN: "Concessional / DFI Debt",
        InstrumentType.BLENDED_FINANCE: "Concessional / DFI Debt",
        InstrumentType.GREEN_BOND: "Green Bonds (Use of Proceeds)",
        InstrumentType.GREEN_REVENUE_BOND: "Green Bonds (Use of Proceeds)",
        InstrumentType.GREEN_PROJECT_BOND: "Green Bonds (Use of Proceeds)",
        InstrumentType.GREEN_SECURITIZED_BOND: "Green Bonds (Use of Proceeds)",
        InstrumentType.ESG_LINKED_BOND: "ESG-Linked (General Purpose)",
        InstrumentType.SUSTAINABILITY_LINKED_LOAN: "ESG-Linked (General Purpose)",
        InstrumentType.PARTIAL_CREDIT_GUARANTEE: "Guarantees & Credit Enhancement",
        InstrumentType.GCGC: "Guarantees & Credit Enhancement",
        InstrumentType.PERFORMANCE_GUARANTEE: "Guarantees & Credit Enhancement",
        InstrumentType.TECH_GUARANTEE: "Guarantees & Credit Enhancement",
        InstrumentType.EXPORT_CREDIT: "Export Credit & Political Risk",
        InstrumentType.POLITICAL_RISK_INSURANCE: "Export Credit & Political Risk",
        InstrumentType.FX_GUARANTEE: "Export Credit & Political Risk",
        InstrumentType.CAR_INSURANCE: "Insurance",
        InstrumentType.INTEREST_RATE_SWAP: "Hedging",
    }

    for inst in all_instruments:
        family = FAMILY_MAP.get(inst.type, "Other")
        if family not in families:
            families[family] = {"eligible": [], "ineligible": []}

        entry = {
            "id": inst.id,
            "name": inst.name,
            "type": inst.type.value,
            "provider": inst.provider,
            "rate_reduction_bps": inst.effective_rate_reduction_bps,
            "coverage": inst.max_coverage_pct,
            "proceeds_type": getattr(inst, 'proceeds_type', ProceedsType.GENERAL_PURPOSE).value,
            "bond_framework": getattr(inst, 'bond_framework', 'NONE'),
            "required_audit_nodes": getattr(inst, 'required_audit_nodes', []),
            "esg_metrics": [{"kpi_name": m.kpi_name, "target_value": m.target_value,
                            "target_unit": m.target_unit, "penalty_bps": m.penalty_bps,
                            "verification_agent": m.verification_agent}
                           for m in getattr(inst, 'esg_metrics', [])],
            # BRIDGE 1: Deal killer blocking detail
            "blocked_by_killers": instrument_blockers.get(inst.id, []),
        }

        if inst.id in eligible:
            entry["status"] = "ELIGIBLE"
            # BRIDGE 2: Remedy calculation for eligible instruments
            if inst.effective_rate_reduction_bps > 0:
                entry["remedy_eur_t"] = round(
                    price_ctx["forward_price_eur_t"] * inst.effective_rate_reduction_bps / 10000, 1
                )
            else:
                entry["remedy_eur_t"] = 0.0
            families[family]["eligible"].append(entry)
        else:
            entry["status"] = "INELIGIBLE"
            entry["reasons"] = ineligible_reasons.get(inst.id, ["Unknown"])
            entry["remedy_eur_t"] = None  # not applicable when ineligible
            families[family]["ineligible"].append(entry)

    # Compute summary
    total = len(all_instruments)
    eligible_count = len(eligible)

    return {
        "project_id": project_id,
        "project_state": stage,
        "jurisdiction": jurisdiction,
        "molecule": molecule,
        "total_instruments": total,
        "eligible_count": eligible_count,
        "ineligible_count": total - eligible_count,
        "families": families,
        # BRIDGE 1: Active deal killers summary
        "active_killers": [_killer_detail(dk) for dk in active_killers],
        "committee_readiness": committee_result["status"],
        # BRIDGE 2: Price context for remedy reference
        "price_context": {
            "forward_price_eur_t": price_ctx["forward_price_eur_t"],
            "financing_spread_eur_t": price_ctx["financing_spread_eur_t"],
            "molecule": price_key,
        },
    }


@instruments_router.get("/{instrument_id}")
async def get_instrument(instrument_id: str):
    from app.core.instrument_registry import get_instrument_registry
    registry = get_instrument_registry()
    inst = registry.get(instrument_id)
    if not inst:
        raise HTTPException(404, f"Instrument not found: {instrument_id}")
    return vars(inst)