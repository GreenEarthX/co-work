"""
External Adjacency Corpus — the license-clean, EMPTY seeding machine for the
Hidalgo product space (review item #5).

Built without data on purpose: fabricating a seed would be worse than N=1.
Ingestion is a drop-in once the attribution line is legally signed
(IEA Hydrogen Production & Infrastructure Projects DB is CC BY 4.0 — verified
2026-07-02; supplementary sources pending legal review).

Design (two-layer adjacency):
  Layer A — ATTRIBUTE proximity (this module): fuel × technology × jurisdiction
            × pathway_class, computable from public project databases.
  Layer B — EVIDENCE-PROFILE proximity (platform-native, adjacency.py §3.5):
            unlocks at N≥5 GEX projects. External projects can never have GEX
            evidence profiles — this module does not pretend otherwise.

EPISTEMIC POLICY (ruled): everything this module emits is an EXTERNAL_PRIOR —
benchmark/nudge context only. It must NEVER enter gate evaluation or a
bankability score. A leak-guard test enforces the import boundary.

Corpus discipline mirrors the ledger's: every snapshot is hash-anchored with
license + attribution + retrieval date; unmappable taxonomy labels QUARANTINE
(census-then-sign, never guess); version-over-version STATUS TRANSITIONS are
first-class — revealed outcomes are the Hidalgo-method analog, the diffs ARE
the dataset.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings

DB_PATH = settings.SQLITE_DB_PATH

EXTERNAL_PRIOR = "EXTERNAL_PRIOR"          # provenance label on every output
GEX_STATUSES = ["concept", "feasibility", "fid", "construction",
                "operational", "decommissioned", "cancelled", "deferred"]

# Attribute-proximity weights — documented HEURISTIC, tunable, not calibrated.
_W = {"fuel_id": 0.40, "technology_class": 0.25, "jurisdiction": 0.20,
      "pathway_class": 0.15}
_NEIGHBOR_THRESHOLD = 0.65
_TOP_K = 10


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS corpus_versions (
            version_id       TEXT PRIMARY KEY,
            source           TEXT NOT NULL,
            source_version   TEXT NOT NULL,
            license          TEXT NOT NULL,
            attribution      TEXT NOT NULL,
            retrieved_at     TEXT NOT NULL,
            imported_at      TEXT NOT NULL,
            imported_by      TEXT NOT NULL,
            snapshot_hash    TEXT NOT NULL,
            row_count        INTEGER NOT NULL,
            quarantined      INTEGER NOT NULL DEFAULT 0,
            UNIQUE (source, source_version)
        );
        CREATE TABLE IF NOT EXISTS external_projects (
            row_id            TEXT PRIMARY KEY,
            version_id        TEXT NOT NULL,
            source            TEXT NOT NULL,
            source_project_id TEXT NOT NULL,
            name              TEXT,
            fuel_id           TEXT,
            pathway_class     TEXT,
            technology_class  TEXT,
            jurisdiction      TEXT,
            capacity_value    REAL,
            capacity_unit     TEXT,
            status            TEXT,
            announced_year    INTEGER,
            fid_year          INTEGER,
            cod_year          INTEGER,
            quarantined       INTEGER NOT NULL DEFAULT 0,
            quarantine_reason TEXT,
            raw               TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ep_version ON external_projects(version_id);
        CREATE INDEX IF NOT EXISTS idx_ep_fuel ON external_projects(fuel_id);
        CREATE TABLE IF NOT EXISTS corpus_taxonomy_map (
            source     TEXT NOT NULL,
            field      TEXT NOT NULL,          -- fuel_id | technology_class | status | pathway_class
            raw_label  TEXT NOT NULL,
            gex_value  TEXT,                   -- NULL = quarantined pending human sign-off
            mapped_by  TEXT,
            mapped_at  TEXT,
            PRIMARY KEY (source, field, raw_label)
        );
        CREATE TABLE IF NOT EXISTS corpus_status_transitions (
            transition_id     TEXT PRIMARY KEY,
            source            TEXT NOT NULL,
            source_project_id TEXT NOT NULL,
            from_version      TEXT NOT NULL,
            to_version        TEXT NOT NULL,
            from_status       TEXT,
            to_status         TEXT,
            fuel_id           TEXT,
            jurisdiction      TEXT,
            observed_at       TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_label(conn, source: str, field: str, raw: Optional[str]) -> tuple[Optional[str], bool]:
    """Resolve a raw label via the signed taxonomy map. Unknown → (None, True)
    i.e. quarantined — census-then-sign, never guess."""
    if raw is None:
        return None, True
    row = conn.execute(
        "SELECT gex_value FROM corpus_taxonomy_map WHERE source=? AND field=? AND raw_label=?",
        (source, field, raw)).fetchone()
    if row is None:
        conn.execute(   # record the unseen label so the census sees it
            "INSERT OR IGNORE INTO corpus_taxonomy_map (source, field, raw_label) VALUES (?,?,?)",
            (source, field, raw))
        return None, True
    return (row["gex_value"], row["gex_value"] is None)


def sign_mapping(source: str, field: str, raw_label: str, gex_value: str,
                 mapped_by: str) -> None:
    """Human sign-off of one observed label → GEX vocabulary."""
    conn = get_db()
    conn.execute(
        "INSERT INTO corpus_taxonomy_map (source, field, raw_label, gex_value, mapped_by, mapped_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(source, field, raw_label) DO UPDATE SET "
        "gex_value=excluded.gex_value, mapped_by=excluded.mapped_by, mapped_at=excluded.mapped_at",
        (source, field, raw_label, gex_value, mapped_by, _now()))
    conn.commit()
    conn.close()


def import_snapshot(*, source: str, source_version: str, license: str,
                    attribution: str, retrieved_at: str, imported_by: str,
                    rows: list[dict]) -> dict:
    """Import one hash-anchored corpus snapshot. Rows with unmapped taxonomy
    labels are QUARANTINED (imported but excluded from proximity/base-rates).
    Diffs vs the previous version of the same source become status transitions."""
    snapshot_hash = "sha256:" + hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:24]
    conn = get_db()
    try:
        version_id = f"cv_{uuid.uuid4().hex[:10]}"
        prev = conn.execute(
            "SELECT version_id FROM corpus_versions WHERE source=? "
            "ORDER BY imported_at DESC LIMIT 1", (source,)).fetchone()
        quarantined = 0
        for r in rows:
            fuel, q1 = _map_label(conn, source, "fuel_id", r.get("fuel"))
            tech, q2 = _map_label(conn, source, "technology_class", r.get("technology"))
            status, q3 = _map_label(conn, source, "status", r.get("status"))
            pclass, q4 = _map_label(conn, source, "pathway_class", r.get("pathway_class") or r.get("fuel"))
            is_q = q1 or q2 or q3 or q4
            reason = None
            if is_q:
                missing = [n for n, q in
                           (("fuel", q1), ("technology", q2), ("status", q3), ("pathway_class", q4)) if q]
                reason = f"unmapped taxonomy labels: {missing}"
                quarantined += 1
            conn.execute(
                "INSERT INTO external_projects (row_id, version_id, source, source_project_id, "
                "name, fuel_id, pathway_class, technology_class, jurisdiction, capacity_value, "
                "capacity_unit, status, announced_year, fid_year, cod_year, quarantined, "
                "quarantine_reason, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"ep_{uuid.uuid4().hex[:10]}", version_id, source,
                 str(r.get("source_project_id")), r.get("name"), fuel, pclass, tech,
                 r.get("jurisdiction"), r.get("capacity_value"), r.get("capacity_unit"),
                 status, r.get("announced_year"), r.get("fid_year"), r.get("cod_year"),
                 int(is_q), reason, json.dumps(r, default=str)))
        # revealed outcomes: status transitions vs previous snapshot
        transitions = 0
        if prev:
            prev_status = {row["source_project_id"]: row["status"] for row in conn.execute(
                "SELECT source_project_id, status FROM external_projects "
                "WHERE version_id=? AND quarantined=0", (prev["version_id"],))}
            for r in conn.execute(
                    "SELECT source_project_id, status, fuel_id, jurisdiction FROM external_projects "
                    "WHERE version_id=? AND quarantined=0", (version_id,)).fetchall():
                old = prev_status.get(r["source_project_id"])
                if old is not None and old != r["status"]:
                    conn.execute(
                        "INSERT INTO corpus_status_transitions VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (f"tr_{uuid.uuid4().hex[:10]}", source, r["source_project_id"],
                         prev["version_id"], version_id, old, r["status"],
                         r["fuel_id"], r["jurisdiction"], _now()))
                    transitions += 1
        conn.execute(
            "INSERT INTO corpus_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (version_id, source, source_version, license, attribution, retrieved_at,
             _now(), imported_by, snapshot_hash, len(rows), quarantined))
        conn.commit()
    finally:
        conn.close()
    return {"version_id": version_id, "snapshot_hash": snapshot_hash,
            "rows": len(rows), "quarantined": quarantined,
            "status_transitions_observed": transitions,
            "provenance": EXTERNAL_PRIOR}


def _latest_rows(conn) -> list[sqlite3.Row]:
    """Non-quarantined rows of the latest version per source."""
    return conn.execute("""
        SELECT ep.* FROM external_projects ep
        JOIN (SELECT source, version_id FROM corpus_versions cv
              WHERE imported_at = (SELECT MAX(imported_at) FROM corpus_versions
                                   WHERE source = cv.source)) latest
          ON ep.version_id = latest.version_id
        WHERE ep.quarantined = 0
    """).fetchall()


def attribute_proximity(a: dict, b: dict) -> float:
    """Layer-A proximity over the four §3.5 attribute axes (heuristic weights)."""
    s = 0.0
    for k, w in _W.items():
        av, bv = a.get(k), b.get(k)
        if av and bv and str(av).upper() == str(bv).upper():
            s += w
    return round(s, 4)


def density(target: dict, platform_projects: Optional[list[dict]] = None) -> dict:
    """Seeded density for a target attribute profile: mean of top-K proximities
    over corpus ∪ platform, with the provenance split ALWAYS reported."""
    conn = get_db()
    try:
        pool = [({"fuel_id": r["fuel_id"], "pathway_class": r["pathway_class"],
                  "technology_class": r["technology_class"],
                  "jurisdiction": r["jurisdiction"]}, "external", r["name"])
                for r in _latest_rows(conn)]
    finally:
        conn.close()
    for p in (platform_projects or []):
        pool.append((p, "platform", p.get("name", "platform-project")))
    if not pool:
        return {"density": None, "n_pool": 0, "neighbors": 0,
                "provenance": EXTERNAL_PRIOR,
                "note": "corpus empty and no platform cohort — density is PENDING, not fabricated"}
    scored = sorted(((attribute_proximity(target, attrs), origin, name)
                     for attrs, origin, name in pool), reverse=True)
    top = scored[:_TOP_K]
    ext = sum(1 for _, o, _n in top if o == "external")
    return {
        "density": round(sum(s for s, _o, _n in top) / len(top), 4),
        "n_pool": len(pool),
        "neighbors": sum(1 for s, _o, _n in scored if s >= _NEIGHBOR_THRESHOLD),
        "top_matches": [{"proximity": s, "origin": o, "name": n} for s, o, n in top[:5]],
        "provenance_split": {"external": round(ext / len(top), 2),
                             "platform": round(1 - ext / len(top), 2)},
        "layer": "A (attribute) — Layer B (evidence-profile) unlocks at N≥5 platform projects",
        "basis": "heuristic attribute proximity; weights uncalibrated",
        "provenance": EXTERNAL_PRIOR,
    }


def base_rates(fuel_id: Optional[str] = None,
               jurisdiction: Optional[str] = None) -> dict:
    """Observed status distribution + revealed transitions for a cohort slice.
    Reports COUNTS and observed shares only — no invented percentiles, and
    explicitly NO DSCR (not observable in any external corpus)."""
    conn = get_db()
    try:
        q = "SELECT status, COUNT(*) n FROM external_projects WHERE quarantined=0"
        args: list[Any] = []
        if fuel_id:
            q += " AND fuel_id=?"; args.append(fuel_id.upper())
        if jurisdiction:
            q += " AND jurisdiction=?"; args.append(jurisdiction.upper())
        counts = {r["status"]: r["n"] for r in conn.execute(q + " GROUP BY status", tuple(args))}
        tq = "SELECT from_status, to_status, COUNT(*) n FROM corpus_status_transitions WHERE 1=1"
        targs: list[Any] = []
        if fuel_id:
            tq += " AND fuel_id=?"; targs.append(fuel_id.upper())
        transitions = [dict(r) for r in conn.execute(
            tq + " GROUP BY from_status, to_status", tuple(targs))]
        versions = conn.execute(
            "SELECT source, source_version, license, attribution, snapshot_hash "
            "FROM corpus_versions").fetchall()
    finally:
        conn.close()
    n = sum(counts.values())
    return {
        "cohort": {"fuel_id": fuel_id, "jurisdiction": jurisdiction},
        "n": n,
        "status_counts": counts,
        "share_operational": round(counts.get("operational", 0) / n, 3) if n else None,
        "share_cancelled_or_deferred": round(
            (counts.get("cancelled", 0) + counts.get("deferred", 0)) / n, 3) if n else None,
        "revealed_transitions": transitions,
        "dscr": None,   # NOT observable externally — never fabricated
        "sources": [dict(v) for v in versions],
        "provenance": EXTERNAL_PRIOR,
        "note": "counts and revealed outcomes only; priors, not platform evidence",
    }


def corpus_summary() -> dict:
    conn = get_db()
    try:
        versions = [dict(r) for r in conn.execute(
            "SELECT source, source_version, license, retrieved_at, snapshot_hash, "
            "row_count, quarantined FROM corpus_versions ORDER BY imported_at")]
        unmapped = [dict(r) for r in conn.execute(
            "SELECT source, field, raw_label FROM corpus_taxonomy_map WHERE gex_value IS NULL")]
    finally:
        conn.close()
    return {"versions": versions, "unmapped_labels_awaiting_signoff": unmapped,
            "empty": not versions, "provenance": EXTERNAL_PRIOR}
