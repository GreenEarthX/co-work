"""
GEX Bankability — Report Assembly API (v2.0)

Endpoints:
  GET  /api/v1/reports/cfo              — CFO → CEO portfolio report
  GET  /api/v1/reports/banker/{project_id}  — Banker quality report (IC Pack summary)
"""
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()


@router.get("/cfo")
async def get_cfo_report(
    period: Optional[str] = Query(None, description="Month or quarter, e.g. '2026-Q1'"),
    project_ids: Optional[str] = Query(None, description="Comma-separated project IDs"),
):
    """
    Assemble CFO → CEO portfolio report.
    Aggregates BankabilitySnapshot per project + CapitalStackScenario + WAE queue.
    """
    return {
        "report_type": "CFO_CEO",
        "period": period or "2026-Q1",
        "generated_at": "2026-03-18T10:00:00Z",
        "workflow_state": "DRAFT",
        "portfolio_summary": [
            {"project_id": "proj_le_havre_eng",  "name": "Le Havre e-NG",               "state": "BANKABLE",   "trust_score": 94, "dscr_p50": 1.58, "next_gate": "G10 Financial Close",  "traffic_light": "GREEN"},
            {"project_id": "proj_bremen_h2",      "name": "Bremen Green Hydrogen Plant",  "state": "BUILDABLE",  "trust_score": 72, "dscr_p50": 1.34, "next_gate": "G1 Grid Connection",   "traffic_light": "AMBER"},
            {"project_id": "proj_helios_emethanol","name": "Helios e-Methanol",           "state": "FUNDABLE",   "trust_score": 51, "dscr_p50": 1.22, "next_gate": "G2 Certification",     "traffic_light": "AMBER"},
            {"project_id": "proj_rotterdam_nh3",  "name": "Rotterdam NH3",                "state": "EARLY_DEV", "trust_score": 40, "dscr_p50": 1.05, "next_gate": "G1 Grid Connection",   "traffic_light": "RED"},
            {"project_id": "proj_wales_saf",      "name": "Wales SAF",                    "state": "EARLY_DEV", "trust_score": 30, "dscr_p50": 0.98, "next_gate": "G0 Site Rights",       "traffic_light": "RED"},
        ],
        "funding_pipeline": {
            "total_ask_eur": 748_000_000,
            "committed_eur": 210_000_000,
            "dfi_mandate_eur": 210_000_000,
            "pipeline_eur": 328_000_000,
            "gap_eur": 538_000_000,
        },
        "key_metrics": {
            "portfolio_avg_wacc": 10.78,
            "dscr_range": {"min": 0.98, "max": 1.58},
            "avg_contracted_pct": 57,
            "cert_readiness_avg": 53,
            "projects_bankable": 1,
            "projects_at_fid_risk": 2,
        },
        "risk_register": [
            {"rank": 1, "severity": "HIGH",   "title": "Grid connection delays", "detail": "Bremen G1 pending utility sign-off. Rotterdam not started. Combined exposure: €330M."},
            {"rank": 2, "severity": "HIGH",   "title": "Offtake coverage insufficient", "detail": "Wales 20%, Rotterdam 35% — both below 70% threshold. Financial close blocked."},
            {"rank": 3, "severity": "MEDIUM", "title": "EPC performance guarantee gap", "detail": "Bremen G5 performance guarantees from PEM OEM still pending. G5 gate incomplete."},
        ],
        "decisions_required": [
            {"id": "dec-001", "action": "Approve BP engagement as second offtaker for Rotterdam NH3", "deadline": "2026-Q2", "budget_eur": None},
            {"id": "dec-002", "action": "Authorize KfW pre-mandate engagement for Bremen H2", "deadline": "2026-Q2", "budget_eur": 85_000},
            {"id": "dec-003", "action": "Confirm EPC shortlist for Wales SAF pre-FEED", "deadline": "2026-Q3", "budget_eur": None},
        ],
        "outlook_90d": [
            {"project": "Le Havre e-NG",  "milestones": ["IE final signoff (wk1-4)", "BPI/EIB term sheet (wk5-8)", "FID preparation (wk9-12)"]},
            {"project": "Bremen H2",       "milestones": ["Grid utility meeting (wk1-2)", "EPC wrap negotiation (wk3-8)", "EIB engagement (wk9-12)"]},
            {"project": "Helios e-Methanol","milestones": ["CO2 supply agreement (wk1-6)", "EPC pre-FEED (wk7-12)"]},
        ],
    }


@router.get("/banker/{project_id}")
async def get_banker_report(project_id: str):
    """Structured banker quality report summary for a project."""
    return {
        "project_id": project_id,
        "report_type": "BANKER_QUALITY",
        "generated_at": "2026-03-18T10:00:00Z",
        "workflow_state": "DRAFT",
        "snapshot_ref": f"snap-{project_id}-001",
        "sensitivity_run_ref": f"sens-{project_id}-001",
        "offtake_assessment_ref": f"offtake-{project_id}-001",
        "cert_readiness_ref": f"cert-{project_id}-001",
        "capital_stack_ref": f"capstack-{project_id}-001",
    }
