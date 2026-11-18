"""
Published returns cases — publish, read, export, share (handoff v4, tasks 8 and 10).
===================================================================================
Prefix /api/v1/returns-cases. PostgreSQL only (migration 123).

  POST   /{project_id}                         the owner publishes a case version
  GET    /{project_id}                         versions the caller may read, with identity
  GET    /{project_id}/versions/{version_id}   one version, disclosed for this reader
  GET    /{project_id}/versions/{version_id}/export   the same, as a JSON export
  GET    /{project_id}/shares                  the owner's RETURNS shares
  POST   /{project_id}/shares                  share one version (or a case and its later versions)
  DELETE /{project_id}/shares/{entitlement_id} revoke

Only the owner company's finance or executive function publishes and shares.
A reader with a RETURNS share sees the stored figures of the shared version(s)
and no dated pre-FID figure. A reader with neither gets 403: no returns of the
project. Nothing here recomputes a published case. Every response is no-store.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core import entitlements as ent
from app.core import pre_fid_access, returns_cases as rc
from app.core.devex_share import PRODUCER_FUNCTIONS, normalise_expiry
from app.core.request_tenant import payload_from_request

router = APIRouter(prefix="/api/v1/returns-cases", tags=["returns-cases"])

_JSON_COLS = ("tea_case", "input_versions", "inputs", "results", "sensitivities", "provenance", "governance")


class PublishRequest(BaseModel):
    case_name: str = Field(..., min_length=1, description="e.g. 'Base case', 'Downside'")
    scenario: str = Field(..., min_length=1)
    valuation_boundary: str = Field("FULL_PROJECT")
    inputs: dict = Field(..., description="The PF engine's returns inputs (ReturnsRequest)")
    tea_case: Optional[dict] = None          # {"claim_id", "pathway_id", ...}
    input_versions: Optional[dict] = None
    assumptions: list[dict] = []             # [{name, value, source, verification_status}]


class ShareRequest(BaseModel):
    user_id: str
    version_id: Optional[str] = None         # one version
    case_id: Optional[str] = None            # or a case and its later versions
    expires_at: Optional[str] = None
    reason: Optional[str] = None


def _payload(request: Request) -> dict:
    payload = payload_from_request(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def _conn(tenant: str):
    from app.core.db_backend import capital_connection, capital_is_postgres, require_postgres
    require_postgres(capital_is_postgres(), "Published returns cases", "CAPITAL_DB_BACKEND")
    return capital_connection(company_id=tenant)


def _row(r) -> dict:
    d = dict(r)
    for k in _JSON_COLS:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    if d.get("published_at") is not None:
        d["published_at"] = str(d["published_at"])
    return d


def _versions(project_id: str, tenant: str) -> list[dict]:
    try:
        conn = _conn(tenant)
        try:
            rows = conn.execute("SELECT * FROM returns_case_version WHERE project_id = ? "
                                "ORDER BY case_id, version_number", [project_id]).fetchall()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — unreadable is "unavailable", never "none published"
        raise pre_fid_access.unavailable("The published returns cases") from exc
    return [_row(r) for r in rows]


def _insert(tenant: str, record: dict) -> dict:
    """Write one version (INSERT only; the table refuses UPDATE and DELETE) and read it back."""
    cols = list(record)
    conn = _conn(tenant)
    try:
        conn.execute(f"INSERT INTO returns_case_version ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                     [json.dumps(record[c]) if c in _JSON_COLS and record[c] is not None else record[c]
                      for c in cols])
        conn.commit()
        return _row(conn.execute("SELECT * FROM returns_case_version WHERE version_id = ?",
                                 [record["version_id"]]).fetchone())
    finally:
        conn.close()


def _returns_shares(access: pre_fid_access.Access) -> tuple[set, set]:
    if not access.user_id:
        return set(), set()
    try:
        caps = [r["capability"] for r in ent.list_entitlements(user_id=access.user_id, project_id=access.project_id)
                if r["status"] == "active"]
    except Exception as exc:  # noqa: BLE001
        raise pre_fid_access.unavailable("The project's shares") from exc
    return rc.shared_targets(caps)


def _owner_finance(access: pre_fid_access.Access, payload: dict) -> bool:
    return access.basis == "owner" and payload.get("business_function") in PRODUCER_FUNCTIONS


def _require_owner_finance(request: Request, project_id: str) -> tuple[pre_fid_access.Access, dict]:
    payload = _payload(request)
    access = pre_fid_access.resolve(request, project_id)
    if not _owner_finance(access, payload):
        raise HTTPException(status_code=403, detail={
            "code": "OWNER_FINANCE_ONLY",
            "message": "Only the finance or executive function of the project's owner publishes or shares returns cases."})
    return access, payload


async def _review(version: dict, owner_tenant: str) -> dict:
    from app.api.v1.routes_bankability_proxy import engine_rules
    from app.core.readiness import current_fingerprint
    try:
        rules = (await engine_rules()).get("rules_version")
    except HTTPException:
        rules = None
    return rc.needs_review(version, current_fingerprint=current_fingerprint(version["project_id"]),
                           current_rules_version=rules,
                           current_tea_claim=_current_tea_claim(version["project_id"], owner_tenant))


def _current_tea_claim(project_id: str, owner_tenant: str) -> Optional[str]:
    try:
        from app.core.db_backend import domain_connection
        conn = domain_connection(company_id=owner_tenant)
        try:
            row = conn.execute(
                "SELECT claim_id FROM model_base_case WHERE project_id = ? AND valid_to IS NULL "
                "AND state NOT IN ('superseded','rejected','expired','failed') ORDER BY created_at DESC LIMIT 1",
                [project_id]).fetchone()
        finally:
            conn.close()
        return row["claim_id"] if row else None
    except Exception:  # noqa: BLE001 — unknown, not "unchanged": needs_review then names no TEA change
        return None


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post("/{project_id}", status_code=201)
async def publish(project_id: str, body: PublishRequest, request: Request, response: Response):
    _no_store(response)
    access, payload = _require_owner_finance(request, project_id)
    return await publish_version(access, payload, request, body)


async def publish_version(access: pre_fid_access.Access, payload: dict, request: Request,
                          body: PublishRequest, chain: Optional[dict] = None) -> dict:
    """Compute on the PF engine and store one version. `chain` (calculation chain,
    18 Nov): {source_versions, checks, remaining_assumptions}, recorded in the
    version's input_versions — hashed with it and shown wherever it is cited."""
    from app.api.v1.routes_finance_model import _call_model
    from app.core import readiness

    if body.valuation_boundary not in rc.BOUNDARIES:
        raise HTTPException(status_code=422, detail=f"valuation_boundary must be one of {list(rc.BOUNDARIES)}")
    _, _, stamp = await readiness.current(access.project_id)
    engine_inputs = {**body.inputs, "valuation_boundary": body.valuation_boundary, "scenario": body.scenario,
                     "provenance_inputs": {"tea_case": body.tea_case, "assumptions": body.assumptions}}
    input_versions = {**(body.input_versions or {}), **({"chain": chain} if chain else {})} or None
    result = (await _call_model("/returns/calculate", method="POST", json_data=engine_inputs,
                                request=request))["returns"]
    cid = rc.case_id(access.project_id, body.case_name)
    previous = next((v for v in reversed(_versions(access.project_id, access.owner_tenant))
                     if v["case_id"] == cid), None)
    record = rc.new_version(
        project_id=access.project_id, owner_tenant_id=access.owner_tenant, case_name=body.case_name,
        previous=previous, engine_result=result, inputs=engine_inputs, readiness=stamp,
        tea_case=body.tea_case, input_versions=input_versions,
        governance={"published_from": "PF engine", "readiness": stamp,
                    "basis": "OWNER_PUBLISHED_FROM_CHAIN" if chain else "OWNER_PUBLISHED",
                    "validity": rc.VALIDITY},
        published_by=access.user_id or payload.get("user_id") or "owner")
    stored = _insert(access.owner_tenant, record)
    try:
        from app.core.event_store import append_event
        append_event(event_type="returns_case.published", aggregate_type="project", aggregate_id=access.project_id,
                     data={"version_id": stored["version_id"], "case_id": stored["case_id"],
                           "version_number": stored["version_number"], "content_sha256": stored["content_sha256"]},
                     user_id=access.user_id)
    except Exception:  # noqa: BLE001 — the version stands; the trace failure is logged by the store
        pass
    return {**rc.disclose(stored, full=True), "review": await _review(stored, access.owner_tenant)}


@router.get("/{project_id}")
async def list_cases(project_id: str, request: Request, response: Response):
    _no_store(response)
    _payload(request)
    access = pre_fid_access.resolve(request, project_id)
    full = access.basis == "owner"
    versions = _versions(access.project_id, access.owner_tenant)
    withdrawn = _withdrawals(access.project_id, access.owner_tenant)
    if not full:
        shared_v, shared_c = _returns_shares(access)
        versions = [v for v in versions if v["version_id"] not in withdrawn
                    and rc.readable_by_share(v, shared_v, shared_c)]
        if not versions:
            raise HTTPException(status_code=403, detail={
                "code": "RETURNS_NOT_SHARED",
                "message": "No returns case of this project has been shared with you. You may run the "
                           "calculator on inputs you enter yourself; they are not the owner's case."})
    out = []
    for v in versions:
        out.append({**rc.identity(v), "review": await _review(v, access.owner_tenant),
                    "withdrawal": withdrawn.get(v["version_id"])})
    return {"project_id": access.project_id, "disclosure": "OWNER" if full else "RETURNS_SHARE", "versions": out}


async def _one(project_id: str, version_id: str, request: Request) -> dict:
    _payload(request)
    access = pre_fid_access.resolve(request, project_id)
    version = next((v for v in _versions(access.project_id, access.owner_tenant)
                    if v["version_id"] == version_id), None)
    full = access.basis == "owner"
    withdrawn = _withdrawals(access.project_id, access.owner_tenant)
    if version is not None and not full:
        shared_v, shared_c = _returns_shares(access)
        if version["version_id"] in withdrawn or not rc.readable_by_share(version, shared_v, shared_c):
            version = None
            pre_fid_access._audit(allowed=False, user_id=access.user_id, project_id=access.project_id,
                                  basis=access.basis, route="returns_case", reason=f"version={version_id}")
    if version is None:
        raise HTTPException(status_code=403 if not full else 404, detail={
            "code": "RETURNS_NOT_SHARED" if not full else "NO_SUCH_VERSION",
            "message": "This returns case has not been shared with you." if not full else "No such case version."})
    return {**rc.disclose(version, full=full, devex_sections=access.sections),
            "review": await _review(version, access.owner_tenant),
            "withdrawal": withdrawn.get(version["version_id"])}


@router.get("/{project_id}/versions/{version_id}")
async def read_version(project_id: str, version_id: str, request: Request, response: Response):
    _no_store(response)
    return await _one(project_id, version_id, request)


@router.get("/{project_id}/versions/{version_id}/export")
async def export_version(project_id: str, version_id: str, request: Request, response: Response):
    """The same disclosure as the screen, as a file. It cites the version; it
    never recomputes it."""
    _no_store(response)
    body = await _one(project_id, version_id, request)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="returns-case-{project_id}-v{body["identity"]["version_number"]}.json"')
    return {"export": "returns_case", "exported_at": rc.now_iso(), **body}


def _share_row(row: dict) -> dict:
    target = row["capability"][len(rc.CAPABILITY_PREFIX):]
    return {"entitlement_id": row["entitlement_id"], "user_id": row["user_id"],
            "version_id": None if target.endswith(rc.LATEST) else target,
            "case_id": target[:-len(rc.LATEST)] if target.endswith(rc.LATEST) else None,
            "granted_by": row["granted_by"], "granted_at": row["granted_at"], "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"], "status": row["status"]}


@router.get("/{project_id}/audience-templates")
def audience_templates(project_id: str, request: Request, response: Response):
    """Suggestions for the owner when sharing. They grant nothing (task 10)."""
    _no_store(response)
    _require_owner_finance(request, project_id)
    from app.core.audience_templates import suggestions
    return suggestions()


@router.get("/{project_id}/shares")
def list_shares(project_id: str, request: Request, response: Response):
    _no_store(response)
    access, _ = _require_owner_finance(request, project_id)
    rows = ent.list_entitlements(project_id=access.project_id)
    return {"project_id": access.project_id,
            "shares": [_share_row(r) for r in rows if r["capability"].startswith(rc.CAPABILITY_PREFIX)]}


@router.post("/{project_id}/shares", status_code=201)
def create_share(project_id: str, body: ShareRequest, request: Request, response: Response):
    _no_store(response)
    access, _ = _require_owner_finance(request, project_id)
    if not body.user_id.strip():
        raise HTTPException(status_code=422, detail="user_id is required")
    versions = _versions(access.project_id, access.owner_tenant)
    if body.version_id and not any(v["version_id"] == body.version_id for v in versions):
        raise HTTPException(status_code=404, detail="No such case version on this project")
    if body.version_id and body.version_id in _withdrawals(access.project_id, access.owner_tenant):
        raise HTTPException(status_code=409, detail={"code": "VERSION_WITHDRAWN",
                            "message": "This version is withdrawn from reliance and cannot be shared."})
    if body.case_id and not any(v["case_id"] == body.case_id for v in versions):
        raise HTTPException(status_code=404, detail="No such case on this project")
    try:
        cap = rc.share_capability(version_id=body.version_id, case=body.case_id)
        expiry = normalise_expiry(body.expires_at)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    row = ent.grant_entitlement(user_id=body.user_id.strip(), project_id=access.project_id,
                                granted_by=access.user_id or "owner", capability=cap,
                                reason=body.reason, expires_at=expiry)
    return {"share": _share_row(row),
            "note": "Read-only. RETURNS discloses this case's results only: no funding, packages, evidence "
                    "or dated pre-FID figure."}


@router.delete("/{project_id}/shares/{entitlement_id}")
def revoke_share(project_id: str, entitlement_id: str, request: Request, response: Response):
    _no_store(response)
    access, _ = _require_owner_finance(request, project_id)
    row = ent.get_entitlement(entitlement_id)
    if not row or row["project_id"] != access.project_id or not row["capability"].startswith(rc.CAPABILITY_PREFIX):
        raise HTTPException(status_code=404, detail="No such returns share on this project")
    return _share_row(ent.revoke_entitlement(entitlement_id, revoked_by=access.user_id or "owner"))


# ── Withdrawal from reliance (migration 125; JML 18 Nov 2026) ─────────────────

class WithdrawRequest(BaseModel):
    reason: str = Field(..., min_length=10)


def _withdrawals(project_id: str, tenant: str) -> dict:
    """{version_id: withdrawal} for the project. Unreadable is 'unavailable', never 'none'."""
    try:
        conn = _conn(tenant)
        try:
            rows = conn.execute("SELECT * FROM returns_case_withdrawal WHERE project_id = ?", [project_id]).fetchall()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise pre_fid_access.unavailable("The withdrawals of published returns cases") from exc
    out = {}
    for r in rows:
        d = dict(r)
        d["withdrawn_at"] = str(d["withdrawn_at"])
        if isinstance(d.get("shares_revoked"), str):
            d["shares_revoked"] = json.loads(d["shares_revoked"])
        out[d["version_id"]] = d
    return out


def _insert_withdrawal(tenant: str, row: dict) -> None:
    conn = _conn(tenant)
    try:
        conn.execute("INSERT INTO returns_case_withdrawal (version_id, project_id, owner_tenant_id, reason, "
                     "withdrawn_by, shares_revoked) VALUES (?,?,?,?,?,?)",
                     [row["version_id"], row["project_id"], row["owner_tenant_id"], row["reason"],
                      row["withdrawn_by"], json.dumps(row["shares_revoked"])])
        conn.commit()
    finally:
        conn.close()


@router.post("/{project_id}/versions/{version_id}/withdraw", status_code=201)
def withdraw_version(project_id: str, version_id: str, body: WithdrawRequest, request: Request,
                     response: Response):
    """Withdraw one version from reliance: revoke every active share that names it,
    then record the withdrawal. The version itself is unchanged and stays readable
    by its owner, marked withdrawn; nobody else reads it any more."""
    _no_store(response)
    access, payload = _require_owner_finance(request, project_id)
    if not any(v["version_id"] == version_id for v in _versions(access.project_id, access.owner_tenant)):
        raise HTTPException(status_code=404, detail="No such case version on this project")
    if version_id in _withdrawals(access.project_id, access.owner_tenant):
        raise HTTPException(status_code=409, detail={"code": "ALREADY_WITHDRAWN",
                                                     "message": "This version is already withdrawn."})
    target = rc.share_capability(version_id=version_id)
    revoked = []
    for row in ent.list_entitlements(project_id=access.project_id):
        if row["capability"] == target and row["status"] == "active":
            ent.revoke_entitlement(row["entitlement_id"], revoked_by=access.user_id or "owner")
            revoked.append({"entitlement_id": row["entitlement_id"], "user_id": row["user_id"]})
    _insert_withdrawal(access.owner_tenant, {
        "version_id": version_id, "project_id": access.project_id, "owner_tenant_id": access.owner_tenant,
        "reason": body.reason.strip(), "withdrawn_by": access.user_id or payload.get("user_id") or "owner",
        "shares_revoked": revoked})
    try:
        from app.core.event_store import append_event
        append_event(event_type="returns_case.withdrawn", aggregate_type="project", aggregate_id=access.project_id,
                     data={"version_id": version_id, "shares_revoked": revoked}, user_id=access.user_id)
    except Exception:  # noqa: BLE001 — the withdrawal stands; the trace failure is logged by the store
        pass
    return {"withdrawal": _withdrawals(access.project_id, access.owner_tenant)[version_id],
            "note": "Withdrawn from reliance. Access is revoked; copies already obtained cannot be recalled. "
                    "Tell each recipient through an authorised communication."}
