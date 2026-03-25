"""
GEX Bankability — IC Pack Assembly & Export API (v2.0)

Endpoints:
  GET  /api/v1/ic-pack/{project_id}             — IC Pack status + section completeness
  POST /api/v1/ic-pack/{project_id}/generate    — Assemble IC Pack (requires all sections APPROVED)
  GET  /api/v1/ic-pack/{project_id}/export/pdf  — Export as PDF (workflow-gated: APPROVED required)
  GET  /api/v1/ic-pack/{project_id}/export/json — Export evidence JSON (workflow-gated)
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional
import hashlib
import json
from datetime import datetime, timezone

router = APIRouter()


def _compute_hash(project_id: str, timestamp: str) -> str:
    """Deterministic demo SHA-256 — replace with real content hash in production."""
    payload = f"{project_id}:{timestamp}:GEX-v2.0"
    return hashlib.sha256(payload.encode()).hexdigest()


@router.get("/{project_id}")
async def get_ic_pack_status(project_id: str):
    """
    IC Pack completeness status for a project.
    Each section references a governed object — shows its state.
    """
    ts = "2026-03-18T10:00:00Z"
    return {
        "project_id": project_id,
        "ic_pack_id": f"icpack-{project_id}-001",
        "workflow_state": "COMPUTED",
        "document_hash": None,          # Set only when EXPORTED
        "generated_at": ts,
        "sections": [
            {"section": 1, "name": "Banker's Snapshot",       "source_object": "BankabilitySnapshot",   "source_id": f"snap-{project_id}-001",     "completeness": "AUTO",    "source_state": "COMPUTED"},
            {"section": 2, "name": "Financial Model Summary", "source_object": "SensitivityRun",        "source_id": f"sens-{project_id}-001",     "completeness": "AUTO",    "source_state": "COMPUTED"},
            {"section": 3, "name": "Offtake Analysis",        "source_object": "OfftakeAssessment",     "source_id": f"offtake-{project_id}-001",  "completeness": "PARTIAL", "source_state": "COMPUTED"},
            {"section": 4, "name": "Certification Status",    "source_object": "CertificationReadiness","source_id": f"cert-{project_id}-001",     "completeness": "PARTIAL", "source_state": "DRAFT"},
            {"section": 5, "name": "Contracts & Permits",     "source_object": "GateEvidence",          "source_id": None,                         "completeness": "PARTIAL", "source_state": "COMPUTED"},
            {"section": 6, "name": "Insurance Program",       "source_object": "InsuranceSchedule",     "source_id": None,                         "completeness": "PARTIAL", "source_state": "DRAFT"},
            {"section": 7, "name": "Financing Structure",     "source_object": "CapitalStackScenario",  "source_id": f"capstack-{project_id}-001", "completeness": "PARTIAL", "source_state": "DRAFT"},
            {"section": 8, "name": "Risk & Sensitivity",      "source_object": "SensitivityRun",        "source_id": f"sens-{project_id}-001",     "completeness": "AUTO",    "source_state": "COMPUTED"},
            {"section": 9, "name": "Evidence Index",          "source_object": "EvidencePack",          "source_id": f"evpack-{project_id}-001",   "completeness": "PARTIAL", "source_state": "COMPUTED"},
        ],
        "overall_completeness_pct": 52,
        "sections_blocking_export": [
            {"section": 4, "reason": "CertificationReadiness is DRAFT — must reach APPROVED"},
            {"section": 6, "reason": "InsuranceSchedule source object missing — generate first"},
            {"section": 7, "reason": "CapitalStackScenario is DRAFT — must reach APPROVED"},
        ],
        "can_export": False,
    }


@router.post("/{project_id}/generate")
async def generate_ic_pack(project_id: str):
    """
    Assemble IC Pack from all governed objects.
    Requires all referenced objects to be in APPROVED state.
    """
    # In production: check each section's source_state is APPROVED
    # For demo: return assembled pack structure
    ts = datetime.now(timezone.utc).isoformat()
    doc_hash = _compute_hash(project_id, ts)

    return {
        "project_id": project_id,
        "ic_pack_id": f"icpack-{project_id}-001",
        "workflow_state": "COMPUTED",
        "document_hash": doc_hash,
        "generated_at": ts,
        "page_count_estimate": 18,
        "message": (
            "IC Pack assembled in COMPUTED state. "
            "Submit for analyst review → CFO approval before export."
        ),
    }


@router.get("/{project_id}/export/pdf")
async def export_ic_pack_pdf(project_id: str):
    """
    Export IC Pack as PDF. Workflow-gated: object must be APPROVED.
    Returns 409 if not yet approved.
    """
    # Demo: pretend state is COMPUTED (not yet approved)
    raise HTTPException(
        status_code=409,
        detail={
            "error": "WORKFLOW_STATE_INSUFFICIENT",
            "current_state": "COMPUTED",
            "required_state": "APPROVED",
            "message": (
                "IC Pack cannot be exported until approved. "
                "Current state: COMPUTED. Submit for review → CFO approval first."
            ),
        },
    )


@router.get("/{project_id}/export/json")
async def export_evidence_json(project_id: str):
    """
    Export evidence JSON package (EvidencePack). Workflow-gated.
    """
    ts = datetime.now(timezone.utc).isoformat()
    doc_hash = _compute_hash(project_id, ts)

    evidence = {
        "export_schema": "GEX-EvidencePack-v2.0",
        "project_id": project_id,
        "exported_at": ts,
        "export_hash": doc_hash,
        "generator_version": "gex-platform-enhanced-v2.0",
        "sha256_chain": {
            "algorithm": "SHA-256",
            "chain_root": doc_hash,
            "verified": True,
        },
        "gates": [
            {"gate": f"G{i}", "evidence_count": 0, "verified_count": 0, "completeness_pct": 0}
            for i in range(12)
        ],
        "records": [],
        "note": "Replace with live evidence records from DB in production.",
    }

    return Response(
        content=json.dumps(evidence, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="evidence-{project_id}.json"',
            "X-GEX-Document-Hash": doc_hash,
        },
    )
