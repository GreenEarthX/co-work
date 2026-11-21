"""TEA quote mode, ignored inputs and declared defaults (calculation chain repair, 18 Nov 2026).

Quote mode prices a plant's OWN lines (a saved Cost Basis) as installed quotes, with
explicit units, location, contingency and labour. Whatever OpenPyTEA still defaults
is returned in `defaults_used`; nothing is applied unseen. Real OpenPyTEA, no database.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tea_engine.compute import run_tea                      # noqa: E402
from tea_engine.compute import quote_plant as qp            # noqa: E402
from tea_engine.models import TEAComputeRequest             # noqa: E402

openpytea = pytest.importorskip("openpytea")


@pytest.fixture(autouse=True)
def _real_engine(monkeypatch):
    monkeypatch.setenv("TEA_STUB", "0")


QUOTES = [{"name": "Electrolyser", "installed_cost": 80_000_000, "cost_year": 2024, "source": "cost basis v1"},
          {"name": "Reactor", "installed_cost": 40_000_000, "cost_year": 2024, "source": "cost basis v1"}]


def _req(**quote_overrides):
    quote = {"equipment": QUOTES, "loc_factor": 1.0, "loc_factor_basis": "local quotes",
             "contingency": 0.10, "operators_hired": 45, "operator_hourly_rate": 33.16,
             "variable_opex": {"electricity": {"consumption": 2400, "unit": "MWh/day", "price": 55,
                                               "source": "cost basis v1"}},
             **quote_overrides}
    return TEAComputeRequest(project_id="p", pathway_id="p:q", fuel_id="E_METHANOL", nameplate_capacity=50_000,
                             nameplate_unit="t_per_year",
                             assumptions={"capacity_factor": 0.9, "discount_rate_pct": 8, "project_life_years": 25},
                             quote_plant=quote)


def test_an_unknown_request_field_is_refused_not_ignored():
    with pytest.raises(ValidationError):
        TEAComputeRequest(project_id="p", pathway_id="x", nameplate_capacity=1, contingency=0.1)


def test_a_misspelt_assumption_is_refused_not_ignored():
    with pytest.raises(ValidationError):
        TEAComputeRequest(project_id="p", pathway_id="x", nameplate_capacity=1,
                          assumptions={"capacity_factr": 0.9})


def test_every_stream_states_its_unit():
    with pytest.raises(ValidationError):
        _req(variable_opex={"hydrogen": {"consumption": 312000, "price": 0.36, "source": "x"}})
    with pytest.raises(ValidationError):
        _req(variable_opex={"hydrogen": {"consumption": 1, "unit": "kg", "price": 1, "source": "x"}})


def test_quotes_reach_openpytea_as_installed_cost_and_the_stated_contingency_applies():
    r = run_tea(_req())
    cfg = r.openpytea_config
    assert [e["purchased_cost"] for e in cfg["equipment"]] == [80_000_000, 40_000_000]
    assert all(e["category"] == "Vendor quote" and e["material_factor"] == 1.0 for e in cfg["equipment"])
    assert cfg["fixed_capital_factors"] == {"contingency": 0.10}
    names = {d["name"] for d in r.defaults_used}
    assert "openpytea.contingency_factor" not in names               # stated, so not defaulted
    assert {"openpytea.osbl_factor", "openpytea.de_factor", "openpytea.working_capital"} <= names
    # ISBL = the quotes; FCI = ISBL + OSBL + D&E + contingency on OpenPyTEA's Fluids factors
    isbl = 120_000_000
    osbl = 0.3 * isbl
    expected = isbl + osbl + 0.3 * (isbl + osbl) + 0.10 * (isbl + osbl)
    assert r.plant_summary.capex_eur == pytest.approx(expected, rel=1e-6)
    assert r.calculation_boundary["basis"] == "QUOTE_LINES"


def test_no_feedstock_is_bought_unless_stated():
    r = run_tea(_req())
    assert set(r.openpytea_config["variable_opex_inputs"]) == {"electricity"}


def test_an_unknown_fixed_opex_component_is_refused():
    with pytest.raises(Exception):
        run_tea(_req(fixed_opex_components={"maintenance": 1.0}))


def test_canonical_mode_refuses_a_stated_contingency_and_lists_its_own_default():
    with pytest.raises(ValueError, match="quote mode"):
        run_tea(TEAComputeRequest(project_id="p", pathway_id="c", fuel_id="E_METHANOL", nameplate_capacity=50_000,
                                  assumptions={"contingency_pct": 10}))
    r = run_tea(TEAComputeRequest(project_id="p", pathway_id="c", fuel_id="E_METHANOL", nameplate_capacity=50_000))
    names = {d["name"] for d in r.defaults_used}
    assert "assumptions.contingency_pct" not in names and "openpytea.contingency_factor" in names


def test_a_stated_osbl_factor_replaces_the_default_and_needs_its_basis():
    r = run_tea(_req(osbl_factor=0.0, osbl_factor_basis="OSBL priced line by line in cost basis v1"))
    assert r.openpytea_config["fixed_capital_factors"] == {"contingency": 0.10, "osbl": 0.0}
    names = {d["name"]: d for d in r.defaults_used}
    assert "openpytea.osbl_factor" not in names and names["quote.osbl_factor"]["basis"].startswith("STATED")
    isbl = 120_000_000
    assert r.plant_summary.capex_eur == pytest.approx(isbl + 0.3 * isbl + 0.10 * isbl, rel=1e-6)   # D&E + X on ISBL
    with pytest.raises(ValueError):
        run_tea(_req(osbl_factor=0.0))


def test_the_declared_defaults_match_the_installed_openpytea():
    import openpytea.plant as P
    assert P.Plant.processTypes == qp.CAPITAL_FACTORS
    src = inspect.getsource(P)
    for key, (value, _) in qp.FIXED_OPEX_FACTORS.items():
        m = re.search(rf'"{key}":\s*([0-9.]+)', src)
        assert m and float(m.group(1)) == value, f"OpenPyTEA default for {key} is no longer {value}"
    assert "np.array([0.3, 0.6, 0.1])" in src and "np.array([0, 0, 0.4, 0.8])" in src


def test_feedstock_balance_reports_coverage_shortfall_and_gaps():
    # 50,000 t/yr x 0.9 = 45,000 t methanol: H2 0.1875 t/t = 8,437.5 t; CO2 1.375 t/t = 61,875 t
    r = run_tea(_req(on_site_supply={"hydrogen": {"t_per_year": 17_520, "basis": "electrolyser output"},
                                     "co2": {"t_per_year": 50_000, "basis": "capture unit rating"}}))
    rows = {b["feedstock"]: b for b in r.feedstock_balance}
    assert rows["hydrogen"]["status"] == "COVERED" and rows["hydrogen"]["surplus_t_per_year"] == pytest.approx(9_082.5)
    assert rows["co2"]["status"] == "SHORTFALL" and rows["co2"]["shortfall_t_per_year"] == pytest.approx(11_875.0)
    r = run_tea(_req())
    assert {b["status"] for b in r.feedstock_balance} == {"NOT_COVERED"}


def test_a_quote_without_a_price_year_is_declared():
    assert not any(d["name"] == "quote.cost_year" for d in run_tea(_req()).defaults_used)   # all dated
    undated = [{k: v for k, v in q.items() if k != "cost_year"} for q in QUOTES]
    r = run_tea(_req(equipment=undated))
    note = next(d for d in r.defaults_used if d["name"] == "quote.cost_year")
    assert "2 line(s)" in note["basis"]


def test_a_purchase_must_actually_cover_the_shortfall():
    on_site = {"co2": {"t_per_year": 50_000, "basis": "capture unit rating"}}
    enough = {"co2": {"consumption": 11_875_000 / (365 * 0.9), "unit": "kg/day", "price": 0.208, "source": "registry"}}
    r = run_tea(_req(on_site_supply=on_site, variable_opex=enough))
    co2 = next(b for b in r.feedstock_balance if b["feedstock"] == "co2")
    assert co2["status"] == "COVERED_WITH_PURCHASE" and co2["purchased_t_per_year"] == pytest.approx(11_875.0)
    short = {"co2": {**enough["co2"], "consumption": 5_000_000 / (365 * 0.9)}}
    co2 = next(b for b in run_tea(_req(on_site_supply=on_site, variable_opex=short)).feedstock_balance
               if b["feedstock"] == "co2")
    assert co2["status"] == "SHORTFALL" and co2["shortfall_t_per_year"] == pytest.approx(6_875.0)
    nm3 = {"co2": {**enough["co2"], "unit": "Nm3/day"}}
    co2 = next(b for b in run_tea(_req(on_site_supply=on_site, variable_opex=nm3)).feedstock_balance
               if b["feedstock"] == "co2")
    assert co2["status"] == "UNVERIFIED_UNIT"


FWD = {"value": 834.6, "low": 749.2, "high": 925.8, "ref_id": "ref-cepci-2026",
       "basis": "Gabillon P-forward calibrated on CEPCI 1987-2024 (PF engine)"}


def _top(req, **top):
    """The same request with request-level fields (cost_base_year, cepci_forward) set."""
    return TEAComputeRequest.model_validate({**req.model_dump(exclude_unset=True), **top})


def test_a_quote_dated_after_the_last_published_cepci_needs_an_approved_forward():
    dated = [{**QUOTES[0], "cost_year": 2026}, QUOTES[1]]
    with pytest.raises(ValueError, match="cepci_forward_2026"):
        run_tea(_req(equipment=dated))


def test_the_approved_forward_converts_the_quote_and_is_declared():
    from tea_engine.compute.quote_plant import published_cepci
    dated = [{**QUOTES[0], "cost_year": 2026}, QUOTES[1]]
    r = run_tea(_top(_req(equipment=dated), cepci_forward={2026: FWD}))
    # Same plant with the electrolyser quote converted by hand to 2024 money.
    by_hand = [{**QUOTES[0], "installed_cost": 80_000_000 * published_cepci()[2024] / 834.6}, QUOTES[1]]
    assert r.plant_summary.capex_eur == pytest.approx(run_tea(_req(equipment=by_hand)).plant_summary.capex_eur,
                                                      rel=1e-6)
    note = next(d for d in r.defaults_used if d["name"] == "cepci_forward.2026")
    assert note["value"] == 834.6 and "ref-cepci-2026" in note["basis"] and "749.2-925.8" in note["basis"]
    assert "price year of 1 quote" in note["basis"]


def test_the_cost_base_moves_to_2026_with_its_forward():
    from tea_engine.compute.quote_plant import published_cepci
    r24 = run_tea(_req())
    with pytest.raises(ValueError, match="cepci_forward_2026"):
        run_tea(_top(_req(), cost_base_year=2026))
    r26 = run_tea(_top(_req(), cost_base_year=2026, cepci_forward={2026: FWD}))
    # Every 2024 quote escalates by forward / published; fixed capital is linear in them.
    assert r26.plant_summary.capex_eur == pytest.approx(r24.plant_summary.capex_eur * 834.6 / published_cepci()[2024],
                                                        rel=1e-6)
    assert r26.cost_basis["cost_year"] == 2026 and "Gabillon forward" in r26.cost_basis["cepci_basis"]
    assert r26.cost_basis["cepci_forward"]["ref_id"] == "ref-cepci-2026"
    assert r26.cost_basis["fx"]["rate_year"] == 2024
    note = next(d for d in r26.defaults_used if d["name"] == "cepci_forward.2026")
    assert "the cost base year" in note["basis"]
    # A quote priced in 2026 money is not escalated at a 2026 cost base.
    in_2026 = [{**q, "cost_year": 2026} for q in QUOTES]
    r = run_tea(_top(_req(equipment=in_2026), cost_base_year=2026, cepci_forward={2026: FWD}))
    assert r.plant_summary.capex_eur == pytest.approx(r24.plant_summary.capex_eur, rel=1e-6)


def test_the_canonical_train_moves_to_2026_too():
    from tea_engine.compute.quote_plant import published_cepci
    base = dict(project_id="p", pathway_id="x", nameplate_capacity=50_000, fuel_id="E_METHANOL")
    r24 = run_tea(TEAComputeRequest(**base))
    with pytest.raises(ValueError, match="cepci_forward_2026"):
        run_tea(TEAComputeRequest(**base, cost_base_year=2026))
    r26 = run_tea(TEAComputeRequest(**base, cost_base_year=2026, cepci_forward={2026: FWD}))
    assert r26.plant_summary.capex_eur == pytest.approx(r24.plant_summary.capex_eur * 834.6 / published_cepci()[2024],
                                                        rel=1e-6)
    assert "USD rate is of 2024, the cost base 2026" in r26.cost_basis["note"]


def test_a_forward_never_leaks_into_another_run():
    from openpytea.equipment import CEPCI_DF
    before = run_tea(_req())
    run_tea(_top(_req(), cost_base_year=2026, cepci_forward={2026: FWD}))
    assert 2026 not in CEPCI_DF.index
    after = run_tea(_req())
    assert after.cost_basis_hash == before.cost_basis_hash
    assert after.plant_summary.capex_eur == before.plant_summary.capex_eur
    with pytest.raises(ValueError, match="cepci_forward_2026"):          # it did not stay behind
        run_tea(_top(_req(), cost_base_year=2026))


def test_the_forward_is_in_the_cost_basis_hash():
    a = run_tea(_top(_req(), cost_base_year=2026, cepci_forward={2026: FWD}))
    b = run_tea(_top(_req(), cost_base_year=2026, cepci_forward={2026: {**FWD, "value": 850.0}}))
    assert a.cost_basis_hash != b.cost_basis_hash


def test_a_published_year_wins_over_a_forward():
    r = run_tea(_top(_req(), cepci_forward={2024: {**FWD, "value": 1.0}}))   # 2024 is published
    assert r.plant_summary.capex_eur == run_tea(_req()).plant_summary.capex_eur
    assert not [d for d in r.defaults_used if d["name"].startswith("cepci_forward")]

# ── Results view (20 Nov 2026): breakdown, tornado with stated ranges, Gabillon band ─────

def test_the_cost_per_kg_adds_back_to_the_lcop():
    r = run_tea(_req())
    b = r.breakdown
    pk = b["per_kg"]
    parts = pk["capital"] + sum(pk["variable"].values()) + sum(pk["fixed"].values()) + pk["by_product_credit"]
    assert parts == pytest.approx(r.lcop, abs=1e-3) and abs(pk["check"]) < 1e-9
    # Electricity runs with production: its per-kg cost is the annual bill over full-rate output.
    assert pk["variable"]["electricity"] == pytest.approx(
        b["variable_opex"]["streams"]["electricity"] / b["production_kg_per_year_full"], rel=1e-9)
    cap = b["capital_costs"]
    assert cap["fixed_capital"] == pytest.approx(r.plant_summary.capex_eur, abs=0.01)
    assert cap["fixed_capital"] == pytest.approx(cap["isbl"] + cap["osbl"] + cap["design_and_engineering"]
                                                 + cap["contingency"], rel=1e-9)
    assert [e["name"] for e in b["equipment"]] == [q["name"] for q in QUOTES]
    assert sum(y["capital"] for y in b["years"]) == pytest.approx(cap["fixed_capital"], rel=1e-9)   # WC returned
    assert "NPV, IRR and payback are not computed here" in b["note"]


def test_fixed_operating_cost_starts_with_production_not_construction():
    """OpenPyTEA 3.1.0: no fixed cost while the plant is built (3.0.0 charged it)."""
    years = run_tea(_req()).breakdown["years"]
    building = [y for y in years if y["production_kg"] == 0 and y["capital"] > 0]
    assert building and all(y["fixed_opex"] == 0 for y in building)


def test_the_tornado_moves_rates_in_points_and_says_every_range_is_a_convention():
    from tea_engine.compute.openpytea_runner import run_sensitivity
    s = run_sensitivity(_req())
    by = {t.parameter: t for t in s.tornado}
    assert set(by) == {"discount_rate", "utilization", "installed_cost", "price:electricity"}
    assert (by["discount_rate"].low_input, by["discount_rate"].high_input) == (6.0, 10.0)
    assert by["discount_rate"].low_lcop < s.base_lcop < by["discount_rate"].high_lcop
    assert by["price:electricity"].low_lcop < s.base_lcop < by["price:electricity"].high_lcop
    assert by["installed_cost"].low_lcop < s.base_lcop < by["installed_cost"].high_lcop
    assert by["utilization"].high_lcop < s.base_lcop     # more output, lower cost per kg
    assert all(t.range_basis.startswith("CONVENTION") for t in s.tornado)
    swings = [abs(t.high_lcop - t.low_lcop) for t in s.tornado]
    assert swings == sorted(swings, reverse=True)


def test_the_index_band_prices_the_plant_at_the_forward_band():
    from tea_engine.compute.openpytea_runner import run_index_band
    band = run_index_band(_top(_req(), cost_base_year=2026, cepci_forward={2026: FWD}))
    assert band["applies"] and set(band["years"]) == {2026}
    lo, hi = band["index_low"], band["index_high"]
    # Quotes in 2024 money escalate linearly in the 2026 index.
    assert lo["fixed_capital"] / band["base"]["fixed_capital"] == pytest.approx(FWD["low"] / FWD["value"], rel=1e-6)
    assert hi["fixed_capital"] / band["base"]["fixed_capital"] == pytest.approx(FWD["high"] / FWD["value"], rel=1e-6)
    assert band["lcop_range"][0] < band["base"]["lcop"] < band["lcop_range"][1]
    assert any("cannot be stored" in n for n in band["not_covered"])


def test_no_forward_no_band_and_it_says_why():
    from tea_engine.compute.openpytea_runner import run_index_band
    band = run_index_band(_req())
    assert band["applies"] is False and "published CEPCI years" in band["reason"]


def test_the_index_band_leaves_no_forward_behind():
    from tea_engine.compute.openpytea_runner import run_index_band
    from tea_engine.compute.quote_plant import published_cepci
    before = dict(published_cepci())
    run_index_band(_top(_req(), cost_base_year=2026, cepci_forward={2026: FWD}))
    assert published_cepci() == before
    with pytest.raises(ValueError, match="cepci_forward_2026"):
        run_tea(_top(_req(), cost_base_year=2026))
