"""
Contract–Debt Coverage — spec §9.1 (divergence fixture), §9.2, §9.3, §9.5.

THE FIXTURE IS THE DELIVERABLE. It is a portfolio that GEX's own contractual rating
engine scores investment grade while 80% of its volume expires in year 4 of a 15-year
debt. The rating-engine half of the divergence is pinned in the GEX backend suite at
`backend/tests/test_rating_engine_expiry_blindness.py` — the two files share the constants
below verbatim, and each names the other. If you change one, change both.
"""
from __future__ import annotations

import pytest

from app.core.coverage.contract_coverage import (
    VERDICT_COVERS,
    VERDICT_DEPENDENT,
    VERDICT_INSUFFICIENT,
    VERDICT_TAIL,
    CoverageContract,
    CoverageInputs,
    compute_coverage,
    outstanding_principal,
)
from app.core.debt.tranche import FinancingStructure, Tranche, TrancheType

# ── the shared fixture — mirrored in the GEX backend suite ────────────────────

NAMEPLATE_TPA = 100_000.0
COD_YEAR = 2030
OPEX_FIXED_EUR = 5_000_000.0
OPEX_VAR_EUR_PER_T = 300.0

CONTRACT_A = dict(  # the bulk of the volume, and it is short
    contract_id="A",
    volume_tpa=80_000.0,
    price_floor_eur_t=900.0,
    tenor_years=4,
    start_year=COD_YEAR,
    counterparty_rating="A-",
    take_or_pay=True,
)
CONTRACT_B = dict(  # long, and thin enough to be irrelevant to debt service
    contract_id="B",
    volume_tpa=10_000.0,
    price_floor_eur_t=950.0,
    tenor_years=15,
    start_year=COD_YEAR,
    counterparty_rating="A",
    take_or_pay=False,
)

SENIOR_AMOUNT = 200_000_000.0
SENIOR_RATE = 0.05
SENIOR_TENOR = 15


def senior_only() -> FinancingStructure:
    return FinancingStructure(
        tranches=[
            Tranche(
                name="senior",
                tranche_type=TrancheType.SENIOR,
                amount=SENIOR_AMOUNT,
                rate=SENIOR_RATE,
                tenor=SENIOR_TENOR,
            )
        ],
        equity_amount=100_000_000.0,
    )


def fixture_inputs(**overrides) -> CoverageInputs:
    base = dict(
        contracts=[CoverageContract(**CONTRACT_A), CoverageContract(**CONTRACT_B)],
        nameplate_tpa=NAMEPLATE_TPA,
        financing=senior_only(),
        cod_year=COD_YEAR,
        opex_fixed_eur=OPEX_FIXED_EUR,
        opex_var_eur_per_t=OPEX_VAR_EUR_PER_T,
    )
    base.update(overrides)
    return CoverageInputs(**base)


# ── §9.1 the divergence ───────────────────────────────────────────────────────


def test_the_portfolio_looks_fully_covered_on_a_timeless_reading():
    """What the current engines see: 90% coverage and a 15-year maximum tenor.

    Both figures are true and both are the reason the defect survives inspection.
    """
    inputs = fixture_inputs()
    scalar_ocr = sum(c.volume_tpa for c in inputs.contracts) / NAMEPLATE_TPA
    max_tenor = max(c.tenor_years for c in inputs.contracts)

    assert scalar_ocr == pytest.approx(0.90)
    assert max_tenor == SENIOR_TENOR  # "tenor matches the debt" — on the longest contract


def test_coverage_collapses_in_year_five_and_the_verdict_is_merchant_dependent():
    result = compute_coverage(fixture_inputs())

    assert result["verdict"] == VERDICT_DEPENDENT
    assert result["coverage_cliff_year"] == 5
    assert result["debt_maturity_year"] == 15
    assert result["tenor_gap_years"] == 10
    assert result["uncovered_debt_years"] == 11

    curve = {row["year"]: row for row in result["coverage_curve"]}
    assert curve[4]["ocr"] == pytest.approx(0.90)
    assert curve[5]["ocr"] == pytest.approx(0.10)


def test_the_naive_tenor_gap_reports_a_perfect_match_and_is_wrong():
    """The comparison figure. max(tenor) says the contracts run exactly as long as the
    debt — gap zero — while the coverage-weighted view says ten uncovered years."""
    result = compute_coverage(fixture_inputs())

    assert result["naive_tenor_gap_years"] == 0
    assert result["tenor_gap_years"] == 10


def test_contracted_revenue_cannot_service_senior_debt_after_the_cliff():
    result = compute_coverage(fixture_inputs())
    curve = {row["year"]: row for row in result["coverage_curve"]}

    # Comfortable while the bulk contract is live...
    assert curve[4]["dscr_contracted"] == pytest.approx(2.569, abs=1e-3)
    # ...and nowhere near 1.0 the year after it expires.
    assert curve[5]["dscr_contracted"] == pytest.approx(0.078, abs=1e-3)

    assert result["min_dscr_contracted"] < 1.0
    assert result["min_dscr_contracted_year"] == 5


def test_most_of_the_senior_debt_is_still_outstanding_when_coverage_ends():
    result = compute_coverage(fixture_inputs())

    assert result["merchant_exposed_debt_pct"] == pytest.approx(0.800, abs=1e-3)
    assert result["merchant_exposed_debt_eur"] == pytest.approx(160_051_000, rel=1e-3)


def test_the_verdict_is_derived_from_scheduled_service_not_sculpted_service():
    """Sculpting floors debt service at interest-only, which flatters DSCR from 0.078 to
    0.15 in the uncovered years. The verdict must not be computed on a number that moves
    when the lender agrees to be paid less."""
    result = compute_coverage(fixture_inputs())
    assert result["inputs_echo"]["dscr_basis"] == "SCHEDULED_DEBT_SERVICE"

    from app.core.debt.sculpting import DebtSculptor

    profile = [row["contracted_cfads_eur"] for row in result["coverage_curve"][:SENIOR_TENOR]]
    sculpted = DebtSculptor(senior_only()).sculpt(profile)

    assert sculpted["summary"]["min_dscr"] > result["min_dscr_contracted"]
    assert sculpted["summary"]["min_dscr"] < 1.0  # still fails, but by less


# ── §9.2 positive control ─────────────────────────────────────────────────────


def test_a_contract_that_outlives_the_debt_returns_contract_covers_debt():
    inputs = fixture_inputs(
        contracts=[
            CoverageContract(
                contract_id="single",
                volume_tpa=90_000.0,
                price_floor_eur_t=900.0,
                tenor_years=18,
                start_year=COD_YEAR,
                counterparty_rating="A",
            )
        ]
    )
    result = compute_coverage(inputs)

    assert result["verdict"] == VERDICT_COVERS
    assert result["uncovered_debt_years"] == 0
    assert result["tenor_gap_years"] < 0  # contracts outlive the debt
    assert result["merchant_exposed_debt_eur"] == 0


def test_a_short_tail_after_the_debt_has_amortised_is_merchant_tail_not_dependent():
    """Coverage ends before maturity, but by then debt service is still fully covered by
    the contracted revenue that remains — a tail, not a dependency."""
    inputs = fixture_inputs(
        contracts=[
            CoverageContract(
                contract_id="bulk",
                volume_tpa=90_000.0,
                price_floor_eur_t=900.0,
                tenor_years=13,
                start_year=COD_YEAR,
            ),
            CoverageContract(
                contract_id="residual",
                volume_tpa=70_000.0,
                price_floor_eur_t=900.0,
                tenor_years=15,
                start_year=COD_YEAR,
            ),
        ],
    )
    result = compute_coverage(inputs)

    assert result["coverage_cliff_year"] == 14
    assert result["min_dscr_contracted"] >= 1.0
    assert result["verdict"] == VERDICT_TAIL


# ── §9.3 insufficient data — negative verification ────────────────────────────


@pytest.mark.parametrize(
    "overrides,expected_reason_fragment",
    [
        ({"financing": None}, "debt tenor"),
        ({"financing": FinancingStructure(tranches=[])}, "debt tenor"),
        ({"cod_year": None}, "COD"),
        ({"nameplate_tpa": 0.0}, "nameplate"),
    ],
)
def test_missing_inputs_return_insufficient_data_and_no_numbers(
    overrides, expected_reason_fragment
):
    """The failure mode guarded here is a fabricated 0, which reads as 'fully covered'.

    Asserting the verdict alone is not enough — assert that every quantitative field is
    None, so a future default value cannot slip through behind a correct verdict.
    """
    result = compute_coverage(fixture_inputs(**overrides))

    assert result["verdict"] == VERDICT_INSUFFICIENT
    assert expected_reason_fragment in result["reason"]

    for field in (
        "min_dscr_contracted",
        "tenor_gap_years",
        "naive_tenor_gap_years",
        "merchant_exposed_debt_eur",
        "merchant_exposed_debt_pct",
        "uncovered_debt_years",
        "coverage_cliff_year",
        "debt_maturity_year",
    ):
        assert result[field] is None, f"{field} must be None, not a fabricated value"


# ── §9.5 edge cases ───────────────────────────────────────────────────────────


def test_zero_contracts_is_a_known_fact_not_missing_data():
    result = compute_coverage(fixture_inputs(contracts=[]))

    assert result["verdict"] == VERDICT_DEPENDENT
    assert result["coverage_cliff_year"] == 1
    assert all(row["ocr"] == 0.0 for row in result["coverage_curve"])


def test_oversold_volume_is_capped_pro_rata_and_never_exceeds_full_coverage():
    inputs = fixture_inputs(
        contracts=[
            CoverageContract(
                contract_id="over1",
                volume_tpa=80_000.0,
                price_floor_eur_t=900.0,
                tenor_years=15,
                start_year=COD_YEAR,
            ),
            CoverageContract(
                contract_id="over2",
                volume_tpa=80_000.0,
                price_floor_eur_t=900.0,
                tenor_years=15,
                start_year=COD_YEAR,
            ),
        ]
    )
    result = compute_coverage(inputs)

    assert all(row["ocr"] <= 1.0 for row in result["coverage_curve"])
    curve = {row["year"]: row for row in result["coverage_curve"]}
    # Revenue is capped at nameplate, not at the 160kt sold.
    assert curve[1]["contracted_cfads_eur"] == pytest.approx(
        NAMEPLATE_TPA * 900.0 - OPEX_FIXED_EUR - OPEX_VAR_EUR_PER_T * NAMEPLATE_TPA
    )


def test_a_contract_expiring_before_cod_contributes_nothing():
    inputs = fixture_inputs(
        contracts=[
            CoverageContract(
                contract_id="expired",
                volume_tpa=90_000.0,
                price_floor_eur_t=900.0,
                tenor_years=3,
                start_year=COD_YEAR - 5,
            )
        ]
    )
    result = compute_coverage(inputs)

    assert result["coverage_cliff_year"] == 1
    assert result["verdict"] == VERDICT_DEPENDENT


def test_a_contract_starting_after_cod_leaves_an_early_gap():
    inputs = fixture_inputs(
        contracts=[
            CoverageContract(
                contract_id="late",
                volume_tpa=90_000.0,
                price_floor_eur_t=900.0,
                tenor_years=15,
                start_year=COD_YEAR + 2,
            )
        ]
    )
    result = compute_coverage(inputs)
    curve = {row["year"]: row for row in result["coverage_curve"]}

    assert curve[1]["ocr"] == 0.0
    assert curve[2]["ocr"] == 0.0
    assert curve[3]["ocr"] == pytest.approx(0.90)
    assert result["coverage_cliff_year"] == 1


def test_start_year_defaults_to_cod_when_absent():
    with_explicit = compute_coverage(fixture_inputs())
    without = compute_coverage(
        fixture_inputs(
            contracts=[
                CoverageContract(**{**CONTRACT_A, "start_year": None}),
                CoverageContract(**{**CONTRACT_B, "start_year": None}),
            ]
        )
    )

    assert without["coverage_cliff_year"] == with_explicit["coverage_cliff_year"]
    assert without["verdict"] == with_explicit["verdict"]


def test_ramp_reduces_available_production_so_early_coverage_reads_higher():
    result = compute_coverage(fixture_inputs(ramp=[0.5]))
    curve = {row["year"]: row for row in result["coverage_curve"]}

    # 90kt contracted against 50kt available — capped at full coverage, not 1.8.
    assert curve[1]["ocr"] == pytest.approx(1.0)
    assert curve[2]["ocr"] == pytest.approx(0.90)


def test_computation_is_deterministic():
    first = compute_coverage(fixture_inputs())
    second = compute_coverage(fixture_inputs())
    assert first == second


# ── outstanding principal ─────────────────────────────────────────────────────


def test_outstanding_principal_is_full_at_inception_and_zero_after_maturity():
    tranche = senior_only().tranches[0]

    assert outstanding_principal(tranche, 1) == pytest.approx(SENIOR_AMOUNT)
    assert outstanding_principal(tranche, SENIOR_TENOR + 1) == 0.0


def test_outstanding_principal_does_not_amortise_during_grace():
    tranche = Tranche(
        name="grace",
        tranche_type=TrancheType.SENIOR,
        amount=SENIOR_AMOUNT,
        rate=SENIOR_RATE,
        tenor=15,
        grace_period_years=3,
    )

    assert outstanding_principal(tranche, 4) == pytest.approx(SENIOR_AMOUNT)
    assert outstanding_principal(tranche, 5) < SENIOR_AMOUNT


def test_outstanding_principal_handles_zero_rate_linearly():
    tranche = Tranche(
        name="zero",
        tranche_type=TrancheType.CONCESSIONAL,
        amount=100_000_000.0,
        rate=0.0,
        tenor=10,
    )

    assert outstanding_principal(tranche, 6) == pytest.approx(50_000_000.0)
