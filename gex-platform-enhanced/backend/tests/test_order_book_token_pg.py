"""
An order-book sell order may name a token (gap G-25, migration 105; GreenMesh Phase 2 Step 3,
JML P2 of 13 Nov 2026).

A firm, all-or-nothing SELL order names one MINTED token of the seller's own project, in its
own commodity. Opening reserves it, cancelling releases it, acceptance puts it on the contract
and matches it. The market's listing views leave it out (origin_book). The point of it: a
contract that has BOTH tokens (so a delivery can draw on them) and typed clauses (so risk,
title and payment are governed). Throwaway database (pg_store); the custody-backed token
comes from the Phase 1 gate's scenario.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from test_contract_clauses import PAYMENT, TITLE
from test_delivery_record_pg import JAN, NOW, _parties, _refused, world  # noqa: F401
from test_delivery_record_pg import _row as _row_su
from test_evidence_pack_pg import GCAP, GPROJECT, GSELLER, GUSERS, _su, client, scenario, seeded  # noqa: F401

DELIVERY_CIF = {"clause_type": "delivery", "attrs": {"incoterm": "CIF", "named_place": "Rotterdam, NL",
                                                     "shipment_point": "Port of loading, BR"}}


def h2_terms(*clauses, tonnes="1", spec=None, extra_year=False):
    months = [("2027-01-01", "2027-01-31")] + ([("2028-01-01", "2028-01-31")] if extra_year else [])
    product = [{"seq": i, "flow_type": "physical", "period_start": a, "period_end": b, "settle_date": b,
                "quantity": tonnes, "unit": "t"} for i, (a, b) in enumerate(months, start=1)]
    payment = [{**f, "flow_type": "fixed_cash", "unit_price": "5000", "quantity_basis": "delivered",
                "quantity_source_flow": f"1.{f['seq']}"} for f in product]
    from app.trading_book.terms import TermsIn

    return TermsIn.model_validate({
        "settlement": "physical", "commodity": "H2", "currency": "EUR",
        "quality_spec": {"parameters": spec} if spec else {},
        "legs": [{"seq": 1, "leg_role": "product", "flows": product}, {"seq": 2, "leg_role": "payment", "flows": payment}],
        "clauses": [{"seq": i, **c} for i, c in enumerate(clauses, start=1)]})


def _until():
    return datetime.now(timezone.utc) + timedelta(days=5)


def _token_state(url, token):
    return _row_su(url, "SELECT lifecycle_state FROM tokens WHERE id = %s", (token,))["lifecycle_state"]


@pytest.fixture
def custody_token(world, client):
    """A MINTED H2 token of the seller's project with 1000 kg allocated from a closed period."""
    from app.core import project_registry as reg

    client.headers.update({"x-test-company": reg.company_slug(GSELLER)})
    try:
        s = scenario(client, world, project=GPROJECT, capacity=GCAP, synthetic=False)
    finally:
        client.headers.pop("x-test-company", None)
    fac = _row_su(world, "SELECT facility_id FROM coc_period WHERE period_id = %s", (s["period"],))["facility_id"]
    return {"token": s["token"], "facility": fac, "period": s["period"], "url": world}


def confirmed_order_book_trade(url, token, clauses=(DELIVERY_CIF, TITLE, PAYMENT), tonnes="1", spec=None,
                               extra_year=False):
    """Order (naming the token) -> open -> the buyer accepts -> four-eye confirmations by both."""
    from app.core import market_engine as me
    from app.core import order_book as ob
    from app.core import project_registry as reg
    from app.db import session

    for uid, (company, function) in GUSERS.items():
        _su(url, "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                 "business_function, user_name, account_state, is_active) VALUES (%s,%s,'x',%s,%s,'PRODUCER',%s,%s,"
                 "'ACTIVE',1) ON CONFLICT DO NOTHING",
            (uid, f"{uid}@test.invalid", reg.company_slug(company), company, function, f"TEST {uid}"))
    seller, buyer = _parties()
    oid = ob.create_order(seller, h2_terms(*clauses, tonnes=tonnes, spec=spec, extra_year=extra_year), side="sell",
                          all_or_nothing=True,
                          valid_until=_until(), token_id=token)["id"]
    ob.open_order(seller, oid)
    cid = ob.accept_order(buyer, oid)["contract_id"]
    saved = session._sync_engine
    session._sync_engine = None              # account lookups read the throwaway database
    try:
        for first, second in (("g_seller", "g_seller2"), ("g_buyer", "g_buyer2")):
            company = seller.company_id if first.startswith("g_seller") else buyer.company_id
            p1, p2 = me.Party(business_function="COMMERCIAL", user_id=first, company_id=company), me.Party(business_function="COMMERCIAL", user_id=second, company_id=company)
            req = ob.request_confirmation(p1, cid)["request_id"]
            done = ob.approve_confirmation(p2, cid, req)
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved
    assert done["trade_status"] == "confirmed", done
    return {"contract_id": cid, "order_id": oid}


def test_a_sell_order_names_one_own_token_and_follows_the_listing_lifecycle(custody_token):
    from app.core import market_engine as me
    from app.core import order_book as ob

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    oid = ob.create_order(seller, h2_terms(), side="sell", all_or_nothing=True, valid_until=_until(), token_id=token)["id"]
    assert _token_state(url, token) == "MINTED"
    ob.open_order(seller, oid)
    assert _token_state(url, token) == "RESERVED"
    assert oid not in {o["id"] for o in me.my_listings(seller)}              # 105: not a market listing
    assert oid not in {o["id"] for o in me.offer_listings(buyer)}
    cid = ob.accept_order(buyer, oid)["contract_id"]
    assert _token_state(url, token) == "MATCHED"
    on = _row_su(url, "SELECT count(*) AS n FROM tb_contract_version_token vt JOIN tb_contract_version v ON "
                      "v.id = vt.version_id WHERE v.contract_id = %s AND vt.token_id = %s", (cid, token))["n"]
    assert on == 1, "the token is on the contract"


def test_cancelling_an_open_token_order_releases_the_token(custody_token):
    from app.core import order_book as ob

    seller, _ = _parties()
    oid = ob.create_order(seller, h2_terms(), side="sell", all_or_nothing=True, valid_until=_until(),
                          token_id=custody_token["token"])["id"]
    ob.open_order(seller, oid)
    ob.cancel_order(seller, oid)
    assert _token_state(custody_token["url"], custody_token["token"]) == "MINTED"


def test_a_token_order_is_a_firm_all_or_nothing_sell_of_an_own_minted_token(custody_token):
    from app.core import order_book as ob

    seller, buyer = _parties()
    token = custody_token["token"]
    _refused(lambda: ob.create_order(seller, h2_terms(), side="buy", all_or_nothing=True, valid_until=_until(),
                                     token_id=token), status=422, code="TOKEN_ORDER_TERMS")
    _refused(lambda: ob.create_order(seller, h2_terms(), side="sell", valid_until=_until(), token_id=token),
             status=422, code="TOKEN_ORDER_TERMS")
    _refused(lambda: ob.create_order(buyer, h2_terms(), side="sell", all_or_nothing=True, valid_until=_until(),
                                     token_id=token), status=404, code="TOKEN_NOT_FOUND")       # not its project
    nh3 = h2_terms().model_copy(update={"commodity": "NH3"})
    _refused(lambda: ob.create_order(seller, nh3, side="sell", all_or_nothing=True, valid_until=_until(),
                                     token_id=token), status=422, code="TOKEN_COMMODITY")
    ob.create_order(seller, h2_terms(), side="sell", all_or_nothing=True, valid_until=_until(), token_id=token)
    _refused(lambda: ob.create_order(seller, h2_terms(), side="sell", all_or_nothing=True, valid_until=_until(),
                                     token_id=token), status=409, code="TOKEN_ALREADY_OFFERED")
    ghost = f"TKN-NONE-{uuid.uuid4().hex[:6]}"
    _refused(lambda: ob.create_order(seller, h2_terms(), side="sell", all_or_nothing=True, valid_until=_until(),
                                     token_id=ghost), status=404, code="TOKEN_NOT_FOUND")


def test_g25_a_contract_with_tokens_and_typed_clauses_takes_a_governed_delivery(custody_token):
    """The acceptance test of G-25: the delivery draws on the contract's token AND reads the
    three typed clauses, so none of its bases is MISSING."""
    from app.core import delivery_record as dr

    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"])
    seller, _ = _parties()
    d = dr.schedule(seller, t["contract_id"], {
        "flow": {"leg_seq": 1, "flow_seq": 1}, "draws": [{"token_id": custody_token["token"], "kg": 400}],
        "window_start": JAN[0], "window_end": JAN[1], "transport_mode": "SHIP",
        "origin": {"facility_id": custody_token["facility"]}, "destination": {"locode": "NLRTM"}})
    assert (d["incoterm"], d["named_place"]) == ("CIF", "Rotterdam, NL")
    assert d["risk_basis"] == "CIF Rotterdam, NL (confirmed terms)"
    assert d["title_basis"] == "ON_ACCEPTANCE (confirmed terms)"
    assert d["payment_basis"] == "ON_INSPECTOR_CERTIFICATE, OUTTURN_QTY (confirmed terms)"


def test_a_market_listing_is_untouched(custody_token):
    """B6: market trades unchanged. A listing created by the market still shows as a listing."""
    from app.core import market_engine as me

    seller, _ = _parties()
    tok = dict(_row_su(custody_token["url"], "SELECT t.*, c.molecule, c.project_id AS capacity_project_id FROM tokens t "
                                             "JOIN capacities c ON c.id = t.capacity_id WHERE t.id = %s",
                       (custody_token["token"],)))
    lid = me.create_listing(seller, tok, volume_mtpd=1, price_eur_kg=5.0, delivery_start="2027-01-01",
                            delivery_end="2027-01-31")["id"]
    assert lid in {o["id"] for o in me.my_listings(seller)}
