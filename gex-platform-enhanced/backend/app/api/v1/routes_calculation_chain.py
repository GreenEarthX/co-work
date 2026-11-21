"""
The calculation chain — saved cost basis -> reviewed TEA -> financing -> returns (JML, 18 Nov).
==============================================================================================
Three prefixes, because three different functions act (domain_authorization):

  /api/v1/cost-basis/{project_id}            projects domain (engineering acts)
     POST   /                                 save the current Cost Basis configuration
     POST   /{version_id}/tea                 run the TEA priced from that saved version
     GET    /workbook/template                the Cost Basis + TEA workbook (filled from the latest version)
     POST   /workbook/preview                 read a filled workbook: report, changes, nothing saved
     POST   /workbook/commit                  save exactly the previewed file as the next cost basis
  /api/v1/tea-review/{project_id}            verification domain (the reviewer acts)
     POST   /{claim_id}                       review a TEA base case run from a cost basis
  /api/v1/calculation-chain/{project_id}     finance domain (the owner's finance acts)
     GET    /                                 the whole chain, as recorded
     GET    /tea/{claim_id}/workbook          the published TEA case as a frozen workbook
     GET    /tea/{claim_id}/openpytea-config  the exact OpenPyTEA config of that run
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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from app.api.v1.routes_plant_builder import PlantConfigRequest, _equipment_to_dict, _serialize_result
from app.api.v1.routes_tea import ApprovalRequest, ComputeRequest, apply_approval, get_db, run_compute
from app.core import calculation_chain as cc
from app.core import cost_workbook as cw
from app.core import pre_fid_access
from app.core.request_tenant import payload_from_request

cost_basis_router = APIRouter(prefix="/api/v1/cost-basis", tags=["calculation-chain"])
review_router = APIRouter(prefix="/api/v1/tea-review", tags=["calculation-chain"])
chain_router = APIRouter(prefix="/api/v1/calculation-chain", tags=["calculation-chain"])

_JSON = ("configuration", "result", "terms", "review_conditions", "tea_inputs", "limitations", "open_issues",
         "declared", "funding_plan")


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


def _insert_many(tenant: str, rows: list[tuple[str, dict]]) -> dict:
    """Insert several records in ONE transaction: all or none (19 Nov: a financing case and the
    workbook import that declared beside it are never left half-written). Returns the first."""
    conn = _conn(tenant)
    try:
        for table, record in rows:
            cols = list(record)
            conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                         [json.dumps(record[c]) if c in _JSON else record[c] for c in cols])
        table, record = rows[0]
        first = _row(conn.execute(f"SELECT * FROM {table} WHERE version_id = ?", [record["version_id"]]).fetchone())
        conn.commit()
        return first
    except Exception:
        conn.rollback()
        raise
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


# ── 1b. The workbook: template, preview, commit ───────────────────────────────
# One workbook, four tabs (Cost Basis, TEA inputs, Financing, Offtake). The preview reads
# them all and writes nothing; each tab is saved on its own call, by the function that may
# act on it, from exactly the previewed file.

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OFFTAKE_FUNCTIONS = frozenset({"COMMERCIAL", "FINANCE_TREASURY", "EXECUTIVE"})


def _financing_functions() -> frozenset:
    from app.core.devex_share import PRODUCER_FUNCTIONS
    return PRODUCER_FUNCTIONS


def _workbook_functions() -> frozenset:
    return cc.COST_BASIS_FUNCTIONS | OFFTAKE_FUNCTIONS | _financing_functions()


def _catalogue() -> dict:
    from app.core.plant_builder import EQUIPMENT_CATALOG
    return {i.id: i for i in EQUIPMENT_CATALOG}


def _xlsx(data: bytes, name: str) -> Response:
    return Response(content=data, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


def _imports(project_id: str, tenant: str, tab: str) -> list[dict]:
    conn = _conn(tenant)
    try:
        rows = conn.execute("SELECT * FROM workbook_import WHERE project_id = ? AND tab = ? ORDER BY imported_at",
                            [project_id, tab]).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("declared"), str):
            d["declared"] = json.loads(d["declared"])
        out.append(d)
    return out


def _import_row(access, tab: str, parsed: dict, target_kind: str, target_ref: str,
                target_sha256: Optional[str], declared: dict) -> dict:
    import uuid
    return {"import_id": str(uuid.uuid4()), "project_id": access.project_id, "owner_tenant_id": access.owner_tenant,
            "tab": tab, "template_version": parsed["template_version"], "file_sha256": parsed["file_sha256"],
            "target_kind": target_kind, "target_ref": target_ref, "target_sha256": target_sha256,
            "declared": declared, "imported_by": access.user_id}


def _insert_import(conn, row: dict) -> None:
    cols = list(row)
    conn.execute(f"INSERT INTO workbook_import ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                 [json.dumps(row[c]) if c == "declared" else row[c] for c in cols])


def _offtake_card(project_id: str) -> dict:
    from app.api.v1.routes_bankability_proxy import _get_db
    from app.core.contract_tokens import card_view
    conn = _get_db()
    try:
        return (card_view(project_id, conn=conn).get("offtake") or {}).get("terms") or {}
    finally:
        conn.close()


def _reviewed_runs(db, project_id: str) -> list[dict]:
    return [_row(r) for r in db.execute(
        "SELECT * FROM model_base_case WHERE project_id=? AND state='verified' AND review_basis='INDEPENDENT' "
        "AND cost_basis_version_id IS NOT NULL ORDER BY created_at", (project_id,)).fetchall()]


@cost_basis_router.get("/{project_id}/workbook/template")
def workbook_template(project_id: str, request: Request, blank: bool = False, db: Any = Depends(get_db)):
    from app.core import finance_workbook as fw
    from app.core.contract_tokens import terms_hash
    access, _ = _owner(request, project_id, _workbook_functions())
    if blank:
        data = cw.template(_catalogue(), project_id=access.project_id, project_name=access.project_name or "")
        return _xlsx(data, f"GEX_workbook_{access.project_id}_blank.xlsx")
    cbs = _read("cost_basis_version", access.project_id, access.owner_tenant)
    fins = _read("financing_case_version", access.project_id, access.owner_tenant)
    fin_decl = next((i["declared"] for i in reversed(_imports(access.project_id, access.owner_tenant, "financing"))
                     if fins and i["target_ref"] == fins[-1]["version_id"]), None)
    if fins and fin_decl is None:
        # a version saved on the screen carries no declaration: keep the case's last declared stack
        fin_decl = next((i["declared"] for i in reversed(_imports(access.project_id, access.owner_tenant, "financing"))
                         if (i["declared"] or {}).get("case_id") == fins[-1]["case_id"]), None)
    runs = _reviewed_runs(db, access.project_id)
    card = _offtake_card(access.project_id)
    off_decl = next((i["declared"] for i in reversed(_imports(access.project_id, access.owner_tenant, "offtake"))
                     if card and i["target_sha256"] == terms_hash(card)), None)
    data = cw.template(_catalogue(), project_id=access.project_id, project_name=access.project_name or "",
                       cost_basis=cbs[-1] if cbs else None,
                       financing=fw.fill_financing(fins[-1] if fins else None, fin_decl,
                                                   runs[-1]["claim_id"] if runs else None),
                       offtake=fw.fill_offtake(card, off_decl))
    suffix = f"cb-v{cbs[-1]['version_number']}" if cbs else "current"
    return _xlsx(data, f"GEX_workbook_{access.project_id}_{suffix}.xlsx")


async def _parse_upload(file: UploadFile, access, db) -> dict:
    """Every tab, with what saving it would change and what would refuse it. Writes nothing."""
    from app.core.contract_tokens import terms_hash
    data = await file.read(cw.MAX_BYTES + 1)
    catalogue = _catalogue()
    try:
        parsed = cw.parse_all(data, catalogue=catalogue, project_id=access.project_id)
    except cw.WorkbookError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": e.message})
    tabs = parsed["tabs"]

    cb = tabs["cost_basis"]
    cbs = _read("cost_basis_version", access.project_id, access.owner_tenant)
    if cb["provided"]:
        cb["versus_current"] = cw.versus_current(cbs[-1] if cbs else None, cb["configuration"])
        cb["_previous"] = cbs[-1] if cbs else None
        if cb["can_commit"]:
            try:
                cb["result_preview"] = cw.compute_result(cb["configuration"], catalogue)
                cc.product_output(cb["configuration"], catalogue)
            except Exception as e:  # noqa: BLE001 — shown, not swallowed: the commit would refuse the same
                cb["can_commit"] = False
                cb["report"].append({"status": "CONFLICTING", "where": "Cost Basis", "field": "result",
                                     "detail": f"The cost basis cannot be computed: {e}", "blocking": True})
        if cb.get("versus_current", {}).get("unchanged"):
            cb["can_commit"] = False

    fin = tabs["financing"]
    if fin["provided"]:
        fins = _read("financing_case_version", access.project_id, access.owner_tenant)
        fin["_previous"] = fins[-1] if fins else None
        fin["_case_latest"] = None
        if fin.get("case_id"):
            same = [f for f in fins if f["case_id"] == fin["case_id"]]
            if not same:
                fin["report"].append({"status": "UNSUPPORTED", "where": "Financing", "field": "financing.case_id",
                                      "detail": f"No financing case {fin['case_id']} on this project: clear the "
                                                "cell to record a new case.", "blocking": True, "issue": False})
            else:
                fin["_case_latest"] = same[-1]
        base = None
        if fin.get("tea_claim_id"):
            row = db.execute("SELECT * FROM model_base_case WHERE claim_id=? AND project_id=?",
                             (fin["tea_claim_id"], access.project_id)).fetchone()
            if row is None:
                fin["report"].append({"status": "UNSUPPORTED", "where": "Financing", "field": "financing.tea_claim_id",
                                      "detail": f"No TEA run '{fin['tea_claim_id']}' on this project.",
                                      "blocking": True, "issue": False})
            else:
                base = _row(row)
        fin["_base"] = base
        from app.core import funding
        fin["funding"] = funding.reconcile(fin["funding_plan"], base_case=base, terms=fin["terms"],
                                           gearing_policy=_gearing_policy())
        fin["limitations"] = cc.draft_limitations(base, fin["terms"]) + fin["funding"]["limitations"]
        fin["would_save_as"] = "DRAFT"
        for l in fin["funding"]["limitations"]:
            fin["report"].append({"status": "CONFLICTING" if l["code"] in cc.STICKY_LIMITATIONS else "MISSING",
                                  "where": "Financing", "field": l["code"], "detail": l["detail"],
                                  "blocking": False, "issue": True})
        latest = fin["_case_latest"]
        if latest and latest.get("tea_claim_id") == fin.get("tea_claim_id") and \
                {k: v["value"] for k, v in fin["terms"].items()} == \
                {k: v["value"] for k, v in (latest.get("terms") or {}).items()} and \
                (fin["funding_plan"] == _plan_key(latest.get("funding_plan")) or
                 (not latest.get("funding_plan") and
                  _stack_key(fin["capital_sources"]) == _stack_key(_declared_stack(access, latest)))):
            fin["unchanged"] = True
        fin["can_commit"] = not any(r["blocking"] for r in fin["report"]) and not fin.get("unchanged")

    off = tabs["offtake"]
    if off["provided"]:
        current = _offtake_card(access.project_id)
        off["unchanged"] = off.get("card") is not None and terms_hash(off["card"]) == terms_hash(current)
        if off.get("card") and off["card"].get("buyers"):
            from app.api.v1.routes_bankability_proxy import _check_frame_buyers
            from app.core.commitment_terms import TermsValidationError
            try:
                _check_frame_buyers(access.project_id, off["card"]["buyers"])
            except TermsValidationError as e:
                off["can_commit"] = False
                off["report"] += [{"status": "CONFLICTING", "where": "Offtake", "field": "company_id",
                                   "detail": p, "blocking": True} for p in e.problems]
        if off["unchanged"]:
            off["can_commit"] = False
    for t in tabs.values():
        t["summary"] = _summary(t["report"])
    return parsed


def _plan_key(plan: Optional[dict]) -> dict:
    return {"sources": list((plan or {}).get("sources") or []), "uses": list((plan or {}).get("uses") or [])}


def _stack_key(stack: list) -> list:
    return sorted((c.get("source_id") or "", c["name"], c["type"], c["amount_eur"], c.get("rate"),
                   c.get("tenor_years"), c.get("status")) for c in stack or [])


def _declared_stack(access, version: dict) -> list:
    return next((i["declared"].get("capital_sources") or [] for i in
                 reversed(_imports(access.project_id, access.owner_tenant, "financing"))
                 if i["target_ref"] == version["version_id"]), [])


def _summary(report: list) -> dict:
    out = {s: 0 for s in ("ACCEPTED", "CONVERTED", "MISSING", "CONFLICTING", "UNSUPPORTED")}
    for r in report:
        out[r["status"]] += 1
    out["blocking"] = sum(1 for r in report if r["blocking"])
    out["open_issues"] = sum(1 for r in report if r.get("issue"))
    return out


def _public(parsed: dict) -> dict:
    return {**parsed, "tabs": {k: {kk: vv for kk, vv in t.items() if not kk.startswith("_")}
                               for k, t in parsed["tabs"].items()}}


@cost_basis_router.post("/{project_id}/workbook/preview")
async def workbook_preview(project_id: str, request: Request, response: Response, file: UploadFile = File(...),
                           db: Any = Depends(get_db)):
    """Reads every tab and says what saving each would do. Writes nothing."""
    _no_store(response)
    access, _ = _owner(request, project_id, _workbook_functions())
    return _public(await _parse_upload(file, access, db))


@cost_basis_router.post("/{project_id}/workbook/commit", status_code=201)
async def workbook_commit(project_id: str, request: Request, response: Response, file: UploadFile = File(...),
                          expected_file_sha256: str = Form(...), tab: str = Form("cost_basis"),
                          db: Any = Depends(get_db)):
    """Saves ONE tab from exactly the file that was previewed, by the function that may act on it."""
    _no_store(response)
    functions = {"cost_basis": cc.COST_BASIS_FUNCTIONS, "financing": _financing_functions(),
                 "offtake": OFFTAKE_FUNCTIONS}.get(tab)
    if functions is None:
        raise HTTPException(status_code=422, detail={"code": "UNKNOWN_TAB", "message": f"No tab '{tab}'."})
    access, payload = _owner(request, project_id, functions)
    parsed = await _parse_upload(file, access, db)
    if parsed["file_sha256"] != expected_file_sha256:
        raise HTTPException(status_code=409, detail={
            "code": "NOT_THE_PREVIEWED_FILE", "message": "This is not the file you previewed: preview it again."})
    t = parsed["tabs"][tab]
    if not t["provided"]:
        raise HTTPException(status_code=422, detail={"code": "TAB_EMPTY", "message": f"The {tab} tab is empty."})
    if t.get("unchanged") or (t.get("versus_current") or {}).get("unchanged"):
        raise HTTPException(status_code=409, detail={"code": "NO_CHANGE", "message": f"The {tab} tab changes nothing."})
    if not t["can_commit"]:
        raise HTTPException(status_code=422, detail={
            "code": "WORKBOOK_HAS_BLOCKING_ENTRIES", "message": f"{t['summary']['blocking']} entries block the "
            f"{tab} tab; see the preview.", "report": [r for r in t["report"] if r["blocking"]]})
    if tab == "cost_basis":
        return _commit_cost_basis(access, payload, t)
    if tab == "financing":
        return _commit_financing(access, parsed, t, db)
    return await _commit_offtake(access, payload, parsed, t)


def _commit_cost_basis(access, payload, t) -> dict:
    configuration = t["configuration"]
    catalogue = _catalogue()
    try:
        result = cw.compute_result(configuration, catalogue)
        product = cc.product_output(configuration, catalogue)
    except cc.ChainError as e:
        raise _refuse(e, 422)
    from app.core.plant_builder import EQUIPMENT_CATALOG
    record = cc.cost_basis_record(
        project_id=access.project_id, owner_tenant=access.owner_tenant, configuration=configuration,
        result=result, product=product, catalogue_hash=cc.catalogue_sha256(EQUIPMENT_CATALOG),
        previous=t["_previous"], saved_by=access.user_id, saved_by_function=payload.get("business_function"),
        open_issues=t.get("open_issues"))
    stored = _insert("cost_basis_version", access.owner_tenant, record)
    _event("cost_basis.saved", access.project_id, access.user_id,
           {"version_id": stored["version_id"], "version_number": stored["version_number"],
            "content_sha256": stored["content_sha256"], "status": stored["status"], "from_workbook": t["file_sha256"]})
    return {"tab": "cost_basis", **stored, "report_summary": t["summary"]}


def _commit_financing(access, parsed, t, db) -> dict:
    """Always a DRAFT: an import never promotes. The case and its declared stack in ONE transaction."""
    import uuid
    stack = [{**c, "source_id": c.get("source_id") or f"CAP-{uuid.uuid4().hex[:10]}"} for c in t["capital_sources"]]
    uses = [{**u, "use_id": u.get("use_id") or f"USE-{uuid.uuid4().hex[:10]}"} for u in t["funding_plan"]["uses"]]
    try:
        record = cc.financing_draft_record(
            project_id=access.project_id, owner_tenant=access.owner_tenant, case_id=t.get("case_id"),
            base_case=t["_base"], terms=t["terms"], previous=t["_previous"], case_latest=t["_case_latest"],
            saved_by=access.user_id, funding_plan={"sources": stack, "uses": uses} if (stack or uses) else None,
            gearing_policy=_gearing_policy())
    except cc.ChainError as e:
        raise _refuse(e, 422)
    imp = _import_row(access, "financing", parsed, "financing_case_version", record["version_id"],
                      record["content_sha256"], {"case_id": record["case_id"], "capital_sources": stack, "uses": uses})
    stored = _insert_many(access.owner_tenant, [("financing_case_version", record), ("workbook_import", imp)])
    _event("financing_case.saved", access.project_id, access.user_id,
           {"version_id": stored["version_id"], "case_id": stored["case_id"], "status": "DRAFT",
            "content_sha256": stored["content_sha256"], "from_workbook": parsed["file_sha256"]})
    return {"tab": "financing", **stored, "capital_sources": stack, "report_summary": t["summary"]}


async def _commit_offtake(access, payload, parsed, t) -> dict:
    from app.api.v1.routes_bankability_proxy import reevaluate, save_card
    from app.core.contract_tokens import terms_hash
    imp = _import_row(access, "offtake", parsed, "offtake_card", access.project_id, terms_hash(t["card"]),
                      t["declared"])
    changed = save_card(access.project_id, "offtake", t["card"], access.user_id, payload.get("company_id"),
                        also=lambda conn: _insert_import(conn, imp))
    reevaluation = None
    if changed:
        try:
            reevaluation = (await reevaluate(access.project_id, reason="terms offtake (workbook)",
                                             actor=access.user_id))["changes"]
        except HTTPException as exc:
            reevaluation = {"error": exc.detail, "state_withdrawn": True}
    return {"tab": "offtake", "terms": t["card"], "changed": changed, "reevaluation": reevaluation,
            "report_summary": t["summary"],
            "note": "Saved on the contract record. Each counterparty confirms its own terms before the gate "
                    "engine uses them."}


# ── 2. TEA from a saved cost basis ─────────────────────────────────────────────

class TeaFromCostBasis(BaseModel):
    model_config = {"extra": "forbid"}
    pathway_id: Optional[str] = None
    # Stated by whoever runs the TEA, each with its basis (core/calculation_chain.tea_request).
    stated: dict = Field(default_factory=dict)
    # Use the TEA inputs the workbook recorded with this cost basis (explicit, never a fallback).
    stated_from_workbook: bool = False


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
    stated = body.stated
    if body.stated_from_workbook:
        recorded = (cb["configuration"].get("workbook") or {}).get("tea_stated")
        if body.stated or not recorded:
            raise HTTPException(status_code=422, detail={
                "code": "TEA_INPUT_SOURCE", "message": "Send either the stated inputs or stated_from_workbook "
                "on a cost basis saved from a workbook, not both."})
        stated = recorded
    try:
        tea_body = cc.tea_request(cb, fuel_id=_fuel_id(cb["molecule"]),
                                  pathway_id=body.pathway_id or f"{access.project_id}:cost-basis",
                                  stated=stated)
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
    from app.core import reviewer_authority as ra
    try:
        test_account = bool(payload.get("user_id")) and ra.is_test_account(payload["user_id"])
        standing = cc.review_standing(
            reviewer=payload, run_by=base.get("run_by"), cost_basis_saved_by=cb["saved_by"],
            owner_tenant=access.owner_tenant,
            appointed_ie=bool(payload.get("user_id")) and _appointed_ie(payload["user_id"], access.project_id),
            test_account=test_account)
    except cc.ChainError as e:
        raise _refuse(e, 403)
    except ra.AuthorityError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})
    checks = cc.cost_basis_vs_tea(cb, base)
    if body.outcome == "approve" and cc.failed(checks):
        raise _refuse(cc.ChainError("CHECKS_FAILED", "These checks fail: " + "; ".join(cc.failed(checks))
                                    + ". Approve with conditions or reject."), 409)
    reviewed_at = _now()
    out = apply_approval(db.execute("SELECT * FROM model_base_case WHERE claim_id=?", (claim_id,)).fetchone(),
                         ApprovalRequest(approved_by=payload["user_id"], outcome=body.outcome,
                                         conditions=body.conditions,
                                         approver_role={"INDEPENDENT": "independent_engineer",
                                                        "TEST": "test_reviewer"}.get(standing,
                                                                                     "owner_internal_review")),
                         db, review={"review_basis": standing,
                                     "reviewed_by_company": payload.get("company_id"),
                                     "reviewed_at": reviewed_at, "review_conditions": body.conditions})
    base = _row(out["base_case"])
    _event("tea_base_case.reviewed", access.project_id, payload["user_id"],
           {"claim_id": claim_id, "outcome": body.outcome, "review_basis": standing})
    return {**out, "base_case": base, "review_basis": standing,
            "review_label": {"INDEPENDENT": "Independent review",
                             "TEST": "TEST review by a test account — not a review"}.get(
                standing, "Owner's internal review — not independent"),
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
                                     previous=versions[-1] if versions else None, saved_by=access.user_id,
                                     case_id=versions[-1]["case_id"] if versions else None)
    except cc.ChainError as e:
        raise _refuse(e)
    stored = _insert("financing_case_version", access.owner_tenant, record)
    _event("financing_case.saved", access.project_id, access.user_id,
           {"version_id": stored["version_id"], "content_sha256": stored["content_sha256"]})
    return stored


@chain_router.post("/{project_id}/financing/{version_id}/promote", status_code=201)
def promote_financing(project_id: str, version_id: str, request: Request, response: Response,
                      db: Any = Depends(get_db)):
    """A DRAFT becomes ELIGIBLE as a NEW version of the same case, on the 124 rules: an
    independently reviewed TEA run, every term with a source, debt + grant within fixed capital."""
    _no_store(response)
    from app.core.devex_share import PRODUCER_FUNCTIONS
    access, _ = _owner(request, project_id, PRODUCER_FUNCTIONS)
    versions = _read("financing_case_version", access.project_id, access.owner_tenant)
    draft = next((v for v in versions if v["version_id"] == version_id), None)
    if draft is None:
        raise HTTPException(status_code=404, detail="No such financing case version on this project")
    latest_of_case = [v for v in versions if v["case_id"] == draft["case_id"]][-1]
    if latest_of_case["version_id"] != draft["version_id"]:
        raise _refuse(cc.ChainError("NOT_THE_LATEST", f"v{latest_of_case['version_number']} supersedes this "
                                    "version; promote that one."))
    base = _base_case(db, draft["tea_claim_id"], access.project_id) if draft.get("tea_claim_id") else None
    try:
        record = cc.promotion_record(draft=draft, base_case=base, previous=versions[-1], saved_by=access.user_id,
                                     gearing_policy=_gearing_policy())
    except cc.ChainError as e:
        raise _refuse(e)
    stored = _insert("financing_case_version", access.owner_tenant, record)
    _event("financing_case.promoted", access.project_id, access.user_id,
           {"version_id": stored["version_id"], "case_id": stored["case_id"], "from_draft": draft["version_id"],
            "content_sha256": stored["content_sha256"]})
    return stored


# ── 5. Returns from the chain ──────────────────────────────────────────────────

class ChainReturnsRequest(BaseModel):
    financing_version_id: str
    case_name: str = Field(..., min_length=1)
    scenario: str = "BASE"
    valuation_boundary: str = "FULL_PROJECT"
    stated: dict[str, Any] = Field(..., description="{field: {value, source, verification_status}}")


def _gearing_policy() -> Optional[dict]:
    """The registry's gearing value as a REFERENCE: who set it, which row and version. Not a hurdle."""
    g = _approved_gearing()
    if not g:
        return None
    return {"owner": f"GEX reference registry: debt_gearing (source {g['source']})", "reference": g["ref_id"],
            "value": float(g["value"]), "standing": "REFERENCE: reported, not a GEX hurdle"}


def _funding_view(version: dict, base: Optional[dict]) -> Optional[dict]:
    from app.core import funding
    plan = version.get("funding_plan") or {}
    if not plan:
        return None
    return funding.reconcile(plan, base_case=base, terms=version.get("terms") or {}, gearing_policy=_gearing_policy())


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

def _report_status(bases: list[dict], cbs: list[dict]) -> None:
    """Each run's fixed report reference and whether its inputs still hold (core/tea_report)."""
    from app.core import tea_report
    from app.api.v1.routes_tea import TEA_ENGINE_URL
    cited = set().union(*[set(tea_report.cited_refs(b)) for b in bases]) if bases else set()
    try:
        states = tea_report.ref_states(cited)
    except Exception:                      # unreadable registry: those checks say NOT_CHECKED
        states = {}
    engine_now = tea_report.engine_version_now(TEA_ENGINE_URL) if bases else None
    for b in bases:
        b["report"] = tea_report.report_ref(b)
        b["inputs_now"] = tea_report.inputs_status(b, cbs, states, engine_now)


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
    _report_status(bases, cbs)
    if reviewer:
        return {"project_id": access.project_id, "project_name": access.project_name, "cost_bases": cbs,
                "tea_base_cases": bases, "financing_cases": [], "returns_versions": [],
                "viewer": {"user_id": payload.get("user_id"), "business_function": payload.get("business_function"),
                           "is_owner": False, "is_appointed_reviewer": True},
                "withheld": "Financing and returns are the owner's; a reviewer sees the cost bases and TEA runs."}
    fins = _read("financing_case_version", access.project_id, access.owner_tenant)
    by_claim = {b["claim_id"]: b for b in bases}
    for f in fins:
        f["funding"] = _funding_view(f, by_claim.get(f.get("tea_claim_id")))
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


# ── The TEA, out of GEX ────────────────────────────────────────────────────────

def _chain_reader(request: Request, project_id: str):
    payload = payload_from_request(request) or {}
    access = pre_fid_access.resolve(request, project_id)
    reviewer = (access.basis not in ("owner", "platform_admin") and bool(payload.get("user_id"))
                and _appointed_ie(payload["user_id"], access.project_id))
    if access.basis not in ("owner", "platform_admin") and not reviewer:
        raise HTTPException(status_code=403, detail={"code": "OWNER_ONLY",
                                                     "message": "The calculation chain is the owner's."})
    return access, payload


def _run_and_basis(db, access, claim_id: str) -> tuple[dict, dict]:
    base = _base_case(db, claim_id, access.project_id)
    if not base.get("cost_basis_version_id"):
        raise _refuse(cc.ChainError("TEA_NOT_FROM_COST_BASIS", "This run was not priced from a saved cost basis."))
    return base, _one("cost_basis_version", access.project_id, access.owner_tenant, base["cost_basis_version_id"])


@chain_router.get("/{project_id}/tea/{claim_id}/workbook")
def tea_workbook(project_id: str, claim_id: str, request: Request, db: Any = Depends(get_db)):
    access, payload = _chain_reader(request, project_id)
    base, cb = _run_and_basis(db, access, claim_id)
    _report_status([base], _read("cost_basis_version", access.project_id, access.owner_tenant))
    data = cw.export_tea(_catalogue(), project_id=access.project_id, project_name=access.project_name or "",
                         cost_basis=cb, base_case=base, checks=cc.cost_basis_vs_tea(cb, base),
                         generated_by=payload.get("user_id"))
    return _xlsx(data, f"GEX_TEA_{access.project_id}_{claim_id}.xlsx")


@chain_router.get("/{project_id}/tea/{claim_id}/openpytea-config")
def tea_openpytea_config(project_id: str, claim_id: str, request: Request, response: Response,
                         db: Any = Depends(get_db)):
    _no_store(response)
    access, _ = _chain_reader(request, project_id)
    base, _cb = _run_and_basis(db, access, claim_id)
    cfg = (base.get("tea_inputs") or {}).get("openpytea_config")
    if not cfg:
        raise HTTPException(status_code=404, detail={"code": "NO_CONFIG_RECORDED",
                                                     "message": "No OpenPyTEA config was recorded for this run."})
    return cfg
