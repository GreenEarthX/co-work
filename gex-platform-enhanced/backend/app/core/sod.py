"""
GEX Segregation of Duties (SoD) Engine
========================================
Detects when the same user attempts to perform two conflicting actions
on the same resource. Runs AFTER ABAC and BEFORE WAE.

ISO 27001 A.6.1.2: separation of duties must be implemented to reduce
risk of fraud or error.

Chain order: ABAC → SoD → DRPL → WAE → CSS → DB

Reference: GEX Security Architecture Extension v1.0, Domain 2
"""

from __future__ import annotations

import sqlite3
import json
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("gex.sod")

_DB_PATH = "gex_platform.db"


# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class SoDOutcome(str, Enum):
    CLEAR    = "CLEAR"    # no conflict detected
    CONFLICT = "CONFLICT" # same user performed conflicting action


class ResourceScope(str, Enum):
    SAME_RESOURCE = "SAME_RESOURCE"  # conflict only when same resource_id
    SAME_PROJECT  = "SAME_PROJECT"   # conflict within same project
    GLOBAL        = "GLOBAL"         # any previous action triggers conflict


@dataclass
class SoDResult:
    outcome: SoDOutcome
    conflict_pair_id: Optional[str] = None
    conflicting_action: Optional[str] = None
    conflicting_resource_id: Optional[str] = None
    performed_at: Optional[str] = None
    description: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# BUILT-IN CONFLICT PAIRS (seed data)
# ═══════════════════════════════════════════════════════════════

SOD_CONFLICT_PAIRS = [
    {
        "id": "SoD-01",
        "action_a": "EVIDENCE_SUBMIT",
        "action_b": "EVIDENCE_VERIFY",
        "resource_scope": ResourceScope.SAME_RESOURCE,
        "description": "Cannot submit and verify the same evidence (self-certification risk)",
    },
    {
        "id": "SoD-02",
        "action_a": "TRADE_ENTER",
        "action_b": "SETTLEMENT_CONFIRM",
        "resource_scope": ResourceScope.SAME_RESOURCE,
        "description": "Cannot enter and confirm settlement of the same trade (fictitious trade risk)",
    },
    {
        "id": "SoD-03",
        "action_a": "MILESTONE_CLAIM_SUBMIT",
        "action_b": "MILESTONE_PAYMENT_AUTHORIZE",
        "resource_scope": ResourceScope.SAME_RESOURCE,
        "description": "Cannot submit milestone claim and authorise its payment (contractor collusion risk)",
    },
    {
        "id": "SoD-04",
        "action_a": "FINANCIAL_MODEL_UPLOAD",
        "action_b": "BANKABILITY_EVALUATE",
        "resource_scope": ResourceScope.SAME_PROJECT,
        "description": "Cannot upload model assumptions and run evaluation on same project (model manipulation risk)",
    },
    {
        "id": "SoD-05",
        "action_a": "PURCHASE_ORDER_CREATE",
        "action_b": "PURCHASE_ORDER_APPROVE_PAYMENT",
        "resource_scope": ResourceScope.SAME_RESOURCE,
        "description": "Cannot create and approve payment for the same purchase order (procurement fraud risk)",
    },
    {
        "id": "SoD-06",
        "action_a": "PPA_PRICE_SET",
        "action_b": "METERED_OUTPUT_RECORD",
        "resource_scope": ResourceScope.SAME_PROJECT,
        "description": "Cannot set electricity sale price and record metered output (revenue manipulation risk)",
    },
    {
        "id": "SoD-07",
        "action_a": "ABAC_ATTRIBUTE_ASSIGN",
        "action_b": "ACTION_ENABLED_BY_THOSE_ATTRIBUTES",
        "resource_scope": ResourceScope.SAME_PROJECT,
        "description": "Cannot assign ABAC attributes to self and immediately use them (privilege escalation risk)",
    },
    {
        "id": "SoD-08",
        "action_a": "REGULATORY_REPORT_DRAFT",
        "action_b": "REGULATORY_REPORT_SUBMIT",
        "resource_scope": ResourceScope.SAME_RESOURCE,
        "description": "Cannot draft and submit the same regulatory report (unreviewed filing risk)",
    },
]

# Map (action_b → [pairs]) for fast lookup
_SOD_INDEX: dict[str, list[dict]] = {}
for _p in SOD_CONFLICT_PAIRS:
    _SOD_INDEX.setdefault(_p["action_b"], []).append(_p)
    # Also index reverse: if proposing action_a, check if action_b was already done
    _SOD_INDEX.setdefault(_p["action_a"], []).append({
        **_p,
        "action_a": _p["action_b"],
        "action_b": _p["action_a"],
        "id": f"{_p['id']}-rev",
        "description": f"(reverse) {_p['description']}",
    })


# ═══════════════════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════════════════

def init_sod_db(db_path: str = _DB_PATH) -> None:
    """Create SoD tables if they don't exist."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS sod_conflict_pairs (
            id TEXT PRIMARY KEY,
            action_a TEXT NOT NULL,
            action_b TEXT NOT NULL,
            resource_scope TEXT NOT NULL DEFAULT 'SAME_RESOURCE',
            description TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sod_action_log (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            resource_id TEXT,
            project_id TEXT,
            performed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS ix_sod_log_user
            ON sod_action_log(user_id, action_type);
        CREATE INDEX IF NOT EXISTS ix_sod_log_resource
            ON sod_action_log(resource_id);
    """)

    # Seed pairs if empty
    cur.execute("SELECT COUNT(*) FROM sod_conflict_pairs")
    if cur.fetchone()[0] == 0:
        for p in SOD_CONFLICT_PAIRS:
            cur.execute(
                "INSERT OR IGNORE INTO sod_conflict_pairs (id, action_a, action_b, resource_scope, description) VALUES (?,?,?,?,?)",
                (p["id"], p["action_a"], p["action_b"],
                 p["resource_scope"] if isinstance(p["resource_scope"], str) else p["resource_scope"].value,
                 p["description"])
            )

    con.commit()
    con.close()


# ═══════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════

def check_sod(
    user_id: str,
    proposed_action: str,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> SoDResult:
    """
    Check whether proposed_action by user_id conflicts with a prior action
    they performed on the same resource/project.

    Returns SoDResult(CLEAR) or SoDResult(CONFLICT).
    """
    conflicting_pairs = _SOD_INDEX.get(proposed_action, [])
    if not conflicting_pairs:
        # No rules touch this action — always clear
        return SoDResult(outcome=SoDOutcome.CLEAR)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    for pair in conflicting_pairs:
        prior_action = pair["action_a"]
        scope = pair.get("resource_scope", ResourceScope.SAME_RESOURCE)
        if isinstance(scope, str):
            scope = ResourceScope(scope)

        if scope == ResourceScope.SAME_RESOURCE and resource_id:
            cur.execute(
                """SELECT * FROM sod_action_log
                   WHERE user_id = ? AND action_type = ? AND resource_id = ?
                   ORDER BY performed_at DESC LIMIT 1""",
                (user_id, prior_action, resource_id)
            )
        elif scope == ResourceScope.SAME_PROJECT and project_id:
            cur.execute(
                """SELECT * FROM sod_action_log
                   WHERE user_id = ? AND action_type = ? AND project_id = ?
                   ORDER BY performed_at DESC LIMIT 1""",
                (user_id, prior_action, project_id)
            )
        elif scope == ResourceScope.GLOBAL:
            cur.execute(
                """SELECT * FROM sod_action_log
                   WHERE user_id = ? AND action_type = ?
                   ORDER BY performed_at DESC LIMIT 1""",
                (user_id, prior_action)
            )
        else:
            continue

        row = cur.fetchone()
        if row:
            con.close()
            logger.warning(
                "SoD CONFLICT: user=%s proposed=%s conflicts_with=%s resource=%s pair=%s",
                user_id, proposed_action, prior_action, resource_id, pair["id"]
            )
            return SoDResult(
                outcome=SoDOutcome.CONFLICT,
                conflict_pair_id=pair["id"],
                conflicting_action=prior_action,
                conflicting_resource_id=row["resource_id"],
                performed_at=row["performed_at"],
                description=pair.get("description", ""),
            )

    con.close()
    return SoDResult(outcome=SoDOutcome.CLEAR)


def record_action(
    user_id: str,
    action_type: str,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> None:
    """
    Record a completed action to the SoD log.
    Called AFTER the DB write succeeds, so only committed actions are logged.
    """
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(
            """INSERT INTO sod_action_log (id, user_id, action_type, resource_id, project_id)
               VALUES (?,?,?,?,?)""",
            (str(uuid.uuid4()), user_id, action_type, resource_id, project_id)
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.warning("SoD record_action failed: %s", exc)


def get_conflict_pairs(active_only: bool = True, db_path: str = _DB_PATH) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    if active_only:
        cur.execute("SELECT * FROM sod_conflict_pairs WHERE active = 1")
    else:
        cur.execute("SELECT * FROM sod_conflict_pairs")
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows
