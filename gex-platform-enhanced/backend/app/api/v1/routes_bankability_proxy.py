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

from app.services.engine_auth import engine_auth_headers
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()

ENGINE_URL = os.getenv("GEX_ENGINE_URL", "http://localhost:8001")
DB_PATH = settings.SQLITE_DB_PATH
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
    # Documents backing evidence items — evidence without a document is a claim.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            evidence_key TEXT NOT NULL,
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            stored_path TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    """)
    # Append-only status transition log — control functions audit transitions,
    # not states. Never UPDATEd, never DELETEd.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            evidence_key TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            actor TEXT NOT NULL,
            at TEXT NOT NULL,
            document_sha256 TEXT
        )
    """)
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


def _upsert_evidence(project_id, evidence_key, status, submitted_by=None, notes=None, document_sha256=None):
    conn = _get_db()
    _ensure_tables(conn)
    old = conn.execute(
        "SELECT status FROM bankability_evidence WHERE project_id = ? AND evidence_key = ?",
        (project_id, evidence_key),
    ).fetchone()
    old_status = old["status"] if old else None
    conn.execute("""
        INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(project_id, evidence_key)
        DO UPDATE SET status=excluded.status,
            submitted_by=COALESCE(excluded.submitted_by, bankability_evidence.submitted_by),
            notes=COALESCE(excluded.notes, bankability_evidence.notes),
            updated_at=datetime('now')
    """, (project_id, evidence_key, status, submitted_by, notes))
    # Append-only audit: every status transition is recorded with its actor.
    if old_status != status:
        conn.execute(
            "INSERT INTO evidence_events (project_id, evidence_key, old_status, new_status, actor, at, document_sha256) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?)",
            (project_id, evidence_key, old_status, status, submitted_by or "system", document_sha256),
        )
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
    conn.execute("DELETE FROM bankability_snapshots WHERE project_id = ?", (project_id,))
    conn.execute("""
        INSERT INTO bankability_snapshots (project_id, current_state, snapshot_json, evaluated_at)
        VALUES (?, ?, ?, datetime('now'))
    """, (project_id, state, snapshot_json))
    conn.commit()
    conn.close()


def _physical_payload(project_id: str) -> dict:
    """
    Power model + phase + financing model for the engine's gate scoping,
    severity escalation, and financing-waived gates. Reads the EFFECTIVE
    context (DB override written via PATCH /projects/{id}/context, falling
    back to the code seed).
    """
    try:
        from app.core.project_registry import get_effective_context
        ctx = get_effective_context(project_id)
        if ctx:
            return {
                "power_model": ctx.power_model,
                "project_phase": ctx.phase,
                "financing_model": ctx.financing_model,
            }
    except Exception:
        pass
    return {"power_model": None, "project_phase": None, "financing_model": None}


async def _call_engine(path, method="GET", json_data=None):
    url = f"{ENGINE_URL}/api/v1/bankability{path}"
    headers = engine_auth_headers()
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            resp = await (client.post(url, json=json_data, headers=headers) if method == "POST" else client.get(url, headers=headers))
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
        **_physical_payload(project_id),
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
        **_physical_payload(project_id),
    })


@router.get("/projects/{project_id}/bankability/{persona}")
async def get_project_bankability_for_persona(project_id: str, persona: str):
    evidence = _load_evidence(project_id)
    previous_state = _get_project_state(project_id)
    return await _call_engine("/evaluate/persona", method="POST", json_data={
        "project_id": project_id, "evidence": evidence,
        "persona": persona.upper(), "previous_state": previous_state,
        **_physical_payload(project_id),
    })


@router.get("/executive/portfolio")
async def get_executive_portfolio():
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT project_id, current_state, snapshot_json FROM bankability_snapshots"
    ).fetchall()
    conn.close()

    projects = []
    total_completion = 0.0
    projects_with_regressions = 0

    for row in rows:
        project_id = row["project_id"]
        evidence = _load_evidence(project_id)
        try:
            persona_view = await _call_engine("/evaluate/persona", method="POST", json_data={
                "project_id": project_id, "evidence": evidence,
                "persona": "EXECUTIVE", "previous_state": row["current_state"],
                **_physical_payload(project_id),
            })
        except Exception:
            persona_view = json.loads(row["snapshot_json"]) if row["snapshot_json"] else {}

        completion = persona_view.get("overall_completion_pct", 0)
        total_completion += completion
        if persona_view.get("regression"):
            projects_with_regressions += 1

        capital_unlocks = persona_view.get("capital_unlocks", [])
        unlocked_count = sum(1 for c in capital_unlocks if c.get("is_unlocked"))

        projects.append({
            "project_id": project_id,
            "current_state": row["current_state"],
            "overall_completion": round(completion, 1),
            "capital_unlocks": capital_unlocks,
            "unlocked_count": unlocked_count,
            "gate_evaluations": persona_view.get("gate_evaluations", []),
            "regression": persona_view.get("regression"),
        })

    count = len(projects)
    avg_completion = round(total_completion / count, 1) if count > 0 else 0.0
    total_unlocked = sum(p["unlocked_count"] for p in projects)

    return {
        "portfolioSummary": {
            "total_projects": count,
            "total_portfolio_value": "N/A",
            "total_unlocked": f"{total_unlocked} capital types unlocked",
            "average_completion": avg_completion,
            "projects_with_regressions": projects_with_regressions,
            "capital_pipeline": [],
        },
        "projects": projects,
    }


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
        **_physical_payload(request.project_id),
    })
    _store_snapshot(request.project_id, snapshot.get("current_state", "SPECULATIVE"), json.dumps(snapshot))
    return snapshot


@router.get("/evidence")
async def list_evidence(project_id: str = Query(default="default")):
    evidence = _load_evidence(project_id)
    return {"project_id": project_id, "evidence": evidence, "count": len(evidence)}


# ── Evidence documents — evidence without a document is a claim ─────────────

EVIDENCE_DOCS_DIR = os.getenv("GEX_EVIDENCE_DOCS_DIR", "data/evidence_docs")
_MAX_DOC_BYTES = 25 * 1024 * 1024  # 25 MB


def _require_actor(authorization: str | None) -> dict:
    from app.core.auth import get_user_payload_from_token
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return get_user_payload_from_token(authorization.split(" ", 1)[1].strip())
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/evidence/document")
async def upload_evidence_document(
    project_id: str = Form(...),
    evidence_key: str = Form(...),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    """
    Attach a document to an evidence item. Stores the file with its sha256,
    records the upload in evidence_documents, moves the item to SUBMITTED,
    and logs the transition (actor + document hash) in evidence_events.
    """
    import hashlib
    from pathlib import Path

    actor = _require_actor(authorization)
    content = await file.read()
    if len(content) > _MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds 25 MB limit")
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Empty file")

    sha = hashlib.sha256(content).hexdigest()
    safe_name = os.path.basename(file.filename or "document.bin")
    dest_dir = Path(EVIDENCE_DOCS_DIR) / project_id / evidence_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{sha[:12]}_{safe_name}"
    dest.write_bytes(content)

    now_actor = actor.get("email", "unknown")
    conn = _get_db()
    _ensure_tables(conn)
    conn.execute(
        "INSERT INTO evidence_documents (project_id, evidence_key, filename, sha256, size_bytes, stored_path, uploaded_by, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (project_id, evidence_key, safe_name, sha, len(content), str(dest), now_actor),
    )
    conn.commit()
    conn.close()

    # Document arrival moves the item to SUBMITTED (never auto-VERIFIED —
    # verification is a separate, human transition).
    _upsert_evidence(project_id, evidence_key, "SUBMITTED", submitted_by=now_actor, document_sha256=sha)

    return {
        "project_id": project_id,
        "evidence_key": evidence_key,
        "filename": safe_name,
        "sha256": sha,
        "size_bytes": len(content),
        "status": "SUBMITTED",
        "uploaded_by": now_actor,
    }


@router.get("/evidence/documents")
async def list_evidence_documents(
    project_id: str = Query(...),
    evidence_key: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Documents on file for a project's evidence items (metadata + hashes)."""
    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    if evidence_key:
        rows = conn.execute(
            "SELECT evidence_key, filename, sha256, size_bytes, uploaded_by, uploaded_at FROM evidence_documents "
            "WHERE project_id = ? AND evidence_key = ? ORDER BY id DESC",
            (project_id, evidence_key),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT evidence_key, filename, sha256, size_bytes, uploaded_by, uploaded_at FROM evidence_documents "
            "WHERE project_id = ? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
    conn.close()
    return {"project_id": project_id, "documents": [dict(r) for r in rows]}


@router.get("/evidence/document/{sha256}/download")
async def download_evidence_document(sha256: str, authorization: str | None = Header(default=None)):
    """Serve a stored evidence document by content hash (auth required)."""
    from fastapi.responses import FileResponse

    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT filename, stored_path FROM evidence_documents WHERE sha256 = ? ORDER BY id DESC LIMIT 1",
        (sha256,),
    ).fetchone()
    conn.close()
    if not row or not os.path.exists(row["stored_path"]):
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(row["stored_path"], filename=row["filename"])


@router.get("/evidence/events")
async def list_evidence_events(
    project_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Append-only evidence status-transition audit trail."""
    _require_actor(authorization)
    conn = _get_db()
    _ensure_tables(conn)
    rows = conn.execute(
        "SELECT evidence_key, old_status, new_status, actor, at, document_sha256 FROM evidence_events "
        "WHERE project_id = ? ORDER BY id DESC LIMIT 500",
        (project_id,),
    ).fetchall()
    conn.close()
    return {"project_id": project_id, "events": [dict(r) for r in rows]}

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
        # G1 expanded evidence (PPA + connection cost + dispatch + water volume)
        "grid_connection_cost_estimate": "IN_PROGRESS", "connection_date_cod_compatibility_memo": "NOT_STARTED",
        "ppa_register": "NOT_STARTED", "ppa_signed_or_term_sheet_evidence": "NOT_STARTED",
        "ppa_volume_load_coverage_analysis": "NOT_STARTED", "ppa_tenor_debt_comparison": "NOT_STARTED",
        "dispatch_load_factor_production_impact": "NOT_STARTED",
        # G1 E-track (off-grid BTM generation)
        "btm_generation_asset_evidence": "SUBMITTED", "generation_yield_study": "IN_PROGRESS",
        "grid_independence_note": "NOT_STARTED", "backup_construction_power_plan": "NOT_STARTED",
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
        **_physical_payload(project_id),
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
