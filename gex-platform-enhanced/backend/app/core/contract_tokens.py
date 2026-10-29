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
"""
from __future__ import annotations

import hashlib
import json
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
        "commissioning_allowance_months", "forecast_cod_date")},
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
CONTRACT_EVIDENCE: dict[str, tuple[str, ...]] = {
    "offtake": ("binding_offtake_contract_executed", "credit_support_package"),
    "ppa": ("ppa_signed_or_term_sheet_evidence",),
    "supply": ("feedstock_supply_agreement",),
    "epc": ("epc_contract_fixed_price_or_capped_gmp", "epc_security_package"),
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


# ── Store (alembic 078), in the caller's tenant ─────────────────────────────

def _conn():
    from app.core.db_backend import domain_connection
    return domain_connection()


def _rows(sql: str, params: tuple) -> list[dict]:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def contract(project_id: str, kind: str, create: bool = True) -> Optional[dict]:
    rows = _rows("SELECT * FROM project_contract WHERE project_id = ? AND kind = ?", (project_id, kind))
    if rows or not create:
        return rows[0] if rows else None
    conn = _conn()
    try:
        conn.execute("INSERT INTO project_contract (project_id, kind) VALUES (?, ?) ON CONFLICT DO NOTHING",
                     (project_id, kind))
        conn.commit()
    finally:
        conn.close()
    return contract(project_id, kind, create=False)


def events(contract_id: int) -> list[dict]:
    rows = _rows("SELECT * FROM project_contract_event WHERE contract_id = ? ORDER BY seq", (contract_id,))
    for r in rows:
        r["at"] = str(r["at"])
        if isinstance(r.get("terms_json"), str):
            r["terms_json"] = json.loads(r["terms_json"])
    return rows


def append(contract_row: dict, event_type: str, actor: str, company_id: Optional[str], *,
           terms: Optional[dict] = None, sha: Optional[str] = None, note: Optional[str] = None) -> dict:
    """Append one event, chained to the previous one by hash."""
    prior = events(contract_row["id"])
    prev_hash = prior[-1]["event_hash"] if prior else None
    seq = (prior[-1]["seq"] + 1) if prior else 1
    body = json.dumps({"contract": contract_row["id"], "seq": seq, "type": event_type, "terms_sha256": sha,
                       "actor": actor, "company": company_id, "note": note, "prev": prev_hash}, sort_keys=True)
    event_hash = hashlib.sha256(body.encode()).hexdigest()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO project_contract_event (contract_id, project_id, seq, event_type, terms_json, terms_sha256, "
            "actor, company_id, note, prev_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (contract_row["id"], contract_row["project_id"], seq, event_type,
             json.dumps(terms) if terms is not None else None, sha, actor, company_id, note, prev_hash, event_hash))
        conn.commit()
    finally:
        conn.close()
    return {"seq": seq, "event_hash": event_hash}


def chain_intact(contract_id: int, evs: Optional[list[dict]] = None) -> bool:
    """Recompute every hash: a rewritten or removed event breaks the chain."""
    prev = None
    for e in (events(contract_id) if evs is None else evs):
        body = json.dumps({"contract": contract_id, "seq": e["seq"], "type": e["event_type"],
                           "terms_sha256": e["terms_sha256"], "actor": e["actor"], "company": e["company_id"],
                           "note": e["note"], "prev": prev}, sort_keys=True)
        if e["prev_hash"] != prev or hashlib.sha256(body.encode()).hexdigest() != e["event_hash"]:
            return False
        prev = e["event_hash"]
    return True


def latest_version(contract_id: int) -> Optional[dict]:
    versions = [e for e in events(contract_id) if e["event_type"] == "VERSION"]
    return versions[-1] if versions else None


def confirmed_terms(project_id: str) -> dict[str, dict]:
    """kind -> terms of its latest CONFIRMED version (a later DISPUTED withdraws it)."""
    out: dict[str, dict] = {}
    for c in _rows("SELECT * FROM project_contract WHERE project_id = ?", (project_id,)):
        evs = events(c["id"])
        versions = {e["terms_sha256"]: e["terms_json"] for e in evs if e["event_type"] == "VERSION"}
        current = None
        for e in evs:
            if e["event_type"] == "CONFIRMED" and e["terms_sha256"] in versions:
                current = versions[e["terms_sha256"]]
            elif e["event_type"] == "DISPUTED":
                current = None
        if current is not None:
            out[c["kind"]] = current
    return out


def record_versions(project_id: str, cards: dict, actor: str, company_id: Optional[str]) -> list[str]:
    """After a card save: a new VERSION on every token whose terms changed."""
    changed = []
    for kind in list(COUNTERPARTY_KINDS) + list(REVIEWER_KINDS):
        terms = kind_terms(cards, kind)
        if not terms:
            continue
        c = contract(project_id, kind)
        last = latest_version(c["id"])
        sha = terms_hash(terms)
        if last is None or last["terms_sha256"] != sha:
            append(c, "VERSION", actor, company_id, terms=terms, sha=sha)
            changed.append(kind)
    return changed


def is_appointed_reviewer(user_id: str, project_id: str, gate_prefix: str) -> bool:
    from app.core.abac import REVIEWER_GATES
    from app.core.projects_store import _rows as admin_rows

    roles = {r["actor_type"] for r in admin_rows(
        "SELECT actor_type FROM auth_user_project_roles WHERE user_id = :u AND project_id = :p",
        {"u": user_id, "p": project_id})}
    return any(gate_prefix in gates for role, gates in REVIEWER_GATES.items()
               if getattr(role, "value", role) in roles)
