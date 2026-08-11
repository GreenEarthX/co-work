"""
TEA engine guardrails.
======================
tea_engine (:8002) sits UPSTREAM of the PF engine: it produces the provisional
cost basis every downstream number depends on. It had no test coverage at all,
so three properties that matter were unguarded:

  1. The cost basis is never SELF-VERIFIED. TEA emits a provisional basis and a
     proposed evidence entry; only an IE/CFO promotes it to model_base_case.
     If TEA ever returned a verified state, release-gated compute would run on
     an unapproved basis.
  2. A molecule with no costed equipment train REFUSES rather than returning a
     number. Three of six registered molecules are scaffolds; a fabricated
     figure a lender cannot distinguish from a real one is the failure mode
     this codebase keeps re-encountering.
  3. Bad input never becomes a 500. OpenPyTEA raises bare KeyError for inputs
     it cannot resolve; those were reaching the API as opaque server errors.

Plus the upstream data-integrity check that unblocked the H2 compressor.

tea_engine is a sibling package of backend/, so it is not on the path when
pytest runs from backend/. The insert below is deliberate and contained.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

openpytea = pytest.importorskip(
    "openpytea", reason="TEA guardrails exercise the real engine, not the stub"
)

from tea_engine import cepci_extension  # noqa: E402
from tea_engine.compute import openpytea_runner as runner  # noqa: E402
from tea_engine.models import ProcessUnitSpec, TEAComputeRequest  # noqa: E402


def _req(**over) -> TEAComputeRequest:
    base = dict(
        project_id="p", pathway_id="pw", fuel_id="E_METHANOL",
        country="United States", nameplate_capacity=100_000, nameplate_unit="t/yr",
        assumptions={"discount_rate_pct": 8.0, "electricity_eur_mwh": 45.0,
                     "capacity_factor": 0.55, "project_life_years": 25},
    )
    base.update(over)
    return TEAComputeRequest(**base)


# ── 1. Upstream data integrity ──────────────────────────────────────────────

def test_no_cost_correlation_references_a_year_outside_the_cepci_series():
    """
    openpytea 2.1.0 ships cost_correlations.csv referencing cost_year 1987 while
    cepci_values.csv starts at 1990, making the H2 compressor — core equipment
    for any RFNBO pathway — uncostable. cepci_extension supplies the published
    value for the gap. This fails if a new gap appears upstream, or if the
    extension stops being applied.
    """
    unresolved = cepci_extension.unresolvable_cost_years()
    assert not unresolved, (
        f"cost correlations reference CEPCI years {unresolved} that the index "
        "does not cover — that equipment cannot be costed. Add the published "
        "value to cepci_extension.GEX_SUPPLIED_CEPCI."
    )


def test_cepci_extension_never_overrides_upstream_values():
    """Upstream always wins — we only fill genuine holes."""
    from openpytea.equipment import CEPCI_DF

    for year in cepci_extension.GEX_SUPPLIED_CEPCI_YEARS:
        assert year in CEPCI_DF.index
    # Every year we supplied was genuinely absent; a year upstream already had
    # must never appear in the supplied list.
    assert set(cepci_extension.GEX_SUPPLIED_CEPCI_YEARS) <= set(
        cepci_extension.GEX_SUPPLIED_CEPCI
    )


def test_the_h2_compressor_is_costable():
    """The specific correlation the CEPCI gap blocked. RFNBO depends on it."""
    capex, opex, lcop = runner._real_numbers(
        _req(),
        [ProcessUnitSpec(id="h2comp", category="Compressors & blowers",
                         equipment_type="H2 compressor",
                         material="316 stainless steel", sizing=300)],
        {"electricity": {"consumption": 1.0, "price": 45.0}},
    )
    assert capex > 0 and lcop > 0


# ── 2. Bad input is 422, never 500 ──────────────────────────────────────────

def _unit(**over):
    spec = dict(id="x", category="Reactors", equipment_type="Autoclave",
                material="316 stainless steel", sizing=25)
    spec.update(over)
    return ProcessUnitSpec(**spec)


def test_unknown_equipment_type_names_the_valid_options():
    with pytest.raises(ValueError) as e:
        runner._validate_equipment([_unit(equipment_type=None)])
    msg = str(e.value)
    assert "Unknown equipment_type" in msg and "Autoclave" in msg


def test_unknown_category_names_the_valid_options():
    with pytest.raises(ValueError) as e:
        runner._validate_equipment([_unit(category="reactor")])
    msg = str(e.value)
    assert "Unknown equipment category" in msg and "Reactors" in msg


def test_valid_equipment_passes_validation():
    runner._validate_equipment([_unit()])


def test_validation_actually_runs_before_openpytea():
    """
    Wiring guard. The two tests above call _validate_equipment directly, and the
    route test is satisfied by the KeyError backstop — so both still pass if the
    call inside _real_numbers is deleted, silently degrading the message from
    'valid options are [...]' back to OpenPyTEA's raw 'add a row to the CSV'.
    Assert the specific exception type only pre-validation produces.
    """
    with pytest.raises(ValueError, match="Unknown equipment_type"):
        runner._real_numbers(
            _req(), [_unit(equipment_type=None)],
            {"electricity": {"consumption": 1.0, "price": 45.0}},
        )


def test_compute_route_maps_bad_input_to_422_not_500():
    """
    Route-level: KeyError from OpenPyTEA is bad input, not a server fault.
    Exercised through the app so the exception handlers are the ones tested.
    """
    from fastapi.testclient import TestClient

    from tea_engine.auth.gex_jwt import AuthenticatedUser
    from tea_engine.main import app
    from tea_engine.routes.tea import get_current_user

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id="test", email=None, role="service"
    )
    try:
        c = TestClient(app, raise_server_exceptions=False)
        body = _req().model_dump(mode="json")
        body["process_units"] = [{"id": "x", "category": "Reactors",
                                  "material": "316 stainless steel", "sizing": 25}]
        r = c.post("/tea/compute", json=body)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── 3. The promotion doctrine ───────────────────────────────────────────────

def test_tea_never_self_verifies_its_cost_basis():
    """
    THE doctrine. TEA produces a PROVISIONAL basis; promotion to
    model_base_case requires an IE/CFO approval_decision. If this ever returns
    a verified state, release-gated compute runs on an unapproved basis.
    """
    result = runner.run_tea(_req())
    assert result.plant_summary.verification_state == "UNVERIFIED"
    assert result.model_claim_state == "submitted"
    assert result.run_evidence.produced_by == "tea_engine"
    assert "IE/CFO" in (result.note or ""), "the promotion requirement must be stated"


def test_cost_basis_is_hashed_and_deterministic():
    a, b = runner.run_tea(_req()), runner.run_tea(_req())
    assert a.cost_basis_hash.startswith("sha256:")
    assert a.cost_basis_hash == b.cost_basis_hash
    assert a.plant_summary.capex_eur == b.plant_summary.capex_eur


# ── 4. Scaffolds refuse; costed molecules compute ───────────────────────────

import tea_engine.process_functions as pfx  # noqa: E402

_COSTED = sorted(k for k, v in pfx.REGISTRY.items() if v.equipment)
_SCAFFOLD = sorted(k for k, v in pfx.REGISTRY.items() if not v.equipment)


def test_the_registry_has_both_costed_and_scaffold_molecules():
    """Guards the parametrisation below from silently covering nothing."""
    assert _COSTED and _SCAFFOLD


@pytest.mark.parametrize("fuel", _SCAFFOLD)
def test_scaffold_molecules_refuse_rather_than_fabricate(fuel):
    """No fictional economics — an honest refusal naming the reason."""
    with pytest.raises(ValueError) as e:
        runner.run_tea(_req(fuel_id=fuel))
    assert "SCAFFOLD" in str(e.value)


@pytest.mark.parametrize("fuel", _COSTED)
def test_costed_molecules_produce_positive_economics_and_a_regime(fuel):
    r = runner.run_tea(_req(fuel_id=fuel))
    assert r.plant_summary.capex_eur > 0
    assert r.plant_summary.opex_eur_per_year > 0
    assert r.lcop > 0
    assert r.regime is not None, "the regulatory fork must resolve for a costed train"
    assert r.regime["pathway_class"] == pfx.REGISTRY[fuel].pathway_class


def test_unregistered_molecule_refuses():
    with pytest.raises(ValueError) as e:
        runner.run_tea(_req(fuel_id="UNOBTANIUM"))
    assert "No process function" in str(e.value)


# ── 5. Documented behaviour that reads like a bug ───────────────────────────

def test_caller_supplied_train_yields_no_regime_by_design():
    """
    Supplying process_units takes the caller-owned-basis branch, which returns
    no process-function meta and therefore no regime. This is deliberate — GEX
    must not attach a regulatory classification to a train it did not derive —
    and is asserted so it is not "fixed" by mistake.
    """
    r = runner.run_tea(_req(process_units=[{
        "id": "meohrx", "category": "Reactors", "equipment_type": "Autoclave",
        "material": "316 stainless steel", "sizing": 25}]))
    assert r.regime is None
    assert r.process_function is None
