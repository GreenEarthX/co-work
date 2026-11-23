"""Returns cases: boundary, scenario, downside and provenance (handoff v4, tasks 6 and 8).

Each test states its rule and builds its own inputs.
"""
import pytest

from pf_engine.core.returns import compute_returns

BASE = dict(fci_eur=100.0, operating_years=10, revenue_y1_eur=30.0, opex_y1_eur=10.0,
            tax_rate=0.25, depreciation_years=10, pre_fid_spend_eur=[5.0, 5.0],
            debt_eur=60.0, interest_rate=0.06, debt_tenor_years=8, cost_of_equity=0.12)


def test_from_fid_excludes_pre_fid_spend_and_says_so():
    """Rule: a FROM_FID case treats pre-FID spend as sunk and excluded; it is a
    separately identified case, labelled on the result, never a full-project return."""
    full = compute_returns(**BASE)
    from_fid = compute_returns(**BASE, valuation_boundary="FROM_FID")
    assert full["valuation_boundary"] == "FULL_PROJECT" and full["devex_eur"] == 10.0
    assert from_fid["valuation_boundary"] == "FROM_FID"
    assert from_fid["devex_eur"] == 0.0 and from_fid["devex_excluded_eur"] == 10.0
    assert from_fid["flows"]["first_period"] == 0
    assert "NOT a full-project return" in from_fid["valuation_boundary_label"]
    # Different cases give different figures; neither is "the" return.
    assert from_fid["unlevered_irr"] > full["unlevered_irr"]


def test_an_unknown_boundary_or_an_unnamed_scenario_is_refused():
    with pytest.raises(ValueError):
        compute_returns(**BASE, valuation_boundary="PARTIAL")
    with pytest.raises(ValueError):
        compute_returns(**BASE, scenario="  ")


def test_downside_rows_rederive_the_model_and_hurt():
    """Rule: returns are shown with downside sensitivities — CAPEX overrun, COD delay,
    revenue and OPEX shocks, interest rate — each a full re-run, NPV at the base hurdle."""
    r = compute_returns(**BASE)
    rows = {row["id"]: row for row in r["downside"]["rows"]}
    for family in ("CAPEX_PLUS", "COD_DELAY", "REVENUE_MINUS", "OPEX_PLUS", "RATE_PLUS"):
        assert any(k.startswith(family) for k in rows), family
    assert rows["CAPEX_PLUS_10"]["unlevered_irr"] < r["unlevered_irr"]
    assert rows["REVENUE_MINUS_20"]["npv_unlevered_eur"] < rows["REVENUE_MINUS_10"]["npv_unlevered_eur"] < r["npv_unlevered_eur"]
    assert rows["OPEX_PLUS_10"]["dscr_min"] < r["debt_metrics"]["dscr_min"]
    assert rows["RATE_PLUS_100BP"]["levered_irr"] < r["levered_irr"]
    assert rows["COD_DELAY_12M"]["unlevered_irr"] < r["unlevered_irr"]
    assert r["downside"]["shock_set_status"] == "GEX proposed"


def test_provenance_travels_with_the_figures():
    """Rule: every computed result identifies its inputs, the TEA case and assumptions
    supplied (or that none was), the model version, boundary, timing, the checks run
    with outcomes, and limitations."""
    r1 = compute_returns(**BASE)
    r2 = compute_returns(**BASE)
    p = r1["provenance"]
    assert p["inputs_sha256"] == r2["provenance"]["inputs_sha256"]
    assert p["calculation"]["model_version"] == r1["model_version"]
    assert p["tea_case"]["status"] == "NOT_SUPPLIED"
    assert {c["check"] for c in p["validation_checks"]} >= {
        "DEVEX outside the construction schedule", "unlevered IRR has a single root"}
    assert all(c["outcome"] in ("PASS", "WARN", "NOT_APPLICABLE") for c in p["validation_checks"])
    assert p["limitations"] and "not mean the forecast outcome is assured" in p["validity"]

    supplied = {"tea_case": {"tea_case_id": "TEA-1", "input_versions": {"capex": 3}},
                "assumptions": [{"name": "revenue_y1_eur", "value": 30.0, "source": "offtake card",
                                 "verification_status": "UNVERIFIED"}]}
    p3 = compute_returns(**BASE, provenance_inputs=supplied)["provenance"]
    assert p3["tea_case"]["tea_case_id"] == "TEA-1"
    assert p3["assumptions"][0]["verification_status"] == "UNVERIFIED"
    # A changed input changes the hash.
    assert compute_returns(**dict(BASE, revenue_y1_eur=31.0))["provenance"]["inputs_sha256"] != p["inputs_sha256"]
