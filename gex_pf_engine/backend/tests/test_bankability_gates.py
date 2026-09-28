"""
Bankability gate invariants — evidence rules 4.0.0.

3.0.0 ("the stronger bar", 25 Sept 2026) stopped the engine scoring intentions as
achievements: a draft CP checklist satisfied Financial Close, a commissioning plan
satisfied COD, an EIA submission satisfied Permits, and a letter of intent could
fill any slot whose name said "executed".

4.0.0 (27 Sept 2026) reads every gate through every party's eyes
(docs/GEX-Twelve-Gates-Multi-Party-Review.docx): financing scope per item rather
than per gate, commitment ladders for offtake (O0–O7) and EPC (E0–E6), ten
coherence checks across contracts, post-FID triggers, lenses and an offtaker view.

A failure here means the engine can again say something stronger than its
evidence supports — or weaker than the commitments it holds justify.
"""

from __future__ import annotations

import copy

import pytest

from pf_engine.core import bankability_engine as B

GATE = {g["gate_id"]: g for g in B.GATES}
LIVE = {k for g in B.GATES for k in g["required_evidence"]}

# Instruments that progress over a project's life, at the stage they reach by
# financial close. Their REQUIRED_MATURITY is the floor for their own gate; the
# ladders ask more of them later.
FINAL_MATURITY = {
    "binding_offtake_contract_executed": "EFFECTIVE",
    "epc_contract_fixed_price_or_capped_gmp": "EFFECTIVE",
    "epc_security_package": "EFFECTIVE",
    "long_lead_items_reserved": "EXECUTED",
    "technology_licence_process_guarantee": "EXECUTED",
}

COHERENT_TERMS = {
    "offtake": {
        "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80, "buyer_investment_grade": True,
        "tenor_years": 15, "cps_satisfied": True, "contracted_tonnes_per_year": 40000,
        "first_delivery_date": "2030-06-01", "delay_ld_cap_eur": 20e6,
        "product_spec_standard": "ASTM D7566 Annex A1", "certification_scheme": "ISCC EU",
        "compliance_regime": ["REFUELEU"], "fm_definition_ref": "FM-A", "change_in_law_allocated": True,
    },
    "epc": {
        "contracting_model": "LSTK", "contract_price_eur": 900e6, "guaranteed_completion_date": "2029-12-01",
        "guaranteed_capacity_tonnes_per_year": 50000, "expected_availability_pct": 90,
        "delay_ld_cap_eur": 30e6, "guaranteed_product_spec": "ASTM D7566 Annex A1", "fm_definition_ref": "FM-A",
    },
    "schedule": {
        "permits_expected_date": "2026-06-01", "appeal_period_months": 2, "fid_target_date": "2026-09-01",
        "construction_months_p80": 36, "commissioning_allowance_months": 6,
    },
    "supply": {
        "feedstock_required_tonnes_per_year": 60000, "feedstock_contracted_tonnes_per_year": 60000,
        "feedstock_tenor_years": 15, "power_meets_certification": True, "co2_source_eligible": True,
        "certification_scheme": "ISCC EU", "fm_definition_ref": "FM-A",
    },
    "model": {
        "debt_tenor_years": 12, "model_contracted_tonnes_per_year": 40000,
        "model_offtake_tenor_years": 15, "model_epc_price_eur": 900e6,
    },
}


def _terms(**overrides) -> dict:
    """The coherent cards, with per-card field overrides (None removes a field)."""
    t = copy.deepcopy(COHERENT_TERMS)
    for card, fields in overrides.items():
        if fields is None:
            t.pop(card, None)
            continue
        for k, v in fields.items():
            if v is None:
                t.setdefault(card, {}).pop(k, None)
            else:
                t.setdefault(card, {})[k] = v
    return t


def _all_evidence(maturity_override: dict | None = None,
                  status_override: dict | None = None,
                  drop: set | None = None,
                  final: bool = True) -> list[dict]:
    """Every live item VERIFIED at its required maturity (or its final stage)."""
    maturity_override = maturity_override or {}
    status_override = status_override or {}
    drop = drop or set()
    out = []
    for g in B.GATES:
        for key in g["required_evidence"]:
            if key in drop:
                continue
            default = (FINAL_MATURITY.get(key) if final else None) or B.REQUIRED_MATURITY.get(key)
            out.append({
                "key": key,
                "status": status_override.get(key, "VERIFIED"),
                "maturity": maturity_override.get(key, default),
            })
    return out


def _gate(snapshot: dict, gate_id: str) -> dict:
    return next(g for g in snapshot["gate_evaluations"] if g["gate_id"] == gate_id)


def _evaluate(evidence, **kw):
    kw.setdefault("power_model", "GRID_CONNECTED")
    kw.setdefault("financing_model", "PROJECT_FINANCE")
    kw.setdefault("terms", _terms())
    return B.evaluate("test-project", evidence, **kw)


def _check(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["coherence_checks"] if c["id"] == cid)


# ═══════════════════════════════════════════════════════════════════════════
# The bar is achievable, and states only what can exist
# ═══════════════════════════════════════════════════════════════════════════

def test_a_fully_evidenced_coherent_project_reaches_operational():
    snap = _evaluate(_all_evidence())
    assert snap["current_state"] == "OPERATIONAL", (snap["gates_blocking_next_state"],
                                                    snap["commitments_blocking_next_state"])
    assert all(g["determination"] == "SATISFIED" for g in snap["gate_evaluations"])
    assert (snap["offtake"]["level"], snap["offtake"]["effective"], snap["epc"]["level"]) == ("O7", True, "E6")


# Evidence that cannot exist before a given state, from project-finance practice.
# Declared here rather than in the engine: it is domain knowledge the engine's
# gate placement is being checked AGAINST, not a rule the engine applies.
_EXISTS_ONLY_FROM = {
    "FINANCEABLE": {
        "cp_checklist_completed", "equity_injected", "dsra_funded",
        "security_package_perfected", "insurance_certificates_delivered",
        "all_major_contracts_executed", "legal_opinions_issued",
        "car_ear_bound", "dsu_bi_bound", "liability_bound", "lenders_loss_payee",
    },
    "OPERATIONAL": {
        "cod_certificate", "performance_tests_passed", "operating_permit_effective",
        "mrv_reporting_live", "six_to_twelve_months_stable_ops",
        "certificates_issued", "first_deliveries_accepted",
    },
}


def test_no_gate_requires_evidence_before_the_state_at_which_it_can_exist():
    order = B.STATE_ORDER
    misplaced = []
    for g in B.GATES:
        gate_state = order.index(g["unlocks_state"])
        for earliest, keys in _EXISTS_ONLY_FROM.items():
            for key in set(g["required_evidence"]) & keys:
                if gate_state < order.index(earliest):
                    misplaced.append(f"{key} is required by {g['gate_id']} but cannot exist before {earliest}")
    assert not misplaced, "\n".join(misplaced)


def test_every_snapshot_records_the_rules_version_that_judged_it():
    """T15 — a determination must be reproducible under a named rule set."""
    assert _evaluate([])["rules_version"] == "4.0.0"


def test_every_live_item_has_a_label_an_owner_and_a_route():
    for key in LIVE:
        meta = B.EVIDENCE_META.get(key) or {}
        assert meta.get("label") and meta.get("owner_function") and meta.get("route"), key


# ═══════════════════════════════════════════════════════════════════════════
# Achievement semantics (3.0.0, kept)
# ═══════════════════════════════════════════════════════════════════════════

def test_T1_financial_close_cannot_complete_on_draft_artefacts():
    evidence = _all_evidence(drop=set(GATE["G10_FINANCIAL_CLOSE_CP"]["required_evidence"]))
    evidence += [
        {"key": "cp_checklist_draft", "status": "VERIFIED", "maturity": "AGREED"},
        {"key": "legal_opinions_draft", "status": "VERIFIED", "maturity": "AGREED"},
        {"key": "security_package_structure", "status": "VERIFIED", "maturity": "AGREED"},
    ]
    snap = _evaluate(evidence)
    g10 = _gate(snap, "G10_FINANCIAL_CLOSE_CP")
    assert not g10["is_complete"] and g10["completion_pct"] == 0.0
    assert snap["current_state"] != "FINANCEABLE"


def test_T1_financial_close_cannot_complete_on_canonical_keys_at_draft_maturity():
    draft = {k: "AGREED" for k in GATE["G10_FINANCIAL_CLOSE_CP"]["required_evidence"]}
    g10 = _gate(_evaluate(_all_evidence(maturity_override=draft)), "G10_FINANCIAL_CLOSE_CP")
    assert not g10["is_complete"]
    assert {s["key"] for s in g10["maturity_shortfalls"]} == set(draft)


def test_T2_cod_cannot_complete_on_plans_and_protocols():
    evidence = _all_evidence(drop=set(GATE["G11_COD_STABILIZATION"]["required_evidence"]))
    evidence += [
        {"key": "commissioning_plan", "status": "VERIFIED", "maturity": "EXECUTED"},
        {"key": "handover_documentation_plan", "status": "VERIFIED", "maturity": "EXECUTED"},
    ]
    snap = _evaluate(evidence)
    assert not _gate(snap, "G11_COD_STABILIZATION")["is_complete"]
    assert snap["current_state"] != "OPERATIONAL"


def test_permits_cannot_complete_on_applications():
    evidence = _all_evidence(drop={"eia_permit_granted", "construction_permit_granted"})
    evidence += [
        {"key": "eia_submission", "status": "VERIFIED", "maturity": "INDICATIVE"},
        {"key": "construction_permit_application", "status": "VERIFIED", "maturity": "INDICATIVE"},
    ]
    g9 = _gate(_evaluate(evidence), "G9_PERMITS_SAFE")
    assert not g9["is_complete"]
    assert set(g9["deal_killers_blocked"]) == {"eia_permit_granted", "construction_permit_granted"}


def test_an_audit_engagement_is_not_an_audit():
    evidence = _all_evidence(drop={"model_audit_opinion"})
    evidence.append({"key": "model_audit_engagement", "status": "VERIFIED", "maturity": "EXECUTED"})
    assert not _gate(_evaluate(evidence), "G8_AUDIT_GRADE_MODEL")["is_complete"]


def test_an_ie_appointment_is_not_a_sign_off():
    evidence = _all_evidence(drop={"ie_report_issued"})
    evidence.append({"key": "ie_appointment_letter", "status": "VERIFIED", "maturity": "EXECUTED"})
    assert not _gate(_evaluate(evidence), "G6_IE_SIGNOFF")["is_complete"]


def test_a_broker_mandate_is_not_insurability():
    evidence = _all_evidence(drop={"insurance_term_sheet"})
    evidence.append({"key": "insurance_broker_mandate", "status": "VERIFIED", "maturity": "EXECUTED"})
    assert not _gate(_evaluate(evidence), "G7_INSURANCE_BOUND")["is_complete"]


def test_no_retired_key_is_scored_by_any_gate():
    assert not (set(B.RETIRED_EVIDENCE) & LIVE)
    for old, info in B.RETIRED_EVIDENCE.items():
        assert info["replaced_by"] in LIVE, f"{old} is retired in favour of a key no gate requires"


# ═══════════════════════════════════════════════════════════════════════════
# Maturity is a separate axis from verification (3.0.0, kept)
# ═══════════════════════════════════════════════════════════════════════════

def test_T8_a_verified_letter_of_intent_cannot_satisfy_binding_offtake():
    loi = {"binding_offtake_contract_executed": "INTENT"}
    snap = _evaluate(_all_evidence(maturity_override=loi))
    g4 = _gate(snap, "G4_OFFTAKE_BANKABLE")
    assert not g4["is_complete"]
    assert g4["maturity_shortfalls"] == [{
        "key": "binding_offtake_contract_executed",
        "required_maturity": "EXECUTED",
        "declared_maturity": "INTENT",
        "maturity_status": "BELOW_REQUIRED",
    }]
    assert "binding_offtake_contract_executed" in g4["deal_killers_blocked"]
    assert snap["offtake"]["level"] == "O1"


def test_undeclared_maturity_fails_closed():
    none = {"binding_offtake_contract_executed": None}
    g4 = _gate(_evaluate(_all_evidence(maturity_override=none)), "G4_OFFTAKE_BANKABLE")
    assert not g4["is_complete"]
    detail = next(d for d in g4["evidence_detail"] if d["key"] == "binding_offtake_contract_executed")
    assert detail["maturity_status"] == "NOT_DECLARED"


def test_maturity_meets_fails_closed_on_its_own():
    assert B.maturity_meets(None, "EXECUTED") is False
    assert B.maturity_meets("SIGNED", "EXECUTED") is False
    assert B.maturity_meets("", "INTENT") is False
    assert B.maturity_meets("INDICATIVE", "EXECUTED") is False
    assert B.maturity_meets("EXECUTED", "EXECUTED") is True
    assert B.maturity_meets("EFFECTIVE", "EXECUTED") is True
    assert B.maturity_meets(None, None) is True


def test_an_unrecognised_maturity_value_fails_closed():
    bogus = {"binding_offtake_contract_executed": "SIGNED"}
    assert not _gate(_evaluate(_all_evidence(maturity_override=bogus)), "G4_OFFTAKE_BANKABLE")["is_complete"]


def test_more_mature_than_required_is_accepted():
    ahead = {"oem_warranties": "EXECUTED"}  # AGREED required
    assert _gate(_evaluate(_all_evidence(maturity_override=ahead)), "G5_EPC_RISK_PRICED")["is_complete"]


def test_studies_and_analyses_are_not_subject_to_maturity():
    studies = {k: None for k in LIVE if k not in B.REQUIRED_MATURITY}
    snap = _evaluate(_all_evidence(maturity_override=studies))
    assert snap["current_state"] == "OPERATIONAL"


def test_maturity_does_not_substitute_for_verification():
    unverified = {"binding_offtake_contract_executed": "SUBMITTED"}
    g4 = _gate(_evaluate(_all_evidence(status_override=unverified)), "G4_OFFTAKE_BANKABLE")
    assert not g4["is_complete"]
    assert g4["maturity_shortfalls"] == []


def test_every_maturity_requirement_uses_a_real_level_and_a_live_key():
    for key, level in B.REQUIRED_MATURITY.items():
        assert key in LIVE, f"{key} has a maturity requirement but no gate requires it"
        assert level in B.MATURITY_LEVELS, f"{key} requires unknown level {level}"


def test_downgrading_maturity_regresses_the_project_and_names_the_gate():
    snap = _evaluate(
        _all_evidence(maturity_override={"epc_contract_fixed_price_or_capped_gmp": "INDICATIVE"}),
        previous_state="OPERATIONAL",
    )
    assert snap["current_state"] == "COMMERCIALLY_PLAUSIBLE"
    assert snap["regression"]["trigger_gate"] == "G5_EPC_RISK_PRICED"


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (1) — financing scope per item, not per gate
# ═══════════════════════════════════════════════════════════════════════════

def test_T12_balance_sheet_waives_only_gates_whose_every_item_protects_a_lender():
    assert B.LENDER_ONLY_GATES == {"G6_IE_SIGNOFF", "G8_AUDIT_GRADE_MODEL"}
    snap = _evaluate([], financing_model="BALANCE_SHEET")
    waived = {g["gate_id"] for g in snap["gate_evaluations"] if g["determination"] == "WAIVED"}
    assert waived == B.LENDER_ONLY_GATES
    for gid in waived:
        assert not _gate(snap, gid)["is_complete"], "a waived gate must never read as satisfied"


def test_a_balance_sheet_producer_still_needs_a_customer():
    """2.1.0 waived the whole offtake gate for balance-sheet funding."""
    snap = _evaluate(_all_evidence(drop={"binding_offtake_contract_executed"}), financing_model="BALANCE_SHEET")
    g4 = _gate(snap, "G4_OFFTAKE_BANKABLE")
    assert g4["determination"] == "BLOCKED"
    assert snap["current_state"] == "COMMERCIALLY_PLAUSIBLE"


def test_lender_protection_items_drop_out_for_balance_sheet_with_a_reason():
    g4 = _gate(_evaluate([], financing_model="BALANCE_SHEET"), "G4_OFFTAKE_BANKABLE")
    by_key = {d["key"]: d for d in g4["evidence_detail"]}
    for key in GATE["G4_OFFTAKE_BANKABLE"]["required_evidence"]:
        d = by_key[key]
        if B.EVIDENCE_SCOPE.get(key) == "PROJECT_FINANCE":
            assert (d["applicable"], d["not_applicable_reason"]) == (False, "FINANCING_MODEL"), key
        else:
            assert d["applicable"], key
    assert g4["total_evidence"] == 4


def test_the_same_items_apply_to_project_finance():
    g4 = _gate(_evaluate([]), "G4_OFFTAKE_BANKABLE")
    assert g4["total_evidence"] == len(GATE["G4_OFFTAKE_BANKABLE"]["required_evidence"])


def test_debt_capital_is_out_of_scope_for_a_balance_sheet_project():
    snap = _evaluate(_all_evidence(), financing_model="BALANCE_SHEET")
    cap = {c["capital_type"]: c for c in snap["capital_unlocks"]}
    for ct in ("SENIOR_DEBT_COMMITMENT", "DEBT_DRAWDOWN", "DFI_MEZZ_GUARANTEES"):
        assert cap[ct]["financing_applicable"] is False and cap[ct]["decision_eligible"] is False
    assert cap["PROJECT_EQUITY"]["decision_eligible"] is True


def test_every_scoped_item_is_live():
    assert set(B.EVIDENCE_SCOPE) <= LIVE


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (2) — the offtake ladder
# ═══════════════════════════════════════════════════════════════════════════

_PF_PROTECTIONS = ("assignment_rights", "step_in_rights", "termination_payment_formula")


def _offtake(maturity, card=None, protections=True, model=None):
    ev = {}
    if maturity:
        ev["binding_offtake_contract_executed"] = {"status": "VERIFIED", "maturity": maturity}
    if protections:
        for k in _PF_PROTECTIONS:
            ev[k] = {"status": "VERIFIED"}
    return B.derive_offtake_level(ev, {"offtake": card or {}, "model": model if model is not None else {"debt_tenor_years": 12}})


_FIRM = {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80, "buyer_investment_grade": True,
         "tenor_years": 15, "change_in_law_allocated": True}


@pytest.mark.parametrize("maturity, card, expected", [
    (None, {}, "O0"),
    ("INTENT", {}, "O1"),
    ("INDICATIVE", {}, "O2"),
    ("AGREED", {}, "O2"),
    ("EXECUTED", {"commitment_form": "FRAMEWORK", "longstop_date": "2028-01-01"}, "O3"),
    ("EXECUTED", {"commitment_form": "TAKE_AND_PAY"}, "O3"),                          # conditional, no longstop
    ("EXECUTED", {"commitment_form": "TAKE_AND_PAY", "longstop_date": "2028-01-01"}, "O4"),
    ("EFFECTIVE", {"commitment_form": "TAKE_IF_DELIVERED"}, "O5"),
    ("EXECUTED", {**_FIRM, "take_or_pay_pct": 50, "longstop_date": "2028-01-01"}, "O4"),  # not firm
    ("EXECUTED", {**_FIRM, "buyer_investment_grade": False, "longstop_date": "2028-01-01"}, "O4"),
    ("EXECUTED", {**_FIRM, "change_in_law_allocated": False, "longstop_date": "2028-01-01"}, "O6"),
    ("EXECUTED", {**_FIRM, "longstop_date": "2028-01-01"}, "O7"),
    ("EFFECTIVE", {**_FIRM}, "O7"),
    ("EFFECTIVE", {**_FIRM, "commitment_form": "TAKE_IF_TENDERED", "take_or_pay_pct": None}, "O7"),
])
def test_offtake_ladder(maturity, card, expected):
    card = {k: v for k, v in card.items() if v is not None}
    assert _offtake(maturity, card)["level"] == expected


def test_an_unverified_offtake_is_O0_whatever_the_card_says():
    ev = {"binding_offtake_contract_executed": {"status": "SUBMITTED", "maturity": "EFFECTIVE"}}
    assert B.derive_offtake_level(ev, {"offtake": _FIRM})["level"] == "O0"


def test_O7_needs_the_offtake_tenor_to_cover_the_debt():
    assert _offtake("EFFECTIVE", {**_FIRM, "tenor_years": 10})["level"] == "O6"
    assert _offtake("EFFECTIVE", _FIRM, model={})["level"] == "O6"      # debt tenor unknown
    assert _offtake("EFFECTIVE", _FIRM, protections=False)["level"] == "O6"


def test_a_credit_support_document_makes_a_buyer_creditworthy():
    ev = {"binding_offtake_contract_executed": {"status": "VERIFIED", "maturity": "EFFECTIVE"},
          "credit_support_package": {"status": "VERIFIED", "maturity": "EXECUTED"}}
    card = {**_FIRM, "buyer_investment_grade": False, "change_in_law_allocated": False}
    assert B.derive_offtake_level(ev, {"offtake": card})["level"] == "O6"


def test_G4_needs_O4_a_signed_contract_with_no_terms_is_not_binding_offtake():
    snap = _evaluate(_all_evidence(), terms=_terms(offtake={"commitment_form": None}))
    g4 = _gate(snap, "G4_OFFTAKE_BANKABLE")
    assert g4["items_complete"] and not g4["is_complete"]
    assert g4["determination"] == "BLOCKED"
    assert g4["commitment_checks"][0]["actual"] == "O3"
    assert snap["current_state"] == "COMMERCIALLY_PLAUSIBLE"


def test_structurally_bankable_needs_a_firm_offtake_for_project_finance_only():
    weak = _terms(offtake={"commitment_form": "TAKE_AND_PAY"})  # binding and effective, not firm: O5
    pf = _evaluate(_all_evidence(), terms=weak)
    assert pf["offtake"]["level"] == "O5"
    assert pf["current_state"] == "BUILDABLE"
    assert pf["commitments_blocking_next_state"][0]["required"] == "O6"
    bs = _evaluate(_all_evidence(), terms=weak, financing_model="BALANCE_SHEET")
    assert bs["current_state"] == "OPERATIONAL"


def test_a_firm_offtake_before_close_is_O7_but_financeable_needs_it_effective():
    """Conditions tied to financial close are necessarily open before close."""
    conditional = _terms(offtake={"cps_satisfied": False, "longstop_date": "2031-06-01"})
    evidence = _all_evidence(maturity_override={"binding_offtake_contract_executed": "EXECUTED"})
    snap = _evaluate(evidence, terms=conditional)
    assert (snap["offtake"]["level"], snap["offtake"]["effective"]) == ("O7", False)
    assert snap["current_state"] == "CREDIT_APPROVED"
    kinds = {c["kind"] for c in snap["commitments_blocking_next_state"]}
    assert kinds == {"offtake_effective"}


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (2) — the EPC ladder
# ═══════════════════════════════════════════════════════════════════════════

def _epc(overrides=None, card=None):
    base = {
        "epc_contract_fixed_price_or_capped_gmp": "EFFECTIVE",
        "feed_complete_class3": None,
        "technology_licence_process_guarantee": "EXECUTED",
        "epc_security_package": "EFFECTIVE",
        "liquidated_damages_schedule": None,
        "long_lead_items_reserved": "EXECUTED",
    }
    base.update(overrides or {})
    ev = {k: {"status": "VERIFIED", "maturity": m} for k, m in base.items() if m != "DROP"}
    return B.derive_epc_level(ev, {"epc": card if card is not None else {"contracting_model": "LSTK"}})


@pytest.mark.parametrize("overrides, card, expected", [
    ({k: "DROP" for k in ("epc_contract_fixed_price_or_capped_gmp",)}, {}, "E0"),
    ({"feed_complete_class3": "DROP", "epc_contract_fixed_price_or_capped_gmp": "DROP"}, {"contracting_model": "EPCM"}, "E1"),
    ({"epc_contract_fixed_price_or_capped_gmp": "INTENT"}, {}, "E2"),
    ({"epc_contract_fixed_price_or_capped_gmp": "INDICATIVE"}, None, "E3"),
    ({"epc_security_package": "INDICATIVE"}, None, "E3"),
    ({"epc_contract_fixed_price_or_capped_gmp": "AGREED"}, None, "E4"),
    ({"long_lead_items_reserved": "AGREED"}, None, "E4"),
    ({"epc_security_package": "EXECUTED"}, None, "E5"),
    ({}, None, "E6"),
])
def test_epc_ladder(overrides, card, expected):
    assert _epc(overrides, card)["level"] == expected


def test_an_insolvent_contractor_caps_the_epc_and_regresses_the_project():
    snap = _evaluate(_all_evidence(), terms=_terms(epc={"counterparty_insolvent": True}), previous_state="OPERATIONAL")
    assert snap["epc"]["level"] == "E3"
    g5 = _gate(snap, "G5_EPC_RISK_PRICED")
    assert g5["determination"] == "BLOCKED" and g5["triggers"][0]["id"] == "T3"
    assert snap["current_state"] == "COMMERCIALLY_PLAUSIBLE"
    assert snap["regression"]["trigger_gate"] == "G5_EPC_RISK_PRICED"


def test_financeable_needs_notice_to_proceed():
    evidence = _all_evidence(maturity_override={"epc_contract_fixed_price_or_capped_gmp": "EXECUTED"})
    snap = _evaluate(evidence)
    assert snap["epc"]["level"] == "E5"
    assert snap["current_state"] == "CREDIT_APPROVED"
    assert {c["kind"] for c in snap["commitments_blocking_next_state"]} == {"epc"}


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (3) — coherence checks
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cid, overrides, gate", [
    ("C1", {"offtake": {"first_delivery_date": "2030-01-01"}}, "G4_OFFTAKE_BANKABLE"),   # before completion + 6 m
    ("C2", {"offtake": {"contracted_tonnes_per_year": 50000}}, "G4_OFFTAKE_BANKABLE"),   # > 50 000 × 90 %
    ("C3", {"offtake": {"product_spec_standard": "ISO 6583"}}, "G4_OFFTAKE_BANKABLE"),
    ("C4", {"offtake": {"delay_ld_cap_eur": 45e6}}, "G5_EPC_RISK_PRICED"),               # > 30 m backstop
    ("C5", {"offtake": {"cps_satisfied": False, "longstop_date": "2029-06-01"}}, "G4_OFFTAKE_BANKABLE"),
    ("C6", {"supply": {"feedstock_tenor_years": 8}}, "G4_OFFTAKE_BANKABLE"),
    ("C7", {"supply": {"co2_source_eligible": False}}, "G4_OFFTAKE_BANKABLE"),
    ("C8", {"supply": {"certification_scheme": "ISCC PLUS"}}, "G4_OFFTAKE_BANKABLE"),
    ("C9", {"epc": {"fm_definition_ref": "FM-B"}}, "G10_FINANCIAL_CLOSE_CP"),
    ("C10", {"model": {"model_contracted_tonnes_per_year": 45000}}, "G8_AUDIT_GRADE_MODEL"),
])
def test_a_failed_coherence_check_blocks_its_gate(cid, overrides, gate):
    evidence = _all_evidence()
    if cid == "C5":  # a conditional offtake is EXECUTED, not yet EFFECTIVE
        evidence = _all_evidence(maturity_override={"binding_offtake_contract_executed": "EXECUTED"})
    snap = _evaluate(evidence, terms=_terms(**overrides), previous_state="OPERATIONAL")
    assert _check(snap, cid)["status"] == "FAIL", _check(snap, cid)
    g = _gate(snap, gate)
    assert g["items_complete"] and g["determination"] == "BLOCKED"
    assert any(r.startswith(f"{cid} failed") for r in g["blocked_reasons"])
    assert snap["current_state"] != "OPERATIONAL"
    assert snap["regression"]["trigger_gate"] == gate


def test_a_forecast_slip_past_the_longstop_fails_C5_after_fid():
    evidence = _all_evidence(maturity_override={"binding_offtake_contract_executed": "EXECUTED"})
    terms = _terms(offtake={"cps_satisfied": False, "longstop_date": "2030-12-01"},
                   schedule={"forecast_cod_date": "2030-09-01"})           # + 6 months = 2031-03-01
    assert _check(_evaluate(evidence, terms=terms), "C5")["status"] == "FAIL"
    terms["schedule"]["forecast_cod_date"] = "2030-05-01"
    assert _check(_evaluate(evidence, terms=terms), "C5")["status"] == "PASS"


def test_missing_data_is_not_evaluable_and_never_blocks():
    snap = _evaluate(_all_evidence(), terms=_terms(schedule=None, supply=None))
    status = {c["id"]: c["status"] for c in snap["coherence_checks"]}
    assert status["C1"] == "NOT_EVALUABLE" and status["C6"] == "NOT_EVALUABLE" and status["C9"] == "NOT_EVALUABLE"
    assert "schedule.commissioning_allowance_months" in _check(snap, "C1")["missing"]
    assert snap["current_state"] == "OPERATIONAL"


def test_checks_that_cannot_apply_say_so():
    snap = _evaluate(_all_evidence(), terms=_terms(offtake={"compliance_regime": []}), financing_model="BALANCE_SHEET")
    status = {c["id"]: c["status"] for c in snap["coherence_checks"]}
    assert status["C5"] == "NOT_APPLICABLE"      # offtake effective: no longstop running
    assert status["C7"] == "NOT_APPLICABLE"      # no compliance regime recorded
    assert status["C10"] == "NOT_APPLICABLE"     # no credit-committee model


def test_every_check_is_defined_once_on_a_real_gate_with_real_lenses():
    ids = [c["id"] for c in B.COHERENCE_CHECKS]
    assert ids == [f"C{i}" for i in range(1, 11)]
    for c in B.COHERENCE_CHECKS:
        assert c["gate"] in GATE and c["lenses"] and set(c["lenses"]) <= set(B.LENSES)
    assert len(B.compute_coherence(_terms())) == 10


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (4) — post-FID triggers
# ═══════════════════════════════════════════════════════════════════════════

def test_revoked_power_or_support_terms_block_g1_and_regress_by_name():
    """Atome, Sept 2026: decrees fixing PPA price and term revoked four months after FID."""
    snap = _evaluate(_all_evidence(), terms=_terms(supply={"support_or_ppa_revoked": True}),
                     previous_state="OPERATIONAL")
    assert _gate(snap, "G1_GRID_UTILITIES_REALITY")["determination"] == "BLOCKED"
    assert snap["current_state"] == "SPECULATIVE"
    assert snap["regression"]["trigger_gate"] == "G1_GRID_UTILITIES_REALITY"
    assert "T1" in snap["regression"]["reason"]


def test_suspended_certification_blocks_the_pathway_and_operations():
    snap = _evaluate(_all_evidence(), terms=_terms(supply={"certification_suspended": True}))
    for gid in ("G2_CERTIFICATION_PATH_LOCKED", "G11_COD_STABILIZATION"):
        assert _gate(snap, gid)["determination"] == "BLOCKED"


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (5) — the producer's and offtaker's questions are evidence now
# ═══════════════════════════════════════════════════════════════════════════

def test_technically_plausible_requires_the_technology_itself():
    """Before 4.0.0 this state was reached on land and utilities alone."""
    snap = _evaluate(_all_evidence(drop={"technology_maturity_dossier"}))
    assert snap["current_state"] == "SPECULATIVE"
    assert "technology_maturity_dossier" in _gate(snap, "G1_GRID_UTILITIES_REALITY")["deal_killers_blocked"]


def test_operational_requires_an_issued_certificate():
    snap = _evaluate(_all_evidence(drop={"certificates_issued"}))
    assert snap["current_state"] == "FINANCEABLE"


def test_every_project_carries_an_independent_technical_review():
    """For balance-sheet projects the lenders' engineer (G6) is waived; the review is not."""
    snap = _evaluate(_all_evidence(drop={"independent_technical_review"}), financing_model="BALANCE_SHEET")
    assert not _gate(snap, "G5_EPC_RISK_PRICED")["is_complete"]
    assert snap["current_state"] == "COMMERCIALLY_PLAUSIBLE"


# ═══════════════════════════════════════════════════════════════════════════
# 4.0.0 (6) — lenses, the offtaker view, state labels
# ═══════════════════════════════════════════════════════════════════════════

def test_every_live_item_speaks_to_at_least_one_party():
    assert set(B.EVIDENCE_LENSES) == LIVE
    for key, lenses in B.EVIDENCE_LENSES.items():
        assert lenses and set(lenses) <= set(B.LENSES), key


def test_lens_readouts_are_views_over_the_same_items():
    snap = _evaluate(_all_evidence(drop={"binding_offtake_contract_executed", "feed_complete_class3"}))
    for g in snap["gate_evaluations"]:
        applicable = [d for d in g["evidence_detail"] if d["applicable"]]
        for lens, r in g["lens_readouts"].items():
            mine = [d["key"] for d in applicable if lens in d["lenses"]]
            assert r["applicable"] == len(mine)
            assert r["verified"] + len(r["blocking"]) == r["applicable"]
            assert set(r["blocking"]) <= set(g["blocking_items"])


def test_the_offtaker_sees_the_gates_its_supply_depends_on():
    assert B.PERSONA_GATES["OFFTAKER"] == [
        "G2_CERTIFICATION_PATH_LOCKED", "G4_OFFTAKE_BANKABLE", "G5_EPC_RISK_PRICED",
        "G9_PERMITS_SAFE", "G10_FINANCIAL_CLOSE_CP", "G11_COD_STABILIZATION",
    ]
    view = B.evaluate_for_persona("p", _all_evidence(), "OFFTAKER", terms=_terms(),
                                  power_model="GRID_CONNECTED", financing_model="PROJECT_FINANCE")
    assert [g["gate_id"] for g in view["gate_evaluations"]] == B.PERSONA_GATES["OFFTAKER"]


def test_persona_gates_are_derived_from_each_gates_own_personas():
    for persona, gates in B.PERSONA_GATES.items():
        if persona == "EXECUTIVE":
            assert gates == [g["gate_id"] for g in B.GATES]
        else:
            assert gates == [g["gate_id"] for g in B.GATES if persona in g["personas"]]


def test_every_state_names_the_commitment_it_enables():
    assert set(B.STATE_COMMITMENT_LABELS) == set(B.STATE_ORDER)
    snap = _evaluate(_all_evidence(drop={"binding_offtake_contract_executed"}))
    assert snap["state_label"] == B.STATE_COMMITMENT_LABELS["COMMERCIALLY_PLAUSIBLE"]
    assert snap["next_state_label"] == B.STATE_COMMITMENT_LABELS["BUILDABLE"]


def test_rules_publish_the_ladders_checks_lenses_and_card_fields():
    rules = B.get_rules()
    for key in ("offtake_levels", "epc_levels", "coherence_checks", "lenses", "evidence_scope",
                "commitment_card_fields", "state_commitment_requirements", "regression_triggers"):
        assert rules[key], key
    assert rules["offtake_levels"] == [f"O{i}" for i in range(8)]
    assert rules["epc_levels"] == [f"E{i}" for i in range(7)]


# ═══════════════════════════════════════════════════════════════════════════
# Determinations and capital semantics (3.0.0, kept)
# ═══════════════════════════════════════════════════════════════════════════

def test_a_gate_with_a_blocked_deal_killer_is_blocked_not_incomplete():
    assert _gate(_evaluate([]), "G0_SITE_RIGHTS")["determination"] == "BLOCKED"


def test_every_gate_carries_exactly_one_determination():
    allowed = {"SATISFIED", "BLOCKED", "INCOMPLETE", "WAIVED"}
    for snap in (_evaluate([]), _evaluate(_all_evidence()), _evaluate([], financing_model="BALANCE_SHEET")):
        assert {g["determination"] for g in snap["gate_evaluations"]} <= allowed


def test_T11_capital_output_is_decision_eligibility_not_a_capital_event():
    snap = _evaluate(_all_evidence())
    for cu in snap["capital_unlocks"]:
        assert "decision_eligible" in cu
        assert cu["decision_eligible"] == cu["is_unlocked"]
        assert not {"committed", "drawable", "drawn"} & {k.lower() for k in cu}
    assert "does not commit" in B.get_rules()["capital_semantics"]
