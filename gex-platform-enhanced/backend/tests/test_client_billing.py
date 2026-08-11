"""
Client commercial agreement and invoicing.

The contract-formation path is: publish terms -> client accepts -> €1000 invoice issued
-> payment recorded -> client ACTIVE. Each edge is asserted, and so is every way of
skipping one.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.core import client_billing as cb


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    cb.init_billing_db()


@pytest.fixture
def client_id() -> str:
    cid = f"testco_{uuid.uuid4().hex[:8]}"
    cb.create_client(cid, "Test Company AG")
    return cid


@pytest.fixture
def terms() -> dict:
    return cb.publish_terms(
        version=f"v{uuid.uuid4().hex[:6]}",
        content="GEX Platform Terms and Conditions. Placeholder pending legal review.",
        published_by="gex_staff",
    )


# ── money ─────────────────────────────────────────────────────────────────────


def test_the_subscription_is_exactly_one_thousand_euro_in_minor_units():
    assert cb.compute_charge(cb.SUBSCRIPTION, quantity=1) == 100_000


def test_money_is_never_a_float():
    charge = cb.compute_charge(cb.TOKENISATION, quantity=1337.4)
    assert isinstance(charge, int)


def test_tokenisation_is_one_euro_per_tonne():
    assert cb.compute_charge(cb.TOKENISATION, quantity=1) == 100
    assert cb.compute_charge(cb.TOKENISATION, quantity=50_000) == 5_000_000  # €50,000


def test_the_throughput_basis_is_the_gross_settled_value():
    """DECIDED 2026-08-11. This test previously asserted the opposite — that the basis was
    undecided and computing a charge must raise.

    Gross means the full molecule value including the commodity base, not the green
    premium alone. Premium-only was the alternative and was not chosen.
    """
    assert cb.PRODUCER_THROUGHPUT.rate_bps == 250  # 2.5%
    assert cb.OFFTAKER_THROUGHPUT.rate_bps == 100  # 1.0%
    assert cb.PRODUCER_THROUGHPUT.basis == cb.BASIS_GROSS_SETTLED_VALUE
    assert cb.OFFTAKER_THROUGHPUT.basis == cb.BASIS_GROSS_SETTLED_VALUE
    assert cb.BASIS_GROSS_SETTLED_VALUE == "GROSS_SETTLED_VALUE"


def test_the_signed_fee_schedule_says_gross_in_words():
    """The frozen schedule is what a client signs. '2.5% throughput fee' without a stated
    basis is exactly the ambiguity that produces a dispute."""
    for component in (cb.PRODUCER_THROUGHPUT, cb.OFFTAKER_THROUGHPUT):
        assert "GROSS" in component.note
        assert "gross" in (component.unit or "")
    assert "GROSS" in cb.PREMIUM_BASIS_DECISION
    assert "repricing" in cb.PREMIUM_BASIS_DECISION


def test_an_unresolved_basis_would_still_refuse_to_produce_a_number():
    """The refusal mechanism outlives the fee that motivated it — the next fee added with
    an undecided basis must still fail loudly rather than bill a guess."""
    undecided = cb.FeeComponent(
        code="FUTURE_FEE", label="Something not yet agreed",
        basis=cb.BASIS_UNRESOLVED, rate_bps=500,
    )
    with pytest.raises(cb.FeeBasisUnresolved):
        cb.compute_charge(undecided, quantity=1000, unit_value_minor=90_000)


def test_negative_quantities_are_refused():
    with pytest.raises(cb.BillingError):
        cb.compute_charge(cb.TOKENISATION, quantity=-1)


def test_the_tokenisation_unit_trap_is_documented_on_the_component():
    """The token ledger stores tonnes-per-day, not tonnes. Whoever implements the meter
    must read this before multiplying by the rate."""
    assert "mtpd" in cb.TOKENISATION.note.lower()
    assert cb.TOKENISATION.unit == "tonne"


# ── terms ─────────────────────────────────────────────────────────────────────


def test_terms_carry_a_content_hash(terms):
    assert len(terms["content_sha256"]) == 64
    stored = cb.get_terms(terms["terms_id"])
    assert stored["content_sha256"] == terms["content_sha256"]


def test_the_fee_schedule_is_frozen_into_the_terms_version(terms):
    schedule = json.loads(cb.get_terms(terms["terms_id"])["fee_schedule_json"])
    codes = {c["code"] for c in schedule}
    assert codes == {"SUBSCRIPTION", "TOKENISATION", "PRODUCER_THROUGHPUT", "OFFTAKER_THROUGHPUT"}

    subscription = next(c for c in schedule if c["code"] == "SUBSCRIPTION")
    assert subscription["rate_minor_per_unit"] == 100_000


def test_acceptance_rerecords_the_hash_so_a_later_edit_cannot_rewrite_history(client_id, terms):
    acceptance = cb.accept_terms(client_id, terms["terms_id"], "user_1")
    assert acceptance["accepted_sha256"] == terms["content_sha256"]

    # The acceptance row carries the hash itself, not merely a foreign key to a row whose
    # content could change.
    assert "accepted_sha256" in acceptance


def test_the_same_client_cannot_accept_the_same_terms_twice(client_id, terms):
    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    with pytest.raises(Exception):
        cb.accept_terms(client_id, terms["terms_id"], "user_1")


def test_acceptance_by_a_non_vetted_user_is_refused(client_id, terms):
    """The commercial agreement inherits the vetting gate rather than routing around it."""

    def reject(_user_id):
        raise cb.BillingError("account is not ACTIVE")

    with pytest.raises(cb.BillingError):
        cb.accept_terms(client_id, terms["terms_id"], "pending_user",
                        assert_user_active=reject)

    assert cb.get_client(client_id)["state"] == cb.PROSPECT


# ── the contract-formation path ───────────────────────────────────────────────


def test_a_new_client_starts_as_a_prospect(client_id):
    assert cb.get_client(client_id)["state"] == cb.PROSPECT


def test_the_full_path_from_prospect_to_active(client_id, terms):
    assert cb.get_client(client_id)["state"] == cb.PROSPECT

    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    assert cb.get_client(client_id)["state"] == cb.TERMS_ACCEPTED

    invoice = cb.issue_subscription_invoice(client_id, terms["terms_id"])
    assert cb.get_client(client_id)["state"] == cb.INVOICED
    assert invoice["amount_minor"] == 100_000
    assert invoice["currency"] == "EUR"
    assert invoice["state"] == cb.INVOICE_ISSUED

    cb.record_payment(invoice["invoice_id"], payment_ref="SEPA-20260811-001")
    assert cb.get_client(client_id)["state"] == cb.ACTIVE
    assert cb.get_invoice(invoice["invoice_id"])["state"] == cb.INVOICE_PAID


def test_an_invoice_cannot_be_issued_before_the_terms_are_accepted(client_id, terms):
    """The invoice is consideration for an agreed contract, not a way to form one."""
    with pytest.raises(cb.BillingError, match="before the terms are accepted"):
        cb.issue_subscription_invoice(client_id, terms["terms_id"])

    assert cb.get_client(client_id)["state"] == cb.PROSPECT


def test_a_client_cannot_jump_straight_to_active(client_id):
    with pytest.raises(cb.BillingError, match="illegal client transition"):
        cb._set_state(client_id, cb.ACTIVE)


def test_paid_means_evidenced_a_payment_reference_is_required(client_id, terms):
    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    invoice = cb.issue_subscription_invoice(client_id, terms["terms_id"])

    with pytest.raises(cb.BillingError, match="payment reference is required"):
        cb.record_payment(invoice["invoice_id"], payment_ref="")


def test_an_invoice_cannot_be_paid_twice(client_id, terms):
    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    invoice = cb.issue_subscription_invoice(client_id, terms["terms_id"])
    cb.record_payment(invoice["invoice_id"], "SEPA-1")

    with pytest.raises(cb.BillingError, match="only ISSUED invoices can be paid"):
        cb.record_payment(invoice["invoice_id"], "SEPA-2")


def test_invoice_numbers_are_unique(client_id, terms):
    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    first = cb.issue_subscription_invoice(client_id, terms["terms_id"])
    second = cb.issue_subscription_invoice(client_id, terms["terms_id"])
    assert first["invoice_number"] != second["invoice_number"]


def test_reissuing_an_invoice_does_not_pretend_the_lifecycle_moved(client_id, terms):
    """A correction or renewal issues a second invoice to a client already INVOICED.
    That is a no-op on state, not an illegal transition and not a forward step."""
    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    cb.issue_subscription_invoice(client_id, terms["terms_id"])
    assert cb.get_client(client_id)["state"] == cb.INVOICED

    cb.issue_subscription_invoice(client_id, terms["terms_id"])
    assert cb.get_client(client_id)["state"] == cb.INVOICED


def test_a_self_transition_is_a_no_op_but_a_backward_one_is_still_refused(client_id, terms):
    cb.accept_terms(client_id, terms["terms_id"], "user_1")
    cb._set_state(client_id, cb.TERMS_ACCEPTED)  # no-op, no raise
    assert cb.get_client(client_id)["state"] == cb.TERMS_ACCEPTED

    with pytest.raises(cb.BillingError, match="illegal client transition"):
        cb._set_state(client_id, cb.PROSPECT)


# ── seats ─────────────────────────────────────────────────────────────────────


def test_the_seat_limit_defaults_to_twenty(client_id):
    assert cb.get_client(client_id)["seat_limit"] == cb.DEFAULT_SEAT_LIMIT == 20


def test_seats_are_counted_from_auth_users_not_a_second_store():
    """There is exactly one user store. Seat counting must read it, not shadow it."""
    import inspect

    source = inspect.getsource(cb.seats_used)
    assert "auth_users" in source
    assert "auth_connection" in source


def test_seats_used_returns_zero_for_a_company_with_no_users(client_id):
    assert cb.seats_used(client_id) == 0


# ── the module must not grow a payment rail by accident ───────────────────────


def test_this_module_holds_no_payment_credentials_or_provider():
    import inspect

    source = inspect.getsource(cb).lower()
    for forbidden in ("stripe", "sk_live", "sk_test", "card_number", "iban=", "api_key"):
        assert forbidden not in source, (
            f"{forbidden!r} appears in client_billing.py — this module records invoices, "
            "it must not move money or hold credentials"
        )
