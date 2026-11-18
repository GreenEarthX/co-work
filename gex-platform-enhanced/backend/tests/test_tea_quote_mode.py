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


def test_canonical_mode_says_its_stated_contingency_is_not_applied():
    r = run_tea(TEAComputeRequest(project_id="p", pathway_id="c", fuel_id="E_METHANOL", nameplate_capacity=50_000))
    note = next(d for d in r.defaults_used if d["name"] == "assumptions.contingency_pct")
    assert note["basis"].startswith("STATED BUT NOT APPLIED")


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
