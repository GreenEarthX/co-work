"""
Contract tokens (JML 2026-10-28; alembic 078; app/core/contract_tokens.py).

DEPRECATED compatibility layer (Phase 2 of "One contract record", 2026-11-06):
the tokens are contracts of the one contract record (alembic 085). These routes
keep working, with the same refusals, until the screens move (Phase 3).

  GET  /api/v1/contract-tokens/{project_id}                       every token, its chain, what is held back
  PUT  /api/v1/contract-tokens/{project_id}/{kind}/counterparty   owner's executive or GEX
  POST /api/v1/contract-tokens/{project_id}/{kind}/confirm        the counterparty (or appointed reviewer)
  POST /api/v1/contract-tokens/{project_id}/{kind}/dispute        the same parties
  POST /api/v1/contract-tokens/{project_id}/offtake/buyers/{company_id}/confirm   a frame's buyer, its own sub-leg
  POST /api/v1/contract-tokens/{project_id}/offtake/buyers/{company_id}/dispute   the same buyer

The offtake frame (Phase 3 of "One contract record", Q2): with several buyers the
offtake has one sub-leg per buyer and each buyer confirms its own; a frame has no
single counterparty, so the contract-level counterparty and confirm routes refuse it.

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
    buyers = ct.frame_confirmations(project_id)
    facts = ct.adverse_facts(project_id)
    _, held = ct.engine_terms(_load_terms_raw(project_id), confirmed, buyers, [f for f in facts if f["open"]])
    frame = ct.frame_state(project_id)
    in_force = {(b["buyer_company_id"], b["sub_leg_hash"].strip(), b["shared_hash"].strip()) for b in buyers}
    scope = ct.reviewer_scope(payload["user_id"], payload.get("company_id"), project_id, profile.owner_company_id)
    out = []
    for kind in list(ct.COUNTERPARTY_KINDS) + list(ct.REVIEWER_KINDS):
        if scope is not None and not ct.kind_gates(kind) & scope:
            continue                     # Q5: a reviewer reads the contracts of its own gates only
        c = ct.contract(project_id, kind, create=False)
        evs = ct.events(c["id"]) if c else []
        last = next((e for e in reversed(evs) if e["event_type"] == "VERSION"), None)
        frame_out = None
        if kind == "offtake" and frame and frame["sub_legs"]:
            frame_out = {"version": frame["version"], "shared_hash": frame["shared_hash"].strip(),
                         "buyers": _frame_buyers_for(frame, in_force, payload.get("company_id"),
                                                     profile.owner_company_id)}
        out.append({
            "kind": kind, "counterparty_company_id": (c or {}).get("counterparty_company_id"), "frame": frame_out,
            "confirmed_by": "counterparty" if kind in ct.COUNTERPARTY_KINDS else
                            f"appointed reviewer of {ct.REVIEWER_KINDS[kind]}",
            "latest_version_sha256": (last or {}).get("terms_sha256"),
            "confirmed": (all(b["confirmed"] for b in frame_out["buyers"]) if frame_out else kind in confirmed),
            "held_back_fields": held.get(kind, []),
            "verifies_evidence": list(ct.CONTRACT_EVIDENCE.get(kind, ())),
            "chain_intact": ct.chain_intact(c["id"]) if c else True,
            "events": [{k: e[k] for k in ("seq", "event_type", "terms_sha256", "actor", "company_id", "note", "at")}
                       for e in evs],
        })
    return {"project_id": project_id, "tokens": out,
            "adverse_facts": [f for f in facts if scope is None or ct.kind_gates(f["kind"]) & scope],
            "novations": ct.novations(project_id) if scope is None else [],
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
    if kind == "offtake" and ct.frame_state(project_id) and ct.frame_state(project_id)["sub_legs"]:
        _refuse(409, "FRAME_HAS_BUYERS", "This offtake is a frame: its buyers are named on the offtake card, "
                                         "one sub-leg each.")
    if body.company_id == profile.owner_company_id:
        _refuse(422, "NOT_A_COUNTERPARTY", "The owner cannot be its own counterparty.")
    if body.company_id not in profile.stakeholder_company_ids:
        _refuse(422, "NOT_A_PROJECT_PARTY", "The counterparty must be a company party to the project "
                                            "(GEX staff grant project access).")
    c = ct.contract(project_id, kind)
    if c.get("counterparty_company_id") == body.company_id:
        return {"kind": kind, "counterparty_company_id": body.company_id, "changed": False}
    # One transaction: the counterparty, COUNTERPARTY_SET, and the DISPUTED that withdraws
    # earlier confirmations (a new counterparty has confirmed nothing).
    ct.set_counterparty(c, body.company_id, payload["user_id"], payload.get("company_id"))
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
    _refuse_frame(project_id, kind)
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
    _refuse_frame(project_id, kind)
    _check_confirmer(payload, profile, kind, c)
    event = ct.append(c, "DISPUTED", payload["user_id"], payload.get("company_id"), note=body.note)
    changes = (await reevaluate(project_id, reason=f"contract {kind} disputed", actor=payload["user_id"]))["changes"]
    return {"kind": kind, "event": event, "reevaluation": changes}


# ── The offtake frame: each buyer confirms its own sub-leg (Phase 3, Q2) ───────

def _frame_buyers_for(frame: dict, in_force: set, viewer: Optional[str], owner: str) -> list[dict]:
    """Each buyer's sub-leg as the viewer may see it. Q5: a buyer sees its own sub-leg;
    another buyer's appears only as its hash and its share of the volume, never its
    company (the 23 Oct anonymity decision). The owner, lenders and reviewers see all."""
    shared = frame["shared_hash"].strip()
    vols = [(s["card_projection"] or {}).get("offtake.contracted_tonnes_per_year") or 0 for s in frame["sub_legs"]]
    total = sum(vols)
    is_buyer = viewer != owner and viewer in {s["company_id"] for s in frame["sub_legs"]}
    out = []
    for s, vol in zip(frame["sub_legs"], vols):
        mine = s["company_id"] == viewer
        out.append({"company_id": s["company_id"] if (mine or not is_buyer) else None,
                    "sub_leg_hash": s["sub_leg_hash"].strip(),
                    "confirmed": (s["company_id"], s["sub_leg_hash"].strip(), shared) in in_force,
                    "volume_share": round(vol / total, 4) if total else None})
    return out


def _refuse_frame(project_id: str, kind: str) -> None:
    if kind == "offtake":
        frame = ct.frame_state(project_id)
        if frame and frame["sub_legs"]:
            _refuse(409, "FRAME_CONFIRMS_PER_BUYER", "This offtake is a frame: each buyer confirms its own "
                                                     "sub-leg (/offtake/buyers/{company_id}/confirm).")


def _check_buyer(payload: dict, company_id: str) -> None:
    from app.core.projects_store import _rows

    if payload.get("is_platform_admin"):
        _refuse(403, "GEX_DOES_NOT_CONFIRM", "GEX sets the rule; it never confirms a party's terms.")
    account = _rows("SELECT account_state, company_id FROM auth_users WHERE user_id = :u", {"u": payload["user_id"]})
    if not account or account[0]["account_state"] != "ACTIVE":
        _refuse(403, "ACCOUNT_NOT_ACTIVE", "Only an active account confirms.")
    if account[0]["company_id"] != company_id:
        _refuse(403, "OWN_SUB_LEG_ONLY", "A buyer confirms or disputes its own sub-leg only.")


class SubLegConfirmBody(BaseModel):
    sub_leg_hash: str
    note: Optional[str] = None


@router.post("/contract-tokens/{project_id}/offtake/buyers/{company_id}/confirm")
async def confirm_sub_leg(project_id: str, company_id: str, body: SubLegConfirmBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate, verify_by_counterparty

    payload, profile = _context(request, project_id)
    _check_buyer(payload, company_id)
    try:
        event = ct.confirm_sub_leg(project_id, company_id, body.sub_leg_hash, "CONFIRMED", payload["user_id"], body.note)
    except ct.TokenRefusal as exc:
        _refuse(exc.status, exc.code, exc.message)
    # The buyer is a party to the offtake it confirms: its confirmation verifies the
    # offtake's own instrument evidence (Q7.4), never a third party's instrument.
    verified = verify_by_counterparty(project_id, ct.CONTRACT_EVIDENCE["offtake"], payload,
                                      note=f"verified by {company_id}'s confirmation of its offtake sub-leg, "
                                           f"event {event['seq']} ({event['event_hash'][:12]})")
    changes = (await reevaluate(project_id, reason=f"offtake sub-leg confirmed by {company_id}",
                                actor=payload["user_id"]))["changes"]
    return {"company_id": company_id, "confirmed_sub_leg_hash": body.sub_leg_hash, "event": event,
            "evidence_verified": verified, "reevaluation": changes}


@router.post("/contract-tokens/{project_id}/offtake/buyers/{company_id}/dispute")
async def dispute_sub_leg(project_id: str, company_id: str, body: DisputeBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate

    payload, profile = _context(request, project_id)
    _check_buyer(payload, company_id)
    try:
        event = ct.confirm_sub_leg(project_id, company_id, "", "DISPUTED", payload["user_id"], body.note)
    except ct.TokenRefusal as exc:
        _refuse(exc.status, exc.code, exc.message)
    changes = (await reevaluate(project_id, reason=f"offtake sub-leg disputed by {company_id}",
                                actor=payload["user_id"]))["changes"]
    return {"company_id": company_id, "event": event, "reevaluation": changes}


# ── Adverse facts as events (Phase 3, Q10) ───────────────────────────────────

# A lender with project access (Q10): the capital providers among abac.ActorType.
LENDER_ACTOR_TYPES = ("COMMERCIAL_BANKER", "DFI", "DFI_CONCESSIONAL", "ECA")


def _party_role(payload: dict, profile, project_id: str) -> Optional[str]:
    """owner | counterparty | buyer | lender | reviewer, or None for anyone else."""
    from app.core.projects_store import _rows

    company = payload.get("company_id")
    if company == profile.owner_company_id:
        return "owner"
    roles = {r["actor_type"] for r in _rows(
        "SELECT actor_type FROM auth_user_project_roles WHERE user_id = :u AND project_id = :p",
        {"u": payload["user_id"], "p": project_id})}
    from app.core.abac import REVIEWER_GATES
    if any(getattr(role, "value", role) in roles for role in REVIEWER_GATES):
        return "reviewer"
    access = _rows("SELECT actor_type FROM project_access WHERE project_id = :p AND company_id = :c",
                   {"p": project_id, "c": company})
    if any((a["actor_type"] or "").upper() in LENDER_ACTOR_TYPES for a in access):
        return "lender"
    return None


def _check_document(project_id: str, sha256: str) -> None:
    from app.core.projects_store import _rows

    if not sha256 or not _rows("SELECT 1 AS x FROM evidence_documents WHERE project_id = :p AND sha256 = :s",
                               {"p": project_id, "s": sha256}):
        _refuse(422, "DOCUMENT_REQUIRED", "Name the sha256 of a document on file for this project "
                                          "(POST /bankability/evidence/document).")


def _confirming_party(project_id: str, kind: str, subject: Optional[str]) -> Optional[str]:
    if kind == "offtake":
        return subject
    c = ct.contract(project_id, kind, create=False)
    return (c or {}).get("counterparty_company_id")


class FactBody(BaseModel):
    fact: str
    document_sha256: str
    subject_company_id: Optional[str] = None      # BUYER_INSOLVENT: the buyer whose sub-leg it concerns
    note: Optional[str] = None


@router.post("/contract-tokens/{project_id}/adverse-facts")
async def report_adverse_fact(project_id: str, body: FactBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate

    payload, profile = _context(request, project_id)
    if body.fact not in ct.FACTS:
        _refuse(422, "UNKNOWN_FACT", f"Adverse facts: {', '.join(ct.FACTS)}.")
    if payload.get("is_platform_admin"):
        _refuse(403, "GEX_REPORTS_NO_FACT", "GEX sets the rule; it reports no party's facts.")
    kind = ct.FACTS[body.fact][0]
    if body.fact == "BUYER_INSOLVENT" and not body.subject_company_id:
        _refuse(422, "SUBJECT_REQUIRED", "Name the buyer whose sub-leg the insolvency concerns.")
    company = payload.get("company_id")
    role = _party_role(payload, profile, project_id)
    frame = ct.frame_state(project_id) if kind == "offtake" else None
    is_buyer = bool(frame) and company in {s["company_id"] for s in frame["sub_legs"]}
    if kind != "offtake" and company == _confirming_party(project_id, kind, None):
        role = role or "counterparty"
    if is_buyer:
        role = role or "buyer"
        if body.subject_company_id and body.subject_company_id != company:
            _refuse(403, "NOT_ABOUT_ANOTHER_BUYER", "A buyer reports only about its own sub-leg or the shared terms.")
    if role is None:
        _refuse(403, "NOT_A_REPORTING_PARTY", "The owner, the contract's counterparty, a lender with project access "
                                              "or an appointed reviewer reports an adverse fact.")
    _check_document(project_id, body.document_sha256)
    try:
        event = ct.report_fact(project_id, body.fact, body.document_sha256, payload["user_id"], company,
                               body.subject_company_id, body.note)
    except ct.TokenRefusal as exc:
        _refuse(exc.status, exc.code, exc.message)
    changes = (await reevaluate(project_id, reason=f"adverse fact {body.fact} reported", actor=payload["user_id"]))["changes"]
    return {"fact": body.fact, "event": event, "reevaluation": changes}


class ClearBody(BaseModel):
    document_sha256: str


@router.post("/contract-tokens/{project_id}/adverse-facts/{report_event_hash}/clear")
async def clear_adverse_fact(project_id: str, report_event_hash: str, body: ClearBody, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate

    payload, profile = _context(request, project_id)
    if payload.get("is_platform_admin"):
        _refuse(403, "GEX_CLEARS_NO_FACT", "GEX never clears an adverse fact.")
    fact = next((f for f in ct.adverse_facts(project_id) if f["report_event_hash"] == report_event_hash), None)
    if fact is None:
        _refuse(404, "NO_SUCH_REPORT", "No adverse fact was reported with that event hash.")
    company = payload.get("company_id")
    if company == fact["reporter_company_id"]:
        _refuse(403, "REPORTER_CANNOT_CLEAR", "The reporter's company never clears its own report.")
    confirming = _confirming_party(project_id, fact["kind"], fact["subject_company_id"])
    subject_is_confirming = ct.FACTS[fact["fact"]][2]
    role = _party_role(payload, profile, project_id)
    if company == confirming:
        if subject_is_confirming:
            _refuse(403, "AFFECTED_PARTY_CANNOT_CLEAR", "The party the fact is about does not clear it: the owner "
                                                         "and a lender or reviewer do.")
        role = role or "counterparty"
    if role not in ("owner", "counterparty", "lender", "reviewer"):
        _refuse(403, "NOT_A_CLEARING_PARTY", "The owner, the confirming party, a lender with project access or an "
                                             "appointed reviewer confirms a clearing.")
    _check_document(project_id, body.document_sha256)
    try:
        event = ct.clear_fact(project_id, report_event_hash, body.document_sha256, payload["user_id"], company)
    except ct.TokenRefusal as exc:
        _refuse(exc.status, exc.code, exc.message)
    still = next(f for f in ct.adverse_facts(project_id) if f["report_event_hash"] == report_event_hash)
    changes = None
    if not still["open"]:
        changes = (await reevaluate(project_id, reason=f"adverse fact {fact['fact']} cleared",
                                    actor=payload["user_id"]))["changes"]
    return {"event": event, "cleared": not still["open"], "cleared_by": still["cleared_by"], "reevaluation": changes}


# ── Novation (Phase 3, Q13): three confirmations, no token ───────────────────

class NovationBody(BaseModel):
    incoming_company_id: str
    document_sha256: Optional[str] = None          # the lenders' consent, when given (not checked by GEX)


def _eligible_incoming(project_id: str, profile, incoming: str) -> None:
    from app.core.projects_store import _rows

    if incoming == profile.owner_company_id:
        _refuse(422, "PRODUCER_CANNOT_BUY_ITS_OWN", "The producer cannot take a buyer's sub-leg.")
    if incoming not in profile.stakeholder_company_ids:
        _refuse(422, "NOT_A_PROJECT_PARTY", "The incoming buyer must be a company party to the project "
                                            "(GEX staff grant project access).")
    if not _rows("SELECT 1 AS x FROM auth_users WHERE company_id = :c AND account_state = 'ACTIVE' "
                 "AND coalesce(is_platform_admin, 0) = 0", {"c": incoming}):
        _refuse(422, "INCOMING_NOT_VETTED", "The incoming buyer has no vetted, active account.")


def _novation_actor(payload: dict) -> None:
    from app.core.projects_store import _rows

    if payload.get("is_platform_admin"):
        _refuse(403, "GEX_IS_NO_PARTY", "GEX is never a party to a novation.")
    account = _rows("SELECT account_state FROM auth_users WHERE user_id = :u", {"u": payload["user_id"]})
    if not account or account[0]["account_state"] != "ACTIVE":
        _refuse(403, "ACCOUNT_NOT_ACTIVE", "Only an active account confirms.")


@router.post("/contract-tokens/{project_id}/offtake/buyers/{company_id}/novation")
async def propose_novation(project_id: str, company_id: str, body: NovationBody, request: Request):
    payload, profile = _context(request, project_id)
    _novation_actor(payload)
    me = payload.get("company_id")
    if me not in (profile.owner_company_id, company_id, body.incoming_company_id):
        _refuse(403, "NOT_A_NOVATION_PARTY", "Only the producer, the outgoing or the incoming buyer proposes a novation.")
    _eligible_incoming(project_id, profile, body.incoming_company_id)
    if body.document_sha256:
        _check_document(project_id, body.document_sha256)
    try:
        event = ct.propose_novation(project_id, profile.owner_company_id, company_id, body.incoming_company_id,
                                    payload["user_id"], me, body.document_sha256)
    except ct.TokenRefusal as exc:
        _refuse(exc.status, exc.code, exc.message)
    return {"proposal_event_hash": event["event_hash"], "event": event,
            "awaiting": [p for p in ct.NOVATION_PARTIES
                         if p != ("producer" if me == profile.owner_company_id else
                                  "outgoing" if me == company_id else "incoming")]}


@router.post("/contract-tokens/{project_id}/offtake/novations/{proposal_event_hash}/confirm")
async def confirm_novation(project_id: str, proposal_event_hash: str, request: Request):
    from app.api.v1.routes_bankability_proxy import reevaluate

    payload, profile = _context(request, project_id)
    _novation_actor(payload)
    try:
        out = ct.confirm_novation(project_id, profile.owner_company_id, proposal_event_hash, payload["user_id"],
                                  payload.get("company_id"))
    except ct.TokenRefusal as exc:
        _refuse(exc.status, exc.code, exc.message)
    if out["completed"]:
        out["reevaluation"] = (await reevaluate(project_id, reason="offtake sub-leg novated",
                                                actor=payload["user_id"]))["changes"]
    return out
