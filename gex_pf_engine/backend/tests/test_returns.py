"""
Return metrics (core/returns.py): unlevered and levered IRR, NPV, ROI, ROE,
hurdle rate. Each test pins one identity that can be checked by hand, so a
wrong sign or an off-by-one period fails here and not in front of a CFO.
"""
import math

import pytest

from pf_engine.core.engine import ProjectFinanceEngine
from pf_engine.core.returns import (
    annuity_schedule, compute_returns, hurdle_rate, irr, npv,
)

BASE = dict(fci_eur=1000.0, operating_years=10, revenue_y1_eur=400.0, opex_y1_eur=150.0,
            tax_rate=0.25, depreciation_years=10, cost_of_equity=0.12)


def test_irr_of_a_one_year_loan_is_its_rate():
    assert irr([-100.0, 110.0]) == pytest.approx(0.10, abs=1e-8)


def test_irr_recovers_the_rate_an_annuity_was_priced_at():
    price = sum(10.0 / 1.08 ** t for t in range(1, 21))
    flows = [-price] + [10.0] * 20
    assert irr(flows) == pytest.approx(0.08, abs=1e-8)
    assert npv(0.08, flows) == pytest.approx(0.0, abs=1e-9)


def test_irr_is_none_without_a_sign_change():
    assert irr([1.0, 2.0, 3.0]) is None
    assert irr([-1.0, -2.0]) is None
    assert irr([]) is None


def test_irr_is_negative_when_the_money_does_not_come_back():
    assert irr([-100.0, 30.0, 30.0, 30.0]) < 0


def test_annuity_repays_exactly_the_principal():
    rows = annuity_schedule(195e6, 0.055, 15)
    assert sum(repaid for _, repaid in rows) == pytest.approx(195e6)
    payments = {round(i + p, 2) for i, p in rows}
    assert len(payments) == 1                      # level payment


def test_without_debt_levered_equals_unlevered():
    r = compute_returns(**BASE)
    assert r["levered_irr"] == pytest.approx(r["unlevered_irr"], abs=1e-9)
    assert r["equity_invested_eur"] == r["total_investment_eur"] == 1000.0
    assert r["roe_avg_annual"] == pytest.approx(r["roi_avg_annual"])


def test_fci_is_the_year_zero_outflow():
    r = compute_returns(**BASE)
    assert r["fci_eur"] == 1000.0
    assert r["flows"]["first_period"] == 0
    assert r["flows"]["unlevered"][0] == -1000.0


def test_hand_checked_unlevered_year():
    # EBITDA 250, depreciation 100, tax 25% of 150 = 37.5, FCF 212.5, NOPAT 112.5.
    r = compute_returns(**BASE)
    y1 = r["schedule"][0]
    assert (y1["ebitda"], y1["depreciation"], y1["tax_unlevered"]) == (250.0, 100.0, 37.5)
    assert y1["fcf_unlevered"] == 212.5
    assert r["roi_avg_annual"] == pytest.approx(112.5 / 1000.0)
    assert r["roi_cumulative"] == pytest.approx((2125.0 - 1000.0) / 1000.0)
    assert r["payback_years"] == pytest.approx(1000.0 / 212.5)


def test_debt_cheaper_than_the_project_return_lifts_equity_irr():
    r = compute_returns(**BASE, debt_eur=600.0, interest_rate=0.05, debt_tenor_years=10)
    assert r["equity_at_fid_eur"] == 400.0
    assert r["levered_irr"] > r["unlevered_irr"]
    y1 = r["schedule"][0]
    assert y1["interest"] == pytest.approx(30.0)
    assert y1["net_income"] == pytest.approx((250.0 - 100.0 - 30.0) * 0.75)


def test_pre_fid_spend_sits_before_year_zero_and_is_equity():
    plain = compute_returns(**BASE, debt_eur=600.0, interest_rate=0.05, debt_tenor_years=10)
    r = compute_returns(**BASE, debt_eur=600.0, interest_rate=0.05, debt_tenor_years=10,
                        pre_fid_spend_eur=[20.0, 30.0])
    assert r["devex_eur"] == 50.0
    assert r["total_investment_eur"] == 1050.0
    assert r["equity_invested_eur"] == 450.0                   # 400 at FID + 50 DEVEX
    assert r["flows"]["first_period"] == -2
    assert r["flows"]["levered"][:3] == [-20.0, -30.0, -400.0]
    assert r["unlevered_irr"] < plain["unlevered_irr"]
    assert r["levered_irr"] < plain["levered_irr"]


def test_npv_is_valued_at_year_zero_so_earlier_spend_is_compounded():
    r = compute_returns(**BASE, pre_fid_spend_eur=[100.0])
    h = r["hurdle"]["project_hurdle"]
    by_hand = -100.0 * (1 + h) - 1000.0 + sum(
        row["fcf_unlevered"] / (1 + h) ** row["year"] for row in r["schedule"])
    assert r["npv_unlevered_eur"] == pytest.approx(by_hand)


def test_npv_at_the_irr_is_zero():
    r = compute_returns(**BASE, debt_eur=600.0, interest_rate=0.05, debt_tenor_years=10,
                        pre_fid_spend_eur=[20.0, 30.0], residual_value_eur=80.0)
    f = r["flows"]
    assert npv(r["unlevered_irr"], f["unlevered"], f["first_period"]) == pytest.approx(0.0, abs=1e-4)
    assert npv(r["levered_irr"], f["levered"], f["first_period"]) == pytest.approx(0.0, abs=1e-4)


def test_hurdle_rate_arithmetic():
    h = hurdle_rate(equity_eur=40.0, debt_eur=60.0, cost_of_debt=0.05, tax_rate=0.25,
                    risk_free_rate=0.03, equity_beta=1.2, equity_risk_premium=0.05,
                    country_risk_premium=0.01, technology_risk_premium=0.02,
                    project_risk_premium=0.01)
    assert h["cost_of_equity_basis"] == "build-up"
    assert h["cost_of_equity"] == pytest.approx(0.03 + 1.2 * 0.05 + 0.01 + 0.02)      # 12%
    assert h["wacc_after_tax"] == pytest.approx(0.4 * 0.12 + 0.6 * 0.05 * 0.75)       # 7.05%
    assert h["project_hurdle"] == pytest.approx(0.0705 + 0.01)
    assert h["equity_hurdle"] == pytest.approx(0.12)


def test_stated_cost_of_equity_wins_over_the_build_up():
    h = hurdle_rate(equity_eur=1.0, debt_eur=0.0, cost_of_debt=0.0, tax_rate=0.25,
                    cost_of_equity=0.15, risk_free_rate=0.03, equity_beta=1.0,
                    equity_risk_premium=0.05)
    assert (h["cost_of_equity"], h["cost_of_equity_basis"]) == (0.15, "stated")


def test_hurdle_rate_refuses_to_guess():
    with pytest.raises(ValueError, match="cost_of_equity"):
        hurdle_rate(equity_eur=1.0, debt_eur=1.0, cost_of_debt=0.05, tax_rate=0.25)


def test_hurdle_test_reports_the_spread():
    r = compute_returns(**BASE)
    t = r["hurdle_test"]["unlevered"]
    assert t["clears"] is (r["unlevered_irr"] >= 0.12)
    assert t["spread_bps"] == pytest.approx((r["unlevered_irr"] - 0.12) * 10_000, abs=0.05)


@pytest.mark.parametrize("bad, message", [
    (dict(fci_eur=0.0), "fci_eur"),
    (dict(tax_rate=1.0), "tax_rate"),
    (dict(debt_eur=1200.0, interest_rate=0.05, debt_tenor_years=10), "exceed the FCI"),
    (dict(debt_eur=600.0, interest_rate=0.05, debt_tenor_years=15), "debt_tenor_years"),
    (dict(pre_fid_spend_eur=[-5.0]), "negative"),
])
def test_inputs_that_would_give_a_misleading_answer_are_refused(bad, message):
    with pytest.raises(ValueError, match=message):
        compute_returns(**{**BASE, **bad})


def test_every_result_carries_its_definitions_and_limits():
    r = compute_returns(**BASE)
    assert "Fixed Capital Investment" in r["definitions"]["fci"]
    for key in ("unlevered_irr", "levered_irr", "npv_unlevered", "roi_avg_annual",
                "roe_avg_annual", "project_hurdle", "equity_hurdle"):
        assert key in r["definitions"]
    assert r["limitations"]


# ── Construction schedule: the scheduled case beside the screening case ─────

LEVERED = dict(BASE, debt_eur=600.0, interest_rate=0.05, debt_tenor_years=10)


def test_default_is_the_labelled_screening_case():
    r = compute_returns(**BASE)
    assert r["case"] == "SCREENING_FCI_YEAR_0"
    assert "screening" in r["case_label"].lower() and "no construction period" in r["case_label"]
    assert r["first_operating_period"] == 1 and r["idc_eur"] == 0.0
    assert "screening_case" not in r


def test_schedule_moves_capex_and_operations_but_not_the_total():
    r = compute_returns(**BASE, construction_schedule_eur=[300.0, 700.0])
    s = r["screening_case"]
    assert r["case"] == "SCHEDULED" and s["case"] == "SCREENING_FCI_YEAR_0"
    assert r["flows"]["unlevered"][:3] == [-300.0, -700.0, 212.5]
    assert s["flows"]["unlevered"][:2] == [-1000.0, 212.5]
    assert (r["first_operating_period"], s["first_operating_period"]) == (2, 1)
    d = r["difference"]["project_undiscounted_total_eur"]
    assert d["scheduled"] == pytest.approx(d["screening"])          # timing only
    assert r["unlevered_irr"] < s["unlevered_irr"]
    assert r["npv_unlevered_eur"] < s["npv_unlevered_eur"]
    assert r["payback_years"] == pytest.approx(s["payback_years"] + 1.0)


def test_screening_case_inside_a_scheduled_result_is_the_plain_calculation():
    plain = compute_returns(**LEVERED, pre_fid_spend_eur=[50.0])
    r = compute_returns(**LEVERED, pre_fid_spend_eur=[50.0],
                        construction_schedule_eur=[500.0, 300.0, 200.0])
    for key in ("unlevered_irr", "levered_irr", "npv_unlevered_eur", "npv_levered_eur",
                "payback_years", "equity_payback_years"):
        assert r["screening_case"][key] == pytest.approx(plain[key])
    # one hurdle for both cases, or the two NPVs would not compare
    assert r["hurdle"] == plain["hurdle"]


def test_equity_goes_in_before_debt_and_pays_interest_during_construction():
    r = compute_returns(**LEVERED, construction_schedule_eur=[500.0, 300.0, 200.0])
    rows = r["construction"]
    assert [(x["equity"], x["debt_draw"]) for x in rows] == [(400.0, 100.0), (0.0, 300.0), (0.0, 200.0)]
    assert [x["idc"] for x in rows] == pytest.approx([0.0, 5.0, 20.0])      # 5% of 100, then of 400
    assert r["idc_eur"] == pytest.approx(25.0)
    assert r["equity_invested_eur"] == pytest.approx(425.0)
    assert r["flows"]["levered"][:3] == pytest.approx([-400.0, -5.0, -20.0])
    assert r["flows"]["unlevered"][:3] == [-500.0, -300.0, -200.0]         # no financing in project flows
    assert r["levered_irr"] < r["screening_case"]["levered_irr"]


def test_grants_are_used_before_equity():
    r = compute_returns(**LEVERED, grant_eur=100.0, construction_schedule_eur=[500.0, 500.0])
    first = r["construction"][0]
    assert (first["grant"], first["equity"], first["debt_draw"]) == (100.0, 300.0, 100.0)


@pytest.mark.parametrize("schedule, message", [
    ([400.0, 500.0], "reconcile"),
    ([-100.0, 1100.0], "non-negative"),
])
def test_a_schedule_that_does_not_reconcile_to_the_fci_is_refused(schedule, message):
    with pytest.raises(ValueError, match=message):
        compute_returns(**BASE, construction_schedule_eur=schedule)


def test_devex_inside_the_schedule_is_named_as_the_likely_cause():
    with pytest.raises(ValueError, match="DEVEX belongs in pre_fid_spend_eur"):
        compute_returns(**BASE, pre_fid_spend_eur=[50.0], construction_schedule_eur=[550.0, 500.0])


def test_schedule_within_tolerance_is_scaled_to_the_fci():
    r = compute_returns(**BASE, construction_schedule_eur=[301.0, 702.0])       # 1003 vs 1000
    assert sum(x["capex"] for x in r["construction"]) == pytest.approx(1000.0)
    assert r["reconciliation"]["difference_eur"] == pytest.approx(3.0)


def test_ramp_up_scales_revenue_and_only_the_variable_share_of_opex():
    fixed = compute_returns(**BASE, ramp_up=[0.5])
    assert fixed["case"] == "SCHEDULED" and fixed["first_operating_period"] == 1
    y1 = fixed["schedule"][0]
    assert (y1["revenue"], y1["opex"], y1["ebitda"]) == (200.0, 150.0, 50.0)
    assert fixed["schedule"][1]["revenue"] == 400.0
    variable = compute_returns(**BASE, ramp_up=[0.5], opex_variable_share=1.0)
    assert variable["schedule"][0]["opex"] == 75.0
    with pytest.raises(ValueError, match="ramp_up"):
        compute_returns(**BASE, ramp_up=[1.5])


def test_scheduled_npv_at_its_irr_is_zero_and_timeline_matches_the_flows():
    r = compute_returns(**LEVERED, pre_fid_spend_eur=[20.0, 30.0],
                        construction_schedule_eur=[500.0, 300.0, 200.0], ramp_up=[0.6, 0.85])
    f = r["flows"]
    assert npv(r["unlevered_irr"], f["unlevered"], f["first_period"]) == pytest.approx(0.0, abs=1e-4)
    assert npv(r["levered_irr"], f["levered"], f["first_period"]) == pytest.approx(0.0, abs=1e-4)
    assert [row["phase"] for row in r["timeline"][:6]] == [
        "PRE_FID", "PRE_FID", "CONSTRUCTION", "CONSTRUCTION", "CONSTRUCTION", "OPERATIONS"]
    assert [row["project_flow"] for row in r["timeline"]] == f["unlevered"]
    assert r["timeline"][0]["period"] == -2 and r["schedule"][0]["period"] == 3


# ── Timing: COD, part years, and the assumptions stated with the result ─────

def test_timing_is_stated_and_defaults_to_the_end_of_the_last_construction_year():
    screening = compute_returns(**BASE)["timing"]
    assert (screening["cod_months_after_fid"], screening["first_operating_project_year"]) == (0, 1)
    t = compute_returns(**BASE, construction_schedule_eur=[300.0, 700.0])["timing"]
    assert (t["cod_months_after_fid"], t["first_operating_project_year"]) == (12, 2)
    assert t["first_year_operating_share"] == 1.0 and "default" in t["cod_basis"]
    assert any("FID date" in line for line in t["assumptions"])


def test_cod_inside_a_year_gives_a_part_first_year_and_a_part_last_year():
    r = compute_returns(**BASE, construction_schedule_eur=[300.0, 700.0], cod_months_after_fid=18)
    assert r["flows"]["unlevered"] == pytest.approx([-300.0, -700.0, 106.25] + [212.5] * 9 + [106.25])
    assert r["first_operating_period"] == 2
    first = r["schedule"][0]
    assert (first["operating_share"], first["revenue"], first["depreciation"]) == (0.5, 200.0, 50.0)
    assert r["schedule"][-1]["operating_share"] == 0.5
    assert r["timing"]["first_year_operating_share"] == 0.5 and r["timing"]["cod_basis"] == "stated"
    totals = r["difference"]["project_undiscounted_total_eur"]
    assert totals["scheduled"] == pytest.approx(totals["screening"])     # operating life is still 10 years
    assert r["roi_avg_annual"] == pytest.approx(112.5 / 1000.0)


def test_a_later_cod_lowers_the_project_return():
    def at(months):
        return compute_returns(**BASE, construction_schedule_eur=[300.0, 700.0],
                               cod_months_after_fid=months)["unlevered_irr"]
    assert at(12) > at(18) > at(24)


def test_capex_and_operations_can_share_a_project_year():
    r = compute_returns(**BASE, construction_schedule_eur=[300.0, 700.0], cod_months_after_fid=6)
    assert r["flows"]["unlevered"][:2] == pytest.approx([-300.0, -700.0 + 106.25])
    assert r["timeline"][1]["phase"] == "CONSTRUCTION+OPERATIONS"


def test_growth_runs_by_operating_year_through_a_part_year():
    r = compute_returns(**dict(BASE, revenue_growth=0.10), cod_months_after_fid=6)
    assert r["case"] == "SCHEDULED"
    assert r["schedule"][0]["revenue"] == pytest.approx(0.5 * 400.0)
    assert r["schedule"][1]["revenue"] == pytest.approx(0.5 * 400.0 + 0.5 * 440.0)


def test_interest_during_construction_stops_at_cod_and_runs_through_idle_years():
    part = compute_returns(**LEVERED, construction_schedule_eur=[500.0, 300.0, 200.0], cod_months_after_fid=18)
    assert [x["idc"] for x in part["construction"]] == pytest.approx([0.0, 5.0, 10.0])   # half of year 2
    idle = compute_returns(**LEVERED, construction_schedule_eur=[400.0, 600.0], cod_months_after_fid=36)
    assert [x["idc"] for x in idle["construction"]] == pytest.approx([0.0, 0.0, 30.0, 30.0])
    assert idle["first_operating_period"] == 4


@pytest.mark.parametrize("months, message", [(6, "after COD"), (-1, "between 0 and"), (500, "between 0 and")])
def test_a_cod_that_contradicts_the_schedule_is_refused(months, message):
    with pytest.raises(ValueError, match=message):
        compute_returns(**BASE, construction_schedule_eur=[300.0, 300.0, 400.0], cod_months_after_fid=months)


def test_lifetime_model_reports_a_number_not_tbd():
    summary = ProjectFinanceEngine("t").model_project_lifetime(
        capacity_mtpd=100.0, price_eur_kg=2.0, opex_eur_kg=0.8, total_capex=300e6,
        senior_debt_amount=180e6, interest_rate=0.055, tenor_years=15)["summary"]
    assert isinstance(summary["project_irr"], float) and math.isfinite(summary["project_irr"])
    assert "unlevered" in summary["project_irr_basis"]


# ── API ──────────────────────────────────────────────────────────────────────

def test_api_returns_the_metrics(service_client):
    r = service_client.post("/api/v1/model/returns/calculate?project_id=P1", json=BASE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == "P1"
    assert body["returns"]["unlevered_irr"] == pytest.approx(compute_returns(**BASE)["unlevered_irr"])


def test_api_takes_a_construction_schedule_and_refuses_one_that_does_not_reconcile(service_client):
    ok = service_client.post("/api/v1/model/returns/calculate",
                             json={**BASE, "construction_schedule_eur": [300.0, 700.0]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["returns"]["case"] == "SCHEDULED"
    assert ok.json()["returns"]["screening_case"]["case"] == "SCREENING_FCI_YEAR_0"
    bad = service_client.post("/api/v1/model/returns/calculate",
                              json={**BASE, "construction_schedule_eur": [300.0, 500.0]})
    assert bad.status_code == 422 and "reconcile" in bad.json()["detail"]


def test_api_answers_422_when_the_hurdle_cannot_be_computed(service_client):
    body = {k: v for k, v in BASE.items() if k != "cost_of_equity"}
    r = service_client.post("/api/v1/model/returns/calculate", json=body)
    assert r.status_code == 422 and "cost_of_equity" in r.json()["detail"]
