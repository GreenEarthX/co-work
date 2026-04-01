"""
Project Truth Registry
======================

Small project-aware truth layer used by guided UX endpoints.

This is not the final system of record. It is a transitional bridge that:
- replaces one-size-fits-all demo payloads with project-specific truth
- keeps task routing and deal-killer evaluation aligned
- can merge runtime evidence counts from bankability SQLite state when present

The long-term destination is a database-backed project truth service. For now,
this file removes the worst failure mode: every project returning the same flow.
"""

from __future__ import annotations

import copy
import os
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = os.getenv("GEX_DB_PATH", "greenearth.db")


DEFAULT_PROJECT_TRUTH: dict[str, Any] = {
    "project_name": "Generic Green Fuel Project",
    "molecule": "H2",
    "deal_killers": {
        "offtake_binding_pct": 40,
        "epc_contract_executed": False,
        "ie_appointed": False,
        "financial_model_status": "IE_REVIEWED",
        "insurance_fully_placed": False,
        "rfnbo_pathway_viable": True,
        "dscr_p90": 1.08,
        "grid_connection_firm": False,
    },
    "task_router": {
        "snapshot_viewed_within_7_days": False,
        "evidence_confirmed_pct": 38.0,
        "capital_stack_committed": False,
        "requirement_defined": False,
        "qualified_offers_count": 0,
        "pricing_reference_ready": False,
        "shortlist_count": 0,
        "evidence_audited_count": 2,
        "evidence_total_count": 18,
        "plant_configured": False,
        "next_gate_missing_items": 5,
        "g8_is_audit_grade": False,
    },
}


PROJECT_TRUTH: dict[str, dict[str, Any]] = {
    "proj_bremen_h2": {
        "project_name": "Bremen Green Hydrogen Plant",
        "molecule": "H2",
        "deal_killers": {
            "offtake_binding_pct": 72,
            "epc_contract_executed": True,
            "ie_appointed": True,
            "financial_model_status": "IE_REVIEWED",
            "insurance_fully_placed": False,
            "rfnbo_pathway_viable": True,
            "dscr_p90": 1.26,
            "grid_connection_firm": False,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": True,
            "evidence_confirmed_pct": 68.0,
            "capital_stack_committed": False,
            "requirement_defined": True,
            "qualified_offers_count": 2,
            "pricing_reference_ready": False,
            "shortlist_count": 1,
            "evidence_audited_count": 4,
            "evidence_total_count": 12,
            "plant_configured": True,
            "next_gate_missing_items": 2,
            "g8_is_audit_grade": False,
        },
    },
    "proj_rotterdam_nh3": {
        "project_name": "Rotterdam Green Ammonia Terminal",
        "molecule": "NH3",
        "deal_killers": {
            "offtake_binding_pct": 20,
            "epc_contract_executed": False,
            "ie_appointed": False,
            "financial_model_status": "SELF_ASSESSED",
            "insurance_fully_placed": False,
            "rfnbo_pathway_viable": True,
            "dscr_p90": 1.02,
            "grid_connection_firm": False,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": False,
            "evidence_confirmed_pct": 31.0,
            "capital_stack_committed": False,
            "requirement_defined": False,
            "qualified_offers_count": 0,
            "pricing_reference_ready": False,
            "shortlist_count": 0,
            "evidence_audited_count": 1,
            "evidence_total_count": 15,
            "plant_configured": False,
            "next_gate_missing_items": 6,
            "g8_is_audit_grade": False,
        },
    },
    "proj_sansebastian_emethanol": {
        "project_name": "Project Helios e-Methanol",
        "molecule": "e-Methanol",
        "deal_killers": {
            "offtake_binding_pct": 60,
            "epc_contract_executed": True,
            "ie_appointed": True,
            "financial_model_status": "IE_REVIEWED",
            "insurance_fully_placed": False,
            "rfnbo_pathway_viable": True,
            "dscr_p90": 1.18,
            "grid_connection_firm": True,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": True,
            "evidence_confirmed_pct": 63.0,
            "capital_stack_committed": False,
            "requirement_defined": True,
            "qualified_offers_count": 3,
            "pricing_reference_ready": True,
            "shortlist_count": 2,
            "evidence_audited_count": 5,
            "evidence_total_count": 14,
            "plant_configured": True,
            "next_gate_missing_items": 3,
            "g8_is_audit_grade": False,
        },
    },
    "proj_wales_saf": {
        "project_name": "Celtic Green SAF Complex",
        "molecule": "SAF",
        "deal_killers": {
            "offtake_binding_pct": 15,
            "epc_contract_executed": False,
            "ie_appointed": False,
            "financial_model_status": "SELF_ASSESSED",
            "insurance_fully_placed": False,
            "rfnbo_pathway_viable": False,
            "dscr_p90": 0.98,
            "grid_connection_firm": False,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": False,
            "evidence_confirmed_pct": 22.0,
            "capital_stack_committed": False,
            "requirement_defined": False,
            "qualified_offers_count": 0,
            "pricing_reference_ready": False,
            "shortlist_count": 0,
            "evidence_audited_count": 1,
            "evidence_total_count": 11,
            "plant_configured": False,
            "next_gate_missing_items": 7,
            "g8_is_audit_grade": False,
        },
    },
    "proj_lehavre_eng": {
        "project_name": "Le Havre e-Gas Hub",
        "molecule": "e-NG",
        "deal_killers": {
            "offtake_binding_pct": 100,
            "epc_contract_executed": True,
            "ie_appointed": True,
            "financial_model_status": "AUDIT_GRADE",
            "insurance_fully_placed": True,
            "rfnbo_pathway_viable": True,
            "dscr_p90": 1.35,
            "grid_connection_firm": True,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": True,
            "evidence_confirmed_pct": 91.0,
            "capital_stack_committed": True,
            "requirement_defined": True,
            "qualified_offers_count": 5,
            "pricing_reference_ready": True,
            "shortlist_count": 3,
            "evidence_audited_count": 8,
            "evidence_total_count": 9,
            "plant_configured": True,
            "next_gate_missing_items": 1,
            "g8_is_audit_grade": True,
        },
    },
    "proj_hamburgone_emethanol": {
        "project_name": "HamburgOne e-Methanol Plant",
        "molecule": "e-Methanol",
        "deal_killers": {
            "offtake_binding_pct": 30,
            "epc_contract_executed": False,
            "ie_appointed": True,
            "financial_model_status": "IE_REVIEWED",
            "insurance_fully_placed": False,
            "rfnbo_pathway_viable": True,
            "dscr_p90": 1.15,
            "grid_connection_firm": False,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": False,
            "evidence_confirmed_pct": 44.0,
            "capital_stack_committed": False,
            "requirement_defined": True,
            "qualified_offers_count": 2,
            "pricing_reference_ready": False,
            "shortlist_count": 1,
            "evidence_audited_count": 3,
            "evidence_total_count": 13,
            "plant_configured": True,
            "next_gate_missing_items": 4,
            "g8_is_audit_grade": False,
        },
    },
    "proj_madrid2_sansebastian": {
        "project_name": "Madrid2 San-Sebastián e-Methanol",
        "molecule": "e-Methanol",
        "deal_killers": {
            "offtake_binding_pct": 12,
            "epc_contract_executed": False,
            "ie_appointed": False,
            "financial_model_status": "SELF_ASSESSED",
            "insurance_fully_placed": False,
            "rfnbo_pathway_viable": True,
            "dscr_p90": 1.04,
            "grid_connection_firm": True,
        },
        "task_router": {
            "snapshot_viewed_within_7_days": False,
            "evidence_confirmed_pct": 28.0,
            "capital_stack_committed": False,
            "requirement_defined": True,
            "qualified_offers_count": 4,
            "pricing_reference_ready": False,
            "shortlist_count": 2,
            "evidence_audited_count": 2,
            "evidence_total_count": 17,
            "plant_configured": True,
            "next_gate_missing_items": 5,
            "g8_is_audit_grade": False,
        },
    },
}


def _db_exists() -> bool:
    return Path(DB_PATH).exists()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _load_runtime_evidence_stats(project_id: str) -> dict[str, Any]:
    if not _db_exists():
        return {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "bankability_evidence"):
            return {}

        rows = conn.execute(
            "SELECT status FROM bankability_evidence WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        if not rows:
            return {}

        total = len(rows)
        audited = sum(1 for row in rows if row["status"] == "AUDITED")
        confirmed_plus = sum(1 for row in rows if row["status"] in {"AUDITED", "CONFIRMED"})

        return {
            "evidence_total_count": total,
            "evidence_audited_count": audited,
            "evidence_confirmed_pct": round((confirmed_plus / total) * 100, 1),
        }
    finally:
        conn.close()


def get_project_truth(project_id: str) -> dict[str, Any]:
    truth = copy.deepcopy(PROJECT_TRUTH.get(project_id, DEFAULT_PROJECT_TRUTH))
    runtime_stats = _load_runtime_evidence_stats(project_id)
    if runtime_stats:
        truth["task_router"].update(runtime_stats)
    return truth


def build_deal_killer_project_data(project_id: str) -> dict[str, Any]:
    return copy.deepcopy(get_project_truth(project_id)["deal_killers"])


def build_task_router_project_data(project_id: str) -> dict[str, Any]:
    return copy.deepcopy(get_project_truth(project_id)["task_router"])
