"""
Characterization tests for DebtSculptor — spec §9.6.

DebtSculptor had ZERO callers when these were written. `sculpt()` was never invoked from
any route, service or test, and `SculptingConstraints.tail_years` was declared and never
read. Its behaviour was therefore asserted by nothing and observed by no user.

These tests PIN CURRENT BEHAVIOUR so that wiring it up is a safe change. Several of them
document defects rather than desirable behaviour; each is labelled DEFECT. Do not "fix"
the assertion to match what the code ought to do — fix the code and update the test
deliberately, in a commit that says so.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from app.core.debt.sculpting import DebtSculptor, SculptingConstraints
from app.core.debt.tranche import DFIProvider, FinancingStructure, Tranche, TrancheType


def senior(amount=200_000_000.0, rate=0.05, tenor=15, grace=0, **kw) -> Tranche:
    return Tranche(
        name=kw.pop("name", "senior"),
        tranche_type=TrancheType.SENIOR,
        amount=amount,
        rate=rate,
        tenor=tenor,
        grace_period_years=grace,
        **kw,
    )


def structure(*tranches: Tranche, equity=100_000_000.0) -> FinancingStructure:
    return FinancingStructure(tranches=list(tranches), equity_amount=equity)


# ── debt service shape ────────────────────────────────────────────────────────


def test_grace_period_is_interest_only_and_flagged():
    t = senior(grace=3)
    fin = structure(t)
    result = DebtSculptor(fin).sculpt([50_000_000.0] * 15)

    year1 = result["sculpted_profile"][0]
    assert year1["is_grace_period"] is True
    assert year1["total_debt_service"] == pytest.approx(200_000_000 * 0.05)

    # First post-grace year amortises over the REMAINING tenor, not the original.
    assert result["sculpted_profile"][3]["is_grace_period"] is False
    assert t.annual_debt_service(4) > t.annual_debt_service(3)


def test_debt_service_is_zero_beyond_tenor():
    t = senior(tenor=10)
    assert t.annual_debt_service(10) > 0
    assert t.annual_debt_service(11) == 0.0


def test_dscr_is_infinite_after_maturity_and_poisons_the_summary():
    """DEFECT: once debt service reaches zero, DSCR is float('inf').

    min_dscr survives (inf never wins a min), but avg_dscr and max_dscr become inf, and
    `Infinity` is not valid strict JSON — a client that parses strictly will reject the
    payload. Callers must clamp the horizon to the debt life or filter the series.
    """
    fin = structure(senior(tenor=10))
    result = DebtSculptor(fin).sculpt([50_000_000.0] * 15)  # horizon exceeds tenor

    assert result["sculpted_profile"][10]["dscr"] == float("inf")
    assert math.isinf(result["summary"]["avg_dscr"])
    assert math.isinf(result["summary"]["max_dscr"])
    assert math.isfinite(result["summary"]["min_dscr"])

    with pytest.raises(ValueError):
        json.dumps(result["summary"], allow_nan=False)


# ── the reduction path ────────────────────────────────────────────────────────


def test_low_dscr_reduces_service_and_floors_at_interest_only():
    fin = structure(senior())
    result = DebtSculptor(fin).sculpt([1_500_000.0] * 15)  # far below any target

    year1 = result["sculpted_profile"][0]
    assert year1["total_debt_service"] == pytest.approx(200_000_000 * 0.05)
    assert year1["is_compliant"] is False
    assert year1["is_lock_up"] is True


def test_reduction_preserves_concessional_tranches():
    commercial = senior(amount=100_000_000.0, name="commercial")
    concessional = Tranche(
        name="ifc",
        tranche_type=TrancheType.CONCESSIONAL,
        amount=100_000_000.0,
        rate=0.02,
        tenor=15,
        dfi_provider=DFIProvider.IFC,
    )
    fin = structure(commercial, concessional)

    scheduled_concessional = concessional.annual_debt_service(1)
    result = DebtSculptor(fin).sculpt([1_000_000.0] * 15)
    payments = result["sculpted_profile"][0]["tranche_payments"]

    assert payments["ifc"] == pytest.approx(scheduled_concessional)
    assert payments["commercial"] == pytest.approx(100_000_000 * 0.05)


def test_interest_floor_ignores_fx_conversion():
    """DEFECT: `_reduce_commercial_first` floors at `t.amount * t.rate`, but
    `annual_debt_service` amortises `t.amount_in_base`. For any tranche whose
    fx_rate_to_base != 1.0 the floor is computed in the WRONG CURRENCY — here the floor
    is 11% higher than the interest actually due in base currency.
    """
    t = senior(amount=100_000_000.0, currency="USD", fx_rate_to_base=0.9)
    assert t.amount_in_base == pytest.approx(90_000_000.0)

    fin = structure(t)
    result = DebtSculptor(fin).sculpt([100_000.0] * 15)
    floored = result["sculpted_profile"][0]["total_debt_service"]

    assert floored == pytest.approx(100_000_000 * 0.05)          # unconverted — the defect
    assert floored != pytest.approx(90_000_000 * 0.05)           # what it should be


# ── the acceleration path ─────────────────────────────────────────────────────


def test_high_dscr_accelerates_senior_capped_at_150_percent_of_schedule():
    t = senior()
    fin = structure(t)
    scheduled = t.annual_debt_service(1)

    result = DebtSculptor(fin).sculpt([500_000_000.0] * 15)  # DSCR far above max_dscr
    accelerated = result["sculpted_profile"][0]["total_debt_service"]

    assert accelerated == pytest.approx(scheduled * 1.5)


def test_acceleration_is_skipped_entirely_during_grace():
    t = senior(grace=2)
    fin = structure(t)
    result = DebtSculptor(fin).sculpt([500_000_000.0] * 15)

    year1 = result["sculpted_profile"][0]
    assert year1["is_grace_period"] is True
    assert year1["total_debt_service"] == pytest.approx(200_000_000 * 0.05)


# ── the defect that matters most ──────────────────────────────────────────────


def test_sculpting_does_not_conserve_principal():
    """DEFECT — the load-bearing one.

    `Tranche.annual_debt_service(year)` recomputes the annuity from the FULL original
    amount every year. It has no knowledge of what was actually paid. So a reduction in
    an early year never increases a later payment, an acceleration never shortens the
    tenor, and `cumulative_shortfall` is recorded but never repaid by anyone.

    Consequence: the sculpted profile does not repay the debt. Any use of this output as
    a repayment schedule — as opposed to a DSCR diagnostic — is wrong.
    """
    t = senior()
    fin = structure(t)
    scheduled_year_5 = t.annual_debt_service(5)

    # Starve years 1-4 so they are forced down to the interest floor.
    profile = [1_000_000.0] * 4 + [500_000_000.0] * 11
    result = DebtSculptor(fin).sculpt(profile)

    assert result["summary"]["cumulative_shortfall"] > 0

    # Year 5's SCHEDULED service is untouched by four years of shortfall.
    assert t.annual_debt_service(5) == pytest.approx(scheduled_year_5)

    # And the sculptor never asks for the missed principal back: year 5 is capped at
    # 150% of the original schedule, not at schedule + accumulated arrears.
    assert result["sculpted_profile"][4]["total_debt_service"] == pytest.approx(
        scheduled_year_5 * 1.5
    )
    assert result["sculpted_profile"][4]["total_debt_service"] < (
        scheduled_year_5 + result["summary"]["cumulative_shortfall"]
    )


def test_negative_cfads_yields_negative_dscr_and_non_compliance():
    fin = structure(senior())
    result = DebtSculptor(fin).sculpt([-5_000_000.0] * 15)

    year1 = result["sculpted_profile"][0]
    assert year1["dscr"] < 0
    assert year1["is_compliant"] is False
    assert year1["is_lock_up"] is True
    assert result["summary"]["all_compliant"] is False


def test_lock_up_years_are_reported_for_every_breaching_year():
    fin = structure(senior())
    profile = [50_000_000.0] * 5 + [1_500_000.0] * 10
    result = DebtSculptor(fin).sculpt(profile)

    assert result["summary"]["lock_up_years"] == list(range(6, 16))
    assert result["summary"]["all_compliant"] is False


def test_empty_profile_returns_zeroed_summary_not_a_crash():
    fin = structure(senior())
    result = DebtSculptor(fin).sculpt([])

    assert result["sculpted_profile"] == []
    assert result["summary"]["min_dscr"] == 0
    assert result["summary"]["all_compliant"] is True  # vacuous truth over an empty series


# ── dead configuration ────────────────────────────────────────────────────────


def test_tail_years_constraint_is_declared_but_never_read():
    """DEFECT: `SculptingConstraints.tail_years` is dead config.

    Walks the AST rather than the text, because a grep for `tail_years` matches this
    test's own docstring — a failure mode this repo has hit repeatedly.
    """
    source = Path(DebtSculptor.__module__.replace(".", "/") + ".py")
    if not source.exists():  # module path differs when run from another cwd
        import app.core.debt.sculpting as sculpting_module

        source = Path(sculpting_module.__file__)

    tree = ast.parse(source.read_text())

    # ast.walk yields an AnnAssign's target Name as its own node, so the declaration
    # would otherwise be counted a second time as a use. Track the target nodes and skip
    # them by identity.
    declaration_targets = set()
    definitions = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "tail_years":
                definitions += 1
                declaration_targets.add(id(node.target))

    reads = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "tail_years":
            reads += 1
        elif isinstance(node, ast.Name) and node.id == "tail_years":
            if id(node) not in declaration_targets:
                reads += 1

    assert definitions == 1, "tail_years should be declared exactly once"
    assert reads == 0, (
        "tail_years is now read somewhere — the sculptor may have gained a tail "
        "constraint. Decide deliberately whether the coverage computation should use it, "
        "then update this test."
    )
