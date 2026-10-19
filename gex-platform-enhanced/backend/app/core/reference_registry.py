"""
Reference data registry — reading, resolving and curating reference values.
==========================================================================
Schema: alembic 061 (`reference_parameter`, `reference_version`). PostgreSQL only;
no table is created here. The tables belong to the fuel-reference slice, so the
connection is `fuelref_connection()`, and on SQLite the registry is simply absent:
every lookup falls back to the caller's code default, marked `model_default`.

Three rules from the design brief (docs/reference_registry):

  · Code holds no reference numbers. A constant is a last-resort fallback, used
    only when no approved value exists, and every use is logged.
  · Append-only. A value is never edited; approval supersedes the old row, which
    stays readable through `as_of`. The database enforces this (061's trigger).
  · No automatic change to project inputs. Nothing here writes a project.

The curation functions take a connection and never commit: the route commits, so
a test can run the whole lifecycle inside one transaction and roll it back.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, NamedTuple, Optional

from app.core.reference_catalog import (
    MONETARY_FAMILIES, PARAMETERS, PATHWAYS, SOURCE_CLASSES, UNIT_FAMILIES,
    family_of, pathway_chain, region_chain,
)

logger = logging.getLogger("gex.reference_registry")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REGION = re.compile(r"^([A-Z]{2}|EU|ROW|ANY)$")

# One WARNING per (key, pathway, region); every use is still logged at INFO.
_announced_fallback: set[tuple[str, str, str]] = set()


class RegistryError(ValueError):
    """A request the registry refuses. `status` is the HTTP code to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class Resolved(NamedTuple):
    """A value and where it came from: `reference` (a registry row) or `model_default`."""
    value: Any
    source_class: str
    ref_id: Optional[str] = None
    unit: Optional[str] = None
    value_low: Optional[float] = None
    value_high: Optional[float] = None


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def registry_available() -> bool:
    from app.core.db_backend import fuelref_is_postgres
    return fuelref_is_postgres()


def _connection():
    from app.core.db_backend import fuelref_connection
    return fuelref_connection()


def _iso_date(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    if not _ISO_DATE.match(value):
        raise RegistryError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError(f"{field} is not a valid date: {value!r}") from exc
    return value


# ── Reading ─────────────────────────────────────────────────────────────────

def in_force(conn, parameter_key: str, pathway: str, region: str,
             as_of: Optional[str] = None) -> Optional[dict]:
    """The row in force for EXACTLY (key, pathway, region) on `as_of` (default today).

    In force = approved or since superseded, `valid_from <= as_of`, latest
    `valid_from`. Approval requires a later `valid_from` than its predecessor, so
    the latest one on or before a date is the one that was in force on that date.
    """
    as_of = _iso_date(as_of, "as_of") or _today()
    row = conn.execute(
        "SELECT * FROM reference_parameter "
        "WHERE parameter_key = ? AND pathway = ? AND region = ? "
        "AND state IN ('approved', 'superseded') AND valid_from <= ? "
        "ORDER BY valid_from DESC LIMIT 1",
        (parameter_key, pathway, region, as_of)).fetchone()
    return dict(row) if row else None


def list_in_force(conn, parameter_key: Optional[str] = None, pathway: Optional[str] = None,
                  region: Optional[str] = None, as_of: Optional[str] = None) -> list[dict]:
    """Every (key, pathway, region) in force on `as_of`, optionally filtered exactly."""
    as_of = _iso_date(as_of, "as_of") or _today()
    where, params = ["state IN ('approved', 'superseded')", "valid_from <= ?"], [as_of]
    for col, val in (("parameter_key", parameter_key), ("pathway", pathway),
                     ("region", region)):
        if val is not None:
            where.append(f"{col} = ?")
            params.append(val)
    rows = conn.execute(
        "SELECT * FROM reference_parameter WHERE " + " AND ".join(where) +
        " ORDER BY parameter_key, pathway, region, valid_from DESC", tuple(params)).fetchall()
    latest: dict[tuple, dict] = {}
    for r in rows:
        latest.setdefault((r["parameter_key"], r["pathway"], r["region"]), dict(r))
    return list(latest.values())


def resolve(conn, parameter_key: str, pathway: str = "ANY", region: str = "ANY",
            as_of: Optional[str] = None) -> Optional[dict]:
    """The most specific row in force, walking pathway then region toward ANY.

    `H2_PEM`/`DE` tries H2_PEM, H2, ANY against DE, EU, ROW, ANY — pathway first,
    because a technology figure for the wrong region is closer than a generic
    figure for the right one. The returned row carries `matched_pathway` and
    `matched_region` so a caller can see how far it had to fall back.
    """
    for p in pathway_chain(pathway):
        for r in region_chain(region):
            row = in_force(conn, parameter_key, p, r, as_of)
            if row:
                row["matched_pathway"], row["matched_region"] = p, r
                return row
    return None


def resolve_or_default(parameter_key: str, default: Any, pathway: str = "ANY",
                       region: str = "ANY", as_of: Optional[str] = None,
                       conn=None) -> Resolved:
    """The registry value, or `default` marked `model_default` — and logged.

    This is the only sanctioned way for code to use a reference constant.
    """
    if parameter_key not in PARAMETERS:
        raise RegistryError(f"unknown parameter_key {parameter_key!r}")
    row = None
    if registry_available():
        own = conn is None
        c = conn or _connection()
        try:
            row = resolve(c, parameter_key, pathway, region, as_of)
        finally:
            if own:
                c.close()
    if row:
        return Resolved(row["value_base"], "reference", row["ref_id"], row["unit"],
                        row["value_low"], row["value_high"])

    key = (parameter_key, pathway, region)
    msg = ("reference fallback: no approved %s for pathway=%s region=%s; "
           "using code default %r (model_default)")
    if key not in _announced_fallback:
        _announced_fallback.add(key)
        logger.warning(msg, parameter_key, pathway, region, default)
    else:
        logger.info(msg, parameter_key, pathway, region, default)
    return Resolved(default, "model_default")


def get_row(conn, ref_id: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM reference_parameter WHERE ref_id = ?",
                       (ref_id,)).fetchone()
    return dict(row) if row else None


def latest_version(conn) -> Optional[dict]:
    row = conn.execute("SELECT * FROM reference_version "
                       "ORDER BY version_number DESC LIMIT 1").fetchone()
    return _version(row)


def get_version(conn, version_id: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM reference_version WHERE version_id = ?",
                       (version_id,)).fetchone()
    return _version(row)


def _version(row) -> Optional[dict]:
    if not row:
        return None
    d = dict(row)
    d["ref_ids"] = json.loads(d.pop("ref_ids_json"))
    return d


# ── Curating ────────────────────────────────────────────────────────────────

def validate_proposal(p: dict) -> dict:
    """Check a proposal against the closed catalog. Returns the normalised row."""
    key = p.get("parameter_key")
    family = family_of(key)
    if family is None:
        raise RegistryError(
            f"unknown parameter_key {key!r}: the catalog is closed "
            "(app/core/reference_catalog.py) so that two quantities never share a key")
    pathway = p.get("pathway") or "ANY"
    region = p.get("region") or "ANY"
    if pathway not in PATHWAYS:
        raise RegistryError(f"pathway must be one of {PATHWAYS}, got {pathway!r}")
    if not _REGION.match(region):
        raise RegistryError(f"region must be an ISO country, EU, ROW or ANY, got {region!r}")
    unit = p.get("unit")
    if unit not in UNIT_FAMILIES[family]:
        raise RegistryError(
            f"{key} is {family}; unit must be one of {UNIT_FAMILIES[family]}, got {unit!r}")
    if p.get("source_class") not in SOURCE_CLASSES:
        raise RegistryError(f"source_class must be one of {SOURCE_CLASSES}")
    if not p.get("source_name"):
        raise RegistryError("source_name is required")

    base = p.get("value_base")
    if base is None:
        raise RegistryError("value_base is required")
    low, high = p.get("value_low"), p.get("value_high")
    if (low is not None and low > base) or (high is not None and base > high):
        raise RegistryError("values must satisfy value_low <= value_base <= value_high")

    currency, price_date = p.get("currency"), _iso_date(p.get("price_base_date"),
                                                        "price_base_date")
    if family in MONETARY_FAMILIES:
        prefix = unit.split("/", 1)[0]
        if currency != prefix:
            raise RegistryError(f"{unit} is monetary: currency must be {prefix!r}")
        if not price_date:
            raise RegistryError("price_base_date is required for a monetary value")
    elif currency is not None:
        raise RegistryError(f"{key} is not monetary: currency must be empty")

    return {
        "parameter_key": key, "pathway": pathway, "region": region,
        "value_low": low, "value_base": base, "value_high": high, "unit": unit,
        "currency": currency, "price_base_date": price_date,
        "source_class": p["source_class"], "source_name": p["source_name"],
        "source_url": p.get("source_url"),
        "retrieved_at": _iso_date(p.get("retrieved_at"), "retrieved_at") or _today(),
        "valid_from": _iso_date(p.get("valid_from"), "valid_from") or _today(),
        "note": p.get("note"),
    }


def propose(conn, proposal: dict, actor: str) -> dict:
    """Insert a `proposed` row. Nothing reads it until it is approved."""
    row = validate_proposal(proposal)
    row.update(ref_id=str(uuid.uuid4()), state="proposed", proposed_by=actor,
               proposed_at=_now())
    cols = list(row)
    conn.execute(
        f"INSERT INTO reference_parameter ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})", tuple(row[c] for c in cols))
    return get_row(conn, row["ref_id"])


def _pending(conn, ref_id: str) -> dict:
    row = get_row(conn, ref_id)
    if row is None:
        raise RegistryError(f"no reference row {ref_id}", 404)
    if row["state"] != "proposed":
        raise RegistryError(f"{ref_id} is {row['state']}, not proposed", 409)
    return row


def approve(conn, ref_id: str, actor: str, reason: Optional[str] = None) -> dict:
    """Approve a proposal: supersede the current row, publish a new version.

    The approver may not be the proposer — the same separation of duties as
    account activation. Returns `{"parameter": row, "version": version}`.
    """
    row = _pending(conn, ref_id)
    if row["proposed_by"] == actor:
        raise RegistryError("the approver must not be the proposer", 403)

    current = conn.execute(
        "SELECT * FROM reference_parameter WHERE parameter_key = ? AND pathway = ? "
        "AND region = ? AND state = 'approved'",
        (row["parameter_key"], row["pathway"], row["region"])).fetchone()
    current = dict(current) if current else None
    if current and row["valid_from"] <= current["valid_from"]:
        raise RegistryError(
            f"valid_from {row['valid_from']} must be after the current value's "
            f"{current['valid_from']}, or as_of could not tell them apart", 409)

    now = _now()
    if current:
        conn.execute("UPDATE reference_parameter SET state = 'superseded' WHERE ref_id = ?",
                     (current["ref_id"],))
    conn.execute(
        "UPDATE reference_parameter SET state = 'approved', approved_by = ?, "
        "approved_at = ?, supersedes_ref_id = ? WHERE ref_id = ?",
        (actor, now, current["ref_id"] if current else None, ref_id))

    previous = latest_version(conn)
    ids = set(previous["ref_ids"]) if previous else set()
    if current:
        ids.discard(current["ref_id"])
    ids.add(ref_id)
    version_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO reference_version "
        "(version_id, version_number, created_at, created_by, reason, ref_ids_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (version_id, (previous["version_number"] if previous else 0) + 1, now, actor,
         reason or f"approved {row['parameter_key']} {row['pathway']}/{row['region']}",
         json.dumps(sorted(ids))))
    return {"parameter": get_row(conn, ref_id), "version": get_version(conn, version_id)}


def reject(conn, ref_id: str, actor: str) -> dict:
    _pending(conn, ref_id)
    conn.execute(
        "UPDATE reference_parameter SET state = 'rejected', rejected_by = ?, "
        "rejected_at = ? WHERE ref_id = ?", (actor, _now(), ref_id))
    return get_row(conn, ref_id)
