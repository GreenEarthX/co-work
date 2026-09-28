"""
The two gate registries must agree.

There are two gate definitions in this system:

  RUNTIME   ../gex_pf_engine/backend/pf_engine/core/bankability_engine.py
            GATES — the engine on :8001. This is what scores projects, sets
            bankability state and unlocks capital.

  REGISTRY  app/core/bankability_engine.py
            GATE_REGISTRY — served by /api/v1/gates/registry, consumed by the
            frontend, and imported by app/core/abac.py to resolve an incoming
            evidence_key to its gate.

On 2026-09-25 they had drifted until only 2 of 12 gate ids matched
(G0_SITE_RIGHTS, G6_IE_SIGNOFF), 1 of 12 names, and the two "owners" fields
drew from disjoint vocabularies — the runtime naming platform personas
(PRODUCER/FINANCE/REGULATOR/EXECUTIVE) and the registry naming organisational
functions (PROJECT/LEGAL/ENGINEERING/...). They also disagreed on what each gate
unlocks: 8 of 12 on capital, 7 of 12 on state.

Nothing detected it because nothing compared them, and no document stated the
gate model for them to contradict. This test is that comparison.

The evidence bar is now asserted too. Until rules 3.0.0 the registry declared 69
keys (demanding executed/bound/funded artefacts) and the runtime scored 49
(accepting drafts and term sheets of the same objects), overlapping on 20 — one
gate id hiding two diligence standards. On 2026-09-25 the stronger bar was
adopted as a product decision and ONE canonical set of 77 items was built from
both, gate by gate. Neither side was adopted verbatim: the registry had dropped
additionality from G2, accepted a "strategy" for G3, had no audit in G8, no
legal opinions in G10, and required insurance BOUND with lenders as loss payee
at G7, two states before lenders exist. The two copies must now be identical in
evidence, maturity requirements and retirement history (Ambition Gap standard,
acceptance test T14: "CI fails on drift").

Skips when the sibling repo is absent — the platform must remain testable alone.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.core import bankability_engine as registry_module
from app.core.bankability_engine import EVIDENCE_GATE_MAP, GATE_REGISTRY

_RUNTIME = (
    Path(__file__).resolve().parents[3]
    / "gex_pf_engine" / "backend" / "pf_engine" / "core" / "bankability_engine.py"
)


def _runtime():
    """Load the sibling engine by path, without importing its package.

    Both repos once shipped a top-level package called `app`; whichever imported
    first won and the other's submodules became unreachable. The sibling was
    renamed to `pf_engine` in September 2026 to end that. Loading by file path
    keeps this test clear of the question entirely.
    """
    if not _RUNTIME.exists():
        pytest.skip(f"sibling PF engine not checked out at {_RUNTIME}")
    spec = importlib.util.spec_from_file_location("_rt_bankability", _RUNTIME)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_rt_bankability"] = mod
    spec.loader.exec_module(mod)
    return mod


def _runtime_gates() -> list[dict]:
    return _runtime().GATES


def test_one_gate_id_means_one_evidence_bar():
    """
    T14. Before rules 3.0.0 the same gate id carried 49 items in one copy and 69
    in the other, overlapping on 20, so which diligence standard a reader got
    depended on which code path they assumed.
    """
    registry = {g.id: g for g in GATE_REGISTRY}
    drift = []
    for g in _runtime_gates():
        r = registry[g["gate_id"]]
        if list(g["required_evidence"]) != list(r.required_evidence):
            only_rt = sorted(set(g["required_evidence"]) - set(r.required_evidence))
            only_reg = sorted(set(r.required_evidence) - set(g["required_evidence"]))
            drift.append(f"{g['gate_id']}: runtime-only {only_rt}, registry-only {only_reg}"
                         + (" (same keys, different order)" if not (only_rt or only_reg) else ""))
    assert not drift, "evidence bars have diverged:\n  " + "\n  ".join(drift)


def test_both_registries_give_every_gate_the_same_name():
    """A gate name is a claim to the reader; two names are two claims."""
    registry = {g.id: g.name for g in GATE_REGISTRY}
    drift = [f"{g['gate_id']}: {g['gate_name']!r} != {registry[g['gate_id']]!r}"
             for g in _runtime_gates() if g["gate_name"] != registry[g["gate_id"]]]
    assert not drift, "gate names have diverged:\n  " + "\n  ".join(drift)


def test_both_registries_require_the_same_maturity_for_every_instrument():
    rt = _runtime()
    assert rt.MATURITY_LEVELS == registry_module.MATURITY_LEVELS
    assert rt.REQUIRED_MATURITY == registry_module.REQUIRED_MATURITY, (
        "maturity requirements have diverged: "
        f"{set(rt.REQUIRED_MATURITY.items()) ^ set(registry_module.REQUIRED_MATURITY.items())}"
    )


def test_both_registries_carry_the_same_retirement_history():
    """A retired key must mean the same thing, and point at the same replacement, everywhere."""
    assert _runtime().RETIRED_EVIDENCE == registry_module.RETIRED_EVIDENCE


def test_both_registries_name_the_same_owner_function_for_every_item():
    """Evidence requests are assigned by owner function; a divergent copy would
    send a document to the wrong person without anyone noticing."""
    rt = _runtime()
    runtime_owner = {k: rt.EVIDENCE_META[k]["owner_function"]
                     for g in rt.GATES for k in g["required_evidence"]}
    assert runtime_owner == registry_module.EVIDENCE_OWNER_FUNCTION, (
        "owner functions have diverged: "
        f"{set(runtime_owner.items()) ^ set(registry_module.EVIDENCE_OWNER_FUNCTION.items())}"
    )
    unmapped = set(runtime_owner.values()) - set(registry_module.OWNER_FUNCTION_TO_BUSINESS_FUNCTION)
    assert not unmapped, f"owner functions with no account routing: {unmapped}"


def test_both_registries_scope_the_same_items_to_project_finance():
    """Rules 4.0.0: financing scope is per item. The platform uses it to decide
    which requests a balance-sheet project is never asked for; the engine uses
    it to score. A divergent copy would raise a request the engine ignores, or
    hide one it requires."""
    rt = _runtime()
    assert rt.EVIDENCE_SCOPE == registry_module.EVIDENCE_SCOPE, (
        f"scope drift: {set(rt.EVIDENCE_SCOPE.items()) ^ set(registry_module.EVIDENCE_SCOPE.items())}"
    )
    assert set(rt.LENDER_ONLY_GATES) == set(registry_module.LENDER_ONLY_GATES)


def test_both_registries_scope_the_same_items_to_each_power_model():
    """The platform decides from this which requests may be raised, assigned and
    committed to. Without it, the 2026-09-26 conversion asked a grid-connected
    plant's engineer for behind-the-meter generation evidence."""
    rt = _runtime()
    scored = [k for g in rt.GATES for k in g["required_evidence"]]
    runtime = {k: list(rt.EVIDENCE_META[k]["applies_to"]) for k in scored
               if "ALL" not in rt.EVIDENCE_META[k]["applies_to"]}
    assert runtime == registry_module.EVIDENCE_POWER_MODELS


def test_the_platform_says_an_item_does_not_apply_exactly_when_the_engine_does():
    """Every scored item under every premise, including undeclared ones."""
    rt = _runtime()
    drift = []
    for key in (k for g in rt.GATES for k in g["required_evidence"]):
        for power in (None, "OFF_GRID_BTM", "GRID_CONNECTED", "HYBRID"):
            for financing in (None, "PROJECT_FINANCE", "BALANCE_SHEET"):
                fits_power = rt._evidence_applies(key, power)
                fits_financing = rt._item_applies_financing(key, financing)
                engine = None if fits_power and fits_financing else (
                    "POWER_MODEL" if not fits_power else "FINANCING_MODEL")
                platform = registry_module.inapplicability(key, power, financing)
                if engine != platform:
                    drift.append(f"{key} {power}/{financing}: engine {engine}, platform {platform}")
    assert not drift, "applicability has diverged:\n  " + "\n  ".join(drift[:20])


def test_both_registries_give_each_persona_the_same_gates():
    """PERSONA_GATES is derived from gate personas on both sides; this pins it,
    including the OFFTAKER view added in 4.0.0."""
    rt = _runtime()
    registry = {p.value: gates for p, gates in registry_module.PERSONA_GATES.items()}
    for persona, gates in rt.PERSONA_GATES.items():
        if persona == "EXECUTIVE":
            continue  # runtime lists all gates; the registry keeps "empty = all"
        assert gates == registry.get(persona), f"{persona}: runtime {gates} != registry {registry.get(persona)}"
    assert "OFFTAKER" in registry


def test_both_registries_define_the_same_commitment_cards():
    """The platform validates card writes against this spec; the engine reads the
    cards. A field one side knows and the other does not is silently dropped or
    silently ignored."""
    rt = _runtime()
    assert rt.COMMITMENT_CARD_FIELDS == registry_module.COMMITMENT_CARD_FIELDS
    assert set(registry_module.TERMS_CARD_GATE) == set(rt.COMMITMENT_CARD_FIELDS)
    for card, gate in registry_module.TERMS_CARD_GATE.items():
        assert gate in {g["gate_id"] for g in _runtime_gates()}, card


def test_a_retired_key_still_resolves_to_a_gate_for_authorization():
    """
    A stale client submitting eia_submission should be told it was replaced by
    eia_permit_granted, not be refused with "write to gate None" by R5 before
    the handler can explain.
    """
    unresolved = sorted(k for k in registry_module.RETIRED_EVIDENCE if k not in EVIDENCE_GATE_MAP)
    assert not unresolved, f"retired keys R5 would refuse unexplained: {unresolved}"


def test_the_two_registries_declare_the_same_twelve_gate_ids():
    runtime = [g["gate_id"] for g in _runtime_gates()]
    registry = [g.id for g in GATE_REGISTRY]
    assert runtime == registry, (
        "gate ids have drifted apart again.\n"
        f"  runtime : {runtime}\n"
        f"  registry: {registry}"
    )


def test_both_registries_carry_both_ownership_axes_with_identical_values():
    """
    `owners` meant different things in each file, which is how they disagreed on
    every gate while both looking correct. The axes are now named:
      personas              — who SEES the gate (platform visibility)
      accountable_functions — who DOES the work (organisational function)
    """
    registry = {g.id: g for g in GATE_REGISTRY}
    mismatches = []
    for g in _runtime_gates():
        r = registry[g["gate_id"]]
        if list(g["personas"]) != list(r.personas):
            mismatches.append(f"{g['gate_id']} personas: {g['personas']} != {r.personas}")
        if list(g["accountable_functions"]) != list(r.accountable_functions):
            mismatches.append(
                f"{g['gate_id']} accountable_functions: "
                f"{g['accountable_functions']} != {r.accountable_functions}"
            )
    assert not mismatches, "ownership has drifted:\n  " + "\n  ".join(mismatches)


def test_the_registry_does_not_promise_capital_the_engine_will_not_unlock():
    """The registry is served to the frontend; the engine is what actually grants."""
    registry = {g.id: g for g in GATE_REGISTRY}
    mismatches = []
    for g in _runtime_gates():
        r = registry[g["gate_id"]]
        declared = [c.value for c in r.unlocks_capital]
        if list(g["unlocks_capital"]) != declared:
            mismatches.append(f"{g['gate_id']}: engine {g['unlocks_capital']} != registry {declared}")
        engine_state = g.get("unlocks_state")
        reg_state = r.unlocks_state.value if r.unlocks_state else None
        if engine_state != reg_state:
            mismatches.append(f"{g['gate_id']} state: engine {engine_state} != registry {reg_state}")
    assert not mismatches, "capital/state claims have drifted:\n  " + "\n  ".join(mismatches)


def test_every_evidence_key_the_engine_scores_resolves_to_a_gate():
    """
    abac_middleware resolves an evidence write to a gate via this map, and notes
    that an unresolved key leaves gate_id None, at which point R5 "denies EVERY
    actor". An unmapped key is therefore an unwritable one.
    """
    unmapped = sorted(
        ek
        for g in _runtime_gates()
        for ek in g["required_evidence"]
        if ek not in EVIDENCE_GATE_MAP
    )
    assert not unmapped, (
        f"{len(unmapped)} evidence keys the engine scores cannot be authorised "
        f"for write: {unmapped}"
    )


def test_a_shared_evidence_key_resolves_to_the_gate_that_scores_it():
    """
    Where both vocabularies claim the same key, the runtime assignment must win —
    that is where the item is actually evaluated. performance_test_protocol is
    the live instance: G11 at runtime, G5 in the registry.
    """
    wrong = []
    for g in _runtime_gates():
        for ek in g["required_evidence"]:
            resolved = EVIDENCE_GATE_MAP.get(ek)
            if resolved != g["gate_id"]:
                wrong.append(f"{ek}: scored by {g['gate_id']}, resolves to {resolved}")
    assert not wrong, "evidence resolves to a gate other than the one scoring it:\n  " + "\n  ".join(wrong)


def test_the_registry_advertises_the_completion_the_engine_requires():
    """
    The engine's `is_complete` is `verified == applicable_total` — every
    applicable item, no threshold. The registry used to advertise 60.0.
    """
    from app.api.v1.routes_gate_registry import _build_entry

    for g in GATE_REGISTRY:
        assert _build_entry(g).min_completion_for_next == 100.0, (
            f"{g.id} advertises a completion threshold the engine does not honour"
        )
