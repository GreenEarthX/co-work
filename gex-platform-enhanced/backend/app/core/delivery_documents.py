"""
Documents on file for a delivery (GreenMesh Phase 2 Step 3; alembic 106).

A delivery fact that rests on a document (unloading under DPU now; the bill of lading, the
inspector's certificate, a waiver later) names it by sha256, and the document must be ON
FILE here first: the bytes stored, their hash computed by GEX, never taken from the caller.

Who files: a party to the delivery (seller or buyer) for the kinds it records. Who reads:
whoever may read the delivery (103's `app_company_sees_delivery`). Append-only: a document is
never changed or removed (106's trigger); filing the same bytes twice for the same delivery
and kind is idempotent.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core import market_engine as me
from app.core.market_engine import Party, _refuse
from app.trading_book import record

KINDS = ("UNLOADING_RECORD", "BILL_OF_LADING", "DELIVERY_ORDER", "INSPECTION_CERTIFICATE",
         "INSPECTOR_APPOINTMENT", "WAIVER", "DISPUTE_RESOLUTION")
# Who files which kind: the seller, the buyer, either party, or the AGREED inspector (107).
FILED_BY = {"UNLOADING_RECORD": "buyer", "BILL_OF_LADING": "seller", "DELIVERY_ORDER": "seller",
            "INSPECTOR_APPOINTMENT": "party", "WAIVER": "party", "INSPECTION_CERTIFICATE": "inspector",
            "DISPUTE_RESOLUTION": "party"}
MAX_BYTES = 25 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def docs_dir() -> Path:
    return Path(os.getenv("GEX_DELIVERY_DOCS_DIR", "data/delivery_docs"))


def file_document(party: Party, delivery_id: str, kind: str, filename: str, content: bytes) -> dict:
    me._trader(party)
    if kind not in FILED_BY:
        _refuse(422, "DELIVERY_DOCUMENT_KIND", f"Kinds a party files now: {', '.join(FILED_BY)}.")
    if not content:
        _refuse(422, "DELIVERY_DOCUMENT_EMPTY", "The document is empty.")
    if len(content) > MAX_BYTES:
        _refuse(413, "DELIVERY_DOCUMENT_TOO_LARGE", "Documents are limited to 25 MB.")
    conn = me._conn()
    try:
        d = record._row(conn, "SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
        roles = set()
        if d is not None:
            roles |= {"seller", "party"} if party.company_id == d["seller_company_id"] else set()
            roles |= {"buyer", "party"} if party.company_id == d["buyer_company_id"] else set()
            roles |= {"inspector"} if d.get("inspector_company_id") and party.company_id == d["inspector_company_id"] else set()
        if not roles:
            _refuse(404, "DELIVERY_NOT_FOUND", "No delivery of yours with that id.")
        if FILED_BY[kind] not in roles:
            _refuse(403, "DELIVERY_WRONG_PARTY", f"A {kind} is filed by the {FILED_BY[kind]}.")
        sha = hashlib.sha256(content).hexdigest()
        found = record._row(conn, "SELECT * FROM delivery_document WHERE delivery_id = ? AND kind = ? AND sha256 = ?",
                            (delivery_id, kind, sha))
        if found:
            return _view(found)
        dest = docs_dir() / delivery_id / kind
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{sha}_{Path(filename or 'document').name}"
        path.write_bytes(content)
        conn.execute("INSERT INTO delivery_document (delivery_id, kind, sha256, filename, size_bytes, stored_path, "
                     "uploaded_by, company_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (delivery_id, kind, sha, Path(filename or "document").name, len(content), str(path),
                      party.user_id, party.company_id))
        conn.commit()
        return _view(record._row(conn, "SELECT * FROM delivery_document WHERE delivery_id = ? AND kind = ? "
                                       "AND sha256 = ?", (delivery_id, kind, sha)))
    finally:
        conn.close()


def on_file(conn, delivery_id: str, kind: str, sha256: Optional[str]) -> dict:
    """The document of that kind and hash for the delivery, or a refusal naming what is missing."""
    if not sha256 or not SHA256.match(str(sha256)):
        _refuse(422, "DELIVERY_DOCUMENT_REQUIRED", f"Name the {kind} on file by its sha256.")
    doc = record._row(conn, "SELECT * FROM delivery_document WHERE delivery_id = ? AND kind = ? AND sha256 = ?",
                      (delivery_id, kind, sha256))
    if doc is None:
        _refuse(422, "DELIVERY_DOCUMENT_NOT_ON_FILE", f"No {kind} with that sha256 is on file for this delivery.")
    return doc


def _view(r: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.items() if k != "stored_path"}


def documents_for(conn, delivery_id: str) -> list[dict]:
    return [_view(r) for r in record._rows(conn, "SELECT * FROM delivery_document WHERE delivery_id = ? "
                                                 "ORDER BY id", (delivery_id,))]
