"""
Contract tokens (JML 2026-10-28; alembic 078; app/core/contract_tokens.py).

  GET  /api/v1/contract-tokens/{project_id}                       every token, its chain, what is held back
  PUT  /api/v1/contract-tokens/{project_id}/{kind}/counterparty   owner's executive or GEX
  POST /api/v1/contract-tokens/{project_id}/{kind}/confirm        the counterparty (or appointed reviewer)
  POST /api/v1/contract-tokens/{project_id}/{kind}/dispute        the same parties

A counterparty's confirmation verifies the contract's own instrument evidence:
an independent verifier may exist but is not required for a contract.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import contract_tokens as ct

router = APIRouter()


def _context(request: Request, project_id: str):
    from app.api.v1.routes_projects import _visible_ids_from_jwt
    from app.core.project_registry import get_project_profile
    from app.core.request_tenant import payload_from_request

    payload = payload_from_request(request) or {}
    if not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Authentication required")
    profile = get_project_profile(project_id)
    if profile is None or project_id not in _visible_ids_from_jwt(payload):
        raise HTTPException(status_code=404, detail="Project not found")
    return payload, profile


def _kind_or_404(kind: str) -> str:
    if kind not in ct.COUNTERPARTY_KINDS and kind not in ct.REVIEWER_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown contract kind: {kind}")
    return kind


def _refuse(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/contract-tokens/{project_id}")
def list_tokens(project_id: str, request: Request):
    from app.api.v1.routes_bankability_proxy import _load_terms_raw

    payload, profile = _context(request, project_id)
    confirmed = ct.confirmed_terms(project_id)
    _, held = ct.engine_terms(_load_terms_raw(project_id), confirmed)
    out = []
    for kind in list(ct.COUNTERPARTY_KINDS) + list(ct.REVIEWER_KINDS):
        c = ct.contract(project_id, kind, create=False)
        evs = ct.events(c["id"]) if c else []
        last = next((e for e in reversed(evs) if e["event_type"] == "VERSION"), None)
        out.append({
            "kind": kind, "counterparty_company_id": (c or {}).get("counterparty_company_id"),
            "confirmed_by": "counterparty" if kind in ct.COUNTERPARTY_KINDS else
                            f"appointed reviewer of {ct.REVIEWER_KINDS[kind]}",
            "latest_version_sha256": (last or {}).get("terms_sha256"),
            "confirmed": kind in confirmed, "held_back_fields": held.get(kind, []),
            "verifies_evidence": list(ct.CONTRACT_EVIDENCE.get(kind, ())),
            "chain_intact": ct.chain_intact(c["id"]) if c else True,
            "events": [{k: e[k] for k in ("seq", "event_type", "terms_sha256", "actor", "company_id", "note", "at")}
                       for e in evs],
        })
    return {"project_id": project_id, "tokens": out,
            "possible_counterparties": sorted(profile.stakeholder_company_ids - {profile.owner_company_id}),
            "you": {"company_id": payload.get("company_id"), "is_gex": bool(payload.get("is_platform_admin")),
                    "is_owner_executive": payload.get("company_id") == profile.owner_company_id
                    and payload.get("business_function") == "EXECUTIVE"}}


class CounterpartyBody(BaseModel):
    company_id: str


@router.put("/contract-tokens/{project_id}/{kind}/counterparty")
async def set_counterparty(project_id: str, kind: str, body: CounterpartyBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate

    payload, profile = _context(request, project_id)
    if _kind_or_404(kind) not in ct.COUNTERPARTY_KINDS:
        _refuse(422, "REVIEWER_CONFIRMS", f"The {kind} terms are confirmed by an appointed reviewer, not a counterparty.")
    owner_exec = (payload.get("company_id") == profile.owner_company_id
                  and payload.get("business_function") == "EXECUTIVE")
    if not (owner_exec or payload.get("is_platform_admin")):
        _refuse(403, "OWNER_EXECUTIVE_OR_GEX", "Only the owner's executive or GEX staff register a counterparty.")
    if body.company_id == profile.owner_company_id:
        _refuse(422, "NOT_A_COUNTERPARTY", "The owner cannot be its own counterparty.")
    if body.company_id not in profile.stakeholder_company_ids:
        _refuse(422, "NOT_A_PROJECT_PARTY", "The counterparty must be a company party to the project "
                                            "(GEX staff grant project access).")
    c = ct.contract(project_id, kind)
    if c.get("counterparty_company_id") == body.company_id:
        return {"kind": kind, "counterparty_company_id": body.company_id, "changed": False}
    from app.core.db_backend import domain_connection
    conn = domain_connection()
    try:
        conn.execute("UPDATE project_contract SET counterparty_company_id = ? WHERE id = ?", (body.company_id, c["id"]))
        conn.commit()
    finally:
        conn.close()
    ct.append(c, "COUNTERPARTY_SET", payload["user_id"], payload.get("company_id"),
              note=f"counterparty {body.company_id}")
    # A new counterparty has confirmed nothing: earlier confirmations no longer stand.
    ct.append(c, "DISPUTED", payload["user_id"], payload.get("company_id"), note="counterparty changed")
    await reevaluate(project_id, reason=f"contract {kind}: counterparty {body.company_id}", actor=payload["user_id"])
    return {"kind": kind, "counterparty_company_id": body.company_id, "changed": True}


class ConfirmBody(BaseModel):
    terms_sha256: Optional[str] = None
    note: Optional[str] = None


def _check_confirmer(payload: dict, profile, kind: str, c: dict) -> None:
    from app.core.projects_store import _rows

    if payload.get("is_platform_admin"):
        _refuse(403, "GEX_DOES_NOT_CONFIRM", "GEX sets the rule; it never confirms a party's terms.")
    account = _rows("SELECT account_state, company_id FROM auth_users WHERE user_id = :u",
                    {"u": payload["user_id"]})
    if not account or account[0]["account_state"] != "ACTIVE":
        _refuse(403, "ACCOUNT_NOT_ACTIVE", "Only an active account confirms.")
    if kind in ct.COUNTERPARTY_KINDS:
        if not c.get("counterparty_company_id"):
            _refuse(409, "NO_COUNTERPARTY", "No counterparty is registered on this contract.")
        if account[0]["company_id"] != c["counterparty_company_id"]:
            _refuse(403, "COUNTERPARTY_ONLY", "Only the registered counterparty confirms these terms.")
    else:
        if account[0]["company_id"] == profile.owner_company_id:
            _refuse(403, "OWNER_CANNOT_CONFIRM", "The producer's own plan is confirmed by an independent reviewer.")
        if not ct.is_appointed_reviewer(payload["user_id"], profile.project_id, ct.REVIEWER_KINDS[kind]):
            _refuse(403, "NOT_APPOINTED_REVIEWER",
                    f"Only a reviewer appointed for {ct.REVIEWER_KINDS[kind]} confirms the {kind} terms.")


@router.post("/contract-tokens/{project_id}/{kind}/confirm")
async def confirm(project_id: str, kind: str, body: ConfirmBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate, verify_by_counterparty

    payload, profile = _context(request, project_id)
    c = ct.contract(project_id, _kind_or_404(kind))
    _check_confirmer(payload, profile, kind, c)
    last = ct.latest_version(c["id"])
    if last is None and kind != "licence":
        _refuse(409, "NOTHING_TO_CONFIRM", "No terms have been recorded for this contract yet.")
    if last is not None and body.terms_sha256 != last["terms_sha256"]:
        _refuse(409, "NOT_THE_LATEST_VERSION",
                "Confirm the latest version you have read: name its terms_sha256 (the terms changed since).")
    event = ct.append(c, "CONFIRMED", payload["user_id"], payload.get("company_id"),
                      sha=(last or {}).get("terms_sha256"), note=body.note)
    verified = []
    if kind in ct.CONTRACT_EVIDENCE:
        verified = verify_by_counterparty(project_id, ct.CONTRACT_EVIDENCE[kind], payload,
                                          note=f"verified by counterparty confirmation on the {kind} token, "
                                               f"event {event['seq']} ({event['event_hash'][:12]})")
    changes = (await reevaluate(project_id, reason=f"contract {kind} confirmed", actor=payload["user_id"]))["changes"]
    return {"kind": kind, "confirmed_sha256": (last or {}).get("terms_sha256"), "event": event,
            "evidence_verified": verified, "reevaluation": changes}


class DisputeBody(BaseModel):
    note: str


@router.post("/contract-tokens/{project_id}/{kind}/dispute")
async def dispute(project_id: str, kind: str, body: DisputeBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate

    payload, profile = _context(request, project_id)
    c = ct.contract(project_id, _kind_or_404(kind))
    _check_confirmer(payload, profile, kind, c)
    event = ct.append(c, "DISPUTED", payload["user_id"], payload.get("company_id"), note=body.note)
    changes = (await reevaluate(project_id, reason=f"contract {kind} disputed", actor=payload["user_id"]))["changes"]
    return {"kind": kind, "event": event, "reevaluation": changes}
