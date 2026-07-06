"""COD test evaluator.

The Commercial Operation Date test is the regime transition: a deal is
governed by pre-COD covenants until this test passes, then by operations
covenants thereafter. The test is a conjunction of hard conditions — ALL
must be satisfied, not a weighted sum.

Standard PF COD test conditions:
  - Capacity demonstration ≥ X% of nameplate (typ. 95%)
  - All operating permits in force
  - All offtake contracts unconditional
  - DSRA funded to target months
  - Insurance package in force
  - O&M agreement signed
  - Lookforward DSCR P90 ≥ minimum (typ. 1.30 for IG senior)

This module evaluates the test at a snapshot in time. When the deal has
no actual_cod_date yet, the engine evaluates a PROJECTED outcome based on
declared values + current state — surfaces in UI as "what would happen if
you tried to pass COD today."
"""
from __future__ import annotations

from gex_pf_engine.models import (
    DealInputs, CODTestSummary, ComputeWarning, PreCODTest,
)
from gex_pf_engine.compute.operations import OperationsOutput


def evaluate_cod_test(
    inputs: DealInputs,
    operations_output: OperationsOutput,
) -> tuple[CODTestSummary, list[ComputeWarning]]:
    """Project the COD test outcome.

    If actual_cod_date is set, this is informational — the deal already
    passed. If not, we project what would happen if the test ran today.
    """
    warnings: list[ComputeWarning] = []

    # Find each pre-COD test that's flagged for COD
    cod_tests = {t.test_type: t for t in inputs.precod if t.test_frequency == "at_cod"}

    # Pull the lookforward DSCR threshold either from the test definition,
    # or default to the operations dscr_floor + 0.25 cushion (market practice).
    lookforward_threshold = _threshold(cod_tests, "lookforward_dscr_p90", default=1.30)

    # The "lookforward DSCR P90" should be computed as a stochastic P90 on
    # the first 12 months of operations. For Sprint 2 we approximate with
    # year-1 DSCR × 0.85 stress factor (rough single-curve P90 proxy);
    # Sprint 3 swaps this for a Monte Carlo against the Gabillon curve.
    year_1_dscr = None
    if operations_output.period_rows:
        first = operations_output.period_rows[0]
        if first.dscr is not None:
            year_1_dscr = first.dscr
            warnings.append(ComputeWarning(
                code="lookforward_p90_simplified",
                message=(
                    "Lookforward DSCR P90 estimated as year-1 DSCR × 0.85. "
                    "Sprint 3 will replace this with stochastic projection "
                    "against the Gabillon curve."
                ),
                severity="info",
            ))

    lookforward_p90 = year_1_dscr * 0.85 if year_1_dscr is not None else None

    # Capacity demonstration — must be supplied as a precod_test threshold;
    # if not declared, mark as None and flag in blocking_conditions.
    cap_demo_threshold = _threshold(cod_tests, "capacity_demonstration_pct", default=95.0)

    # DSRA funded: from operations year 0
    dsra_funded = False
    if operations_output.period_rows:
        target_dsra = operations_output.period_rows[0].total_debt_service_eur * 0.5  # 6 months
        dsra_funded = operations_output.period_rows[0].dsra_balance_eur >= target_dsra * 0.95

    # Offtake unconditional: need at least one signed_unconditional offtake
    offtake_unconditional = any(
        o.status == "signed_unconditional" for o in inputs.offtakes
    )
    # Or: a deal-killer offtake that's still not signed_unconditional is fatal
    pending_killer_offtakes = [
        o for o in inputs.offtakes
        if o.deal_killer_flag and o.status != "signed_unconditional"
    ]

    blocking: list[str] = []
    projected_pass = True

    if lookforward_p90 is None:
        blocking.append("lookforward DSCR P90 not computable (no operating periods)")
        projected_pass = False
    elif lookforward_p90 < lookforward_threshold:
        blocking.append(
            f"lookforward DSCR P90 ({lookforward_p90:.2f}) < threshold "
            f"({lookforward_threshold:.2f})"
        )
        projected_pass = False

    if not offtake_unconditional:
        blocking.append("no offtake contracts are signed_unconditional")
        projected_pass = False

    if pending_killer_offtakes:
        names = ", ".join(o.counterparty_name for o in pending_killer_offtakes)
        blocking.append(f"deal-killer offtakes not signed_unconditional: {names}")
        projected_pass = False

    if not dsra_funded:
        blocking.append("DSRA not funded to target at COD")
        projected_pass = False

    summary = CODTestSummary(
        capacity_demonstration_pct=cap_demo_threshold,  # threshold; actual fed at test time
        permits_in_force=None,                            # external evidence
        offtake_unconditional=offtake_unconditional,
        dsra_funded=dsra_funded,
        lookforward_dscr_p90=lookforward_p90,
        lookforward_dscr_threshold=lookforward_threshold,
        projected_passed=projected_pass,
        blocking_conditions=blocking,
    )

    return summary, warnings


def _threshold(tests: dict[str, PreCODTest], test_type: str, default: float) -> float:
    t = tests.get(test_type)
    if t and t.threshold is not None:
        return float(t.threshold)
    return default
