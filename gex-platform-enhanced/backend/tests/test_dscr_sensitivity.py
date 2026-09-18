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


# ── The power/OPEX split is supplied, never assumed ───────────────────────────
#
# `_sensitivity_params` used to close the gap with
#     power_share = float(getattr(self, "power_opex_share", 0.73))
# while its own docstring said a caller could override it. No caller could: the
# name occurred exactly twice in the tree — that docstring and that getattr — so
# every project was stressed at a 73% power share. Both heatmap axes act on the
# power term, so that constant set every cell of the grid and the break-even
# power price a credit committee reads.


def _agg(share=None, overrides=None):
    from decimal import Decimal

    from app.services.dscr_aggregator import DSCRAggregator

    return DSCRAggregator(
        annual_debt_service=None,
        covenant_floor=Decimal("1.20"),
        power_opex_share=share,
        sensitivity_overrides=overrides,
    )


def _basis():
    """A real cashflow basis: revenue, opex and debt service all non-zero."""
    from decimal import Decimal

    return Decimal("100"), Decimal("-52"), Decimal("40")


def test_a_cashflow_basis_alone_does_not_produce_a_stress_grid():
    """With money but no power split, the three stress outputs stay empty."""
    rev, opex, ds = _basis()
    agg = _agg(share=None)
    assert agg._build_heatmap(1.2, rev, opex, ds) == []
    assert agg._build_sensitivity_rows(1.2, rev, opex, ds) == []
    assert agg._build_breakevens(1.2, rev, opex, ds) == []


def test_a_supplied_power_share_produces_a_grid_and_changes_it():
    """
    Negative verification: the share must actually reach the model. If it were
    still decorative, these two grids would be identical.
    """
    rev, opex, ds = _basis()
    low = _agg(share=0.40)._build_heatmap(1.2, rev, opex, ds)
    high = _agg(share=0.85)._build_heatmap(1.2, rev, opex, ds)

    assert low and high, "a supplied share must produce a grid"
    assert len(low) == len(high)

    stressed = [(a, b) for a, b in zip(low, high) if a.power_delta != 0]
    assert stressed, "grid must contain power-stressed cells"
    assert any(a.dscr != b.dscr for a, b in stressed), (
        "power_opex_share does not reach the surface — it is decorative again"
    )


def test_base_efficiency_is_project_supplied_not_frozen_at_72():
    """
    `base_efficiency_pct` is the denominator of the efficiency axis. It sat in
    DEFAULT_PARAMS under the comment "every caller may override" while the one
    real caller passed only four of the twelve terms, so it was 72.0 for every
    project ever stressed.
    """
    rev, opex, ds = _basis()
    default = _agg(share=0.70)._build_heatmap(1.2, rev, opex, ds)
    supplied = _agg(
        share=0.70, overrides={"base_efficiency_pct": 55.0}
    )._build_heatmap(1.2, rev, opex, ds)

    stressed = [(a, b) for a, b in zip(default, supplied) if a.eff_delta != 0]
    assert stressed, "grid must contain efficiency-stressed cells"
    assert any(a.dscr != b.dscr for a, b in stressed), (
        "base_efficiency_pct does not reach the model"
    )


def test_an_out_of_range_power_share_is_refused_at_construction():
    import pytest as _pytest

    for bad in (-0.1, 1.4, 73.0):
        with _pytest.raises(ValueError):
            _agg(share=bad)


def test_the_result_says_why_the_stress_outputs_are_missing():
    """
    An empty grid because a project has no debt service yet, and an empty grid
    because nobody supplied the power split, are different facts. A caller that
    cannot tell them apart will report the wrong one to a lender.
    """
    from datetime import date
    from decimal import Decimal

    from app.services.cashflow_client import CashflowProjectionDTO

    projection = CashflowProjectionDTO(
        project_asset_id="a1",
        project_name="Test",
        from_date=date(2027, 1, 1),
        to_date=date(2027, 12, 31),
        granularity="monthly",
        rows=[],
    )

    assert _agg(share=None).compute(projection).sensitivity_basis == (
        "none_power_opex_split_not_supplied"
    )
    assert _agg(share=0.70).compute(projection).sensitivity_basis == (
        "none_no_cashflow_basis"
    )


def test_no_fabricated_power_share_default_returns():
    """
    AST-matched, not text-matched: this test's own explanation names the very
    pattern it forbids, and earlier guardrails in this repo repeatedly matched
    their own prose.

    Forbids `getattr(<anything>, "power_opex_share", <number>)` — a lookup that
    silently substitutes a constant for a project fact.
    """
    import ast

    offenders = []
    for f in (BACKEND / "app").rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
                continue
            if len(node.args) != 3:
                continue
            name, default = node.args[1], node.args[2]
            if not (isinstance(name, ast.Constant) and name.value == "power_opex_share"):
                continue
            if isinstance(default, ast.Constant) and isinstance(
                default.value, (int, float)
            ):
                offenders.append(f"{f}:{node.lineno}")

    assert not offenders, (
        "power_opex_share is being defaulted to a literal again: "
        + ", ".join(offenders)
    )


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
