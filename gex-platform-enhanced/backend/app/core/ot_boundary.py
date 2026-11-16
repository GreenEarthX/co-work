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
from datetime import date, datetime, timezone
from typing import Callable, Optional
from app.core.config import settings
from app.core.db_backend import domain_connection, domain_is_postgres

logger = logging.getLogger("gex.ot_boundary")

_DB_PATH = settings.SQLITE_DB_PATH


# ═══════════════════════════════════════════════════════════════
# ENUMS / TYPES
# ═══════════════════════════════════════════════════════════════

ALLOWED_DATA_TYPES = {
    "PRODUCTION_VOLUME",       # metered: quantity + unit (kg, t, kg/h, t/h, t/d) per interval
    "POWER_CONSUMPTION",       # metered: quantity + unit (kWh, MWh, GWh, kW, MW) per interval
    "PPA_GENERATION",          # metered (099): generation of one registered PPA, MWh per interval
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


# ── Metered readings (migration 098, GreenMesh Phase 1 Step 3) ────────────────
# A metered payload names its quantity, its unit and its interval explicitly:
#   {"quantity": 12.5, "unit": "t", "interval_start": "2026-02-01T00:00:00+00:00",
#    "interval_end": "2026-02-02T00:00:00+00:00", "molecule": "H2"}
# It is stored normalised to kg (production) or MWh (power) for that interval. A rate
# unit is multiplied by the interval's hours. A unit not listed here is REFUSED.
# Volumes (G-22, Phase 2 Step 1): hydrogen in Nm3 or Nm3/h converts to kg with the APPROVED
# reference row `h2_density_normal_0c_101325pa` in force on the interval's first day, and the
# reading keeps that row's id. With no approved row the reading is refused — no density is
# ever assumed. An actual m3 (or m3/h) is refused outright: it needs the gas's pressure and
# temperature, which a reading does not carry. Other molecules have no density key.
METERED_DATA_TYPES = {"PRODUCTION_VOLUME", "POWER_CONSUMPTION", "PPA_GENERATION"}
_TOTAL_UNITS = {
    "PRODUCTION_VOLUME": {"kg": 1.0, "t": 1000.0},
    "POWER_CONSUMPTION": {"kWh": 0.001, "MWh": 1.0, "GWh": 1000.0},
    "PPA_GENERATION": {"kWh": 0.001, "MWh": 1.0, "GWh": 1000.0},
}
_RATE_UNITS_PER_HOUR = {
    "PRODUCTION_VOLUME": {"kg/h": 1.0, "t/h": 1000.0, "kg/d": 1.0 / 24, "t/d": 1000.0 / 24,
                          "t/day": 1000.0 / 24},
    "POWER_CONSUMPTION": {"kW": 0.001, "MW": 1.0},
    "PPA_GENERATION": {"kW": 0.001, "MW": 1.0},
}
NORMALISED_UNIT = {"PRODUCTION_VOLUME": "kg", "POWER_CONSUMPTION": "MWh", "PPA_GENERATION": "MWh"}
_NORMAL_VOLUME_UNITS = {"Nm3": None, "Nm3/h": 1.0}       # None: a total; 1.0: per hour
H2_DENSITY_KEY = "h2_density_normal_0c_101325pa"


def approved_h2_density(on: date) -> Optional[dict]:
    """The APPROVED hydrogen density (kg per Nm3) in force on `on`, or None."""
    from app.core import reference_registry as reg

    if not reg.registry_available():
        return None
    conn = reg._connection()
    try:
        row = reg.resolve(conn, H2_DENSITY_KEY, "H2", "ANY", on.isoformat())
    finally:
        conn.close()
    return {"kg_per_nm3": float(row["value_base"]), "ref_id": row["ref_id"]} if row else None


class MeteredPayloadError(ValueError):
    pass


def _instant(value, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise MeteredPayloadError(f"{field} must be an ISO-8601 date-time") from exc
    if dt.tzinfo is None:
        raise MeteredPayloadError(f"{field} must carry a UTC offset")
    return dt


def normalise_metered(data_type: str, payload: dict,
                      density_on: Callable[[date], Optional[dict]] = approved_h2_density) -> dict:
    """The normalised reading, or MeteredPayloadError saying what is missing or wrong."""
    unit = payload.get("unit")
    if not isinstance(unit, str) or not unit:
        raise MeteredPayloadError(f"{data_type} needs an explicit unit")
    qty = payload.get("quantity")
    if isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty < 0:
        raise MeteredPayloadError("quantity must be a number, zero or more")
    start = _instant(payload.get("interval_start"), "interval_start")
    end = _instant(payload.get("interval_end"), "interval_end")
    if end <= start:
        raise MeteredPayloadError("interval_end must be after interval_start")
    hours = (end - start).total_seconds() / 3600
    conversion_ref_id = None
    if data_type == "PRODUCTION_VOLUME" and unit in _NORMAL_VOLUME_UNITS:
        if payload.get("molecule") != "H2":
            raise MeteredPayloadError(f"a volume ({unit}) converts to kg only for hydrogen; report "
                                      f"{payload.get('molecule')!r} in kg or t")
        d = density_on(start.date())
        if not d:
            raise MeteredPayloadError(f"no APPROVED hydrogen density ({H2_DENSITY_KEY}) is in force on "
                                      f"{start.date()}: {unit} cannot be converted (G-22)")
        per_hour = _NORMAL_VOLUME_UNITS[unit]
        q = float(qty) * (hours if per_hour else 1.0) * d["kg_per_nm3"]
        conversion_ref_id = d["ref_id"]
    elif data_type == "PRODUCTION_VOLUME" and unit in ("m3", "m3/h"):
        raise MeteredPayloadError(f"an actual volume ({unit}) needs the gas's pressure and temperature; "
                                  "report Nm3 (0 °C, 101.325 kPa), kg or t")
    elif unit in _TOTAL_UNITS[data_type]:
        q = float(qty) * _TOTAL_UNITS[data_type][unit]
    elif unit in _RATE_UNITS_PER_HOUR[data_type]:
        q = float(qty) * _RATE_UNITS_PER_HOUR[data_type][unit] * hours
    else:
        known = sorted(_TOTAL_UNITS[data_type]) + sorted(_RATE_UNITS_PER_HOUR[data_type])
        raise MeteredPayloadError(f"unit {unit!r} is not accepted for {data_type}; use one of {known}")
    molecule = payload.get("molecule")
    if data_type == "PRODUCTION_VOLUME" and not (isinstance(molecule, str) and molecule):
        raise MeteredPayloadError("PRODUCTION_VOLUME names its molecule")
    ppa_ref = payload.get("ppa_ref")
    if data_type == "PPA_GENERATION" and not (isinstance(ppa_ref, str) and ppa_ref):
        raise MeteredPayloadError("PPA_GENERATION names its ppa_ref")
    return {"molecule": molecule if data_type == "PRODUCTION_VOLUME" else None,
            "ppa_ref": ppa_ref if data_type == "PPA_GENERATION" else None,
            "interval_start": start, "interval_end": end,
            "quantity_normalised": q, "normalised_unit": NORMALISED_UNIT[data_type],
            "conversion_ref_id": conversion_ref_id}


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

def _conn(db_path: str):
    """SQLite at an explicit path, or the shared PostgreSQL store.

    `db_path` is honoured only on SQLite — it is how tests point this module at
    a throwaway file. On PostgreSQL there is one database and the caller's
    tenant context decides what is visible, so a path would be meaningless.
    """
    if domain_is_postgres():
        return domain_connection()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def init_ot_db(db_path: str = _DB_PATH) -> None:
    if domain_is_postgres():
        # 044 owns gateway_registry and plant_data. The demo gateway seeded
        # below is not seeded there either: a fabricated gateway with a
        # placeholder certificate fingerprint is demo furniture, and inventing
        # one in the system of record is exactly what this cutover is undoing.
        return
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

    # No seeded gateway (2026-10-25): one was registered for a project that
    # does not exist ("proj_breizh_saf"). Gateways are registered, not seeded.

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
    project_id: Optional[str] = None,
) -> BoundaryValidation:
    """
    Validate an inbound OT data packet before accepting it.
    Checks: registered gateway, the gateway's own project (when `project_id` is given),
    data type allowlist, a metered payload's unit and interval, SHA-256 integrity.
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

    if project_id is not None and gw.get("project_id") != project_id:
        return BoundaryValidation(
            valid=False, gateway_id=gateway_id, data_type=data_type,
            sha256_match=False, schema_valid=False,
            reason=f"Gateway '{gateway_id}' reports for another project than {project_id}",
        )

    if data_type in METERED_DATA_TYPES:
        if not gw.get("facility_id"):
            return BoundaryValidation(
                valid=False, gateway_id=gateway_id, data_type=data_type,
                sha256_match=False, schema_valid=False,
                reason=f"Gateway '{gateway_id}' names no facility, so its meter readings cannot be placed",
            )
        try:
            normalise_metered(data_type, payload)
        except MeteredPayloadError as exc:
            return BoundaryValidation(
                valid=False, gateway_id=gateway_id, data_type=data_type,
                sha256_match=False, schema_valid=False, reason=str(exc),
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
    """Append plant data record. Returns record_id.

    Raises on failure. It used to log and return a record id anyway, so the ingest
    route answered "accepted" for a reading that was never stored. A metered reading
    (PRODUCTION_VOLUME, POWER_CONSUMPTION) is PostgreSQL only and stored normalised,
    with its gateway's facility (migration 098).
    """
    record_id = str(uuid.uuid4())
    received_at = datetime.now(timezone.utc).isoformat()
    metered = data_type in METERED_DATA_TYPES
    if metered and not domain_is_postgres():
        from app.core.db_backend import require_postgres

        require_postgres(False, "Metered plant data", "DOMAIN_DB_BACKEND")
    con = _conn(db_path)
    try:
        cur = con.cursor()
        # received_at is set here, not by a column default: SQLite defaults it
        # with datetime('now') and PostgreSQL (044) has no default at all, so
        # leaving it out would silently store NULL on one store only.
        if metered:
            n = normalise_metered(data_type, payload)
            gw = cur.execute("SELECT facility_id FROM gateway_registry WHERE id = ?", (gateway_id,)).fetchone()
            ppa_id = None
            if n["ppa_ref"]:
                ppa = cur.execute("SELECT ppa_id FROM coc_ppa WHERE project_id = ? AND ppa_ref = ?",
                                  (project_id, n["ppa_ref"])).fetchone()
                if not ppa:
                    raise MeteredPayloadError(f"PPA {n['ppa_ref']!r} is not registered for project {project_id}")
                ppa_id = ppa["ppa_id"]
            cur.execute(
                """INSERT INTO plant_data (id, project_id, gateway_id, data_type, payload_json, sha256_hash,
                       received_at, facility_id, molecule, interval_start, interval_end,
                       quantity_normalised, normalised_unit, ppa_id, conversion_ref_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, project_id, gateway_id, data_type, json.dumps(payload), sha256_hash,
                 received_at, gw["facility_id"] if gw else None, n["molecule"], n["interval_start"],
                 n["interval_end"], n["quantity_normalised"], n["normalised_unit"], ppa_id,
                 n["conversion_ref_id"]))
        else:
            cur.execute(
                """INSERT INTO plant_data (id, project_id, gateway_id, data_type, payload_json, sha256_hash, received_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (record_id, project_id, gateway_id, data_type,
                 json.dumps(payload), sha256_hash, received_at)
            )
        con.commit()
    except Exception:
        try:
            con.rollback()
        finally:
            logger.error("OT store_plant_data failed for gateway %s (%s)", gateway_id, data_type)
        raise
    finally:
        con.close()
    return record_id


def get_plant_data(project_id: str, data_type: Optional[str] = None,
                   limit: int = 100, db_path: str = _DB_PATH) -> list[dict]:
    con = _conn(db_path)
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
        for k in ("interval_start", "interval_end"):
            if hasattr(d.get(k), "isoformat"):
                d[k] = d[k].isoformat()
        rows.append(d)
    con.close()
    return rows


def get_gateways(project_id: Optional[str] = None, db_path: str = _DB_PATH) -> list[dict]:
    con = _conn(db_path)
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
        con = _conn(db_path)
        cur = con.cursor()
        cur.execute("SELECT * FROM gateway_registry WHERE id = ?", (gateway_id,))
        row = cur.fetchone()
        con.close()
        return dict(row) if row else None
    except Exception:
        return None


def _update_gateway_seen(gateway_id: str, db_path: str) -> None:
    try:
        con = _conn(db_path)
        cur = con.cursor()
        cur.execute(
            "UPDATE gateway_registry SET last_seen = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), gateway_id)
        )
        con.commit()
        con.close()
    except Exception:
        pass
