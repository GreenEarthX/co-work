"""
The offtake frame — one sub-leg per buyer, each confirmed by that buyer (Phase 3 of
"One contract record", step 4; Phase 0 Q2 and Q3; alembic 092).

A project with several offtakers keeps ONE offtake record: the shared terms and a
sub-leg per buyer, each hashed on its own. Each buyer confirms its own sub-leg;
only buyers whose part changed re-confirm, and a change to the shared terms
withdraws every confirmation. The engine reads one offtake card built from the
confirmed buyers by JML's conservative aggregate (2026-11-10): the volume is the
sum, tenor / take-or-pay / commitment form the weakest buyer's, investment grade
and credit support only if every buyer has them.

Unit tests of the aggregate need nothing; the rest run in the throwaway
PostgreSQL database (conftest.pg_store) with the engine faked.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import contract_tokens as ct
from pg_support import connect_dsn

A, B, C = "test_fr_buyer_a", "test_fr_buyer_b", "test_fr_buyer_c"
SHARED = {"product_spec_standard": "IMPCA 2021", "certification_scheme": "RFNBO", "change_in_law_allocated": True}
BUYER_A = {"company_id": A, "contracted_tonnes_per_year": 30000, "tenor_years": 15, "commitment_form": "TAKE_OR_PAY",
           "take_or_pay_pct": 80, "buyer_investment_grade": True, "credit_support": True}
BUYER_B = {"company_id": B, "contracted_tonnes_per_year": 20000, "tenor_years": 10, "commitment_form": "TAKE_IF_TENDERED",
           "buyer_investment_grade": True, "credit_support": False}
FRAME = {"offtake": {**SHARED, "planned_output_tonnes_per_year": 60000, "buyers": [BUYER_A, BUYER_B]}}


def _conf(company, buyer, shared=SHARED):
    return {"buyer_company_id": company, "shared_terms": {f"offtake.{k}": v for k, v in shared.items()},
            "sub_leg_terms": {f"offtake.{k}": v for k, v in buyer.items() if k != "company_id"}}


# ── the aggregate (pure) ────────────────────────────────────────────────────

def test_nothing_of_the_frame_reaches_the_engine_before_a_buyer_confirms():
    used, held = ct.engine_terms(FRAME, {}, [])
    assert "offtake" not in used
    assert "offtake.contracted_tonnes_per_year (2 of 2 buyers not confirmed)" in held["offtake"]


def test_one_confirmed_buyer_counts_its_volume_and_nothing_that_needs_every_buyer():
    used, held = ct.engine_terms(FRAME, {}, [_conf(A, BUYER_A)])
    assert used["offtake"] == {"contracted_tonnes_per_year": 30000}
    assert {"offtake.tenor_years", "offtake.commitment_form", "offtake.product_spec_standard"} <= set(held["offtake"])


def test_with_every_buyer_confirmed_the_engine_reads_the_conservative_aggregate():
    used, held = ct.engine_terms(FRAME, {}, [_conf(A, BUYER_A), _conf(B, BUYER_B)])
    assert used["offtake"] == {**SHARED, "contracted_tonnes_per_year": 50000, "tenor_years": 10,
                               "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80,
                               "buyer_investment_grade": True, "credit_support": False}
    assert not held.get("offtake")


def test_a_shared_change_withdraws_every_buyers_confirmation():
    edited = {"offtake": {**FRAME["offtake"], "certification_scheme": "ISCC PLUS"}}
    used, held = ct.engine_terms(edited, {}, [_conf(A, BUYER_A), _conf(B, BUYER_B)])
    assert "offtake" not in used


def test_only_the_changed_buyer_re_confirms():
    edited = {"offtake": {**FRAME["offtake"], "buyers": [BUYER_A, {**BUYER_B, "contracted_tonnes_per_year": 25000}]}}
    used, held = ct.engine_terms(edited, {}, [_conf(A, BUYER_A), _conf(B, BUYER_B)])
    assert used["offtake"]["contracted_tonnes_per_year"] == 30000           # A still counts; B's new volume waits
    assert "offtake.contracted_tonnes_per_year (1 of 2 buyers not confirmed)" in held["offtake"]
    assert used["offtake"]["tenor_years"] == 10                             # B's tenor did not change


def test_a_field_the_rule_does_not_name_counts_only_when_every_buyer_agrees():
    a, b = {**BUYER_A, "price_mechanism": "FIXED"}, {**BUYER_B, "price_mechanism": "INDEX_PLUS_PREMIUM"}
    frame = {"offtake": {**FRAME["offtake"], "buyers": [a, b]}}
    used, held = ct.engine_terms(frame, {}, [_conf(A, a), _conf(B, b)])
    assert "price_mechanism" not in used["offtake"]
    assert "offtake.price_mechanism (the buyers' values differ)" in held["offtake"]


def test_a_card_without_buyers_is_read_exactly_as_before():
    cards = {"offtake": {"contracted_tonnes_per_year": 40000, "tenor_years": 15}}
    confirmed = {"offtake": ct.kind_terms(cards, "offtake")}
    assert ct.engine_terms(cards, confirmed, [_conf(A, BUYER_A)]) == ct.engine_terms(cards, confirmed)


def test_the_card_refuses_a_malformed_frame():
    from app.core.commitment_terms import TermsValidationError, validate_card

    for bad in ([{"contracted_tonnes_per_year": 1}],                                # no company
                [{"company_id": A}, {"company_id": A}],                             # twice
                [{"company_id": A, "certification_scheme": "x"}]):                  # a shared field in a buyer
        with pytest.raises(TermsValidationError):
            validate_card("offtake", {"buyers": bad})
    with pytest.raises(TermsValidationError, match="not at the top"):
        validate_card("offtake", {"tenor_years": 5, "buyers": [{"company_id": A}]})
    assert validate_card("offtake", FRAME["offtake"])["buyers"][1]["company_id"] == B


def test_the_record_refuses_a_frame_whose_sub_legs_repeat_or_lack_a_buyer():
    """C03 (trading_book/validation.py): the record's own check, behind the card's."""
    from app.trading_book.terms import SubLegIn, TermsIn
    from app.trading_book.validation import validate_card

    def frame(*subs):
        return TermsIn(profile="card", card_projection={"offtake.certification_scheme": "RFNBO"}, sub_legs=list(subs))

    one = {"offtake.tenor_years": 10}
    assert validate_card(frame(SubLegIn(seq=1, buyer="x", card_projection=one),
                               SubLegIn(seq=2, buyer="y", card_projection=one))) == []
    assert validate_card(frame(SubLegIn(seq=1, buyer="x", card_projection=one),
                               SubLegIn(seq=2, buyer="x", card_projection=one))) == ["C03"]
    assert validate_card(frame(SubLegIn(seq=1, buyer=None, card_projection=one))) == ["C03"]


# ── PostgreSQL: the record, the routes ──────────────────────────────────────

OWNER, OUTSIDER = "test_fr_owner", "test_fr_outsider"
PID = "proj_TEST_offtake_frame"
NAMES = {OWNER: "Test FR Owner", A: "Test FR Buyer A", B: "Test FR Buyer B", C: "Test FR Buyer C",
         OUTSIDER: "Test FR Outsider", "greenearthx": "GreenEarthX"}
USERS = {"u_fr_exec": (OWNER, "EXECUTIVE", False), "u_fr_a": (A, "COMMERCIAL", False),
         "u_fr_b": (B, "COMMERCIAL", False), "u_fr_c": (C, "COMMERCIAL", False),
         "u_fr_out": (OUTSIDER, "EXECUTIVE", False),
         "u_fr_gex": ("greenearthx", "EXECUTIVE", True)}


def _h(uid):
    company, fn, gex = USERS[uid]
    return {"x-test-payload": json.dumps({"user_id": uid, "company_id": company, "company_name": NAMES[company],
                                          "business_function": fn, "is_platform_admin": gex})}


@pytest.fixture(scope="module")
def client(pg_store):
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in (OWNER, A, B, C, OUTSIDER):
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST frame plant', %s, 'H2') ON CONFLICT DO NOTHING", (PID, OWNER))
    for company in (A, B, C):
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                    "(%s, %s, 'OFFTAKER', 'STAKEHOLDER')", (PID, company))
    for uid, (company, fn, _) in USERS.items():
        if company == "greenearthx":
            continue
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    cur.execute("INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by, document_hash, "
                "maturity) VALUES (%s, 'binding_offtake_contract_executed', 'SUBMITTED', 'u_fr_exec', %s, 'EXECUTED')",
                (PID, "c" * 64))
    conn.commit()
    conn.close()

    from app.api.v1 import routes_bankability_proxy as proxy, routes_contract_tokens
    from app.db import session

    async def engine(path, method="GET", json_data=None):
        if path == "/rules":
            return {"rules_version": "t", "persona_gates": {"EXECUTIVE": []}}
        return {"current_state": "SPECULATIVE", "rules_version": "t", "gate_evaluations": []}

    saved_engine, saved_session, saved_raw = proxy._call_engine, session._sync_engine, proxy._load_terms_raw
    proxy._call_engine = engine
    proxy._load_terms_raw = lambda pid: STATE["cards"] if pid == PID else saved_raw(pid)
    session._sync_engine = None
    app = FastAPI()

    @app.middleware("http")
    async def bind(request: Request, call_next):
        from app.core.request_tenant import (reset_current_company, reset_current_user, set_current_company,
                                             set_current_user)
        payload = json.loads(request.headers["x-test-payload"])
        request.state.user_payload = payload
        t1 = set_current_company("PLATFORM_ADMIN" if payload["is_platform_admin"] else payload["company_id"])
        t2 = set_current_user(payload["user_id"])
        try:
            return await call_next(request)
        finally:
            reset_current_company(t1)
            reset_current_user(t2)

    app.include_router(routes_contract_tokens.router, prefix="/api/v1")
    yield TestClient(app)
    proxy._call_engine, proxy._load_terms_raw = saved_engine, saved_raw
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved_session


STATE: dict = {}


def _save(cards):
    from app.core.request_tenant import reset_current_company, set_current_company

    STATE["cards"] = cards
    t = set_current_company(OWNER)
    try:
        return ct.record_versions(PID, cards, "u_fr_exec", OWNER)
    finally:
        reset_current_company(t)


def _frame(client, uid="u_fr_exec"):
    return next(t for t in client.get(f"/api/v1/contract-tokens/{PID}", headers=_h(uid)).json()["tokens"]
                if t["kind"] == "offtake")["frame"]


def _engine_offtake():
    from app.api.v1.routes_bankability_proxy import _load_terms
    from app.core.request_tenant import reset_current_company, set_current_company

    t = set_current_company(OWNER)
    try:
        return _load_terms(PID).get("offtake", {})
    finally:
        reset_current_company(t)


def _confirm(client, uid, company, sub_leg_hash):
    return client.post(f"/api/v1/contract-tokens/{PID}/offtake/buyers/{company}/confirm", headers=_h(uid),
                       json={"sub_leg_hash": sub_leg_hash})


def test_a_frame_version_holds_one_hashed_sub_leg_per_buyer(client):
    from app.core import market_engine as me
    from app.trading_book import canonical, record

    assert "offtake" in _save(FRAME)
    frame = _frame(client)
    assert [b["company_id"] for b in frame["buyers"]] == [A, B] and not any(b["confirmed"] for b in frame["buyers"])
    conn = me._conn()
    try:
        state = ct.frame_state(PID, conn=conn)
        terms = record.load_terms(conn, record.current_version(conn, state["contract_id"])["terms_id"])
        assert record.stored_hashes_hold(conn, record.current_version(conn, state["contract_id"])["terms_id"])
        h = canonical.hashes(terms)
        assert [s["sub_leg_hash"].strip() for s in state["sub_legs"]] == [h["sub_legs"][1], h["sub_legs"][2]]
        assert record.chain_intact(conn, state["contract_id"])
    finally:
        conn.close()
    assert _engine_offtake() == {}


def test_each_buyer_confirms_its_own_sub_leg_only(client):
    frame = _frame(client)
    ha, hb = (b["sub_leg_hash"] for b in frame["buyers"])
    assert _confirm(client, "u_fr_a", B, hb).json()["detail"]["code"] == "OWN_SUB_LEG_ONLY"
    assert _confirm(client, "u_fr_gex", A, ha).json()["detail"]["code"] == "GEX_DOES_NOT_CONFIRM"
    assert _confirm(client, "u_fr_out", OUTSIDER, ha).status_code == 404           # not a project party at all
    assert _confirm(client, "u_fr_c", C, ha).json()["detail"]["code"] == "NOT_A_BUYER_OF_THIS_FRAME"
    assert _confirm(client, "u_fr_a", A, hb).json()["detail"]["code"] == "NOT_THE_LATEST_VERSION"
    assert client.post(f"/api/v1/contract-tokens/{PID}/offtake/confirm", headers=_h("u_fr_a"),
                       json={"terms_sha256": "x"}).json()["detail"]["code"] == "FRAME_CONFIRMS_PER_BUYER"
    assert client.put(f"/api/v1/contract-tokens/{PID}/offtake/counterparty", headers=_h("u_fr_exec"),
                      json={"company_id": A}).json()["detail"]["code"] == "FRAME_HAS_BUYERS"
    ok = _confirm(client, "u_fr_a", A, ha)
    assert ok.status_code == 200, ok.text
    assert ok.json()["evidence_verified"] == ["binding_offtake_contract_executed"]
    assert [b["confirmed"] for b in _frame(client)["buyers"]] == [True, False]
    assert _engine_offtake() == {"contracted_tonnes_per_year": 30000}


def test_with_both_confirmed_the_engine_reads_the_aggregate(client):
    hb = _frame(client)["buyers"][1]["sub_leg_hash"]
    assert _confirm(client, "u_fr_b", B, hb).status_code == 200
    assert _engine_offtake() == {**SHARED, "contracted_tonnes_per_year": 50000, "tenor_years": 10,
                                 "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80,
                                 "buyer_investment_grade": True, "credit_support": False}


def test_after_an_edit_only_the_changed_buyer_re_confirms(client):
    edited = {"offtake": {**FRAME["offtake"], "buyers": [BUYER_A, {**BUYER_B, "contracted_tonnes_per_year": 25000}]}}
    assert "offtake" in _save(edited)
    frame = _frame(client)
    assert [b["confirmed"] for b in frame["buyers"]] == [True, False]          # A's sub-leg hash did not move
    assert _engine_offtake()["contracted_tonnes_per_year"] == 30000
    assert _confirm(client, "u_fr_b", B, frame["buyers"][1]["sub_leg_hash"]).status_code == 200
    assert _engine_offtake()["contracted_tonnes_per_year"] == 55000


def test_a_shared_change_withdraws_both_and_a_dispute_withdraws_one(client):
    shared_edit = {"offtake": {**STATE["cards"]["offtake"], "certification_scheme": "ISCC PLUS"}}
    _save(shared_edit)
    assert [b["confirmed"] for b in _frame(client)["buyers"]] == [False, False]
    assert _engine_offtake() == {}
    for uid, company, n in (("u_fr_a", A, 0), ("u_fr_b", B, 1)):
        assert _confirm(client, uid, company, _frame(client)["buyers"][n]["sub_leg_hash"]).status_code == 200
    assert _engine_offtake()["contracted_tonnes_per_year"] == 55000
    r = client.post(f"/api/v1/contract-tokens/{PID}/offtake/buyers/{B}/dispute", headers=_h("u_fr_b"),
                    json={"note": "TEST: the volume is not what we signed"})
    assert r.status_code == 200, r.text
    assert _engine_offtake() == {"contracted_tonnes_per_year": 30000}


def test_the_card_save_refuses_a_buyer_that_is_not_a_project_party():
    from app.api.v1.routes_bankability_proxy import _check_frame_buyers
    from app.core.commitment_terms import TermsValidationError

    with pytest.raises(TermsValidationError, match="not a company party"):
        _check_frame_buyers(PID, [{"company_id": OUTSIDER}])
    with pytest.raises(TermsValidationError, match="own buyer"):
        _check_frame_buyers(PID, [{"company_id": OWNER}])


def test_q5_a_buyer_reads_its_own_sub_leg_and_the_other_only_as_a_share(client, pg_store):
    """RLS (092): a buyer's session reads its own card sub-leg only; the owner and a
    project party that is not a buyer read both. The readout shows the other buyer
    as a hash and a volume share, never its company."""
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    seen = {}
    for company in (OWNER, A, B, C, OUTSIDER):
        cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute("SELECT cp.company_id FROM tb_sub_leg s JOIN tb_terms t ON t.id = s.terms_id "
                    "JOIN tb_counterparty cp ON cp.id = s.buyer_id JOIN tb_contract_version v ON v.terms_id = t.id "
                    "JOIN tb_contract c ON c.id = v.contract_id WHERE c.project_id = %s AND v.superseded_at IS NULL "
                    "AND s.card_projection IS NOT NULL", (PID,))
        seen[company] = sorted(r["company_id"] for r in cur.fetchall())
    conn.close()
    assert seen == {OWNER: [A, B], A: [A], B: [B], C: [A, B], OUTSIDER: []}
    frame = _frame(client, uid="u_fr_b")
    assert [b["company_id"] for b in frame["buyers"]] == [None, B]
    assert all(b["sub_leg_hash"] and b["volume_share"] for b in frame["buyers"])
    assert [b["company_id"] for b in _frame(client, uid="u_fr_c")["buyers"]] == [A, B]


def test_q5_the_card_shows_a_buyer_its_own_entry_only():
    from app.api.v1.routes_bankability_proxy import _hide_other_buyers

    cards = {"offtake": {"terms": {**SHARED, "buyers": [BUYER_A, BUYER_B]}}}
    _hide_other_buyers(cards, B, OWNER)
    assert cards["offtake"]["terms"]["buyers"] == [{"company_id": None, "hidden": True, "volume_share": 0.6}, BUYER_B]
    owners = {"offtake": {"terms": {**SHARED, "buyers": [BUYER_A, BUYER_B]}}}
    _hide_other_buyers(owners, OWNER, OWNER)
    assert owners["offtake"]["terms"]["buyers"] == [BUYER_A, BUYER_B]


def test_a_frame_turned_back_into_one_buyer_counts_no_buyers_confirmation(client):
    """092: a sub-leg's CONFIRMED is never the whole contract's. A card with no
    buyers is a single-counterparty offtake again, confirmed by its registered
    counterparty only; the buyers' earlier sub-leg confirmations do not carry over."""
    # A buyer's CONFIRMED is the chain's last decisive event, and the single card keeps the
    # frame's shared terms — so only 092's filter keeps it from reading as the contract's.
    assert _confirm(client, "u_fr_b", B, _frame(client)["buyers"][1]["sub_leg_hash"]).status_code == 200
    shared_now = {k: v for k, v in STATE["cards"]["offtake"].items() if k != "buyers"}
    single = {"offtake": {**shared_now, "contracted_tonnes_per_year": 30000, "tenor_years": 15}}
    _save(single)
    assert _frame(client) is None
    assert _engine_offtake() == {}
