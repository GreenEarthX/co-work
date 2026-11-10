"""
The ledger anchor — Phase 4 of "One contract record" (JML's prompt §8; Phase 0 Q11, Q12).
==========================================================================================
Per contract event, a hash goes to a public ledger, so a lender or a court can check
that GEX did not rewrite a contract's history. What leaves is EXACTLY

    {schema_version, pseudo_id, event_type, event_hash, prev_hash}

— no terms, prices, volumes, names, company or user ids, ever. The ledger is Hedera
Consensus Service messages only: no token of any kind (rule 3). The contract record
stays the source of truth; the anchor only proves it was not rewritten.

THE MECHANISM, NOT THE PROVIDER. The provider (Truzzt or a direct integration) is
JML's decision with Marwen. Anchoring is OFF by default: LEDGER_ANCHOR_BACKEND = none
starts no worker and leaves every outbox row PENDING; `scripts/drain_anchor_outbox.py
--once` with it off marks them NOT_ANCHORED (NullAnchor). `hedera_testnet` is the
only ledger value; mainnet is not a value until JML adds it.

THE OUTBOX (alembic 095). Every event writes its row in the event's own transaction,
by trigger. The worker (role gex_anchor, its own credential) claims rows with
SELECT … FOR UPDATE SKIP LOCKED and a lease, submits, and records the ledger
reference. Retries back off 1 min, 5 min, 30 min, 2 h, then 12 h; after 8 attempts
the row is FAILED and shows on the GEX staff console. Anchoring never blocks a
contract event: the event is committed before the worker ever sees it.

A crash between the ledger's acceptance and the row update can send a message
twice. `scripts/verify_anchor.py` takes the FIRST message carrying an event hash and
reports the others (Q11).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
PAYLOAD_KEYS = ("schema_version", "pseudo_id", "event_type", "event_hash", "prev_hash")
BACKENDS = ("none", "hedera_testnet")
BACKOFF_SECONDS = (60, 300, 1800, 7200, 43200)        # 1 min, 5 min, 30 min, 2 h, then 12 h
MAX_ATTEMPTS = 8
LEASE_SECONDS = 120
BATCH = 20


class AnchorUnavailable(RuntimeError):
    """The ledger could not take the message now: retried with backoff."""


# ── what is anchored ─────────────────────────────────────────────────────────

def pseudo_id(contract_ref: str, salt: Optional[str] = None) -> Optional[str]:
    """HMAC-SHA256(salt, contract_ref): one value per contract for its life (Q12). An
    outsider can follow one contract's events but cannot link two contracts or find a
    company. None without a salt (the contract then waits for --assign-pseudo-ids)."""
    if salt is None:
        from app.core.config import settings
        salt = settings.LEDGER_ANCHOR_SALT
    if not salt or not contract_ref:
        return None
    return hmac.new(salt.encode("utf-8"), contract_ref.encode("utf-8"), hashlib.sha256).hexdigest()


def _hex(v: Optional[str]) -> Optional[str]:
    return v.strip() if isinstance(v, str) else v


def payload(row: dict) -> dict:
    """Exactly the five keys, from an outbox row (or anything carrying them)."""
    if not row.get("pseudo_id"):
        raise ValueError("an event is anchored only with its contract's pseudonymous id")
    return {"schema_version": SCHEMA_VERSION, "pseudo_id": _hex(row["pseudo_id"]),
            "event_type": row["event_type"], "event_hash": _hex(row["event_hash"]),
            "prev_hash": _hex(row.get("prev_hash"))}


def message(row: dict) -> bytes:
    return json.dumps(payload(row), sort_keys=True, separators=(",", ":")).encode("utf-8")


def backoff_seconds(attempts: int) -> int:
    """The wait after the `attempts`-th failure (1-based)."""
    return BACKOFF_SECONDS[min(max(attempts, 1), len(BACKOFF_SECONDS)) - 1]


# ── the adapters ─────────────────────────────────────────────────────────────

@dataclass
class AnchorReceipt:
    network: str
    topic_id: str
    sequence_number: int
    consensus_timestamp: Optional[str] = None
    transaction_id: Optional[str] = None


class LedgerAnchor:
    """The interface. `anchors` False means the adapter records nothing anywhere."""
    name = "abstract"
    network = "none"
    anchors = True

    def submit(self, data: bytes) -> AnchorReceipt:
        raise NotImplementedError

    def lookup(self, topic_id: str, sequence_number: int) -> Optional[dict]:
        """The ledger's copy of one message: {sequence_number, consensus_timestamp, message (bytes)}."""
        return None

    def messages(self, topic_id: str) -> Iterable[dict]:
        """Every message on the topic, oldest first, in lookup()'s shape."""
        return iter(())


class NullAnchor(LedgerAnchor):
    """The default. Sends nothing; the drain marks rows NOT_ANCHORED."""
    name = "none"
    anchors = False

    def submit(self, data: bytes) -> AnchorReceipt:     # pragma: no cover - never called
        raise AnchorUnavailable("anchoring is off")


class HederaHcsAnchor(LedgerAnchor):
    """Hedera Consensus Service: one ConsensusSubmitMessage per event, one topic per
    environment. Operator id and key come from files/.env (Settings), never from
    compose or code. Reads go to the public mirror node over HTTPS.

    The submit path uses the Hiero Python SDK (`hiero_sdk_python`), imported only
    when a message is sent: it is NOT installed in this environment and has never
    been exercised here — the manual testnet run is its test (handoff)."""
    name = "hedera_testnet"
    NETWORKS = ("testnet",)

    def __init__(self, *, operator_id: str, operator_key: str, topic_id: str, mirror_url: str,
                 network: str = "testnet", http_get: Optional[Callable[[str], dict]] = None):
        if network not in self.NETWORKS:
            raise ValueError(f"Hedera network {network!r} is not allowed; only {self.NETWORKS} (mainnet needs JML)")
        missing = [k for k, v in (("HEDERA_OPERATOR_ID", operator_id), ("HEDERA_OPERATOR_KEY", operator_key),
                                  ("HEDERA_TOPIC_ID", topic_id), ("HEDERA_MIRROR_URL", mirror_url)) if not v]
        if missing:
            raise ValueError(f"missing {', '.join(missing)}")
        self.network = f"hedera:{network}"
        self._net, self._operator_id, self._key = network, operator_id, operator_key
        self.topic_id, self.mirror_url = topic_id, mirror_url.rstrip("/")
        self._get = http_get or _http_get_json

    def submit(self, data: bytes) -> AnchorReceipt:
        try:
            from hiero_sdk_python import (AccountId, Client, Network, PrivateKey, TopicId,  # type: ignore
                                          TopicMessageSubmitTransaction)
        except ImportError as exc:
            raise AnchorUnavailable("the Hiero Python SDK (hiero_sdk_python) is not installed") from exc
        failure = None
        try:
            client = Client(Network(self._net))
            key = PrivateKey.from_string(self._key)
            client.set_operator(AccountId.from_string(self._operator_id), key)
            tx = (TopicMessageSubmitTransaction(topic_id=TopicId.from_string(self.topic_id),
                                                message=data.decode("utf-8"))
                  .freeze_with(client).sign(key))
            receipt = tx.execute(client)
        except Exception as exc:  # noqa: BLE001 - the key must never reach a log or the outbox
            failure = _scrub(f"{type(exc).__name__}: {exc}", self._key)
        if failure is not None:
            # Raised OUTSIDE the except block, so the new error holds no reference to the
            # original (`from None` only hides it from tracebacks; __context__ keeps it).
            raise AnchorUnavailable(failure)
        seq = getattr(receipt, "topic_sequence_number", None)
        if seq is None:
            raise AnchorUnavailable(f"the ledger answered without a sequence number ({getattr(receipt, 'status', '?')})")
        tx_id = getattr(receipt, "transaction_id", None) or getattr(tx, "transaction_id", None)
        return AnchorReceipt(network=self.network, topic_id=self.topic_id, sequence_number=int(seq),
                             transaction_id=str(tx_id) if tx_id is not None else None)

    def _shape(self, m: dict) -> dict:
        return {"sequence_number": int(m["sequence_number"]), "consensus_timestamp": m["consensus_timestamp"],
                "message": base64.b64decode(m["message"])}

    def lookup(self, topic_id: str, sequence_number: int) -> Optional[dict]:
        m = self._get(f"{self.mirror_url}/api/v1/topics/{topic_id}/messages/{int(sequence_number)}")
        return self._shape(m) if m and "message" in m else None

    def messages(self, topic_id: str) -> Iterable[dict]:
        url = f"{self.mirror_url}/api/v1/topics/{topic_id}/messages?limit=100&order=asc"
        while url:
            page = self._get(url) or {}
            for m in page.get("messages", []):
                yield self._shape(m)
            nxt = (page.get("links") or {}).get("next")
            url = f"{self.mirror_url}{nxt}" if nxt else None


def _http_get_json(url: str) -> dict:
    import httpx

    r = httpx.get(url, timeout=15)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def _scrub(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[redacted]")
    return text[:500]


def config_problems(s=None) -> list[str]:
    """What the configured backend still lacks. Empty when it may start."""
    if s is None:
        from app.core.config import settings as s
    if s.LEDGER_ANCHOR_BACKEND == "none":
        return []
    out = [f"{k} is not set" for k in ("LEDGER_ANCHOR_SALT", "LEDGER_ANCHOR_DATABASE_URL", "HEDERA_OPERATOR_ID",
                                        "HEDERA_OPERATOR_KEY", "HEDERA_TOPIC_ID", "HEDERA_MIRROR_URL")
           if not getattr(s, k)]
    if s.LEDGER_ANCHOR_DATABASE_URL and "gex_anchor" not in s.LEDGER_ANCHOR_DATABASE_URL.split("@")[0]:
        out.append("LEDGER_ANCHOR_DATABASE_URL must use the gex_anchor role")
    return out


def anchor_from_settings(s=None) -> LedgerAnchor:
    if s is None:
        from app.core.config import settings as s
    if s.LEDGER_ANCHOR_BACKEND == "none":
        return NullAnchor()
    if s.LEDGER_ANCHOR_BACKEND == "hedera_testnet":
        return HederaHcsAnchor(operator_id=s.HEDERA_OPERATOR_ID, operator_key=s.HEDERA_OPERATOR_KEY,
                               topic_id=s.HEDERA_TOPIC_ID, mirror_url=s.HEDERA_MIRROR_URL, network="testnet")
    raise ValueError(f"unknown LEDGER_ANCHOR_BACKEND {s.LEDGER_ANCHOR_BACKEND!r}")


# ── the drain ────────────────────────────────────────────────────────────────

def connect_worker(dsn: Optional[str] = None):
    """A connection as gex_anchor — the worker's own role, never the runtime's."""
    import psycopg2
    import psycopg2.extras

    if dsn is None:
        from app.core.config import settings
        dsn = settings.LEDGER_ANCHOR_DATABASE_URL
    if not dsn:
        raise RuntimeError("LEDGER_ANCHOR_DATABASE_URL is not set")
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


CLAIM = """UPDATE ledger_anchor_outbox SET next_attempt_at = now() + make_interval(secs => %s)
           WHERE id IN (SELECT id FROM ledger_anchor_outbox
                        WHERE status = 'PENDING' AND next_attempt_at <= now() AND (pseudo_id IS NOT NULL OR %s)
                        ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED)
           RETURNING id, pseudo_id, event_type, event_hash, prev_hash, attempts"""


def claim(conn, anchor: LedgerAnchor, batch: int = BATCH) -> list[dict]:
    """Take up to `batch` due rows for LEASE_SECONDS. A row another worker holds is
    skipped; a row whose worker died becomes due again when its lease runs out."""
    cur = conn.cursor()
    cur.execute(CLAIM, (LEASE_SECONDS, not anchor.anchors, batch))
    rows = sorted((dict(r) for r in cur.fetchall()), key=lambda r: r["id"])
    conn.commit()
    return rows


def drain_once(connect: Callable[[], Any], anchor: LedgerAnchor, batch: int = BATCH) -> dict:
    counts = {"claimed": 0, "anchored": 0, "not_anchored": 0, "retrying": 0, "failed": 0, "timestamps": 0}
    conn = connect()
    try:
        rows = claim(conn, anchor, batch)
        counts["claimed"] = len(rows)
        cur = conn.cursor()
        for row in rows:
            if not anchor.anchors:
                cur.execute("UPDATE ledger_anchor_outbox SET status = 'NOT_ANCHORED', last_error = NULL "
                            "WHERE id = %s AND status = 'PENDING'", (row["id"],))
                conn.commit()
                counts["not_anchored"] += 1
                continue
            try:
                r = anchor.submit(message(row))
            except Exception as exc:  # noqa: BLE001 - any failure is a retry, never a lost event
                attempts = row["attempts"] + 1
                failed = attempts >= MAX_ATTEMPTS
                cur.execute("UPDATE ledger_anchor_outbox SET attempts = %s, status = %s, last_error = %s, "
                            "next_attempt_at = now() + make_interval(secs => %s) WHERE id = %s AND status = 'PENDING'",
                            (attempts, "FAILED" if failed else "PENDING", f"{type(exc).__name__}: {exc}"[:500],
                             backoff_seconds(attempts), row["id"]))
                conn.commit()
                counts["failed" if failed else "retrying"] += 1
                continue
            cur.execute("UPDATE ledger_anchor_outbox SET status = 'ANCHORED', attempts = attempts + 1, "
                        "last_error = NULL, ledger_network = %s, ledger_topic_id = %s, ledger_sequence_number = %s, "
                        "ledger_consensus_timestamp = %s, ledger_transaction_id = %s, anchored_at = now() "
                        "WHERE id = %s AND status = 'PENDING'",
                        (r.network, r.topic_id, r.sequence_number, r.consensus_timestamp, r.transaction_id, row["id"]))
            conn.commit()
            counts["anchored"] += 1
        if anchor.anchors:
            counts["timestamps"] = fill_consensus_timestamps(conn, anchor, batch)
    finally:
        conn.close()
    return counts


def fill_consensus_timestamps(conn, anchor: LedgerAnchor, batch: int = BATCH) -> int:
    """The receipt carries the sequence number; the consensus timestamp is read back
    from the mirror node once it has the message."""
    cur = conn.cursor()
    cur.execute("SELECT id, ledger_topic_id, ledger_sequence_number FROM ledger_anchor_outbox "
                "WHERE status = 'ANCHORED' AND ledger_consensus_timestamp IS NULL AND ledger_network = %s "
                "ORDER BY id LIMIT %s", (anchor.network, batch))
    n = 0
    for row in [dict(r) for r in cur.fetchall()]:
        try:
            m = anchor.lookup(row["ledger_topic_id"], row["ledger_sequence_number"])
        except Exception:  # noqa: BLE001 - the mirror lags or is down: next pass
            m = None
        if m:
            cur.execute("UPDATE ledger_anchor_outbox SET ledger_consensus_timestamp = %s WHERE id = %s "
                        "AND ledger_consensus_timestamp IS NULL", (m["consensus_timestamp"], row["id"]))
            n += 1
    conn.commit()
    return n


# ── the worker loop (Q11: in-process, only when the backend is not none) ─────

STATE: dict = {"backend": "none", "running": False, "refused": [], "last_run_at": None, "last_result": None,
               "last_error": None}
_TASK: Optional[asyncio.Task] = None


async def _loop(interval: int) -> None:
    anchor = anchor_from_settings()
    while True:
        try:
            STATE["last_result"] = await asyncio.to_thread(drain_once, connect_worker, anchor)
            STATE["last_error"] = None
        except Exception as exc:  # noqa: BLE001 - the loop outlives a bad pass
            STATE["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
            logger.warning("ledger anchor drain failed: %s", STATE["last_error"])
        STATE["last_run_at"] = datetime.now(timezone.utc).isoformat()
        await asyncio.sleep(interval)


def start_worker() -> dict:
    """Called at backend startup. Starts nothing when the backend is none, and
    nothing (loudly) when it is misconfigured: anchoring never stops the platform."""
    global _TASK
    from app.core.config import settings

    STATE.update(backend=settings.LEDGER_ANCHOR_BACKEND, running=False, refused=[])
    if settings.LEDGER_ANCHOR_BACKEND == "none":
        return STATE
    problems = config_problems(settings)
    if problems:
        STATE["refused"] = problems
        logger.error("ledger anchor worker NOT started: %s", "; ".join(problems))
        return STATE
    _TASK = asyncio.get_event_loop().create_task(_loop(settings.LEDGER_ANCHOR_INTERVAL_SECONDS))
    STATE["running"] = True
    logger.info("ledger anchor worker started (%s, every %ss)", settings.LEDGER_ANCHOR_BACKEND,
                settings.LEDGER_ANCHOR_INTERVAL_SECONDS)
    return STATE


async def stop_worker() -> None:
    global _TASK
    if _TASK is not None:
        _TASK.cancel()
        try:
            await _TASK
        except asyncio.CancelledError:
            pass
        _TASK = None
    STATE["running"] = False


# ── verification ─────────────────────────────────────────────────────────────

def index_messages(msgs: Iterable[dict]) -> dict[str, list[dict]]:
    """event_hash -> every ledger message carrying it, by sequence number. A message
    that is not one of ours (not JSON, other keys) is ignored."""
    out: dict[str, list[dict]] = {}
    for m in msgs:
        try:
            body = json.loads(m["message"])
        except (ValueError, TypeError):
            continue
        if isinstance(body, dict) and isinstance(body.get("event_hash"), str):
            out.setdefault(body["event_hash"], []).append({**m, "body": body})
    for v in out.values():
        v.sort(key=lambda m: m["sequence_number"])
    return out


def verify_contract(contract_ref: str, pseudo: Optional[str], events: list[dict], outbox: list[dict],
                    ledger: dict[str, list[dict]], salt: Optional[str] = None) -> dict:
    """Recompute the chain, then check every anchored event against the ledger: the
    FIRST message carrying its hash must be the one recorded, with exactly the
    payload expected; any later one is reported as a duplicate (Q11)."""
    from app.trading_book import record

    problems: list[str] = []
    intact = record.chain_intact_events(contract_ref, events)
    if not intact:
        problems.append("CHAIN_BROKEN")
    if salt is not None and pseudo and pseudo_id(contract_ref, salt) != _hex(pseudo):
        problems.append("PSEUDO_ID_MISMATCH")
    by_hash = {_hex(o["event_hash"]): o for o in outbox}
    rows = []
    for e in events:
        h = _hex(e["event_hash"])
        o = by_hash.get(h)
        item = {"seq": e["seq"], "event_hash": h, "status": o["status"] if o else None, "problems": [],
                "duplicates": []}
        if o is None:
            item["problems"].append("NO_OUTBOX_ROW")
        elif (o["event_type"], _hex(o.get("prev_hash"))) != (e["event_type"], _hex(e.get("prev_hash"))):
            item["problems"].append("OUTBOX_DIFFERS_FROM_RECORD")
        elif o["status"] == "ANCHORED":
            found = ledger.get(h, [])
            if not found:
                item["problems"].append("NOT_ON_LEDGER")
            else:
                first, rest = found[0], found[1:]
                if int(first["sequence_number"]) != int(o["ledger_sequence_number"]):
                    item["problems"].append("FIRST_MESSAGE_IS_NOT_THE_RECORDED_ONE")
                if first["body"] != payload({**o, "pseudo_id": pseudo or o.get("pseudo_id")}):
                    item["problems"].append("LEDGER_PAYLOAD_DIFFERS")
                if o.get("ledger_consensus_timestamp") and \
                        first.get("consensus_timestamp") != o["ledger_consensus_timestamp"]:
                    item["problems"].append("CONSENSUS_TIMESTAMP_DIFFERS")
                item["duplicates"] = [int(m["sequence_number"]) for m in rest]
        problems += [f"seq {e['seq']}: {p}" for p in item["problems"]]
        rows.append(item)
    return {"contract_ref": contract_ref, "pseudo_id": _hex(pseudo), "chain_intact": intact, "events": rows,
            "anchored": sum(1 for r in rows if r["status"] == "ANCHORED"), "problems": problems,
            "ok": not problems}


# ── the parties' readout ─────────────────────────────────────────────────────

def chain_for(company_id: Optional[str], is_admin: bool, contract_id: str) -> dict:
    """The contract's chain with its ledger anchors, for whoever may read the contract
    (the record's own RLS decides, on the caller's connection). Hashes, types, times
    and ledger references only — the terms are in the record readout. A buyer also
    gets the Merkle proof of its own sub-leg (and of the shared terms) inside the
    current version's root (Q12), so it can show its part is inside what was
    anchored without seeing the other buyers'."""
    from app.core.db_backend import PLATFORM_ADMIN, market_connection, market_is_postgres
    from app.core.market_engine import MarketRefused
    from app.trading_book import canonical, record

    if not market_is_postgres():
        raise MarketRefused(503, "POSTGRES_REQUIRED", "The contract record lives in PostgreSQL only.")
    me = PLATFORM_ADMIN if is_admin else company_id
    if not me:
        raise MarketRefused(403, "NO_COMPANY", "Your account belongs to no company.")
    mine = market_connection(company_id=me)
    try:
        seen = record._row(mine, "SELECT id FROM tb_contract WHERE id = ? AND contract_type = 'terms'",
                           (contract_id,))
    finally:
        mine.close()
    if seen is None:
        raise MarketRefused(404, "CONTRACT_NOT_FOUND", "No contract record you can read with that id.")
    # Authorised by the caller's own RLS above; what follows is hashes only.
    conn = market_connection(company_id=PLATFORM_ADMIN)
    try:
        c = record._row(conn, "SELECT contract_ref, pseudo_id FROM tb_contract WHERE id = ?", (contract_id,))
        evs = record.events(conn, contract_id)
        anchors = {r["event_id"]: r for r in record._rows(conn, "SELECT * FROM ledger_anchor_outbox "
                                                                 "WHERE contract_id = ?", (contract_id,))}
        out_events = []
        for e in evs:
            a = anchors.get(e["id"]) or {}
            out_events.append({
                "seq": e["seq"], "event_type": e["event_type"], "at": _s(e["at"]), "prev_hash": _hex(e["prev_hash"]),
                "event_hash": _hex(e["event_hash"]), "hash_scheme": e["hash_scheme"],
                "ledger_anchor": {"status": a.get("status"), "network": a.get("ledger_network"),
                                  "topic_id": a.get("ledger_topic_id"),
                                  "sequence_number": a.get("ledger_sequence_number"),
                                  "consensus_timestamp": a.get("ledger_consensus_timestamp"),
                                  "transaction_id": a.get("ledger_transaction_id"),
                                  "anchored_at": _s(a.get("anchored_at"))}})
        v = record.current_version(conn, contract_id)
        merkle = None
        if v is not None:
            t = record._row(conn, "SELECT shared_hash FROM tb_terms WHERE id = ?", (v["terms_id"],))
            subs = record._rows(conn, "SELECT s.seq, s.sub_leg_hash, cp.company_id FROM tb_sub_leg s "
                                      "LEFT JOIN tb_counterparty cp ON cp.id = s.buyer_id "
                                      "WHERE s.terms_id = ? ORDER BY s.seq", (v["terms_id"],))
            if t and t["shared_hash"] and all(s["sub_leg_hash"] for s in subs):
                leaves = [_hex(t["shared_hash"])] + [_hex(s["sub_leg_hash"]) for s in subs]
                own = next((i for i, s in enumerate(subs, start=1) if company_id and s["company_id"] == company_id),
                           None)
                carried = next((e for e in reversed(evs) if _hex(e["terms_hash"]) == _hex(v["terms_hash"])), None)
                merkle = {"version": v["version"], "terms_hash": _hex(v["terms_hash"]),
                          "carried_by_event_hash": _hex(carried["event_hash"]) if carried else None,
                          "shared": {"leaf": leaves[0], "proof": canonical.merkle_proof(leaves, 0)},
                          "own_sub_leg": ({"seq": subs[own - 1]["seq"], "leaf": leaves[own],
                                           "proof": canonical.merkle_proof(leaves, own)} if own else None)}
        from app.core.config import settings
        return {"contract_id": contract_id, "pseudo_id": _hex(c["pseudo_id"]),
                "chain_intact": record.chain_intact(conn, contract_id),
                "anchoring": settings.LEDGER_ANCHOR_BACKEND, "events": out_events, "merkle": merkle}
    finally:
        conn.close()


def _s(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v
