"""
Gaps, packages and decision tests (handoff v4, tasks 2-4 and 6; Part C tests 3, 4, 6-9).

Pure: no database, no engine. Policies are passed in as the registry would resolve
them, so every outcome is checked without depending on which rows the dev
registry happens to hold.
"""
from __future__ import annotations

import pytest

from app.core import decision_policy as dp
from app.core.structuring_engine import GAP_MAPPING, conditional_outcome, get_structuring_engine

G4 = "G4_OFFTAKE_BANKABLE"


def _gate(gid, determination, items, reasons=()):
    return {"gate_id": gid, "gate_name": gid.split("_", 1)[1].replace("_", " ").title(),
            "determination": determination, "blocking_items": [k for k, _ in items if _ != "VERIFIED"],
            "blocked_reasons": list(reasons),
            "evidence_detail": [{"key": k, "label": f"Label {k}", "status": s, "severity": "deal_killer",
                                 "applicable": True} for k, s in items]}


def _snapshot(g4_items, state="TECHNICALLY_PLAUSIBLE"):
    det = "SATISFIED" if all(s == "VERIFIED" for _, s in g4_items) else "INCOMPLETE"
    return {"current_state": state, "next_state": "COMMERCIALLY_PLAUSIBLE",
            "gate_evaluations": [_gate(G4, det, g4_items),
                                 _gate("G0_SITE_RIGHTS", "INCOMPLETE", [("lease", "NOT_STARTED")])]}


def _ctx(snapshot, **metrics):
    return {"_snapshot": snapshot, "jurisdiction": "DE", "molecule": "H2", "stage": snapshot["current_state"],
            "rules": {"state_requirements": {"COMMERCIALLY_PLAUSIBLE": [G4]}}, **metrics}


def _approved(value, party="GEX", status=dp.GEX_DEFAULT):
    return {"approved": {"value": value, "status": status, "policy_party": party,
                         "effective_date": "2026-11-20", "ref_id": "r1"}, "proposed": []}


_REAL_EVALUATE = dp.evaluate
PROPOSED_ONLY = {"approved": None, "proposed": [{"value": 1.30, "status": dp.GEX_PROPOSED, "policy_party": "GEX"}]}


# ── Test 3: no manufactured readiness ────────────────────────────────────────

def test_a_package_never_changes_the_state_and_its_after_figures_are_estimates():
    """Rule (test 3, task 4): selecting a package changes no state, closes no gap and
    passes no decision test. The next state is conditional and its after-figures are ESTIMATES."""
    snap = _snapshot([("hot", "SUBMITTED"), ("spa", "NOT_STARTED")])
    rec = get_structuring_engine().recommend("P1", _ctx(snap, wacc=0.09, dscr_p50=1.2, dscr_p90=1.1), {})
    pkg = rec.package
    assert pkg.current_state == "TECHNICALLY_PLAUSIBLE" == rec.before_metrics["state"]
    assert pkg.conditional_outcome["label"] == "conditional — not achieved"
    assert pkg.conditional_outcome["would_follow"] == "COMMERCIALLY_PLAUSIBLE"
    assert [g["gate_id"] for g in pkg.conditional_outcome["gates"]] == [G4]
    assert set(pkg.gaps_remaining) == {g.gap_id for g in rec.gaps}           # nothing closed
    for k in ("wacc_pct", "dscr_p50", "dscr_p90"):
        assert pkg.estimates[k]["basis"] == "ESTIMATE"
    assert pkg.estimates["llcr"]["basis"] == "UNAVAILABLE" and pkg.estimates["llcr"]["value"] is None
    assert "never changes a state" in pkg.estimates["method"]
    assert not any(hasattr(pkg, a) for a in ("after_state", "state_after", "achieved_state"))


def test_no_state_map_promotion_remains_in_the_structuring_engine():
    import inspect
    from app.core import structuring_engine
    src = inspect.getsource(structuring_engine)
    assert "state_map" not in src


def test_conditional_outcome_without_a_snapshot_is_not_evaluated():
    out = conditional_outcome({})
    assert out["status"] == "NOT_EVALUATED" and out["gates"] == []


# ── Test 4: gaps follow requirements ─────────────────────────────────────────

def test_a_g4_gap_closes_only_when_its_requirement_is_verified_and_the_gate_stays_incomplete():
    """Rule (test 4, task 2): verifying one G4 requirement closes that gap only; G4
    stays incomplete until all its applicable requirements are verified."""
    eng = get_structuring_engine()
    before = [g for g in eng.analyze_gaps("P1", _ctx(_snapshot([("hot", "SUBMITTED"), ("spa", "NOT_STARTED")])), {})
              if g.gate_id == G4]
    assert {g.requirement_key for g in before} == {"hot", "spa"} and all(g.kind == "REQUIREMENT" for g in before)
    assert before[0].gate_remaining_requirements == ["Label hot", "Label spa"]

    snap = _snapshot([("hot", "VERIFIED"), ("spa", "NOT_STARTED")])
    after = [g for g in eng.analyze_gaps("P1", _ctx(snap), {}) if g.gate_id == G4]
    assert [g.requirement_key for g in after] == ["spa"]
    assert snap["gate_evaluations"][0]["determination"] == "INCOMPLETE"
    assert after[0].gate_remaining_requirements == ["Label spa"]

    done = [g for g in eng.analyze_gaps("P1", _ctx(_snapshot([("hot", "VERIFIED"), ("spa", "VERIFIED")])), {})
            if g.gate_id == G4]
    assert done == []


def test_gaps_come_only_from_the_mapped_gates_and_no_typed_status_remains():
    from app.core import structuring_context as sc
    eng = get_structuring_engine()
    gaps = eng.analyze_gaps("P1", _ctx(_snapshot([("hot", "SUBMITTED")]),
                                       cert_readiness="LOCKED", epc_status="SIGNED"), {})
    assert {g.gate_id for g in gaps if g.kind == "REQUIREMENT"} == {G4}      # G0 is not mapped
    assert set(GAP_MAPPING["requirements"]) == {"G1_GRID_UTILITIES_REALITY", "G2_CERTIFICATION_PATH_LOCKED",
                                                G4, "G5_EPC_RISK_PRICED", "G7_INSURANCE_BOUND"}
    assert set(sc.RETIRED_TYPED_FIELDS) >= {"cert_readiness", "epc_status", "insurance_status", "grid_status"}
    assert not set(sc.RECORDED_FIELDS) & set(sc.RETIRED_TYPED_FIELDS)


def test_metric_gaps_are_decision_tests_feeding_capital_decisions_not_gates():
    """Rule (task 3): WACC and DSCR map to decision tests and capital decisions, never to a gate."""
    gaps = get_structuring_engine().analyze_gaps("P1", _ctx(_snapshot([("hot", "VERIFIED")]),
                                                            wacc=0.12, dscr_p50=1.1, dscr_p90=1.0), {})
    tests = {g.gap_id: g for g in gaps if g.kind == "DECISION_TEST"}
    assert {"GAP_TEST_WACC", "GAP_TEST_DSCR_P50", "GAP_TEST_DSCR_P90"} <= set(tests)
    for g in tests.values():
        assert g.affected_gates == [] and g.capital_decisions
    assert tests["GAP_TEST_DSCR_P50"].capital_decisions == ["SENIOR_DEBT_COMMITMENT"]
    assert "PROJECT_EQUITY" in tests["GAP_TEST_WACC"].capital_decisions


# ── Tests 6-8: policy ────────────────────────────────────────────────────────

def test_a_missing_input_is_not_assessable_never_a_pass_or_a_breach():
    """Rule (test 6): a missing required input gives 'not assessable', whatever the policy."""
    r = dp.evaluate("DSCR_P50", None, policy=_approved(1.30))
    assert r["outcome"] == dp.NOT_ASSESSABLE and r["message"] == "not assessable — required inputs missing"


def test_a_proposed_value_judges_nothing_and_the_calculation_is_still_shown():
    """Rule (test 7): without an approved value the metric is shown, no pass/fail."""
    r = dp.evaluate("DSCR_P50", 1.05, policy=PROPOSED_ONLY)
    assert r["outcome"] == dp.NO_THRESHOLD and r["value"] == 1.05
    assert r["message"] == "no approved threshold — no pass/fail"
    assert r["proposed_values"][0]["status"] == dp.GEX_PROPOSED


@pytest.mark.parametrize("value,comparator_test,outcome", [
    (1.35, "DSCR_P50", dp.PASS), (1.29, "DSCR_P50", dp.FAIL), (1.30, "DSCR_P50", dp.PASS),
])
def test_an_approved_floor_judges_and_names_its_party_status_and_date(value, comparator_test, outcome):
    """Rule (test 8): a judgement names whose policy it applies, its status and effective date."""
    r = dp.evaluate(comparator_test, value, policy=_approved(1.30, party="KFW", status=dp.INSTITUTION))
    assert r["outcome"] == outcome
    assert "KFW" in r["message"] and dp.INSTITUTION in r["message"] and "2026-11-20" in r["message"]


def test_a_ceiling_test_passes_at_or_below():
    assert dp.evaluate("WACC", 0.08, policy=_approved(0.08))["outcome"] == dp.PASS
    assert dp.evaluate("WACC", 0.081, policy=_approved(0.08))["outcome"] == dp.FAIL


def test_status_wording_never_lets_a_gex_approval_stand_in_for_an_institution():
    """Rule: JML's approval establishes a GEX default; an institution's value counts
    as its policy only with a reference; a proposed value is 'GEX proposed'."""
    assert dp._status({"state": "proposed", "policy_party": "KFW"}) == dp.GEX_PROPOSED
    assert dp._status({"state": "approved", "policy_party": "GEX"}) == dp.GEX_DEFAULT
    assert dp._status({"state": "approved", "policy_party": "KFW", "policy_reference": "KfW letter"}) == dp.INSTITUTION
    assert dp._status({"state": "approved", "policy_party": "KFW"}) is None


def test_an_institution_value_without_a_reference_is_never_the_approved_policy(monkeypatch):
    rows = [{"ref_id": "a", "parameter_key": "dfi_irr_hurdle", "state": "approved", "policy_party": "KFW",
             "policy_reference": None, "value_base": 0.08, "valid_from": "2026-01-01"}]
    monkeypatch.setattr(dp, "_rows", lambda conn, key: rows)
    import app.core.reference_registry as rr
    monkeypatch.setattr(rr, "registry_available", lambda: True)
    assert dp.resolve("dfi_irr_hurdle", party="KFW", conn=object())["approved"] is None


# ── The DSCR deal killer is a decision test ──────────────────────────────────

def _killer(monkeypatch, policy, dscr):
    from app.core import deal_killers as dk
    monkeypatch.setattr(dp, "evaluate", lambda t, v, **kw: _REAL_EVALUATE(t, v, policy=policy))
    data = {} if dscr is None else {"dscr_p90": dscr}
    return next(k for k in dk.deal_killer_engine.evaluate(data) if k.id == "DK_DSCR_BELOW_FLOOR")


def test_the_dscr_killer_fires_only_below_an_approved_floor(monkeypatch):
    from app.core.deal_killers import KillerStatus
    assert _killer(monkeypatch, _approved(1.10), None).current_status == KillerStatus.NOT_ASSESSABLE
    assert _killer(monkeypatch, PROPOSED_ONLY, 0.9).current_status == KillerStatus.NO_APPROVED_THRESHOLD
    assert _killer(monkeypatch, _approved(1.10), 1.05).current_status == KillerStatus.ACTIVE
    assert _killer(monkeypatch, _approved(1.10), 1.20).current_status == KillerStatus.RESOLVED


def test_an_unjudged_killer_never_lets_a_committee_be_ready(monkeypatch):
    from app.core import deal_killers as dk
    monkeypatch.setattr(dp, "evaluate", lambda t, v, **kw: _REAL_EVALUATE(t, v, policy=PROPOSED_ONLY))
    clean = {"offtake_binding_pct": 100, "epc_contract_executed": True, "ie_appointed": True,
             "financial_model_status": "AUDIT_GRADE", "insurance_fully_placed": True,
             "rfnbo_pathway_viable": True, "grid_connection_firm": True, "dscr_p90": 1.5,
             "third_party_binding_offtake_pct": 100}
    out = dk.deal_killer_engine.committee_ready(clean)
    assert out["status"] == "CONDITIONAL" and any("DK_DSCR_BELOW_FLOOR" in c for c in out["conditions"])


def test_the_dscr_killer_text_quotes_no_floor():
    from app.core.deal_killers import DEAL_KILLERS_BY_ID
    k = DEAL_KILLERS_BY_ID["DK_DSCR_BELOW_FLOOR"]
    text = " ".join(str(getattr(k, a, "")) for a in ("plain_language", "resolution_action", "description"))
    assert "1.10" not in text and "1.25" not in text


# ── Test 9: additionality is evidenced criteria, not an IRR comparison ───────

def _inp(**kw):
    from app.api.v1.additionality import AdditionalityInput
    return AdditionalityInput(project_id="P1", dfi_institution="KFW", tranche_amount_eur=1e7,
                              total_capex_eur=1e8, assessed_by="u1", **kw)


def test_an_irr_gap_alone_never_establishes_additionality(monkeypatch):
    """Rule (test 9): without evidence on availability, risk mitigation and mobilisation
    the result is NOT_ASSESSABLE, however the IRRs compare."""
    from app.api.v1.additionality import AdditionalityStatus, _compute_additionality
    monkeypatch.setattr(dp, "resolve", lambda *a, **kw: _approved(0.10, party="KFW", status=dp.INSTITUTION))
    r = _compute_additionality(_inp(), {"irr_with_dfi": 0.12, "irr_without_dfi": 0.04})
    assert r.additionality_status == AdditionalityStatus.NOT_ASSESSABLE
    assert "IRR comparison alone does not establish" in r.message
    assert r.g10_pre_condition_met is False


def test_evidenced_criteria_are_evidence_for_the_dfi_decision_not_the_decision(monkeypatch):
    from app.api.v1.additionality import AdditionalityStatus, _compute_additionality
    monkeypatch.setattr(dp, "resolve", lambda *a, **kw: {"approved": None, "proposed": []})
    ev = {"statement": "s", "evidence": [{"reference": "term sheet A"}]}
    r = _compute_additionality(_inp(financing_unavailable=ev, risk_mitigation=ev,
                                    mobilisation={**ev, "commercial_eur": 4e7, "dfi_eur": 1e7}), {})
    assert r.additionality_status == AdditionalityStatus.EVIDENCED and r.g10_pre_condition_met is False
    cat = next(t for t in r.decision_tests if t["test"] == "DFI_CATALYTIC")
    assert cat["value"] == 4.0 and cat["outcome"] == dp.NO_THRESHOLD


def test_the_caller_cannot_type_an_irr():
    from app.api.v1.additionality import AdditionalityInput
    for f in ("irr_with_dfi", "irr_without_dfi", "commercial_hurdle_rate"):
        assert f not in AdditionalityInput.model_fields
    import app.api.v1.additionality as a
    assert not hasattr(a, "DFI_HURDLE_RATES") and not hasattr(a, "DFI_CATALYTIC_MINIMUMS")
