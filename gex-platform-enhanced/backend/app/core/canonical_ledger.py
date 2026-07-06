"""
CanonicalProjectLedger — persistent store (canonical-first cutover, per the
signed census + Migration Spec v0.3-rc2).

One store, three relations: canonical_ledger_entries (append-only, bitemporal,
hash-anchored), evidence_links (§6b), ledger_migration_map (§6). Claims/nodes
are NEVER stored — they are folded on read via efuel_truth_stack projectors.

SUBSTRATE RULE (Decision 4): Postgres via CANONICAL_DATABASE_URL. SQLite is
refused unless GEX_CANONICAL_DEV=1 — and then every read/write surface reports
substrate='sqlite-dev' so a dev ledger can never masquerade as canonical truth.

WRITE RULES enforced here (mirroring efuel_truth_stack.ledger.append):
  · id uniqueness (append-only)      · kind admits entry_type (model validator)
  · write authority (spec v0.3)      · to_state bounds (ToStateViolation)
  · supersedes must reference an existing row
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

# efuel_truth_stack is a sibling package of backend/
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT / "efuel_truth_stack") not in sys.path:
    sys.path.insert(0, str(_ROOT / "efuel_truth_stack"))

from efuel_truth_stack.enums import EntryType, KIND_OF_ENTRY_TYPE, LedgerKind  # noqa: E402
from efuel_truth_stack.ledger import (  # noqa: E402
    Ledger, ToStateViolation, WriteAuthorityError, ImmutabilityError,
    _TERMINAL_VALID_STATES, _DEMOTING_STATES,
)
from efuel_truth_stack.models import CanonicalLedgerEntry, EvidenceLink  # noqa: E402
from efuel_truth_stack.projectors import fold_claims  # noqa: E402
from efuel_truth_stack.spec import WRITE_AUTHORITY  # noqa: E402

CANONICAL_DATABASE_URL = os.getenv("CANONICAL_DATABASE_URL", "")
_DEV_WAIVER = os.getenv("GEX_CANONICAL_DEV", "0") == "1"
_SQLITE_PATH = os.getenv("GEX_CANONICAL_SQLITE_PATH",
                         str(_ROOT / "backend" / "canonical_ledger.db"))


class SubstrateError(RuntimeError):
    """Canonical truth may not accumulate on a non-ruled substrate."""


def substrate() -> str:
    if CANONICAL_DATABASE_URL.startswith(("postgres://", "postgresql://")):
        return "postgres"
    if _DEV_WAIVER:
        return "sqlite-dev"
    return "unconfigured"


def _connect():
    sub = substrate()
    if sub == "postgres":
        import psycopg2
        return psycopg2.connect(CANONICAL_DATABASE_URL), "postgres"
    if sub == "sqlite-dev":
        conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite-dev"
    raise SubstrateError(
        "Canonical ledger substrate unconfigured: set CANONICAL_DATABASE_URL "
        "(postgres://…) per Migration Decision 4, or GEX_CANONICAL_DEV=1 for an "
        "explicitly-flagged dev substrate.")


_DDL = [
    """CREATE TABLE IF NOT EXISTS canonical_ledger_entries (
        id                      TEXT PRIMARY KEY,
        project_id              TEXT NOT NULL,
        kind                    TEXT NOT NULL,
        entry_type              TEXT NOT NULL,
        produced_by             TEXT NOT NULL,
        verified_by             TEXT,
        valid_from              TEXT NOT NULL,
        valid_to                TEXT,
        recorded_at             TEXT NOT NULL,
        regulatory_cliff        TEXT,
        payload                 TEXT NOT NULL,
        hash                    TEXT NOT NULL,
        version                 INTEGER NOT NULL DEFAULT 1,
        supersedes              TEXT,
        reconciliation_group_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cle_project ON canonical_ledger_entries(project_id)",
    """CREATE TABLE IF NOT EXISTS evidence_links (
        link_id                TEXT PRIMARY KEY,
        claim_id               TEXT NOT NULL,
        ledger_entry_id        TEXT NOT NULL,
        link_type              TEXT NOT NULL,
        linked_at              TEXT NOT NULL,
        linked_by              TEXT NOT NULL,
        evidence_hash_at_link  TEXT NOT NULL,
        migration_run_id       TEXT,
        UNIQUE (claim_id, ledger_entry_id, link_type)
    )""",
    """CREATE TABLE IF NOT EXISTS ledger_migration_map (
        map_id               TEXT PRIMARY KEY,
        legacy_table         TEXT NOT NULL,
        legacy_record_id     TEXT NOT NULL,
        new_ledger_entry_id  TEXT,
        migration_version    TEXT NOT NULL,
        migration_run_id     TEXT NOT NULL,
        migration_timestamp  TEXT NOT NULL,
        migrated_by          TEXT NOT NULL,
        legacy_content_hash  TEXT NOT NULL,
        new_content_hash     TEXT,
        migration_status     TEXT NOT NULL,
        verification_status  TEXT NOT NULL DEFAULT 'pending',
        quarantine_reason    TEXT,
        UNIQUE (legacy_table, legacy_record_id, migration_version)
    )""",
]


def init_db() -> str:
    conn, sub = _connect()
    cur = conn.cursor()
    for ddl in _DDL:
        cur.execute(ddl)
    conn.commit()
    conn.close()
    return sub


def _q(conn, sql: str, args: tuple = ()):  # paramstyle bridge
    cur = conn.cursor()
    if not isinstance(conn, sqlite3.Connection):
        sql = sql.replace("?", "%s")
    cur.execute(sql, args)
    return cur


def append_entry(*, project_id: str, entry_type: str, produced_by: str,
                 payload: dict, valid_from: Optional[date] = None,
                 valid_to: Optional[date] = None,
                 supersedes: Optional[str] = None,
                 reconciliation_group_id: Optional[str] = None,
                 entry_id: Optional[str] = None) -> dict:
    """Append one canonical entry, enforcing all v0.3 write rules."""
    et = EntryType(entry_type)
    entry = CanonicalLedgerEntry(   # validates kind-admission + computes hash
        id=entry_id or f"le_{uuid.uuid4().hex[:12]}",
        project_id=project_id, kind=KIND_OF_ENTRY_TYPE[et], entry_type=et,
        produced_by=produced_by, valid_from=valid_from or date.today(),
        valid_to=valid_to, recorded_at=datetime.now(timezone.utc),
        payload=payload, supersedes=supersedes,
        reconciliation_group_id=reconciliation_group_id,
    )
    allowed = WRITE_AUTHORITY.get(et.value)
    if allowed is not None and produced_by not in allowed:
        raise WriteAuthorityError(
            f"actor '{produced_by}' may not append '{et.value}' "
            f"(allowed: {sorted(allowed)})")
    to_state = payload.get("to_state")
    if to_state in (_TERMINAL_VALID_STATES | _DEMOTING_STATES) \
            and entry.kind is not LedgerKind.DECISION:
        raise ToStateViolation(
            f"to_state='{to_state}' on {entry.kind.value} entry — terminal/"
            f"demoting states require decision-kind entries (spec v0.3 §5.4).")

    conn, sub = _connect()
    try:
        if _q(conn, "SELECT 1 FROM canonical_ledger_entries WHERE id=?",
              (entry.id,)).fetchone():
            raise ImmutabilityError(f"entry id '{entry.id}' exists — append-only")
        if supersedes and not _q(conn,
                "SELECT 1 FROM canonical_ledger_entries WHERE id=?",
                (supersedes,)).fetchone():
            raise ImmutabilityError(f"supersedes unknown row '{supersedes}'")
        _q(conn, "INSERT INTO canonical_ledger_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (entry.id, project_id, entry.kind.value, et.value, produced_by,
            entry.verified_by, str(entry.valid_from),
            str(entry.valid_to) if entry.valid_to else None,
            entry.recorded_at.isoformat(),
            str(entry.regulatory_cliff) if entry.regulatory_cliff else None,
            json.dumps(payload, default=str), entry.hash, entry.version,
            supersedes, reconciliation_group_id))
        conn.commit()
    finally:
        conn.close()
    return {"entry_id": entry.id, "hash": entry.hash, "kind": entry.kind.value,
            "entry_type": et.value, "substrate": sub}


def link_evidence(*, claim_id: str, ledger_entry_id: str, linked_by: str,
                  link_type: str = "supports",
                  migration_run_id: Optional[str] = None) -> dict:
    """Hash-pinned many-to-many link (spec §6b). Pins the entry's CURRENT hash."""
    conn, sub = _connect()
    try:
        row = _q(conn, "SELECT hash FROM canonical_ledger_entries WHERE id=?",
                 (ledger_entry_id,)).fetchone()
        if not row:
            raise ImmutabilityError(f"cannot link to unknown entry '{ledger_entry_id}'")
        entry_hash = row[0]
        link_id = f"lk_{uuid.uuid4().hex[:12]}"
        try:
            _q(conn, "INSERT INTO evidence_links VALUES (?,?,?,?,?,?,?,?)",
               (link_id, claim_id, ledger_entry_id, link_type,
                datetime.now(timezone.utc).isoformat(), linked_by,
                entry_hash, migration_run_id))
            conn.commit()
        except Exception:   # UNIQUE violation → idempotent
            conn.rollback()
            return {"link_id": None, "deduplicated": True, "substrate": sub}
    finally:
        conn.close()
    return {"link_id": link_id, "evidence_hash_at_link": entry_hash, "substrate": sub}


def fold_project(project_id: str) -> dict:
    """Rebuild entries → fold claims (with evidence_links). READ = projection."""
    conn, sub = _connect()
    try:
        rows = _q(conn, "SELECT * FROM canonical_ledger_entries WHERE project_id=? "
                        "ORDER BY recorded_at, id", (project_id,)).fetchall()
        cols = ["id", "project_id", "kind", "entry_type", "produced_by",
                "verified_by", "valid_from", "valid_to", "recorded_at",
                "regulatory_cliff", "payload", "hash", "version", "supersedes",
                "reconciliation_group_id"]
        lg = Ledger()
        for r in rows:
            d = dict(zip(cols, tuple(r)))
            lg.append(CanonicalLedgerEntry(
                id=d["id"], project_id=d["project_id"],
                kind=LedgerKind(d["kind"]), entry_type=EntryType(d["entry_type"]),
                produced_by=d["produced_by"], verified_by=d["verified_by"],
                valid_from=date.fromisoformat(d["valid_from"]),
                valid_to=date.fromisoformat(d["valid_to"]) if d["valid_to"] else None,
                recorded_at=datetime.fromisoformat(d["recorded_at"]),
                payload=json.loads(d["payload"]), hash=d["hash"],
                version=d["version"], supersedes=d["supersedes"],
                reconciliation_group_id=d["reconciliation_group_id"]))
        lrows = _q(conn, "SELECT claim_id, ledger_entry_id, evidence_hash_at_link, "
                         "link_type FROM evidence_links").fetchall()
        links = [EvidenceLink(claim_id=t[0], ledger_entry_id=t[1],
                              evidence_hash=t[2], link_type=t[3]) for t in lrows]
    finally:
        conn.close()
    claims = fold_claims(lg, evidence_links=links or None)
    return {
        "substrate": sub,
        "entry_count": len(rows),
        "claims": {cid: {"state": c.state.value, "claim_type": c.claim_type,
                         "subject_node": c.subject_node, "value": c.value,
                         "unit": c.unit, "superseded_by": c.superseded_by,
                         "evidence_count": len(c.evidence_refs)}
                   for cid, c in claims.items()},
    }
