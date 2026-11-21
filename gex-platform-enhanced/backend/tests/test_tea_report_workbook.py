"""The TEA report sheets of the exported workbook (20 Nov 2026): the screen's content in the
screen's order, values only, every figure with a unit and a standing. No database."""
from __future__ import annotations

import io

from openpyxl import Workbook, load_workbook

from app.core import tea_report_workbook as trw

YEARS = [{"year": i, "discount_factor": 1 / 1.08 ** i, "production_kg": 0 if i == 0 else 1e6,
          "capital": 50e6 if i == 0 else 0, "fixed_opex": 0 if i == 0 else 4e6, "variable_opex": 0 if i == 0 else 3e6,
          "by_product_revenue": 0, "cost": 50e6 if i == 0 else 7e6} for i in range(3)]
BASE = {
    "claim_id": "CLM-MBC-abc", "state": "submitted", "engine": "openpytea", "engine_version": "3.2.3", "lcop": 12.5,
    "created_at": "2026-11-20T22:38:00", "run_by": "cfo",
    "report": {"ref": "GEX-TEA-abc-1234abcd", "sha256": "1234abcd" * 8, "basis": "The run as stored."},
    "inputs_now": {"unchanged": True, "checks": [{"check": "engine", "result": "SAME", "detail": "OpenPyTEA 3.2.3."}]},
    "tea_inputs": {
        "request": {"quote_plant": {"equipment": [{"name": "Electrolyser", "installed_cost": 80e6, "source": "Vendor quote Q-17"}],
                                    "variable_opex": {"electricity": {"consumption": 480, "unit": "MWh/day", "price": 60,
                                                                      "source": "PPA term sheet"}}}},
        "defaults_used": [{"name": "openpytea.osbl_factor", "value": 0.3, "basis": "OpenPyTEA default"},
                          {"name": "openpytea.maintenance", "value": 0.05, "basis": "x ISBL"}],
        "analysis": {
            "cost_basis": {"cost_year": 2026, "cepci_basis": "CEPCI 2026 (Gabillon forward)"},
            "breakdown": {
                "currency": "EUR", "discount_rate": 0.08, "plant_utilization": 0.9, "project_lifetime": 3,
                "location_factor": 1, "production_kg_per_year_full": 1e6,
                "capital_costs": {"isbl": 80e6, "osbl": 24e6, "design_and_engineering": 31.2e6, "contingency": 10.4e6,
                                  "fixed_capital": 145.6e6, "working_capital": 21.84e6},
                "equipment": [{"name": "Electrolyser", "category": "Vendor quote", "cost_year": 2024, "target_year": 2026,
                               "direct_cost": 83e6}],
                "variable_opex": {"streams": {"electricity": 3e6}, "total": 3e6},
                "fixed_opex": {"components": {"maintenance": 4e6}, "total": 4e6},
                "per_kg": {"capital": 6.0, "variable": {"electricity": 3.0}, "fixed": {"maintenance": 3.5},
                           "by_product_credit": 0, "levelized_cost": 12.5, "check": 0},
                "years": YEARS, "note": "Pre-tax, unfinanced."},
            "sensitivity": {"tornado": [{"parameter": "discount_rate", "label": "Discount rate", "unit": "%",
                                         "base_input": 8, "low_input": 6, "high_input": 10, "low_lcop": 11.4,
                                         "high_lcop": 13.7, "range_basis": "CONVENTION"}]},
            "index_band": {"applies": False, "reason": "No approved forward."},
            "market_reference": {"applies": True, "model": "Gabillon two-factor (PF engine)", "molecule": "E_METHANOL",
                                 "calibration_status": "SEED", "n_observations": 0, "last_calibrated": "2026-03-22",
                                 "spot": 0.8, "long_term_equilibrium": 0.8, "capex_floor": 0.6, "half_life_months": 12.8,
                                 "levelised_price": 0.716, "required_price": 12.5, "difference": 11.784,
                                 "basis": "levelised like the LCOP", "standing": "SEED: not a market quote.",
                                 "years": [{"year": 1, "operating_year": 1, "price_real": 0.82, "price_nominal": 0.83},
                                           {"year": 2, "operating_year": 2, "price_real": 0.81, "price_nominal": 0.84}]},
        },
    },
}


def _book(base) -> Workbook:
    wb = Workbook()
    trw.write(wb, base, {"version_number": 1, "content_sha256": "cb"}, "p", "Project P")
    buf = io.BytesIO()
    wb.save(buf)
    return load_workbook(io.BytesIO(buf.getvalue()))


def _cells(ws):
    return [c for row in ws.iter_rows() for c in row if c.value is not None]


def test_the_report_sheets_follow_the_screen_and_carry_its_reference():
    wb = _book(BASE)
    assert wb.sheetnames[:7] == ["Report", "Capital", "Operating costs", "Cost by year", "Sensitivity",
                                 "Index band", "Gabillon price"]
    for name in wb.sheetnames[:6]:
        assert "GEX-TEA-abc-1234abcd" in str(wb[name]["A1"].value), name


def test_values_only_with_a_unit_and_standing_on_each_headline_figure():
    wb = _book(BASE)
    assert not any(isinstance(c.value, str) and c.value.startswith("=") for ws in wb for c in _cells(ws))
    rows = {r[0]: r for r in wb["Report"].iter_rows(values_only=True) if r[0]}
    assert rows["Required price (LCOP)"][1:4] == (12.5, "EUR/kg", "CALCULATED")
    assert rows["Fixed capital"][1:4] == (145.6, "M EUR", "CALCULATED")
    assert rows["Gabillon price, levelised (real)"][3] == "MODEL · SEED"
    lcop = next(c for c in _cells(wb["Report"]) if c.value == 12.5 and c.column == 2)
    assert lcop.number_format == "0.000"


def test_defaults_and_capital_driven_costs_are_named():
    wb = _book(BASE)
    cap = {r[0]: r for r in wb["Capital"].iter_rows(values_only=True) if r[0]}
    assert cap["OSBL"][4] == "DEFAULT" and "OpenPyTEA default 0.3" in cap["OSBL"][5]
    op = [r[0] for r in wb["Operating costs"].iter_rows(values_only=True) if r[0]]
    assert "Maintenance †" in op


def test_a_run_before_recorded_results_gets_one_sheet_and_nothing_invented():
    old = {**BASE, "tea_inputs": {"request": {}}}
    wb = _book(old)
    assert "Capital" not in wb.sheetnames
    assert any("only its headline" in str(c.value) for c in _cells(wb["Report"]))


def test_the_three_graphs_are_excel_charts_on_their_own_cells():
    wb = _book(BASE)
    kinds = {name: [type(c).__name__ for c in wb[name]._charts] for name in ("Report", "Cost by year", "Gabillon price")}
    assert kinds == {"Report": ["BarChart"], "Cost by year": ["BarChart"], "Gabillon price": ["LineChart"]}
    g = {r[0]: r for r in wb["Gabillon price"].iter_rows(values_only=True) if isinstance(r[0], int)}
    assert all(row[5] == 12.5 for row in g.values())        # the required price drawn beside the deck
