"""
GEX Data Residency Policy Layer (DRPL)
========================================
Governs WHERE data is physically stored and processed.
Answers: can this data category for this company be stored in this zone?

ABAC  = WHO sees data
DRPL  = WHERE data lives

Runs after SoD, before WAE in the decision chain.
Returns HTTP 451 (Unavailable for Legal Reasons) on BLOCKED.

Jurisdictions: EU (GDPR), CH (FADP 2023), GB (UK GDPR), US (SOC 2)

Reference: GEX Security Architecture Extension v1.0, Domain 5
"""

from __future__ import annotations

import sqlite3
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("gex.drpl")

_DB_PATH = settings.SQLITE_DB_PATH

def _gov_conn(db_path: str):
    """
    Slice-6b-4 connection — SQLite or PostgreSQL by configuration
    (GOVERNANCE_DB_BACKEND).

    `db_path` is honoured only on SQLite; these functions accept it for
    testability and it has no meaning against PostgreSQL.
    """
    from app.core.db_backend import (PLATFORM_ADMIN, governance_connection,
                                     governance_is_postgres)

    if governance_is_postgres():
        # Explicit admin: these rules are read WHILE deciding whether an
        # action is permitted, so they cannot be filtered by that decision.
        return governance_connection(company_id=PLATFORM_ADMIN)
    import sqlite3 as _s

    conn = _s.connect(db_path)
    conn.row_factory = _s.Row
    return conn




# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class ResidencyOutcome(str, Enum):
    ALLOWED        = "ALLOWED"
    BLOCKED        = "BLOCKED"         # → HTTP 451
    NEEDS_CONSENT  = "NEEDS_CONSENT"   # → consent capture flow


class DataCategory(str, Enum):
    PERSONAL          = "PERSONAL"
    CONTRACT          = "CONTRACT"
    FINANCIAL_MODEL   = "FINANCIAL_MODEL"
    CERTIFICATION     = "CERTIFICATION"
    COMMS_METADATA    = "COMMS_METADATA"
    PLANT_DATA        = "PLANT_DATA"
    AUDIT_LOG         = "AUDIT_LOG"


@dataclass
class ResidencyDecision:
    outcome: ResidencyOutcome
    data_category: str
    company_id: str
    requested_zone: str
    required_jurisdiction: Optional[str] = None
    policy_id: Optional[str] = None
    reason: Optional[str] = None


# No built-in per-company policies (2026-10-25). DEFAULT_POLICIES used to
# enforce residency for two sample companies ("bp_global_energy",
# "totsa_total_energy") that are not GEX clients. A company's policy is what it
# recorded in data_residency_policies; with none recorded, ALWAYS_EU still holds.

# Zone → accepted jurisdiction
ZONE_JURISDICTION: dict[str, str] = {
    "eu-west-1":     "EU",
    "eu-central-1":  "EU",
    "eu-south-1":    "EU",
    "ch-zurich-1":   "CH",
    "gb-london-1":   "GB",
    "us-east-1":     "US",
    "localhost":      "EU",     # dev: treated as EU
    "sqlite-local":  "EU",
}

# Data categories that are ALWAYS EU regardless of company setting
ALWAYS_EU = {DataCategory.AUDIT_LOG.value, DataCategory.COMMS_METADATA.value}


# ═══════════════════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════════════════

def init_drpl_db(db_path: str = _DB_PATH) -> None:
    from app.core.db_backend import governance_is_postgres

    # SQLite only. On PostgreSQL the schema is owned by alembic (migration 042),
    # which also declares the CHECK constraints and the four distinct RLS policy
    # shapes. This function uses executescript(), which does not exist on the
    # PostgreSQL adapter, so it would error rather than silently no-op.
    if governance_is_postgres():
        return
    con = _gov_conn(db_path)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS data_residency_policies (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            data_category TEXT NOT NULL,
            required_jurisdiction TEXT NOT NULL,  -- EU | CH | GB | US
            storage_zone TEXT,
            active INTEGER DEFAULT 1,
            consented_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uix_drpl_co_cat
            ON data_residency_policies(company_id, data_category);
    """)
    con.commit()
    con.close()


# ═══════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════

def check_residency(
    company_id: str,
    data_category: str,
    target_zone: str = "localhost",
    db_path: str = _DB_PATH,
) -> ResidencyDecision:
    """
    Check whether storing data_category for company_id in target_zone is permitted.

    Returns ResidencyDecision with ALLOWED, BLOCKED (→ 451), or NEEDS_CONSENT.
    """
    # Always-EU categories
    if data_category in ALWAYS_EU:
        zone_juris = ZONE_JURISDICTION.get(target_zone, "UNKNOWN")
        if zone_juris not in ("EU", "EU,CH"):
            return ResidencyDecision(
                outcome=ResidencyOutcome.BLOCKED,
                data_category=data_category,
                company_id=company_id,
                requested_zone=target_zone,
                required_jurisdiction="EU",
                reason=f"{data_category} must remain in EU jurisdiction",
            )
        return ResidencyDecision(
            outcome=ResidencyOutcome.ALLOWED,
            data_category=data_category,
            company_id=company_id,
            requested_zone=target_zone,
            required_jurisdiction="EU",
        )

    # Check DB policy
    policy = _get_policy(company_id, data_category, db_path)

    if policy is None:
        # No recorded policy → allowed (permissive default)
        return ResidencyDecision(
            outcome=ResidencyOutcome.ALLOWED,
            data_category=data_category,
            company_id=company_id,
            requested_zone=target_zone,
            reason="No residency policy recorded — permissive default",
        )
    required_juris = policy.get("required_jurisdiction")

    zone_juris = ZONE_JURISDICTION.get(target_zone, "UNKNOWN")

    if zone_juris == required_juris or zone_juris.startswith(required_juris):
        return ResidencyDecision(
            outcome=ResidencyOutcome.ALLOWED,
            data_category=data_category,
            company_id=company_id,
            requested_zone=target_zone,
            required_jurisdiction=required_juris,
            policy_id=policy.get("id") if policy else None,
        )

    # Check if consent was given
    if policy and policy.get("consented_at"):
        return ResidencyDecision(
            outcome=ResidencyOutcome.ALLOWED,
            data_category=data_category,
            company_id=company_id,
            requested_zone=target_zone,
            required_jurisdiction=required_juris,
            reason="Cross-jurisdiction transfer — explicit consent on file",
        )

    logger.warning(
        "DRPL BLOCKED: company=%s category=%s zone=%s zone_juris=%s required=%s",
        company_id, data_category, target_zone, zone_juris, required_juris
    )

    return ResidencyDecision(
        outcome=ResidencyOutcome.BLOCKED,
        data_category=data_category,
        company_id=company_id,
        requested_zone=target_zone,
        required_jurisdiction=required_juris,
        policy_id=policy.get("id") if policy else None,
        reason=f"Zone '{target_zone}' ({zone_juris}) does not satisfy required jurisdiction '{required_juris}'",
    )


def _get_policy(company_id: str, data_category: str,
                db_path: str = _DB_PATH) -> Optional[dict]:
    try:
        con = _gov_conn(db_path)
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM data_residency_policies WHERE company_id = ? AND data_category = ? AND active = 1",
            (company_id, data_category)
        )
        row = cur.fetchone()
        con.close()
        return dict(row) if row else None
    except Exception:
        return None


def get_policies(company_id: str, db_path: str = _DB_PATH) -> list[dict]:
    try:
        con = _gov_conn(db_path)
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM data_residency_policies WHERE company_id = ? ORDER BY data_category",
            (company_id,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        return []


def upsert_policy(
    company_id: str,
    data_category: str,
    required_jurisdiction: str,
    storage_zone: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> dict:
    import uuid
    from datetime import datetime, timezone
    policy_id = str(uuid.uuid4())
    try:
        con = _gov_conn(db_path)
        cur = con.cursor()
        cur.execute(
            """INSERT INTO data_residency_policies
               (id, company_id, data_category, required_jurisdiction, storage_zone, consented_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(company_id, data_category)
               DO UPDATE SET required_jurisdiction=excluded.required_jurisdiction,
                             storage_zone=excluded.storage_zone,
                             consented_at=excluded.consented_at""",
            (policy_id, company_id, data_category, required_jurisdiction,
             storage_zone, datetime.now(timezone.utc).isoformat())
        )
        con.commit()
        con.close()
        return {"status": "ok", "company_id": company_id, "data_category": data_category}
    except Exception as exc:
        return {"error": str(exc)}


def get_residency_audit(company_id: str, db_path: str = _DB_PATH) -> dict:
    """
    Recorded required jurisdiction per data category, for the CISO view.

    Where the data actually sits is not measured, so nothing is claimed about it
    (2026-10-25: this used to report every category stored in "eu-west-1" and
    COMPLIANT — a placeholder — and fill gaps from sample company defaults).
    """
    policies = {p["data_category"]: p for p in get_policies(company_id, db_path)}
    return {"company_id": company_id, "storage_checked": False, "categories": {
        cat.value: {
            "required_jurisdiction": ("EU" if cat.value in ALWAYS_EU else
                                      policies[cat.value]["required_jurisdiction"] if cat.value in policies else None),
            "policy_source": ("ALWAYS_EU" if cat.value in ALWAYS_EU else
                              "RECORDED" if cat.value in policies else "NONE"),
            "current_zone": None,
            "status": "NOT_CHECKED",
        } for cat in DataCategory}}
