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
    capex, opex, lcop, currency = runner._real_numbers(
        _req(),
        [ProcessUnitSpec(id="h2comp", category="Compressors & blowers",
                         equipment_type="H2 compressor",
                         material="316 stainless steel", sizing=300)],
        {"electricity": {"consumption": 1.0, "price": 45.0}},
    )
    assert capex > 0 and lcop > 0 and currency


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


# ── 6. Input integrity — provenance (G1) and units / plausibility (G2) ───────

def test_unknown_nameplate_unit_is_refused_not_guessed():
    """G2: an unrecognised unit RAISES (→422), never read as t/yr — the
    1000×/365× trap. A known unit converts through the one canonical table."""
    from tea_engine import integrity
    with pytest.raises(ValueError) as e:
        runner.run_tea(_req(nameplate_unit="furlongs_per_fortnight"))
    assert "Unknown nameplate_unit" in str(e.value)
    assert integrity.to_t_per_year(50, "kt_per_year") == 50_000
    assert integrity.to_t_per_year(50, "t_per_day") == 50 * 365


def test_implausible_output_flagged_and_status_downgraded():
    """G2: a 1000× sizing error yields a physically implausible specific CAPEX;
    the result carries a flag and status IMPLAUSIBLE, not a normal-looking case."""
    r = runner.run_tea(_req(process_units=[{
        "id": "rx", "category": "Reactors", "equipment_type": "Tubular fixed bed",
        "material": "Carbon steel", "sizing": 110_000_000}]))
    assert r.result_status == "IMPLAUSIBLE"
    assert r.plausibility and any("specific_capex" in f or "lcop" in f for f in r.plausibility)


def test_provenance_distinguishes_model_default_from_project_input():
    """G1: a defaulted input is model_default (SCREENING); an all-supplied set is
    sponsor_assumption (PROVISIONAL) — the distinction attack #18 relies on."""
    from tea_engine.models import FinancialAssumptions, TEAComputeRequest
    base = dict(project_id="p", pathway_id="pw", fuel_id="E_METHANOL",
                nameplate_capacity=100_000, nameplate_unit="t/yr")
    r_def = runner.run_tea(TEAComputeRequest(assumptions=FinancialAssumptions(), **base))
    assert r_def.input_provenance["electricity_eur_mwh"]["source_class"] == "model_default"
    assert r_def.result_status == "SCREENING"
    full = FinancialAssumptions(discount_rate_pct=8.5, electricity_eur_mwh=55,
        capacity_factor=0.65, project_life_years=25, contingency_pct=20,
        co2_eur_t=60, hydrogen_eur_t=2800, feedstock_oil_eur_t=1100)
    r_full = runner.run_tea(TEAComputeRequest(assumptions=full, **base))
    assert all(v["source_class"] == "sponsor_assumption"
               for v in r_full.input_provenance.values())
    assert r_full.result_status == "PROVISIONAL"


def test_caller_can_upgrade_provenance_class():
    """G1: a caller may classify an input above the default sponsor tier."""
    from tea_engine.models import FinancialAssumptions, TEAComputeRequest
    a = FinancialAssumptions(electricity_eur_mwh=55,
                             provenance={"electricity_eur_mwh": "vendor_guaranteed"})
    r = runner.run_tea(TEAComputeRequest(project_id="p", pathway_id="pw",
        fuel_id="E_METHANOL", nameplate_capacity=100_000, nameplate_unit="t/yr", assumptions=a))
    assert r.input_provenance["electricity_eur_mwh"]["source_class"] == "vendor_guaranteed"


# ── 7. Output integrity — scaling (G4), cost basis (G5), boundary (G6) ───────

def test_scaling_basis_is_exposed_and_extreme_extrapolation_flagged():
    """G4: the sizing scaling (reference, ratio, exponents) is surfaced, and an
    extreme nameplate-to-reference ratio is flagged (a likely unit/scale error)."""
    from tea_engine import integrity
    s = runner.run_tea(_req(nameplate_capacity=200_000)).process_function["scaling"]
    assert s["reference_nameplate_t_per_year"] == 50_000
    assert s["ratio"] == 4.0 and s["component_scale_exponents"] == [0.65]
    assert s["extrapolated"] is False
    assert integrity.scaling_flags({"scaling": {"ratio": 100.0,
        "reference_nameplate_t_per_year": 50_000}})            # extreme → flagged
    assert not integrity.scaling_flags({"scaling": {"ratio": 4.0,
        "reference_nameplate_t_per_year": 50_000}})            # moderate → not flagged


def test_cost_basis_default_is_eur_fx_normalised_from_usd():
    """G5 fix: OpenPyTEA's USD correlations are converted to the base currency (EUR)
    at a FIXED DATED rate; the basis is FX-normalised and carries the rate's
    provenance (external_benchmark for the default)."""
    cb = runner.run_tea(_req()).cost_basis
    assert cb["currency"] == "EUR" and cb["cost_year"] == 2024
    assert cb["fx_normalised"] is True
    assert cb["fx"]["rate"] == 0.924 and cb["fx"]["provenance"] == "external_benchmark"


def test_base_currency_usd_is_native_and_eur_is_scaled_by_the_rate():
    """USD base is native (rate 1.0); the EUR figure is the USD capital cost scaled
    by the dated rate — variable OPEX (already base-currency) is not double-converted."""
    r = runner.run_tea(_req())                        # EUR default
    u = runner.run_tea(_req(base_currency="USD"))      # native USD
    assert u.cost_basis["currency"] == "USD" and u.cost_basis["fx"]["rate"] == 1.0
    assert abs(r.plant_summary.capex_eur - u.plant_summary.capex_eur * 0.924) < 1.0


def test_fx_override_is_a_sponsor_assumption():
    """A caller/CFO FX override wins and its provenance downgrades to sponsor."""
    cb = runner.run_tea(_req(fx_usd_to_eur=0.90)).cost_basis
    assert cb["fx"]["rate"] == 0.90 and cb["fx"]["provenance"] == "sponsor_assumption"


def test_cost_basis_hash_deterministic_and_currency_sensitive():
    """A fixed dated rate keeps cost_basis_hash reproducible; a currency change shows."""
    assert runner.run_tea(_req()).cost_basis_hash == runner.run_tea(_req()).cost_basis_hash
    assert (runner.run_tea(_req()).cost_basis_hash
            != runner.run_tea(_req(base_currency="USD")).cost_basis_hash)


def test_fx_override_bounded_to_conservative_band():
    """Increment 3: the ±5% band is a source invariant — an override beyond it raises
    (→ 422 via the route), regardless of who asked. Benchmark USD->EUR=0.924 → [0.8778, 0.9702]."""
    from tea_engine import integrity
    assert integrity.usd_to_base_rate("EUR", 0.90) == 0.90          # in band
    for out in (1.50, 0.80, 0.98):                                   # far / just-below / just-above
        with pytest.raises(ValueError):
            integrity.usd_to_base_rate("EUR", out)
    with pytest.raises(ValueError):                                 # run_tea surfaces it
        runner.run_tea(_req(fx_usd_to_eur=1.50))


def test_calculation_boundary_canonical_vs_caller_supplied():
    """G6: a registry train declares its battery-limit nodes; a caller-supplied
    train that dropped blocks is flagged incomplete (attack I)."""
    canon = runner.run_tea(_req()).calculation_boundary
    assert canon["basis"] == "canonical" and canon["complete"] is True
    assert set(canon["nodes"]) == {"synthesis", "product", "storage"}

    train = [ProcessUnitSpec(id=f"u{i}", category="Reactors",
             equipment_type="Tubular fixed bed", material="Carbon steel", sizing=200)
             for i in range(3)]
    part = runner.run_tea(_req(process_units=train)).calculation_boundary
    assert part["basis"] == "caller_supplied"
    assert part["equipment_count"] == 3 and part["canonical_equipment_count"] == 12
    assert part["complete"] is False and "missing process blocks" in part["note"]


# ── 8. Monte Carlo — the distribution, not a single LCOP (attack L) ──────────

def _mc(**over):
    from tea_engine.models import TEAMonteCarloRequest
    base = dict(
        project_id="p", pathway_id="pw", fuel_id="E_METHANOL",
        country="United States", nameplate_capacity=100_000, nameplate_unit="t/yr",
        assumptions={"discount_rate_pct": 8.0, "electricity_eur_mwh": 45.0,
                     "capacity_factor": 0.55, "project_life_years": 25},
        num_samples=500,
    )
    base.update(over)
    return TEAMonteCarloRequest(**base)


def test_monte_carlo_is_centred_bracketing_and_reproducible():
    """The band brackets the point estimate and centres on it (lifetime held — see the
    canary below), and a fixed seed reproduces it exactly."""
    a = runner.run_monte_carlo(_mc())
    assert a.lcop.p5 <= a.base_lcop <= a.lcop.p95
    assert abs(a.lcop.mean / a.base_lcop - 1) < 0.03
    assert a.num_valid == a.num_samples == 500
    assert runner.run_monte_carlo(_mc()).lcop == a.lcop             # same seed → identical
    assert runner.run_monte_carlo(_mc(seed=7)).lcop != a.lcop       # other seed → differs


def test_monte_carlo_samples_the_dominant_drivers_with_provenance():
    """OpenPyTEA holds feedstock prices and utilisation fixed by default, which would make
    the band falsely narrow. GEX samples them and labels every varied input; a caller
    override becomes a sponsor assumption."""
    by = {b["input"]: b for b in runner.run_monte_carlo(_mc()).uncertainty_basis}
    for name in ("Hydrogen price", "Electricity price", "Plant utilization"):
        assert by[name]["std"] > 0 and by[name]["source_class"] == "model_default"
    ov = {b["input"]: b for b in
          runner.run_monte_carlo(_mc(price_rel_std={"hydrogen": 0.25})).uncertainty_basis}
    assert ov["Hydrogen price"]["source_class"] == "sponsor_assumption"
    assert ov["Hydrogen price"]["std"] > by["Hydrogen price"]["std"]


def test_monte_carlo_holds_lifetime_fixed_and_says_so():
    """The direct guard on the lifetime hold (see the canary). The centring test is NOT
    enough: negative-verified 2026-09-22, re-enabling lifetime sampling on _mc's config
    moves the mean only -2%, inside its 3% tolerance. So assert the hold itself."""
    r = runner.run_monte_carlo(_mc())
    assert "Project lifetime" not in {b["input"] for b in r.uncertainty_basis}
    assert "lifetime" in r.held_fixed[0]


def test_monte_carlo_links_to_compute_and_answers_a_target():
    r = runner.run_monte_carlo(_mc())
    assert r.cost_basis_hash == runner.run_tea(_req()).cost_basis_hash
    t = runner.run_monte_carlo(_mc(target_lcop=r.lcop.p50))
    assert 0.45 <= t.p_lcop_le_target <= 0.55


def test_monte_carlo_refuses_specs_that_would_mislead():
    """A typo'd stream, an absurd σ, and sampling lifetime (known upstream bias) are
    refused rather than silently absorbed; sample count is bounded per request."""
    for bad in ({"price_rel_std": {"hydrogn": 0.2}},
                {"price_rel_std": {"hydrogen": 0.9}},
                {"project_uncertainties": {"project_lifetime": {"std": 5}}}):
        with pytest.raises(ValueError):
            runner.run_monte_carlo(_mc(**bad))
    from pydantic import ValidationError
    for n in (10, 50_000):                 # OpenPyTEA's 1e6 default is unusable per request
        with pytest.raises(ValidationError):
            _mc(num_samples=n)


def test_monte_carlo_needs_the_real_engine(monkeypatch):
    monkeypatch.setenv("TEA_STUB", "1")
    with pytest.raises(NotImplementedError):
        runner.run_monte_carlo(_mc())


def test_openpytea_mc_lifetime_bug_canary():
    """CANARY — OpenPyTEA 2.1.0's vectorised Monte Carlo ignores per-sample lifetime:
    samples at ~15 y and ~35 y return the same LCOP, although deterministically they
    differ materially. GEX holds lifetime fixed because of it (MC_LIFETIME_HELD).
    IF THIS TEST FAILS, upstream fixed the bug: re-enable lifetime sampling in
    run_monte_carlo, drop MC_LIFETIME_HELD, and delete this canary."""
    import numpy as np
    from openpytea.analysis import monte_carlo
    req = _req()
    units, var_opex, _ = runner.resolve_process_function(req)
    pu = {k: {"std": 0} for k in ("fixed_capital_factor", "fixed_opex_factor",
                                   "interest_rate", "plant_utilization", "tax_rate")}
    plant, _ = runner._build_plant(req, units, var_opex,
                                   extra_config={"project_uncertainties": pu})
    np.random.seed(1)
    mc = monte_carlo(plant, num_samples=3000, batch_size=1000)
    life = np.asarray(mc["inputs"]["Project lifetime"])
    lcop = np.asarray(mc["metrics"]["LCOP"])
    short, long_ = lcop[life < 17].mean(), lcop[life > 33].mean()
    assert abs(short - long_) < 0.05, "upstream fixed the lifetime bug — see docstring"
