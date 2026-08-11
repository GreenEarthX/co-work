"""
Throughput billing — charging a settled delivery.

The billable event is a settlement: the offtaker confirms receipt of a volume, which is
what they must do to claim the green attribute. Both sides are charged on the same event —
producer 2.5%, offtaker 1% — so one delivery yields 3.5% of gross settled value.

The tests lean on refusal and on idempotency. Double-billing is the most common defect in
usage-based systems, and billing a corrupted row is worse than not billing it.
"""
from __future__ import annotations

import uuid

import pytest

from app.core import client_billing as cb


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    cb.init_throughput_db()


def a_settlement(**over) -> dict:
    base = dict(
        settlement_id=f"stl_{uuid.uuid4().hex[:10]}",
        contract_id="ctr_1",
        project_id="prj_1",
        token_id="tok_1",
        counterparty_seller_id="producer_co",
        counterparty_buyer_id="offtaker_co",
        settlement_type="DELIVERY",
        settlement_status="SETTLED",
        volume_kg=1_000_000.0,          # 1,000 tonnes
        price_per_kg=0.90,              # EUR 900/tonne
        total_amount=900_000.0,         # EUR 900,000
        currency="EUR",
        settlement_date="2030-01-31T00:00:00+00:00",
    )
    base.update(over)
    return base


# ── the charge ────────────────────────────────────────────────────────────────


def test_one_delivery_charges_both_sides():
    charges = cb.charges_for_settlement(a_settlement())
    assert {c.side for c in charges} == {cb.PRODUCER_SIDE, cb.OFFTAKER_SIDE}

    producer = next(c for c in charges if c.side == cb.PRODUCER_SIDE)
    offtaker = next(c for c in charges if c.side == cb.OFFTAKER_SIDE)

    assert producer.company_id == "producer_co"
    assert offtaker.company_id == "offtaker_co"

    # EUR 900,000 settled -> 2.5% and 1.0%, in integer minor units
    assert producer.settled_value_minor == 90_000_000
    assert producer.fee_minor == 2_250_000   # EUR 22,500.00
    assert offtaker.fee_minor == 900_000     # EUR  9,000.00


def test_the_two_sides_together_are_three_and_a_half_percent():
    charges = cb.charges_for_settlement(a_settlement())
    total = sum(c.fee_minor for c in charges)
    assert total == round(90_000_000 * 350 / 10_000)


def test_fees_are_integers_in_minor_units():
    for charge in cb.charges_for_settlement(a_settlement()):
        assert isinstance(charge.fee_minor, int)
        assert isinstance(charge.settled_value_minor, int)


def test_payment_is_due_ten_days_after_title_transfers():
    charge = cb.charges_for_settlement(a_settlement())[0]
    assert charge.settled_at.startswith("2030-01-31")
    assert charge.due_at.startswith("2030-02-10")
    assert cb.PAYMENT_TERMS_DAYS == 10


# ── refusals ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["PENDING", "DRAFT", "DISPUTED", ""])
def test_a_settlement_that_has_not_settled_is_not_billable(status):
    """A delivery is billable when title has transferred, not when it is expected."""
    with pytest.raises(cb.BillingError, match="not final"):
        cb.charges_for_settlement(a_settlement(settlement_status=status))


def test_a_non_eur_settlement_refuses_rather_than_inventing_an_fx_rate():
    with pytest.raises(cb.BillingError, match="no FX rate"):
        cb.charges_for_settlement(a_settlement(currency="USD"))


def test_a_total_that_contradicts_its_own_volume_and_price_is_refused():
    """Billing a corrupted row is worse than not billing it."""
    with pytest.raises(cb.BillingError, match="disagrees"):
        cb.charges_for_settlement(a_settlement(total_amount=450_000.0))


def test_a_rounding_level_discrepancy_is_tolerated():
    charges = cb.charges_for_settlement(a_settlement(total_amount=900_100.0))
    assert charges[0].settled_value_minor == 90_010_000


def test_a_missing_counterparty_refuses_rather_than_skipping_a_payer():
    for missing in ("counterparty_seller_id", "counterparty_buyer_id"):
        with pytest.raises(cb.BillingError, match="no counterparty"):
            cb.charges_for_settlement(a_settlement(**{missing: None}))


def test_a_settlement_with_no_total_or_no_volume_is_refused():
    with pytest.raises(cb.BillingError, match="no total_amount"):
        cb.charges_for_settlement(a_settlement(total_amount=None))
    with pytest.raises(cb.BillingError, match="no positive volume"):
        cb.charges_for_settlement(a_settlement(volume_kg=0))


def test_a_settlement_without_a_date_is_refused_because_the_due_date_derives_from_it():
    with pytest.raises(cb.BillingError, match="no settlement_date"):
        cb.charges_for_settlement(a_settlement(settlement_date=None))


# ── idempotency ───────────────────────────────────────────────────────────────


def test_accruing_the_same_settlement_twice_bills_once():
    """Replayed feeds, re-run periods and retried webhooks must not double-bill."""
    settlement = a_settlement()

    first = cb.accrue_settlement(settlement)
    assert len(first) == 2

    second = cb.accrue_settlement(settlement)
    assert second == []

    period = cb.charges_for_period("producer_co", "2030-01-01", "2030-02-01")
    mine = [c for c in period["charges"] if c["settlement_id"] == settlement["settlement_id"]]
    assert len(mine) == 1


def test_two_different_settlements_both_bill():
    a, b = a_settlement(), a_settlement()
    cb.accrue_settlement(a)
    cb.accrue_settlement(b)

    period = cb.charges_for_period("offtaker_co", "2030-01-01", "2030-02-01")
    ids = {c["settlement_id"] for c in period["charges"]}
    assert {a["settlement_id"], b["settlement_id"]} <= ids


# ── period aggregation ────────────────────────────────────────────────────────


def test_a_period_totals_only_deliveries_settled_inside_it():
    company = f"prod_{uuid.uuid4().hex[:8]}"
    cb.accrue_settlement(a_settlement(counterparty_seller_id=company,
                                      settlement_date="2030-03-15T00:00:00+00:00"))
    cb.accrue_settlement(a_settlement(counterparty_seller_id=company,
                                      settlement_date="2030-04-02T00:00:00+00:00"))

    march = cb.charges_for_period(company, "2030-03-01", "2030-04-01")
    assert len(march["charges"]) == 1
    assert march["total_fee_minor"] == 2_250_000
    assert march["total_volume_kg"] == 1_000_000.0
    assert march["currency"] == "EUR"


def test_a_period_with_no_deliveries_totals_zero_rather_than_failing():
    empty = cb.charges_for_period("nobody_co", "2030-01-01", "2030-02-01")
    assert empty["charges"] == []
    assert empty["total_fee_minor"] == 0


# ── units ─────────────────────────────────────────────────────────────────────


def test_the_tokenisation_fee_converts_kilograms_to_tonnes():
    """Settlements are in kg. The fee is EUR 1.00 per TONNE."""
    assert cb.tokenisation_charge_minor(1_000.0) == 100        # 1 tonne  -> EUR 1.00
    assert cb.tokenisation_charge_minor(1_000_000.0) == 100_000  # 1000 t -> EUR 1,000.00


def test_fees_are_charged_on_gross_settled_value_not_the_green_premium():
    """DECIDED 2026-08-11: gross. The charge is the full settled value including the
    commodity base, not the premium alone."""
    charges = cb.charges_for_settlement(a_settlement())
    producer = next(c for c in charges if c.side == cb.PRODUCER_SIDE)

    # EUR 900/tonne is the whole price, not a premium over a grey benchmark.
    assert producer.settled_value_minor == 90_000_000
    assert producer.fee_minor == 2_250_000

    assert "GROSS" in cb.PREMIUM_BASIS_DECISION
    for component in (cb.PRODUCER_THROUGHPUT, cb.OFFTAKER_THROUGHPUT):
        assert "premium" not in (component.unit or "").lower()


def test_reversing_the_gross_decision_would_require_a_new_terms_version():
    """The fee schedule is frozen into the terms a client signs, so changing the basis is
    a repricing that needs a fresh acceptance — it cannot be done by editing a constant."""
    import json

    schedule = json.loads(cb.fee_schedule_payload())
    producer = next(c for c in schedule if c["code"] == "PRODUCER_THROUGHPUT")
    assert producer["basis"] == cb.BASIS_GROSS_SETTLED_VALUE
    assert "GROSS" in producer["note"]
