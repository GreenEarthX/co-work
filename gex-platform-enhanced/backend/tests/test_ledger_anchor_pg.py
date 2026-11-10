"""
The ledger anchor outbox, in PostgreSQL (Phase 4 of "One contract record"; alembic 095).

Every event on the record writes one outbox row in its own transaction (by trigger,
so no writer can forget it); the runtime reads it under the record's RLS and writes
nothing; the worker's role writes only the anchoring columns; what is anchored never
changes and no row is ever removed. The worker drains with NullAnchor (rows marked
NOT_ANCHORED) or an adapter (here a fake), backs off, gives up after eight attempts,
and two workers never claim the same row. The parties read the chain with its
anchors; a buyer gets the Merkle proof of its own sub-leg. verify_anchor finds a
changed ledger message, a broken chain and duplicate messages.

No ledger is reached: a fake adapter stands in for Hedera (JML's prompt §8). In the
throwaway PostgreSQL database (conftest.pg_store), which other modules share — so
every count here is scoped to this module's own contracts.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core import contract_tokens as ct
from app.core import ledger_anchor as la
from pg_support import connect_dsn

OWNER, A, B, X = "test_la_owner", "test_la_buyer_a", "test_la_buyer_b", "test_la_stranger"
PID = "proj_TEST_ledger_anchor"
ASSET = "00000000-0000-4000-8000-0000000095a1"
NAMES = {OWNER: "Test LA Owner GmbH", A: "Test LA Buyer A SA", B: "Test LA Buyer B AG", X: "Test LA Stranger Ltd"}
USERS = {"u_la_exec": (OWNER, "EXECUTIVE"), "u_la_a1": (A, "EXECUTIVE"), "u_la_a2": (A, "COMMERCIAL"),
         "u_la_b1": (B, "EXECUTIVE"), "u_la_x": (X, "EXECUTIVE")}
SALT = "test-ledger-anchor-salt-not-a-secret"
PRICE, VOLUME = "1.37", 7
FRAME = {"offtake": {"certification_scheme": "RFNBO", "planned_output_tonnes_per_year": 40000, "buyers": [
    {"company_id": A, "contracted_tonnes_per_year": 12000.0, "tenor_years": 10.0},
    {"company_id": B, "contracted_tonnes_per_year": 9000.0, "tenor_years": 8.0}]}}
STATE: dict = {}


class FakeAnchor(la.LedgerAnchor):
    """An in-memory topic in Hedera's shapes: what a ledger would have received."""
    name, network = "fake", "fake:test"

    def __init__(self, fail: bool = False):
        self.topic, self.log, self.fail = "0.0.95", [], fail

    def submit(self, data: bytes) -> la.AnchorReceipt:
        if self.fail:
            raise la.AnchorUnavailable("ledger down (fake)")
        self.log.append({"sequence_number": len(self.log) + 1, "message": data,
                         "consensus_timestamp": f"1762790400.{len(self.log) + 1:09d}"})
        return la.AnchorReceipt(network=self.network, topic_id=self.topic, sequence_number=len(self.log),
                                transaction_id=f"0.0.2@1762790400.{len(self.log)}")

    def lookup(self, topic_id, sequence_number):
        return next((m for m in self.log if m["sequence_number"] == sequence_number), None)

    def messages(self, topic_id):
        return iter(self.log)


def _owner_dsn(pg_store):
    return os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + pg_store.rsplit("/", 1)[1]


def _worker(pg_store):
    """A connection AS gex_anchor (the owner SETs ROLE; no password needed in a test)."""
    def connect():
        conn = connect_dsn(_owner_dsn(pg_store))
        conn.cursor().execute("SET ROLE gex_anchor")
        conn.commit()
        return conn
    return connect


def _party(uid):
    from app.core import market_engine as me

    return me.Party(user_id=uid, company_id=USERS[uid][0], company_name=NAMES[USERS[uid][0]])


@pytest.fixture(scope="module")
def world(pg_store):
    from app.core.config import settings
    from app.db import session

    saved = session._sync_engine
    session._sync_engine = None
    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "LEDGER_ANCHOR_SALT", SALT)
    conn = connect_dsn(pg_store)
    cur = conn.cursor()
    cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
    for company in NAMES:
        cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) VALUES "
                    "(%s, %s, 'PRODUCER', 'DE') ON CONFLICT DO NOTHING", (company, NAMES[company]))
    cur.execute("INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
                "(%s, 'TEST ledger anchor plant', %s, 'e-Methanol') ON CONFLICT DO NOTHING", (PID, OWNER))
    cur.execute("INSERT INTO tb_asset (id, project_id, name, location, country_code, technology, capacity_mw, "
                "is_active, created_at, updated_at) VALUES (%s, %s, 'TEST', 'TEST', 'DE', 'PEM', 1, true, now(), "
                "now())", (ASSET, PID))
    for buyer in (A, B):
        cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role) VALUES "
                    "(%s, %s, 'OFFTAKER', 'STAKEHOLDER')", (PID, buyer))
    for uid, (company, fn) in USERS.items():
        cur.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                    "business_function, user_name, account_state) VALUES (%s, %s, 'TEST', %s, %s, 'PRODUCER', %s, %s, "
                    "'ACTIVE') ON CONFLICT DO NOTHING", (uid, f"{uid}@test.invalid", company, NAMES[company], fn, uid))
    conn.commit()
    conn.close()
    STATE["trade"] = _trade()
    STATE["frame"] = _frame()
    yield pg_store
    mp.undo()
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _trade() -> dict:
    """A firm sell order for the project's output, accepted by buyer A: a trade record."""
    from app.core import market_engine as me
    from app.core import order_book as ob
    from app.trading_book.terms import TermsIn

    conn = me._conn()
    try:
        terms = me.market_terms(conn, molecule="e-Methanol", volume_mtpd=VOLUME, price_eur_kg=float(PRICE),
                                delivery_start=date(2027, 1, 1), delivery_end=date(2027, 12, 31))
    finally:
        conn.close()
    data = terms.model_dump(mode="json")
    for leg in data["legs"]:
        for f in leg["flows"]:
            f["asset_id"] = ASSET
    owner = _party("u_la_exec")
    o = ob.create_order(owner, TermsIn.model_validate(data), side="sell",
                        valid_until=datetime.now(timezone.utc) + timedelta(days=30))
    ob.open_order(owner, o["id"])
    r = ob.accept_order(_party("u_la_a1"), o["id"])
    req = ob.request_confirmation(_party("u_la_a1"), r["contract_id"])
    ob.approve_confirmation(_party("u_la_a2"), r["contract_id"], req["request_id"])
    return {"id": r["contract_id"], "terms": data}


def _frame() -> str:
    from app.core.request_tenant import reset_current_company, set_current_company

    t = set_current_company(OWNER)
    try:
        ct.record_versions(PID, FRAME, "u_la_exec", OWNER, card_type="offtake")
    finally:
        reset_current_company(t)
    return ct.contract(PID, "offtake", create=False)["id"]


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


def _outbox(world, contract_id):
    return _sql(_owner_dsn(world), "SELECT * FROM ledger_anchor_outbox WHERE contract_id = %s ORDER BY id",
                (contract_id,))


def _events(world, contract_id):
    return _sql(_owner_dsn(world), "SELECT * FROM tb_contract_event WHERE contract_id = %s ORDER BY seq",
                (contract_id,))


def _refused(fn, match):
    with pytest.raises(Exception, match=match):
        fn()


# ── the outbox is written with every event ──────────────────────────────────

def test_every_event_writes_one_outbox_row_in_its_transaction(world):
    for cid in (STATE["trade"]["id"], STATE["frame"]):
        evs, box = _events(world, cid), _outbox(world, cid)
        ref = _sql(_owner_dsn(world), "SELECT contract_ref, pseudo_id FROM tb_contract WHERE id = %s", (cid,))[0]
        assert ref["pseudo_id"] == la.pseudo_id(ref["contract_ref"], SALT)
        assert evs and [o["event_id"] for o in box] == [e["id"] for e in evs]
        for e, o in zip(evs, box):
            assert (o["event_hash"], o["prev_hash"], o["event_type"]) == (e["event_hash"], e["prev_hash"],
                                                                           e["event_type"])
            assert o["pseudo_id"] == ref["pseudo_id"] and (o["status"], o["attempts"]) == ("PENDING", 0)


def test_a_rolled_back_event_leaves_no_outbox_row(world):
    from app.core import market_engine as me
    from app.trading_book import record

    before = len(_outbox(world, STATE["trade"]["id"]))
    conn = me._conn()
    try:
        record.append_event(conn, STATE["trade"]["id"], "STATUS_CHANGED", "u_la_exec", OWNER, note="rolled back")
        conn.rollback()
    finally:
        conn.close()
    assert len(_outbox(world, STATE["trade"]["id"])) == before


def test_the_runtime_reads_the_outbox_and_writes_nothing(world):
    cid = STATE["trade"]["id"]
    for sql in ("INSERT INTO ledger_anchor_outbox (event_id, contract_id, event_type, event_hash) "
                "SELECT id, contract_id, event_type, md5(random()::text) || md5(random()::text) "
                "FROM tb_contract_event LIMIT 1",
                "UPDATE ledger_anchor_outbox SET status = 'ANCHORED' WHERE contract_id = %s",
                "DELETE FROM ledger_anchor_outbox WHERE contract_id = %s"):
        _refused(lambda: _sql(world, sql, (cid,) if "%s" in sql else (), company="PLATFORM_ADMIN"),
                 "permission denied")


def test_the_parties_read_their_contracts_anchors_and_nobody_else_does(world):
    cid = STATE["trade"]["id"]
    n = len(_outbox(world, cid))
    read = "SELECT count(*) AS n FROM ledger_anchor_outbox WHERE contract_id = %s"
    assert _sql(world, read, (cid,), company=OWNER)[0]["n"] == n
    assert _sql(world, read, (cid,), company=A)[0]["n"] == n
    assert _sql(world, read, (cid,), company=X)[0]["n"] == 0
    assert _sql(world, read, (cid,), company="__no_tenant_context__")[0]["n"] == 0


def test_the_worker_role_writes_only_the_anchoring_columns(world):
    conn = _worker(world)()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE ledger_anchor_outbox SET last_error = 'probe' WHERE contract_id = %s",
                    (STATE["trade"]["id"],))
        assert cur.rowcount >= 1                               # it sees every row, under its own policy
        conn.rollback()
        for sql in ("UPDATE ledger_anchor_outbox SET event_hash = repeat('0', 64)",
                    "UPDATE ledger_anchor_outbox SET pseudo_id = repeat('0', 64)",
                    "DELETE FROM ledger_anchor_outbox",
                    "SELECT 1 FROM tb_contract LIMIT 1",
                    "SELECT 1 FROM tb_contract_event LIMIT 1",
                    "SELECT 1 FROM tb_terms LIMIT 1"):
            with pytest.raises(Exception, match="permission denied"):
                cur.execute(sql)
            conn.rollback()
    finally:
        conn.close()


def test_what_is_anchored_never_changes_and_no_row_is_removed(world):
    owner, cid = _owner_dsn(world), STATE["trade"]["id"]
    _refused(lambda: _sql(owner, "UPDATE ledger_anchor_outbox SET event_hash = repeat('0', 64) "
                                 "WHERE contract_id = %s", (cid,)), "ANCHOR_OUTBOX_IDENTITY")
    _refused(lambda: _sql(owner, "UPDATE ledger_anchor_outbox SET prev_hash = NULL WHERE contract_id = %s",
                          (cid,)), "ANCHOR_OUTBOX_IDENTITY")
    _refused(lambda: _sql(owner, "DELETE FROM ledger_anchor_outbox WHERE contract_id = %s", (cid,)),
             "ANCHOR_OUTBOX_KEPT")
    _refused(lambda: _sql(owner, "UPDATE tb_contract SET pseudo_id = repeat('1', 64) WHERE id = %s", (cid,)),
             "PSEUDO_ID_FIXED")


# ── the drain ───────────────────────────────────────────────────────────────

def test_with_anchoring_off_the_drain_marks_rows_not_anchored(world):
    la.drain_once(_worker(world), la.NullAnchor(), batch=100000)
    box = _outbox(world, STATE["trade"]["id"])
    assert {o["status"] for o in box} == {"NOT_ANCHORED"}
    assert all(o["ledger_topic_id"] is None and o["anchored_at"] is None for o in box)
    conn = _worker(world)()
    conn.cursor().execute("UPDATE ledger_anchor_outbox SET status = 'PENDING', next_attempt_at = now() "
                          "WHERE status = 'NOT_ANCHORED'")      # what --requeue-not-anchored does
    conn.commit()
    conn.close()


def test_an_adapter_records_the_ledger_reference_and_exactly_five_keys_leave(world):
    fake = FakeAnchor()
    STATE["fake"] = fake
    counts = la.drain_once(_worker(world), fake, batch=100000)
    assert counts["anchored"] >= 1 and counts["timestamps"] >= 1
    for cid in (STATE["trade"]["id"], STATE["frame"]):
        for o in _outbox(world, cid):
            assert o["status"] == "ANCHORED" and o["ledger_network"] == "fake:test" and o["anchored_at"]
            sent = next(m for m in fake.log if m["sequence_number"] == o["ledger_sequence_number"])
            assert json.loads(sent["message"]) == la.payload(o)
            assert o["ledger_consensus_timestamp"] == sent["consensus_timestamp"]


def test_the_payload_carries_no_identifier_price_or_volume(world):
    cid = STATE["trade"]["id"]
    ref = _sql(_owner_dsn(world), "SELECT contract_ref, origin_ref FROM tb_contract WHERE id = %s", (cid,))[0]
    forbidden = [*NAMES, *NAMES.values(), *USERS, cid, ref["contract_ref"], ref["origin_ref"], PID, ASSET]
    numbers = {PRICE, f"{VOLUME}.0", f"{VOLUME * 365}"}
    payloads = [json.loads(m["message"]) for m in STATE["fake"].log]
    assert payloads and all(tuple(sorted(p)) == tuple(sorted(la.PAYLOAD_KEYS)) for p in payloads)
    for p in payloads:
        for v in p.values():
            text = str(v)
            assert not any(f.lower() in text.lower() for f in forbidden), (v, "names an identifier")
            assert not any(n in text for n in numbers if "." in n) and text not in numbers, (v, "a price or volume")


def test_an_anchored_row_keeps_its_reference_for_good(world):
    conn = _worker(world)()
    cur = conn.cursor()
    try:
        for sql in ("UPDATE ledger_anchor_outbox SET status = 'PENDING' WHERE contract_id = %s",
                    "UPDATE ledger_anchor_outbox SET ledger_sequence_number = ledger_sequence_number + 1 "
                    "WHERE contract_id = %s",
                    "UPDATE ledger_anchor_outbox SET ledger_consensus_timestamp = '1.1' WHERE contract_id = %s"):
            with pytest.raises(Exception, match="ANCHOR_REFERENCE_FIXED"):
                cur.execute(sql, (STATE["trade"]["id"],))
            conn.rollback()
    finally:
        conn.close()


def _new_events(n: int) -> list[str]:
    from app.core import market_engine as me
    from app.trading_book import record

    conn = me._conn()
    try:
        out = [record.append_event(conn, STATE["trade"]["id"], "STATUS_CHANGED", "u_la_exec", OWNER,
                                   note=json.dumps({"probe": i}))["event_hash"] for i in range(n)]
        conn.commit()
        return out
    finally:
        conn.close()


def test_a_failing_ledger_backs_off_and_fails_after_eight_attempts(world):
    (h,) = _new_events(1)
    row = lambda: next(o for o in _outbox(world, STATE["trade"]["id"]) if o["event_hash"] == h)  # noqa: E731
    la.drain_once(_worker(world), FakeAnchor(fail=True), batch=100000)
    r = row()
    assert (r["status"], r["attempts"]) == ("PENDING", 1) and "ledger down" in r["last_error"]
    wait = (r["next_attempt_at"] - datetime.now(timezone.utc)).total_seconds()
    assert 50 < wait <= 60
    for _ in range(7):
        conn = _worker(world)()
        conn.cursor().execute("UPDATE ledger_anchor_outbox SET next_attempt_at = now() WHERE event_hash = %s", (h,))
        conn.commit()
        conn.close()
        la.drain_once(_worker(world), FakeAnchor(fail=True), batch=100000)
    r = row()
    assert (r["status"], r["attempts"]) == ("FAILED", 8)
    # The contract event itself was never blocked: it is in the record, chained.
    assert any(e["event_hash"] == h for e in _events(world, STATE["trade"]["id"]))


def test_two_workers_never_claim_the_same_row(world):
    hashes = set(_new_events(3))
    first, second = _worker(world)(), _worker(world)()
    try:
        cur = first.cursor()
        cur.execute(la.CLAIM, (la.LEASE_SECONDS, False, 100000))           # held, not yet committed
        held = {r["event_hash"] for r in cur.fetchall()}
        assert hashes <= held
        taken = {r["event_hash"] for r in la.claim(second, FakeAnchor(), batch=100000)}
        assert not taken & held                                           # SKIP LOCKED
        first.commit()
        assert not {r["event_hash"] for r in la.claim(second, FakeAnchor(), batch=100000)} & hashes   # the lease
    finally:
        first.close()
        second.close()
    conn = _worker(world)()                                               # release for the tests after
    conn.cursor().execute("UPDATE ledger_anchor_outbox SET next_attempt_at = now() WHERE status = 'PENDING'")
    conn.commit()
    conn.close()


def test_a_pseudo_id_set_late_reaches_the_earlier_rows(world):
    from app.core import market_engine as me
    from app.core.config import settings
    from app.trading_book import record

    conn = me._conn()
    try:
        settings.LEDGER_ANCHOR_SALT = ""                                  # restored by the world's MonkeyPatch
        cid = str(record.create_contract(conn, terms=record.load_terms(conn, _terms_id(conn)), owner_company_id=OWNER,
                                         kind="trade", project_id=PID, origin_ref="test_la_late", correlation_id=None,
                                         actor="u_la_exec", company_id=OWNER, note="no salt yet")["id"])
        conn.commit()
    finally:
        settings.LEDGER_ANCHOR_SALT = SALT
        conn.close()
    assert [o["pseudo_id"] for o in _outbox(world, cid)] == [None]
    w = _worker(world)()
    try:                                                              # never sent without one
        assert _outbox(world, cid)[0]["event_hash"] not in {o["event_hash"] for o in la.claim(w, FakeAnchor(), 100000)}
    finally:
        w.close()
    conn = me._conn()
    try:
        record.append_event(conn, cid, "STATUS_CHANGED", "u_la_exec", OWNER, note="salt now set")
        conn.commit()
        ref = record._row(conn, "SELECT contract_ref, pseudo_id FROM tb_contract WHERE id = ?", (cid,))
    finally:
        conn.close()
    assert ref["pseudo_id"].strip() == la.pseudo_id(ref["contract_ref"], SALT)
    assert {o["pseudo_id"] for o in _outbox(world, cid)} == {ref["pseudo_id"]}


def _terms_id(conn) -> str:
    from app.trading_book import record

    return str(record.current_version(conn, STATE["trade"]["id"])["terms_id"])


# ── what the parties read, and verification ─────────────────────────────────

def test_a_party_reads_the_chain_with_its_anchors_and_a_stranger_reads_nothing(world):
    from app.core.market_engine import MarketRefused

    out = la.chain_for(OWNER, False, STATE["trade"]["id"])
    assert out["chain_intact"] and out["pseudo_id"]
    first = out["events"][0]
    assert first["ledger_anchor"]["status"] == "ANCHORED" and first["ledger_anchor"]["sequence_number"]
    assert set(first) == {"seq", "event_type", "at", "prev_hash", "event_hash", "hash_scheme", "ledger_anchor"}
    with pytest.raises(MarketRefused) as exc:
        la.chain_for(X, False, STATE["trade"]["id"])
    assert exc.value.status == 404


def test_a_buyer_proves_its_own_sub_leg_is_inside_the_anchored_root(world):
    from app.trading_book import canonical

    out = la.chain_for(A, False, STATE["frame"])
    m = out["merkle"]
    own = m["own_sub_leg"]
    assert own and canonical.verify_proof(own["leaf"], [tuple(p) for p in own["proof"]], m["terms_hash"])
    assert canonical.verify_proof(m["shared"]["leaf"], [tuple(p) for p in m["shared"]["proof"]], m["terms_hash"])
    assert m["carried_by_event_hash"] in {e["event_hash"] for e in out["events"]}
    assert B not in json.dumps(out) and NAMES[B] not in json.dumps(out)        # the other buyer stays a hash
    b_own = la.chain_for(B, False, STATE["frame"])["merkle"]["own_sub_leg"]
    assert b_own["leaf"] != own["leaf"]


def test_verify_anchor_checks_the_chain_and_every_anchored_event_on_the_ledger(world):
    from app.core import market_engine as me
    from app.trading_book import record

    cid = STATE["frame"]
    conn = me._conn()
    try:
        c = record._row(conn, "SELECT contract_ref, pseudo_id FROM tb_contract WHERE id = ?", (cid,))
        evs = record.events(conn, cid)
    finally:
        conn.close()
    box = _outbox(world, cid)
    fake = STATE["fake"]
    good = la.verify_contract(c["contract_ref"], c["pseudo_id"], evs, box, la.index_messages(fake.messages("")),
                              salt=SALT)
    assert good["ok"] and good["anchored"] == len(evs), good["problems"]

    mine = box[0]["ledger_sequence_number"]                         # the frame's first anchored message
    # a changed ledger message
    tampered = [{**m, "message": m["message"].replace(b'"event_type":"', b'"event_type":"X')}
                if m["sequence_number"] == mine else m for m in fake.log]
    bad = la.verify_contract(c["contract_ref"], c["pseudo_id"], evs, box, la.index_messages(tampered), salt=SALT)
    assert not bad["ok"]
    # a rewritten event breaks the recomputed chain
    broken = [{**e, "note": "rewritten"} if e["seq"] == 1 else e for e in evs]
    assert "CHAIN_BROKEN" in la.verify_contract(c["contract_ref"], c["pseudo_id"], broken, box,
                                                la.index_messages(fake.log), salt=SALT)["problems"]
    # the wrong salt does not reproduce the pseudonymous id
    assert "PSEUDO_ID_MISMATCH" in la.verify_contract(c["contract_ref"], c["pseudo_id"], evs, box,
                                                      la.index_messages(fake.log), salt="other")["problems"]
    # a duplicate (a crash between acceptance and the row update) is reported, not a failure
    original = next(m for m in fake.log if m["sequence_number"] == mine)
    dup = fake.log + [{**original, "sequence_number": len(fake.log) + 1}]
    r = la.verify_contract(c["contract_ref"], c["pseudo_id"], evs, box, la.index_messages(dup), salt=SALT)
    assert r["ok"] and r["events"][0]["duplicates"] == [len(fake.log) + 1]
    # a copy that came FIRST is not the recorded message: reported, never taken for it
    earlier = fake.log + [{**original, "sequence_number": 0}]
    moved = la.verify_contract(c["contract_ref"], c["pseudo_id"], evs, box, la.index_messages(earlier), salt=SALT)
    assert "seq 1: FIRST_MESSAGE_IS_NOT_THE_RECORDED_ONE" in moved["problems"]


def test_the_verify_script_reads_the_record_and_the_ledger(world, capsys):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_anchor.py"
    spec = importlib.util.spec_from_file_location("verify_anchor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--contract", STATE["frame"]], anchor=STATE["fake"]) == 0
    assert "chain intact" in capsys.readouterr().out
    tampered = FakeAnchor()
    tampered.log = [{**m, "message": m["message"].replace(b"schema_version", b"schema_versioN")}
                    for m in STATE["fake"].log]
    assert mod.main(["--contract", STATE["frame"]], anchor=tampered) == 1


def test_the_gex_staff_console_shows_failed_rows_and_the_worker(world):
    from fastapi import HTTPException

    from app.api.v1 import routes_gex_console as console

    class Req:
        def __init__(self, admin):
            self.state = type("S", (), {"user_payload": {"user_id": "u", "is_platform_admin": admin}})()

    with pytest.raises(HTTPException) as exc:
        console.ledger_anchor_health(Req(False))
    assert exc.value.status_code == 403
    out = console.ledger_anchor_health(Req(True))
    assert out["by_status"]["FAILED"]["count"] >= 1 and out["failed"][0]["attempts"] == 8
    assert out["backend"] == "none" and out["worker_running"] is False
    assert not any(k in json.dumps(out) for k in (STATE["trade"]["id"], OWNER, A)), json.dumps(out)[:1500]
