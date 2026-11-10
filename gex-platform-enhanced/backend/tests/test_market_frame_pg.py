"""
A market trade joins its project's offtake frame (Phase 3 of "One contract record",
Phase 0 Q6.4; JML 2026-11-10: lock it, keep as trade; alembic 094).

When the project records a planned output and its offtake is a frame, an accepted
trade for the project's output becomes the buyer's sub-leg of the frame in the same
transaction: LOCKED to the trade (the owner's card cannot change or drop it), named
by it (source contract and terms hash, inside the sub-leg hash), carrying the
projection Q4 derives from the trade. An acceptance that would exceed the planned
output is refused whole. A project with no planned output keeps the trade a trade.
The buyer's four-eye TRADE_CONFIRM is what confirms the sub-leg (Q7.3).

In the throwaway PostgreSQL database (conftest.pg_store).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core import contract_tokens as ct
from pg_support import connect_dsn

OWNER, A, M, N = "test_mf_owner", "test_mf_buyer_a", "test_mf_market", "test_mf_market_n"
PID, PID_PLAIN = "proj_TEST_market_frame", "proj_TEST_market_plain"
NAMES = {OWNER: "Test MF Owner", A: "Test MF Buyer A", M: "Test MF Market", N: "Test MF Market N"}
USERS = {"u_mf_exec": (OWNER, "EXECUTIVE"), "u_mf_m1": (M, "EXECUTIVE"), "u_mf_m2": (M, "COMMERCIAL"),
         "u_mf_n1": (N, "EXECUTIVE"), "u_mf_a": (A, "COMMERCIAL")}
ASSET, ASSET_PLAIN = "00000000-0000-4000-8000-0000000094a1", "00000000-0000-4000-8000-0000000094a2"
CARDS = {"offtake": {"certification_scheme": "RFNBO", "planned_output_tonnes_per_year": 10000,
                     "buyers": [{"company_id": A, "contracted_tonnes_per_year": 6000.0, "tenor_years": 10.0}]}}
STATE: dict = {}


def _party(uid):
    from app.core import market_engine as me

    return me.Party(user_id=uid, company_id=USERS[uid][0], company_name=NAMES[USERS[uid][0]])


@pytest.fixture(scope="module")
def world(pg_store):
    from app.db import session

    saved = session._sync_engine
    session._sync_engine = None
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, A, M, N):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (company, NAMES[company]))
    for pid, asset in ((PID, ASSET), (PID_PLAIN, ASSET_PLAIN)):
        cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                    "(%s, 'TEST market frame plant', %s, 'e-Methanol') ON CONFLICT DO NOTHING", (pid, OWNER))
        cur.execute("INSERT INTO tb_asset (id, project_id, name, location, country_code, technology, capacity_mw, "
                    "is_active, created_at, updated_at) VALUES (%s, %s, 'TEST', 'TEST', 'DE', 'PEM', 1, true, now(), "
                    "now())", (asset, pid))
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                    "(%s, %s, 'OFFTAKER', 'STAKEHOLDER')", (pid, A))
    for uid, (company, fn) in USERS.items():
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    conn.commit()
    conn.close()
    _save(CARDS)
    yield
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _save(cards, pid=PID):
    from app.core.request_tenant import reset_current_company, set_current_company

    t = set_current_company(OWNER)
    try:
        return ct.record_versions(pid, cards, "u_mf_exec", OWNER, card_type="offtake")
    finally:
        reset_current_company(t)


def _sell(asset, tonnes_per_day, start=date(2027, 1, 1), end=date(2028, 12, 31)):
    """The owner's firm sell order for its project's output (the flows name the project's asset)."""
    from app.core import market_engine as me
    from app.core import order_book as ob
    from app.trading_book.terms import TermsIn

    conn = me._conn()
    try:
        terms = me.market_terms(conn, molecule="e-Methanol", volume_mtpd=tonnes_per_day, price_eur_kg=1.2,
                                delivery_start=start, delivery_end=end)
    finally:
        conn.close()
    data = terms.model_dump()
    for leg in data["legs"]:
        for f in leg["flows"]:
            f["asset_id"] = asset
    owner = _party("u_mf_exec")
    o = ob.create_order(owner, TermsIn.model_validate(data), side="sell",
                        valid_until=datetime.now(timezone.utc) + timedelta(days=30))
    ob.open_order(owner, o["id"])
    return o["id"]


def _frame():
    return ct.frame_state(PID)


def _code(fn):
    from fastapi import HTTPException

    from app.core.market_engine import MarketRefused

    with pytest.raises((HTTPException, ct.TokenRefusal, MarketRefused)) as exc:
        fn()
    e = exc.value
    return e.detail["code"] if isinstance(e, HTTPException) else e.code


def test_an_accepted_trade_becomes_the_buyers_locked_sub_leg(world):
    from app.core import order_book as ob

    r = ob.accept_order(_party("u_mf_m1"), _sell(ASSET, 5))
    STATE["trade"] = r["contract_id"]
    assert r["frame_sub_leg_hash"]
    subs = {s["company_id"]: s for s in _frame()["sub_legs"]}
    assert set(subs) == {A, M}
    m = subs[M]
    assert str(m["source_contract_id"]) == r["contract_id"] and m["source_terms_hash"].strip() == r["terms_hash"]
    # Q4: first delivery, whole years covered (2), the smallest full year (365 days × 5 t; 2028 has 366)
    assert m["card_projection"] == {"offtake.first_delivery_date": "2027-01-01", "offtake.tenor_years": 2.0,
                                    "offtake.contracted_tonnes_per_year": 1825.0}
    assert ct.card_view(PID)["offtake"]["terms"]["buyers"][1] == {
        "company_id": M, "first_delivery_date": "2027-01-01", "tenor_years": 2.0, "contracted_tonnes_per_year": 1825.0}


def test_the_sub_leg_is_confirmed_by_the_buyers_four_eye_trade_confirmation(world):
    from app.core import order_book as ob

    sub = next(s for s in _frame()["sub_legs"] if s["company_id"] == M)
    assert _code(lambda: ct.confirm_sub_leg(PID, M, sub["sub_leg_hash"].strip(), "CONFIRMED", "u_mf_m1")) \
        == "CONFIRM_ON_THE_TRADE"
    req = ob.request_confirmation(_party("u_mf_m1"), STATE["trade"])
    ob.approve_confirmation(_party("u_mf_m2"), STATE["trade"], req["request_id"])
    assert M in {r["buyer_company_id"] for r in ct.frame_confirmations(PID)}


def test_the_owners_card_cannot_change_or_drop_a_market_sub_leg(world):
    view = ct.card_terms(PID)
    changed = {**view, "offtake": {**view["offtake"], "buyers": [
        view["offtake"]["buyers"][0], {**view["offtake"]["buyers"][1], "contracted_tonnes_per_year": 9000.0}]}}
    assert _code(lambda: _save(changed)) == "MARKET_SUB_LEG_LOCKED"
    dropped = {**view, "offtake": {**view["offtake"], "buyers": [view["offtake"]["buyers"][0]]}}
    assert _code(lambda: _save(dropped)) == "MARKET_SUB_LEG_LOCKED"
    single = {**view, "offtake": {"certification_scheme": "RFNBO", "planned_output_tonnes_per_year": 10000,
                                  "contracted_tonnes_per_year": 6000.0}}
    assert _code(lambda: _save(single)) == "MARKET_SUB_LEG_LOCKED"
    before = next(s for s in _frame()["sub_legs"] if s["company_id"] == M)["sub_leg_hash"]
    a_edit = {**view, "offtake": {**view["offtake"], "buyers": [
        {**view["offtake"]["buyers"][0], "tenor_years": 12.0}, view["offtake"]["buyers"][1]]}}
    assert "offtake" in _save(a_edit)                        # another buyer's edit goes through
    after = next(s for s in _frame()["sub_legs"] if s["company_id"] == M)
    assert after["sub_leg_hash"] == before and str(after["source_contract_id"]) == STATE["trade"]
    assert M in {r["buyer_company_id"] for r in ct.frame_confirmations(PID)}   # still in force


def test_an_acceptance_that_would_exceed_the_planned_output_is_refused_whole(world):
    from app.core import market_engine as me
    from app.core import order_book as ob

    oid = _sell(ASSET, 10)                                    # up to 3660 t/year on top of 6000 + 1825
    assert _code(lambda: ob.accept_order(_party("u_mf_n1"), oid)) == "EXCEEDS_FRAME_OUTPUT"
    conn = me._conn()
    try:
        fills = conn.execute("SELECT count(*) AS n FROM tb_fill WHERE sell_order_id = ?", (oid,)).fetchone()["n"]
    finally:
        conn.close()
    assert fills == 0 and {s["company_id"] for s in _frame()["sub_legs"]} == {A, M}


def test_without_a_planned_output_the_trade_stays_a_trade(world):
    from app.core import order_book as ob

    _save({"offtake": {"certification_scheme": "RFNBO", "buyers": [{"company_id": A, "tenor_years": 5.0}]}},
          pid=PID_PLAIN)
    r = ob.accept_order(_party("u_mf_n1"), _sell(ASSET_PLAIN, 5))
    assert r["contract_id"] and r["frame_sub_leg_hash"] is None
    assert [s["company_id"] for s in ct.frame_state(PID_PLAIN)["sub_legs"]] == [A]


def test_a_market_sub_leg_changes_hands_only_with_its_trade(world):
    assert _code(lambda: ct.propose_novation(PID, OWNER, M, N, "u_mf_exec", OWNER)) == "MARKET_SUB_LEG_LOCKED"


def test_the_derived_projection_follows_q4():
    from app.core import market_engine as me

    conn = me._conn()
    try:
        short = me.market_terms(conn, molecule="e-Methanol", volume_mtpd=2, price_eur_kg=1, delivery_start="2027-03-01",
                                delivery_end="2027-08-31")
    finally:
        conn.close()
    proj, yearly = ct.derive_projection(short)
    assert proj == {"offtake.first_delivery_date": "2027-03-01", "offtake.tenor_years": 0.0}   # no full year
    assert float(yearly) == 2 * 184
