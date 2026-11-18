"""
Typed clauses on the confirmed terms (GreenMesh Phase 2 Step 3, amendment B1; sub-step 1).

Risk (delivery clause: Incoterm, named place, shipment point), title (title clause) and
payment (payment clause: trigger, quantity basis) are three records. V15 refuses an invalid
typed clause and two of a kind in one scope; free text is never read as a typed clause; a
sub-leg's own clause wins. The Incoterm says nothing about title (ruling R1). Pure: no database.
"""
from __future__ import annotations

import pytest

from app.trading_book import clauses, validation
from app.trading_book.terms import TermsIn


def _terms(*cls):
    flow = {"seq": 1, "flow_type": "physical", "period_start": "2027-01-01", "period_end": "2027-01-31",
            "settle_date": "2027-01-31", "quantity": "10", "unit": "t"}
    pay = {**flow, "flow_type": "fixed_cash", "unit_price": "900", "quantity_basis": "delivered",
           "quantity_source_flow": "1.1"}
    return TermsIn.model_validate({
        "settlement": "physical", "commodity": "EMEOH", "currency": "EUR",
        "legs": [{"seq": 1, "leg_role": "product", "flows": [flow]}, {"seq": 2, "leg_role": "payment", "flows": [pay]}],
        "clauses": [{"seq": i, **c} for i, c in enumerate(cls, start=1)]})


DELIVERY = {"clause_type": "delivery", "attrs": {"incoterm": "CIF", "named_place": "Rotterdam, NL",
                                                 "shipment_point": "Port of loading, BR"}}
TITLE = {"clause_type": "title", "attrs": {"passes": "ON_ACCEPTANCE"}}
PAYMENT = {"clause_type": "payment", "attrs": {"trigger": "ON_INSPECTOR_CERTIFICATE", "quantity_basis": "OUTTURN_QTY"}}


def test_valid_typed_clauses_pass_v15():
    assert validation.validate(_terms(DELIVERY, TITLE, PAYMENT), "order") == []


def test_free_text_clauses_are_untouched():
    """The market's clauses (delivery_terms, payment_terms) are not typed and stay valid."""
    t = _terms({"clause_type": "delivery", "attrs": {"delivery_terms": "FOB Hamburg"}},
               {"clause_type": "payment", "attrs": {"payment_terms": "30 days"}})
    assert validation.validate(t, "order") == []


@pytest.mark.parametrize("bad", [
    {"clause_type": "delivery", "attrs": {"incoterm": "FOB"}},                                # no named place
    {"clause_type": "delivery", "attrs": {"incoterm": "XYZ", "named_place": "x"}},            # not an Incoterm
    {"clause_type": "delivery", "attrs": {"incoterm": "FOB", "named_place": "x", "shipment_point": " "}},
    {"clause_type": "title", "attrs": {"passes": "ON_DELIVERY"}},                             # not an option
    {"clause_type": "title", "attrs": {"passes": None}},
    {"clause_type": "payment", "attrs": {"trigger": "ON_BL"}},                                # no quantity basis
    {"clause_type": "payment", "attrs": {"trigger": "ON_ARRIVAL", "quantity_basis": "BL_QTY"}},
], ids=["no-place", "bad-incoterm", "blank-shipment-point", "bad-title", "null-title", "half-payment",
        "bad-trigger"])
def test_an_invalid_typed_clause_fails_v15(bad):
    assert "V15" in validation.validate(_terms(bad), "order")


def test_one_typed_clause_of_a_kind_per_scope():
    assert "V15" in validation.validate(_terms(TITLE, {"clause_type": "title", "attrs": {"passes": "ON_RISK"}}), "order")


def test_the_title_clause_type_is_known():
    assert "V14" not in validation.validate(_terms(TITLE), "order")


def test_a_sub_legs_own_clause_wins_and_free_text_is_never_read():
    rows = [{"sub_leg_id": None, "clause_type": "delivery", "attrs": {"incoterm": "FOB", "named_place": "Pecem, BR"}},
            {"sub_leg_id": "s2", "clause_type": "delivery", "attrs": {"incoterm": "DAP", "named_place": "Rotterdam, NL"}},
            {"sub_leg_id": None, "clause_type": "title", "attrs": {"passes": "ON_PAYMENT_IN_FULL"}},
            {"sub_leg_id": None, "clause_type": "payment", "attrs": {"payment_terms": "30 days"}}]
    own = clauses.read(rows, "s2")
    assert (own["risk"]["incoterm"], own["risk"]["source"]) == ("DAP", "sub_leg")
    assert clauses.read(rows, "s1")["risk"]["incoterm"] == "FOB"
    assert own["title"]["passes"] == "ON_PAYMENT_IN_FULL" and own["payment"] is None


def test_three_records_three_bases_and_the_incoterm_says_nothing_about_title():
    """R1: an Incoterm with no title clause still gives NO title basis; a title clause with no
    Incoterm still gives one. A C term without its shipment point gives no risk basis."""
    only_incoterm = clauses.bases(clauses.read([{"sub_leg_id": None, **DELIVERY}], None))
    assert not only_incoterm["risk_basis"].startswith("MISSING")
    assert only_incoterm["title_basis"].startswith("MISSING") and "title clause" in only_incoterm["title_basis"]
    only_title = clauses.bases(clauses.read([{"sub_leg_id": None, **TITLE}], None))
    assert only_title["title_basis"] == "ON_ACCEPTANCE (confirmed terms)"
    assert only_title["risk_basis"].startswith("MISSING")
    c_without_point = {"sub_leg_id": None, "clause_type": "delivery", "attrs": {"incoterm": "CFR", "named_place": "x"}}
    assert "shipment point" in clauses.bases(clauses.read([c_without_point], None))["risk_basis"]
    assert clauses.bases(clauses.read([{"sub_leg_id": None, **PAYMENT}], None))["payment_basis"] == (
        "ON_INSPECTOR_CERTIFICATE, OUTTURN_QTY (confirmed terms)")
