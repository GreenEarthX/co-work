"""The calculation chain's rules (core/calculation_chain.py, JML 2026-11-18). Offline, no database."""
from __future__ import annotations

import pytest

from app.core import calculation_chain as cc
from app.core.plant_builder import EQUIPMENT_CATALOG

CAT = {i.id: i for i in EQUIPMENT_CATALOG}
CONFIG = {"molecule": "E_METHANOL", "capacity_factor": 0.6, "power_price_eur_mwh": 55.0, "water_price_eur_m3": 2.5,
          "contingency_pct": 0.1, "wacc_pct": 0.08, "project_life_years": 25, "labour_count": 45,
          "labour_cost_eur_year": 65_000,
          "equipment": [{"equipment_id": "PEM_ELEC_120MW", "quantity": 1},
                        {"equipment_id": "MEOH_SYNTH_50KT", "quantity": 1},
                        {"equipment_id": "SITE_PREP", "quantity": 1}]}
LINES = [{"equipment_id": "PEM_ELEC_120MW", "quantity": 1, "installed_cost_eur": 87_750_000, "annual_output_tonnes": 11_680},
         {"equipment_id": "MEOH_SYNTH_50KT", "quantity": 1, "installed_cost_eur": 38_640_000, "annual_output_tonnes": 50_000},
         {"equipment_id": "SITE_PREP", "quantity": 1, "installed_cost_eur": 15_000_000, "annual_output_tonnes": 0}]
RESULT = {"capex": {"total_capex_eur": 126_400_000},
          "opex": {"total_annual_opex_eur": 40_000_000, "annual_om_eur": 2_000_000, "annual_insurance_eur": 600_000},
          "output": {"annual_output_tonnes": 67_520, "total_annual_power_mwh": 630_720, "total_annual_water_m3": 0},
          "equipment_lines": LINES}
STATED_TEA = {"process_type": {"value": "Fluids", "basis": "liquid/gas process"},
              "loc_factor": {"value": 1.0, "basis": "local installed prices"},
              "feedstocks": {"hydrogen": {"on_site_t_per_year": 11_680, "basis": "electrolyser"},
                             "co2": {"on_site_t_per_year": 50_000, "basis": "capture unit"}}}
OWNER = "owner_co"


def _cb():
    product = cc.product_output(CONFIG, CAT)
    return {**cc.cost_basis_record(project_id="p", owner_tenant=OWNER, configuration=CONFIG, result=RESULT,
                                   product=product, catalogue_hash="c" * 64, previous=None, saved_by="eng",
                                   saved_by_function="ENGINEERING"), "saved_at": "2026-11-18"}


def _tea_inputs(cb, balance=None):
    return {"calculation_boundary": {"basis": "QUOTE_LINES"},
            "openpytea_config": {"equipment": [{"name": f"{l['equipment_id']} x{l['quantity']}",
                                                "purchased_cost": l["installed_cost_eur"]} for l in LINES]},
            "feedstock_balance": balance if balance is not None else [
                {"feedstock": "hydrogen", "status": "COVERED", "required_t_per_year": 5625.0,
                 "on_site_t_per_year": 11680.0, "on_site_basis": "electrolyser"}],
            "defaults_used": [{"name": "openpytea.osbl_factor", "value": 0.3, "basis": "default"}],
            "request": {"plant_process_type": "Fluids", "quote_plant": {"loc_factor": 1.0, "loc_factor_basis": "local",
                        "on_site_supply": {"hydrogen": {"t_per_year": 11680, "basis": "electrolyser"}},
                        "variable_opex": {}}}}


def _base(cb, **kw):
    return {"claim_id": "CLM-1", "state": "verified", "cost_basis_version_id": cb["version_id"],
            "cost_basis_sha256": cb["content_sha256"], "cost_basis_hash": "h" * 64, "capex_eur": 300e6,
            "opex_eur_per_year": 30e6, "nameplate_capacity": 50000.0, "run_by": "eng", "review_basis": "INDEPENDENT",
            "tea_inputs": _tea_inputs(cb), **kw}


TERMS = {"debt_eur": {"value": 180e6, "source": "term sheet draft"},
         "interest_rate": {"value": 0.06, "source": "indicative"},
         "debt_tenor_years": {"value": 15, "source": "indicative"}}


def test_product_output_counts_only_the_product_lines():
    p = cc.product_output(CONFIG, CAT)
    assert p["nameplate_t_per_year"] == 50000.0
    assert p["product_lines"] == ["MEOH_SYNTH_50KT"]      # the electrolyser makes H2, not methanol
    assert p["basis"] == "LITERAL_CAPACITY_NO_RUN_TIME"


def test_no_product_line_is_refused():
    with pytest.raises(cc.ChainError) as e:
        cc.product_output({**CONFIG, "equipment": [{"equipment_id": "PEM_ELEC_120MW"}]}, CAT)
    assert e.value.code == "NO_PRODUCT_LINE"


def test_cost_basis_hash_covers_configuration_and_result():
    a = _cb()
    b = cc.cost_basis_record(project_id="p", owner_tenant=OWNER, configuration={**CONFIG, "capacity_factor": 0.7},
                             result=RESULT, product=cc.product_output(CONFIG, CAT), catalogue_hash="c" * 64,
                             previous=None, saved_by="eng", saved_by_function="ENGINEERING")
    assert a["content_sha256"] != b["content_sha256"]
    nxt = cc.cost_basis_record(project_id="p", owner_tenant=OWNER, configuration=CONFIG, result=RESULT,
                               product=a["result"]["product"], catalogue_hash="c" * 64, previous=a, saved_by="eng",
                               saved_by_function="ENGINEERING")
    assert nxt["version_number"] == 2 and nxt["supersedes_version_id"] == a["version_id"]


def test_tea_request_prices_the_cost_basis_lines_in_quote_mode():
    r = cc.tea_request(_cb(), fuel_id="E_METHANOL", pathway_id="p:cb", stated=STATED_TEA)
    q = r["quote_plant"]
    assert [e["installed_cost"] for e in q["equipment"]] == [l["installed_cost_eur"] for l in LINES]
    assert q["contingency"] == 0.1 and q["operators_hired"] == 45
    assert q["operator_hourly_rate"] * 1960 == pytest.approx(65_000)
    # per-day at full rate: OpenPyTEA multiplies by 365 x utilisation, so the annual power is recovered
    assert q["variable_opex"]["electricity"]["consumption"] * 365 * 0.6 == pytest.approx(630_720)
    assert q["variable_opex"]["electricity"]["unit"] == "MWh/day" and "water" not in q["variable_opex"]
    assert set(q["on_site_supply"]) == {"hydrogen", "co2"} and r["plant_process_type"] == "Fluids"
    assert r["nameplate_capacity"] == 50000.0


@pytest.mark.parametrize("missing", ["process_type", "loc_factor"])
def test_tea_inputs_that_would_default_must_be_stated(missing):
    stated = {k: v for k, v in STATED_TEA.items() if k != missing}
    with pytest.raises(cc.ChainError) as e:
        cc.tea_request(_cb(), fuel_id="E_METHANOL", pathway_id="p", stated=stated)
    assert e.value.code == "TEA_INPUT_REQUIRED"


def test_a_feedstock_may_be_partly_on_site_and_partly_bought():
    stated = {**STATED_TEA, "feedstocks": {"co2": {"on_site_t_per_year": 50_000, "basis": "capture",
                                                   "price_eur_per_unit": 0.05, "unit": "kg/day",
                                                   "consumption_per_day": 32_500, "source": "supplier quote"}}}
    q = cc.tea_request(_cb(), fuel_id="E_METHANOL", pathway_id="p", stated=stated)["quote_plant"]
    assert "co2" in q["on_site_supply"] and q["variable_opex"]["co2"]["unit"] == "kg/day"


def test_differences_are_reported_and_physical_checks_are_judged():
    cb = _cb()
    checks = {c["check"]: c for c in cc.cost_basis_vs_tea(cb, _base(cb))}
    assert checks["TEA priced from this saved cost basis"]["result"] == "PASS"
    assert checks["TEA priced the cost basis's own lines (quote mode)"]["result"] == "PASS"
    assert checks["Every cost basis line priced in the TEA, at its installed cost"]["result"] == "PASS"
    assert checks["Feedstock balance: hydrogen"]["result"] == "PASS"
    capex = checks["CAPEX: Cost Basis vs TEA fixed capital"]
    assert capex["result"] == "REPORTED" and capex["difference"] == 300e6 - 126.4e6
    assert checks["Cost Basis screen output"]["result"] == "REPORTED"


def test_a_generic_train_a_missing_line_or_a_feedstock_shortfall_fails():
    cb = _cb()
    generic = _base(cb, tea_inputs=None)
    assert "TEA priced the cost basis's own lines (quote mode)" in cc.failed(cc.cost_basis_vs_tea(cb, generic))
    ti = _tea_inputs(cb)
    ti["openpytea_config"]["equipment"] = ti["openpytea_config"]["equipment"][:2]
    assert "Every cost basis line priced in the TEA, at its installed cost" in cc.failed(
        cc.cost_basis_vs_tea(cb, _base(cb, tea_inputs=ti)))
    short = _tea_inputs(cb, [{"feedstock": "co2", "status": "SHORTFALL", "required_t_per_year": 61875.0,
                              "on_site_t_per_year": 50000.0, "shortfall_t_per_year": 11875.0}])
    assert "Feedstock balance: co2" in cc.failed(cc.cost_basis_vs_tea(cb, _base(cb, tea_inputs=short)))


@pytest.mark.parametrize("reviewer,expected", [
    ({"user_id": "cfo", "company_id": OWNER, "business_function": "EXECUTIVE"}, "OWNER_INTERNAL"),
    ({"user_id": "ie", "company_id": "ie_co", "business_function": "ENGINEERING"}, "INDEPENDENT"),
])
def test_review_standing(reviewer, expected):
    assert cc.review_standing(reviewer=reviewer, run_by="eng", cost_basis_saved_by="eng", owner_tenant=OWNER,
                              appointed_ie=expected == "INDEPENDENT") == expected


@pytest.mark.parametrize("reviewer,code", [
    ({"user_id": "eng", "company_id": OWNER, "business_function": "EXECUTIVE"}, "SELF_REVIEW"),
    ({"user_id": "x", "company_id": OWNER, "business_function": "COMMERCIAL"}, "NOT_A_REVIEWER"),
    ({"user_id": "bank", "company_id": "bank_co", "business_function": "FINANCE_TREASURY"}, "NOT_A_REVIEWER"),
    ({"user_id": "ie", "company_id": OWNER, "business_function": "ENGINEERING"}, "NOT_A_REVIEWER"),
])
def test_review_refusals(reviewer, code):
    with pytest.raises(cc.ChainError) as e:
        cc.review_standing(reviewer=reviewer, run_by="eng", cost_basis_saved_by="eng", owner_tenant=OWNER,
                           appointed_ie=reviewer["user_id"] == "ie")
    assert e.value.code == code


def test_financing_needs_a_reviewed_base_case_and_sources():
    cb = _cb()
    with pytest.raises(cc.ChainError) as e:
        cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=_base(cb, state="submitted"),
                            terms=TERMS, previous=None, saved_by="cfo")
    assert e.value.code == "TEA_NOT_REVIEWED"
    with pytest.raises(cc.ChainError) as e:
        cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=_base(cb),
                            terms={**TERMS, "interest_rate": {"value": 0.06, "source": " "}}, previous=None,
                            saved_by="cfo")
    assert e.value.code == "SOURCE_REQUIRED"
    with pytest.raises(cc.ChainError) as e:
        cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=_base(cb),
                            terms={**TERMS, "debt_eur": {"value": 301e6, "source": "x"}}, previous=None, saved_by="cfo")
    assert e.value.code == "DEBT_EXCEEDS_FCI"
    with pytest.raises(cc.ChainError) as e:
        cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=_base(cb, tea_inputs=None), terms=TERMS,
                            previous=None, saved_by="cfo")
    assert e.value.code == "TEA_NOT_FROM_QUOTE_MODE"
    fin = cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=_base(cb), terms=TERMS, previous=None,
                              saved_by="cfo")
    assert fin["fci_eur"] == 300e6 and fin["terms"]["debt_eur"]["verification_status"] == "ASSUMPTION"


def _fin(cb):
    return cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=_base(cb), terms=TERMS, previous=None,
                               saved_by="cfo")


STATED = {"product_price_eur_t": {"value": 1200, "source": "registry market_spot_price"},
          "tax_rate": {"value": 0.25, "source": "owner"}, "depreciation_years": {"value": 20, "source": "owner"},
          "cost_of_equity": {"value": 0.12, "source": "owner"}}


def test_returns_inputs_come_from_the_chain():
    cb = _cb()
    out = cc.returns_inputs(cost_basis=cb, base_case=_base(cb), financing=_fin(cb), stated=STATED,
                            project_capex_eur=250e6, approved_gearing={"value": 0.65, "ref_id": "R", "source": "OIES"})
    i = out["inputs"]
    assert i["fci_eur"] == 300e6 and i["opex_y1_eur"] == 30e6 and i["operating_years"] == 25
    assert i["debt_eur"] == 180e6 and i["revenue_y1_eur"] == 1200 * 50000 * 0.6
    checks = {c["check"]: c["result"] for c in out["checks"]}
    assert checks["FCI = reviewed TEA CAPEX"] == "PASS"
    assert checks["Project record CAPEX vs reviewed TEA CAPEX"] == "REPORTED"
    assert {s for s in out["source_versions"]} == {"cost_basis", "tea_base_case", "financing_case"}
    names = {a["name"] for a in out["remaining_assumptions"]}
    assert {"product_price_eur_t", "tax_rate", "financing.debt_eur", "cost_basis.capacity_factor"} <= names


def test_a_chain_figure_cannot_be_stated():
    cb = _cb()
    with pytest.raises(cc.ChainError) as e:
        cc.returns_inputs(cost_basis=cb, base_case=_base(cb), financing=_fin(cb),
                          stated={**STATED, "fci_eur": {"value": 250e6, "source": "record"}},
                          project_capex_eur=None, approved_gearing=None)
    assert e.value.code == "CHAIN_CONFLICT"


def test_a_broken_link_is_refused():
    cb = _cb()
    fin = _fin(cb)
    with pytest.raises(cc.ChainError) as e:
        cc.returns_inputs(cost_basis=cb, base_case=_base(cb, claim_id="CLM-OTHER"), financing=fin, stated=STATED,
                          project_capex_eur=None, approved_gearing=None)
    assert e.value.code == "CHAIN_BROKEN"
    with pytest.raises(cc.ChainError) as e:
        cc.returns_inputs(cost_basis=cb, base_case=_base(cb, cost_basis_version_id="other"), financing=fin,
                          stated=STATED, project_capex_eur=None, approved_gearing=None)
    assert e.value.code == "CHAIN_BROKEN"


def test_only_an_independent_review_publishes():
    cb = _cb()
    with pytest.raises(cc.ChainError) as e:
        cc.returns_inputs(cost_basis=cb, base_case=_base(cb, review_basis="OWNER_INTERNAL"), financing=_fin(cb),
                          stated=STATED, project_capex_eur=None, approved_gearing=None)
    assert e.value.code == "REVIEW_NOT_INDEPENDENT"


def test_a_failed_check_blocks_publication():
    cb = _cb()
    short = _tea_inputs(cb, [{"feedstock": "co2", "status": "NOT_COVERED", "required_t_per_year": 1.0}])
    base = _base(cb, tea_inputs=short)
    fin = cc.financing_record(project_id="p", owner_tenant=OWNER, base_case=base, terms=TERMS, previous=None,
                              saved_by="cfo")
    with pytest.raises(cc.ChainError) as e:
        cc.returns_inputs(cost_basis=cb, base_case=base, financing=fin, stated=STATED,
                          project_capex_eur=None, approved_gearing=None)
    assert e.value.code == "CHECKS_FAILED"


def test_tea_defaults_are_listed_and_the_previous_version_is_reconciled():
    cb = _cb()
    prev = {"version_id": "v1", "version_number": 1, "content_sha256": "c5de", "withdrawal": {"reason": "boundary"},
            "inputs": {"fci_eur": 175e6, "opex_y1_eur": 52e6, "operating_years": 25}, "results": {"unlevered_irr": -0.1}}
    out = cc.returns_inputs(cost_basis=cb, base_case=_base(cb), financing=_fin(cb), stated=STATED,
                            project_capex_eur=None, approved_gearing=None, previous=prev)
    names = {a["name"] for a in out["remaining_assumptions"]}
    assert {"tea.openpytea.osbl_factor", "tea.loc_factor", "tea.on_site.hydrogen"} <= names
    r = out["reconciliation_vs_previous"]
    assert r["previous_withdrawn"] and r["previous_withdrawal_reason"] == "boundary"
    assert {row["item"] for row in r["inputs_changed"]} >= {"fci_eur", "opex_y1_eur"}


def test_every_tea_request_field_is_accepted_by_the_platform_route():
    """The chain's TEA body must pass the platform route's no-extras rule (it caught plant_process_type)."""
    from app.api.v1.routes_tea import ComputeRequest
    ComputeRequest(**cc.tea_request(_cb(), fuel_id="E_METHANOL", pathway_id="p", stated=STATED_TEA))
