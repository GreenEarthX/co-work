"""
Party signatures on the contract record (Phase 5 of "One contract record"; alembic 096).

A company registers an ed25519 public key: an executive proposes, a second executive
activates, every step in the ledger; the database keeps the key material fixed and
the four eyes real. A CONFIRMED or DISPUTED event MAY carry the party's signature over
"GEX-CONTRACT-EVENT-v1:" + event_hash: the action is first prepared (nothing written,
the hash returned), then sent signed and verified on write. A bad, stale, foreign or
revoked signature is refused and writes nothing. REQUIRE_PARTY_SIGNATURE (default
false) refuses an unsigned act; unsigned confirmations read "confirmed in GEX, not
signed by the party". Hashes and ledger anchors are unchanged by a signature.

In the throwaway PostgreSQL database (conftest.pg_store).
"""
from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import ledger_anchor as la
from app.core import party_keys as pk
from app.trading_book import record
from pg_support import connect_dsn

OWNER, A, X = "test_ps_owner", "test_ps_buyer_a", "test_ps_other"
PID, ASSET = "proj_TEST_party_signatures", "00000000-0000-4000-8000-0000000096a1"
NAMES = {OWNER: "Test PS Owner", A: "Test PS Buyer A", X: "Test PS Other"}
USERS = {"u_ps_exec": (OWNER, "EXECUTIVE"), "u_ps_a1": (A, "EXECUTIVE"), "u_ps_a2": (A, "EXECUTIVE"),
         "u_ps_a3": (A, "COMMERCIAL"), "u_ps_x1": (X, "EXECUTIVE"), "u_ps_x2": (X, "EXECUTIVE")}
STATE: dict = {}


def _payload(uid, **kw):
    return {"user_id": uid, "company_id": USERS[uid][0], "company_name": NAMES[USERS[uid][0]], **kw}


def _party(uid):
    from app.core import market_engine as me

    return me.Party(user_id=uid, company_id=USERS[uid][0], company_name=NAMES[USERS[uid][0]])


def _keypair():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, base64.b64encode(pub).decode()


def _sign(priv, intent, key_ref, event_hash=None):
    h = event_hash or intent["event_hash"]
    return {"scheme": "ed25519", "signer_key_ref": key_ref, "at": intent["at"], "event_hash": h,
            "signature": base64.b64encode(priv.sign(record.sign_message(h))).decode()}


def _owner_dsn(pg_store):
    return os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + pg_store.rsplit("/", 1)[1]


def _sql(dsn, sql, params=(), company=None):
    conn = connect_dsn(dsn)
    try:
        cur = conn.cursor()
        if company:
            cur.execute("SET app.current_company_id = %s", (company,))
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        conn.commit()
        return rows
    finally:
        conn.close()


@pytest.fixture(scope="module")
def world(pg_store):
    from app.db import session

    saved = session._sync_engine
    session._sync_engine = None
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in NAMES:
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST party signatures plant', %s, 'e-Methanol') ON CONFLICT DO NOTHING", (PID, OWNER))
    cur.execute("INSERT INTO tb_asset (id, project_id, name, location, country_code, technology, capacity_mw, "
                "is_active, created_at, updated_at) VALUES (%s, %s, 'TEST', 'TEST', 'DE', 'PEM', 1, true, now(), "
                "now())", (ASSET, PID))
    for uid, (company, fn) in USERS.items():
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    conn.commit()
    conn.close()
    yield pg_store
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _trade() -> str:
    """A firm sell order for the project's output, accepted by buyer A."""
    from app.core import market_engine as me
    from app.core import order_book as ob
    from app.trading_book.terms import TermsIn

    conn = me._conn()
    try:
        terms = me.market_terms(conn, molecule="e-Methanol", volume_mtpd=3, price_eur_kg=1.1,
                                delivery_start=date(2027, 1, 1), delivery_end=date(2027, 12, 31))
    finally:
        conn.close()
    data = terms.model_dump(mode="json")
    for leg in data["legs"]:
        for f in leg["flows"]:
            f["asset_id"] = ASSET
    o = ob.create_order(_party("u_ps_exec"), TermsIn.model_validate(data), side="sell",
                        valid_until=datetime.now(timezone.utc) + timedelta(days=30))
    ob.open_order(_party("u_ps_exec"), o["id"])
    return ob.accept_order(_party("u_ps_a1"), o["id"])["contract_id"]


class Req:
    def __init__(self, payload):
        self.state = type("S", (), {"user_payload": payload})()


def _approve(contract_id, request_id, uid, **body):
    from app.api.v1 import routes_order_book as r

    return r.approve_confirmation(contract_id, request_id, Req(_payload(uid)), r.SignedAct(**body))


def _code(fn):
    from fastapi import HTTPException

    with pytest.raises((HTTPException, pk.KeyRefused, record.RecordRefused)) as exc:
        fn()
    e = exc.value
    return e.detail["code"] if isinstance(e, HTTPException) else e.code


def _events(world, cid):
    return _sql(_owner_dsn(world), "SELECT * FROM tb_contract_event WHERE contract_id = %s ORDER BY seq", (cid,))


# ── the key registry ────────────────────────────────────────────────────────

def test_an_executive_proposes_and_a_second_executive_activates(world):
    priv, pub = _keypair()
    assert _code(lambda: pk.propose(_payload("u_ps_a3"), pub)) == "EXECUTIVE_ONLY"
    assert _code(lambda: pk.propose(_payload("u_ps_a1", is_platform_admin=True), pub)) == "GEX_DOES_NOT_SIGN"
    assert _code(lambda: pk.propose(_payload("u_ps_a1"), "bm90IGEga2V5")) == "NOT_AN_ED25519_KEY"
    key = pk.propose(_payload("u_ps_a1"), pub, "treasury HSM")
    assert key["status"] == "PROPOSED" and key["key_ref"] == pk.key_ref_for(pub)
    assert _code(lambda: pk.activate(_payload("u_ps_a1"), key["key_ref"])) == "FOUR_EYES"
    assert _code(lambda: pk.activate(_payload("u_ps_x1"), key["key_ref"])) == "KEY_NOT_FOUND"   # RLS: not theirs
    assert pk.list_keys(_payload("u_ps_x1")) == []
    assert pk.activate(_payload("u_ps_a2"), key["key_ref"])["status"] == "ACTIVE"
    ledger = _sql(_owner_dsn(world), "SELECT event_type FROM platform_events WHERE object_id = %s "
                                     "ORDER BY 1", (key["key_ref"],))
    assert [r["event_type"] for r in ledger] == ["party_key.activated", "party_key.proposed"]
    STATE.update(priv=priv, ref=key["key_ref"])
    xpriv, xpub = _keypair()                                   # company X's key, for the foreign-key test
    xk = pk.propose(_payload("u_ps_x1"), xpub)
    pk.activate(_payload("u_ps_x2"), xk["key_ref"])
    STATE.update(xpriv=xpriv, xref=xk["key_ref"])


def test_a_key_change_the_ledger_cannot_record_is_not_made(world, monkeypatch):
    from app.core import event_store

    def down(**kw):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(event_store, "append_event", down)
    _, pub = _keypair()
    assert _code(lambda: pk.propose(_payload("u_ps_a1"), pub)) == "AUDIT_UNAVAILABLE"
    assert not _sql(_owner_dsn(world), "SELECT 1 FROM party_signing_key WHERE public_key = %s", (pub,))


def test_the_database_keeps_the_key_fixed_and_the_four_eyes_real(world):
    owner, ref = _owner_dsn(world), STATE["ref"]
    with pytest.raises(Exception, match="permission denied"):
        _sql(world, "UPDATE party_signing_key SET public_key = 'x' WHERE key_ref = %s", (ref,), company=A)
    for sql, match in (("UPDATE party_signing_key SET public_key = 'x' WHERE key_ref = %s", "PARTY_KEY_FIXED"),
                       ("UPDATE party_signing_key SET status = 'PROPOSED' WHERE key_ref = %s", "PARTY_KEY_TRANSITION"),
                       ("DELETE FROM party_signing_key WHERE key_ref = %s", "PARTY_KEY_KEPT")):
        with pytest.raises(Exception, match=match):
            _sql(owner, sql, (ref,))
    _, pub = _keypair()
    with pytest.raises(Exception, match="PARTY_KEY_STARTS_PROPOSED"):
        _sql(world, "INSERT INTO party_signing_key (company_id, key_ref, scheme, public_key, status, proposed_by, "
                    "approved_by) VALUES (%s, %s, 'ed25519', %s, 'ACTIVE', 'u_ps_a1', 'u_ps_a2')",
             (A, pk.key_ref_for(pub), pub), company=A)
    with pytest.raises(Exception, match="row-level security"):          # a company registers its own keys only
        _sql(world, "INSERT INTO party_signing_key (company_id, key_ref, scheme, public_key, proposed_by) "
                    "VALUES (%s, %s, 'ed25519', %s, 'u_ps_x1')", (A, pk.key_ref_for(pub), pub), company=X)
    p2 = pk.propose(_payload("u_ps_a1"), pub)
    with pytest.raises(Exception, match="ck_party_key_four_eyes"):
        _sql(owner, "UPDATE party_signing_key SET status = 'ACTIVE', approved_by = proposed_by WHERE key_ref = %s",
             (p2["key_ref"],))


# ── signing a confirmation ──────────────────────────────────────────────────

def test_a_prepared_confirmation_writes_nothing_and_its_signature_is_verified_on_write(world):
    from app.core import order_book as ob

    cid = _trade()
    req = ob.request_confirmation(_party("u_ps_a1"), cid)
    before = len(_events(world, cid))
    intent = _approve(cid, req["request_id"], "u_ps_a2", signature_intent=True)["signature_intent"]
    assert intent["message"] == "GEX-CONTRACT-EVENT-v1:" + intent["event_hash"]
    assert len(_events(world, cid)) == before                                    # nothing written
    pending = _sql(_owner_dsn(world), "SELECT status FROM approval_requests WHERE id = %s", (req["request_id"],))
    assert pending and pending[0]["status"] == "PENDING"                        # the approval is not recorded
    out = _approve(cid, req["request_id"], "u_ps_a2", signature=_sign(STATE["priv"], intent, STATE["ref"]))
    assert "signature_intent" not in out
    e = next(e for e in _events(world, cid) if e["event_type"] == "CONFIRMED")
    assert e["event_hash"] == intent["event_hash"] and e["signature_scheme"] == "ed25519"
    assert e["signer_key_ref"] == STATE["ref"]
    # the chain still holds (the signature is beside the hash), and a reader can check it
    chain = la.chain_for(A, False, cid)
    assert chain["chain_intact"]
    signed = next(x for x in chain["events"] if x["event_type"] == "CONFIRMED")
    assert signed["signed_by_party"] and signed["signature_valid"] and signed["signer_key_status"] == "ACTIVE"
    assert signed["signature_label"] == "signed by the party"
    # what is anchored is unchanged: still the five keys
    box = _sql(_owner_dsn(world), "SELECT * FROM ledger_anchor_outbox WHERE event_hash = %s", (e["event_hash"],))[0]
    assert set(la.payload({**box, "pseudo_id": box["pseudo_id"] or "0" * 64})) == set(la.PAYLOAD_KEYS)
    STATE["signed_contract"] = cid


def _prepared(cid, uid="u_ps_a2"):
    from app.core import order_book as ob

    req = ob.request_confirmation(_party("u_ps_a1"), cid)
    return req, _approve(cid, req["request_id"], uid, signature_intent=True)["signature_intent"]


def test_a_bad_foreign_stale_or_expired_signature_is_refused_and_writes_nothing(world):
    cid = _trade()
    req, intent = _prepared(cid)
    n = len(_events(world, cid))
    bad = {**_sign(STATE["priv"], intent, STATE["ref"]),
           "signature": base64.b64encode(STATE["priv"].sign(b"something else")).decode()}
    assert _code(lambda: _approve(cid, req["request_id"], "u_ps_a2", signature=bad)) == "INVALID_SIGNATURE"
    foreign = _sign(STATE["xpriv"], intent, STATE["xref"])
    assert _code(lambda: _approve(cid, req["request_id"], "u_ps_a2", signature=foreign)) == "SIGNER_KEY_NOT_YOURS"
    old = {**_sign(STATE["priv"], intent, STATE["ref"]),
           "at": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()}
    assert _code(lambda: _approve(cid, req["request_id"], "u_ps_a2", signature=old)) == "SIGNATURE_INTENT_EXPIRED"
    # the chain moves on after the event was prepared
    from app.core import market_engine as me
    conn = me._conn()
    record.append_event(conn, cid, "STATUS_CHANGED", "u_ps_exec", OWNER, note="moved")
    conn.commit()
    conn.close()
    stale = _sign(STATE["priv"], intent, STATE["ref"])
    assert _code(lambda: _approve(cid, req["request_id"], "u_ps_a2", signature=stale)) == "SIGNATURE_STALE"
    assert len(_events(world, cid)) == n + 1 and not any(e["event_type"] == "CONFIRMED" for e in _events(world, cid))
    STATE["open"] = (cid, req)


def test_a_revoked_key_signs_nothing_new_and_its_old_signatures_still_read(world):
    priv, pub = _keypair()
    k = pk.propose(_payload("u_ps_a1"), pub)
    pk.activate(_payload("u_ps_a2"), k["key_ref"])
    assert _code(lambda: pk.revoke(_payload("u_ps_a1"), k["key_ref"], "")) == "REASON_REQUIRED"
    assert pk.revoke(_payload("u_ps_a1"), k["key_ref"], "laptop lost")["status"] == "REVOKED"
    cid = _trade()
    req, intent = _prepared(cid)
    assert _code(lambda: _approve(cid, req["request_id"], "u_ps_a2",
                                  signature=_sign(priv, intent, k["key_ref"]))) == "SIGNER_KEY_NOT_ACTIVE"
    # the database refuses it too, whatever the application does
    with pytest.raises(Exception, match="SIGNER_KEY_NOT_ACTIVE"):
        _sql(_owner_dsn(world), "INSERT INTO tb_contract_event (contract_id, seq, event_type, actor, company_id, at, "
             "prev_hash, event_hash, hash_scheme, signature, signature_scheme, signer_key_ref) "
             "SELECT contract_id, seq + 1, 'CONFIRMED', 'u', %s, now(), event_hash, md5('a') || md5('b'), '2', 'c2ln', "
             "'ed25519', %s FROM tb_contract_event WHERE contract_id = %s ORDER BY seq DESC LIMIT 1",
             (A, k["key_ref"], cid))


def test_only_a_confirmation_or_dispute_carries_a_signature(world):
    cid = STATE["signed_contract"]
    with pytest.raises(Exception, match="ck_event_signature"):
        _sql(_owner_dsn(world), "INSERT INTO tb_contract_event (contract_id, seq, event_type, actor, company_id, at, "
             "prev_hash, event_hash, hash_scheme, signature, signature_scheme, signer_key_ref) "
             "SELECT contract_id, seq + 1, 'VERSION', 'u', %s, now(), event_hash, md5('c') || md5('d'), '2', 'c2ln', "
             "'ed25519', %s FROM tb_contract_event WHERE contract_id = %s ORDER BY seq DESC LIMIT 1",
             (A, STATE["ref"], cid))


def test_only_the_partys_own_first_act_is_signed(world):
    """A second CONFIRMED the same act causes (a trade confirming its frame sub-leg, Q7.3)
    is the GEX-side consequence, unsigned; a system event is never a party act."""
    from app.core import market_engine as me

    cid = _trade()
    conn = me._conn()
    try:
        with record.party_act(A, prepare=True):
            # a system event inside the act is written as usual, never taken for the act
            record.append_event(conn, cid, "STATUS_CHANGED", "u_ps_exec", OWNER, note="system")
            conn.rollback()
            conn.close()
            conn = me._conn()
            with pytest.raises(record.SigningIntent) as got:
                record.append_event(conn, cid, "CONFIRMED", "u_ps_a2", A, note="act")
        conn.rollback()
        conn.close()
        conn = me._conn()                          # a rollback also drops the connection's tenant setting
        intent = got.value.intent
        with record.party_act(A, signature=_sign(STATE["priv"], intent, STATE["ref"])):
            first = record.append_event(conn, cid, "CONFIRMED", "u_ps_a2", A, note="act")
            second = record.append_event(conn, cid, "CONFIRMED", "u_ps_a2", A, note="consequence")
        conn.commit()
    finally:
        conn.close()
    rows = {e["event_hash"]: e for e in _events(world, cid)}
    assert first["event_hash"] == intent["event_hash"] and rows[first["event_hash"]]["signature_scheme"] == "ed25519"
    assert rows[second["event_hash"]]["signature_scheme"] == "none"
    view = record.signature_view(rows[second["event_hash"]])
    assert view["signature_label"] == "confirmed in GEX, not signed by the party"


def test_unsigned_acts_stand_by_default_and_are_refused_when_required(world, monkeypatch):
    from app.core.config import settings

    cid, req = STATE["open"]
    monkeypatch.setattr(settings, "REQUIRE_PARTY_SIGNATURE", True)
    assert _code(lambda: _approve(cid, req["request_id"], "u_ps_a2")) == "PARTY_SIGNATURE_REQUIRED"
    assert not any(e["event_type"] == "CONFIRMED" for e in _events(world, cid))
    # a system event outside any party act is never asked for a signature
    from app.core import market_engine as me
    conn = me._conn()
    record.append_event(conn, cid, "DISPUTED", "system", A, note="counterparty changed")
    conn.commit()
    conn.close()
    monkeypatch.setattr(settings, "REQUIRE_PARTY_SIGNATURE", False)
    _approve(cid, req["request_id"], "u_ps_a2")                      # the wae approval was recorded above
    e = [e for e in _events(world, cid) if e["event_type"] == "CONFIRMED"]
    assert len(e) == 1 and e[0]["signature_scheme"] == "none"
    from app.core import order_book as ob
    readout = ob.get_contract(_party("u_ps_a1"), cid)
    conf = next(x for x in readout["events"] if x["event_type"] == "CONFIRMED")
    assert conf["signature_label"] == "confirmed in GEX, not signed by the party" and not conf["signed_by_party"]


def test_a_card_confirmation_route_prepares_without_writing(world):
    """The contract-token routes run the same act helper: a prepared confirmation of a
    card contract writes nothing and returns the hash to sign."""
    from app.api.v1 import routes_contract_tokens as rt
    from app.api.v1.routes_order_book import SignedAct
    from app.core import contract_tokens as ct

    c = ct.contract(PID, "epc")
    n = len(ct.events(c["id"]))
    event, intent = rt._act(_payload("u_ps_a1"), SignedAct(signature_intent=True),
                            lambda: ct.append(c, "DISPUTED", "u_ps_a1", A, note="prepared only"))
    assert event is None and intent["signature_intent"]["event_type"] == "DISPUTED"
    assert len(ct.events(c["id"])) == n
    event, intent = rt._act(_payload("u_ps_a1"),
                            SignedAct(signature=_sign(STATE["priv"], intent["signature_intent"], STATE["ref"])),
                            lambda: ct.append(c, "DISPUTED", "u_ps_a1", A, note="prepared only"))
    assert intent is None
    last = ct.events(c["id"])[-1]
    assert last["signed_by_party"] and last["signature_label"] == "signed by the party"
    assert json.dumps(last["signer_key_ref"]) == json.dumps(STATE["ref"])


def test_a_reader_is_told_when_a_stored_signature_does_not_verify(world):
    """A signature written past the application (as the owner, by hand) is shown as
    not valid: the readout checks it against the key, it does not trust the column."""
    cid = _trade()
    _sql(_owner_dsn(world), "INSERT INTO tb_contract_event (contract_id, seq, event_type, actor, company_id, at, "
         "prev_hash, event_hash, hash_scheme, signature, signature_scheme, signer_key_ref) "
         "SELECT contract_id, seq + 1, 'CONFIRMED', 'u', %s, now(), event_hash, md5(random()::text) || "
         "md5(random()::text), '2', %s, 'ed25519', %s FROM tb_contract_event WHERE contract_id = %s "
         "ORDER BY seq DESC LIMIT 1",
         (A, base64.b64encode(b"\x00" * 64).decode(), STATE["ref"], cid))
    chain = la.chain_for(A, False, cid)
    forged = next(x for x in chain["events"] if x["event_type"] == "CONFIRMED")
    assert forged["signed_by_party"] and forged["signature_valid"] is False
    assert chain["chain_intact"] is False
