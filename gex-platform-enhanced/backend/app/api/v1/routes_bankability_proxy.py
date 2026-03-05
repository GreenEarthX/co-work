"""
GEX Platform — Bankability Proxy Routes
=========================================
Mount in gex-platform-enhanced/backend/app/main.py:

    from app.api.v1.routes_bankability_proxy import router as bankability_proxy_router
    app.include_router(bankability_proxy_router, prefix="/api/v1/bankability", tags=["Bankability"])

Architecture:
    Frontend (React) -> Platform Backend (8000) /api/v1/bankability/* -> Engine (8001)
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

ENGINE_URL = os.getenv("GEX_ENGINE_URL", "http://localhost:8001")
DB_PATH = os.getenv("GEX_DB_PATH", "greenearth.db")
ENGINE_TIMEOUT = 10.0


class EvidenceUpdateRequest(BaseModel):
    project_id: str = "default"
    evidence_key: str
    new_status: str
    submitted_by: Optional[str] = None
    notes: Optional[str] = None


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bankability_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL DEFAULT 'default',
            evidence_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            submitted_by TEXT, verified_by TEXT,
            submitted_at TEXT, verified_at TEXT,
            document_hash TEXT, notes TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, evidence_key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bankability_snapshots (
            project_id TEXT PRIMARY KEY,
            current_state TEXT NOT NULL,
            snapshot_json TEXT,
            evaluated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_project ON bankability_evidence(project_id)")
    conn.commit()


def _load_evidence(project_id="default"):
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute("SELECT * FROM bankability_evidence WHERE project_id = ?", (project_id,)).fetchall()
    conn.close()
    return [{"key": r["evidence_key"], "status": r["status"], "submitted_by": r["submitted_by"],
             "verified_by": r["verified_by"], "submitted_at": r["submitted_at"],
             "verified_at": r["verified_at"], "document_hash": r["document_hash"],
             "notes": r["notes"]} for r in rows]


def _upsert_evidence(project_id, evidence_key, status, submitted_by=None, notes=None):
    conn = _get_db()
    _ensure_tables(conn)
    conn.execute("""
        INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(project_id, evidence_key)
        DO UPDATE SET status=excluded.status,
            submitted_by=COALESCE(excluded.submitted_by, bankability_evidence.submitted_by),
            notes=COALESCE(excluded.notes, bankability_evidence.notes),
            updated_at=datetime('now')
    """, (project_id, evidence_key, status, submitted_by, notes))
    conn.commit()
    conn.close()


def _get_project_state(project_id="default"):
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute("SELECT current_state FROM bankability_snapshots WHERE project_id = ?", (project_id,)).fetchone()
    conn.close()
    return row["current_state"] if row else None


def _store_snapshot(project_id, state, snapshot_json):
    conn = _get_db()
    _ensure_tables(conn)
    conn.execute("""
        INSERT INTO bankability_snapshots (project_id, current_state, snapshot_json, evaluated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(project_id) DO UPDATE SET current_state=excluded.current_state,
            snapshot_json=excluded.snapshot_json, evaluated_at=datetime('now')
    """, (project_id, state, snapshot_json))
    conn.commit()
    conn.close()


async def _call_engine(path, method="GET", json_data=None):
    url = f"{ENGINE_URL}/api/v1/bankability{path}"
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            resp = await (client.post(url, json=json_data) if method == "POST" else client.get(url))
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Engine error: {resp.text}")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Bankability engine unavailable (port 8001)")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Bankability engine timeout")


@router.get("/evaluate")
async def evaluate_project(project_id: str = Query(default="default")):
    evidence = _load_evidence(project_id)
    previous_state = _get_project_state(project_id)
    snapshot = await _call_engine("/evaluate", method="POST", json_data={
        "project_id": project_id, "evidence": evidence, "previous_state": previous_state,
    })
    _store_snapshot(project_id, snapshot.get("current_state", "SPECULATIVE"), json.dumps(snapshot))
    return snapshot


@router.get("/evaluate/persona")
async def evaluate_for_persona(
    persona: str = Query(..., description="PRODUCER|FINANCE|REGULATOR|EXECUTIVE"),
    project_id: str = Query(default="default"),
):
    evidence = _load_evidence(project_id)
    previous_state = _get_project_state(project_id)
    return await _call_engine("/evaluate/persona", method="POST", json_data={
        "project_id": project_id, "evidence": evidence, "persona": persona, "previous_state": previous_state,
    })


@router.get("/gates")
async def get_gate_definitions():
    return await _call_engine("/gates")


@router.get("/rules")
async def get_rules():
    return await _call_engine("/rules")


@router.post("/evidence")
async def update_evidence(request: EvidenceUpdateRequest):
    _upsert_evidence(request.project_id, request.evidence_key, request.new_status, request.submitted_by, request.notes)
    evidence = _load_evidence(request.project_id)
    previous_state = _get_project_state(request.project_id)
    snapshot = await _call_engine("/evaluate", method="POST", json_data={
        "project_id": request.project_id, "evidence": evidence, "previous_state": previous_state,
    })
    _store_snapshot(request.project_id, snapshot.get("current_state", "SPECULATIVE"), json.dumps(snapshot))
    return snapshot


@router.get("/evidence")
async def list_evidence(project_id: str = Query(default="default")):
    evidence = _load_evidence(project_id)
    return {"project_id": project_id, "evidence": evidence, "count": len(evidence)}

"""@router.post("/evidence/seed")
async def seed_demo_evidence(project_id: str = Query(default="default")):
   Seed demo evidence — self-contained, no engine call needed.
    demo = {
        """
    
@router.post("/evidence/seed")
async def seed_demo_evidence(project_id: str = Query(default="default")):
    gates = await _call_engine("/gates")
    demo = {
        "land_option_or_lease_executed": "VERIFIED", "zoning_compatibility_memo": "VERIFIED",
        "stakeholder_map_v1": "SUBMITTED", "grid_interconnection_study": "VERIFIED",
        "queue_position_evidence": "UNDER_REVIEW", "curtailment_assessment": "IN_PROGRESS",
        "water_source_plan": "VERIFIED", "water_permit_pathway_memo": "NOT_STARTED",
        "certification_scheme_selection": "VERIFIED", "additionality_evidence": "SUBMITTED",
        "ghg_methodology_memo": "IN_PROGRESS", "feedstock_supply_loi": "VERIFIED",
        "transport_logistics_study": "SUBMITTED", "storage_plan": "IN_PROGRESS",
        "binding_offtake_term_sheet": "UNDER_REVIEW", "offtake_credit_assessment": "IN_PROGRESS",
        "price_review_mechanism_memo": "NOT_STARTED", "epc_contract_heads_of_terms": "SUBMITTED",
        "performance_guarantees_draft": "IN_PROGRESS", "epc_contractor_dd": "NOT_STARTED",
        "ie_appointment_letter": "VERIFIED", "ie_technical_model_review": "IN_PROGRESS",
        "ie_site_visit_report": "NOT_STARTED", "insurance_broker_mandate": "VERIFIED",
        "insurance_market_report": "SUBMITTED", "insurance_term_sheet": "NOT_STARTED",
        "financial_model_v1": "SUBMITTED", "model_audit_engagement": "IN_PROGRESS",
        "sensitivity_analysis": "NOT_STARTED", "eia_submission": "IN_PROGRESS",
        "construction_permit_application": "NOT_STARTED", "operating_permit_pathway": "NOT_STARTED",
        "cp_checklist_draft": "NOT_STARTED", "legal_opinions_draft": "NOT_STARTED",
        "security_package_structure": "NOT_STARTED", "commissioning_plan": "NOT_STARTED",
        "performance_test_protocol": "NOT_STARTED", "handover_documentation_plan": "NOT_STARTED",
    }
    seeded = 0
    for gate in gates:
        for ek in gate.get("required_evidence", []):
            _upsert_evidence(project_id, ek, demo.get(ek, "NOT_STARTED"), "demo_seed", f"Seeded demo")
            seeded += 1
    return {"seeded": seeded, "project_id": project_id}


@router.get("/regression/check")
async def check_regression(project_id: str = Query(default="default")):
    evidence = _load_evidence(project_id)
    previous_state = _get_project_state(project_id)
    return await _call_engine("/regression/check", method="POST", json_data={
        "project_id": project_id, "evidence": evidence, "previous_state": previous_state,
    })


@router.get("/health")
async def health_check():
    db_ok = engine_ok = False
    try:
        conn = _get_db(); _ensure_tables(conn); conn.close(); db_ok = True
    except Exception: pass
    try:
        r = await _call_engine("/health"); engine_ok = r.get("status") == "healthy"
    except Exception: pass
    return {"status": "healthy" if db_ok and engine_ok else "degraded",
            "platform_db": "ok" if db_ok else "error", "engine": "ok" if engine_ok else "unreachable"}
