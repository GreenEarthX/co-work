"""
Product records — /api/v1/products (Phase 1; alembic 116). Policy and every check:
core/product_record.py. The acting party is the signed-in user and company from the token.

    POST /projects/{project_id}/documents     multipart `file`; GEX computes the sha256
    POST /tokens/{token_id}/quality           a typed quality parameter, declared or measured
    POST /tokens/{token_id}/carbon-intensity  value, method, boundary, calculation date, basis
    POST /certificates                        certificate or inspection report, scope, coverage
    POST /certificates/{id}/decision          verified | rejected — an appointed reviewer only (D-F)
    GET  /tokens/{token_id}                   the product view (owner, appointed reviewers, GEX)
    GET  /parameters                          the typed quality parameters and their units
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import market_engine as me
from app.core import product_record as pr

router = APIRouter()


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


class QualityIn(BaseModel):
    parameter: str
    value: float
    basis: str = "declared"
    document_sha256: Optional[str] = None


class CarbonIntensityIn(BaseModel):
    value_gco2e_mj: float = Field(..., ge=0)
    method: str
    system_boundary: str
    calculation_date: str
    basis: str
    document_sha256: Optional[str] = None


class CoverIn(BaseModel):
    token_id: str
    quantity_t: Optional[float] = Field(None, gt=0)
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class CertificateIn(BaseModel):
    project_id: str
    kind: str
    scheme: str
    body: str
    reference: str
    scope: str
    valid_from: str
    valid_until: Optional[str] = None
    facility_id: Optional[str] = None
    document_sha256: Optional[str] = None
    covers: list[CoverIn] = []


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None


@router.get("/parameters")
def parameters():
    return {"parameters": [{"parameter": k, "unit": u, "label": label} for k, (u, label) in pr.PARAMETERS.items()]}


@router.post("/projects/{project_id}/documents", status_code=201)
async def file_document(project_id: str, request: Request):
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(422, {"code": "DOCUMENT_EMPTY", "message": "Send the document as `file`."})
    content = await upload.read()
    return _call(pr.file_document, _party(request), project_id, getattr(upload, "filename", None) or "document", content)


@router.post("/tokens/{token_id}/quality", status_code=201)
def add_quality(token_id: str, body: QualityIn, request: Request):
    return _call(pr.add_quality, _party(request), token_id, **body.model_dump())


@router.post("/tokens/{token_id}/carbon-intensity", status_code=201)
def add_carbon_intensity(token_id: str, body: CarbonIntensityIn, request: Request):
    return _call(pr.add_carbon_intensity, _party(request), token_id, **body.model_dump())


@router.post("/certificates", status_code=201)
def submit_certificate(body: CertificateIn, request: Request):
    data = body.model_dump()
    project_id = data.pop("project_id")
    data["covers"] = [c for c in data["covers"]]
    return _call(pr.submit_certificate, _party(request), project_id, **data)


@router.post("/certificates/{certificate_id}/decision")
def decide(certificate_id: str, body: DecisionIn, request: Request):
    return _call(pr.decide_certificate, _party(request), certificate_id, body.decision, body.note)


@router.get("/tokens/{token_id}/listing-preview")
def listing_preview(token_id: str, request: Request):
    return _call(pr.listing_preview, _party(request), token_id)


@router.get("/tokens/{token_id}")
def product(token_id: str, request: Request):
    return _call(pr.product_view, _party(request), token_id)
