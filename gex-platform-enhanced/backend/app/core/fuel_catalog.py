"""Database-backed fuel catalogue and unit conversion rules."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app.core.config import settings

DB_PATH = settings.SQLITE_DB_PATH


def _resolve_legacy_catalog_path() -> Path:
    """Locate gex_fuel_catalog.json across host and container layouts.

    On a dev checkout the file sits four levels above this module; in the
    Docker image the backend is the root, so it is copied alongside /app.
    """
    override = os.getenv("GEX_FUEL_CATALOG_PATH")
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    candidates = [
        # dev checkout: <workspace>/gex-platform-enhanced/backend/app/core/
        *(p / "gex_fuel_catalog.json" for p in here.parents[:5]),
        # container: WORKDIR /app
        Path("/app/gex_fuel_catalog.json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # nothing found — return the dev-layout path so errors stay readable
    return here.parents[min(4, len(here.parents) - 1)] / "gex_fuel_catalog.json"


LEGACY_CATALOG_PATH = _resolve_legacy_catalog_path()


def _get_conn() -> sqlite3.Connection:
    """
    Slice-6b-3 connection — SQLite or PostgreSQL by configuration
    (FUELREF_DB_BACKEND).
    """
    from app.core.db_backend import fuelref_connection

    return fuelref_connection()


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """
    SQLite only. On PostgreSQL the schema is owned by alembic (migration 041),
    which also carries the real FK (fuel_unit_conversions -> fuel_catalog,
    ON DELETE CASCADE), the UNIQUE(fuel_id, from_unit, to_unit) rule and the
    RLS policies. CREATE TABLE IF NOT EXISTS here would silently no-op or, on
    a fresh database, create unprotected tables without any of them.
    """
    from app.core.db_backend import fuelref_is_postgres

    if fuelref_is_postgres():
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_catalog (
            fuel_id TEXT PRIMARY KEY,
            label TEXT NOT NULL UNIQUE,
            offered INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            legacy_aliases_json TEXT NOT NULL DEFAULT '[]',
            applications_json TEXT NOT NULL DEFAULT '[]',
            trading_unit TEXT NOT NULL,
            price_unit TEXT NOT NULL,
            mass_unit TEXT NOT NULL,
            energy_unit TEXT NOT NULL,
            specific_energy_unit TEXT NOT NULL DEFAULT 'kWh/kg',
            specific_energy_value REAL,
            capacity_unit TEXT NOT NULL,
            emissions_unit TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_by TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_unit_conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuel_id TEXT NOT NULL,
            from_unit TEXT NOT NULL,
            to_unit TEXT NOT NULL,
            multiplier REAL NOT NULL,
            offset REAL NOT NULL DEFAULT 0,
            dimension TEXT NOT NULL,
            rule_type TEXT NOT NULL DEFAULT 'system',
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (fuel_id) REFERENCES fuel_catalog(fuel_id) ON DELETE CASCADE,
            UNIQUE (fuel_id, from_unit, to_unit)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fuel_catalog_label ON fuel_catalog(label)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fuel_catalog_active ON fuel_catalog(is_active, offered)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fuel_conversion_fuel ON fuel_unit_conversions(fuel_id)")
    conn.commit()


def _load_legacy_seed() -> dict[str, Any]:
    with LEGACY_CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _base_conversion_rules(fuel: dict[str, Any]) -> list[dict[str, Any]]:
    fuel_id = fuel["id"]
    measures = fuel.get("measures", {})
    specific_energy = measures.get("specific_energy_value")

    rules = [
        {
            "fuel_id": fuel_id,
            "from_unit": "kg",
            "to_unit": "t",
            "multiplier": 0.001,
            "offset": 0.0,
            "dimension": "mass",
            "rule_type": "system",
            "note": "Metric mass conversion",
        },
        {
            "fuel_id": fuel_id,
            "from_unit": "t",
            "to_unit": "kg",
            "multiplier": 1000.0,
            "offset": 0.0,
            "dimension": "mass",
            "rule_type": "system",
            "note": "Metric mass conversion",
        },
        {
            "fuel_id": fuel_id,
            "from_unit": "kWh",
            "to_unit": "MWh",
            "multiplier": 0.001,
            "offset": 0.0,
            "dimension": "energy",
            "rule_type": "system",
            "note": "Metric energy conversion",
        },
        {
            "fuel_id": fuel_id,
            "from_unit": "MWh",
            "to_unit": "kWh",
            "multiplier": 1000.0,
            "offset": 0.0,
            "dimension": "energy",
            "rule_type": "system",
            "note": "Metric energy conversion",
        },
        {
            "fuel_id": fuel_id,
            "from_unit": "MTPD",
            "to_unit": "t/day",
            "multiplier": 1.0,
            "offset": 0.0,
            "dimension": "capacity",
            "rule_type": "system",
            "note": "GEX production capacity shorthand",
        },
        {
            "fuel_id": fuel_id,
            "from_unit": "t/day",
            "to_unit": "MTPD",
            "multiplier": 1.0,
            "offset": 0.0,
            "dimension": "capacity",
            "rule_type": "system",
            "note": "GEX production capacity shorthand",
        },
    ]

    if specific_energy and specific_energy > 0:
        rules.extend(
            [
                {
                    "fuel_id": fuel_id,
                    "from_unit": "kg",
                    "to_unit": "kWh",
                    "multiplier": specific_energy,
                    "offset": 0.0,
                    "dimension": "mass_energy",
                    "rule_type": "derived",
                    "note": "Derived from indicative specific energy",
                },
                {
                    "fuel_id": fuel_id,
                    "from_unit": "kWh",
                    "to_unit": "kg",
                    "multiplier": 1 / specific_energy,
                    "offset": 0.0,
                    "dimension": "energy_mass",
                    "rule_type": "derived",
                    "note": "Derived from indicative specific energy",
                },
                {
                    "fuel_id": fuel_id,
                    "from_unit": "t",
                    "to_unit": "MWh",
                    "multiplier": specific_energy,
                    "offset": 0.0,
                    "dimension": "mass_energy",
                    "rule_type": "derived",
                    "note": "Derived from indicative specific energy",
                },
                {
                    "fuel_id": fuel_id,
                    "from_unit": "MWh",
                    "to_unit": "t",
                    "multiplier": 1 / specific_energy,
                    "offset": 0.0,
                    "dimension": "energy_mass",
                    "rule_type": "derived",
                    "note": "Derived from indicative specific energy",
                },
                {
                    "fuel_id": fuel_id,
                    "from_unit": "t",
                    "to_unit": "kWh",
                    "multiplier": specific_energy * 1000,
                    "offset": 0.0,
                    "dimension": "mass_energy",
                    "rule_type": "derived",
                    "note": "Derived from indicative specific energy",
                },
                {
                    "fuel_id": fuel_id,
                    "from_unit": "kWh",
                    "to_unit": "t",
                    "multiplier": 1 / (specific_energy * 1000),
                    "offset": 0.0,
                    "dimension": "energy_mass",
                    "rule_type": "derived",
                    "note": "Derived from indicative specific energy",
                },
            ]
        )

    return rules


def _merge_rules(
    fuel: dict[str, Any],
    custom_rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    merged = {
        (rule["from_unit"], rule["to_unit"]): rule
        for rule in _base_conversion_rules(fuel)
    }
    for rule in custom_rules or []:
        merged[(rule["from_unit"], rule["to_unit"])] = {
            "fuel_id": fuel["id"],
            "from_unit": rule["from_unit"],
            "to_unit": rule["to_unit"],
            "multiplier": float(rule["multiplier"]),
            "offset": float(rule.get("offset", 0.0)),
            "dimension": rule.get("dimension", "custom"),
            "rule_type": rule.get("rule_type", "custom"),
            "note": rule.get("note"),
        }
    return list(merged.values())


def _replace_conversion_rules(
    conn: sqlite3.Connection,
    fuel: dict[str, Any],
    custom_rules: list[dict[str, Any]] | None = None,
) -> None:
    conn.execute("DELETE FROM fuel_unit_conversions WHERE fuel_id = ?", (fuel["id"],))
    for rule in _merge_rules(fuel, custom_rules):
        conn.execute(
            """
            INSERT INTO fuel_unit_conversions (
                fuel_id, from_unit, to_unit, multiplier, offset,
                dimension, rule_type, note, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule["fuel_id"],
                rule["from_unit"],
                rule["to_unit"],
                rule["multiplier"],
                rule.get("offset", 0.0),
                rule["dimension"],
                rule["rule_type"],
                rule.get("note"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _bootstrap_from_seed(conn: sqlite3.Connection) -> None:
    seed = _load_legacy_seed()
    for index, fuel in enumerate(seed.get("fuels", []), start=1):
        measures = fuel.get("measures", {})
        conn.execute(
            """
            INSERT OR IGNORE INTO fuel_catalog (
                fuel_id, label, offered, status, legacy_aliases_json,
                applications_json, trading_unit, price_unit, mass_unit,
                energy_unit, specific_energy_unit, specific_energy_value,
                capacity_unit, emissions_unit, sort_order, is_active, updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                fuel["id"],
                fuel["label"],
                1 if fuel.get("offered") else 0,
                fuel.get("status", "active_catalog"),
                json.dumps(fuel.get("legacy_aliases", [])),
                json.dumps(fuel.get("applications", [])),
                measures.get("trading_unit", "t"),
                measures.get("price_unit", "EUR/t"),
                measures.get("mass_unit", "t"),
                measures.get("energy_unit", "kWh"),
                measures.get("specific_energy_unit", "kWh/kg"),
                measures.get("specific_energy_value"),
                measures.get("capacity_unit", "MTPD"),
                measures.get("emissions_unit", "kgCO2e/kg"),
                index,
                "seed:gex_fuel_catalog.json",
            ),
        )
        rule_count = conn.execute(
            "SELECT COUNT(*) AS count FROM fuel_unit_conversions WHERE fuel_id = ?",
            (fuel["id"],),
        ).fetchone()["count"]
        if rule_count == 0:
            _replace_conversion_rules(conn, fuel)
    conn.commit()


def init_fuel_catalog_db() -> None:
    conn = _get_conn()
    try:
        _ensure_tables(conn)
        _bootstrap_from_seed(conn)
    finally:
        conn.close()


def _conversion_rows(conn: sqlite3.Connection, fuel_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT from_unit, to_unit, multiplier, offset, dimension, rule_type, note
        FROM fuel_unit_conversions
        WHERE fuel_id = ?
        ORDER BY dimension, from_unit, to_unit
        """,
        (fuel_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _row_to_fuel(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    measures = {
        "trading_unit": row["trading_unit"],
        "price_unit": row["price_unit"],
        "mass_unit": row["mass_unit"],
        "energy_unit": row["energy_unit"],
        "specific_energy_unit": row["specific_energy_unit"],
        "specific_energy_value": row["specific_energy_value"],
        "capacity_unit": row["capacity_unit"],
        "emissions_unit": row["emissions_unit"],
    }
    return {
        "id": row["fuel_id"],
        "label": row["label"],
        "offered": bool(row["offered"]),
        "status": row["status"],
        "legacy_aliases": json.loads(row["legacy_aliases_json"] or "[]"),
        "applications": json.loads(row["applications_json"] or "[]"),
        "measures": measures,
        "conversion_rules": _conversion_rows(conn, row["fuel_id"]),
        "sort_order": row["sort_order"],
        "is_active": bool(row["is_active"]),
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    }


def list_fuels(
    *,
    offered_only: bool = False,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    init_fuel_catalog_db()
    conn = _get_conn()
    try:
        conditions: list[str] = []
        params: list[Any] = []
        if offered_only:
            conditions.append("offered = 1")
        if not include_inactive:
            conditions.append("is_active = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"""
            SELECT *
            FROM fuel_catalog
            {where}
            ORDER BY sort_order, label
            """,
            params,
        ).fetchall()
        return [_row_to_fuel(conn, row) for row in rows]
    finally:
        conn.close()


def load_fuel_catalog(
    *,
    offered_only: bool = False,
    include_inactive: bool = False,
) -> dict[str, Any]:
    fuels = list_fuels(offered_only=offered_only, include_inactive=include_inactive)
    version = max((fuel["updated_at"] for fuel in fuels), default=None)
    return {
        "version": version or datetime.now(timezone.utc).date().isoformat(),
        "source": "sqlite",
        "fuels": fuels,
    }


def get_fuel(fuel_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    init_fuel_catalog_db()
    conn = _get_conn()
    try:
        query = "SELECT * FROM fuel_catalog WHERE fuel_id = ?"
        params: list[Any] = [fuel_id]
        if not include_inactive:
            query += " AND is_active = 1"
        row = conn.execute(query, params).fetchone()
        if not row:
            return None
        return _row_to_fuel(conn, row)
    finally:
        conn.close()


def find_fuel(value: str) -> dict[str, Any] | None:
    needle = value.strip().lower()
    for fuel in list_fuels(include_inactive=False):
        aliases = [fuel.get("id", ""), fuel.get("label", ""), *fuel.get("legacy_aliases", [])]
        if any(alias and alias.lower() == needle for alias in aliases):
            return fuel
    return None


def offered_molecule_payload() -> list[dict[str, Any]]:
    return [
        {
            "code": fuel["label"],
            "name": fuel["label"],
            "description": fuel["applications"][0] if fuel.get("applications") else "",
            "typical_uses": fuel.get("applications", []),
            "measures": fuel.get("measures", {}),
        }
        for fuel in list_fuels(offered_only=True)
    ]


def convert_fuel_value(fuel_id: str, value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    init_fuel_catalog_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT multiplier, offset, rule_type, note
            FROM fuel_unit_conversions
            WHERE fuel_id = ? AND lower(from_unit) = lower(?) AND lower(to_unit) = lower(?)
            """,
            (fuel_id, from_unit, to_unit),
        ).fetchone()
        if not row:
            raise KeyError(f"No conversion rule for {fuel_id}: {from_unit} -> {to_unit}")
        converted = (value * row["multiplier"]) + row["offset"]
        return {
            "fuel_id": fuel_id,
            "input": {"value": value, "unit": from_unit},
            "output": {"value": converted, "unit": to_unit},
            "rule": {
                "multiplier": row["multiplier"],
                "offset": row["offset"],
                "rule_type": row["rule_type"],
                "note": row["note"],
            },
        }
    finally:
        conn.close()


def upsert_fuel(fuel: dict[str, Any], updated_by: str) -> dict[str, Any]:
    init_fuel_catalog_db()
    measures = fuel.get("measures", {})
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO fuel_catalog (
                fuel_id, label, offered, status, legacy_aliases_json,
                applications_json, trading_unit, price_unit, mass_unit,
                energy_unit, specific_energy_unit, specific_energy_value,
                capacity_unit, emissions_unit, sort_order, is_active,
                updated_at, updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fuel_id) DO UPDATE SET
                label=excluded.label,
                offered=excluded.offered,
                status=excluded.status,
                legacy_aliases_json=excluded.legacy_aliases_json,
                applications_json=excluded.applications_json,
                trading_unit=excluded.trading_unit,
                price_unit=excluded.price_unit,
                mass_unit=excluded.mass_unit,
                energy_unit=excluded.energy_unit,
                specific_energy_unit=excluded.specific_energy_unit,
                specific_energy_value=excluded.specific_energy_value,
                capacity_unit=excluded.capacity_unit,
                emissions_unit=excluded.emissions_unit,
                sort_order=excluded.sort_order,
                is_active=excluded.is_active,
                updated_at=excluded.updated_at,
                updated_by=excluded.updated_by
            """,
            (
                fuel["id"],
                fuel["label"],
                1 if fuel.get("offered", False) else 0,
                fuel.get("status", "active_catalog"),
                json.dumps(fuel.get("legacy_aliases", [])),
                json.dumps(fuel.get("applications", [])),
                measures.get("trading_unit", "t"),
                measures.get("price_unit", "EUR/t"),
                measures.get("mass_unit", "t"),
                measures.get("energy_unit", "kWh"),
                measures.get("specific_energy_unit", "kWh/kg"),
                measures.get("specific_energy_value"),
                measures.get("capacity_unit", "MTPD"),
                measures.get("emissions_unit", "kgCO2e/kg"),
                int(fuel.get("sort_order", 0)),
                1 if fuel.get("is_active", True) else 0,
                datetime.now(timezone.utc).isoformat(),
                updated_by,
            ),
        )
        _replace_conversion_rules(conn, fuel, fuel.get("conversion_rules", []))
        conn.commit()
        return get_fuel(fuel["id"], include_inactive=True) or fuel
    finally:
        conn.close()


def deactivate_fuel(fuel_id: str, updated_by: str) -> None:
    init_fuel_catalog_db()
    conn = _get_conn()
    try:
        conn.execute(
            """
            UPDATE fuel_catalog
            SET is_active = 0, updated_at = ?, updated_by = ?
            WHERE fuel_id = ?
            """,
            (datetime.now(timezone.utc).isoformat(), updated_by, fuel_id),
        )
        conn.commit()
    finally:
        conn.close()

