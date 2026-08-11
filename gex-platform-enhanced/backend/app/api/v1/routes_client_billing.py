"""
Client commercial agreement and invoicing routes.

Two identity rules, both server-side:

  * Terms are accepted BY the authenticated user, FOR the caller's own company. Neither
    is a body field. Accepting a contract on behalf of someone else is not a feature.
  * Publishing terms and recording payment are GEX staff operations. A client marking
    their own invoice paid is not an oversight to fix later.

This surface records invoices. It does not move money — see `app.core.client_billing`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import client_billing as cb
from app.core.request_tenant import company_from_payload, payload_from_request

router = APIRouter(prefix="/billing", tags=["Client Billing"])

try:
    cb.init_billing_db()
except Exception:  # pragma: no cover - schema init is best-effort at import
    pass


def _payload(request: Request) -> dict:
    return payload_from_request(request) or {}


def _require_staff(request: Request) -> dict:
    payload = _payload(request)
    if not payload.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail="GEX staff only")
    return payload


def _require_own_company(request: Request, client_id: str) -> dict:
    """A user acts for their own company. Staff may act for any."""
    payload = _payload(request)
    company_id = company_from_payload(payload)
    if not company_id:
        raise HTTPException(status_code=401, detail="authenticated identity required")
    if company_id != client_id and not payload.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail="not your client account")
    return payload


class PublishTermsInput(BaseModel):
    version: str
    content: str
    effective_from: Optional[str] = None


class CreateClientInput(BaseModel):
    client_id: str
    company_name: str
    seat_limit: int = cb.DEFAULT_SEAT_LIMIT


class AcceptTermsInput(BaseModel):
    terms_id: str
    channel: str = "WEB"


class IssueInvoiceInput(BaseModel):
    terms_id: str
    due_at: Optional[str] = None


class RecordPaymentInput(BaseModel):
    payment_ref: str


@router.post("/terms")
async def publish_terms(request: Request, body: PublishTermsInput):
    payload = _require_staff(request)
    return cb.publish_terms(
        version=body.version,
        content=body.content,
        published_by=payload.get("sub") or "gex_staff",
        effective_from=body.effective_from,
    )


@router.get("/terms/{terms_id}")
async def get_terms(terms_id: str):
    terms = cb.get_terms(terms_id)
    if terms is None:
        raise HTTPException(status_code=404, detail="no such terms")
    return terms


@router.post("/clients")
async def create_client(request: Request, body: CreateClientInput):
    _require_staff(request)
    try:
        return cb.create_client(body.client_id, body.company_name, body.seat_limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/clients/{client_id}")
async def get_client(request: Request, client_id: str):
    _require_own_company(request, client_id)
    client = cb.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="no such client")
    return {**client, "seats_used": cb.seats_used(client_id)}


@router.post("/clients/{client_id}/accept-terms")
async def accept_terms(request: Request, client_id: str, body: AcceptTermsInput):
    """Accepted by the authenticated user. Who accepted is not a body field."""
    payload = _require_own_company(request, client_id)
    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="authenticated user required")

    def assert_active(_uid: str) -> None:
        if payload.get("account_state") not in (None, "ACTIVE"):
            raise cb.BillingError("account is not ACTIVE")

    try:
        return cb.accept_terms(client_id, body.terms_id, user_id, body.channel,
                               assert_user_active=assert_active)
    except cb.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/clients/{client_id}/invoice")
async def issue_invoice(request: Request, client_id: str, body: IssueInvoiceInput):
    _require_staff(request)
    try:
        return cb.issue_subscription_invoice(client_id, body.terms_id, body.due_at)
    except cb.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/invoices/{invoice_id}")
async def get_invoice(request: Request, invoice_id: str):
    invoice = cb.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="no such invoice")
    _require_own_company(request, invoice["client_id"])
    return invoice


@router.post("/invoices/{invoice_id}/payment")
async def record_payment(request: Request, invoice_id: str, body: RecordPaymentInput):
    """Staff only. A client marking their own invoice paid is not a feature."""
    _require_staff(request)
    try:
        return cb.record_payment(invoice_id, body.payment_ref)
    except cb.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
