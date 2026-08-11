"""
DSCR sensitivity invariants.

Each test here corresponds to a defect that reached a lender's screen:

  * the single-factor table showed a power-price RISE improving DSCR while the
    two-factor grid on the same page showed the opposite;
  * the grid was a plane — `base + Δp·k₁ + Δe·k₂` — so a "combined shock"
    carried no information the single-factor table did not already have, and
    understated the worst corner;
  * break-evens came from assumed "DSCR per unit" constants that disagreed with
    both tables;
  * when no cashflow basis existed, a plausible-looking surface was synthesised
    rather than an empty state being shown.

A failure here is not a broken test — it means one of those is back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.dscr_sensitivity import (
    DEFAULT_POWER_DELTAS,
    base_dscr,
    break_even_metrics,
    compute_sensitivity,
    normalise_params,
    shocked_dscr,
    single_factor_rows,
    surface,
)

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"

# A base case with genuine headroom, so break-evens are solvable.
PARAMS = normalise_params({"debt_service": 33.0})


def _grid(p):
    return {(c["powerDelta"], c["effDelta"]): c["dscr"] for c in surface(p)}


# ── Sign convention ───────────────────────────────────────────────────────────

def test_cheaper_power_improves_dscr():
    """Power is a cost. Cheaper power must raise DSCR — the defect inverted this."""
    row = next(r for r in single_factor_rows(PARAMS) if r["factor"] == "power_price")
    assert row["values"][0] > row["values"][-1], (
        f"power price sign inverted: {row['delta_labels']} -> {row['values']}"
    )


def test_better_efficiency_improves_dscr():
    row = next(r for r in single_factor_rows(PARAMS) if r["factor"] == "efficiency")
    assert row["values"][-1] > row["values"][0]


@pytest.mark.parametrize("factor", ["capex", "cod_delay", "curtailment",
                                    "logistics_cost", "interest_rate"])
def test_adverse_moves_reduce_dscr(factor):
    """Every remaining factor must worsen DSCR as its shock increases."""
    row = next(r for r in single_factor_rows(PARAMS) if r["factor"] == factor)
    assert row["values"][0] > row["values"][-1], f"{factor}: {row['values']}"


# ── The two tables must agree, by construction ────────────────────────────────

def test_single_factor_row_is_a_slice_of_the_surface():
    """
    The rows and the grid were separate hand-tuned tables and drifted apart.
    A row must now BE a slice of the surface — identical values, not merely
    the same sign.
    """
    row = next(r for r in single_factor_rows(PARAMS) if r["factor"] == "power_price")
    g = _grid(PARAMS)
    slice_at_zero_eff = [g[(pd, 0)] for pd in DEFAULT_POWER_DELTAS]
    assert row["values"] == slice_at_zero_eff, (
        f"row {row['values']} != surface slice {slice_at_zero_eff}"
    )


# ── Genuine interaction ───────────────────────────────────────────────────────

def test_surface_is_not_additive():
    """
    For an additive surface the mixed second difference is exactly zero
    everywhere. Power price and efficiency compound, so it must not be.
    """
    g = _grid(PARAMS)
    interaction = g[(20, -5)] - g[(20, 0)] - g[(0, -5)] + g[(0, 0)]
    assert abs(interaction) > 1e-6, "surface is additive — the combined shock adds no information"


def test_worst_corner_is_worse_than_the_additive_prediction():
    """
    The direction matters: an additive grid UNDERSTATES the tail, which is the
    one direction a credit committee cannot tolerate.
    """
    g = _grid(PARAMS)
    additive_prediction = g[(20, 0)] + g[(0, -5)] - g[(0, 0)]
    assert g[(20, -5)] < additive_prediction, (
        f"worst corner {g[(20, -5)]} is not worse than additive {additive_prediction}"
    )


# ── Break-evens are solved, not assumed ───────────────────────────────────────

def test_break_even_lands_on_the_covenant_floor():
    floor = 1.20
    metrics = {m["label"]: m["value"] for m in break_even_metrics(PARAMS, floor)}
    pct = float(re.sub(r"[^0-9.\-]", "", metrics["Max power price rise"]))
    dscr_at_break_even = shocked_dscr(PARAMS, power_delta=pct / 100.0)
    assert dscr_at_break_even == pytest.approx(floor, abs=1e-3), (
        f"solved break-even {pct}% gives DSCR {dscr_at_break_even}, expected {floor}"
    )


def test_no_headroom_is_reported_when_base_is_at_the_floor():
    at_floor = normalise_params({"debt_service": 40.0})   # base == 1.20
    assert base_dscr(at_floor) == pytest.approx(1.20, abs=1e-9)
    for m in break_even_metrics(at_floor, 1.20):
        assert m["breached"] is True
        assert m["value"] == "0"


# ── Honest empty state instead of fabrication ─────────────────────────────────

def test_aggregator_returns_nothing_without_a_cashflow_basis():
    from decimal import Decimal

    from app.services.dscr_aggregator import DSCRAggregator

    agg = DSCRAggregator(annual_debt_service=None, covenant_floor=Decimal("1.20"))
    zero = Decimal(0)
    assert agg._build_heatmap(0.0, zero, zero, zero) == []
    assert agg._build_sensitivity_rows(0.0, zero, zero, zero) == []
    assert agg._build_breakevens(0.0, zero, zero, zero) == []


def test_no_module_carries_its_own_sensitivity_model():
    """
    The additive formula and the elasticity tables existed in three places.
    They must exist in exactly one — app/services/dscr_sensitivity.py.
    """
    offenders = []

    additive = re.compile(r"\(\s*pd\s*/\s*10\s*\)\s*\*\s*\(?\s*-?0\.07")
    elasticity = re.compile(r"-?0\.14\s*,\s*-?0\.07\s*,\s*0\s*,")

    py_files = [f for f in (BACKEND / "app").rglob("*.py")
                if f.name != "dscr_sensitivity.py"]
    tsx_files = list(FRONTEND.rglob("*.tsx")) if FRONTEND.exists() else []

    for f in py_files + tsx_files:
        src = f.read_text(errors="ignore")
        # ignore explanatory comments describing the removed defect
        code = "\n".join(
            ln for ln in src.splitlines()
            if not ln.lstrip().startswith(("#", "//", "*", "/*"))
        )
        if additive.search(code) or elasticity.search(code):
            offenders.append(str(f))

    assert not offenders, (
        "a local sensitivity model is back — it must live only in "
        "app/services/dscr_sensitivity.py:\n" + "\n".join(offenders)
    )


def test_payload_declares_its_interaction_and_method():
    payload = compute_sensitivity({})
    assert payload["interaction"] == "multiplicative"
    assert "multiplicative" in payload["method"]
    assert payload["sensitivityRows"] and payload["heatmapCells"]
