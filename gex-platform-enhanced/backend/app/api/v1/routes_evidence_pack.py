"""
Lender evidence pack — GET /api/v1/evidence-pack/contract/{contract_id}
=======================================================================
GreenMesh Phase 1, Step 5. Assembled by `app/core/evidence_pack.py` from the records, with a
SHA-256 manifest; every item labelled VERIFIED, DECLARED or MISSING. A caller who may not read
the contract (tb_contract's RLS: owner, parties, linked) gets 404, never a partial pack.
PostgreSQL only.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db_backend import domain_connection, domain_is_postgres, require_postgres

router = APIRouter(prefix="/api/v1/evidence-pack", tags=["evidence-pack"])


def get_db():
    require_postgres(domain_is_postgres(), "Evidence pack", "DOMAIN_DB_BACKEND")
    conn = domain_connection()
    try:
        yield conn
    finally:
        conn.close()


@router.get("/contract/{contract_id}")
def contract_pack(contract_id: str, db: Any = Depends(get_db)):
    from app.core.evidence_pack import build

    pack = build(db, contract_id)
    if pack is None:
        raise HTTPException(404, f"Contract {contract_id} not found")
    return pack



def _party(request: Request):
    from app.core import market_engine as me

    try:
        return me.Party.from_payload(getattr(request.state, "user_payload", None) or {})
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


@router.post("/contract/{contract_id}/export", status_code=201)
def export_submission(contract_id: str, request: Request, connector: str = "gex_export_v1",
                      db: Any = Depends(get_db)):
    """Phase 2 Step 6 (D6, export only): the seller exports a submission file built from VERIFIED
    items only; refused, naming each item, unless every required item is VERIFIED and PASS.
    Written to the append-only registry outbox; nothing is sent."""
    from app.core import market_engine as me
    from app.core import registry_connectors as rc

    try:
        return rc.export(_party(request), contract_id, connector, conn=db)
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


@router.get("/contract/{contract_id}/exports")
def list_exports(contract_id: str, request: Request):
    from app.core import registry_connectors as rc

    return {"exports": rc.outbox(_party(request), contract_id)}
