"""
The commitment taxonomy — item 2, "clean the mess".

Six commitment-shaped objects accumulated here, one per conversation with a differently
imagined user. They were never six versions of one thing: they are two families that act
on different parts of a financial model, plus three modules that are not instruments at
all.

These tests keep that true. The failure they exist to prevent is the seventh object.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core import vocabulary as v
from app.core.instrument_registry import InstrumentType

CROSSWALK = "app.core.instrument_registry.InstrumentType"


# ── the two families ──────────────────────────────────────────────────────────


def test_every_instrument_belongs_to_exactly_one_family():
    families = {t.bucket for t in v.COMMITMENT_INSTRUMENT.terms}
    assert families == {v.DEMAND_FAMILY, v.CAPITAL_SUPPORT_FAMILY}

    for term in v.COMMITMENT_INSTRUMENT.terms:
        assert v.commitment_family(term.canonical) == term.bucket


def test_demand_and_capital_support_never_share_a_canonical_value():
    demand = {t.canonical for t in v.COMMITMENT_INSTRUMENT.terms if t.bucket == v.DEMAND_FAMILY}
    support = {
        t.canonical for t in v.COMMITMENT_INSTRUMENT.terms if t.bucket == v.CAPITAL_SUPPORT_FAMILY
    }
    assert demand and support
    assert demand.isdisjoint(support)


def test_the_tenet_is_in_the_demand_family():
    """Long-term offtake matching is the platform's tenet. If bilateral offtake ever
    stops being a demand instrument, something has gone badly wrong upstream."""
    assert v.commitment_family("bilateral_offtake") == v.DEMAND_FAMILY
    assert v.commitment_family("advance_market_commitment") == v.DEMAND_FAMILY


def test_a_guarantee_over_an_offtake_is_still_capital_support():
    """OFFTAKE_GUARANTEE is the classic misfiling: it contains the word offtake and is
    not one. It underwrites a loss; it does not buy a molecule."""
    mapped = v.COMMITMENT_INSTRUMENT.crosswalks[CROSSWALK]["OFFTAKE_GUARANTEE"]
    assert v.commitment_family(mapped) == v.CAPITAL_SUPPORT_FAMILY


# ── completeness ──────────────────────────────────────────────────────────────


def test_every_built_instrument_type_is_classified():
    """A new InstrumentType member must be filed into a family in the same commit.
    Otherwise the registry silently regrows an unclassified vocabulary."""
    crosswalk = v.COMMITMENT_INSTRUMENT.crosswalks[CROSSWALK]
    unmapped = [t.value for t in InstrumentType if t.value not in crosswalk]
    assert not unmapped, f"unclassified InstrumentType members: {unmapped}"


def test_the_registry_is_almost_entirely_capital_support():
    """The measurement that started this work, pinned so it cannot quietly drift.

    Of the built instrument registry, exactly one member is a demand instrument. That
    asymmetry is the finding: the capital-support side was built in depth and the demand
    side — the tenet — has almost no object. When this test starts failing because the
    demand count rose, that is the platform catching up with its own strategy: update
    the number deliberately.
    """
    crosswalk = v.COMMITMENT_INSTRUMENT.crosswalks[CROSSWALK]
    demand = [k for k, c in crosswalk.items() if v.commitment_family(c) == v.DEMAND_FAMILY]
    assert demand == ["CFD"], f"demand-side InstrumentType members changed: {demand}"


# ── which module do I use ─────────────────────────────────────────────────────


def test_exactly_one_canonical_owner_per_family():
    canonical = [
        (module, spec)
        for module, spec in v.COMMITMENT_OBJECT_ROLES.items()
        if spec["role"].startswith("CANONICAL")
    ]
    by_family = {}
    for module, spec in canonical:
        by_family.setdefault(spec["family"], []).append(module)

    assert by_family["DEMAND"] == ["app.core.contractual_rating_engine.OfftakeContract"]
    assert by_family["CAPITAL_SUPPORT"] == ["app.core.instrument_registry.Instrument"]


def test_every_role_declares_what_it_is_not_for():
    """Half of a taxonomy's value is the negative. A role with no `not_for` is an
    invitation to reuse it for the wrong thing."""
    for module, spec in v.COMMITMENT_OBJECT_ROLES.items():
        assert spec["not_for"].strip(), f"{module} declares no boundary"
        assert spec["family"] in {"DEMAND", "CAPITAL_SUPPORT", "NEITHER"}


def test_the_signature_service_is_declared_not_an_instrument():
    """`css` / routes_commitments is eIDAS non-repudiation. 'Commitment' there means a
    signed record. It is the most likely wrong import in this codebase and the taxonomy
    has to say so out loud."""
    css = v.COMMITMENT_OBJECT_ROLES["app.core.css"]
    assert css["family"] == "NEITHER"
    assert "signature" in css["role"].lower()


def test_project_context_offtake_fields_are_a_projection_not_a_record():
    spec = v.COMMITMENT_OBJECT_ROLES["project_context.offtake_*"]
    assert "PROJECTION" in spec["role"]
    assert "system of record" in spec["not_for"]


# ── the canonical demand object can express a timeline ────────────────────────


def test_the_canonical_demand_object_can_place_a_contract_in_time():
    """Being canonical is a claim the object has to earn. An offtake register that
    cannot say when a contract starts cannot answer the only question that matters —
    does it outlast the debt."""
    from app.core.contractual_rating_engine import OfftakeContract

    fields = OfftakeContract.__dataclass_fields__
    assert "start_year" in fields
    assert "tenor_years" in fields


# ── no new commitment object without a role ───────────────────────────────────


def test_no_unregistered_commitment_module_appears():
    """Walks module names, not contents, so a seventh object cannot arrive unnoticed.

    If this fails, either register the new module in COMMITMENT_OBJECT_ROLES with its
    family and its boundary, or — better — use one of the two canonical objects.
    """
    app_root = Path(v.__file__).resolve().parent.parent
    # Role keys are dotted paths that may end in a CLASS
    # (…contractual_rating_engine.OfftakeContract) or a MODULE (…core.css), so every
    # segment counts as registered — matching only the last segment would miss the two
    # canonical modules and is exactly the bug this comment exists to prevent recurring.
    registered = {segment for m in v.COMMITMENT_OBJECT_ROLES for segment in m.split(".")}

    known_unrelated = {
        "refresh_tokens",       # auth session tokens
        "routes_commitments",   # the CSS route surface; core module `css` is registered
        "marketplace_sqlite",   # matching, not the agreement
        "marketplace_analytics",
        "trader_rfqs",          # request-for-quote, pre-agreement
        "routes_instruments",     # route surface over the registered instrument_registry
        "routes_open_interest",   # route surface over the registered core.open_interest
        "routes_deal_killers",
    }

    suspicious = []
    for path in sorted(app_root.rglob("*.py")):
        if "__pycache__" in path.parts or "A_main" in path.name:
            continue
        stem = path.stem
        # "interest" is in this list because open_interest.py — a genuinely new
        # demand-side object — was added while the list was narrower and slipped
        # through. The keyword set is the guardrail's blind spot; widen it when a new
        # word for "a promise about molecules" enters the codebase.
        if any(k in stem for k in
               ("commitment", "offtake", "instrument", "contract", "interest")):
            if stem not in registered and stem not in known_unrelated:
                suspicious.append(str(path.relative_to(app_root)))

    assert not suspicious, (
        "commitment-shaped modules with no declared role: "
        f"{suspicious}. Register them in COMMITMENT_OBJECT_ROLES or use a canonical object."
    )
