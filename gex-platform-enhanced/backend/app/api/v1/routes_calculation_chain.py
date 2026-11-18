"""
The calculation chain — saved cost basis -> reviewed TEA -> financing -> returns (JML, 18 Nov).
==============================================================================================
Three prefixes, because three different functions act (domain_authorization):

  /api/v1/cost-basis/{project_id}            projects domain (engineering acts)
     POST   /                                 save the current Cost Basis configuration
     POST   /{version_id}/tea                 run the TEA priced from that saved version
  /api/v1/tea-review/{project_id}            verification domain (the reviewer acts)
     POST   /{claim_id}                       review a TEA base case run from a cost basis
  /api/v1/calculation-chain/{project_id}     finance domain (the owner's finance acts)
     GET    /                                 the whole chain, as recorded
     POST   /financing                        save a financing case on a reviewed TEA
     POST   /returns                          publish a returns version built from the chain

Rules: core/calculation_chain.py. Only the owner company writes (and GEX staff
read). The reviewer is an appointed independent engineer or the owner's finance
or executive function, never the person who saved the cost basis or ran the TEA.
Every response is no-store. Nothing here is shown to a shared reader: a bank
reads the returns version, which cites these records by id and hash.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.v1.routes_plant_builder import PlantConfigRequest, _equipment_to_dict, _serialize_result
from app.api.v1.routes_tea import ApprovalRequest, ComputeRequest, apply_approval, get_db, run_compute
from app.core import calculation_chain as cc
from app.core import pre_fid_access
from app.core.request_tenant import payload_from_request

cost_basis_router = APIRouter(prefix="/api/v1/cost-basis", tags=["calculation-chain"])
review_router = APIRouter(prefix="/api/v1/tea-review", tags=["calculation-chain"])
chain_router = APIRouter(prefix="/api/v1/calculation-chain", tags=["calculation-chain"])

_JSON = ("configuration", "result", "terms", "review_conditions", "tea_inputs")


# ── plumbing ───────────────────────────────────────────────────────────────────

def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _refuse(e: cc.ChainError, status: int = 409) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": e.code, "message": e.message})


def _owner(request: Request, project_id: str, functions: frozenset) -> tuple[pre_fid_access.Access, dict]:
    payload = payload_from_request(request) or {}
    if not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Authentication required")
    access = pre_fid_access.resolve(request, project_id)
    if access.basis != "owner" or payload.get("business_function") not in functions:
        raise HTTPException(status_code=403, detail={
            "code": "OWNER_ONLY",
            "message": "Only the project owner's " + ", ".join(sorted(f.lower() for f in functions))
                       + " function acts on its calculation chain."})
    return access, payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r) -> dict:
    d = dict(r)
    for k in _JSON:
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    for k in ("saved_at",):
        if d.get(k) is not None:
            d[k] = str(d[k])
    return d


def _conn(tenant: str):
    from app.core.db_backend import domain_connection, domain_is_postgres, require_postgres
    require_postgres(domain_is_postgres(), "The calculation chain", "DOMAIN_DB_BACKEND")
    return domain_connection(company_id=tenant)


def _read(table: str, project_id: str, tenant: str) -> list[dict]:
    conn = _conn(tenant)
    try:
        rows = conn.execute(f"SELECT * FROM {table} WHERE project_id = ? ORDER BY version_number",
                            [project_id]).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def _one(table: str, project_id: str, tenant: str, version_id: str) -> dict:
    found = next((v for v in _read(table, project_id, tenant) if v["version_id"] == version_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No such {table.replace('_', ' ')} on this project")
    return found


def _insert(table: str, tenant: str, record: dict) -> dict:
    cols = list(record)
    conn = _conn(tenant)
    try:
        conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                     [json.dumps(record[c]) if c in _JSON else record[c] for c in cols])
        conn.commit()
        return _row(conn.execute(f"SELECT * FROM {table} WHERE version_id = ?", [record["version_id"]]).fetchone())
    finally:
        conn.close()


def _base_case(db, claim_id: str, project_id: str) -> dict:
    row = db.execute("SELECT * FROM model_base_case WHERE claim_id=? AND project_id=?",
                     (claim_id, project_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No such TEA base case on this project")
    return _row(row)


def _event(event_type: str, project_id: str, user_id: Optional[str], data: dict) -> None:
    try:
        from app.core.event_store import append_event
        append_event(event_type=event_type, aggregate_type="project", aggregate_id=project_id,
                     data=data, user_id=user_id)
    except Exception:  # noqa: BLE001 — the record stands; the trace failure is logged by the store
        pass


# ── 1. Save a cost basis ───────────────────────────────────────────────────────

@cost_basis_router.post("/{project_id}", status_code=201)
def save_cost_basis(project_id: str, body: PlantConfigRequest, request: Request, response: Response):
    """The server recomputes the result from the configuration and stores both."""
    _no_store(response)
    from app.core.plant_builder import (EQUIPMENT_CATALOG, CapacityFactorRequired, PlantConfiguration,
                                        get_plant_builder)

    access, payload = _owner(request, project_id, cc.COST_BASIS_FUNCTIONS)
    configuration = {**body.model_dump(exclude={"project_id", "equipment"}),
                     "equipment": _equipment_to_dict(body.equipment)}
    catalogue = {i.id: i for i in EQUIPMENT_CATALOG}
    unknown = [e["equipment_id"] for e in configuration["equipment"] if e["equipment_id"] not in catalogue]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown equipment: {', '.join(unknown)}")
    try:
        result = get_plant_builder().build(PlantConfiguration(
            project_id=access.project_id, molecule=body.molecule, location_jurisdiction=body.location_jurisdiction,
            equipment=configuration["equipment"], power_price_eur_mwh=body.power_price_eur_mwh,
            water_price_eur_m3=body.water_price_eur_m3, labour_count=body.labour_count,
            labour_cost_eur_year=body.labour_cost_eur_year, insurance_pct_capex=body.insurance_pct_capex,
            contingency_pct=body.contingency_pct, target_market_price_eur_t=body.target_market_price_eur_t,
            wacc_pct=body.wacc_pct, project_life_years=body.project_life_years,
            capacity_factor=body.capacity_factor))
        product = cc.product_output(configuration, catalogue)
    except CapacityFactorRequired as e:
        raise HTTPException(status_code=422, detail=str(e))
    except cc.ChainError as e:
        raise _refuse(e, 422)
    versions = _read("cost_basis_version", access.project_id, access.owner_tenant)
    record = cc.cost_basis_record(
        project_id=access.project_id, owner_tenant=access.owner_tenant, configuration=configuration,
        result=_serialize_result(result), product=product, catalogue_hash=cc.catalogue_sha256(EQUIPMENT_CATALOG),
        previous=versions[-1] if versions else None, saved_by=access.user_id,
        saved_by_function=payload.get("business_function"))
    stored = _insert("cost_basis_version", access.owner_tenant, record)
    _event("cost_basis.saved", access.project_id, access.user_id,
           {"version_id": stored["version_id"], "version_number": stored["version_number"],
            "content_sha256": stored["content_sha256"]})
    return stored


# ── 2. TEA from a saved cost basis ─────────────────────────────────────────────

class TeaFromCostBasis(BaseModel):
    model_config = {"extra": "forbid"}
    pathway_id: Optional[str] = None
    # Stated by whoever runs the TEA, each with its basis (core/calculation_chain.tea_request).
    stated: dict = Field(default_factory=dict)


def _fuel_id(molecule: str) -> str:
    """The fuel catalogue's id for the cost basis molecule (its id or a legacy alias)."""
    from app.core.db_backend import domain_connection
    conn = domain_connection()
    try:
        rows = conn.execute("SELECT fuel_id, legacy_aliases_json FROM fuel_catalog WHERE is_active = 1").fetchall()
    finally:
        conn.close()
    for r in rows:
        if molecule == r["fuel_id"] or molecule in json.loads(r["legacy_aliases_json"] or "[]"):
            return r["fuel_id"]
    raise HTTPException(status_code=422, detail={"code": "FUEL_NOT_IN_CATALOGUE",
                                                 "message": f"'{molecule}' is not in the fuel catalogue."})


@cost_basis_router.post("/{project_id}/{version_id}/tea", status_code=201)
async def tea_from_cost_basis(project_id: str, version_id: str, body: TeaFromCostBasis, request: Request,
                              response: Response, db: Any = Depends(get_db)):
    _no_store(response)
    access, _ = _owner(request, project_id, cc.COST_BASIS_FUNCTIONS)
    cb = _one("cost_basis_version", access.project_id, access.owner_tenant, version_id)
    try:
        tea_body = cc.tea_request(cb, fuel_id=_fuel_id(cb["molecule"]),
                                  pathway_id=body.pathway_id or f"{access.project_id}:cost-basis",
                                  stated=body.stated)
    except cc.ChainError as e:
        raise _refuse(e, 422)
    out = await run_compute(access.project_id, request, ComputeRequest(**tea_body), db,
                            link={"cost_basis_version_id": cb["version_id"],
                                  "cost_basis_sha256": cb["content_sha256"], "run_by": access.user_id})
    base = _row(db.execute("SELECT * FROM model_base_case WHERE claim_id=?",
                           (out["base_case"]["claim_id"],)).fetchone())
    return {**out, "base_case": base, "tea_request": tea_body,
            "reconciliation": cc.cost_basis_vs_tea(cb, base)}


# ── 3. Review ──────────────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    outcome: str = Field(..., description="approve | approve_with_conditions | reject")
    conditions: list[str] = []


def _appointed_ie(user_id: str, project_id: str) -> bool:
    from app.core.projects_store import _rows
    return bool(_rows("SELECT 1 FROM auth_user_project_roles WHERE user_id = :u AND project_id = :p "
                      "AND actor_type = 'INDEPENDENT_ENGINEER'", {"u": user_id, "p": project_id}))


@review_router.post("/{project_id}/{claim_id}")
def review_tea(project_id: str, claim_id: str, body: ReviewRequest, request: Request, response: Response,
               db: Any = Depends(get_db)):
    _no_store(response)
    payload = payload_from_request(request) or {}
    access = pre_fid_access.resolve(request, project_id)
    if body.outcome not in cc.REVIEW_OUTCOMES:
        raise HTTPException(status_code=422, detail=f"outcome must be one of {list(cc.REVIEW_OUTCOMES)}")
    if body.outcome == "approve_with_conditions" and not [c for c in body.conditions if c.strip()]:
        raise HTTPException(status_code=422, detail="State the conditions.")
    base = _base_case(db, claim_id, access.project_id)
    if not base.get("cost_basis_version_id"):
        raise _refuse(cc.ChainError("TEA_NOT_FROM_COST_BASIS", "This base case was not priced from a saved "
                                    "cost basis; review it on the TEA screen."))
    cb = _one("cost_basis_version", access.project_id, access.owner_tenant, base["cost_basis_version_id"])
    try:
        standing = cc.review_standing(
            reviewer=payload, run_by=base.get("run_by"), cost_basis_saved_by=cb["saved_by"],
            owner_tenant=access.owner_tenant,
            appointed_ie=bool(payload.get("user_id")) and _appointed_ie(payload["user_id"], access.project_id))
    except cc.ChainError as e:
        raise _refuse(e, 403)
    checks = cc.cost_basis_vs_tea(cb, base)
    if body.outcome == "approve" and cc.failed(checks):
        raise _refuse(cc.ChainError("CHECKS_FAILED", "These checks fail: " + "; ".join(cc.failed(checks))
                                    + ". Approve with conditions or reject."), 409)
    reviewed_at = _now()
    out = apply_approval(db.execute("SELECT * FROM model_base_case WHERE claim_id=?", (claim_id,)).fetchone(),
                         ApprovalRequest(approved_by=payload["user_id"], outcome=body.outcome,
                                         conditions=body.conditions,
                                         approver_role="independent_engineer" if standing == "INDEPENDENT"
                                         else "owner_internal_review"),
                         db, review={"review_basis": standing,
                                     "reviewed_by_company": payload.get("company_id"),
                                     "reviewed_at": reviewed_at, "review_conditions": body.conditions})
    base = _row(out["base_case"])
    _event("tea_base_case.reviewed", access.project_id, payload["user_id"],
           {"claim_id": claim_id, "outcome": body.outcome, "review_basis": standing})
    return {**out, "base_case": base, "review_basis": standing,
            "review_label": "Independent review" if standing == "INDEPENDENT"
            else "Owner's internal review — not independent",
            "reconciliation": cc.cost_basis_vs_tea(cb, base)}


# ── 4. Financing case ──────────────────────────────────────────────────────────

class Term(BaseModel):
    value: float
    source: str
    verification_status: Optional[str] = None


class FinancingRequest(BaseModel):
    tea_claim_id: str
    terms: dict[str, Term]


@chain_router.post("/{project_id}/financing", status_code=201)
def save_financing(project_id: str, body: FinancingRequest, request: Request, response: Response,
                   db: Any = Depends(get_db)):
    _no_store(response)
    from app.core.devex_share import PRODUCER_FUNCTIONS
    access, _ = _owner(request, project_id, PRODUCER_FUNCTIONS)
    base = _base_case(db, body.tea_claim_id, access.project_id)
    if not base.get("review_basis"):
        raise _refuse(cc.ChainError("TEA_NOT_REVIEWED", "This TEA base case has no review on the calculation "
                                    "chain. Review it first."))
    versions = _read("financing_case_version", access.project_id, access.owner_tenant)
    try:
        record = cc.financing_record(project_id=access.project_id, owner_tenant=access.owner_tenant,
                                     base_case=base, terms={k: v.model_dump() for k, v in body.terms.items()},
                                     previous=versions[-1] if versions else None, saved_by=access.user_id)
    except cc.ChainError as e:
        raise _refuse(e)
    stored = _insert("financing_case_version", access.owner_tenant, record)
    _event("financing_case.saved", access.project_id, access.user_id,
           {"version_id": stored["version_id"], "content_sha256": stored["content_sha256"]})
    return stored


# ── 5. Returns from the chain ──────────────────────────────────────────────────

class ChainReturnsRequest(BaseModel):
    financing_version_id: str
    case_name: str = Field(..., min_length=1)
    scenario: str = "BASE"
    valuation_boundary: str = "FULL_PROJECT"
    stated: dict[str, Any] = Field(..., description="{field: {value, source, verification_status}}")


def _approved_gearing() -> Optional[dict]:
    try:
        from app.core.db_backend import domain_connection
        conn = domain_connection()
        try:
            r = conn.execute("SELECT ref_id, value_base, source_name FROM reference_parameter WHERE "
                             "parameter_key = 'debt_gearing' AND state = 'approved' ORDER BY valid_from DESC "
                             "LIMIT 1").fetchone()
        finally:
            conn.close()
        return {"ref_id": r["ref_id"], "value": r["value_base"], "source": r["source_name"]} if r else None
    except Exception:  # noqa: BLE001 — the check says it could not be read
        return None


def _project_capex(project_id: str) -> Optional[float]:
    from app.core.projects_store import _rows
    rows = _rows("SELECT capex_eur FROM projects WHERE project_id = :p", {"p": project_id})
    return float(rows[0]["capex_eur"]) if rows and rows[0]["capex_eur"] is not None else None


@chain_router.post("/{project_id}/returns", status_code=201)
async def publish_from_chain(project_id: str, body: ChainReturnsRequest, request: Request, response: Response,
                             db: Any = Depends(get_db)):
    _no_store(response)
    from app.api.v1.routes_returns_cases import PublishRequest, publish_version
    from app.core.devex_share import PRODUCER_FUNCTIONS
    access, payload = _owner(request, project_id, PRODUCER_FUNCTIONS)
    fin = _one("financing_case_version", access.project_id, access.owner_tenant, body.financing_version_id)
    base = _base_case(db, fin["tea_claim_id"], access.project_id)
    if not base.get("review_basis"):
        raise _refuse(cc.ChainError("TEA_NOT_REVIEWED", "The TEA base case has no review on the chain."))
    cb = _one("cost_basis_version", access.project_id, access.owner_tenant, base["cost_basis_version_id"])
    from app.api.v1.routes_returns_cases import _versions, _withdrawals
    from app.core import returns_cases as rc
    cid = rc.case_id(access.project_id, body.case_name)
    prior = [v for v in _versions(access.project_id, access.owner_tenant) if v["case_id"] == cid]
    previous = None
    if prior:
        previous = {**prior[-1], "withdrawal": _withdrawals(access.project_id, access.owner_tenant).get(
            prior[-1]["version_id"])}
    try:
        built = cc.returns_inputs(cost_basis=cb, base_case=base, financing=fin,
                                  stated={k: dict(v) for k, v in body.stated.items()},
                                  project_capex_eur=_project_capex(access.project_id),
                                  approved_gearing=_approved_gearing(), previous=previous)
    except cc.ChainError as e:
        raise _refuse(e)
    tea_case = {"claim_id": base["claim_id"], "pathway_id": base.get("pathway_id"),
                "cost_basis_hash": base["cost_basis_hash"], "state": base["state"],
                "review_basis": base["review_basis"]}
    pub = PublishRequest(case_name=body.case_name, scenario=body.scenario, valuation_boundary=body.valuation_boundary,
                         inputs=built["inputs"], tea_case=tea_case, assumptions=built["remaining_assumptions"])
    return await publish_version(access, payload, request, pub,
                                 chain={k: built[k] for k in ("source_versions", "checks", "remaining_assumptions",
                                                              "reconciliation_vs_previous") if k in built})


# ── The chain, as recorded ─────────────────────────────────────────────────────

@chain_router.get("/{project_id}")
def read_chain(project_id: str, request: Request, response: Response, db: Any = Depends(get_db)):
    _no_store(response)
    payload = payload_from_request(request) or {}
    access = pre_fid_access.resolve(request, project_id)
    reviewer = (access.basis not in ("owner", "platform_admin") and bool(payload.get("user_id"))
                and _appointed_ie(payload["user_id"], access.project_id))
    if access.basis not in ("owner", "platform_admin") and not reviewer:
        raise HTTPException(status_code=403, detail={
            "code": "OWNER_ONLY", "message": "The calculation chain is the owner's. A shared reader sees the "
                                             "returns version, which cites it."})
    from app.core.plant_builder import EQUIPMENT_CATALOG
    catalogue = {i.id: i for i in EQUIPMENT_CATALOG}
    cbs = _read("cost_basis_version", access.project_id, access.owner_tenant)
    for c in cbs:
        c["outputs_by_molecule"] = cc.outputs_by_molecule(c, catalogue)
    bases = [_row(r) for r in db.execute(
        "SELECT * FROM model_base_case WHERE project_id=? AND cost_basis_version_id IS NOT NULL "
        "ORDER BY created_at", (access.project_id,)).fetchall()]
    by_cb = {c["version_id"]: c for c in cbs}
    for b in bases:
        cb = by_cb.get(b["cost_basis_version_id"])
        b["reconciliation"] = cc.cost_basis_vs_tea(cb, b) if cb else []
        b["failed_checks"] = cc.failed(b["reconciliation"])
        b["can_review"] = (b["state"] == "submitted" and payload.get("user_id") not in
                           {b.get("run_by"), cb and cb["saved_by"]}
                           and (reviewer or (payload.get("business_function") in cc.OWNER_REVIEW_FUNCTIONS
                                             and access.basis == "owner")))
        b["review_would_be"] = ("INDEPENDENT" if reviewer else "OWNER_INTERNAL") if b["can_review"] else None
    if reviewer:
        return {"project_id": access.project_id, "project_name": access.project_name, "cost_bases": cbs,
                "tea_base_cases": bases, "financing_cases": [], "returns_versions": [],
                "viewer": {"user_id": payload.get("user_id"), "business_function": payload.get("business_function"),
                           "is_owner": False, "is_appointed_reviewer": True},
                "withheld": "Financing and returns are the owner's; a reviewer sees the cost bases and TEA runs."}
    fins = _read("financing_case_version", access.project_id, access.owner_tenant)
    from app.api.v1.routes_returns_cases import _versions
    from app.core import returns_cases as rc
    from app.api.v1.routes_returns_cases import _withdrawals
    withdrawn = _withdrawals(access.project_id, access.owner_tenant)
    returns = [{**rc.identity(v), "chain": (v.get("input_versions") or {}).get("chain"),
                "withdrawal": withdrawn.get(v["version_id"])}
               for v in _versions(access.project_id, access.owner_tenant)
               if (v.get("input_versions") or {}).get("chain")]
    return {"project_id": access.project_id, "project_name": access.project_name, "cost_bases": cbs,
            "tea_base_cases": bases, "financing_cases": fins, "returns_versions": returns,
            "viewer": {"user_id": payload.get("user_id"), "business_function": payload.get("business_function"),
                       "is_owner": access.basis == "owner"}}
