"""
GEX Platform — TEA bridge (backend 8000  →  tea_engine 8002  →  truth ledger)
============================================================================
Step 2 of the OpenPyTEA integration play. This router:

  1. proxies a techno-economic compute request to tea_engine (port 8002),
  2. appends the run to the hash-chained evidence_ledger as immutable EVIDENCE
     (category=COST, verification_state=UNVERIFIED — a raw run is never trusted),
  3. creates a `model_base_case` CLAIM in state `submitted`, linked to that
     evidence, superseding any prior live base case for the same pathway.

It deliberately does NOT verify the run. Promotion submitted → verified happens
via /base-case/{claim_id}/approve (an IE/CFO approval_decision). Until then the
base case is PROVISIONAL and no release-gated compute may run on it (the B7 rule
proven in schemas/validate_pathway.py; enforced at PF-call time in step 4).

Mount in main.py:
    from app.api.v1.routes_tea import router as tea_router, init_db as tea_init_db
    tea_init_db()
    app.include_router(tea_router, prefix="/api/v1/tea", tags=["TEA Engine Bridge"])
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel

# Approval notifications → per-project Matrix rooms (no-op if Matrix absent).
try:
    from app.services.approval_notifier import (
        notify_approval_requested, notify_approval_decided,
    )
except Exception:  # noqa: BLE001
    def notify_approval_requested(*a, **k):  # type: ignore
        pass
    def notify_approval_decided(*a, **k):  # type: ignore
        pass

from app.core.config import settings
from app.api.v1.evidence_ledger import (
    EvidenceCategory,
    EvidenceCreate,
    VerificationState,
    append_evidence,
)

router = APIRouter()

DB_PATH = settings.SQLITE_DB_PATH
TEA_ENGINE_URL = os.getenv("TEA_ENGINE_URL", "http://localhost:8002")
ENGINE_TIMEOUT = 30.0

# Subset of the 9-state ClaimState machine this table uses, with legal forward
# transitions (mirrors efuel_truth_stack.enums.CLAIM_STATE_TRANSITIONS).
TERMINAL_VALID = {"verified", "satisfied", "waived"}
LEGAL_TRANSITIONS = {
    "submitted": {"verified", "rejected"},
    "verified": {"satisfied", "expired", "superseded"},
    "rejected": {"submitted"},
}


# ───────────────────────────────────────────────────────────────────────────
# DB
# ───────────────────────────────────────────────────────────────────────────

def get_db():
    # check_same_thread=False: async endpoints receive this connection from a
    # threadpool-run dependency but use it on the event loop — different threads.
    # Safe here because each request gets its own connection (never shared).
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create the append-only model_base_case claim table. Call from main.py."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_base_case (
            claim_id                TEXT PRIMARY KEY,
            project_id              TEXT NOT NULL,
            pathway_id              TEXT,
            subject_node            TEXT NOT NULL DEFAULT 'financial_model',
            claim_type              TEXT NOT NULL DEFAULT 'model_base_case',
            state                   TEXT NOT NULL DEFAULT 'submitted',
            engine                  TEXT,
            cost_basis_hash         TEXT NOT NULL,
            capex_eur               REAL,
            opex_eur_per_year       REAL,
            lcop                    REAL,
            nameplate_capacity      REAL,
            nameplate_unit          TEXT,
            run_evidence_id         TEXT,
            supersedes_claim_id     TEXT,
            superseded_by           TEXT,
            reconciliation_group_id TEXT,
            approved_by             TEXT,
            approval_decision_id    TEXT,
            valid_from              TEXT NOT NULL,
            valid_to                TEXT,
            created_at              TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mbc_project ON model_base_case(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mbc_state ON model_base_case(state)")
    # General claim table (mirrors efuel_truth_stack Claim) — home for GHG and
    # other pathway claims that walk the 9-state machine, like model_base_case.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pathway_claims (
            claim_id                TEXT PRIMARY KEY,
            project_id              TEXT NOT NULL,
            pathway_id              TEXT,
            subject_node            TEXT,
            claim_type              TEXT NOT NULL,
            value_type              TEXT NOT NULL DEFAULT 'numeric',
            value                   REAL,
            unit                    TEXT,
            state                   TEXT NOT NULL DEFAULT 'submitted',
            method                  TEXT,
            evidence_id             TEXT,
            supersedes_claim_id     TEXT,
            superseded_by           TEXT,
            approved_by             TEXT,
            approval_decision_id    TEXT,
            valid_from              TEXT NOT NULL,
            valid_to                TEXT,
            created_at              TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_project ON pathway_claims(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_type ON pathway_claims(claim_type)")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def release_ready_state(project_id: str, pathway_id: Optional[str] = None) -> Optional[dict]:
    """The live base case's release-readiness for `project_id`, or None if none exists.

    Standalone (opens its own connection) so other routers — notably the PF-engine
    proxy — can enforce the B7 compute-authorization rule without importing the DB
    plumbing. Returns {claim_id, state, is_release_ready}.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        q = ("SELECT claim_id, state FROM model_base_case "
             "WHERE project_id=? AND valid_to IS NULL "
             "AND state NOT IN ('superseded','rejected','expired','failed')")
        args: list[Any] = [project_id]
        if pathway_id:
            q += " AND pathway_id=?"
            args.append(pathway_id)
        q += " ORDER BY created_at DESC LIMIT 1"
        row = conn.execute(q, tuple(args)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "claim_id": row["claim_id"],
        "state": row["state"],
        "is_release_ready": row["state"] in TERMINAL_VALID,
    }


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["is_release_ready"] = d["state"] in TERMINAL_VALID
    return d


# ───────────────────────────────────────────────────────────────────────────
# Models
# ───────────────────────────────────────────────────────────────────────────

class ComputeRequest(BaseModel):
    pathway_id: str
    # Optional: omit to let tea_engine derive the equipment train from the
    # molecule's canonical process function (fuel_id).
    process_units: list[dict] = []
    assumptions: dict = {}
    nameplate_capacity: float
    nameplate_unit: str = "t_per_year"
    fuel_id: str = "E_METHANOL"
    reconciliation_group_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    approved_by: str
    outcome: str = "approve"          # approve | approve_with_conditions | reject
    conditions: list[str] = []
    # Canonical write authority is per ROLE (spec v0.3 actors); the human user id
    # is recorded in the decision payload, the role is the authorised writer.
    approver_role: str = "independent_engineer"


def _canonical(fn, **kwargs) -> dict:
    """Emit to the canonical ledger (write-time contract, census sign-off).
    Never silent: returns the entry ref, or the explicit error surface."""
    try:
        from app.core import canonical_ledger as cl
        cl.init_db()
        return getattr(cl, fn)(**kwargs)
    except Exception as e:  # noqa: BLE001 — surfaced, not swallowed
        return {"error": f"{type(e).__name__}: {e}"}


# ───────────────────────────────────────────────────────────────────────────
# Engine proxy
# ───────────────────────────────────────────────────────────────────────────

async def _call_tea(path: str, payload: dict, auth_header: Optional[str]) -> dict:
    url = f"{TEA_ENGINE_URL}/tea{path}"
    headers = {"Authorization": auth_header} if auth_header else {}
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"tea_engine error: {resp.text}")
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(503, "TEA engine unavailable (port 8002)")


# ───────────────────────────────────────────────────────────────────────────
# Routes
# ───────────────────────────────────────────────────────────────────────────

@router.post("/compute/{project_id}", status_code=201)
async def compute_base_case(
    project_id: str,
    request: Request,
    body: ComputeRequest = Body(...),
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Run TEA on :8002, record the run as evidence, create a submitted base-case claim."""
    auth = request.headers.get("Authorization")
    tea_payload = {
        "project_id": project_id,
        "pathway_id": body.pathway_id,
        "process_units": body.process_units,
        "assumptions": body.assumptions,
        "nameplate_capacity": body.nameplate_capacity,
        "nameplate_unit": body.nameplate_unit,
        "fuel_id": body.fuel_id,
    }
    result = await _call_tea("/compute", tea_payload, auth)
    ps = result["plant_summary"]

    # 1) record the OpenPyTEA run as immutable evidence (UNVERIFIED).
    ev = append_evidence(
        EvidenceCreate(
            project_id=project_id,
            entity_type="model_base_case",
            entity_id=body.pathway_id,
            category=EvidenceCategory.COST,
            document_ref=result["cost_basis_hash"],
            verification_state=VerificationState.UNVERIFIED,
            submitted_by="tea_engine",
        ),
        db,
    )
    run_evidence_id = ev["evidence_id"]

    # 2) supersede any prior live base case for this pathway.
    now = _now()
    prior = db.execute(
        "SELECT claim_id FROM model_base_case "
        "WHERE project_id=? AND pathway_id=? AND valid_to IS NULL "
        "AND state NOT IN ('superseded','rejected','expired','failed') "
        "ORDER BY created_at DESC LIMIT 1",
        (project_id, body.pathway_id),
    ).fetchone()

    claim_id = f"CLM-MBC-{uuid.uuid4().hex[:10]}"
    if prior:
        db.execute(
            "UPDATE model_base_case SET state='superseded', superseded_by=?, valid_to=? "
            "WHERE claim_id=?",
            (claim_id, now, prior["claim_id"]),
        )

    # 3) create the submitted (PROVISIONAL) base-case claim.
    db.execute("""
        INSERT INTO model_base_case
        (claim_id, project_id, pathway_id, state, engine, cost_basis_hash,
         capex_eur, opex_eur_per_year, lcop, nameplate_capacity, nameplate_unit,
         run_evidence_id, supersedes_claim_id, reconciliation_group_id,
         valid_from, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        claim_id, project_id, body.pathway_id, "submitted", result["engine"],
        result["cost_basis_hash"], ps["capex_eur"], ps["opex_eur_per_year"],
        result["lcop"], ps["nameplate_capacity"], ps["nameplate_unit"],
        run_evidence_id, prior["claim_id"] if prior else None,
        body.reconciliation_group_id, now, now,
    ))
    db.commit()

    # CANONICAL (system of record, write-time contract): the run as a derived
    # projection_snapshot asserting the claim at 'submitted'. Legacy tables above
    # are now read-models fed by the same code path, not competing truth.
    canonical = _canonical(
        "append_entry", project_id=project_id, entry_type="projection_snapshot",
        produced_by="tea_engine",
        payload={"claim_id": claim_id, "claim_type": "model_base_case",
                 "subject_node": "financial_model", "value_type": "doc_ref",
                 "value": result["cost_basis_hash"], "to_state": "submitted",
                 "capex_eur": ps["capex_eur"], "opex_eur_per_year": ps["opex_eur_per_year"],
                 "lcop": result["lcop"], "engine": result["engine"],
                 **({"supersedes_claim": prior["claim_id"]} if prior else {}),
                 "legacy": {"table": "model_base_case", "record_id": claim_id,
                            "evidence_id": run_evidence_id}},
    )

    # Nudge, not silence: tell the approver a cost basis awaits them.
    notify_approval_requested(
        project_id=project_id, request_id=claim_id,
        action_type="model_base_case_verification",
        initiator_user_id="tea_engine",
        required_roles=["INDEPENDENT_ENGINEER", "CFO"],
    )

    row = db.execute("SELECT * FROM model_base_case WHERE claim_id=?", (claim_id,)).fetchone()
    return {
        "base_case": _row(row),
        "run_evidence": ev,
        "canonical": canonical,
        "engine": result["engine"],
        "note": result.get("note"),
    }


@router.get("/base-case/{project_id}")
def current_base_case(
    project_id: str,
    pathway_id: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """The current live base case (most recent non-superseded), with release-readiness."""
    q = ("SELECT * FROM model_base_case WHERE project_id=? AND valid_to IS NULL "
         "AND state NOT IN ('superseded','rejected','expired','failed')")
    args: list[Any] = [project_id]
    if pathway_id:
        q += " AND pathway_id=?"
        args.append(pathway_id)
    q += " ORDER BY created_at DESC LIMIT 1"
    row = db.execute(q, tuple(args)).fetchone()
    if not row:
        raise HTTPException(404, "no live base case for project")
    return _row(row)


@router.post("/base-case/{claim_id}/approve")
def approve_base_case(
    claim_id: str,
    body: ApprovalRequest,
    x_demo_user: Optional[str] = Header(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """IE/CFO approval_decision: folds submitted → verified (or rejected).

    Approver identity comes from the session header (x-demo-user, same convention
    as routes_approvals) — the request body is a fallback, not an assertion of
    identity. The approver MUST NOT be tea_engine (no self-verification)."""
    row = db.execute("SELECT * FROM model_base_case WHERE claim_id=?", (claim_id,)).fetchone()
    if not row:
        raise HTTPException(404, "base case not found")
    approver = x_demo_user or body.approved_by
    if not approver:
        raise HTTPException(401, "no approver identity (x-demo-user header or approved_by)")
    body.approved_by = approver
    if approver == "tea_engine":
        raise HTTPException(403, "tea_engine may not verify its own run")

    target = "verified" if body.outcome in ("approve", "approve_with_conditions") else "rejected"
    if target not in LEGAL_TRANSITIONS.get(row["state"], set()):
        raise HTTPException(
            409, f"illegal transition {row['state']} → {target}")

    # the approval is itself evidence (a decision-kind entry).
    decision = append_evidence(
        EvidenceCreate(
            project_id=row["project_id"],
            entity_type="model_base_case_approval",
            entity_id=claim_id,
            category=EvidenceCategory.COST,
            document_ref=f"approval:{body.outcome}:{row['cost_basis_hash']}",
            verification_state=VerificationState.CONFIRMED,
            reviewer_id=body.approved_by,
            submitted_by=body.approved_by,
        ),
        db,
    )
    db.execute(
        "UPDATE model_base_case SET state=?, approved_by=?, approval_decision_id=? "
        "WHERE claim_id=?",
        (target, body.approved_by, decision["evidence_id"], claim_id),
    )
    db.commit()
    canonical = _canonical(
        "append_entry", project_id=row["project_id"], entry_type="approval_decision",
        produced_by=body.approver_role,
        payload={"claim_id": claim_id, "outcome": body.outcome,
                 "approved_by_user": body.approved_by,
                 "conditions": body.conditions,
                 "legacy": {"table": "model_base_case", "record_id": claim_id,
                            "decision_evidence_id": decision["evidence_id"]}},
    )
    notify_approval_decided(
        project_id=row["project_id"], request_id=claim_id,
        decision=body.outcome, approver_user_id=body.approved_by, new_status=target,
    )
    row = db.execute("SELECT * FROM model_base_case WHERE claim_id=?", (claim_id,)).fetchone()
    return {"base_case": _row(row), "approval_decision": decision, "canonical": canonical}


# ───────────────────────────────────────────────────────────────────────────
# LCA / GHG claims — same evidence→submitted→verified pattern as the cost basis
# ───────────────────────────────────────────────────────────────────────────

def _persist_claim(db, project_id, pathway_id, subject_node, claim_type, value,
                   unit, method, evidence_id) -> str:
    """Create a submitted pathway claim, superseding any prior live one of the
    same (project, pathway, claim_type)."""
    now = _now()
    prior = db.execute(
        "SELECT claim_id FROM pathway_claims WHERE project_id=? AND pathway_id=? "
        "AND claim_type=? AND valid_to IS NULL "
        "AND state NOT IN ('superseded','rejected','expired','failed') "
        "ORDER BY created_at DESC LIMIT 1",
        (project_id, pathway_id, claim_type),
    ).fetchone()
    cid = f"CLM-{claim_type[:12].upper()}-{uuid.uuid4().hex[:8]}"
    if prior:
        db.execute("UPDATE pathway_claims SET state='superseded', superseded_by=?, valid_to=? "
                   "WHERE claim_id=?", (cid, now, prior["claim_id"]))
    db.execute(
        "INSERT INTO pathway_claims (claim_id, project_id, pathway_id, subject_node, "
        "claim_type, value_type, value, unit, state, method, evidence_id, "
        "supersedes_claim_id, valid_from, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, project_id, pathway_id, subject_node, claim_type, "numeric", value, unit,
         "submitted", method, evidence_id, prior["claim_id"] if prior else None, now, now),
    )
    return cid


@router.post("/lca/{project_id}", status_code=201)
async def compute_lca_claims(
    project_id: str,
    request: Request,
    body: ComputeRequest = Body(...),
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Run the regime-correct LCA on :8002, record it as evidence, and create the
    g_co2e_per_mj + ghg_saving claims (submitted) — the GHG equivalent of the
    cost-basis flow. Approve via /claim/{id}/approve; the certification gate then
    reads these persisted claims."""
    auth = request.headers.get("Authorization")
    result = await _call_tea("/lca/compute", {
        "project_id": project_id, "pathway_id": body.pathway_id, "fuel_id": body.fuel_id,
    }, auth)
    ev = append_evidence(
        EvidenceCreate(
            project_id=project_id, entity_type="lca_run", entity_id=body.pathway_id,
            category=EvidenceCategory.CERTIFICATION, document_ref=result["lci_hash"],
            verification_state=VerificationState.UNVERIFIED, submitted_by="tea_engine",
        ), db)
    eid = ev["evidence_id"]
    ghg = _persist_claim(db, project_id, body.pathway_id, "ghg_lca", "g_co2e_per_mj",
                         result["g_co2e_per_mj"], "gCO2e/MJ", result["ghg_method"], eid)
    sav = _persist_claim(db, project_id, body.pathway_id, "ghg_lca", "ghg_saving",
                         result["ghg_saving_frac"], "fraction", result["ghg_method"], eid)
    db.commit()

    # CANONICAL: one derived run entry per claim (state assertion at 'submitted'),
    # plus an evidence_link tying the GHG run entry to the ghg_saving claim too —
    # one computation backing two claims (spec §6b many-to-many, live).
    can_ghg = _canonical(
        "append_entry", project_id=project_id, entry_type="projection_snapshot",
        produced_by="tea_engine",
        payload={"claim_id": ghg, "claim_type": "g_co2e_per_mj",
                 "subject_node": "ghg_lca", "value_type": "numeric",
                 "value": result["g_co2e_per_mj"], "unit": "gCO2e/MJ",
                 "to_state": "submitted", "method": result["ghg_method"],
                 "allocation": result.get("allocation"),
                 "lci_hash": result["lci_hash"],
                 "legacy": {"table": "pathway_claims", "record_id": ghg,
                            "evidence_id": eid}})
    can_sav = _canonical(
        "append_entry", project_id=project_id, entry_type="projection_snapshot",
        produced_by="tea_engine",
        payload={"claim_id": sav, "claim_type": "ghg_saving",
                 "subject_node": "ghg_lca", "value_type": "numeric",
                 "value": result["ghg_saving_frac"], "unit": "fraction",
                 "to_state": "submitted", "method": result["ghg_method"],
                 "legacy": {"table": "pathway_claims", "record_id": sav,
                            "evidence_id": eid}})
    can_link = (_canonical("link_evidence", claim_id=sav,
                           ledger_entry_id=can_ghg["entry_id"],
                           linked_by="tea_engine")
                if "entry_id" in can_ghg else {"error": can_ghg.get("error")})

    notify_approval_requested(
        project_id=project_id, request_id=ghg,
        action_type="ghg_claim_verification",
        initiator_user_id="tea_engine",
        required_roles=["CERTIFIER", "INDEPENDENT_ENGINEER"],
    )
    return {"lca": {"g_co2e_per_mj": result["g_co2e_per_mj"],
                    "ghg_saving_frac": result["ghg_saving_frac"],
                    "ghg_method": result["ghg_method"],
                    "allocation": result.get("allocation"),
                    "meets_threshold": result["meets_threshold"]},
            "claims": {"g_co2e_per_mj": ghg, "ghg_saving": sav},
            "run_evidence": ev,
            "canonical": {"ghg_entry": can_ghg, "saving_entry": can_sav,
                          "many_to_many_link": can_link}}


@router.post("/claim/{claim_id}/approve")
def approve_claim(
    claim_id: str, body: ApprovalRequest,
    x_demo_user: Optional[str] = Header(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Generic pathway-claim approval (IE / certifier). Folds submitted → verified;
    blocks tea_engine self-approval and illegal transitions. Approver identity from
    the session header (x-demo-user), body as fallback."""
    row = db.execute("SELECT * FROM pathway_claims WHERE claim_id=?", (claim_id,)).fetchone()
    if not row:
        raise HTTPException(404, "claim not found")
    approver = x_demo_user or body.approved_by
    if not approver:
        raise HTTPException(401, "no approver identity (x-demo-user header or approved_by)")
    body.approved_by = approver
    if approver == "tea_engine":
        raise HTTPException(403, "tea_engine may not verify its own run")
    target = "verified" if body.outcome in ("approve", "approve_with_conditions") else "rejected"
    if target not in LEGAL_TRANSITIONS.get(row["state"], set()):
        raise HTTPException(409, f"illegal transition {row['state']} → {target}")
    decision = append_evidence(
        EvidenceCreate(
            project_id=row["project_id"], entity_type="claim_approval", entity_id=claim_id,
            category=EvidenceCategory.CERTIFICATION,
            document_ref=f"approval:{body.outcome}:{row['claim_type']}",
            verification_state=VerificationState.CONFIRMED,
            reviewer_id=body.approved_by, submitted_by=body.approved_by,
        ), db)
    db.execute("UPDATE pathway_claims SET state=?, approved_by=?, approval_decision_id=? "
               "WHERE claim_id=?", (target, body.approved_by, decision["evidence_id"], claim_id))
    db.commit()
    canonical = _canonical(
        "append_entry", project_id=row["project_id"], entry_type="approval_decision",
        produced_by=body.approver_role,
        payload={"claim_id": claim_id, "outcome": body.outcome,
                 "approved_by_user": body.approved_by,
                 "legacy": {"table": "pathway_claims", "record_id": claim_id,
                            "decision_evidence_id": decision["evidence_id"]}},
    )
    notify_approval_decided(
        project_id=row["project_id"], request_id=claim_id,
        decision=body.outcome, approver_user_id=body.approved_by, new_status=target,
    )
    row = db.execute("SELECT * FROM pathway_claims WHERE claim_id=?", (claim_id,)).fetchone()
    return {"claim": dict(row), "approval_decision": decision, "canonical": canonical}


@router.get("/certification-gate/{project_id}")
async def certification_gate_from_ledger(
    project_id: str,
    request: Request,
    fuel_id: str,
    pathway_id: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Close the loop: read the project's PERSISTED live claims and evaluate the
    certification gate for the fuel's regime via :8002. The gate opens only when
    every regime-required claim is terminal-valid in the ledger."""
    q = ("SELECT claim_type, state FROM pathway_claims WHERE project_id=? "
         "AND valid_to IS NULL AND state NOT IN ('superseded','rejected','expired','failed')")
    args: list[Any] = [project_id]
    if pathway_id:
        q += " AND pathway_id=?"; args.append(pathway_id)
    claim_states = {r["claim_type"]: r["state"] for r in db.execute(q, tuple(args)).fetchall()}
    auth = request.headers.get("Authorization")
    verdict = await _call_tea(f"/certification-gate/{fuel_id}", claim_states, auth)
    return {"project_id": project_id, "claim_states_from_ledger": claim_states, "gate": verdict}


@router.get("/canonical/{project_id}")
def canonical_projection(
    project_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """THE canonical read: fold the persisted canonical ledger into claim
    projections, and run the live projection-equivalence check (Migration Spec
    acceptance test C/G) against the legacy read-model tables. States must
    match claim-for-claim — a mismatch is surfaced, never reconciled silently."""
    folded = _canonical("fold_project", project_id=project_id)
    if "error" in folded:
        return {"project_id": project_id, "canonical": folded}

    legacy: dict[str, str] = {}
    for r in db.execute("SELECT claim_id, state FROM model_base_case WHERE project_id=?",
                        (project_id,)).fetchall():
        legacy[r["claim_id"]] = r["state"]
    for r in db.execute("SELECT claim_id, state FROM pathway_claims WHERE project_id=?",
                        (project_id,)).fetchall():
        legacy[r["claim_id"]] = r["state"]

    mismatches = []
    for cid, c in folded["claims"].items():
        if cid in legacy and legacy[cid] != c["state"]:
            mismatches.append({"claim_id": cid, "canonical": c["state"],
                               "legacy": legacy[cid]})
    missing_in_canonical = sorted(set(legacy) - set(folded["claims"]))

    return {
        "project_id": project_id,
        "canonical": folded,
        "projection_equivalence": {
            "legacy_claims": len(legacy),
            "state_mismatches": mismatches,
            "missing_in_canonical": missing_in_canonical,
            "equivalent": not mismatches and not missing_in_canonical,
        },
    }
