"""
Trader RFQ management — /api/v1/trader/rfqs. A buyer's own RFQs.

Everything goes through the market engine (core/market_engine.py). Before
2026-10-23 this module always opened the SQLite file and wrote a `rfqs` table
that existed in neither store, so every call failed (gap register G-01; the
table is alembic 063). The buyer is the signed-in company; nothing in the body
names it. Other companies see an RFQ only as an anonymised listing
(GET /api/v1/market/listings/rfqs).

States: draft -> open | cancelled; open -> withdrawn | expired. 'matched' is set
by the market when both parties accept a match.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import market_engine as me

router = APIRouter()


class RFQCreate(BaseModel):
    molecule: str
    volume_mtpd: float
    max_price_eur_kg: Optional[float] = None
    delivery_start: str
    delivery_end: str
    location: Optional[str] = None
    buyer_name: Optional[str] = None          # ignored: the buyer is the signed-in company
    buyer_contact: Optional[str] = None
    compliance_requirements: Optional[List[str]] = None
    status: str = "draft"


def _party(request: Request) -> me.Party:
    try:
        return me.Party.from_payload(getattr(request.state, "user_payload", None) or {})
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


def _shape(row: dict) -> dict:
    out = dict(row)
    try:
        out["compliance_requirements"] = json.loads(row.get("compliance_requirements") or "[]")
    except (TypeError, ValueError):
        out["compliance_requirements"] = []
    return out


@router.post("/", status_code=201)
async def create_rfq(rfq: RFQCreate, request: Request):
    data = rfq.model_dump(exclude={"buyer_name"})
    return _shape(_call(me.create_rfq, _party(request), **data))


@router.get("/", response_model=dict)
async def list_rfqs(request: Request, status: Optional[str] = None, molecule: Optional[str] = None):
    rows = _call(me.my_rfqs, _party(request))
    rows = [r for r in rows if (not status or r["status"] == status)
            and (not molecule or r["molecule"] == molecule)]
    return {"rfqs": [_shape(r) for r in rows]}


@router.get("/{rfq_id}")
async def get_rfq(rfq_id: str, request: Request):
    for r in _call(me.my_rfqs, _party(request)):
        if r["id"] == rfq_id:
            return _shape(r)
    raise HTTPException(404, "RFQ not found")


@router.patch("/{rfq_id}/status", status_code=200)
async def update_rfq_status(rfq_id: str, new_status: str, request: Request):
    return _shape(_call(me.transition_rfq, _party(request), rfq_id, new_status))


@router.get("/{rfq_id}/transitions", status_code=200)
async def get_valid_rfq_transitions(rfq_id: str, request: Request):
    rfq = await get_rfq(rfq_id, request)
    return {"rfq_id": rfq_id, "current_status": rfq["status"],
            "valid_transitions": list(me.RFQ_TRANSITIONS.get(rfq["status"], ()))}
