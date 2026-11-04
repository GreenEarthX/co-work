"""The mass balance is computed and reported, not asserted in a docstring.

JML 2026-10-26: "are you certain the mass balance equations and parameters are created
and calculated? is this process clean". They were not. There was no closure equation
anywhere in tea_engine/; the phrase "the mass balance closes" existed only in a
docstring on CoProduct.

Three things this pins, no Aspen and no surrogate models involved:

1. ONE RULE for feedstock. `feedstock_per_t_primary` used
   `scale = M if has_co else (1.0 / yield_frac)` — one factor OR the other. On a
   co-product pathway that DISCARDED yield_frac: E_SAF published `yield_frac: 0.75`
   in its result meta while its price contained no conversion loss at all.
   The rule is now `declared x M / yield_frac`, and both factors apply because they
   are orthogonal: M is what you call the product, yield_frac is how much feed fails
   to become any product. Verified against first principles — every declared ratio is
   raw stoichiometry to within 0.7%, so there is no loss allowance to double-count.
2. A CLOSURE CHECK, `integrity.mass_balance_flags`, the input-side sibling of
   `plausibility_flags`. Process Mass Intensity, so a reader can check it by hand.
3. The band DISCLOSES that quantity risk is excluded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tea_engine.process_functions as pfx          # noqa: E402
from tea_engine import integrity                    # noqa: E402
from tea_engine.compute import run_tea              # noqa: E402
from tea_engine.models import TEAComputeRequest     # noqa: E402

MW = {"CO2": 44.009, "H2": 2.016, "CH3OH": 32.042, "CH4": 16.043,
      "CH2": 14.027, "NH3": 17.031}


def _req(fuel="E_METHANOL"):
    return TEAComputeRequest(project_id="mb", pathway_id="m", fuel_id=fuel,
                             nameplate_capacity=50000.0, nameplate_unit="t_per_year")


@pytest.mark.parametrize("fuel,stream,stoich", [
    ("E_METHANOL", "hydrogen", 3 * MW["H2"] / MW["CH3OH"]),
    ("E_METHANOL", "co2", MW["CO2"] / MW["CH3OH"]),
    ("E_METHANE", "hydrogen", 4 * MW["H2"] / MW["CH4"]),
    ("E_METHANE", "co2", MW["CO2"] / MW["CH4"]),
    ("E_SAF", "hydrogen", 3 * MW["H2"] / MW["CH2"]),
    ("E_SAF", "co2", MW["CO2"] / MW["CH2"]),
    ("E_AMMONIA", "hydrogen", 3 * MW["H2"] / (2 * MW["NH3"])),
])
def test_declared_ratios_are_stoichiometry_so_yield_is_not_double_counted(fuel, stream, stoich):
    """The justification for applying BOTH M and 1/yield_frac. If a declared ratio ever
    gains a loss allowance, this fails and the one rule must be revisited."""
    declared = {f.stream: f.t_per_t_product
                for f in pfx.REGISTRY[fuel].feedstocks if f.t_per_t_product}[stream]
    assert abs(declared / stoich - 1) < 0.01, (
        f"{fuel}.{stream} declared {declared} is {declared/stoich:.4f}x stoichiometric "
        f"{stoich:.5f} — it carries a loss allowance, so dividing by yield_frac would "
        f"double-count it")


def test_one_rule_applies_both_factors():
    """The fork applied one OR the other. Both are needed, and they are independent."""
    for fuel in ("E_SAF", "BIO_SAF_HEFA"):
        pf = pfx.REGISTRY[fuel]
        M = pfx.total_product_per_primary(pf)
        assert M > 1.0 and pf.yield_frac < 1.0, f"{fuel} must exercise both factors"
        declared = {f.stream: f.t_per_t_product for f in pf.feedstocks if f.t_per_t_product}
        effective = {s: q for s, q, is_energy, _ in pfx.feedstock_per_t_primary(pf)
                     if not is_energy}
        for s, d in declared.items():
            expected = d * M / pf.yield_frac
            assert abs(effective[s] - expected) < 1e-9, (
                f"{fuel}.{s}: yield_frac {pf.yield_frac} is being discarded")


def test_energy_streams_take_the_slate_but_not_the_yield():
    """A MWh is not consumed by unreacted feed, so energy scales by M only."""
    pf = pfx.REGISTRY["E_SAF"]
    M = pfx.total_product_per_primary(pf)
    declared = {f.stream: f.mwh_per_t_product for f in pf.feedstocks if f.mwh_per_t_product}
    effective = {s: q for s, q, is_energy, _ in pfx.feedstock_per_t_primary(pf) if is_energy}
    for s, d in declared.items():
        assert abs(effective[s] - d * M) < 1e-9, f"{s} must scale by M alone"


def test_single_product_pathways_are_unchanged_by_the_one_rule():
    """M = 1 for a pathway with no co-products, so the rule reduces to 1/yield_frac and
    methanol must still price at exactly what it did before."""
    assert pfx.total_product_per_primary(pfx.REGISTRY["E_METHANOL"]) == 1.0
    assert run_tea(_req()).lcop == 2.307


def test_the_balance_is_published_so_it_can_be_checked_by_hand():
    mb = run_tea(_req()).mass_balance
    assert mb["basis"] == "per tonne of PRIMARY product"
    assert mb["rule"] == "declared x total_product_per_primary / yield_frac"
    # 0.1875 + 1.375 = 1.5625, / 0.9 = 1.736111 — checkable with a calculator
    assert abs(mb["inputs_t"] - 1.736111) < 1e-5
    assert mb["products_t"] == 1.0
    assert abs(mb["process_mass_intensity"] - 1.7361) < 1e-3
    assert abs(mb["undeclared_outputs_t"] - 0.736111) < 1e-5


def test_the_balance_does_not_reclassify_every_basis_as_implausible():
    """result_status turns ANY plausibility flag into IMPLAUSIBLE, and the undeclared
    reaction water is a data gap on every pathway. Merging the two would block all
    promotion and make the release gate meaningless."""
    r = run_tea(_req())
    assert r.mass_balance["flags"], "the undeclared output must be reported"
    assert r.plausibility == [], "it must NOT be merged into plausibility"
    assert r.result_status == "SCREENING"


@pytest.mark.parametrize("fuel,expect", [
    ("E_AMMONIA", "below"),        # nitrogen from air never declared -> PMI 0.198
    ("GREEN_H2", "no mass input"),  # feed water never declared -> PMI 0.000
])
def test_a_pathway_that_makes_mass_from_nothing_is_flagged(fuel, expect):
    pf = pfx.REGISTRY[fuel]
    mi = pfx._mass_in_per_t_primary(pf)
    mo = pfx.total_product_per_primary(pf)
    flags = integrity.mass_balance_flags({
        "mass_in_t_per_t_primary": mi, "mass_out_t_per_t_primary": mo,
        "undeclared_outputs_t_per_t_primary": max(mi - mo, 0.0)})
    assert any(expect in f for f in flags), f"{fuel} PMI {mi/mo:.3f} not flagged: {flags}"


def test_the_monte_carlo_band_says_quantity_risk_is_excluded():
    """yield_frac is not an OpenPyTEA input, so it appeared in neither uncertainty_basis
    nor held_fixed — the band did not disclose that conversion risk was absent."""
    from tea_engine.compute import run_monte_carlo
    from tea_engine.models import TEAMonteCarloRequest
    m = run_monte_carlo(TEAMonteCarloRequest(
        project_id="mb", pathway_id="m", fuel_id="E_METHANOL",
        nameplate_capacity=50000.0, nameplate_unit="t_per_year", num_samples=300))
    disclosed = [h for h in m.held_fixed if "yield_frac" in h]
    assert disclosed, f"conversion yield not disclosed as held fixed: {m.held_fixed}"
    assert "not quantity risk" in disclosed[0]
    assert "Conversion yield" not in {b["input"] for b in m.uncertainty_basis}
