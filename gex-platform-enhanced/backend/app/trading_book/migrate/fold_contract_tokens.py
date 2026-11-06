"""
Phase 2 — fold the contract tokens (alembic 078) into the one contract record.

Each project_contract (one per project and kind) becomes ONE tb_contract
(origin_ref 'project:<project_id>:<kind>', the project's owner as
owner_company_id, the registered counterparty as confirming_company_id). Each
VERSION event becomes a contract version whose terms are `card` terms holding
the version's exact {card.field: value} (Phase 0 Q3), frozen at the time the
version was recorded, with the 078 terms_sha256 kept as legacy_terms_sha256 —
the hash the counterparty names when it confirms. Every event is copied
VERBATIM — seq, type, actor, company, note, timestamp, prev_hash, event_hash —
under hash scheme '078' with its 078 contract id, so every chain still verifies
with the hashes it was written with; the next event appended continues the
same chain under scheme '2'. Each copied chain is re-verified before the fold
commits, and so is each terms hash against its terms (gap 2 of Phase 0 §4).

Idempotent: a contract already folded (its origin_ref exists) is skipped.
Used by alembic 085 on the migration connection, and by the tests on data they
prepare.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

from app.trading_book import record
from app.trading_book.terms import TermsIn


class SAConnection:
    """The record's `?`-placeholder connection interface over a SQLAlchemy Connection."""

    def __init__(self, conn):
        self._c = conn

    def execute(self, sql: str, params=()):
        return self._c.exec_driver_sql(sql.replace("?", "%s"), tuple(params)).mappings()


def origin(project_id: str, kind: str) -> str:
    return f"project:{project_id}:{kind}"


def _legacy_sha(terms: dict) -> str:
    return hashlib.sha256(json.dumps(terms, sort_keys=True, default=str).encode()).hexdigest()


def fold(conn) -> dict:
    """Fold every 078 contract not yet folded. `conn` uses `?` placeholders."""
    done, skipped = [], []
    for pc in record._rows(conn, "SELECT pc.*, p.owner_tenant_id FROM project_contract pc "
                                 "JOIN projects p ON p.project_id = pc.project_id ORDER BY pc.id"):
        ref = origin(pc["project_id"], pc["kind"])
        if record.by_origin(conn, ref):
            skipped.append(ref)
            continue
        evs = record._rows(conn, "SELECT * FROM project_contract_event WHERE contract_id = ? ORDER BY seq", (pc["id"],))
        contract_id = str(uuid.uuid4())
        conn.execute("INSERT INTO tb_contract (id, contract_type, contract_ref, kind, project_id, origin_ref, "
                     "owner_company_id, confirming_company_id, verification_state, token_ref, created_at, updated_at) "
                     "VALUES (?, 'terms', ?, ?, ?, ?, ?, ?, 'UNVERIFIED', ?, ?, now())",
                     (contract_id, record._next_ref(conn), pc["kind"], pc["project_id"], ref, pc["owner_tenant_id"],
                      pc["counterparty_company_id"], evs[0]["event_hash"] if evs else None, pc["created_at"]))
        versions: dict[str, str] = {}               # legacy sha -> version id (the latest with that sha)
        version_rows = [e for e in evs if e["event_type"] == "VERSION"]
        for n, e in enumerate(version_rows, start=1):
            terms = e["terms_json"] if isinstance(e["terms_json"], dict) else json.loads(e["terms_json"])
            if _legacy_sha(terms) != e["terms_sha256"]:
                raise RuntimeError(f"078 contract {pc['id']} seq {e['seq']}: terms_json does not match terms_sha256")
            w = record.write_terms(conn, TermsIn(profile="card", card_projection=terms), pc["owner_tenant_id"],
                                   frozen_at=e["at"])
            nxt = version_rows[n]["at"] if n < len(version_rows) else None
            vid = str(uuid.uuid4())
            conn.execute("INSERT INTO tb_contract_version (id, contract_id, version, terms_id, terms_hash, valid_from, "
                         "superseded_at, reason, legacy_terms_sha256, token_event_ref) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, 'migrated', ?, ?)",
                         (vid, contract_id, n, w["terms_id"], w["terms_hash"], e["at"], nxt, e["terms_sha256"],
                          e["event_hash"]))
            versions[e["terms_sha256"]] = vid
            e["_version_id"] = vid
        for e in evs:
            vid: Optional[str] = e.get("_version_id") or (versions.get(e["terms_sha256"])
                                                         if e["event_type"] == "CONFIRMED" else None)
            conn.execute("INSERT INTO tb_contract_event (contract_id, seq, event_type, version_id, terms_hash, actor, "
                         "company_id, note, at, prev_hash, event_hash, hash_scheme, legacy_contract_id) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '078', ?)",
                         (contract_id, e["seq"], e["event_type"], vid, e["terms_sha256"], e["actor"], e["company_id"],
                          e["note"], e["at"], e["prev_hash"], e["event_hash"], pc["id"]))
        if not record.chain_intact(conn, contract_id):
            raise RuntimeError(f"078 contract {pc['id']} ({ref}): its chain does not verify after the fold")
        for v in record._rows(conn, "SELECT terms_id FROM tb_contract_version WHERE contract_id = ?", (contract_id,)):
            if not record.stored_hashes_hold(conn, str(v["terms_id"])):
                raise RuntimeError(f"{ref}: a folded version's terms do not match their hash")
        done.append(ref)
    return {"folded": done, "already_folded": skipped}
