"""
GEX Workflow Authorization Engine (WAE)
=========================================
Controls whether a WRITE action takes effect immediately or requires
countersignatures before it becomes binding.

Sits downstream of ABAC:
  ABAC → CAN the user write? (access control)
  WAE  → SHOULD the write take effect now, or wait for approvals?

Chain order: ABAC → SoD → DRPL → WAE → CSS → DB

Reference: GEX Security Architecture Extension v1.0, Domain 1
"""

from __future__ import annotations

import sqlite3
import json
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger("gex.wae")

_DB_PATH = "gex_platform.db"


# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class AuthorizationOutcome(str, Enum):
    IMMEDIATE         = "IMMEDIATE"         # write proceeds without approval
    PENDING_APPROVAL  = "PENDING_APPROVAL"  # write held until countersigned
    DENIED            = "DENIED"            # no matching policy + no default pass


class ApprovalStatus(str, Enum):
    PENDING    = "PENDING"
    APPROVED   = "APPROVED"
    REJECTED   = "REJECTED"
    EXPIRED    = "EXPIRED"
    ESCALATED  = "ESCALATED"


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT  = "REJECT"


# ═══════════════════════════════════════════════════════════════
# DATA OBJECTS
# ═══════════════════════════════════════════════════════════════

@dataclass
class AuthorizationDecision:
    outcome: AuthorizationOutcome
    action_type: str
    request_id: Optional[str] = None        # set when PENDING_APPROVAL
    required_roles: list[str] = field(default_factory=list)
    min_approvers: int = 0
    policy_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class ApprovalRequest:
    id: str
    policy_id: str
    initiator_user_id: str
    action_type: str
    resource_id: Optional[str]
    project_id: Optional[str]
    payload_json: dict
    status: str
    created_at: str
    expires_at: Optional[str]
    required_roles: list[str]
    min_approvers: int


# ═══════════════════════════════════════════════════════════════
# BUILT-IN APPROVAL POLICIES (seed data)
# ═══════════════════════════════════════════════════════════════

APPROVAL_POLICIES = [
    {
        "id": "pol-saf-forward-sale",
        "action_type": "SAF_FORWARD_SALE",
        "threshold_currency": 500_000.0,
        "threshold_volume": 1_000.0,
        "required_roles": ["TRADER", "RISK_OFFICER", "TREASURY_HEAD"],
        "min_approvers": 2,
        "escalation_timeout_hours": 24,
        "escalation_role": "CFO",
    },
    {
        "id": "pol-ppa-execution",
        "action_type": "PPA_EXECUTION",
        "threshold_currency": None,
        "threshold_volume": None,
        "required_roles": ["ENERGY_MANAGER", "CFO"],
        "min_approvers": 2,
        "escalation_timeout_hours": 48,
        "escalation_role": "CEO",
    },
    {
        "id": "pol-financing-drawdown",
        "action_type": "FINANCING_DRAWDOWN",
        "threshold_currency": None,
        "threshold_volume": None,
        "required_roles": ["FINANCE_DIRECTOR", "TREASURY_HEAD"],
        "min_approvers": 2,
        "escalation_timeout_hours": 24,
        "escalation_role": "CFO",
    },
    {
        "id": "pol-insurance-placement",
        "action_type": "INSURANCE_PLACEMENT",
        "threshold_currency": 100_000.0,
        "threshold_volume": None,
        "required_roles": ["RISK_MANAGER", "CFO"],
        "min_approvers": 2,
        "escalation_timeout_hours": 24,
        "escalation_role": None,
    },
    {
        "id": "pol-epc-milestone",
        "action_type": "EPC_MILESTONE_PAYMENT",
        "threshold_currency": 250_000.0,
        "threshold_volume": None,
        "required_roles": ["PROJECT_DIRECTOR", "FINANCE_DIRECTOR"],
        "min_approvers": 2,
        "escalation_timeout_hours": 48,
        "escalation_role": "CFO",
    },
    {
        "id": "pol-cert-application",
        "action_type": "CERTIFICATE_APPLICATION",
        "threshold_currency": None,
        "threshold_volume": None,
        "required_roles": ["COMPLIANCE_OFFICER", "TECHNICAL_DIRECTOR"],
        "min_approvers": 2,
        "escalation_timeout_hours": 72,
        "escalation_role": None,
    },
    {
        "id": "pol-evidence-export",
        "action_type": "EVIDENCE_EXPORT",
        "threshold_currency": None,
        "threshold_volume": None,
        "required_roles": ["DATA_OWNER", "CISO"],
        "min_approvers": 2,
        "escalation_timeout_hours": 12,
        "escalation_role": None,
    },
    {
        "id": "pol-counterparty-nda",
        "action_type": "COUNTERPARTY_NDA",
        "threshold_currency": None,
        "threshold_volume": None,
        "required_roles": ["LEGAL", "COMMERCIAL_DIRECTOR"],
        "min_approvers": 2,
        "escalation_timeout_hours": 48,
        "escalation_role": "CEO",
    },
]

# Action types that ALWAYS require approval (regardless of threshold)
ALWAYS_REQUIRES_APPROVAL = {
    "PPA_EXECUTION",
    "FINANCING_DRAWDOWN",
    "CERTIFICATE_APPLICATION",
    "COUNTERPARTY_NDA",
}

# Actions that bypass WAE (internal ops)
WAE_BYPASS = {
    "READ",
    "INTERNAL_UPDATE",
    "EVIDENCE_UPLOAD",
    "BANKABILITY_EVALUATE",
}


# ═══════════════════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════════════════

def init_wae_db(db_path: str = _DB_PATH) -> None:
    """Create WAE tables if they don't exist."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS approval_policies (
            id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            threshold_currency REAL,
            threshold_volume REAL,
            required_roles TEXT NOT NULL,   -- JSON array
            min_approvers INTEGER NOT NULL DEFAULT 2,
            escalation_timeout_hours INTEGER DEFAULT 24,
            escalation_role TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS approval_requests (
            id TEXT PRIMARY KEY,
            policy_id TEXT NOT NULL,
            initiator_user_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            resource_id TEXT,
            project_id TEXT,
            payload_json TEXT NOT NULL,     -- JSON
            status TEXT DEFAULT 'PENDING',  -- PENDING|APPROVED|REJECTED|EXPIRED|ESCALATED
            required_roles TEXT NOT NULL,   -- JSON array
            min_approvers INTEGER NOT NULL DEFAULT 2,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_approval_requests_status
            ON approval_requests(status);
        CREATE INDEX IF NOT EXISTS ix_approval_requests_project
            ON approval_requests(project_id);

        CREATE TABLE IF NOT EXISTS approval_decisions (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            approver_user_id TEXT NOT NULL,
            decision TEXT NOT NULL,         -- APPROVE | REJECT
            reason_text TEXT,
            decided_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS ix_approval_decisions_request
            ON approval_decisions(request_id);
    """)

    # Seed policies if empty
    cur.execute("SELECT COUNT(*) FROM approval_policies")
    if cur.fetchone()[0] == 0:
        for p in APPROVAL_POLICIES:
            cur.execute(
                """INSERT OR IGNORE INTO approval_policies
                   (id, action_type, threshold_currency, threshold_volume,
                    required_roles, min_approvers, escalation_timeout_hours, escalation_role)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (p["id"], p["action_type"], p.get("threshold_currency"),
                 p.get("threshold_volume"), json.dumps(p["required_roles"]),
                 p["min_approvers"], p.get("escalation_timeout_hours", 24),
                 p.get("escalation_role"))
            )

    con.commit()
    con.close()


# ═══════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════

def _find_policy(action_type: str, amount: Optional[float] = None,
                 volume: Optional[float] = None,
                 db_path: str = _DB_PATH) -> Optional[dict]:
    """Find the active policy matching action_type and thresholds."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM approval_policies WHERE action_type = ? AND active = 1 LIMIT 1",
        (action_type,)
    )
    row = cur.fetchone()
    con.close()

    if row is None:
        # Fall back to built-in dict
        for p in APPROVAL_POLICIES:
            if p["action_type"] == action_type:
                return p
        return None

    return dict(row)


def evaluate_authorization(
    initiator_user_id: str,
    action_type: str,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
    payload: Optional[dict] = None,
    amount: Optional[float] = None,
    volume: Optional[float] = None,
    db_path: str = _DB_PATH,
) -> AuthorizationDecision:
    """
    Evaluate whether the action can proceed immediately or requires countersignatures.

    Returns AuthorizationDecision with outcome IMMEDIATE or PENDING_APPROVAL.
    If PENDING_APPROVAL, also creates and persists an ApprovalRequest.
    """
    if action_type in WAE_BYPASS:
        return AuthorizationDecision(
            outcome=AuthorizationOutcome.IMMEDIATE,
            action_type=action_type,
            reason="Action type exempt from WAE",
        )

    policy = _find_policy(action_type, amount, volume, db_path)

    if policy is None:
        return AuthorizationDecision(
            outcome=AuthorizationOutcome.IMMEDIATE,
            action_type=action_type,
            reason="No WAE policy defined — passes through",
        )

    # Check thresholds
    needs_approval = action_type in ALWAYS_REQUIRES_APPROVAL

    if not needs_approval:
        tc = policy.get("threshold_currency")
        tv = policy.get("threshold_volume")
        if tc is not None and amount is not None and amount >= tc:
            needs_approval = True
        if tv is not None and volume is not None and volume >= tv:
            needs_approval = True

    if not needs_approval:
        return AuthorizationDecision(
            outcome=AuthorizationOutcome.IMMEDIATE,
            action_type=action_type,
            reason="Below approval thresholds",
        )

    # Create approval request
    required_roles = policy.get("required_roles", [])
    if isinstance(required_roles, str):
        required_roles = json.loads(required_roles)
    min_approvers = policy.get("min_approvers", 2)
    timeout_h = policy.get("escalation_timeout_hours", 24)
    policy_id = policy.get("id", f"pol-{action_type.lower()}")

    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=timeout_h)).isoformat()

    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(
            """INSERT INTO approval_requests
               (id, policy_id, initiator_user_id, action_type, resource_id, project_id,
                payload_json, status, required_roles, min_approvers, created_at, expires_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (request_id, policy_id, initiator_user_id, action_type,
             resource_id, project_id, json.dumps(payload or {}),
             ApprovalStatus.PENDING.value, json.dumps(required_roles),
             min_approvers, now.isoformat(), expires_at)
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.warning("WAE DB write failed: %s", exc)

    logger.info("WAE PENDING: action=%s initiator=%s request_id=%s",
                action_type, initiator_user_id, request_id)

    return AuthorizationDecision(
        outcome=AuthorizationOutcome.PENDING_APPROVAL,
        action_type=action_type,
        request_id=request_id,
        required_roles=required_roles,
        min_approvers=min_approvers,
        policy_id=policy_id,
    )


# ═══════════════════════════════════════════════════════════════
# APPROVAL DECISION
# ═══════════════════════════════════════════════════════════════

def record_decision(
    request_id: str,
    approver_user_id: str,
    decision: ApprovalDecision,
    reason_text: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> dict:
    """
    Record an APPROVE or REJECT decision for a pending request.
    Returns updated request state including whether quorum is reached.
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Fetch request
    cur.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,))
    req = cur.fetchone()
    if not req:
        con.close()
        return {"error": "Request not found"}

    if req["status"] != ApprovalStatus.PENDING.value:
        con.close()
        return {"error": f"Request is already {req['status']}"}

    # Insert decision
    decision_id = str(uuid.uuid4())
    cur.execute(
        """INSERT INTO approval_decisions (id, request_id, approver_user_id, decision, reason_text)
           VALUES (?,?,?,?,?)""",
        (decision_id, request_id, approver_user_id, decision.value, reason_text)
    )

    # Count approvals
    cur.execute(
        "SELECT COUNT(*) FROM approval_decisions WHERE request_id = ? AND decision = 'APPROVE'",
        (request_id,)
    )
    approval_count = cur.fetchone()[0]
    min_approvers = req["min_approvers"]

    new_status = req["status"]

    if decision == ApprovalDecision.REJECT:
        new_status = ApprovalStatus.REJECTED.value
    elif approval_count >= min_approvers:
        new_status = ApprovalStatus.APPROVED.value

    if new_status != req["status"]:
        cur.execute(
            "UPDATE approval_requests SET status = ? WHERE id = ?",
            (new_status, request_id)
        )

    con.commit()
    con.close()

    logger.info("WAE decision: request=%s approver=%s decision=%s new_status=%s",
                request_id, approver_user_id, decision.value, new_status)

    return {
        "request_id": request_id,
        "decision": decision.value,
        "new_status": new_status,
        "approvals_received": approval_count,
        "min_approvers": min_approvers,
        "quorum_reached": new_status == ApprovalStatus.APPROVED.value,
    }


def get_pending_approvals(
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    if project_id:
        cur.execute(
            "SELECT * FROM approval_requests WHERE status = 'PENDING' AND project_id = ? ORDER BY created_at DESC",
            (project_id,)
        )
    else:
        cur.execute(
            "SELECT * FROM approval_requests WHERE status = 'PENDING' ORDER BY created_at DESC LIMIT 100"
        )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    for r in rows:
        r["required_roles"] = json.loads(r.get("required_roles", "[]"))
        r["payload_json"] = json.loads(r.get("payload_json", "{}"))
    return rows


def get_request(request_id: str, db_path: str = _DB_PATH) -> Optional[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    req = dict(row)
    cur.execute("SELECT * FROM approval_decisions WHERE request_id = ? ORDER BY decided_at", (request_id,))
    req["decisions"] = [dict(d) for d in cur.fetchall()]
    con.close()
    req["required_roles"] = json.loads(req.get("required_roles", "[]"))
    req["payload_json"] = json.loads(req.get("payload_json", "{}"))
    return req


def get_audit_trail(resource_id: str, db_path: str = _DB_PATH) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM approval_requests WHERE resource_id = ? ORDER BY created_at DESC",
        (resource_id,)
    )
    rows = []
    for req in cur.fetchall():
        r = dict(req)
        cur2 = con.cursor()
        cur2.execute("SELECT * FROM approval_decisions WHERE request_id = ?", (r["id"],))
        r["decisions"] = [dict(d) for d in cur2.fetchall()]
        r["required_roles"] = json.loads(r.get("required_roles", "[]"))
        rows.append(r)
    con.close()
    return rows
