"""
Registry and scheme connectors (GreenMesh Phase 2 Step 6; D5, D6; alembic 111).

ONE interface for every connector, so a new scheme, registry or GO hub is an added module,
not a redesign (D5):

    class Connector:
        name: str
        def build(pack: dict) -> dict      # the submission payload, from VERIFIED items only

`export(party, contract_id, connector)`:
  1. builds the contract's evidence pack as the caller (RLS decides what it may read);
  2. REFUSES unless every required item is VERIFIED and PASS — the refusal names each one;
  3. builds the payload with the connector, from VERIFIED items only;
  4. writes it to a file under REGISTRY_EXPORT_DIR and to the append-only `registry_outbox`
     with its SHA-256 — and sends NOTHING (REGISTRY_CONNECTOR_BACKEND = "none", the only value).

D6: GEX does not submit for a client; the party or its certifier does. The research behind
this (docs/GREENMESH_CONNECTORS_RESEARCH.md, 13 Nov 2026) found no public field-level spec
for CertifHy, ISCC, the UDB or the AIB hub, so the only connector is `gex_export_v1`, GEX's
own format. A scheme module is added when its interface document is in hand.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core import market_engine as me
from app.core.market_engine import Party, _refuse

from .gex_export import GexExportV1

CONNECTORS = {GexExportV1.name: GexExportV1()}


def required_failures(pack: dict) -> list[str]:
    """Every item that stops an export: compliance and delivery quality not VERIFIED and PASS,
    and no compliance at all."""
    out = []
    comp = pack["sections"]["compliance"]["items"]
    if not comp:
        out.append("compliance: no custody period behind the contract")
    for i in comp:
        if i["label"] != "VERIFIED" or i.get("result") == "FAIL":
            out.append(f"compliance.{i['item']}: {i['label']}{' ' + i['result'] if i.get('result') else ''}")
    for i in pack["sections"].get("deliveries", {}).get("items", []):
        if i["item"] == "quality" and not (i["label"] == "VERIFIED" and i.get("result") == "PASS"):
            out.append(f"delivery {i['delivery_id']}.quality: {i['label']}"
                       f"{' ' + i['result'] if i.get('result') else ''}")
    return out


def export(party: Party, contract_id: str, connector: str = GexExportV1.name, *, conn=None) -> dict:
    """Build, gate and export one submission file. `conn` is the caller's RLS connection."""
    from app.core.config import settings
    from app.core.evidence_pack import build
    from app.trading_book import record

    me._trader(party)
    if settings.REGISTRY_CONNECTOR_BACKEND != "none":       # config refuses any other value; belt and braces
        _refuse(503, "REGISTRY_BACKEND", "Only export (none) is allowed.")
    impl = CONNECTORS.get(connector)
    if impl is None:
        _refuse(422, "REGISTRY_CONNECTOR_UNKNOWN", f"Connectors: {', '.join(sorted(CONNECTORS))}.")
    op = me._conn()
    try:
        who = record.parties(op, contract_id)
        if party.company_id not in who["companies"]:
            _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
        if party.company_id != who["seller"]:
            _refuse(403, "REGISTRY_EXPORT_BY_SELLER", "The producer (the seller) exports its submission file.")
    finally:
        op.close()
    pack = build(conn, contract_id) if conn is not None else None
    if pack is None:
        _refuse(404, "CONTRACT_NOT_FOUND", "No contract of yours with that id.")
    missing = required_failures(pack)
    if missing:
        _refuse(409, "REGISTRY_EXPORT_NOT_VERIFIED",
                "Not every required item is VERIFIED and PASS: " + "; ".join(missing))
    payload = impl.build(pack)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    dest = Path(settings.REGISTRY_EXPORT_DIR) / contract_id
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{connector}_{sha}.json"
    path.write_bytes(body)
    op = me._conn()
    try:
        op.execute("INSERT INTO registry_outbox (contract_id, connector, backend, status, payload, payload_sha256, "
                   "pack_sha256, exported_path, created_by, company_id) VALUES (?, ?, 'none', 'EXPORTED', "
                   "CAST(? AS jsonb), ?, ?, ?, ?, ?)",
                   (contract_id, connector, body.decode("utf-8"), sha, pack["manifest"]["pack_sha256"], str(path),
                    party.user_id, party.company_id))
        op.commit()
    finally:
        op.close()
    return {"connector": connector, "backend": "none", "sent": False, "payload_sha256": sha,
            "pack_sha256": pack["manifest"]["pack_sha256"], "exported_path": str(path),
            "note": "exported for the party or its certifier to submit; GEX sent nothing (D6)", "payload": payload}


def outbox(party: Party, contract_id: str) -> list[dict]:
    """This contract's exports, as the caller may read them (111's RLS)."""
    from app.core.db_backend import PLATFORM_ADMIN, market_connection

    conn = market_connection(company_id=PLATFORM_ADMIN if party.is_admin else party.company_id)
    try:
        rows = conn.execute("SELECT id, connector, backend, status, payload_sha256, pack_sha256, created_by, "
                            "company_id, created_at FROM registry_outbox WHERE contract_id = ? ORDER BY id",
                            (contract_id,)).fetchall()
        return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()} for r in rows]
    finally:
        conn.close()


__all__ = ["CONNECTORS", "export", "outbox", "required_failures"]
