"""
Project Truth API

One project-aware endpoint for the dashboard front door.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from app.core.deal_killers import DealKillerEngine, KillerSeverity
from app.core.instrument_registry import get_instrument_registry
from app.core.project_registry import get_project_profile
from app.core.project_truth import (
    build_deal_killer_project_data,
    build_task_router_project_data,
    get_project_truth,
)
from app.core.task_router import ActorType, task_router_engine
from app.core.config import settings

router = APIRouter(prefix="/project-truth", tags=["project-truth"])

deal_killer_engine = DealKillerEngine()
instrument_registry = get_instrument_registry()


GATE_DEFS: dict[str, dict[str, Any]] = {
    "G0": {"name": "Site Rights & Social License", "owners": ["Producer", "Executive"]},
    "G1": {"name": "Power, Utilities & Technology Basis", "owners": ["Producer"]},
    "G2": {"name": "Green Certification Pathway", "owners": ["Regulator"]},
    "G3": {"name": "Feedstock & Logistics Terms", "owners": ["Producer"]},
    "G4": {"name": "Binding Offtake", "owners": ["Finance"]},
    "G5": {"name": "EPC Risk Priced", "owners": ["Producer", "Executive"]},
    "G6": {"name": "Independent Engineer Sign-off", "owners": ["Finance", "Regulator"]},
    "G7": {"name": "Insurability Confirmed", "owners": ["Finance"]},
    "G8": {"name": "Audit-Grade Financial Model", "owners": ["Finance"]},
    "G9": {"name": "Permits Granted & Appeal Risk Managed", "owners": ["Producer", "Regulator"]},
    "G10": {"name": "Financial Close", "owners": ["Finance"]},
    "G11": {"name": "COD & Stabilization", "owners": ["Producer", "Executive"]},
}

ROLE_GATE_SCOPE: dict[str, list[str]] = {
    "PRODUCER": ["G0", "G1", "G3", "G5", "G9", "G11"],
    "OFFTAKER": ["G4"],
    "COMMERCIAL_BANKER": ["G4", "G6", "G7", "G8", "G10"],
    "INSURER": ["G5", "G6", "G7"],
    "REGULATOR": ["G2", "G6", "G9"],
    "EXECUTIVE": list(GATE_DEFS.keys()),
    "GUEST": [],
}

SERVICE_ROLE_MAP = {
    "BANK": "COMMERCIAL_BANKER",
    "INSURER": "INSURER",
    "CERTIFIER": "REGULATOR",
    "LEGAL": "REGULATOR",
}

# Project facts come from PostgreSQL (`projects`) only. The FALLBACK_PROJECT_META
# dictionary that stood here — a third copy of project data in code — and the
# SQLite `capacities` read that preferred it were removed on 2026-10-25.

STAGE_BY_STATUS = {
    "development": "BUILDABLE",
    "construction": "FINANCEABLE",
    "commissioning": "FINANCEABLE",
    "operating": "OPERATIONAL",
}

MOLECULE_MAP = {
    "H2": "H2",
    "NH3": "NH3",
    "SAF": "SAF",
    "e-Methanol": "E_METHANOL",
    "e-NG": "E_NG",
}


def _short_gate_id(gate_id: str) -> str:
    return gate_id.split("_", 1)[0] if "_" in gate_id else gate_id


def _scope_roles(
    company_type: str | None,
    business_function: str | None,
    service_type: str | None,
    capabilities: list[str],
) -> list[str]:
    if business_function == "EXECUTIVE":
        return ["EXECUTIVE"]

    roles: list[str] = []
    cap_set = set(capabilities)

    if company_type == "PRODUCER" or "PRODUCE" in cap_set:
        roles.append("PRODUCER")
    if company_type == "OFFTAKER" or "OFFTAKE" in cap_set:
        roles.append("OFFTAKER")
    if company_type == "THIRD_PARTY" and service_type:
        mapped = SERVICE_ROLE_MAP.get(service_type)
        if mapped:
            roles.append(mapped)
    if business_function == "COMPLIANCE_LEGAL":
        roles.append("REGULATOR")
    if business_function == "FINANCE_TREASURY":
        roles.append("COMMERCIAL_BANKER")

    return roles or ["GUEST"]


def _visible_gates(
    company_type: str | None,
    business_function: str | None,
    service_type: str | None,
    capabilities: list[str],
) -> list[str]:
    gates: list[str] = []
    for role in _scope_roles(company_type, business_function, service_type, capabilities):
        for gate_id in ROLE_GATE_SCOPE.get(role, []):
            if gate_id not in gates:
                gates.append(gate_id)
    return gates


def _actor_type(company_type: str | None, business_function: str | None, service_type: str | None) -> ActorType:
    if business_function == "EXECUTIVE":
        return ActorType.CREDIT_COMMITTEE_CHAIR
    if company_type == "OFFTAKER":
        return ActorType.OFFTAKER
    if service_type == "BANK" or business_function == "FINANCE_TREASURY":
        return ActorType.COMMERCIAL_BANKER
    return ActorType.PRODUCER


def _actor_owner_label(actor_type: ActorType) -> str:
    if actor_type == ActorType.CREDIT_COMMITTEE_CHAIR:
        return "Executive"
    if actor_type == ActorType.COMMERCIAL_BANKER:
        return "Finance"
    if actor_type == ActorType.OFFTAKER:
        return "Commercial"
    return "Producer"


def _scope_readiness(active_killers: list[Any]) -> str:
    if any(k.severity == KillerSeverity.FATAL for k in active_killers):
        return "NOT_READY"
    if active_killers:
        return "CONDITIONAL"
    return "READY"


def _load_project_meta(project_id: str) -> dict[str, Any]:
    """The project's headline facts from PostgreSQL; a fact not recorded is None."""
    from app.core.projects_store import fetch_project

    row = fetch_project(project_id) or {}
    profile = get_project_profile(project_id)
    return {
        "project_name": row.get("project_name"),
        "molecule": row.get("molecule"),
        "location": row.get("location"),
        "status": row.get("status"),
        "capex_eur": float(row["capex_eur"]) if row.get("capex_eur") is not None else None,
        "jurisdiction": profile.jurisdiction if profile and profile.jurisdiction else None,
    }


def _owner_load(visible_gates: list[str], blockers_in_scope: list[Any]) -> list[dict[str, Any]]:
    blocked_gate_ids = {_short_gate_id(killer.gate) for killer in blockers_in_scope}
    owner_map: dict[str, dict[str, Any]] = {}

    for gate_id in visible_gates:
        gate_def = GATE_DEFS.get(gate_id, {"owners": ["Unassigned"]})
        for owner in gate_def["owners"]:
            record = owner_map.setdefault(
                owner,
                {"owner": owner, "scope_topics": 0, "blocked_topics": 0, "gates": []},
            )
            record["scope_topics"] += 1
            if gate_id in blocked_gate_ids:
                record["blocked_topics"] += 1
            if gate_id not in record["gates"]:
                record["gates"].append(gate_id)

    return sorted(
        owner_map.values(),
        key=lambda item: (-item["blocked_topics"], -item["scope_topics"], item["owner"]),
    )


def _gate_scope_items(visible_gates: list[str], blockers_in_scope: list[Any]) -> list[dict[str, Any]]:
    blocked_gate_ids = {_short_gate_id(killer.gate) for killer in blockers_in_scope}
    items: list[dict[str, Any]] = []
    for gate_id in visible_gates:
        gate_def = GATE_DEFS.get(gate_id, {"name": gate_id, "owners": ["Unassigned"]})
        items.append(
            {
                "gate_id": gate_id,
                "gate_name": gate_def["name"],
                "owners": gate_def["owners"],
                "status": "BLOCKED" if gate_id in blocked_gate_ids else "IN_SCOPE",
            }
        )
    return items


def _eligible_instruments(meta: dict[str, Any]) -> list[dict[str, Any]]:
    # Eligibility needs the project's real jurisdiction, size and molecule. When
    # one is not recorded there is no answer — never a guessed one (it used to
    # assume DE, 200M EUR and H2).
    molecule = MOLECULE_MAP.get(meta.get("molecule") or "")
    jurisdiction = meta.get("jurisdiction")
    if not (molecule and jurisdiction and meta.get("capex_eur")):
        return []
    stage = STAGE_BY_STATUS.get(meta.get("status") or "development", "BUILDABLE")
    project_size_eur = int(meta["capex_eur"])

    results = instrument_registry.get_eligible_for_project(
        jurisdiction=jurisdiction,
        molecule=molecule,
        stage=stage,
        project_size_eur=project_size_eur,
    )
    top = sorted(results, key=lambda inst: inst.effective_rate_reduction_bps, reverse=True)[:3]
    return [
        {
            "id": inst.id,
            "name": inst.name,
            "type": inst.type.value,
            "provider": inst.provider,
            "coverage_pct": round(inst.max_coverage_pct * 100),
            "rate_reduction_bps": inst.effective_rate_reduction_bps,
        }
        for inst in top
    ]


def _capital_path(meta: dict[str, Any], all_active_killers: list[Any], blockers_in_scope: list[Any]) -> dict[str, Any]:
    status = meta.get("status", "development")
    if any(k.severity == KillerSeverity.FATAL for k in blockers_in_scope):
        return {
            "status": "BLOCKED",
            "headline": "No capital advance while in-scope fatal blockers remain",
            "detail": "Resolve the blocker chain in your visible gate scope before pushing the next capital event.",
        }
    if blockers_in_scope:
        return {
            "status": "CONDITIONAL",
            "headline": "Capital progression remains conditional",
            "detail": "Critical issues remain in your gate scope. Progress is possible only with explicit waivers or parallel resolution.",
        }
    if any(k.severity == KillerSeverity.FATAL for k in all_active_killers):
        return {
            "status": "WAITING_ON_OTHERS",
            "headline": "Your scope is clear, but capital is still blocked elsewhere",
            "detail": "This project still carries fatal blockers outside your current gate scope.",
        }
    if status == "operating":
        return {
            "status": "OPEN",
            "headline": "Refinancing and green bond eligibility",
            "detail": "Operating assets with resolved blocker chains should move toward refinance and portfolio-style capital rotation.",
        }
    if status in {"construction", "commissioning"}:
        return {
            "status": "OPEN",
            "headline": "Debt drawdown and completion capital",
            "detail": "The next capital move is construction drawdown discipline, completion support, and covenant protection.",
        }
    return {
        "status": "OPEN",
        "headline": "Strategic equity and senior debt preparation",
        "detail": "The next move is to convert evidence and contracts into bankable funding readiness.",
    }


@router.get("/{project_id}")
async def get_project_truth_view(
    project_id: str,
    company_type: str | None = Query(default=None),
    business_function: str | None = Query(default=None),
    service_type: str | None = Query(default=None),
    capabilities: str | None = Query(default=None),
) -> dict[str, Any]:
    """
    Return one dashboard-ready project truth object.
    """
    capability_list = [cap.strip() for cap in (capabilities or "").split(",") if cap.strip()]
    visible_gates = _visible_gates(company_type, business_function, service_type, capability_list)

    meta = _load_project_meta(project_id)
    truth = get_project_truth(project_id)
    project_data = build_deal_killer_project_data(project_id)
    task_data = build_task_router_project_data(project_id)

    active_killers = deal_killer_engine.get_active_killers(project_data)
    scoped_killers = [
        killer for killer in active_killers if _short_gate_id(killer.gate) in visible_gates
    ]
    hidden_killer_count = max(len(active_killers) - len(scoped_killers), 0)

    actor_type = _actor_type(company_type, business_function, service_type)
    actor_owner = _actor_owner_label(actor_type)
    task_data["active_fatal_killers"] = len(
        [killer for killer in active_killers if killer.severity == KillerSeverity.FATAL]
    )
    flow = task_router_engine.get_flow(actor_type, project_id, task_data)

    top_blocker = scoped_killers[0] if scoped_killers else (active_killers[0] if active_killers else None)
    top_blocker_owner = (
        GATE_DEFS.get(_short_gate_id(top_blocker.gate), {}).get("owners", ["Unassigned"])[0]
        if top_blocker
        else actor_owner
    )

    evidence_total = truth.get("task_router", {}).get("evidence_total_count", 0)
    evidence_audited = truth.get("task_router", {}).get("evidence_audited_count", 0)
    evidence_confirmed = truth.get("task_router", {}).get("evidence_confirmed_pct", 0)

    return {
        "project_id": project_id,
        "project_name": meta.get("project_name") or truth.get("project_name") or project_id,
        "molecule": meta.get("molecule") or truth.get("molecule") or "",
        "location": meta.get("location") or "Not recorded",
        "status": meta.get("status") or "Not recorded",
        "objective": flow.objective,
        "scope_readiness": _scope_readiness(scoped_killers),
        "overall_readiness": deal_killer_engine.committee_ready(project_data)["status"],
        "scope_note": (
            "No visible gates in current scope."
            if not visible_gates
            else f"{len(visible_gates)} gate(s) in your scope."
        ),
        "top_blocker": {
            "id": top_blocker.id if top_blocker else None,
            "gate": _short_gate_id(top_blocker.gate) if top_blocker else None,
            "severity": top_blocker.severity.value if top_blocker else None,
            "plain_language": top_blocker.plain_language if top_blocker else "No active blocker in your current scope.",
            "action": top_blocker.resolution_action if top_blocker else flow.next_action,
            "page": top_blocker.resolution_page if top_blocker else flow.next_action_page,
            "owner": top_blocker_owner,
        },
        "next_action": {
            "label": flow.next_action,
            "page": flow.next_action_page,
            "owner": top_blocker_owner if top_blocker else actor_owner,
        },
        "evidence": {
            "confirmed_pct": evidence_confirmed,
            "audited_count": evidence_audited,
            "total_count": evidence_total,
        },
        "gate_scope": {
            "visible_count": len(visible_gates),
            "items": _gate_scope_items(visible_gates, scoped_killers),
        },
        "blockers": {
            "fatal_count": len([killer for killer in scoped_killers if killer.severity == KillerSeverity.FATAL]),
            "critical_count": len([killer for killer in scoped_killers if killer.severity == KillerSeverity.CRITICAL]),
            "hidden_count": hidden_killer_count,
            "items": [
                {
                    "id": killer.id,
                    "gate": _short_gate_id(killer.gate),
                    "severity": killer.severity.value,
                    "plain_language": killer.plain_language,
                    "action": killer.resolution_action,
                    "page": killer.resolution_page,
                }
                for killer in scoped_killers
            ],
        },
        "owners": _owner_load(visible_gates, scoped_killers),
        "eligible_instruments": _eligible_instruments(meta),
        "capital_path": _capital_path(meta, active_killers, scoped_killers),
    }
