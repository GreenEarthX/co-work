"""
Contracts API — /api/v1/contracts.

Creation goes through the market engine (core/market_engine.py): a contract is
made only from a match BOTH parties accepted, once, by one of the two parties,
and its terms are the match's snapshot — nothing is retyped. Reads show only the
contracts the caller is a party to (GEX sees all). A contract is a record: it is
cancelled through its status, never deleted.

Before 2026-10-23 this module opened the SQLite file directly and its `contracts`
table existed in neither store, so every call failed (gap register G-01; the
table is alembic 063).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import market_engine as me

router = APIRouter()


class ContractCreate(BaseModel):
    match_id: str
    delivery_terms: str
    payment_terms: str
    counterparty: Optional[str] = None   # ignored: the counterparty comes from the match


def _party(request: Request) -> me.Party:
    try:
        return me.Party.from_payload(getattr(request.state, "user_payload", None) or {})
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc


def _shape(row: dict) -> dict:
    return {k: row.get(k) for k in (
        "id", "project_id", "contract_id_external", "counterparty", "molecule", "volume_mtpd",
        "price_eur_kg", "start_date", "end_date", "tenor_years", "pricing_basis", "credit_rating",
        "status", "created_at", "project_name", "correlation_id", "match_id", "token_id",
        "seller_company_id", "buyer_company_id", "delivery_terms", "payment_terms")}


def _visible(conn, party: me.Party, where: str = "1=1", params: tuple = ()) -> list[dict]:
    sql = ("SELECT c.*, p.project_name FROM contracts c LEFT JOIN capacities p ON c.project_id = p.id "
           f"WHERE {where}")
    if not party.is_admin:
        sql += " AND (c.seller_company_id = ? OR c.buyer_company_id = ?)"
        params = (*params, party.company_id, party.company_id)
    return me._rows(conn, sql + " ORDER BY c.created_at DESC", params)


def _one(conn, party: me.Party, contract_id: str) -> dict:
    rows = _visible(conn, party, "c.id = ?", (contract_id,))
    if not rows:
        raise HTTPException(404, "Contract not found")
    return rows[0]


@router.post("/", status_code=201)
async def create_contract(contract: ContractCreate, request: Request):
    try:
        row = me.create_contract(_party(request), contract.match_id,
                                 delivery_terms=contract.delivery_terms,
                                 payment_terms=contract.payment_terms)
    except me.MarketRefused as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc
    return _shape(row)


@router.get("/", response_model=dict)
async def list_contracts(request: Request, molecule: Optional[str] = None, status: Optional[str] = None):
    party = _party(request)
    where, params = "1=1", []
    if molecule:
        where += " AND c.molecule = ?"
        params.append(molecule)
    if status:
        where += " AND c.status = ?"
        params.append(status)
    conn = me._conn()
    try:
        return {"contracts": [_shape(r) for r in _visible(conn, party, where, tuple(params))]}
    finally:
        conn.close()


@router.get("/accepted-matches/available", response_model=dict)
async def get_accepted_matches(request: Request):
    """My agreed matches that have no contract yet."""
    party = _party(request)
    conn = me._conn()
    try:
        rows = me._rows(conn, "SELECT m.*, p.project_name FROM matches m LEFT JOIN capacities p "
                              "ON p.id = m.project_id WHERE m.status = 'accepted' AND "
                              "(m.seller_company_id = ? OR m.buyer_company_id = ?) AND NOT EXISTS "
                              "(SELECT 1 FROM contracts c WHERE c.match_id = m.id) "
                              "ORDER BY m.created_at DESC", (party.company_id, party.company_id))
    finally:
        conn.close()
    return {"matches": [{k: r.get(k) for k in ("id", "match_score", "volume_mtpd", "price_eur_kg",
                                               "molecule", "delivery_start", "delivery_end",
                                               "project_name")} for r in rows]}


@router.get("/{contract_id}")
async def get_contract(contract_id: str, request: Request):
    conn = me._conn()
    try:
        return _shape(_one(conn, _party(request), contract_id))
    finally:
        conn.close()


@router.patch("/{contract_id}/status", status_code=200)
async def update_contract_status(contract_id: str, new_status: str, request: Request,
                                 notes: Optional[str] = None):
    """A party moves its contract through the contract state machine; GEX does not."""
    from app.core.state_machine import PreconditionError, TransitionError, transition_state

    party = _party(request)
    if party.is_admin:
        raise HTTPException(403, {"code": "GEX_DOES_NOT_TRADE",
                                  "message": "GEX operates the market and changes no contract."})
    conn = me._conn()
    try:
        row = _one(conn, party, contract_id)
        current = row["status"] or "draft"
        try:
            event_id = transition_state(aggregate_type="contract", aggregate_id=contract_id,
                                        from_state=current, to_state=new_status,
                                        data={"notes": notes, "changed_by": party.user_id},
                                        user_id=party.user_id, correlation_id=row["correlation_id"])
        except TransitionError as exc:
            raise HTTPException(400, f"Invalid transition: {exc}") from exc
        except PreconditionError as exc:
            raise HTTPException(422, f"Precondition failed: {exc}") from exc
        conn.execute("UPDATE contracts SET status = ?, updated_at = ? WHERE id = ?",
                     (new_status, me._now(), contract_id))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Status updated successfully", "contract_id": contract_id,
            "old_status": current, "new_status": new_status, "event_id": event_id}


@router.get("/{contract_id}/transitions", status_code=200)
async def get_valid_contract_transitions(contract_id: str, request: Request):
    from app.core.state_machine import get_valid_next_states

    conn = me._conn()
    try:
        current = _one(conn, _party(request), contract_id)["status"] or "draft"
    finally:
        conn.close()
    return {"contract_id": contract_id, "current_status": current,
            "valid_transitions": get_valid_next_states("contract", current)}


@router.delete("/{contract_id}", status_code=409)
async def delete_contract(contract_id: str):
    raise HTTPException(409, {"code": "CONTRACTS_ARE_RECORDS",
                              "message": "A contract is never deleted; cancel it through its status."})
