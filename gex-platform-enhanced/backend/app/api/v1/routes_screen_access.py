"""
Screen access rules API — mounted at /api/v1/ciso/screen-access.

GET  — the caller's own company's rules (any authenticated member: the menu needs them).
PUT  — replace the company's rule set. The /api/v1/ciso prefix is the governance
       domain, so domain_authorization already restricts writes to EXECUTIVE; the
       interface additionally sits behind the CISO password.
The company always comes from the verified token, never from the request.
A platform admin must name the company explicitly (?company_id=).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core import screen_access as sa_store
from app.core.request_tenant import PLATFORM_ADMIN, company_from_payload, payload_from_request

router = APIRouter()


class RuleIn(BaseModel):
    screen_id: str = Field(..., max_length=64)
    business_function: str = Field(..., max_length=32)
    effect: str = Field(..., max_length=8)


class RulesIn(BaseModel):
    rules: list[RuleIn] = Field(default_factory=list)


def _company(request: Request, company_id: Optional[str]) -> tuple[str, dict]:
    payload = payload_from_request(request) or {}
    tenant = company_from_payload(payload)
    if not tenant:
        raise HTTPException(status_code=401, detail="authenticated identity required")
    if tenant == PLATFORM_ADMIN:
        if not company_id:
            raise HTTPException(status_code=400, detail="platform admin must pass company_id")
        return company_id, payload
    if company_id and company_id != tenant:
        raise HTTPException(status_code=403, detail="a company can only read or change its own rules")
    return tenant, payload


@router.get("")
def get_rules(request: Request, company_id: Optional[str] = Query(default=None)):
    cid, _ = _company(request, company_id)
    return {"company_id": cid, "rules": sa_store.list_rules(cid)}


@router.put("")
def put_rules(request: Request, body: RulesIn, company_id: Optional[str] = Query(default=None)):
    cid, payload = _company(request, company_id)
    try:
        rules = sa_store.replace_rules(
            cid, [r.model_dump() for r in body.rules],
            updated_by=payload.get("user_id") or payload.get("email"),
        )
    except sa_store.ScreenAccessError as exc:
        raise HTTPException(status_code=422, detail={"problems": exc.problems}) from exc
    return {"company_id": cid, "rules": rules}
