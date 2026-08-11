"""
The rating-engine half of the §9.1 divergence fixture.

Spec: docs/contract-debt-coverage-spec.md
Coverage half: files/gex_pf_engine/backend/tests/test_contract_debt_coverage.py

Same portfolio, both engines. This file proves the rating engine calls it investment
grade; the PF-engine file proves contracted revenue cannot service the senior debt from
year 5 of 15. Neither engine is wrong about what it measures — the point is that nothing
in the platform measures the difference.

The fixture constants are mirrored verbatim in the PF-engine file. If you change one,
change both.
"""
from __future__ import annotations

import pytest

from app.core.contractual_rating_engine import (
    ContractualRatingInput,
    ContractualRatingEngine,
    OfftakeContract,
)

# ── the shared fixture — mirrored in the PF engine suite ──────────────────────

NAMEPLATE_TPA = 100_000.0
LCOF_EUR_T = 700.0

# Contract A carries 80% of the volume and expires in year 4 of a 15-year debt.
CONTRACT_A_VOLUME = 80_000.0
CONTRACT_A_PRICE = 900.0
CONTRACT_A_TENOR = 4

# Contract B is long enough to match the debt and too thin to service it.
CONTRACT_B_VOLUME = 10_000.0
CONTRACT_B_PRICE = 950.0
CONTRACT_B_TENOR = 15


def portfolio(a_tenor: int = CONTRACT_A_TENOR) -> list[OfftakeContract]:
    return [
        OfftakeContract(
            counterparty_name="Bulk Buyer",
            counterparty_rating="A-",
            contracted_volume_tpa=CONTRACT_A_VOLUME,
            tenor_years=a_tenor,
            price_floor_eur_t=CONTRACT_A_PRICE,
            take_or_pay=True,
            corporate_floor=True,
        ),
        OfftakeContract(
            counterparty_name="Residual Buyer",
            counterparty_rating="A",
            contracted_volume_tpa=CONTRACT_B_VOLUME,
            tenor_years=CONTRACT_B_TENOR,
            price_floor_eur_t=CONTRACT_B_PRICE,
        ),
    ]


def rating_input(a_tenor: int = CONTRACT_A_TENOR) -> ContractualRatingInput:
    return ContractualRatingInput(
        offtake_contracts=portfolio(a_tenor),
        nameplate_capacity_tpa=NAMEPLATE_TPA,
        lcof_eur_t=LCOF_EUR_T,
        # A credible FEED-stage project on every other axis, so the rating is not
        # carried by the offtake pillar alone.
        equity_cleared=True,
        grid_secured=True,
        epc_price_locked=True,
        subsidy_eu_h2_bank=True,
        carbon_intensity_kgco2_per_kg=1.2,
        tokenized_lca=True,
        tokenized_volume_pct=80.0,
        trl=8,
        land_permitted=True,
        developer_track_record_projects=3,
        developer_track_record_mw=450.0,
    )


@pytest.fixture
def engine() -> ContractualRatingEngine:
    return ContractualRatingEngine()


# ── the claim ─────────────────────────────────────────────────────────────────


def test_the_fixture_rates_investment_grade(engine):
    """This is the claim the coverage computation contradicts."""
    rating = engine.rate(rating_input())

    assert rating.investment_grade is True
    assert rating.final_score >= 68


def test_the_engine_sees_ninety_percent_coverage_with_no_time_dimension(engine):
    rating = engine.rate(rating_input())

    assert rating.ocr == pytest.approx(0.90)
    anchor = next(p for p in rating.pillars if p.pillar == "Offtake Anchor")
    assert anchor.factors["max_tenor_years"] == 15


def test_the_bulk_contracts_tenor_does_not_reach_the_score_at_all(engine):
    """The sharpest form of the defect.

    `tenor_score` is computed from `max(c.tenor_years)`. Contract A holds 80% of the
    volume, so whether it runs for one year or fourteen is the single most important
    fact about this portfolio's revenue certainty — and it changes nothing, because
    Contract B's 15 years always wins the max.
    """
    one_year = engine.rate(rating_input(a_tenor=1))
    four_years = engine.rate(rating_input(a_tenor=4))
    fourteen_years = engine.rate(rating_input(a_tenor=14))

    assert one_year.final_score == four_years.final_score == fourteen_years.final_score
    assert one_year.investment_grade is True

    # And it is specifically the tenor sub-factor that is blind, not merely the total.
    def anchor_of(r):
        return next(p for p in r.pillars if p.pillar == "Offtake Anchor")

    assert anchor_of(one_year).factors["tenor_and_floor"] == pytest.approx(
        anchor_of(fourteen_years).factors["tenor_and_floor"]
    )


def test_ocr_is_identical_whether_the_bulk_contract_has_expired_or_not(engine):
    """OCR is contracted volume over nameplate with no reference to a year, so a
    portfolio that is 90% covered in year 1 and 10% covered in year 5 reports one
    number for both."""
    assert engine.rate(rating_input(a_tenor=1)).ocr == pytest.approx(
        engine.rate(rating_input(a_tenor=15)).ocr
    )


def test_offtake_contract_can_now_express_when_a_contract_starts(engine):
    """The schema half of the root cause is fixed; the scoring half is not.

    This test previously asserted `start_year` did NOT exist. It now asserts the
    opposite, because the field landed when OfftakeContract was promoted to the
    canonical demand-side object. Contracts can now be placed on a timeline.

    What has NOT changed is the engine: `tenor_score` still reads max(tenor_years) and
    ignores `start_year` entirely. The field makes the fix possible; it is not the fix.
    The three tests above still pass, and that is the remaining work.
    """
    contract = portfolio()[0]
    assert hasattr(contract, "start_year")
    assert contract.start_year is None  # unknown is legitimate; COD is the default

    dated = OfftakeContract(
        counterparty_name="Bulk Buyer",
        counterparty_rating="A-",
        contracted_volume_tpa=CONTRACT_A_VOLUME,
        tenor_years=CONTRACT_A_TENOR,
        price_floor_eur_t=CONTRACT_A_PRICE,
        start_year=2030,
    )
    assert dated.start_year == 2030

    # And the engine still does not consult it.
    baseline = engine.rate(rating_input())
    with_dates = ContractualRatingInput(
        offtake_contracts=[dated] + portfolio()[1:],
        nameplate_capacity_tpa=NAMEPLATE_TPA,
        lcof_eur_t=LCOF_EUR_T,
    )
    anchor = next(
        p for p in engine.rate(with_dates).pillars if p.pillar == "Offtake Anchor"
    )
    baseline_anchor = next(p for p in baseline.pillars if p.pillar == "Offtake Anchor")
    assert anchor.factors["max_tenor_years"] == baseline_anchor.factors["max_tenor_years"]
