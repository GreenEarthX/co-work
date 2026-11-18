"""
Structuring context (app/core/structuring_context.py): gate scores and state
from the gate engine, identity from the project registry, the rest from the
recorded inputs — and nothing from anywhere else. Pure function; no database.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.structuring_context import (
    DERIVED_FIELDS, RECORDED_FIELDS, RETIRED_TYPED_FIELDS, ContextUnavailable, build_context, engine_gate_scores,
    normalise_molecule, public,
)

REFERENCE = json.loads((Path(__file__).resolve().parent / "fixtures/reference_cases/breizh_saf.json").read_text())
ENGINE_IDS = ["G0_SITE_RIGHTS", "G1_GRID_UTILITIES_REALITY", "G2_CERTIFICATION_PATH_LOCKED", "G3_INPUTS_SECURED",
              "G4_OFFTAKE_BANKABLE", "G5_EPC_RISK_PRICED", "G6_IE_SIGNOFF", "G7_INSURANCE_BOUND",
              "G8_AUDIT_GRADE_MODEL", "G9_PERMITS_SAFE", "G10_FINANCIAL_CLOSE_CP", "G11_COD_STABILIZATION"]


def snapshot(completion=None, state="TECHNICALLY_PLAUSIBLE"):
    completion = completion or [0.0] * 12
    return {"current_state": state, "rules_version": "4.8.0", "evaluated_at": "2026-11-16T10:00:00+00:00",
            "gate_evaluations": [{"gate_id": g, "gate_name": g, "completion_pct": c}
                                 for g, c in zip(ENGINE_IDS, completion)]}


IDENTITY = {"project_id": "P_NEW", "country": "de", "molecule": "Green H2", "capex_eur": 180_000_000}
OWN_INPUTS = {"dscr_p50": 1.27, "dscr_p90": 1.12, "llcr": 1.33, "wacc": 0.072, "offtake_coverage_pct": 0.62,
              "cert_readiness": 70, "epc_status": "NOT_STARTED", "insurance_status": "NOT_STARTED",
              "grid_status": "APPLIED"}


def record(payload, state="UNVERIFIED"):
    return {"payload": payload, "verification_state": state}


def test_gate_scores_and_state_are_the_engines():
    ctx = build_context("P_NEW", identity=IDENTITY, snapshot=snapshot([25.0] + [0.0] * 11),
                        evaluated_at=None, record=record(OWN_INPUTS))
    assert ctx["gate_scores"] == {**{f"G{i}": 0.0 for i in range(12)}, "G0": 25.0}
    assert ctx["stage"] == "TECHNICALLY_PLAUSIBLE"
    assert ctx["sources"]["engine"]["rules_version"] == "4.8.0"


def test_identity_comes_from_the_project_record():
    ctx = build_context("P_NEW", identity=IDENTITY, snapshot=snapshot(), evaluated_at=None, record=record(OWN_INPUTS))
    assert (ctx["jurisdiction"], ctx["molecule"], ctx["project_size_eur"]) == ("DE", "H2", 180_000_000)
    eu = build_context("P_NEW", identity={**IDENTITY, "country": "EU"}, snapshot=snapshot(), evaluated_at=None,
                       record=record(OWN_INPUTS))
    assert eu["jurisdiction"] is None and eu["sources"]["registry"]["missing"] == ["jurisdiction"]


def test_a_record_carrying_the_breizh_gate_profile_no_longer_reaches_a_result():
    # proj_bremen_h2 as loaded on 2026-10-25: Breizh's gate scores, state and size in the stored record
    copied = {**OWN_INPUTS, "gate_scores": REFERENCE["gate_scores"], "stage": "BUILDABLE",
              "project_size_eur": REFERENCE["identity"]["capex_eur"], "jurisdiction": "FR", "molecule": "SAF"}
    ctx = build_context("proj_bremen_h2", identity=IDENTITY, snapshot=snapshot(), evaluated_at=None,
                        record=record(copied))
    assert ctx["gate_scores"] != REFERENCE["gate_scores"]
    assert ctx["stage"] != "BUILDABLE" and ctx["project_size_eur"] != REFERENCE["identity"]["capex_eur"]
    # 2026-11-17 (task 2): the typed grid/certification/EPC/insurance status and the typed
    # LLCR are ignored too; they come from engine evidence and the PF engine.
    assert ctx["sources"]["recorded"]["ignored"] == sorted(DERIVED_FIELDS + RETIRED_TYPED_FIELDS)


def test_a_new_project_receives_nothing_it_was_not_given():
    """Every value in the context is traceable to the engine, the registry or the record."""
    snap = snapshot([10.0, 20.0] + [0.0] * 10, state="TECHNICALLY_PLAUSIBLE")
    ctx = build_context("P_NEW", identity=IDENTITY, snapshot=snap, evaluated_at="t", record=record(OWN_INPUTS))
    expected = {"gate_scores": engine_gate_scores(snap), "stage": "TECHNICALLY_PLAUSIBLE", "jurisdiction": "DE",
                "molecule": "H2", "project_size_eur": 180_000_000,
                **{k: OWN_INPUTS[k] for k in RECORDED_FIELDS}, "llcr": None, "readiness": None}
    assert {k: v for k, v in public(ctx).items() if k != "sources"} == expected
    breizh_points = {**REFERENCE["structuring_inputs"], "gate_scores": REFERENCE["gate_scores"],
                     "project_size_eur": REFERENCE["identity"]["capex_eur"]}
    assert not [k for k, v in breizh_points.items() if ctx.get(k) == v]


@pytest.mark.parametrize("kwargs, status, code", [
    (dict(identity=None, snapshot=snapshot(), record=record(OWN_INPUTS)), 404, "PROJECT_NOT_FOUND"),
    (dict(identity=IDENTITY, snapshot=None, record=record(OWN_INPUTS)), 409, "NOT_EVALUATED_BY_GATE_ENGINE"),
    (dict(identity=IDENTITY, snapshot={"current_state": None, "gate_evaluations": []}, record=record(OWN_INPUTS)),
     409, "NOT_EVALUATED_BY_GATE_ENGINE"),
    (dict(identity=IDENTITY, snapshot=snapshot(), record=None), 404, "STRUCTURING_INPUTS_NOT_RECORDED"),
])
def test_a_missing_source_is_refused_not_filled(kwargs, status, code):
    with pytest.raises(ContextUnavailable) as e:
        build_context("P_NEW", evaluated_at=None, **kwargs)
    assert (e.value.status, e.value.code) == (status, code)


def test_incomplete_inputs_are_named_and_not_a_refusal():
    """Rule (JML 2026-11-17): a missing required input makes its decision test "not
    assessable"; it never blocks the calculation. It is named in the sources."""
    partial = {k: v for k, v in OWN_INPUTS.items() if k not in ("wacc", "grid_status")}
    ctx = build_context("P_NEW", identity=IDENTITY, snapshot=snapshot(), evaluated_at=None, record=record(partial))
    assert ctx["wacc"] is None and ctx["sources"]["recorded"]["missing"] == ["wacc"]
    assert set(RECORDED_FIELDS) >= set(ctx["sources"]["recorded"]["missing"])


@pytest.mark.parametrize("raw, expected", [("e-NG", "E_NG"), ("e-Methanol", "E_METHANOL"), ("e-NH3", "NH3"),
                                           ("SAF", "SAF"), ("Green H2", "H2"), (None, None)])
def test_molecules_are_put_in_the_instrument_registrys_terms(raw, expected):
    assert normalise_molecule(raw) == expected
