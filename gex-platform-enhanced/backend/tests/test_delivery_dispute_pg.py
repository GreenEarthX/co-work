"""
The DISPUTED exit (GreenMesh Phase 2 Step 3, sub-step 4; alembic 108; B3, ruling R4; T2 open).

A dispute leaves DISPUTED only by a resolution one party proposes (document on file) and the
OTHER confirms with four eyes; the state then moves by itself, never by a party, and GEX
arbitrates nothing. R4: ACCEPTED only with the agreed inspector's certificate — PASS gives
"resolved, VERIFIED", FAIL gives DECLARED/FAIL; with no certificate, only REJECTED, which
releases the draws. Real confirmed order-book trades (G-25). Throwaway database (pg_store).
"""
from __future__ import annotations

import psycopg2
import pytest

from test_delivery_inspection_pg import (GOOD, OFF, _accounts, _appoint, _certify, _doc, _docs_dir,  # noqa: F401
                                         _inspection, _party, inspectors)
from test_delivery_record_pg import JAN, NOW, _parties, _refused, world  # noqa: F401
from test_evidence_pack_pg import client, seeded  # noqa: F401
from test_order_book_token_pg import confirmed_order_book_trade, custody_token  # noqa: F401


def _resolve(d, outcome, proposer, confirmer, second):
    from app.core import delivery_inspection as di

    di.propose_resolution(proposer, d["id"], outcome, _doc(proposer, d, "DISPUTE_RESOLUTION", f"TEST {outcome} ".encode()))
    with _accounts():
        req = di.request_confirmation(confirmer, d["id"], "RESOLUTION_CONFIRMED")["request_id"]
        return di.approve_confirmation(second, d["id"], req)


def _disputed_after_certificate(custody_token, measured):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token))
    _certify(d, measured)
    return dr.dispute(buyer, d["id"], "TEST cargo disputed after the certificate")


def test_a_dispute_with_no_certificate_cannot_resolve_to_acceptance(custody_token):
    """R4: certification happens only in QUALITY_VERIFICATION, so a dispute raised before it has
    no certificate, and resolves only to REJECTED."""
    from app.core import delivery_inspection as di
    from app.core import delivery_record as dr

    seller, _ = _parties()
    d = _appoint(_inspection(custody_token))
    d = dr.dispute(seller, d["id"], "TEST seller disputes the timing")
    assert d["status"] == "DISPUTED"
    _refused(lambda: di.propose_resolution(seller, d["id"], "ACCEPTED", _doc(seller, d, "DISPUTE_RESOLUTION")),
             status=409, code="DELIVERY_RESOLUTION_NO_CERTIFICATE")


def test_a_dispute_of_an_accepted_delivery_resolved_on_its_pass_certificate_is_verified(custody_token):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token))
    _certify(d, GOOD)                                                        # PASS: ACCEPTED
    d = dr.dispute(buyer, d["id"], "TEST buyer disputes after acceptance")
    d = _resolve(d, "ACCEPTED", buyer, seller, _party("g_seller2", seller.company_id))
    assert d["status"] == "ACCEPTED"
    assert d["quality"]["acceptance"] == {"basis": "RESOLUTION", "label": "VERIFIED", "result": "PASS",
                                          "resolved": True}


def test_resolution_to_acceptance_needs_the_certificate_and_follows_it(custody_token):
    seller, buyer = _parties()
    d = _disputed_after_certificate(custody_token, OFF)                     # FAIL, then disputed
    d = _resolve(d, "ACCEPTED", seller, buyer, _party("g_buyer2", buyer.company_id))
    assert d["status"] == "ACCEPTED"
    accepted = [e for e in d["events"] if e["event_type"] == "DELIVERY_ACCEPTED"][-1]
    assert (accepted["company_id"], accepted["actor"]) == (None, "system:inspection")
    assert d["quality"]["acceptance"] == {"basis": "RESOLUTION", "label": "DECLARED", "result": "FAIL",
                                          "resolved": True}


def test_resolution_to_rejection_releases_the_draws(custody_token):
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _inspection(custody_token, kg=1000)
    d = dr.dispute(buyer, d["id"], "TEST no inspector could be agreed")
    d = _resolve(d, "REJECTED", buyer, seller, _party("g_seller2", seller.company_id))
    assert d["status"] == "REJECTED"
    again = dr.schedule(seller, d["contract_id"], {
        "flow": {"leg_seq": 1, "flow_seq": 1}, "draws": [{"token_id": custody_token["token"], "kg": 1000}],
        "window_start": JAN[0], "window_end": JAN[1], "transport_mode": "SHIP",
        "origin": {"facility_id": custody_token["facility"]}, "destination": {"locode": "NLRTM"}})
    assert again["nominated_kg"] == "1000"


def test_one_party_alone_never_resolves_and_gex_does_not_arbitrate(custody_token):
    from app.core import delivery_inspection as di
    from app.core import delivery_record as dr
    from app.core import market_engine as me

    seller, buyer = _parties()
    d = _inspection(custody_token)
    d = dr.dispute(buyer, d["id"], "TEST")
    di.propose_resolution(buyer, d["id"], "REJECTED", _doc(buyer, d, "DISPUTE_RESOLUTION"))
    with _accounts():
        _refused(lambda: di.request_confirmation(buyer, d["id"], "RESOLUTION_CONFIRMED"), status=403,
                 code="DELIVERY_SAME_PARTY")
    gex = me.Party(business_function="COMMERCIAL", user_id="u_gex_test", company_id="greenearthx", is_admin=True)
    _refused(lambda: di.propose_resolution(gex, d["id"], "REJECTED", "0" * 64), status=403, code="GEX_DOES_NOT_TRADE")
    assert dr.get_delivery(seller, d["id"])["status"] == "DISPUTED"
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record
    for event, company, refusal in (("DELIVERY_REJECTED", None, "DELIVERY_NOT_RESOLVED"),
                                    ("DELIVERY_REJECTED", buyer.company_id, "DELIVERY_RESOLUTION_DERIVED"),
                                    ("DELIVERY_QUALITY_VERIFICATION", buyer.company_id, "DELIVERY_STATE_ORDER")):
        shim = market_connection(company_id=PLATFORM_ADMIN)
        try:
            with pytest.raises(psycopg2.Error, match=refusal):
                record.append_event(shim, d["contract_id"], event, "test", company, delivery_id=d["id"])
        finally:
            shim.rollback()
            shim.close()


def test_a_confirmation_must_match_the_latest_proposal(custody_token):
    from app.core import delivery_inspection as di
    from app.core import delivery_record as dr

    seller, buyer = _parties()
    d = _disputed_after_certificate(custody_token, GOOD)
    di.propose_resolution(seller, d["id"], "ACCEPTED", _doc(seller, d, "DISPUTE_RESOLUTION"))
    with _accounts():
        req = di.request_confirmation(buyer, d["id"], "RESOLUTION_CONFIRMED")["request_id"]
        di.propose_resolution(seller, d["id"], "REJECTED", _doc(seller, d, "DISPUTE_RESOLUTION", b"TEST v2 "))
        _refused(lambda: di.approve_confirmation(_party("g_buyer2", buyer.company_id), d["id"], req), status=409,
                 code="DELIVERY_PROPOSAL_CHANGED")
    assert dr.get_delivery(seller, d["id"])["status"] == "DISPUTED"
