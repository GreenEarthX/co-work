"""
GEX OT/IT Boundary Security
==============================
Enforces one-way data flow from Operational Technology (OT) to IT.
GEX NEVER initiates connections to OT zone.

Architecture:
  OT Zone (ISA 62443 L3-4)
    SCADA → Historian → OT Gateway
      ↓ ONE-WAY ONLY (mTLS + SHA-256)
  DMZ Relay
      ↓
  GEX Ingestion API (POST /api/v1/plant-data/ingest)
      ↓
  plant_data table (append-only)
      ↓
  bankability_client: metered output → G11 evidence, quality → G2 evidence

Reference: GEX Security Architecture Extension v1.0, Domain 4
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("gex.ot_boundary")

_DB_PATH = "gex_platform.db"


# ═══════════════════════════════════════════════════════════════
# ENUMS / TYPES
# ═══════════════════════════════════════════════════════════════

ALLOWED_DATA_TYPES = {
    "PRODUCTION_VOLUME",       # m³/h H2, t/day NH3, etc.
    "POWER_CONSUMPTION",       # MWh
    "ELECTROLYSER_EFFICIENCY", # kWh/kg H2
    "QUALITY_CERTIFICATE",     # purity, carbon intensity per kg
    "METERED_DELIVERY",        # GoO delivery confirmation
    "PLANT_STATUS",            # OPERATING | MAINTENANCE | SHUTDOWN
    "ALARM_EVENT",             # plant alarm (metadata only, no SCADA raw)
    "GHG_MEASUREMENT",         # gCO2eq/MJ for RED III
}

# Commands GEX must NEVER send to OT
FORBIDDEN_COMMAND_TYPES = {
    "SETPOINT_CHANGE",
    "VALVE_COMMAND",
    "EMERGENCY_STOP",
    "FIRMWARE_UPDATE",
    "PARAMETER_WRITE",
}


@dataclass
class BoundaryValidation:
    valid: bool
    gateway_id: str
    data_type: str
    sha256_match: bool
    schema_valid: bool
    reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════════════════

def init_ot_db(db_path: str = _DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS gateway_registry (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            gateway_name TEXT NOT NULL,
            cert_fingerprint TEXT,          -- mTLS client cert SHA-256
            ip_allowlist TEXT,              -- JSON array of allowed IPs
            active INTEGER DEFAULT 1,
            registered_at TEXT DEFAULT (datetime('now')),
            last_seen TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_gateway_project
            ON gateway_registry(project_id);

        CREATE TABLE IF NOT EXISTS plant_data (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            gateway_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            sha256_hash TEXT NOT NULL,
            received_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS ix_plant_data_project
            ON plant_data(project_id, received_at);
        CREATE INDEX IF NOT EXISTS ix_plant_data_type
            ON plant_data(data_type);
    """)

    # Seed demo gateway for Breizh SAF
    cur.execute("SELECT COUNT(*) FROM gateway_registry")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """INSERT OR IGNORE INTO gateway_registry
               (id, project_id, gateway_name, cert_fingerprint, ip_allowlist)
               VALUES (?,?,?,?,?)""",
            ("gw-breizh-001", "proj_breizh_saf", "Breizh SAF OT Gateway",
             "sha256:demo_cert_fingerprint_change_in_production",
             json.dumps(["10.0.100.1", "10.0.100.2", "127.0.0.1"]))
        )

    con.commit()
    con.close()


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════

def validate_inbound(
    gateway_id: str,
    data_type: str,
    payload: dict,
    claimed_sha256: str,
    source_ip: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> BoundaryValidation:
    """
    Validate an inbound OT data packet before accepting it.
    Checks: registered gateway, data type allowlist, SHA-256 integrity.
    """
    # Reject any command attempts (should never come inbound, but defence-in-depth)
    if data_type in FORBIDDEN_COMMAND_TYPES:
        logger.error("OT BOUNDARY: FORBIDDEN command type attempted: %s from %s", data_type, gateway_id)
        return BoundaryValidation(
            valid=False, gateway_id=gateway_id, data_type=data_type,
            sha256_match=False, schema_valid=False,
            reason=f"Command type '{data_type}' is forbidden on the IT/OT boundary",
        )

    # Check data type allowlist
    if data_type not in ALLOWED_DATA_TYPES:
        return BoundaryValidation(
            valid=False, gateway_id=gateway_id, data_type=data_type,
            sha256_match=False, schema_valid=False,
            reason=f"Data type '{data_type}' not in allowlist",
        )

    # Check gateway registration
    gw = _get_gateway(gateway_id, db_path)
    if not gw:
        return BoundaryValidation(
            valid=False, gateway_id=gateway_id, data_type=data_type,
            sha256_match=False, schema_valid=False,
            reason=f"Gateway '{gateway_id}' not registered",
        )

    if not gw.get("active"):
        return BoundaryValidation(
            valid=False, gateway_id=gateway_id, data_type=data_type,
            sha256_match=False, schema_valid=False,
            reason="Gateway is disabled",
        )

    # IP allowlist check
    if source_ip:
        ip_list = json.loads(gw.get("ip_allowlist", "[]"))
        if ip_list and source_ip not in ip_list:
            return BoundaryValidation(
                valid=False, gateway_id=gateway_id, data_type=data_type,
                sha256_match=False, schema_valid=False,
                reason=f"Source IP {source_ip} not in gateway allowlist",
            )

    # SHA-256 verification
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    actual_hash = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    sha256_ok = actual_hash == claimed_sha256

    if not sha256_ok:
        logger.warning("OT BOUNDARY: SHA-256 mismatch gateway=%s expected=%s got=%s",
                       gateway_id, claimed_sha256, actual_hash)

    # Update last_seen
    _update_gateway_seen(gateway_id, db_path)

    return BoundaryValidation(
        valid=sha256_ok,
        gateway_id=gateway_id,
        data_type=data_type,
        sha256_match=sha256_ok,
        schema_valid=True,
        reason=None if sha256_ok else "SHA-256 hash mismatch — data integrity failure",
    )


def store_plant_data(
    gateway_id: str,
    project_id: str,
    data_type: str,
    payload: dict,
    sha256_hash: str,
    db_path: str = _DB_PATH,
) -> str:
    """Append plant data record. Returns record_id."""
    record_id = str(uuid.uuid4())
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(
            """INSERT INTO plant_data (id, project_id, gateway_id, data_type, payload_json, sha256_hash)
               VALUES (?,?,?,?,?,?)""",
            (record_id, project_id, gateway_id, data_type,
             json.dumps(payload), sha256_hash)
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.error("OT store_plant_data failed: %s", exc)
    return record_id


def get_plant_data(project_id: str, data_type: Optional[str] = None,
                   limit: int = 100, db_path: str = _DB_PATH) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    if data_type:
        cur.execute(
            "SELECT * FROM plant_data WHERE project_id = ? AND data_type = ? ORDER BY received_at DESC LIMIT ?",
            (project_id, data_type, limit)
        )
    else:
        cur.execute(
            "SELECT * FROM plant_data WHERE project_id = ? ORDER BY received_at DESC LIMIT ?",
            (project_id, limit)
        )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["payload_json"] = json.loads(d["payload_json"])
        rows.append(d)
    con.close()
    return rows


def get_gateways(project_id: Optional[str] = None, db_path: str = _DB_PATH) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    if project_id:
        cur.execute("SELECT * FROM gateway_registry WHERE project_id = ?", (project_id,))
    else:
        cur.execute("SELECT * FROM gateway_registry")
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def _get_gateway(gateway_id: str, db_path: str) -> Optional[dict]:
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM gateway_registry WHERE id = ?", (gateway_id,))
        row = cur.fetchone()
        con.close()
        return dict(row) if row else None
    except Exception:
        return None


def _update_gateway_seen(gateway_id: str, db_path: str) -> None:
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(
            "UPDATE gateway_registry SET last_seen = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), gateway_id)
        )
        con.commit()
        con.close()
    except Exception:
        pass
