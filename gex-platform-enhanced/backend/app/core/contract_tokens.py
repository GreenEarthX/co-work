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


def engine_terms(cards: dict, confirmed: dict[str, dict]) -> tuple[dict, dict]:
    """(terms the engine may use, fields held back awaiting confirmation).

    `confirmed` maps kind -> {"card.field": value} of its latest CONFIRMED version.
    """
    used: dict[str, dict] = {}
    held: dict[str, list[str]] = {}
    for card, fields in (cards or {}).items():
        for field, value in (fields or {}).items():
            kind = FIELD_KIND.get(card, {}).get(field)
            ok = (kind is not None and f"{card}.{field}" in confirmed.get(kind, {})
                  and confirmed[kind][f"{card}.{field}"] == value)
            if (card, field) in ADVERSE_FACTS and value is True:
                ok = True
            if ok:
                used.setdefault(card, {})[field] = value
            else:
                held.setdefault(kind or "unmapped", []).append(f"{card}.{field}")
    return used, held


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


def _record_version(c, contract_row: dict, terms: dict, sha: str, actor: str, company_id: Optional[str]) -> dict:
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
    ev = record.append_event(c, cid, "VERSION", actor, company_id, version_id=vid, terms_hash=w["terms_hash"])
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


def record_versions(project_id: str, cards: dict, actor: str, company_id: Optional[str], conn=None) -> list[str]:
    """After a card save: a new VERSION on every contract whose terms changed. With
    `conn`, inside the caller's transaction (the card save, Phase 0 Q9)."""
    def go(c):
        changed = []
        for kind in list(COUNTERPARTY_KINDS) + list(REVIEWER_KINDS):
            terms = kind_terms(cards, kind)
            if not terms:
                continue
            row = contract(project_id, kind, conn=c)
            last = latest_version(row["id"], conn=c)
            sha = terms_hash(terms)
            if last is None or last["terms_sha256"] != sha:
                append(row, "VERSION", actor, company_id, terms=terms, sha=sha, conn=c)
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
