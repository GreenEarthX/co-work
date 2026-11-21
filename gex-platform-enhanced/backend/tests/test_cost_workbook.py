"""The Cost Basis and TEA workbook (core/cost_workbook.py, 19 Nov 2026). Offline, no database.

Synthetic values only: no reference case's data points.
"""
from __future__ import annotations

import io
import json

import pytest
from openpyxl import load_workbook

from app.core import calculation_chain as cc
from app.core import cost_workbook as cw
from app.core.plant_builder import EQUIPMENT_CATALOG

CAT = {i.id: i for i in EQUIPMENT_CATALOG}
P = "proj_TEST_workbook"


def _blank():
    return load_workbook(io.BytesIO(cw.template(CAT, project_id=P)))


def _set(wb, sheet, key, value, source="test source", as_of="2026-11-19", standing=None):
    ws = wb[sheet]
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 1).value == key:
            ws.cell(r, 3).value = value          # .value: ws.cell(r, c, None) would not clear a cell
            ws.cell(r, 5).value = source
            if not key.startswith(("boundary.", "scope.")):
                ws.cell(r, 6).value = as_of
                ws.cell(r, 7).value = standing
            return
    raise KeyError(key)


def _table(wb, sheet, header, columns, rows):
    ws = wb[sheet]
    start = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == header)
    for i, row in enumerate(rows, start + 1):
        assert ws.cell(i, 1).value == "row"
        for j, name in enumerate(columns, 2):
            ws.cell(i, j, row.get(name))


def _bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BOUNDARY = {"boundary.hydrogen": "ON_SITE", "boundary.co2": "PURCHASED", "boundary.nitrogen": "NOT_USED",
            "scope.electrolysis": "INCLUDED", "scope.power_infrastructure": "INCLUDED",
            "scope.co2_supply": "EXCLUDED", "scope.nitrogen_supply": "NOT_APPLICABLE",
            "scope.storage_logistics": "INCLUDED", "scope.site_civil": "INCLUDED"}
FIELDS = {"molecule": "E_METHANOL", "detail_level": "EARLY_ESTIMATE", "location_jurisdiction": "DE",
          "nameplate_t_per_year": 40_000, "capacity_factor": "85%", "project_life_years": 25, "wacc_pct": 0.08,
          "contingency_pct": 0.15, "power_price_eur_mwh": 60, "water_price_eur_m3": 2, "labour_count": 30,
          "labour_cost_eur_year": 70_000}
LINES = [{"line_ref": "A01", "kind": "AGGREGATE", "description": "Whole plant, pre-feasibility", "scope": "WHOLE_PLANT",
          "installed_cost_eur": 250_000_000, "price_year": 2026, "estimate_class": 5, "annual_power_mwh": 600_000,
          "source": "pre-feasibility study", "as_of": "2026-10"}]
FEEDS = [{"stream": "hydrogen", "on_site_t_per_year": 8_000, "on_site_basis": "electrolyser in the aggregate"},
         {"stream": "co2", "purchase_unit": "t/day", "consumption_per_day": 180, "price_eur_per_unit": 200,
          "price_source": "supplier indication"}]


def _workbook(fields=None, boundary=None, lines=None, feeds=None, tea=None, external=None, drop=()):
    wb = _blank()
    for k, v in {**BOUNDARY, **(boundary or {})}.items():
        _set(wb, "Cost Basis", k, v, source="stated by CFO")
    for k, v in {**FIELDS, **(fields or {})}.items():
        if k not in drop:
            _set(wb, "Cost Basis", k, v)
    for k, v in {"tea.process_type": "Fluids", "tea.loc_factor": 1.0, **(tea or {})}.items():
        _set(wb, "TEA inputs", k, v, source="local quotes")
    _table(wb, "Cost Basis", "lines.header", cw.LINE_COLUMNS, LINES if lines is None else lines)
    _table(wb, "TEA inputs", "feedstocks.header", cw.FEED_COLUMNS, FEEDS if feeds is None else feeds)
    _table(wb, "TEA inputs", "external.header", cw.EXT_COLUMNS, external or [])
    return wb


def _parse(wb):
    return cw.parse(_bytes(wb), catalogue=CAT, project_id=P)


def _statuses(parsed, field):
    return {r["status"] for r in parsed["report"] if r["field"] == field}


def test_the_blank_template_reads_as_not_provided_and_a_started_one_as_missing_not_zero():
    p = cw.parse(cw.template(CAT, project_id=P), catalogue=CAT, project_id=P)
    assert p["provided"] is False and not p["can_commit"]
    wb = _blank()
    _set(wb, "Cost Basis", "molecule", "E_METHANOL")
    p = _parse(wb)
    assert p["provided"] and not p["can_commit"]
    missing = {r["field"] for r in p["report"] if r["status"] == "MISSING" and r["blocking"]}
    assert {"capacity_factor", "lines"} <= missing
    open_ = {i["field"] for i in p["open_issues"]}                  # an open boundary is a draft's issue
    assert {"boundary.hydrogen", "scope.electrolysis"} <= open_
    assert "insurance_pct_capex" not in p["configuration"]


def test_an_early_estimate_with_an_aggregate_capex_is_accepted_and_labelled():
    p = _parse(_workbook())
    assert p["can_commit"], [r for r in p["report"] if r["blocking"]]
    c = p["configuration"]
    assert not [r for r in p["report"] if r["status"] == "UNSUPPORTED"]   # the template's own rows all read
    assert c["capacity_factor"] == pytest.approx(0.85)                  # 85% converted, and said
    assert "CONVERTED" in _statuses(p, "capacity_factor")
    assert c["own_lines"][0]["kind"] == "AGGREGATE" and c["own_lines"][0]["estimate_class"] == 5
    assert c["provenance"]["wacc_pct"]["source"] == "test source"
    r = cw.compute_result(c, CAT)
    assert r["capex"]["total_capex_eur"] == round(250e6 * 1.15)
    assert r["opex"]["annual_insurance_eur"] is None and r["opex"]["opex_complete"] is False   # unknown, not 0
    assert r["opex"]["annual_om_eur"] is None and r["opex"]["om_unknown_lines"] == ["A01"]
    product = cc.product_output(c, CAT)
    assert product["basis"] == "STATED_NAMEPLATE" and product["nameplate_t_per_year"] == 40_000


def test_a_required_value_without_its_source_blocks():
    wb = _workbook()
    _set(wb, "Cost Basis", "wacc_pct", 0.08, source=None)
    p = _parse(wb)
    assert any(r["field"] == "wacc_pct" and r["status"] == "MISSING" and r["blocking"] for r in p["report"])


@pytest.mark.parametrize("boundary,feeds,lines,field", [
    ({"scope.electrolysis": "EXCLUDED"}, None, None, "boundary.hydrogen"),            # made on site, not in CAPEX
    ({"boundary.hydrogen": "PURCHASED"}, [FEEDS[1], {"stream": "hydrogen", "purchase_unit": "t/day",
      "consumption_per_day": 20, "price_eur_per_unit": 5000, "price_source": "x"}],
     [{"line_ref": "C1", "kind": "CATALOGUE", "catalogue_id": "PEM_ELEC_120MW"}, LINES[0]], "boundary.hydrogen"),
    ({}, [FEEDS[0]], None, "co2"),                                                     # bought, but no purchase row
    ({"scope.co2_supply": "INCLUDED"}, None,
     [{**LINES[0], "scope": "SYNTHESIS", "annual_power_mwh": 1}], "scope.co2_supply"),  # included, no such line
])
def test_the_plant_boundary_is_checked_against_lines_and_tea_inputs(boundary, feeds, lines, field):
    p = _parse(_workbook(boundary=boundary, feeds=feeds, lines=lines))
    assert "CONFLICTING" in _statuses(p, field)
    assert p["can_commit"] and p["would_save_as"] == "DRAFT"             # recorded, and stated
    assert any(i["field"] == field for i in p["open_issues"])


def test_financing_preparation_with_an_aggregate_is_only_a_draft():
    p = _parse(_workbook(fields={"detail_level": "FINANCING_PREP"}))
    assert "CONFLICTING" in _statuses(p, "detail_level") and p["would_save_as"] == "DRAFT"


def test_no_tea_runs_from_a_draft_cost_basis():
    p = _parse(_workbook(boundary={"scope.electrolysis": "EXCLUDED"}))
    cb = _saved(p)
    assert cb["status"] == "DRAFT" and cb["open_issues"]
    with pytest.raises(cc.ChainError) as e:
        cc.tea_request(cb, fuel_id="E_METHANOL", pathway_id="p", stated=p["tea_stated"])
    assert e.value.code == "COST_BASIS_DRAFT" and "electrolysis" in e.value.message


def test_a_catalogue_line_with_a_typed_price_is_a_conflict_not_silently_ignored():
    lines = [{"line_ref": "C1", "kind": "CATALOGUE", "catalogue_id": "MEOH_SYNTH_50KT", "installed_cost_eur": 1}]
    p = _parse(_workbook(lines=lines + LINES))
    assert "CONFLICTING" in _statuses(p, "C1")


def test_an_electrolysis_quote_without_its_power_blocks():
    q = {"line_ref": "Q1", "kind": "QUOTE", "scope": "ELECTROLYSIS", "installed_cost_eur": 90e6, "source": "OEM"}
    p = _parse(_workbook(lines=[q, {**LINES[0], "scope": "SYNTHESIS", "annual_power_mwh": None}]))
    assert any(r["field"] == "Q1" and r["blocking"] for r in p["report"])


def test_an_uncalculated_formula_is_unsupported():
    wb = _workbook()
    ws = wb["Cost Basis"]
    row = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "labour_count")
    ws.cell(row, 3, "=10*3")
    p = _parse(wb)
    assert "UNSUPPORTED" in _statuses(p, "labour_count") and not p["can_commit"]


def test_wrong_version_or_project_is_refused():
    wb = _workbook()
    wb["Cost Basis"].cell(2, 2, "gex-cost-tea-0")
    with pytest.raises(cw.WorkbookError) as e:
        _parse(wb)
    assert e.value.code == "TEMPLATE_VERSION_UNSUPPORTED"
    with pytest.raises(cw.WorkbookError) as e:
        cw.parse(_bytes(_workbook()), catalogue=CAT, project_id="another")
    assert e.value.code == "WRONG_PROJECT"


def test_an_external_result_is_kept_attributed_not_as_gex_figure():
    ext = [{"metric": "LCOP_EUR_PER_KG", "value": 1.9, "unit": "EUR/kg", "author": "Consultant Ltd",
            "model_and_date": "TEA model 12 Nov 2026", "document": "report.pdf"}]
    p = _parse(_workbook(external=ext))
    x = p["configuration"]["workbook"]["external"][0]
    assert x["standing"] == "EXTERNAL_ASSESSMENT" and x["author"] == "Consultant Ltd"
    assert "lcop" not in p["configuration"]


def _saved(parsed, previous=None):
    c = parsed["configuration"]
    return {**cc.cost_basis_record(project_id=P, owner_tenant="o", configuration=c,
                                   result=cw.compute_result(c, CAT), product=cc.product_output(c, CAT),
                                   catalogue_hash="c" * 64, previous=previous, saved_by="cfo",
                                   saved_by_function="FINANCE_TREASURY", open_issues=parsed.get("open_issues")),
            "saved_at": "2026-11-19"}


def _without_sha(c):
    return {**c, "workbook": {k: v for k, v in c["workbook"].items() if k != "file_sha256"}}


def test_the_filled_template_reimports_to_the_same_inputs():
    ext = [{"metric": "CAPEX_EUR", "value": 3e8, "unit": "EUR", "author": "Bank adviser", "model_and_date": "m 1"}]
    cb = _saved(_parse(_workbook(external=ext)))
    again = cw.parse(cw.template(CAT, project_id=P, cost_basis=cb), catalogue=CAT, project_id=P)
    assert again["can_commit"]
    assert _without_sha(again["configuration"]) == _without_sha(cb["configuration"])
    assert cw.versus_current(cb, again["configuration"])["unchanged"]


def test_an_amended_workbook_shows_its_changes():
    cb = _saved(_parse(_workbook()))
    p = _parse(_workbook(fields={"power_price_eur_mwh": 55}))
    v = cw.versus_current(cb, p["configuration"])
    assert v["current_version"] == 1 and {"field": "power_price_eur_mwh", "from": 60, "to": 55} in v["changes"]


def _tea_inputs(req, cfg=None):
    return {"request": req, "calculation_boundary": {"basis": "QUOTE_LINES"},
            "openpytea_config": cfg or {"equipment": [{"name": e["name"], "purchased_cost": e["installed_cost"],
                                                       "cost_year": e.get("cost_year")}
                                                      for e in req["quote_plant"]["equipment"]]},
            "feedstock_balance": [], "defaults_used": [{"name": "openpytea.osbl_factor", "value": 0.3, "basis": "d"}]}


def test_the_tea_from_a_workbook_cost_basis_carries_price_year_boundary_and_aggregate_label():
    p = _parse(_workbook())
    cb = _saved(p)
    req = cc.tea_request(cb, fuel_id="E_METHANOL", pathway_id="p", stated=p["tea_stated"])
    assert req["quote_plant"]["equipment"][0]["cost_year"] == 2026
    assert req["quote_plant"]["osbl_factor"] == 0.0 and "whole-plant aggregate" in req["quote_plant"]["osbl_factor_basis"]
    assert "maintenance_costs" not in req["quote_plant"]["fixed_opex_components"]   # unknown O&M: default, said
    assert set(req["quote_plant"]["variable_opex"]) == {"electricity", "water", "co2"} or \
        set(req["quote_plant"]["variable_opex"]) == {"electricity", "co2"}
    base = {"cost_basis_version_id": cb["version_id"], "cost_basis_sha256": cb["content_sha256"],
            "nameplate_capacity": req["nameplate_capacity"], "capex_eur": 4e8, "opex_eur_per_year": 5e7,
            "tea_inputs": _tea_inputs(req)}
    checks = {c["check"]: c for c in cc.cost_basis_vs_tea(cb, base)}
    assert checks["Plant boundary: hydrogen"]["result"] == "PASS"
    assert checks["Plant boundary: co2"]["result"] == "PASS"
    assert checks["Cost detail"]["result"] == "REPORTED" and "aggregate" in checks["Cost detail"]["detail"]
    assert not cc.failed(checks.values())
    # the TEA run that buys hydrogen instead of making it (v1's defect) fails the boundary
    wrong = {**req, "quote_plant": {**req["quote_plant"], "on_site_supply": {},
                                    "variable_opex": {**req["quote_plant"]["variable_opex"],
                                                      "hydrogen": {"consumption": 1, "unit": "t/day", "price": 1,
                                                                   "source": "x"}}}}
    bad = cc.cost_basis_vs_tea(cb, {**base, "tea_inputs": _tea_inputs(wrong)})
    assert "Plant boundary: hydrogen" in cc.failed(bad)


def test_the_export_is_a_frozen_record_with_the_exact_openpytea_config():
    ext = [{"metric": "LCOP_EUR_PER_KG", "value": 1.9, "unit": "EUR/kg", "author": "Consultant Ltd",
            "model_and_date": "TEA model 12 Nov 2026"}]
    p = _parse(_workbook(external=ext))
    cb = _saved(p)
    req = cc.tea_request(cb, fuel_id="E_METHANOL", pathway_id="p", stated=p["tea_stated"])
    cfg = {"plant_name": "p", "equipment": [{"name": "A01 x1", "purchased_cost": 2.5e8, "cost_year": 2026,
                                            "category": "Vendor quote"}]}
    base = {"claim_id": "CLM-X", "state": "submitted", "cost_basis_version_id": cb["version_id"],
            "cost_basis_sha256": cb["content_sha256"], "nameplate_capacity": 40_000, "capex_eur": 4e8,
            "opex_eur_per_year": 5e7, "lcop": 2.4, "engine": "openpytea", "tea_inputs": _tea_inputs(req, cfg)}
    data = cw.export_tea(CAT, project_id=P, project_name="Test", cost_basis=cb, base_case=base,
                         checks=cc.cost_basis_vs_tea(cb, base), generated_by="cfo")
    wb = load_workbook(io.BytesIO(data))
    assert {"Cost Basis", "TEA inputs", "TEA results", "Defaults used", "Feedstock balance", "Checks",
            "External vs GEX", "OpenPyTEA config"} <= set(wb.sheetnames)
    assert json.loads(wb["OpenPyTEA config"].cell(2, 6).value) == cfg
    ext_row = [c.value for c in wb["External vs GEX"][2]]
    assert ext_row[0] == "LCOP_EUR_PER_KG" and ext_row[5] == 2.4 and ext_row[6] == pytest.approx(0.5)
    assert not any(isinstance(c.value, str) and c.value.startswith("=") for ws in wb for row in ws for c in row)
    # its own Cost Basis and TEA inputs sheets re-import to the same inputs
    again = cw.parse(data, catalogue=CAT, project_id=P)
    assert again["can_commit"] and _without_sha(again["configuration"])["own_lines"] == cb["configuration"]["own_lines"]
    assert again["tea_stated"]["feedstocks"] == p["tea_stated"]["feedstocks"]


# ── Financing and Offtake tabs (finance_workbook) ──────────────────────────────

from app.core import finance_workbook as fw    # noqa: E402

FIN = {"financing.tea_claim_id": "CLM-REVIEWED", "financing.debt_eur": 180e6, "financing.interest_rate": "6%",
       "financing.debt_tenor_years": 15, "financing.grant_eur": 20e6}
STACK = [{"name": "Innovation grant", "type": "GRANT", "amount_eur": 20e6, "status": "APPLIED",
          "obligation": "INDICATIVE", "source": "application"},
         {"name": "Senior bank debt", "type": "SENIOR_DEBT", "amount_eur": 120e6, "rate": 0.065, "tenor_years": 15,
          "status": "TERM_SHEET", "obligation": "INDICATIVE", "lender_max_gearing": 0.5, "source": "term sheet 3 Nov"},
         {"name": "DFI loan", "type": "DFI_LOAN", "amount_eur": 60e6, "rate": 0.04, "tenor_years": 18,
          "status": "MANDATE", "obligation": "CONDITIONAL", "conditions": "credit committee approval",
          "source": "mandate letter"},
         {"name": "Sponsor equity", "type": "SPONSOR_EQUITY", "amount_eur": 90e6, "status": "COMMITTED",
          "obligation": "BINDING", "available_eur": 80e6, "received_eur": 10e6, "source": "board minute"},
         {"name": "Green bond (prospect)", "type": "GREEN_BOND", "amount_eur": 50e6, "obligation": "NONE",
          "in_plan": "No", "source": "arranger call"}]
USES = [{"kind": "DEVELOPMENT", "amount_eur": 12e6, "standing": "MANAGEMENT_ASSUMPTION", "source": "DEVEX plan"},
        {"kind": "FINANCING_COSTS", "component": "IDC", "amount_eur": 15e6,
         "reason": "engine IDC not built for this drawdown schedule", "source": "lender model"},
        {"kind": "RESERVES", "amount_eur": 8e6, "source": "term sheet DSRA 6 months"},
        {"kind": "WORKING_CAPITAL", "amount_eur": 5e6, "source": "30 days of OPEX"}]
BUYER = {"counterparty_name": "Shipping Co (synthetic)", "counterparty_role": "END_USER", "commitment_form": "TAKE_OR_PAY",
         "take_or_pay_pct": 0.8, "contracted_tonnes_per_year": 30_000, "tenor_years": 12, "buyer_investment_grade": "Yes",
         "price_mechanism": "INDEX_PLUS_PREMIUM", "first_delivery_date": "2029-01-01", "source": "HoT 1 Oct 2026"}


def _fin_wb(fields=None, stack=None, buyers=None, shared=None, uses=None):
    wb = _workbook()
    for k, v in {**FIN, **(fields or {})}.items():
        _set(wb, "Financing", k, v, source="term sheet", standing="TERM_SHEET")
    _table(wb, "Financing", "capital.header", fw.CAP_COLUMNS, STACK if stack is None else stack)
    _table(wb, "Financing", "uses.header", fw.USE_COLUMNS, USES if uses is None else uses)
    for k, v in (shared or {"offtake.planned_output_tonnes_per_year": 45_000,
                            "offtake.change_in_law_allocated": "Yes"}).items():
        _set(wb, "Offtake", k, v, source="business plan")
    _table(wb, "Offtake", "buyers.header", fw.BUYER_COLUMNS, [BUYER] if buyers is None else buyers)
    return wb


def _tabs(wb):
    return cw.parse_all(_bytes(wb), catalogue=CAT, project_id=P)["tabs"]


def test_untouched_financing_and_offtake_tabs_are_not_provided():
    t = _tabs(_workbook())
    assert t["cost_basis"]["provided"] and not t["financing"]["provided"] and not t["offtake"]["provided"]


def test_the_financing_case_takes_its_terms_with_source_date_and_standing():
    f = _tabs(_fin_wb())["financing"]
    assert f["can_commit"], [r for r in f["report"] if r["blocking"]]
    assert f["tea_claim_id"] == "CLM-REVIEWED"
    assert f["terms"]["interest_rate"]["value"] == pytest.approx(0.06)
    assert f["terms"]["debt_eur"]["standing"] == "TERM_SHEET" and f["terms"]["debt_eur"]["source"] == "term sheet"
    assert len(f["capital_sources"]) == 5
    rec = cc.financing_record(project_id=P, owner_tenant="o", saved_by="cfo", previous=None, terms=f["terms"],
                              base_case={"claim_id": "CLM-REVIEWED", "state": "verified", "cost_basis_version_id": "x",
                                         "cost_basis_hash": "h", "capex_eur": 300e6,
                                         "tea_inputs": {"calculation_boundary": {"basis": "QUOTE_LINES"}}})
    assert rec["terms"]["debt_eur"]["standing"] == "TERM_SHEET"
    assert rec["terms"]["debt_eur"]["verification_status"] == "ASSUMPTION"     # declared, not verified


BASE = {"claim_id": "CLM-REVIEWED", "capex_eur": 300e6}


def test_the_selected_case_is_reconciled_and_the_pipeline_kept_apart():
    from app.core import funding
    f = _tabs(_fin_wb())["financing"]
    assert f["can_commit"], [r for r in f["report"] if r["blocking"]]
    assert "CONVERTED" in _statuses(f, "financing.interest_rate")             # weighted stack rate vs the case's
    r = funding.reconcile(f["funding_plan"], base_case=BASE, terms=f["terms"],
                          gearing_policy={"owner": "GEX reference registry: debt_gearing (source OIES ET21)",
                                          "reference": "ref-1", "value": 0.65})
    assert r["limitations"] == []
    assert r["total_uses_eur"] == 340e6 and not r["total_is_floor"]          # 300 TEA + 12 + 15 + 8 + 5
    assert r["uses"][0] == {"kind": "CONSTRUCTION", "amount_eur": 300e6, "origin": "CALCULATED",
                            "source": "TEA run CLM-REVIEWED fixed capital (OpenPyTEA: ISBL, OSBL, D&E, contingency)"}
    assert r["openpytea_working_capital_eur"] == 45e6                      # shown beside the stated 5M, not added
    assert r["received_eur"] == 10e6 and r["binding_available_eur"] == 80e6
    assert r["remaining_need_eur"] == 250e6                                  # 340 - 10 received - 80 binding
    assert [c["name"] for c in r["conditional"]] == ["DFI loan"]
    assert r["pipeline_total_eur"] == 50e6 and r["allocated_eur"] == 290e6  # the bond is never counted
    g = {x["by"]: x for x in r["gearing"]}
    assert g["GEX reference registry: debt_gearing (source OIES ET21)"]["result"] == "WITHIN"
    assert g["Senior bank debt"]["result"] == "ABOVE" and "own limit" in g["Senior bank debt"]["standing"]


def test_the_case_and_its_plan_must_agree_and_every_use_is_stated_or_unknown():
    from app.core import funding
    f = _tabs(_fin_wb(fields={"financing.grant_eur": 10e6, "financing.debt_eur": 150e6}))["financing"]
    r = funding.reconcile(f["funding_plan"], base_case=BASE, terms=f["terms"])
    assert {"GRANTS_UNRECONCILED", "STACK_DEBT_UNRECONCILED"} <= {l["code"] for l in r["limitations"]}
    f = _tabs(_fin_wb(uses=[USES[0], {**USES[1], "reason": None}, {**USES[3], "amount_eur": 0}]))["financing"]
    r = funding.reconcile(f["funding_plan"], base_case=BASE, terms=f["terms"])
    codes = {l["code"] for l in r["limitations"]}
    assert {"USES_INCOMPLETE", "FINANCING_COSTS_UNEXPLAINED", "WORKING_CAPITAL_ZERO_UNEXPLAINED"} <= codes
    assert r["total_is_floor"] and r["unknown_uses"] == ["RESERVES"]
    r = funding.reconcile({"sources": [], "uses": [{"kind": "CONSTRUCTION", "amount_eur": 1e8, "source": "x"}]},
                          base_case=BASE, terms={})
    assert "CONSTRUCTION_TWICE" in {l["code"] for l in r["limitations"]}
    r = funding.reconcile({"sources": [], "uses": [{"kind": "CONSTRUCTION", "amount_eur": 1e8, "source": "x"}]},
                          base_case=None, terms={})
    assert r["uses"][0]["origin"] == "ESTIMATE"                              # no TEA run: a labelled estimate
    f = _tabs(_fin_wb())["financing"]
    r = funding.reconcile(f["funding_plan"], base_case=None, terms=f["terms"])  # construction unknown
    assert r["total_is_floor"] and r["remaining_need_eur"] is None           # not "at least 0"


def test_available_to_draw_needs_a_binding_obligation():
    f = _tabs(_fin_wb(stack=[{**STACK[2], "available_eur": 1e6}]))["financing"]
    assert not f["can_commit"]


def test_a_financing_term_without_its_source_blocks():
    wb = _fin_wb()
    _set(wb, "Financing", "financing.debt_tenor_years", 15, source=None)
    f = _tabs(wb)["financing"]
    assert any(r["field"] == "financing.debt_tenor_years" and r["blocking"] for r in f["report"])


def test_one_buyer_without_company_is_a_single_card_validated_by_the_card_rules():
    o = _tabs(_fin_wb())["offtake"]
    assert o["can_commit"] and not o["frame"], [r for r in o["report"] if r["blocking"]]
    card = o["card"]
    assert card["take_or_pay_pct"] == 80.0 and card["buyer_investment_grade"] is True
    assert card["planned_output_tonnes_per_year"] == 45_000 and card["change_in_law_allocated"] is True
    assert "buyers" not in card and o["declared"]["buyers"]["#1"]["source"] == "HoT 1 Oct 2026"


def test_several_buyers_make_a_frame_and_each_needs_its_company():
    two = [{**BUYER, "company_id": "buyer_a"}, {**BUYER, "counterparty_name": "B", "contracted_tonnes_per_year": 10_000}]
    o = _tabs(_fin_wb(buyers=two))["offtake"]
    assert o["frame"] and not o["can_commit"] and "MISSING" in _statuses(o, "company_id")
    two[1]["company_id"] = "buyer_b"
    o = _tabs(_fin_wb(buyers=two))["offtake"]
    assert o["can_commit"] and [b["company_id"] for b in o["card"]["buyers"]] == ["buyer_a", "buyer_b"]
    assert "planned_output_tonnes_per_year" in o["card"]                               # shared stays at the top


def test_an_invalid_offtake_term_is_refused_by_the_card_rules():
    o = _tabs(_fin_wb(buyers=[{**BUYER, "commitment_form": "HANDSHAKE"}]))["offtake"]
    assert not o["can_commit"] and "CONFLICTING" in _statuses(o, "card")
    o = _tabs(_fin_wb(buyers=[{**BUYER, "source": None}]))["offtake"]
    assert not o["can_commit"]


def test_financing_and_offtake_fill_back_to_the_same_values():
    t = _tabs(_fin_wb())
    f, o = t["financing"], t["offtake"]
    version = {"tea_claim_id": f["tea_claim_id"], "terms": f["terms"]}
    wb = load_workbook(io.BytesIO(cw.template(CAT, project_id=P,
                                              financing=fw.fill_financing(version, {"capital_sources": f["capital_sources"]}, None),
                                              offtake=fw.fill_offtake(o["card"], o["declared"]))))
    again = _tabs(wb)
    assert again["financing"]["terms"] == f["terms"] and again["financing"]["capital_sources"] == f["capital_sources"]
    assert again["offtake"]["card"] == o["card"] and again["offtake"]["declared"] == o["declared"]


# ── the routes, with the stores replaced in memory (they commit; the dev database is never touched) ──

class _DB:
    def __init__(self, bases):
        self.bases = bases

    def execute(self, sql, params=()):
        rows = [b for b in self.bases.values() if not params or b["claim_id"] == params[0]] \
            if "model_base_case" in sql else []
        if "state='verified'" in sql:
            rows = [b for b in self.bases.values() if b["state"] == "verified" and b.get("review_basis") == "INDEPENDENT"]
        return type("R", (), {"fetchone": lambda s: rows[0] if rows else None, "fetchall": lambda s: rows})()


@pytest.fixture
def client(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1 import routes_calculation_chain as r
    from app.api.v1 import routes_bankability_proxy as bp
    store = {"cost_basis_version": [], "financing_case_version": [], "workbook_import": [], "card": {}}
    access = SimpleNamespace(project_id=P, project_name="Test", owner_tenant="o", user_id="cfo", basis="owner")
    fn = {"f": "FINANCE_TREASURY"}
    monkeypatch.setattr(r, "_owner", lambda req, p, f: (access, {"business_function": fn["f"], "company_id": "o"})
                        if fn["f"] in f else (_ for _ in ()).throw(r.HTTPException(status_code=403, detail="no")))
    monkeypatch.setattr(r, "_read", lambda t, p, o: [dict(x) for x in store[t]])
    monkeypatch.setattr(r, "_insert", lambda t, o, rec: store[t].append({**rec, "saved_at": "now"}) or store[t][-1])

    def insert_many(o, rows):
        for t, rec in rows:
            store[t].append({**rec, "saved_at": "now"})
        return store[rows[0][0]][-1]
    monkeypatch.setattr(r, "_insert_many", insert_many)
    monkeypatch.setattr(r, "_insert_import", lambda conn, row: store["workbook_import"].append(row))
    monkeypatch.setattr(r, "_event", lambda *a, **k: None)
    monkeypatch.setattr(r, "_imports", lambda p, o, tab: [i for i in store["workbook_import"] if i["tab"] == tab])
    monkeypatch.setattr(r, "_offtake_card", lambda p: dict(store["card"]))

    def save_card(p, kind, clean, who, company, also=None):
        changed = store["card"] != clean
        store["card"] = clean
        if also:
            also(None)
        return changed

    async def reevaluate(*a, **k):
        return {"changes": []}
    monkeypatch.setattr(bp, "save_card", save_card)
    monkeypatch.setattr(bp, "reevaluate", reevaluate)
    bases = {"CLM-REVIEWED": {"claim_id": "CLM-REVIEWED", "project_id": P, "state": "verified",
                              "review_basis": "INDEPENDENT", "cost_basis_version_id": "x", "cost_basis_hash": "h",
                              "capex_eur": 300e6, "tea_inputs": {"calculation_boundary": {"basis": "QUOTE_LINES"}}}}
    app = FastAPI()
    app.include_router(r.cost_basis_router)
    app.include_router(r.chain_router)
    app.dependency_overrides[r.get_db] = lambda: _DB(bases)
    return TestClient(app), store, fn, bases


def _up(c, url, data, **form):
    return c.post(url, files={"file": ("w.xlsx", data, "application/octet-stream")}, data=form)


def _preview(c, data):
    r = _up(c, f"/api/v1/cost-basis/{P}/workbook/preview", data)
    assert r.status_code == 200, r.text
    return r.json()


def _commit(c, data, sha, tab):
    return _up(c, f"/api/v1/cost-basis/{P}/workbook/commit", data, expected_file_sha256=sha, tab=tab)


def test_preview_writes_nothing_and_commit_saves_only_the_previewed_file(client):
    c, store, fn, _ = client
    fn["f"] = "ENGINEERING"
    data = _bytes(_workbook())
    pv = _preview(c, data)
    cb = pv["tabs"]["cost_basis"]
    assert cb["can_commit"] and cb["would_save_as"] == "READY" and store["cost_basis_version"] == []
    assert cb["result_preview"]["capex"]["total_capex_eur"] == round(250e6 * 1.15)
    other = _bytes(_workbook(fields={"labour_count": 31}))
    assert _commit(c, other, pv["file_sha256"], "cost_basis").status_code == 409
    ok = _commit(c, data, pv["file_sha256"], "cost_basis")
    assert ok.status_code == 201, ok.text
    assert len(store["cost_basis_version"]) == 1 and store["cost_basis_version"][0]["status"] == "READY"
    again = _commit(c, data, pv["file_sha256"], "cost_basis")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NO_CHANGE"
    tpl = c.get(f"/api/v1/cost-basis/{P}/workbook/template")
    assert tpl.status_code == 200 and "cb-v1" in tpl.headers["content-disposition"]
    reparsed = cw.parse(tpl.content, catalogue=CAT, project_id=P)
    assert cw.versus_current(store["cost_basis_version"][0], reparsed["configuration"])["unchanged"]


def test_a_boundary_conflict_saves_a_draft_and_an_unreadable_entry_saves_nothing(client):
    c, store, fn, _ = client
    fn["f"] = "ENGINEERING"
    data = _bytes(_workbook(boundary={"scope.electrolysis": "EXCLUDED"}))
    pv = _preview(c, data)
    assert _commit(c, data, pv["file_sha256"], "cost_basis").status_code == 201
    assert store["cost_basis_version"][-1]["status"] == "DRAFT" and store["cost_basis_version"][-1]["open_issues"]
    bad = _bytes(_workbook(lines=[{**LINES[0], "source": None}]))
    pv = _preview(c, bad)
    r = _commit(c, bad, pv["file_sha256"], "cost_basis")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "WORKBOOK_HAS_BLOCKING_ENTRIES"
    assert len(store["cost_basis_version"]) == 1


def test_financing_is_recorded_as_a_draft_and_promoted_only_on_an_independent_review(client):
    c, store, fn, bases = client
    data = _bytes(_fin_wb())
    pv = _preview(c, data)
    fin = pv["tabs"]["financing"]
    assert fin["can_commit"] and fin["would_save_as"] == "DRAFT" and fin["limitations"] == []
    assert fin["funding"]["remaining_need_eur"] == 250e6 and fin["funding"]["pipeline_total_eur"] == 50e6
    fn["f"] = "ENGINEERING"                                                   # engineering may not save financing
    assert _commit(c, data, pv["file_sha256"], "financing").status_code == 403
    fn["f"] = "FINANCE_TREASURY"
    ok = _commit(c, data, pv["file_sha256"], "financing")
    assert ok.status_code == 201, ok.text
    draft = store["financing_case_version"][0]
    assert draft["status"] == "DRAFT" and draft["terms"]["debt_eur"]["standing"] == "TERM_SHEET"
    imp = store["workbook_import"][0]
    assert imp["target_ref"] == draft["version_id"] and all(x["source_id"] for x in imp["declared"]["capital_sources"])
    # promotion: a NEW, ELIGIBLE version of the same case
    pr = c.post(f"/api/v1/calculation-chain/{P}/financing/{draft['version_id']}/promote")
    assert pr.status_code == 201, pr.text
    eligible = store["financing_case_version"][-1]
    assert eligible["status"] == "ELIGIBLE" and eligible["case_id"] == draft["case_id"]
    assert eligible["supersedes_version_id"] == draft["version_id"] and eligible["fci_eur"] == 300e6
    assert eligible["uses_total_eur"] == 340e6 and len(eligible["funding_plan"]["sources"]) == 5
    assert all(u["use_id"] for u in eligible["funding_plan"]["uses"])


def test_a_draft_without_an_independent_review_is_recorded_but_not_promoted(client):
    c, store, fn, bases = client
    bases["CLM-REVIEWED"]["review_basis"] = "OWNER_INTERNAL"
    data = _bytes(_fin_wb(fields={"financing.debt_tenor_years": None}))
    pv = _preview(c, data)
    fin = pv["tabs"]["financing"]
    assert fin["can_commit"] and {l["code"] for l in fin["limitations"]} == {
        "TEA_NOT_INDEPENDENTLY_REVIEWED", "TERMS_MISSING"}
    assert _commit(c, data, pv["file_sha256"], "financing").status_code == 201
    draft = store["financing_case_version"][-1]
    assert draft["debt_tenor_years"] is None
    pr = c.post(f"/api/v1/calculation-chain/{P}/financing/{draft['version_id']}/promote")
    assert pr.status_code == 409 and pr.json()["detail"]["code"] == "REVIEW_NOT_INDEPENDENT"


def test_unreconciled_grants_are_recorded_and_block_promotion(client):
    c, store, fn, bases = client
    data = _bytes(_fin_wb(fields={"financing.grant_eur": 10e6}))
    pv = _preview(c, data)
    assert _commit(c, data, pv["file_sha256"], "financing").status_code == 201
    draft = store["financing_case_version"][-1]
    assert draft["grant_eur"] == 10e6 and "GRANTS_UNRECONCILED" in {l["code"] for l in draft["limitations"]}
    pr = c.post(f"/api/v1/calculation-chain/{P}/financing/{draft['version_id']}/promote")
    assert pr.status_code == 409 and pr.json()["detail"]["code"] == "DRAFT_HAS_OPEN_LIMITATIONS"


def test_a_plan_with_unknown_uses_is_recorded_but_not_promoted(client):
    c, store, fn, bases = client
    data = _bytes(_fin_wb(uses=USES[:2]))
    pv = _preview(c, data)
    assert "USES_INCOMPLETE" in {l["code"] for l in pv["tabs"]["financing"]["limitations"]}
    assert _commit(c, data, pv["file_sha256"], "financing").status_code == 201
    draft = store["financing_case_version"][-1]
    pr = c.post(f"/api/v1/calculation-chain/{P}/financing/{draft['version_id']}/promote")
    assert pr.status_code == 409 and pr.json()["detail"]["code"] == "FUNDING_UNRECONCILED"


def test_a_reimport_finds_its_case_and_sources_by_their_ids_not_by_names(client):
    c, store, fn, bases = client
    data = _bytes(_fin_wb())
    pv = _preview(c, data)
    _commit(c, data, pv["file_sha256"], "financing")
    first = store["financing_case_version"][-1]
    ids = {x["name"]: x["source_id"] for x in store["workbook_import"][-1]["declared"]["capital_sources"]}
    tpl = c.get(f"/api/v1/cost-basis/{P}/workbook/template").content
    pv = _preview(c, tpl)
    assert pv["tabs"]["financing"].get("unchanged") and not pv["tabs"]["financing"]["can_commit"]
    # amend in the downloaded workbook: a term changes, a source is RENAMED; ids stay
    wb = load_workbook(io.BytesIO(tpl))
    _set(wb, "Financing", "financing.debt_eur", 170e6, source="term sheet v2", standing="TERM_SHEET")
    ws = wb["Financing"]
    for row in ws.iter_rows():
        if row[2].value == "Senior bank debt":
            row[2].value = "Senior debt (club of three banks)"
    amended = _bytes(wb)
    pv = _preview(c, amended)
    assert pv["tabs"]["financing"]["can_commit"], pv["tabs"]["financing"]["report"]
    assert _commit(c, amended, pv["file_sha256"], "financing").status_code == 201
    second = store["financing_case_version"][-1]
    assert second["case_id"] == first["case_id"] and second["supersedes_version_id"] == first["version_id"]
    stack = store["workbook_import"][-1]["declared"]["capital_sources"]
    assert len(stack) == 5 and {x["source_id"] for x in stack} == set(ids.values())
    assert [u["use_id"] for u in second["funding_plan"]["uses"]] == [u["use_id"] for u in first["funding_plan"]["uses"]]
    assert next(x for x in stack if x["source_id"] == ids["Senior bank debt"])["name"] == \
        "Senior debt (club of three banks)"
    wb = load_workbook(io.BytesIO(amended))
    _set(wb, "Financing", "financing.case_id", "not-a-case")
    pv = _preview(c, _bytes(wb))
    assert not pv["tabs"]["financing"]["can_commit"]


def test_the_offtake_tab_saves_through_the_card_path_and_declares_its_sources(client):
    c, store, fn, _ = client
    fn["f"] = "COMMERCIAL"
    data = _bytes(_fin_wb())
    pv = _preview(c, data)
    assert pv["tabs"]["offtake"]["can_commit"]
    ok = _commit(c, data, pv["file_sha256"], "offtake")
    assert ok.status_code == 201 and ok.json()["changed"] and store["card"]["take_or_pay_pct"] == 80.0
    assert "confirms" in ok.json()["note"] and len(store["workbook_import"]) == 1
    assert _commit(c, data, pv["file_sha256"], "offtake").status_code == 409
    tpl = c.get(f"/api/v1/cost-basis/{P}/workbook/template")
    t = cw.parse_all(tpl.content, catalogue=CAT, project_id=P)["tabs"]["offtake"]
    assert t["card"] == store["card"] and t["declared"]["buyers"]["#1"]["source"] == "HoT 1 Oct 2026"
