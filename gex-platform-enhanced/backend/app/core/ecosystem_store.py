"""
Ecosystem Navigator — server-side store for map publication.

WHY THIS EXISTS
---------------
Publishing a plant to the Ecosystem Map was implemented entirely in the browser:
`frontend/src/lib/ecosystem/userProjects.ts` wrote to `localStorage` under
`gex_ecosystem_user_projects` and `gex_ecosystem_enrichments`. Its own comment
said the record is published "so the project shows up on the map for everyone",
but localStorage is per-browser, so nothing reached another user, another device
or the backend. The feature did not do what it said.

DESIGN RULES (from docs/ecosystem-navigator-data-structure-review.md)
---------------------------------------------------------------------
1. ATTACH, NEVER OVERWRITE. A tenant enriching a map project writes their own
   enrichment row. Two tenants enriching the same project produce two rows and
   both survive. Nothing a publisher writes destroys another reading — which is
   what makes disagreement visible instead of averaged away.
2. WITHDRAW IS A SOFT DELETE. `withdrawn_at` is set; the row stays.
3. PUBLISHER CONFIDENTIALITY IS THE PUBLISHER'S. `visible_fields` records which
   optional extras the publisher chose to expose. It is honoured for every other
   viewer INCLUDING a platform admin — see `redact_for_viewer`. This is the
   Open Interest Board rule: publisher confidentiality is security, viewer
   preference is not, and admin does not bypass security.
4. NEWS NEVER WRITES HERE. This table holds Class B data — a tenant's own
   assertion about their own project, published by their own act. Ingested
   third-party data is Class C and belongs in its own namespace.

POSTGRES
--------
These tables are tenant-scoped, so on PostgreSQL they need RLS policies, which
belong in an Alembic migration alongside the other slices — not in a
CREATE TABLE IF NOT EXISTS here. `init_db()` therefore refuses to create them on
PostgreSQL rather than silently creating an unprotected table. All eight backend
switches currently read `sqlite`, so this is the live path today.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings

# Fields a publisher exposes by the act of publishing — they are what puts a
# marker on a map at all. Everything else is opt-in via `visible_fields`.
CORE_FIELDS = (
    "id", "name", "lat", "lng", "phase", "status", "layer", "country",
    "moleculeType", "productionPathway", "capacity", "owner", "dataSource",
)
# Optional extras, shown only when the publisher listed them.
GATED_FIELDS = (
    "commissioningYear", "website", "offtakers", "certifications", "technology",
)

USER_PUBLISHED = "user_published"

# Lifecycle is two fields (Data Structure v4.2): PHASE says where a project is in
# its life, STATUS whether it is going ahead. One list could express neither a
# cancelled project's phase nor a planned project's status.
#
# This mirrors `normaliseLifecycle` in frontend/src/lib/ecosystem/types.ts. Two
# copies exist deliberately and only for as long as legacy rows do: rows written
# before the split carry a single status, and both ends must read them the same
# way. `tests/test_ecosystem_publication.py` pins the table against that file.
PHASES = (
    "concept", "pre_feasibility", "feed", "financing",
    "construction", "commissioning", "operation", "unknown",
)
STATUSES = ("active", "on_hold", "cancelled", "mothballed", "decommissioned", "superseded")

# "planned" and "cancelled" land on an unknown phase on purpose: the first said
# only that building had not started, the second never recorded how far it got.
_LEGACY_LIFECYCLE = {
    "concept": ("concept", "active"),
    "planned": ("unknown", "active"),
    "construction": ("construction", "active"),
    "operational": ("operation", "active"),
    "cancelled": ("unknown", "cancelled"),
}


def normalise_lifecycle(phase: Optional[str], status: Optional[str]) -> tuple[str, str]:
    """(phase, status) from a record in either vocabulary. Never raises: this
    runs over third-party rows as well as our own.

    "unknown" is NOT a recorded phase — it is the absence of one, which is also
    what the additive migration writes into every pre-split row. So a stored
    "unknown" must not shadow the legacy status that carries the real meaning.
    """
    legacy = _LEGACY_LIFECYCLE.get(status or "")
    known_phase = phase if (phase in PHASES and phase != "unknown") else None
    if known_phase:
        if status in STATUSES:
            return known_phase, status
        return known_phase, legacy[1] if legacy else "active"
    if status in STATUSES:
        return "unknown", status
    if legacy:
        return legacy
    return "unknown", "active"


class PostgresMigrationRequired(RuntimeError):
    """Raised rather than creating a tenant table with no RLS behind it."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ecosystem_is_postgres() -> bool:
    import os
    return (os.getenv("ECOSYSTEM_DB_BACKEND") or "sqlite").strip().lower() == "postgres"


def init_db() -> None:
    if _ecosystem_is_postgres():
        raise PostgresMigrationRequired(
            "ecosystem tables are tenant-scoped and need RLS policies from an "
            "Alembic migration; refusing to create them unprotected"
        )
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ecosystem_published_projects (
                eco_project_id     TEXT PRIMARY KEY,
                tenant_id          TEXT NOT NULL,
                published_by       TEXT NOT NULL,
                slug               TEXT NOT NULL,
                name               TEXT NOT NULL,
                lat                REAL,
                lng                REAL,
                country            TEXT,
                molecule_type      TEXT,
                production_pathway TEXT,
                phase              TEXT NOT NULL DEFAULT 'unknown',
                status             TEXT NOT NULL,
                layer              TEXT NOT NULL DEFAULT 'production',
                owner_name         TEXT,
                capacity_label     TEXT,
                capacity_value     TEXT,
                capacity_unit      TEXT,
                extras             TEXT NOT NULL DEFAULT '{}',
                visible_fields     TEXT NOT NULL DEFAULT '[]',
                data_source        TEXT NOT NULL DEFAULT 'user_published',
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL,
                withdrawn_at       TEXT,
                UNIQUE (tenant_id, slug)
            );
            CREATE INDEX IF NOT EXISTS idx_eco_pub_tenant
                ON ecosystem_published_projects(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_eco_pub_live
                ON ecosystem_published_projects(withdrawn_at);

            -- One row per (target project, enriching tenant). A second tenant
            -- enriching the same target ADDS a row; it never replaces one.
            CREATE TABLE IF NOT EXISTS ecosystem_enrichments (
                enrichment_id  TEXT PRIMARY KEY,
                target_eco_id  TEXT NOT NULL,
                tenant_id      TEXT NOT NULL,
                published_by   TEXT NOT NULL,
                payload        TEXT NOT NULL,
                visible_fields TEXT NOT NULL DEFAULT '[]',
                match_rule     TEXT,
                match_reason   TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                withdrawn_at   TEXT,
                UNIQUE (target_eco_id, tenant_id)
            );
            CREATE INDEX IF NOT EXISTS idx_eco_enr_target
                ON ecosystem_enrichments(target_eco_id);
        """)
        # Additive migration for stores created before the phase/status split.
        # Existing rows keep their legacy status and read through
        # normalise_lifecycle(); they are not rewritten, because guessing the
        # phase a row never recorded is exactly what the split prevents.
        cols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(ecosystem_published_projects)")}
        if "phase" not in cols:
            conn.execute("ALTER TABLE ecosystem_published_projects "
                         "ADD COLUMN phase TEXT NOT NULL DEFAULT 'unknown'")
        conn.commit()
    finally:
        conn.close()


# ── writes ──────────────────────────────────────────────────────────────────

def publish_project(*, tenant_id: str, user_id: str, slug: str, name: str,
                    lat: Optional[float], lng: Optional[float],
                    status: str, phase: str = "unknown",
                    country: Optional[str] = None,
                    molecule_type: Optional[str] = None,
                    production_pathway: Optional[str] = None,
                    owner_name: Optional[str] = None,
                    capacity_label: Optional[str] = None,
                    capacity_value: Optional[str] = None,
                    capacity_unit: Optional[str] = None,
                    extras: Optional[dict[str, Any]] = None,
                    visible_fields: Optional[list[str]] = None,
                    layer: str = "production") -> dict[str, Any]:
    """Publish (or re-publish) one tenant-owned marker. Idempotent per (tenant, slug).

    A caller still sending a single legacy status ("planned", "operational" …)
    is normalised rather than refused: older clients are in the field.
    """
    if lat is None or lng is None:
        raise ValueError("coordinates are required to place a marker")
    phase, status = normalise_lifecycle(phase, status)
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT eco_project_id, created_at FROM ecosystem_published_projects "
            "WHERE tenant_id = ? AND slug = ?", (tenant_id, slug)).fetchone()
        eco_id = row["eco_project_id"] if row else f"pub_{uuid.uuid4().hex[:12]}"
        created = row["created_at"] if row else _now()
        conn.execute(
            "INSERT INTO ecosystem_published_projects ("
            " eco_project_id, tenant_id, published_by, slug, name, lat, lng, country,"
            " molecule_type, production_pathway, phase, status, layer, owner_name,"
            " capacity_label, capacity_value, capacity_unit, extras, visible_fields,"
            " data_source, created_at, updated_at, withdrawn_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)"
            " ON CONFLICT(eco_project_id) DO UPDATE SET"
            "  published_by=excluded.published_by, name=excluded.name,"
            "  lat=excluded.lat, lng=excluded.lng, country=excluded.country,"
            "  molecule_type=excluded.molecule_type,"
            "  production_pathway=excluded.production_pathway,"
            "  phase=excluded.phase, status=excluded.status,"
            "  owner_name=excluded.owner_name,"
            "  capacity_label=excluded.capacity_label,"
            "  capacity_value=excluded.capacity_value,"
            "  capacity_unit=excluded.capacity_unit, extras=excluded.extras,"
            "  visible_fields=excluded.visible_fields, updated_at=excluded.updated_at,"
            "  withdrawn_at=NULL",
            (eco_id, tenant_id, user_id, slug, name, lat, lng, country,
             molecule_type, production_pathway, phase, status, layer, owner_name,
             capacity_label, capacity_value, capacity_unit,
             json.dumps(extras or {}), json.dumps(visible_fields or []),
             USER_PUBLISHED, created, _now()))
        conn.commit()
        return get_published(eco_id) or {}
    finally:
        conn.close()


def attach_enrichment(*, tenant_id: str, user_id: str, target_eco_id: str,
                      payload: dict[str, Any],
                      visible_fields: Optional[list[str]] = None,
                      match_rule: Optional[str] = None,
                      match_reason: Optional[str] = None) -> dict[str, Any]:
    """Attach this tenant's reading of an existing map project.

    ATTACH, NOT OVERWRITE — the row is keyed by (target, tenant), so another
    tenant's enrichment of the same target is a separate row and survives.
    """
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT enrichment_id, created_at FROM ecosystem_enrichments "
            "WHERE target_eco_id = ? AND tenant_id = ?",
            (target_eco_id, tenant_id)).fetchone()
        enr_id = row["enrichment_id"] if row else f"enr_{uuid.uuid4().hex[:12]}"
        created = row["created_at"] if row else _now()
        conn.execute(
            "INSERT INTO ecosystem_enrichments ("
            " enrichment_id, target_eco_id, tenant_id, published_by, payload,"
            " visible_fields, match_rule, match_reason, created_at, updated_at,"
            " withdrawn_at) VALUES (?,?,?,?,?,?,?,?,?,?,NULL)"
            " ON CONFLICT(enrichment_id) DO UPDATE SET"
            "  published_by=excluded.published_by, payload=excluded.payload,"
            "  visible_fields=excluded.visible_fields,"
            "  match_rule=excluded.match_rule, match_reason=excluded.match_reason,"
            "  updated_at=excluded.updated_at, withdrawn_at=NULL",
            (enr_id, target_eco_id, tenant_id, user_id, json.dumps(payload),
             json.dumps(visible_fields or []), match_rule, match_reason,
             created, _now()))
        conn.commit()
        return {"enrichment_id": enr_id, "target_eco_id": target_eco_id,
                "tenant_id": tenant_id}
    finally:
        conn.close()


def withdraw_project(*, tenant_id: str, slug: str) -> bool:
    """Soft-delete. The row stays; the marker stops being served."""
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE ecosystem_published_projects SET withdrawn_at = ?, updated_at = ? "
            "WHERE tenant_id = ? AND slug = ? AND withdrawn_at IS NULL",
            (_now(), _now(), tenant_id, slug))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def withdraw_enrichment(*, tenant_id: str, target_eco_id: str) -> bool:
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE ecosystem_enrichments SET withdrawn_at = ?, updated_at = ? "
            "WHERE tenant_id = ? AND target_eco_id = ? AND withdrawn_at IS NULL",
            (_now(), _now(), tenant_id, target_eco_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── reads ───────────────────────────────────────────────────────────────────

def _row_to_eco(row: sqlite3.Row) -> dict[str, Any]:
    extras = json.loads(row["extras"] or "{}")
    keys = row.keys()
    # Rows written before the split have no phase column value to trust, so the
    # pair is resolved on read as well as on write.
    phase, status = normalise_lifecycle(
        row["phase"] if "phase" in keys else None, row["status"])
    return {
        "id": row["eco_project_id"],
        "name": row["name"],
        "lat": row["lat"], "lng": row["lng"],
        "phase": phase, "status": status, "layer": row["layer"],
        "country": row["country"],
        "moleculeType": row["molecule_type"],
        "productionPathway": row["production_pathway"],
        "capacity": row["capacity_label"],
        "capacityValue": row["capacity_value"],
        "capacityUnit": row["capacity_unit"],
        "owner": row["owner_name"],
        "dataSource": row["data_source"],
        "_tenantId": row["tenant_id"],
        "_visibleFields": json.loads(row["visible_fields"] or "[]"),
        "_updatedAt": row["updated_at"],
        **{k: v for k, v in extras.items()},
    }


def get_published(eco_project_id: str) -> Optional[dict[str, Any]]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM ecosystem_published_projects WHERE eco_project_id = ?",
            (eco_project_id,)).fetchone()
        return _row_to_eco(row) if row else None
    finally:
        conn.close()


def list_published() -> list[dict[str, Any]]:
    """Every live marker, unredacted. Callers MUST pass these through
    `redact_for_viewer` before returning them to anyone."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM ecosystem_published_projects WHERE withdrawn_at IS NULL "
            "ORDER BY updated_at DESC").fetchall()
        return [_row_to_eco(r) for r in rows]
    finally:
        conn.close()


def list_enrichments(target_eco_id: Optional[str] = None) -> list[dict[str, Any]]:
    """All live enrichments. More than one per target is normal and expected —
    that is what 'attach, never overwrite' produces."""
    conn = _conn()
    try:
        sql = ("SELECT * FROM ecosystem_enrichments WHERE withdrawn_at IS NULL")
        args: tuple = ()
        if target_eco_id:
            sql += " AND target_eco_id = ?"
            args = (target_eco_id,)
        rows = conn.execute(sql + " ORDER BY updated_at DESC", args).fetchall()
        return [{
            "enrichment_id": r["enrichment_id"],
            "target_eco_id": r["target_eco_id"],
            "tenant_id": r["tenant_id"],
            "payload": json.loads(r["payload"] or "{}"),
            "visible_fields": json.loads(r["visible_fields"] or "[]"),
            "match_rule": r["match_rule"],
            "match_reason": r["match_reason"],
            "updated_at": r["updated_at"],
        } for r in rows]
    finally:
        conn.close()


def redact_for_viewer(record: dict[str, Any], viewer_tenant: Optional[str]
                      ) -> dict[str, Any]:
    """Apply the publisher's own confidentiality choice.

    The publisher sees their record whole. EVERY other viewer — including a
    platform admin — sees the core marker fields plus only those extras the
    publisher listed in `visible_fields`. Admin does not bypass this, because it
    is the publisher's confidentiality and not a viewer preference.
    """
    owner_tenant = record.get("_tenantId")
    out = {k: v for k, v in record.items() if not k.startswith("_")}
    out["owned"] = bool(viewer_tenant) and viewer_tenant == owner_tenant
    if out["owned"]:
        return out
    allowed = set(record.get("_visibleFields") or [])
    for field in GATED_FIELDS:
        if field not in allowed:
            out.pop(field, None)
    return out
