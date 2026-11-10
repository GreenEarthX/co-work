"""
Contract tokens — only confirmed terms reach the engine (JML 2026-10-28; 078).

The commitment cards hold the terms the cross-contract checks (C1–C10) and the
offtake / EPC ladders compare. The OWNER types them. On their own they prove
nothing: an owner could adjust a volume until C2 passed. So every card field
belongs to a CONTRACT KIND, each kind of a project has a token (an append-only,
hash-chained event log), and a field reaches the engine only when its value is
the one in the latest version CONFIRMED on that token:

  offtake, ppa, supply, epc, licence   confirmed by the COUNTERPARTY company,
                                       registered on the token by the owner.
                                       Its confirmation also VERIFIES the
                                       contract's own instrument evidence.
  technical (G5), model (G8)           the producer's own plan — confirmed by an
                                       appointed independent reviewer of that gate.

A card edit appends a VERSION; until it is confirmed the changed fields are held
back, so the checks that need them read UNRESOLVED — never the unconfirmed
number. Adverse facts (contractor insolvent, PPA or support revoked,
certification suspended) apply at once when reported; clearing one needs a
confirmation.

STORE (Phase 2 of "One contract record", 2026-11-06; alembic 085). The tokens
are no longer a store of their own: each (project, kind) is ONE contract of the
contract record (trading_book/record.py) — origin_ref 'project:<id>:<kind>',
`card` terms holding the version's {card.field: value}, one hash-chained event
log — and the engine reads the view v_engine_contract_terms. This module keeps
its functions and their shapes so /api/v1/contract-tokens and the card save
behave exactly as before; it is a compatibility layer and is DEPRECATED for new
callers (handoff §8 item 57). `terms_sha256` is still 078's hash of the
projection (tb_contract_version.legacy_terms_sha256): the hash a confirmation
names. Writes run on the record's operator connection, after the route has
authorised the actor — the runtime role can no longer insert a contract event
of its own (alembic 083/085).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

# card -> field -> contract kind
FIELD_KIND: dict[str, dict[str, str]] = {
    "offtake": {**{f: "offtake" for f in (
        "counterparty_name", "counterparty_role", "buyer_investment_grade", "credit_support", "commitment_form",
        "take_or_pay_pct", "contracted_tonnes_per_year", "tenor_years", "price_mechanism", "cps_satisfied",
        "conditions_precedent", "longstop_date", "first_delivery_date", "delay_ld_cap_eur",
        "product_spec_standard", "certification_scheme", "compliance_regime", "fm_definition_ref",
        "change_in_law_allocated")},
        "planned_output_tonnes_per_year": "technical"},
    "epc": {**{f: "epc" for f in (
        "contractor_name", "contracting_model", "contract_price_eur", "guaranteed_completion_date",
        "guaranteed_capacity_tonnes_per_year", "expected_availability_pct", "delay_ld_cap_eur",
        "performance_ld_cap_eur", "guaranteed_product_spec", "fm_definition_ref")},
        "contingency_eur": "model", "sponsor_support_eur": "model", "counterparty_insolvent": "epc"},
    "schedule": {f: "technical" for f in (
        "permits_expected_date", "appeal_period_months", "fid_target_date", "construction_months_p80",
        "commissioning_allowance_months", "forecast_cod_date", "actual_cod_date")},
    "supply": {"feedstock_required_tonnes_per_year": "technical", "power_required_mwh_per_year": "technical",
               "feedstock_contracted_tonnes_per_year": "supply", "feedstock_tenor_years": "supply",
               "co2_source_eligible": "supply", "certification_scheme": "supply", "fm_definition_ref": "supply",
               "power_contracted_mwh_per_year": "ppa", "power_tenor_years": "ppa",
               "power_meets_certification": "ppa",
               "support_or_ppa_revoked": "ppa", "certification_suspended": "supply"},
    "model": {f: "model" for f in ("debt_tenor_years", "model_contracted_tonnes_per_year",
                                   "model_offtake_tenor_years", "model_epc_price_eur")},
}
# Reporting one of these only hurts the reporter: it applies at once when true.
ADVERSE_FACTS = {("epc", "counterparty_insolvent"), ("supply", "support_or_ppa_revoked"),
                 ("supply", "certification_suspended")}
COUNTERPARTY_KINDS = ("offtake", "ppa", "supply", "epc", "licence")

# Adverse facts as EVENTS (Phase 3 of "One contract record", Q10, JML 2026-11-06):
# fact -> (the contract kind it is reported on, the card field it sets for the
# engine, whether its subject is the contract's confirming party). BUYER_INSOLVENT
# is new: it is reported on one buyer's sub-leg of an offtake frame and drops only
# that buyer from the aggregate. A card that still says true keeps applying (the
# card and the events are joined, never one in place of the other), so moving to
# events cannot weaken a fact already reported.
FACTS: dict[str, tuple[str, Optional[tuple[str, str]], bool]] = {
    "COUNTERPARTY_INSOLVENT": ("epc", ("epc", "counterparty_insolvent"), True),
    "SUPPORT_OR_PPA_REVOKED": ("ppa", ("supply", "support_or_ppa_revoked"), False),
    "CERTIFICATION_SUSPENDED": ("supply", ("supply", "certification_suspended"), False),
    "BUYER_INSOLVENT": ("offtake", None, True),
}
CLEARERS_NEEDED = 2
REVIEWER_KINDS = {"technical": "G5", "model": "G8"}     # gate whose appointed reviewer confirms
# The instruments a counterparty's confirmation verifies (it is a party to them).
# Never an instrument a THIRD PARTY issues — the offtaker's letter of credit, the EPC contractor's
# bond: confirming one's own contract says nothing about the bank behind it (rules 4.3.0 review).
CONTRACT_EVIDENCE: dict[str, tuple[str, ...]] = {
    "offtake": ("binding_offtake_contract_executed",),
    "ppa": ("ppa_signed_or_term_sheet_evidence",),
    "supply": ("feedstock_supply_agreement",),
    "epc": ("epc_contract_fixed_price_or_capped_gmp",),
    "licence": ("technology_licensor_term_sheet", "technology_licence_process_guarantee"),
}


class TokenRefusal(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def kind_terms(cards: dict, kind: str) -> dict:
    """The fields of every card that belong to `kind`, as {"card.field": value}."""
    out = {}
    for card, fields in FIELD_KIND.items():
        for field, k in fields.items():
            if k == kind and field in (cards.get(card) or {}):
                out[f"{card}.{field}"] = (cards.get(card) or {})[field]
    return out


def terms_hash(terms: dict) -> str:
    return hashlib.sha256(json.dumps(terms, sort_keys=True, default=str).encode()).hexdigest()


def engine_terms(cards: dict, confirmed: dict[str, dict],
                 buyers: Optional[list[dict]] = None, facts: Optional[list[dict]] = None) -> tuple[dict, dict]:
    """(terms the engine may use, fields held back awaiting confirmation).

    `confirmed` maps kind -> {"card.field": value} of its latest CONFIRMED version.
    `buyers` are a frame's in-force buyer confirmations (v_engine_offtake_buyers);
    when the offtake card is a frame, its offtake fields come from them alone
    (frame_engine_card), never from a contract-level confirmation.
    """
    used: dict[str, dict] = {}
    held: dict[str, list[str]] = {}
    facts = facts or []
    insolvent = {f["subject_company_id"] for f in facts if f["fact"] == "BUYER_INSOLVENT"}
    frame = frame_buyers(cards or {})
    if frame:
        # An insolvent buyer's confirmation stops counting at once (Q10): its volume leaves the aggregate.
        f_used, f_held = frame_engine_card(cards, [b for b in buyers or [] if b["buyer_company_id"] not in insolvent])
        if f_used:
            used["offtake"] = f_used
        if f_held:
            held["offtake"] = f_held
    for card, fields in (cards or {}).items():
        for field, value in (fields or {}).items():
            if frame and card == "offtake" and (field == "buyers" or FIELD_KIND["offtake"].get(field) == "offtake"):
                continue                      # the frame's own offtake terms: decided above
            kind = FIELD_KIND.get(card, {}).get(field)
            ok = (kind is not None and f"{card}.{field}" in confirmed.get(kind, {})
                  and confirmed[kind][f"{card}.{field}"] == value)
            if (card, field) in ADVERSE_FACTS and value is True:
                ok = True
            if ok:
                used.setdefault(card, {})[field] = value
            else:
                held.setdefault(kind or "unmapped", []).append(f"{card}.{field}")
    for f in facts:                            # an open adverse fact applies at once, whatever the card says
        target = FACTS[f["fact"]][1]
        if target is not None:
            used.setdefault(target[0], {})[target[1]] = True
    return used, held


# ── The offtake frame (Phase 3, Q2): one sub-leg per buyer ──────────────────
#
# With several buyers the offtake card holds the shared terms at its top level and
# one entry per buyer in `buyers` (validated in core/commitment_terms.py). Each
# buyer confirms its own sub-leg; the engine reads ONE offtake card built from the
# confirmed buyers — JML's conservative aggregate, 2026-11-10:
#   contracted_tonnes_per_year   the sum over the confirmed buyers
#   tenor_years, take_or_pay_pct the weakest (smallest) buyer's
#   commitment_form              the weakest buyer's (FORM_STRENGTH)
#   buyer_investment_grade,      true only if EVERY buyer's is
#   credit_support
# A field reaches the engine only when every buyer of the card has confirmed its
# own value for it — the volume excepted, which sums the confirmed buyers (a lower
# bound). A buyer's confirmation is in force only while the shared terms are the
# ones it confirmed (a shared change withdraws every confirmation, Q2); the shared
# terms themselves reach the engine only when every buyer's is. Fields JML's rule
# does not name (counterparty, price mechanism, CPs, longstop, first delivery, LD
# cap) reach the engine only when every buyer confirmed the SAME value.

FORM_STRENGTH = {"FRAMEWORK": 0, "TAKE_IF_DELIVERED": 1, "TAKE_AND_PAY": 2, "TAKE_OR_PAY": 3,
                 "TAKE_IF_TENDERED": 4}
_SUMMED = ("contracted_tonnes_per_year",)
_WEAKEST = ("tenor_years",)
_EVERY = ("buyer_investment_grade", "credit_support")


def frame_buyers(cards: dict) -> Optional[list[dict]]:
    """The offtake card's buyers when it is a frame, else None (one counterparty, as in Phase 2)."""
    buyers = (cards.get("offtake") or {}).get("buyers")
    return buyers if isinstance(buyers, list) and buyers else None


def frame_terms(cards: dict) -> tuple[dict, list[tuple[str, dict]]]:
    """(shared {"offtake.field": value}, [(buyer company, its {"offtake.field": value})])."""
    off = cards.get("offtake") or {}
    shared = {f"offtake.{f}": v for f, v in off.items() if f != "buyers" and FIELD_KIND["offtake"].get(f) == "offtake"}
    buyers = [(b["company_id"], {f"offtake.{f}": v for f, v in b.items() if f != "company_id"})
              for b in frame_buyers(cards) or []]
    return shared, buyers


def frame_hash(shared: dict, buyers: list[tuple[str, dict]]) -> str:
    return terms_hash({"shared": shared, "buyers": [[company, terms] for company, terms in buyers]})


def frame_engine_card(cards: dict, confirmations: list[dict]) -> tuple[dict, list[str]]:
    """(the offtake card the engine may use, fields held back) from a frame card and
    its buyers' in-force confirmations."""
    shared, buyers = frame_terms(cards)
    conf = {r["buyer_company_id"]: r for r in confirmations}
    in_force = {c: conf[c] for c, _ in buyers if c in conf and (conf[c]["shared_terms"] or {}) == shared}
    used: dict = {}
    held: list[str] = []
    if len(in_force) == len(buyers):
        used.update({k.split(".", 1)[1]: v for k, v in shared.items()})
    else:
        held += sorted(shared)

    def confirmed(company: str, key: str):
        row = in_force.get(company)
        return row is not None and key in (row["sub_leg_terms"] or {}) and row["sub_leg_terms"][key] == \
            dict(buyers)[company].get(key)

    keys = sorted({k for _, t in buyers for k in t} - {"offtake.take_or_pay_pct"})   # decided with the form
    for key in keys:
        field = key.split(".", 1)[1]
        have = [(c, t[key]) for c, t in buyers if key in t]
        ok = [(c, v) for c, v in have if confirmed(c, key)]
        if field in _SUMMED:
            if ok:
                used[field] = sum(v for _, v in ok)
            if len(ok) < len(buyers):
                held.append(f"{key} ({len(buyers) - len(ok)} of {len(buyers)} buyers not confirmed)")
            continue
        if len(ok) < len(buyers):           # a buyer without the field, or not confirmed: not every buyer's
            held.append(key)
            continue
        values = [v for _, v in ok]
        if field in _WEAKEST:
            used[field] = min(values)
        elif field in _EVERY:
            used[field] = all(values)
        elif field == "commitment_form":
            used[field] = min(values, key=lambda f: FORM_STRENGTH.get(f, -1))
        elif all(v == values[0] for v in values):
            used[field] = values[0]
        else:
            held.append(f"{key} (the buyers' values differ)")
    # take-or-pay: once the form is settled, the smallest share among the buyers on a
    # take-or-pay form, each confirmed — never a share standing for a form not yet known.
    top = [c for c, t in buyers if t.get("offtake.commitment_form") == "TAKE_OR_PAY"]
    if top and "commitment_form" in used:
        pcts = [dict(buyers)[c].get("offtake.take_or_pay_pct") for c in top]
        if all(p is not None for p in pcts) and all(confirmed(c, "offtake.take_or_pay_pct") for c in top):
            used["take_or_pay_pct"] = min(pcts)
        else:
            held.append("offtake.take_or_pay_pct")
    elif top:
        held.append("offtake.take_or_pay_pct")
    return used, held


def frame_confirmations(project_id: str) -> list[dict]:
    """The frame's in-force buyer confirmations, from v_engine_offtake_buyers (alembic 092)."""
    from app.trading_book import record

    return _run(lambda c: record._rows(c, "SELECT * FROM v_engine_offtake_buyers WHERE project_id = ?", (project_id,)))


def frame_state(project_id: str, conn=None) -> Optional[dict]:
    """The frame's latest version: its shared hash and one entry per buyer's sub-leg."""
    from app.trading_book import record

    def go(c):
        row = record.by_origin(c, _origin(project_id, "offtake"))
        v = record.current_version(c, str(row["id"])) if row else None
        if v is None:
            return None
        t = record._row(c, "SELECT shared_hash FROM tb_terms WHERE id = ?", (str(v["terms_id"]),))
        subs = record._rows(c, "SELECT s.id, s.seq, s.sub_leg_hash, s.card_projection, cp.company_id "
                               "FROM tb_sub_leg s JOIN tb_counterparty cp ON cp.id = s.buyer_id "
                               "WHERE s.terms_id = ? AND s.card_projection IS NOT NULL ORDER BY s.seq",
                            (str(v["terms_id"]),))
        return {"contract_id": str(row["id"]), "version": v["version"], "version_id": str(v["id"]),
                "shared_hash": t["shared_hash"], "sub_legs": subs}
    return _run(go, conn)


def confirm_sub_leg(project_id: str, buyer_company: str, sub_leg_hash: str, event_type: str, actor: str,
                    note: Optional[str] = None) -> dict:
    """A buyer's CONFIRMED (or DISPUTED) of its own sub-leg of the latest version.
    The route has authorised the actor as that buyer; this checks the hash."""
    from app.trading_book import record

    def go(c):
        state = frame_state(project_id, conn=c)
        sub = next((s for s in (state or {}).get("sub_legs", []) if s["company_id"] == buyer_company), None)
        if sub is None:
            raise TokenRefusal(404, "NOT_A_BUYER_OF_THIS_FRAME", "Your company has no sub-leg in this offtake frame.")
        if event_type == "CONFIRMED" and sub_leg_hash != sub["sub_leg_hash"].strip():
            raise TokenRefusal(409, "NOT_THE_LATEST_VERSION",
                               "Confirm the latest version of your sub-leg: name its sub_leg_hash (it changed).")
        return record.append_event(c, state["contract_id"], event_type, actor, buyer_company,
                                   version_id=state["version_id"], sub_leg_id=str(sub["id"]),
                                   terms_hash=sub["sub_leg_hash"].strip(), note=note)
    return _run(go)


def _record_frame_version(c, contract_row: dict, cards: dict, sha: str, actor: str,
                          company_id: Optional[str], note: Optional[str] = None) -> dict:
    from app.trading_book import record
    from app.trading_book.terms import SubLegIn, TermsIn

    shared, buyers = frame_terms(cards)
    cid = contract_row["id"]
    owner = record._row(c, "SELECT owner_company_id FROM tb_contract WHERE id = ?", (cid,))["owner_company_id"]
    terms = TermsIn(profile="card", card_projection=shared,
                    sub_legs=[SubLegIn(seq=n, buyer=record.counterparty_for(c, company), card_projection=proj)
                              for n, (company, proj) in enumerate(buyers, start=1)])
    from app.trading_book.validation import validate_card
    problems = validate_card(terms)
    if problems:
        raise TokenRefusal(422, "FRAME_INVALID", f"The offtake frame does not validate: {problems}.")
    w = record.write_terms(c, terms, owner)
    n = (record._row(c, "SELECT coalesce(max(version), 0) AS n FROM tb_contract_version WHERE contract_id = ?",
                     (cid,))["n"]) + 1
    c.execute("UPDATE tb_contract_version SET superseded_at = now() WHERE contract_id = ? AND superseded_at IS NULL",
              (cid,))
    vid = str(uuid.uuid4())
    c.execute("INSERT INTO tb_contract_version (id, contract_id, version, terms_id, terms_hash, reason, "
              "legacy_terms_sha256) VALUES (?, ?, ?, ?, ?, 'card_saved', ?)",
              (vid, cid, n, w["terms_id"], w["terms_hash"], sha))
    ev = record.append_event(c, cid, "VERSION", actor, company_id, version_id=vid, terms_hash=w["terms_hash"],
                             note=note)
    c.execute("UPDATE tb_contract_version SET token_event_ref = ? WHERE id = ?", (ev["event_hash"], vid))
    return ev


# ── The cards as a view over the record (Phase 3, Q9) ───────────────────────
#
# A commitment card is no longer a row of its own (commitment_terms, retired by
# alembic 093): it is the union of the latest version of every contract kind its
# fields belong to (FIELD_KIND), with the offtake frame's buyers rebuilt from its
# sub-legs. A save writes versions only (record_versions), so the card and the
# record cannot diverge. Which card was saved, by whom and when is the CARD_SAVED
# marker each save leaves on the project's `technical` contract chain.

CARD_KIND_ORDER = list(COUNTERPARTY_KINDS) + list(REVIEWER_KINDS)
CARD_NOTE = '{"card"%'                # a save's note: {"card": card_type, "save": id} (sort_keys)


def _projection(c, terms_id: str) -> dict:
    """A version's {"card.field": value}, with a frame's buyers as "offtake.buyers"."""
    from app.trading_book import record

    t = record._row(c, "SELECT card_projection FROM tb_terms WHERE id = ?", (terms_id,))
    proj = dict((t or {}).get("card_projection") or {})
    subs = record._rows(c, "SELECT s.card_projection, cp.company_id FROM tb_sub_leg s JOIN tb_counterparty cp "
                           "ON cp.id = s.buyer_id WHERE s.terms_id = ? AND s.card_projection IS NOT NULL "
                           "ORDER BY s.seq", (terms_id,))
    if subs:
        proj["offtake.buyers"] = [{"company_id": s["company_id"],
                                   **{k.split(".", 1)[1]: v for k, v in (s["card_projection"] or {}).items()}}
                                  for s in subs]
    return proj


def card_view(project_id: str, conn=None) -> dict[str, dict]:
    """{card_type: {"terms", "updated_by", "updated_at"}} rebuilt from the record: each
    kind's current version, split back into the cards its fields come from. A card a
    save emptied stays listed, empty. On the caller's tenant connection RLS applies
    (a frame buyer reads its own sub-leg only)."""
    from app.trading_book import record

    def go(c):
        cards: dict[str, dict] = {}
        meta: dict[str, dict] = {}

        def touch(card, actor, at):
            if card not in meta or at > meta[card]["updated_at"]:
                meta[card] = {"updated_by": actor, "updated_at": at}

        for kind in CARD_KIND_ORDER:
            row = record.by_origin(c, _origin(project_id, kind))
            if row is None:
                continue
            v = record.current_version(c, str(row["id"]))
            made = record._row(c, "SELECT actor, at FROM tb_contract_event WHERE event_hash = ?",
                               (v["token_event_ref"],)) if v is not None and v.get("token_event_ref") else None
            if v is not None:
                for key, value in _projection(c, str(v["terms_id"])).items():
                    card, field = key.split(".", 1)
                    cards.setdefault(card, {})[field] = value
                    if made:
                        touch(card, made["actor"], str(made["at"]))
            for e in record._rows(c, "SELECT actor, at, note FROM tb_contract_event WHERE contract_id = ? "
                                     "AND event_type = 'VERSION' AND note LIKE ?", (str(row["id"]), CARD_NOTE)):
                touch(json.loads(e["note"])["card"], e["actor"], str(e["at"]))
        return {card: {"terms": cards.get(card, {}), **m} for card, m in meta.items()}
    return _run(go, conn)


def card_terms(project_id: str, conn=None) -> dict[str, dict]:
    """{card_type: terms}: the cards as the engine's input."""
    return {card: v["terms"] for card, v in card_view(project_id, conn=conn).items()}


def card_history(project_id: str, conn=None) -> list[dict]:
    """The cards' history, newest first, in the shape 058's commitment_terms_events
    had: {card_type, old_json, new_json, actor, at}, one entry per save that changed
    its card — rebuilt by replaying the project's card-saved VERSION events, save by save."""
    from app.trading_book import record

    def go(c):
        evs = []
        for kind in CARD_KIND_ORDER:
            row = record.by_origin(c, _origin(project_id, kind))
            if row is None:
                continue
            for e in record._rows(c, "SELECT e.seq, e.at, e.actor, e.note, v.terms_id FROM tb_contract_event e "
                                     "JOIN tb_contract_version v ON v.id = e.version_id WHERE e.contract_id = ? "
                                     "AND e.event_type = 'VERSION' AND e.note LIKE ?", (str(row["id"]), CARD_NOTE)):
                evs.append({**e, "kind": kind, **json.loads(e["note"])})
        evs.sort(key=lambda e: (str(e["at"]), e["seq"]))
        by_kind: dict[str, dict] = {}
        out, prev = [], {}
        for save_id in dict.fromkeys(e["save"] for e in evs):
            group = [e for e in evs if e["save"] == save_id]
            card_type = group[0]["card"]
            for e in group:
                by_kind[e["kind"]] = _projection(c, str(e["terms_id"]))
            now = {k.split(".", 1)[1]: v for proj in by_kind.values() for k, v in proj.items()
                   if k.split(".", 1)[0] == card_type}
            new_json = json.dumps(now, sort_keys=True)
            if new_json != prev.get(card_type):
                out.append({"card_type": card_type, "old_json": prev.get(card_type), "new_json": new_json,
                            "actor": group[0]["actor"], "at": str(group[0]["at"])})
                prev[card_type] = new_json
        return list(reversed(out))
    return _run(go, conn)


# ── Novation (Phase 3, Q13): a buyer's sub-leg changes hands, with consent ──
#
# Rule 3 stands: the record is not a transferable asset and no token is built. A
# sub-leg changes hands by NOVATION events on the frame's chain: a proposal naming
# the outgoing and the incoming buyer and the sub-leg hash it moves, then one
# confirmation from each of the three parties — the producer, the outgoing buyer
# and the incoming buyer — each naming the proposal's event hash (the proposer's
# proposal is its confirmation). On the third, in the same transaction, the frame
# gets a new version in which that sub-leg's buyer is the incoming buyer (same
# terms), and the incoming buyer's confirmation of the novation is recorded as its
# CONFIRMED of that sub-leg: its volume reaches the engine at once. Until then the
# outgoing buyer's confirmed terms keep counting. Lenders' consent, when given, is a
# document named on the event; GEX checks none of it.

NOVATION_PARTIES = ("producer", "outgoing", "incoming")


def _novation_events(c, contract_id: str) -> list[dict]:
    from app.trading_book import record

    return [{**json.loads(e["note"]), "seq": e["seq"], "event_hash": e["event_hash"], "actor": e["actor"],
             "company_id": e["company_id"], "at": str(e["at"])}
            for e in record._rows(c, "SELECT * FROM tb_contract_event WHERE contract_id = ? "
                                     "AND event_type = 'NOVATION' ORDER BY seq", (contract_id,))]


def novations(project_id: str, conn=None) -> list[dict]:
    """Every novation proposed on the offtake frame: who must still confirm, and its state."""
    from app.trading_book import record

    def go(c):
        row = record.by_origin(c, _origin(project_id, "offtake"))
        if row is None:
            return []
        evs = _novation_events(c, str(row["id"]))
        current = {s["company_id"]: s["sub_leg_hash"].strip()
                   for s in (frame_state(project_id, conn=c) or {}).get("sub_legs", [])}
        out = []
        for p in (e for e in evs if e.get("step") == "proposed"):
            confirms = [p] + [e for e in evs if e.get("step") == "confirmed" and e.get("proposal") == p["event_hash"]]
            done = {e["party"] for e in confirms}
            # a proposal lapses when the sub-leg it moves is no longer the outgoing buyer's current one
            state = ("completed" if any(e.get("step") == "completed" and e.get("proposal") == p["event_hash"]
                                        for e in evs)
                     else "pending" if current.get(p["outgoing"]) == p["sub_leg_hash"] else "lapsed")
            out.append({"proposal_event_hash": p["event_hash"], "outgoing_company_id": p["outgoing"],
                        "incoming_company_id": p["incoming"], "sub_leg_hash": p["sub_leg_hash"],
                        "document_sha256": p.get("document_sha256"), "confirmed_by": sorted(done),
                        "awaiting": [x for x in NOVATION_PARTIES if x not in done], "state": state})
        return out
    return _run(go, conn)


def _party_of(project_owner: str, proposal: dict, company: str) -> Optional[str]:
    if company == project_owner:
        return "producer"
    if company == proposal["outgoing"]:
        return "outgoing"
    if company == proposal["incoming"]:
        return "incoming"
    return None


def propose_novation(project_id: str, owner: str, outgoing: str, incoming: str, actor: str, company_id: str,
                     document_sha256: Optional[str] = None) -> dict:
    """NOVATION 'proposed' on the frame — the proposer's own confirmation. The route has
    checked the proposer is one of the three and the incoming buyer is eligible."""
    from app.trading_book import record

    def go(c):
        state = frame_state(project_id, conn=c)
        sub = next((s for s in (state or {}).get("sub_legs", []) if s["company_id"] == outgoing), None)
        if sub is None:
            raise TokenRefusal(404, "NOT_A_BUYER_OF_THIS_FRAME", f"{outgoing} has no sub-leg in the offtake frame.")
        if incoming in {s["company_id"] for s in state["sub_legs"]}:
            raise TokenRefusal(409, "ALREADY_A_BUYER", f"{incoming} already holds a sub-leg; a frame has one per buyer.")
        if any(n["state"] == "pending" and n["outgoing_company_id"] == outgoing for n in novations(project_id, conn=c)):
            raise TokenRefusal(409, "NOVATION_PENDING", "A novation of this sub-leg is already awaiting confirmation.")
        last = record._row(c, "SELECT e.event_type FROM tb_contract_event e JOIN tb_sub_leg s ON s.id = e.sub_leg_id "
                              "JOIN tb_counterparty cp ON cp.id = s.buyer_id WHERE e.contract_id = ? "
                              "AND cp.company_id = ? AND e.event_type IN ('CONFIRMED', 'DISPUTED') "
                              "ORDER BY e.seq DESC LIMIT 1", (state["contract_id"], outgoing))
        if last and last["event_type"] == "DISPUTED":
            raise TokenRefusal(409, "SUB_LEG_DISPUTED", "The sub-leg has an open dispute: settle it before it changes hands.")
        cps = [record.counterparty_for(c, outgoing), record.counterparty_for(c, incoming),
               record.counterparty_for(c, owner)]
        restricted = record._row(c, "SELECT 1 AS x FROM tb_counterparty_restriction WHERE active AND "
                                    "((counterparty_id = ? AND restricted_counterparty_id = ?) OR "
                                    "(counterparty_id = ? AND restricted_counterparty_id = ?))",
                                 (cps[2], cps[1], cps[1], cps[2]))
        if restricted:
            raise TokenRefusal(409, "RESTRICTED_COUNTERPARTY", "The producer and the incoming buyer are a restricted pair.")
        party = _party_of(owner, {"outgoing": outgoing, "incoming": incoming}, company_id)
        body = {"step": "proposed", "outgoing": outgoing, "incoming": incoming, "sub_leg_hash": sub["sub_leg_hash"].strip(),
                "document_sha256": document_sha256, "party": party}
        return record.append_event(c, state["contract_id"], "NOVATION", actor, company_id,
                                   version_id=state["version_id"], sub_leg_id=str(sub["id"]),
                                   note=json.dumps(body, sort_keys=True))
    return _run(go)


def confirm_novation(project_id: str, owner: str, proposal_hash: str, actor: str, company_id: str) -> dict:
    """One party's confirmation; on the third, the novation completes in this transaction."""
    from app.trading_book import record
    from app.trading_book.terms import SubLegIn, TermsIn

    def go(c):
        n = next((x for x in novations(project_id, conn=c) if x["proposal_event_hash"] == proposal_hash), None)
        if n is None:
            raise TokenRefusal(404, "NO_SUCH_NOVATION", "No novation was proposed with that event hash.")
        if n["state"] == "completed":
            raise TokenRefusal(409, "NOVATION_COMPLETED", "That novation is complete.")
        if n["state"] == "lapsed":
            raise TokenRefusal(409, "SUB_LEG_CHANGED", "The sub-leg changed after the novation was proposed: "
                                                       "propose it again on its current terms.")
        proposal = {"outgoing": n["outgoing_company_id"], "incoming": n["incoming_company_id"]}
        party = _party_of(owner, proposal, company_id)
        if party is None:
            raise TokenRefusal(403, "NOT_A_NOVATION_PARTY", "Only the producer, the outgoing and the incoming buyer "
                                                            "confirm a novation.")
        if party in n["confirmed_by"]:
            raise TokenRefusal(409, "ALREADY_CONFIRMED", "Your party has confirmed this novation.")
        state = frame_state(project_id, conn=c)
        sub = next((s for s in state["sub_legs"] if s["company_id"] == n["outgoing_company_id"]), None)
        if sub is None or sub["sub_leg_hash"].strip() != n["sub_leg_hash"]:
            raise TokenRefusal(409, "SUB_LEG_CHANGED", "The sub-leg changed after the novation was proposed: "
                                                       "propose it again on its current terms.")
        ev = record.append_event(c, state["contract_id"], "NOVATION", actor, company_id,
                                 note=json.dumps({"step": "confirmed", "proposal": proposal_hash, "party": party},
                                                 sort_keys=True))
        if len(n["confirmed_by"]) + 1 < len(NOVATION_PARTIES):
            return {"event": ev, "completed": False}
        # The third confirmation: the frame's next version names the incoming buyer on the same terms.
        cid = state["contract_id"]
        v = record.current_version(c, cid)
        old = record.load_terms(c, str(v["terms_id"]))
        cp_in = record.counterparty_for(c, n["incoming_company_id"])
        subs = [SubLegIn(seq=s.seq, rank=s.rank, buyer=cp_in if s.seq == sub["seq"] else s.buyer,
                         card_projection=s.card_projection) for s in old.sub_legs]
        terms = TermsIn(profile="card", card_projection=old.card_projection, sub_legs=subs)
        w = record.write_terms(c, terms, record._row(c, "SELECT owner_company_id FROM tb_contract WHERE id = ?",
                                                     (cid,))["owner_company_id"])
        shared, buyers = frame_terms({"offtake": {**{k.split(".", 1)[1]: val for k, val in (old.card_projection or {}).items()},
                                                  "buyers": [{"company_id": n["incoming_company_id"] if s.seq == sub["seq"]
                                                              else record.company_of_counterparty(c, s.buyer),
                                                              **{k.split(".", 1)[1]: val for k, val in
                                                                 (s.card_projection or {}).items()}} for s in old.sub_legs]}})
        nv = v["version"] + 1
        c.execute("UPDATE tb_contract_version SET superseded_at = now() WHERE contract_id = ? AND superseded_at IS NULL",
                  (cid,))
        vid = str(uuid.uuid4())
        c.execute("INSERT INTO tb_contract_version (id, contract_id, version, terms_id, terms_hash, reason, "
                  "legacy_terms_sha256) VALUES (?, ?, ?, ?, ?, 'novation', ?)",
                  (vid, cid, nv, w["terms_id"], w["terms_hash"], frame_hash(shared, buyers)))
        done = record.append_event(c, cid, "NOVATION", actor, company_id, version_id=vid, terms_hash=w["terms_hash"],
                                   note=json.dumps({"step": "completed", "proposal": proposal_hash}, sort_keys=True))
        c.execute("UPDATE tb_contract_version SET token_event_ref = ? WHERE id = ?", (done["event_hash"], vid))
        new_sub = w["sub_legs"][sub["seq"]]
        incoming_actor = actor if party == "incoming" else next(
            e["actor"] for e in _novation_events(c, cid)
            if e.get("party") == "incoming" and e.get("proposal", e["event_hash"]) in (proposal_hash,))
        conf = record.append_event(c, cid, "CONFIRMED", incoming_actor, n["incoming_company_id"], version_id=vid,
                                   sub_leg_id=new_sub["id"], terms_hash=new_sub["hash"],
                                   note=f"confirmed by its confirmation of novation {proposal_hash[:12]}")
        return {"event": ev, "completed": True, "version": nv, "incoming_confirmed": conf}
    return _run(go)


# ── Adverse facts (Q10) ─────────────────────────────────────────────────────

def _fact_events(c, contract_id: str) -> list[dict]:
    from app.trading_book import record

    out = []
    for e in record._rows(c, "SELECT * FROM tb_contract_event WHERE contract_id = ? AND event_type IN "
                             "('ADVERSE_FACT_REPORTED', 'ADVERSE_FACT_CLEARED') ORDER BY seq", (contract_id,)):
        body = json.loads(e["note"] or "{}")
        out.append({**body, "event_type": e["event_type"], "seq": e["seq"], "event_hash": e["event_hash"],
                    "actor": e["actor"], "company_id": e["company_id"], "at": str(e["at"])})
    return out


def adverse_facts(project_id: str, conn=None) -> list[dict]:
    """Every adverse fact reported on the project's contracts, open or cleared: the
    report, who confirmed its clearing, and whether it still applies."""
    def go(c):
        out = []
        for kind in {k for k, _, _ in FACTS.values()}:
            row = contract(project_id, kind, create=False, conn=c)
            if row is None:
                continue
            evs = _fact_events(c, row["id"])
            for r in (e for e in evs if e["event_type"] == "ADVERSE_FACT_REPORTED"):
                clears = [e for e in evs if e["event_type"] == "ADVERSE_FACT_CLEARED" and e.get("clears") == r["event_hash"]]
                out.append({"kind": kind, "fact": r["fact"], "subject_company_id": r.get("subject_company_id"),
                            "report_event_hash": r["event_hash"], "reported_by": r["actor"],
                            "reporter_company_id": r["company_id"], "document_sha256": r["document_sha256"],
                            "note": r.get("text"), "at": r["at"],
                            "cleared_by": [{"company_id": e["company_id"], "actor": e["actor"],
                                            "document_sha256": e["document_sha256"]} for e in clears],
                            "open": len({e["company_id"] for e in clears}) < CLEARERS_NEEDED})
        return out
    return _run(go, conn)


def open_facts(project_id: str) -> list[dict]:
    return [f for f in adverse_facts(project_id) if f["open"]]


def report_fact(project_id: str, fact: str, document_sha256: str, actor: str, company_id: str,
                subject_company_id: Optional[str] = None, text: Optional[str] = None) -> dict:
    """ADVERSE_FACT_REPORTED on the contract it concerns. The route has authorised the reporter."""
    from app.trading_book import record

    kind = FACTS[fact][0]

    def go(c):
        row = contract(project_id, kind, conn=c)
        body = {"fact": fact, "document_sha256": document_sha256, "subject_company_id": subject_company_id,
                "text": text}
        sub_leg_id = None
        if fact == "BUYER_INSOLVENT":
            state = frame_state(project_id, conn=c)
            sub = next((s for s in (state or {}).get("sub_legs", []) if s["company_id"] == subject_company_id), None)
            if sub is None:
                raise TokenRefusal(404, "NOT_A_BUYER_OF_THIS_FRAME", "That company has no sub-leg in the offtake frame.")
            sub_leg_id = str(sub["id"])
        if any(f["fact"] == fact and f["subject_company_id"] == subject_company_id and f["open"]
               for f in adverse_facts(project_id, conn=c)):
            raise TokenRefusal(409, "ALREADY_REPORTED", "That fact is already reported and not cleared.")
        return record.append_event(c, row["id"], "ADVERSE_FACT_REPORTED", actor, company_id, sub_leg_id=sub_leg_id,
                                   note=json.dumps(body, sort_keys=True))
    return _run(go)


def clear_fact(project_id: str, report_event_hash: str, document_sha256: str, actor: str, company_id: str) -> dict:
    """One party's ADVERSE_FACT_CLEARED naming the report. The fact stops applying once
    two parties of different companies have cleared it. The route checks who may."""
    from app.trading_book import record

    def go(c):
        fact = next((f for f in adverse_facts(project_id, conn=c) if f["report_event_hash"] == report_event_hash), None)
        if fact is None:
            raise TokenRefusal(404, "NO_SUCH_REPORT", "No adverse fact was reported with that event hash.")
        if not fact["open"]:
            raise TokenRefusal(409, "ALREADY_CLEARED", "That fact is already cleared.")
        if company_id in {x["company_id"] for x in fact["cleared_by"]}:
            raise TokenRefusal(409, "ALREADY_CONFIRMED_BY_YOUR_COMPANY",
                               "Your company has confirmed this clearing; a second company must.")
        row = contract(project_id, fact["kind"], create=False, conn=c)
        return record.append_event(c, row["id"], "ADVERSE_FACT_CLEARED", actor, company_id,
                                   note=json.dumps({"clears": report_event_hash, "document_sha256": document_sha256},
                                                   sort_keys=True))
    return _run(go)


# ── Store: the one contract record (alembic 065/083/085) ────────────────────

def _conn():
    """The record's operator connection (PLATFORM_ADMIN). Every caller of a write
    has authorised its actor first (routes_contract_tokens, the card save's R5)."""
    from app.core import market_engine as me

    return me._conn()


def _run(fn, conn=None):
    """Run `fn(conn)`; with no connection given, on a new one that is committed."""
    if conn is not None:
        return fn(conn)
    own = _conn()
    try:
        out = fn(own)
        own.commit()
        return out
    finally:
        own.close()


def _origin(project_id: str, kind: str) -> str:
    return f"project:{project_id}:{kind}"


def _contract_dict(row: dict) -> dict:
    return {"id": str(row["id"]), "project_id": row["project_id"], "kind": row["kind"],
            "counterparty_company_id": row["confirming_company_id"], "contract_ref": row["contract_ref"]}


def contract(project_id: str, kind: str, create: bool = True, conn=None) -> Optional[dict]:
    from app.trading_book import record

    def go(c):
        row = record.by_origin(c, _origin(project_id, kind))
        if row is None and create:
            owner = record._row(c, "SELECT owner_tenant_id FROM projects WHERE project_id = ?", (project_id,))
            c.execute("INSERT INTO tb_contract (id, contract_type, contract_ref, kind, project_id, origin_ref, "
                      "owner_company_id, verification_state, created_at, updated_at) "
                      "VALUES (gen_random_uuid(), 'terms', ?, ?, ?, ?, ?, 'UNVERIFIED', now(), now()) "
                      "ON CONFLICT (origin_ref) DO NOTHING",
                      (record._next_ref(c), kind, project_id, _origin(project_id, kind),
                       (owner or {}).get("owner_tenant_id")))
            row = record.by_origin(c, _origin(project_id, kind))
        return _contract_dict(row) if row else None
    return _run(go, conn)


def events(contract_id: str, conn=None) -> list[dict]:
    """The contract's chain, with 078's field names kept: `terms_sha256` is the
    hash a confirmation names, `terms_json` a VERSION's {card.field: value}."""
    from app.trading_book import record

    def go(c):
        rows = record._rows(c, "SELECT e.*, v.version, v.legacy_terms_sha256, t.card_projection, s.seq AS sub_leg_seq "
                               "FROM tb_contract_event e LEFT JOIN tb_contract_version v ON v.id = e.version_id "
                               "LEFT JOIN tb_terms t ON t.id = v.terms_id LEFT JOIN tb_sub_leg s ON s.id = e.sub_leg_id "
                               "WHERE e.contract_id = ? ORDER BY e.seq", (contract_id,))
        for r in rows:
            r["terms_sha256"] = r["terms_hash"] if r["hash_scheme"] == "078" else r["legacy_terms_sha256"]
            r["terms_json"] = r["card_projection"] if r["event_type"] == "VERSION" else None
            r["at"] = str(r["at"])
        return rows
    return _run(go, conn)


def _version_for(c, contract_id: str, sha: Optional[str]) -> Optional[dict]:
    from app.trading_book import record

    if not sha:
        return None
    return record._row(c, "SELECT * FROM tb_contract_version WHERE contract_id = ? AND legacy_terms_sha256 = ? "
                          "ORDER BY version DESC LIMIT 1", (contract_id, sha))


def _record_version(c, contract_row: dict, terms: dict, sha: str, actor: str, company_id: Optional[str],
                    note: Optional[str] = None) -> dict:
    from app.trading_book import record
    from app.trading_book.terms import TermsIn

    cid = contract_row["id"]
    owner = record._row(c, "SELECT owner_company_id FROM tb_contract WHERE id = ?", (cid,))["owner_company_id"]
    w = record.write_terms(c, TermsIn(profile="card", card_projection=terms), owner)
    n = (record._row(c, "SELECT coalesce(max(version), 0) AS n FROM tb_contract_version WHERE contract_id = ?",
                     (cid,))["n"]) + 1
    c.execute("UPDATE tb_contract_version SET superseded_at = now() WHERE contract_id = ? AND superseded_at IS NULL",
              (cid,))
    vid = str(uuid.uuid4())
    c.execute("INSERT INTO tb_contract_version (id, contract_id, version, terms_id, terms_hash, reason, "
              "legacy_terms_sha256) VALUES (?, ?, ?, ?, ?, 'card_saved', ?)",
              (vid, cid, n, w["terms_id"], w["terms_hash"], sha))
    ev = record.append_event(c, cid, "VERSION", actor, company_id, version_id=vid, terms_hash=w["terms_hash"],
                             note=note)
    c.execute("UPDATE tb_contract_version SET token_event_ref = ? WHERE id = ?", (ev["event_hash"], vid))
    return ev


def append(contract_row: dict, event_type: str, actor: str, company_id: Optional[str], *,
           terms: Optional[dict] = None, sha: Optional[str] = None, note: Optional[str] = None, conn=None) -> dict:
    """Append one event to the contract's chain (scheme 2, chained to whatever
    came before, 078 history included). A VERSION writes the version too."""
    from app.trading_book import record

    def go(c):
        if event_type == "VERSION":
            return _record_version(c, contract_row, terms, sha, actor, company_id)
        v = _version_for(c, contract_row["id"], sha)
        return record.append_event(c, contract_row["id"], event_type, actor, company_id,
                                   version_id=str(v["id"]) if v else None,
                                   terms_hash=v["terms_hash"] if v else None, note=note)
    return _run(go, conn)


def set_counterparty(contract_row: dict, company: str, actor: str, actor_company: Optional[str]) -> None:
    """Register the counterparty and withdraw earlier confirmations — ONE
    transaction (078 used three, so a failure between them could leave a new
    counterparty with the old confirmations standing; Phase 0 §4, gap 4)."""
    from app.trading_book import record

    def go(c):
        c.execute("UPDATE tb_contract SET confirming_company_id = ?, updated_at = now() WHERE id = ?",
                  (company, contract_row["id"]))
        record.append_event(c, contract_row["id"], "COUNTERPARTY_SET", actor, actor_company,
                            note=f"counterparty {company}")
        # A new counterparty has confirmed nothing: earlier confirmations no longer stand.
        record.append_event(c, contract_row["id"], "DISPUTED", actor, actor_company, note="counterparty changed")
    _run(go)


def chain_intact(contract_id: str, evs: Optional[list[dict]] = None) -> bool:
    """Recompute every hash, each by its own scheme (078 for folded events, 2 after):
    a rewritten, removed or reordered event breaks the chain."""
    from app.trading_book import record

    def go(c):
        row = record._row(c, "SELECT contract_ref FROM tb_contract WHERE id = ?", (contract_id,))
        chain = events(contract_id, conn=c) if evs is None else evs
        return row is not None and record.chain_intact_events(row["contract_ref"], chain)
    return _run(go)


def latest_version(contract_id: str, conn=None) -> Optional[dict]:
    versions = [e for e in events(contract_id, conn=conn) if e["event_type"] == "VERSION"]
    return versions[-1] if versions else None


def confirmed_terms(project_id: str) -> dict[str, dict]:
    """kind -> terms of its latest CONFIRMED version (a later DISPUTED withdraws
    it), read from v_engine_contract_terms — the one view the engine reads."""
    from app.trading_book import record

    return _run(lambda c: {r["kind"]: r["terms"] for r in record._rows(
        c, "SELECT kind, terms FROM v_engine_contract_terms WHERE project_id = ?", (project_id,))})


def record_versions(project_id: str, cards: dict, actor: str, company_id: Optional[str], conn=None,
                    card_type: Optional[str] = None) -> list[str]:
    """After a card save: a new VERSION on every contract whose terms changed. With
    `conn`, inside the caller's transaction (the card save, Phase 0 Q9). Since
    Phase 3 the record IS the card store (card_view): `card_type` names the card
    saved, on every VERSION it causes, and a contract whose fields were all
    cleared gets an empty version — never keeps its last."""
    save = json.dumps({"card": card_type, "save": str(uuid.uuid4())}, sort_keys=True) if card_type else None

    def go(c):
        changed = []
        for kind in list(COUNTERPARTY_KINDS) + list(REVIEWER_KINDS):
            if kind == "offtake" and frame_buyers(cards):
                row = contract(project_id, kind, conn=c)
                last = latest_version(row["id"], conn=c)
                sha = frame_hash(*frame_terms(cards))
                if last is None or last["terms_sha256"] != sha:
                    _record_frame_version(c, row, cards, sha, actor, company_id, note=save)
                    changed.append(kind)
                continue
            terms = kind_terms(cards, kind)
            row = contract(project_id, kind, create=bool(terms), conn=c)
            if row is None:
                continue                      # nothing recorded, nothing to record
            last = latest_version(row["id"], conn=c)
            if not terms and last is None:
                continue
            sha = terms_hash(terms)
            if last is None or last["terms_sha256"] != sha:
                _record_version(c, row, terms, sha, actor, company_id, note=save)
                changed.append(kind)
        return changed
    return _run(go, conn)


def kind_gates(kind: str) -> set[str]:
    """The gates ("G4", …) a contract kind's terms serve: its instrument evidence's
    gates, or the reviewer gate for the producer's own plan."""
    from app.core.abac import gate_for_evidence

    if kind in REVIEWER_KINDS:
        return {REVIEWER_KINDS[kind]}
    return {g.split("_", 1)[0] for g in (gate_for_evidence(k) for k in CONTRACT_EVIDENCE.get(kind, ())) if g}


def reviewer_scope(user_id: str, company_id: Optional[str], project_id: str, owner_company_id: str) -> Optional[set[str]]:
    """Phase 0 Q5: an appointed reviewer reads only the contracts of the gates it
    reviews. None = no restriction (the owner, a lender, any other project party)."""
    from app.core.abac import REVIEWER_GATES
    from app.core.projects_store import _rows as admin_rows

    if company_id == owner_company_id:
        return None
    roles = {r["actor_type"] for r in admin_rows(
        "SELECT actor_type FROM auth_user_project_roles WHERE user_id = :u AND project_id = :p",
        {"u": user_id, "p": project_id})}
    gates = [g for role, gs in REVIEWER_GATES.items() if getattr(role, "value", role) in roles for g in gs]
    return set(gates) if gates else None


def is_appointed_reviewer(user_id: str, project_id: str, gate_prefix: str) -> bool:
    from app.core.abac import REVIEWER_GATES
    from app.core.projects_store import _rows as admin_rows

    roles = {r["actor_type"] for r in admin_rows(
        "SELECT actor_type FROM auth_user_project_roles WHERE user_id = :u AND project_id = :p",
        {"u": user_id, "p": project_id})}
    return any(gate_prefix in gates for role, gates in REVIEWER_GATES.items()
               if getattr(role, "value", role) in roles)
