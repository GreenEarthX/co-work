"""
The contract record — the ONE writer of contracts (alembic 065 + 083; Phase 1).

docs/CONTRACT_RECORD_PHASE0.md. A contract is stored once: tb_contract, its
versions, each version's frozen terms (shared terms, one sub-leg per buyer,
legs, flows, clauses) and one append-only hash-chained event log
(tb_contract_event). Every caller — the market engine when both sides of a
match accept, the order book when an order is accepted — creates contracts
here, on ITS OWN connection, so the contract is part of the caller's
transaction: either the agreement and its contract both commit or neither does.

Callers authorise the Party before calling; these functions do not decide who
may act. They run on the market's PLATFORM_ADMIN connection (`?` placeholders,
core/db_backend.PostgresConnection).

Event hash, scheme '2' (Phase 0 §4): sha256 of the canonical JSON of
  {schema, contract_ref, seq, event_type, version, sub_leg, terms_hash,
   actor, company, note, at, prev}
`at` is inside the hash (078's chain left it out). Scheme '078' is the Phase 2
fold's, for the migrated contract tokens.

The 065 token columns (decided in Phase 0 §4, rule 3: no transferable token):
tb_contract.token_ref is the contract's genesis event hash, and each version's
token_event_ref the hash of the event that carried it. 065's triggers keep both
fixed, so the record keeps one identity for its life.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from app.trading_book import canonical
from app.trading_book.conventions import PAYER_SIDE, LegRole, Side
from app.trading_book.terms import TermsIn

SCHEME = "2"


class RecordRefused(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _row(conn, sql: str, params: Iterable = ()) -> Optional[dict]:
    r = conn.execute(sql, tuple(params)).fetchone()
    return dict(r) if r else None


def _rows(conn, sql: str, params: Iterable = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


# ── reference data ──────────────────────────────────────────────────────────

def counterparty_for(conn, company_id: str) -> str:
    """The tb_counterparty of a platform company, registered from its tenant row
    the first time it trades. A company whose tenant record names no two-letter
    jurisdiction is refused rather than given an invented country."""
    found = _row(conn, "SELECT id FROM tb_counterparty WHERE company_id = ?", (company_id,))
    if found:
        return str(found["id"])
    t = _row(conn, "SELECT company_name, jurisdiction FROM tenants WHERE company_id = ?", (company_id,))
    if not t or not t.get("jurisdiction") or len(t["jurisdiction"]) != 2:
        raise RecordRefused(409, "COUNTERPARTY_UNRESOLVED",
                            f"Company {company_id} has no registered tenant with a two-letter jurisdiction.")
    conn.execute("INSERT INTO tb_counterparty (id, legal_name, country_code, is_active, created_at, updated_at, "
                 "company_id) VALUES (?, ?, ?, true, now(), now(), ?) "
                 "ON CONFLICT (company_id) WHERE company_id IS NOT NULL DO NOTHING",
                 (str(uuid.uuid4()), t["company_name"], t["jurisdiction"].upper(), company_id))
    return str(_row(conn, "SELECT id FROM tb_counterparty WHERE company_id = ?", (company_id,))["id"])


def company_of_counterparty(conn, counterparty_id) -> Optional[str]:
    r = _row(conn, "SELECT company_id FROM tb_counterparty WHERE id = ?", (str(counterparty_id),))
    return r["company_id"] if r else None


def commodity_for_molecule(conn, molecule: Optional[str]) -> Optional[str]:
    """tb_commodity.code for the market's molecule code (065 mapped them)."""
    r = _row(conn, "SELECT code FROM tb_commodity WHERE market_molecule = ? OR code = ?", (molecule, molecule))
    return r["code"] if r else None


# ── terms ───────────────────────────────────────────────────────────────────

def _buyer_of(legs) -> Optional[str]:
    """The buying party of a sub-leg, read through the side convention (§2)."""
    for leg in legs:
        payer_side = PAYER_SIDE[LegRole(leg.leg_role)]
        party = leg.payer if payer_side == Side.BUY else leg.receiver
        if party:
            return party
    return None


def write_terms(conn, terms: TermsIn, owner_company_id: str, *, profile: Optional[str] = None,
                freeze: bool = True, frozen_at=None) -> dict:
    """Insert terms with their sub-legs, legs, flows and clauses, then freeze them
    with their hashes. Returns {terms_id, terms_hash, shared_hash, sub_legs: {seq: {id, hash}}}.
    `frozen_at` lets the Phase 2 fold keep the time a 078 version was recorded."""
    h = canonical.hashes(terms)
    profile = profile or terms.profile
    commodity_id = None
    if terms.commodity is not None:
        commodity = _row(conn, "SELECT id FROM tb_commodity WHERE code = ?", (terms.commodity,))
        if commodity is None:
            raise RecordRefused(422, "UNKNOWN_COMMODITY", f"No commodity {terms.commodity!r} in tb_commodity.")
        commodity_id = str(commodity["id"])
    terms_id = str(uuid.uuid4())
    conn.execute("INSERT INTO tb_terms (id, owner_company_id, settlement, commodity_id, quality_spec, currency, "
                 "profile, card_projection) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (terms_id, owner_company_id, terms.settlement.value if terms.settlement else None, commodity_id,
                  json.dumps(terms.quality_spec, sort_keys=True), terms.currency.upper() if terms.currency else None,
                  profile, json.dumps(terms.card_projection, sort_keys=True, default=str)
                  if terms.card_projection is not None else None))
    ranks = {s.seq: s.rank for s in terms.sub_legs}
    cards = {s.seq: s for s in terms.sub_legs if s.card_projection is not None}
    subs: dict[int, dict] = {}
    for n in terms.sub_leg_numbers():
        sid = str(uuid.uuid4())
        legs = [leg for leg in terms.legs if leg.sub_leg == n]
        card = cards.get(n)
        conn.execute("INSERT INTO tb_sub_leg (id, terms_id, seq, buyer_id, rank, sub_leg_hash, card_projection) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (sid, terms_id, n, card.buyer if card else _buyer_of(legs), ranks.get(n), h["sub_legs"][n],
                      json.dumps(card.card_projection, sort_keys=True, default=str) if card else None))
        subs[n] = {"id": sid, "hash": h["sub_legs"][n]}
    flow_ids: dict[str, str] = {}
    sources: list[tuple[str, str]] = []
    for leg in sorted(terms.legs, key=lambda l: l.seq):
        leg_id = str(uuid.uuid4())
        conn.execute("INSERT INTO tb_leg (id, terms_id, leg_role, payer_id, receiver_id, seq, sub_leg_id) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (leg_id, terms_id, leg.leg_role.value, leg.payer, leg.receiver, leg.seq, subs[leg.sub_leg]["id"]))
        for f in sorted(leg.flows, key=lambda f: f.seq):
            fid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO tb_flow (id, leg_id, seq, flow_type, period_start, period_end, settle_date, quantity, "
                "unit, is_notional, quantity_basis, tolerance_min_pct, tolerance_max_pct, asset_id, unit_price, "
                "index_id, index_multiplier, spread, cap, floor, fixing_method, fixing_start, fixing_end) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (fid, leg_id, f.seq, f.flow_type.value, f.period_start, f.period_end, f.settle_date, f.quantity,
                 f.unit, f.is_notional, f.quantity_basis, f.tolerance_min_pct, f.tolerance_max_pct, f.asset_id,
                 f.unit_price, f.index, f.index_multiplier, f.spread, f.cap, f.floor, f.fixing_method,
                 f.fixing_start, f.fixing_end))
            flow_ids[f"{leg.seq}.{f.seq}"] = fid
            if f.quantity_source_flow:
                sources.append((fid, f.quantity_source_flow))
    for fid, ref in sources:          # validation (V10) guarantees the reference is in these terms
        conn.execute("UPDATE tb_flow SET quantity_source_flow_id = ? WHERE id = ?", (flow_ids[ref], fid))
    for c in terms.clauses:
        conn.execute("INSERT INTO tb_clause (terms_id, sub_leg_id, clause_type, seq, attrs) VALUES (?, ?, ?, ?, ?)",
                     (terms_id, subs[c.sub_leg]["id"] if c.sub_leg is not None else None, c.clause_type, c.seq,
                      json.dumps(c.attrs, sort_keys=True)))
    if freeze:
        conn.execute("UPDATE tb_terms SET frozen_at = coalesce(?, now()), terms_hash = ?, shared_hash = ? WHERE id = ?",
                     (frozen_at, h["terms_hash"], h["shared_hash"], terms_id))
    return {"terms_id": terms_id, "terms_hash": h["terms_hash"], "shared_hash": h["shared_hash"], "sub_legs": subs}


def load_terms(conn, terms_id: str) -> TermsIn:
    """Read stored terms back into the payload model — for cloning an order's
    terms into a contract, for terms.json, and to re-check a stored hash."""
    t = _row(conn, "SELECT t.*, co.code FROM tb_terms t LEFT JOIN tb_commodity co ON co.id = t.commodity_id "
                   "WHERE t.id = ?", (terms_id,))
    if t is None:
        raise RecordRefused(404, "TERMS_NOT_FOUND", "No terms with that id.")
    subs = {str(s["id"]): s for s in _rows(conn, "SELECT * FROM tb_sub_leg WHERE terms_id = ?", (terms_id,))}
    legs = _rows(conn, "SELECT * FROM tb_leg WHERE terms_id = ? ORDER BY seq", (terms_id,))
    flows = _rows(conn, "SELECT f.*, l.seq AS leg_seq FROM tb_flow f JOIN tb_leg l ON l.id = f.leg_id "
                        "WHERE l.terms_id = ? ORDER BY l.seq, f.seq", (terms_id,))
    ref = {str(f["id"]): f"{f['leg_seq']}.{f['seq']}" for f in flows}

    def flow(f: dict) -> dict:
        out = {k: f[k] for k in ("seq", "period_start", "period_end", "settle_date", "quantity", "unit",
                                 "is_notional", "tolerance_min_pct", "tolerance_max_pct", "unit_price",
                                 "index_multiplier", "spread", "cap", "floor", "fixing_start", "fixing_end")}
        out.update(flow_type=str(f["flow_type"]), quantity_basis=f["quantity_basis"] and str(f["quantity_basis"]),
                   fixing_method=f["fixing_method"] and str(f["fixing_method"]),
                   quantity_source_flow=ref.get(str(f["quantity_source_flow_id"])) if f["quantity_source_flow_id"] else None,
                   asset_id=str(f["asset_id"]) if f["asset_id"] else None,
                   index=str(f["index_id"]) if f["index_id"] else None)
        return out

    payload = {
        "profile": t["profile"], "card_projection": t["card_projection"],
        "settlement": str(t["settlement"]) if t["settlement"] else None, "commodity": t["code"],
        "quality_spec": t["quality_spec"] or {}, "currency": t["currency"],
        "legs": [{"seq": l["seq"], "sub_leg": subs[str(l["sub_leg_id"])]["seq"] if l["sub_leg_id"] else 1,
                  "leg_role": str(l["leg_role"]),
                  "payer": str(l["payer_id"]) if l["payer_id"] else None,
                  "receiver": str(l["receiver_id"]) if l["receiver_id"] else None,
                  "flows": [flow(f) for f in flows if f["leg_seq"] == l["seq"]]} for l in legs],
        "sub_legs": [{"seq": s["seq"], "rank": s["rank"],
                      **({"buyer": str(s["buyer_id"]) if s["buyer_id"] else None,
                          "card_projection": s["card_projection"]}
                         if s.get("card_projection") is not None else {})}
                     for s in subs.values() if s["rank"] is not None or s.get("card_projection") is not None],
        "clauses": [{"seq": c["seq"], "clause_type": c["clause_type"], "sub_leg": c["sub_leg"],
                     "attrs": c["attrs"] or {}} for c in clauses(conn, terms_id)],
    }
    return TermsIn.model_validate(payload)


def freeze(conn, terms_id: str) -> dict:
    """Freeze stored terms with the hashes of what is stored."""
    h = canonical.hashes(load_terms(conn, terms_id))
    for n, digest in h["sub_legs"].items():
        conn.execute("UPDATE tb_sub_leg SET sub_leg_hash = ? WHERE terms_id = ? AND seq = ?", (digest, terms_id, n))
    conn.execute("UPDATE tb_terms SET frozen_at = now(), terms_hash = ?, shared_hash = ? WHERE id = ? "
                 "AND frozen_at IS NULL", (h["terms_hash"], h["shared_hash"], terms_id))
    return h


def stored_hashes_hold(conn, terms_id: str) -> bool:
    """Recompute the hashes of stored, frozen terms: true when nothing under them changed."""
    t = _row(conn, "SELECT terms_hash, shared_hash FROM tb_terms WHERE id = ?", (terms_id,))
    h = canonical.hashes(load_terms(conn, terms_id))
    subs = {r["seq"]: r["sub_leg_hash"] for r in _rows(conn, "SELECT seq, sub_leg_hash FROM tb_sub_leg "
                                                              "WHERE terms_id = ?", (terms_id,))}
    return (t["terms_hash"] == h["terms_hash"] and t["shared_hash"] == h["shared_hash"]
            and subs == h["sub_legs"])


# ── the event chain ─────────────────────────────────────────────────────────

def _iso(at) -> str:
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    return at.astimezone(timezone.utc).isoformat(timespec="microseconds")


def event_hash(*, contract_ref: str, seq: int, event_type: str, version: Optional[int], sub_leg: Optional[int],
               terms_hash: Optional[str], actor: str, company: Optional[str], note: Optional[str], at,
               prev: Optional[str]) -> str:
    body = {"schema": 2, "contract_ref": contract_ref, "seq": seq, "event_type": event_type, "version": version,
            "sub_leg": sub_leg, "terms_hash": terms_hash, "actor": actor, "company": company, "note": note,
            "at": _iso(at), "prev": prev}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def append_event(conn, contract_id: str, event_type: str, actor: str, company_id: Optional[str], *,
                 version_id: Optional[str] = None, sub_leg_id: Optional[str] = None,
                 terms_hash: Optional[str] = None, note: Optional[str] = None) -> dict:
    """Append one event, chained to the previous one. The contract row is locked
    first, so two writers can never take the same seq (078's race)."""
    c = _row(conn, "SELECT contract_ref FROM tb_contract WHERE id = ? FOR UPDATE", (contract_id,))
    if c is None:
        raise RecordRefused(404, "CONTRACT_NOT_FOUND", "No contract with that id.")
    last = _row(conn, "SELECT seq, event_hash FROM tb_contract_event WHERE contract_id = ? ORDER BY seq DESC LIMIT 1",
                (contract_id,))
    seq = (last["seq"] + 1) if last else 1
    prev = last["event_hash"] if last else None
    version = _row(conn, "SELECT version FROM tb_contract_version WHERE id = ?", (version_id,)) if version_id else None
    sub = _row(conn, "SELECT seq FROM tb_sub_leg WHERE id = ?", (sub_leg_id,)) if sub_leg_id else None
    at = datetime.now(timezone.utc)
    digest = event_hash(contract_ref=c["contract_ref"], seq=seq, event_type=event_type,
                        version=version["version"] if version else None, sub_leg=sub["seq"] if sub else None,
                        terms_hash=terms_hash, actor=actor, company=company_id, note=note, at=at, prev=prev)
    conn.execute("INSERT INTO tb_contract_event (contract_id, seq, event_type, version_id, sub_leg_id, terms_hash, "
                 "actor, company_id, note, at, prev_hash, event_hash, hash_scheme) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (contract_id, seq, event_type, version_id, sub_leg_id, terms_hash, actor, company_id, note, at,
                  prev, digest, SCHEME))
    # The genesis event is the contract's identity for life (065's token_ref; fixed by trigger).
    conn.execute("UPDATE tb_contract SET token_ref = ? WHERE id = ? AND token_ref IS NULL", (digest, contract_id))
    return {"seq": seq, "event_hash": digest}


def events(conn, contract_id: str) -> list[dict]:
    return _rows(conn, "SELECT e.*, v.version, s.seq AS sub_leg_seq FROM tb_contract_event e "
                       "LEFT JOIN tb_contract_version v ON v.id = e.version_id "
                       "LEFT JOIN tb_sub_leg s ON s.id = e.sub_leg_id WHERE e.contract_id = ? ORDER BY e.seq",
                 (contract_id,))


def legacy_event_hash(e: dict, prev: Optional[str]) -> str:
    """Scheme '078' — alembic 078's formula, kept so the contract tokens folded in
    Phase 2 stay verifiable with the hashes they were written with. `contract`
    is the 078 contract id (legacy_contract_id); `at` is outside this hash, which
    is why new events use scheme 2."""
    body = json.dumps({"contract": e["legacy_contract_id"], "seq": e["seq"], "type": e["event_type"],
                       "terms_sha256": e["terms_hash"], "actor": e["actor"], "company": e["company_id"],
                       "note": e["note"], "prev": prev}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def chain_intact_events(contract_ref: str, evs: list[dict]) -> bool:
    """Recompute every hash, each by its own scheme: a rewritten, removed or
    reordered event, or (scheme 2) a changed timestamp, breaks the chain."""
    prev = None
    for i, e in enumerate(evs, start=1):
        if e["seq"] != i or e["prev_hash"] != prev:
            return False
        if e["hash_scheme"] == "078":
            digest = legacy_event_hash(e, prev)
        elif e["hash_scheme"] == SCHEME:
            digest = event_hash(contract_ref=contract_ref, seq=e["seq"], event_type=e["event_type"],
                                version=e["version"], sub_leg=e["sub_leg_seq"], terms_hash=e["terms_hash"],
                                actor=e["actor"], company=e["company_id"], note=e["note"], at=e["at"], prev=prev)
        else:
            return False
        if digest != e["event_hash"]:
            return False
        prev = e["event_hash"]
    return True


def chain_intact(conn, contract_id: str) -> bool:
    c = _row(conn, "SELECT contract_ref FROM tb_contract WHERE id = ?", (contract_id,))
    return c is not None and chain_intact_events(c["contract_ref"], events(conn, contract_id))


# ── contracts ───────────────────────────────────────────────────────────────

def _next_ref(conn) -> str:
    n = _row(conn, "SELECT nextval('tb_contract_ref_seq') AS n")["n"]
    return f"GEX-TB-{date.today().year}-{n:06d}"


def create_contract(conn, *, terms: TermsIn, owner_company_id: str, kind: str, project_id: Optional[str],
                    origin_ref: str, correlation_id: Optional[str], actor: str, company_id: Optional[str],
                    note: str, event_type: str = "CREATED_FROM_MATCH", fill_id: Optional[str] = None,
                    token_ids: Iterable[str] = (), reason: str = "executed",
                    trade_status: str = "pending_confirmation") -> dict:
    """A draft contract — version 1, pending confirmation, UNVERIFIED — with its
    terms frozen and its genesis event, in the caller's transaction."""
    if _row(conn, "SELECT id FROM tb_contract WHERE origin_ref = ?", (origin_ref,)):
        raise RecordRefused(409, "CONTRACT_EXISTS", f"{origin_ref} already has its contract.")
    w = write_terms(conn, terms, owner_company_id)
    contract_id, version_id, ref = str(uuid.uuid4()), str(uuid.uuid4()), _next_ref(conn)
    conn.execute("INSERT INTO tb_contract (id, contract_type, contract_ref, trade_status, verification_state, "
                 "trade_date, kind, project_id, origin_ref, correlation_id, fill_id, created_at, updated_at) "
                 "VALUES (?, 'terms', ?, ?, 'UNVERIFIED', current_date, ?, ?, ?, ?, ?, now(), now())",
                 (contract_id, ref, trade_status, kind, project_id, origin_ref, correlation_id, fill_id))
    conn.execute("INSERT INTO tb_contract_version (id, contract_id, version, terms_id, terms_hash, reason) "
                 "VALUES (?, ?, 1, ?, ?, ?)", (version_id, contract_id, w["terms_id"], w["terms_hash"], reason))
    for token_id in token_ids:
        conn.execute("INSERT INTO tb_contract_version_token (version_id, token_id) VALUES (?, ?)", (version_id, token_id))
    genesis = append_event(conn, contract_id, event_type, actor, company_id, version_id=version_id,
                           terms_hash=w["terms_hash"], note=note)
    conn.execute("UPDATE tb_contract SET token_ref = ? WHERE id = ?", (genesis["event_hash"], contract_id))
    conn.execute("UPDATE tb_contract_version SET token_event_ref = ? WHERE id = ?", (genesis["event_hash"], version_id))
    return {"id": contract_id, "contract_ref": ref, "version_id": version_id, "event": genesis, **w}


def current_version(conn, contract_id: str) -> Optional[dict]:
    return _row(conn, "SELECT * FROM tb_contract_version WHERE contract_id = ? AND superseded_at IS NULL",
                (contract_id,))


def parties(conn, contract_id: str) -> dict:
    """{"seller": company, "buyers": [company…], "companies": {…}} of the current
    version, read from its legs through the side convention."""
    v = current_version(conn, contract_id)
    if v is None:
        return {"seller": None, "buyers": [], "companies": set()}
    legs = _rows(conn, "SELECT l.leg_role::text AS leg_role, pc.company_id AS payer, rc.company_id AS receiver "
                       "FROM tb_leg l LEFT JOIN tb_counterparty pc ON pc.id = l.payer_id "
                       "LEFT JOIN tb_counterparty rc ON rc.id = l.receiver_id WHERE l.terms_id = ?", (v["terms_id"],))
    seller, buyers = None, []
    for leg in legs:
        sell_pays = PAYER_SIDE[LegRole(leg["leg_role"])] == Side.SELL
        s, b = (leg["payer"], leg["receiver"]) if sell_pays else (leg["receiver"], leg["payer"])
        seller = seller or s
        if b and b not in buyers:
            buyers.append(b)
    return {"seller": seller, "buyers": buyers, "companies": {c for c in [seller, *buyers] if c}}


def by_origin(conn, origin_ref: str) -> Optional[dict]:
    return _row(conn, "SELECT * FROM tb_contract WHERE origin_ref = ?", (origin_ref,))


def clauses(conn, terms_id: str) -> list[dict]:
    return _rows(conn, "SELECT c.clause_type, c.seq, c.attrs, s.seq AS sub_leg FROM tb_clause c "
                       "LEFT JOIN tb_sub_leg s ON s.id = c.sub_leg_id WHERE c.terms_id = ? ORDER BY c.seq",
                 (terms_id,))


# ── the market's view of a contract (the 063 shape, until the screens move) ─

def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def market_view(conn, contract_id: str) -> Optional[dict]:
    """A record contract in the shape the market screens read from `contracts`
    (063). Phase 3 replaces this with views; until then nothing is typed twice:
    every value comes from the record."""
    c = _row(conn, "SELECT c.*, p.project_name FROM tb_contract c LEFT JOIN projects p ON p.project_id = c.project_id "
                   "WHERE c.id = ? AND c.contract_type = 'terms'", (contract_id,))
    if c is None:
        return None
    v = current_version(conn, contract_id)
    t = _row(conn, "SELECT t.currency, co.market_molecule FROM tb_terms t JOIN tb_commodity co ON co.id = t.commodity_id "
                   "WHERE t.id = ?", (v["terms_id"],))
    flows = _rows(conn, "SELECT l.leg_role::text AS leg_role, f.flow_type::text AS flow_type, f.period_start, "
                        "f.period_end, f.quantity, f.unit_price FROM tb_flow f JOIN tb_leg l ON l.id = f.leg_id "
                        "WHERE l.terms_id = ? ORDER BY l.seq, f.seq", (v["terms_id"],))
    product = [f for f in flows if f["flow_type"] == "physical"]
    priced = [f for f in flows if f["flow_type"] == "fixed_cash" and f["unit_price"] is not None]
    start = min((f["period_start"] for f in product), default=None)
    end = max((f["period_end"] for f in product), default=None)
    days = (end - start).days + 1 if start and end else None
    total = sum((f["quantity"] for f in product), Decimal(0))
    who = parties(conn, contract_id)
    buyer = who["buyers"][0] if who["buyers"] else None
    names = {r["company_id"]: r["company_name"] for r in _rows(
        conn, "SELECT company_id, company_name FROM tenants WHERE company_id IN (?, ?)", (who["seller"], buyer))}
    cl = {x["clause_type"]: (x["attrs"] or {}).get("text") for x in clauses(conn, v["terms_id"])}
    token = _row(conn, "SELECT token_id FROM tb_contract_version_token WHERE version_id = ? LIMIT 1", (v["id"],))
    origin = c["origin_ref"] or ""
    return {
        "id": str(c["id"]), "project_id": c["project_id"], "project_name": c.get("project_name"),
        "contract_id_external": c["contract_ref"], "counterparty": names.get(buyer) or buyer,
        "molecule": t["market_molecule"], "currency": t["currency"],
        "volume_mtpd": _f(total / days) if days else None,
        "price_eur_kg": _f(priced[0]["unit_price"] / 1000) if priced else None,
        "start_date": start.isoformat() if start else None, "end_date": end.isoformat() if end else None,
        "tenor_years": max(0, int(days / 365.25)) if days else None,
        "pricing_basis": " | ".join(x for x in (cl.get("delivery"), cl.get("payment")) if x) or None,
        "delivery_terms": cl.get("delivery"), "payment_terms": cl.get("payment"), "credit_rating": None,
        "status": c["trade_status"], "verification_state": c["verification_state"],
        "version": v["version"], "terms_hash": v["terms_hash"],
        "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
        "correlation_id": c["correlation_id"],
        "match_id": origin[len("match:"):] if origin.startswith("match:") else None,
        "token_id": token["token_id"] if token else None,
        "seller_company_id": who["seller"], "buyer_company_id": buyer,
    }


def market_views_for(conn, company_id: Optional[str]) -> list[dict]:
    """Every record contract the company is a party to (None: every one — GEX)."""
    ids = [str(r["id"]) for r in _rows(conn, "SELECT id FROM tb_contract WHERE contract_type = 'terms' "
                                             "ORDER BY created_at DESC")]
    out = []
    for cid in ids:
        if company_id is None or company_id in parties(conn, cid)["companies"]:
            out.append(market_view(conn, cid))
    return out
