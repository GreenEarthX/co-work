"""Part C test 5 — independent financial expectations, and task 11 (part-year COD with ramp-up).

Business rule: the engine's unlevered and levered IRR, NPV, payback, ROI, ROE,
DSCR and LLCR must match values computed independently of the engine, with the
method written down (docs/validation/returns_expectations.md), within stated
tolerances. The expected values live in tests/validation/returns_expectations.json,
produced by tests/validation/independent_returns.py, which never imports the
engine. A changed expected value is a model change: record it in
docs/MODEL_CHANGE_REGISTER.md. LLCR is shown only because these cases pass.
"""
import json
from pathlib import Path

import pytest

from pf_engine.core.returns import LLCR_VALIDATION, compute_returns

DATA = json.loads((Path(__file__).parent / "validation" / "returns_expectations.json").read_text())
TOL = DATA["tolerances"]


def _close(actual, expected, kind):
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if kind == "npv_relative":
        return abs(actual - expected) <= TOL["npv_relative"] * max(1.0, abs(expected))
    return abs(actual - expected) <= TOL[kind]


ENGINE_KEYS = {  # expected key -> (where the engine reports it, tolerance kind)
    "unlevered_irr": (("unlevered_irr",), "irr"),
    "levered_irr": (("levered_irr",), "irr"),
    "npv_unlevered_eur": (("npv_unlevered_eur",), "npv_relative"),
    "npv_levered_eur": (("npv_levered_eur",), "npv_relative"),
    "payback_years": (("payback_years",), "payback"),
    "equity_payback_years": (("equity_payback_years",), "payback"),
    "roi_avg_annual": (("roi_avg_annual",), "ratio"),
    "roi_cumulative": (("roi_cumulative",), "ratio"),
    "roe_avg_annual": (("roe_avg_annual",), "ratio"),
    "dscr_min": (("debt_metrics", "dscr_min"), "ratio"),
    "dscr_avg": (("debt_metrics", "dscr_avg"), "ratio"),
    "llcr": (("debt_metrics", "llcr"), "ratio"),
    "wacc_after_tax": (("hurdle", "wacc_after_tax"), "ratio"),
    "project_hurdle": (("hurdle", "project_hurdle"), "ratio"),
    "idc_eur": (("idc_eur",), "npv_relative"),
}


def _get(result, path):
    for key in path:
        result = result[key]
    return result


@pytest.mark.parametrize("case", sorted(DATA["cases"]))
@pytest.mark.parametrize("metric", sorted(ENGINE_KEYS))
def test_engine_matches_independent_expectation(case, metric):
    """Each metric of each case equals the independently computed value."""
    spec = DATA["cases"][case]
    result = compute_returns(**spec["inputs"])
    path, kind = ENGINE_KEYS[metric]
    expected = spec["expected"][metric]
    actual = _get(result, path)
    assert _close(actual, expected, kind), f"{case} {metric}: engine {actual} vs expected {expected}"


def test_llcr_is_shown_only_as_validated():
    """LLCR is shown because the cases above pass; the status says so."""
    assert LLCR_VALIDATION["status"] == "VALIDATED"
    result = compute_returns(**DATA["cases"]["REFERENCE_BREIZH_SAF"]["inputs"])
    assert result["debt_metrics"]["llcr_status"] == "COMPUTED"


def test_no_debt_means_no_dscr_or_llcr_rather_than_a_number():
    """A metric that does not apply is absent, never zero."""
    inputs = dict(DATA["cases"]["OPERATING_INVENTED"]["inputs"], debt_eur=0.0, debt_tenor_years=0)
    dm = compute_returns(**inputs)["debt_metrics"]
    assert dm["dscr_min"] is None and dm["llcr"] is None


# ── Task 11: a part-year COD combined with ramp-up ───────────────────────────

def _part_year_ramp():
    """COD 30 months after FID (inside project year 3) with a two-year ramp-up.
    Expected values derived by hand from the written conventions, not from the engine."""
    return dict(fci_eur=120.0, operating_years=4, revenue_y1_eur=100.0, opex_y1_eur=40.0,
                opex_variable_share=0.5, ramp_up=[0.5, 0.8], tax_rate=0.0,
                depreciation_years=4, construction_schedule_eur=[60.0, 60.0],
                cod_months_after_fid=30, cost_of_equity=0.10)


def test_part_year_cod_with_ramp_up_prorates_the_ramped_years():
    """Rule: with COD inside a project year, the first project year holds the
    share after COD of operating year 1, and each later project year holds the
    rest of one operating year plus the start of the next; ramp-up applies by
    operating year from COD; OPEX scales by its variable share only.

    Operating years (ramp 0.5, 0.8, 1, 1): revenue 50, 80, 100, 100;
    OPEX 40*(1-0.5*(1-r)): 30, 36, 40, 40; EBITDA 20, 44, 60, 60.
    COD at month 30: first operating project year is 3 with share 0.5.
      project year 3: 0.5*20                = 10
      project year 4: 0.5*20 + 0.5*44       = 32
      project year 5: 0.5*44 + 0.5*60       = 52
      project year 6: 0.5*60 + 0.5*60       = 60
      project year 7: 0.5*60                = 30
    No tax and no maintenance, so free cash flow equals EBITDA.
    """
    r = compute_returns(**_part_year_ramp())
    assert r["first_operating_period"] == 3
    assert r["timing"]["first_year_operating_share"] == pytest.approx(0.5)
    by_period = {row["period"]: row["fcf_unlevered"] for row in r["schedule"]}
    assert by_period == pytest.approx({3: 10.0, 4: 32.0, 5: 52.0, 6: 60.0, 7: 30.0})
    assert sum(by_period.values()) == pytest.approx(20 + 44 + 60 + 60)
    # Output shares by project year: the operating-share-weighted ramp.
    outputs = {row["period"]: row["output"] for row in r["schedule"]}
    assert outputs[3] == pytest.approx(0.5)
    assert outputs[4] == pytest.approx((0.5 * 0.5 + 0.5 * 0.8) / 1.0)
    assert outputs[7] == pytest.approx(1.0)
    # CAPEX stays in years 0 and 1 and the operating life stays four years.
    assert r["timing"]["operating_life_years"] == 4
    assert r["case"] == "SCHEDULED" and r["difference"]["ramp_up_applied"] is True
