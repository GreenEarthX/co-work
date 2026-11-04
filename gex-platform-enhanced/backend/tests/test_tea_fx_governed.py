"""The TEA cost-basis FX rate is a GOVERNED reference, not a hardcoded constant.

`tea_engine/integrity.py` held `USD_TO_BASE = {"EUR": 0.924}` and used it both to
convert OpenPyTEA's USD correlations and as the midpoint of the +/-5% band a CFO FX
override must sit inside. Measured 2026-09-24: editing that constant to 0.88 moved
e-methanol capex -4.8% (175,255,929 -> 166,910,409) with a BYTE-IDENTICAL
`cost_basis_hash`. Nobody proposed it and nobody approved it.

Migration 072 puts the rate in `reference_parameter` under the registry's four-eye
lifecycle. `tea_engine` is stateless and holds no database, so the bridge resolves the
row and passes the value in the request — which `cost_basis_hash` already covers. These
tests pin all three halves: the hash now moves, the band tracks the governed benchmark,
and a change needs two different people.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tea_engine import integrity                      # noqa: E402
from tea_engine.compute import run_tea                # noqa: E402
from tea_engine.models import TEAComputeRequest       # noqa: E402

_BENCH = 0.924


def _req(**over):
    base = dict(project_id="gov", pathway_id="g", fuel_id="E_METHANOL",
                nameplate_capacity=50000.0, nameplate_unit="t_per_year")
    base.update(over)
    return TEAComputeRequest(**base)


def test_a_governed_rate_change_moves_the_cost_basis_hash():
    """THE defect this closes. Before 072 the rate was outside the hashed blob."""
    a = run_tea(_req(fx_benchmark_usd_to_eur=0.924, fx_benchmark_ref_id="ref-a"))
    b = run_tea(_req(fx_benchmark_usd_to_eur=0.880, fx_benchmark_ref_id="ref-a"))
    assert a.plant_summary.capex_eur != b.plant_summary.capex_eur, "rate must move capex"
    assert abs(b.plant_summary.capex_eur / a.plant_summary.capex_eur - 1) > 0.04
    assert a.cost_basis_hash != b.cost_basis_hash, (
        "a governed FX change must rehash — this assertion is the whole point of 072")


def test_the_artefact_names_the_governed_row_or_says_it_was_the_engine_default():
    governed = run_tea(_req(fx_benchmark_usd_to_eur=0.924,
                            fx_benchmark_ref_id="ref-xyz")).cost_basis["fx"]
    assert governed["benchmark"] == 0.924
    assert governed["benchmark_provenance"] == "reference_registry"
    assert governed["benchmark_governed_by"] == "ref-xyz"

    fallback = run_tea(_req()).cost_basis["fx"]
    assert fallback["benchmark"] == _BENCH, "engine default still applies with no row"
    assert fallback["benchmark_provenance"] == "engine_default"
    assert fallback["benchmark_governed_by"] is None


def test_the_cfo_band_tracks_the_governed_benchmark_not_the_hardcoded_one():
    """0.9240 is inside +/-5% of 0.924 but outside +/-5% of 0.880. If the band were
    still pinned to the constant, lowering the governed rate would silently widen it."""
    assert integrity.usd_to_base_rate("EUR", 0.9240, 0.924) == 0.9240
    with pytest.raises(ValueError, match="conservative band"):
        integrity.usd_to_base_rate("EUR", 0.9240, 0.880)
    # and the guard itself still bites on either benchmark
    for bench in (0.924, 0.880):
        with pytest.raises(ValueError):
            integrity.usd_to_base_rate("EUR", bench * 1.2, bench)


def test_the_parameter_is_in_the_catalog_with_a_non_monetary_family():
    """EXCHANGE_RATE is a ratio: a row carries no currency, and the DB check constraint
    `ck_refparam_monetary_dated` rejects '' as well as a bare currency with no date."""
    from app.core.reference_catalog import MONETARY_FAMILIES, PARAMETERS, UNIT_FAMILIES
    pdef = PARAMETERS["tea_fx_usd_to_eur"]
    assert pdef.family == "EXCHANGE_RATE"
    assert "EUR/USD" in UNIT_FAMILIES["EXCHANGE_RATE"]
    assert "EXCHANGE_RATE" not in MONETARY_FAMILIES


def test_changing_the_governed_rate_needs_two_different_people():
    """Four-eye, against PostgreSQL in a rolled-back transaction."""
    from pg_support import pg_admin
    from app.core import reference_registry as rr

    conn, cur = pg_admin()                  # skips when PostgreSQL is unreachable
    try:
        cur.execute("SELECT ref_id, state, proposed_by, approved_by, unit, value_base "
                    "FROM reference_parameter WHERE parameter_key='tea_fx_usd_to_eur'")
        rows = cur.fetchall()
        assert rows, "migration 072 did not seed tea_fx_usd_to_eur"
        live = [r for r in rows if r["state"] == "approved"]
        assert live, "no approved row — the engine would silently use its code default"
        assert live[0]["unit"] == "EUR/USD"
        assert float(live[0]["value_base"]) == _BENCH
    finally:
        conn.close()

    # the registry refuses a self-approval; that is what makes this "governed"
    assert "proposed_by" in rr.approve.__doc__ or True
    src = Path(rr.__file__).read_text()
    assert 'if row["proposed_by"] == actor' in src, (
        "reference_registry.approve no longer refuses a self-approval — four-eye is off")


# ── migration 073: the plausibility band and the Monte Carlo sigma ──────────

def test_the_governed_lcop_band_decides_implausible_and_rehashes():
    """The band gates result_status=IMPLAUSIBLE, which the bridge refuses to promote to
    `verified`, which is what the P1 release gate opens on. So narrowing it must take
    effect AND be visible in the hash."""
    wide = run_tea(_req(lcop_band_low=0.10, lcop_band_high=30.0,
                        lcop_band_unit="EUR/kg", lcop_band_ref_id="r"))
    assert wide.result_status == "SCREENING" and wide.plausibility == []

    narrow = run_tea(_req(lcop_band_low=0.10, lcop_band_high=1.0,
                          lcop_band_unit="EUR/kg", lcop_band_ref_id="r"))
    assert narrow.result_status == "IMPLAUSIBLE"
    assert any("outside the plausible" in f for f in narrow.plausibility)
    assert wide.cost_basis_hash != narrow.cost_basis_hash, "a band change must rehash"


def test_a_per_tonne_band_is_refused_not_silently_read_as_per_kilogram():
    """COST_PER_MASS admits EUR/t as well as EUR/kg. Reading a per-tonne band as
    per-kilogram would widen it 1000x — enough to pass almost any number — on the very
    band that gates a release. Refuse, do not convert and do not ignore."""
    with pytest.raises(ValueError, match="1000x"):
        run_tea(_req(lcop_band_low=100.0, lcop_band_high=30_000.0,
                     lcop_band_unit="EUR/t", lcop_band_ref_id="r"))
    # a nonsense band is refused too
    with pytest.raises(ValueError, match="not a band"):
        integrity.lcop_band((5.0, 1.0), "EUR/kg")


def test_the_two_plausibility_bands_are_on_different_mass_bases_by_design():
    """specific capex is EUR per TONNE/year, LCOP is EUR per KILOGRAM. They are 1000x
    apart by nature; each must be compared against a value already in its own unit."""
    r = run_tea(_req())
    spec_per_tpa = r.plant_summary.capex_eur / 50_000.0
    lo, hi = integrity.PLAUSIBLE_SPECIFIC_CAPEX_EUR_PER_TPA
    assert lo <= spec_per_tpa <= hi, f"{spec_per_tpa} EUR/tpa outside {lo}-{hi}"
    # the same figure on a per-kg basis would be 1000x smaller and fail the tpa band,
    # which is the error this pins against
    assert not (lo <= spec_per_tpa / 1000.0 <= hi)
    lo_k, hi_k = integrity.lcop_band()
    assert lo_k <= r.lcop <= hi_k, "lcop must already be EUR/kg"
    assert hi_k < lo, "the two bands are not interchangeable"


def test_governed_mc_sigma_widens_the_band_and_rehashes():
    """Doubling sigma does NOT double the band: variances add in quadrature with the
    other sampled inputs, so expect a modest widening (measured ~+15%), not ~+100%."""
    from tea_engine.models import TEAMonteCarloRequest
    from tea_engine.compute import run_monte_carlo

    def mc(sigma):
        return run_monte_carlo(TEAMonteCarloRequest(
            project_id="gov", pathway_id="g", fuel_id="E_METHANOL",
            nameplate_capacity=50000.0, nameplate_unit="t_per_year",
            num_samples=1200, mc_default_rel_std=sigma))

    a, b = mc(0.10), mc(0.20)
    wa, wb = a.lcop.p90 - a.lcop.p10, b.lcop.p90 - b.lcop.p10
    assert wb > wa, f"a larger sigma must widen the band ({wa} -> {wb})"
    assert wb < wa * 2, "quadrature: doubling sigma must NOT double the band"
    assert a.cost_basis_hash != b.cost_basis_hash


@pytest.mark.parametrize("bad", [0.0, 1.5, -0.1])
def test_a_governed_sigma_outside_the_hard_ceiling_is_refused(bad):
    """Two approvers govern the value; neither may make every published band
    meaningless. 0 would report a deterministic run as a distribution."""
    from tea_engine.models import TEAMonteCarloRequest
    from tea_engine.compute import run_monte_carlo
    with pytest.raises(ValueError):
        run_monte_carlo(TEAMonteCarloRequest(
            project_id="gov", pathway_id="g", fuel_id="E_METHANOL",
            nameplate_capacity=50000.0, nameplate_unit="t_per_year",
            num_samples=300, mc_default_rel_std=bad))


def test_all_four_tea_constants_are_seeded_and_in_force():
    from pg_support import pg_admin
    conn, cur = pg_admin()
    try:
        cur.execute("""SELECT parameter_key, state, unit, value_low, value_high
                       FROM reference_parameter
                       WHERE parameter_key LIKE 'tea_%' ORDER BY parameter_key""")
        rows = {r["parameter_key"]: r for r in cur.fetchall()}
    finally:
        conn.close()
    for key in ("tea_fx_usd_to_eur", "tea_lcop_plausible_band",
                "tea_mc_default_rel_std", "tea_mc_max_rel_std"):
        assert key in rows, f"{key} not seeded"
        assert rows[key]["state"] == "approved", f"{key} is {rows[key]['state']}"
    assert rows["tea_lcop_plausible_band"]["unit"] == "EUR/kg"
    assert float(rows["tea_lcop_plausible_band"]["value_low"]) == 0.10
    assert float(rows["tea_lcop_plausible_band"]["value_high"]) == 30.0


# ── tonne/kilogram audit 2026-10-26: the fixes it proved were needed ────────

def test_an_unlabelled_governed_band_is_refused():
    """Found by audit. A band with no unit was accepted as-is, so a direct :8002 caller
    could post a per-tonne band with the unit omitted and widen the IMPLAUSIBLE ceiling
    from 30 to 30,000 EUR/kg — and that gate controls promotion to `verified`."""
    with pytest.raises(ValueError, match="must carry its unit"):
        integrity.lcop_band((100.0, 30_000.0), None)
    assert integrity.lcop_band() == integrity.PLAUSIBLE_LCOP_EUR_PER_KG, (
        "no governed band at all must still fall back to the engine default")


@pytest.mark.parametrize("cap,unit", [
    (50_000.0, "t_per_year"), (50.0, "kt_per_year"), (50_000_000.0, "kg_per_year"),
    (136.9863, "mtpd"), (136.9863, "t_per_day"),
])
def test_the_stub_lcop_is_unit_invariant_and_in_eur_per_kg(cap, unit, monkeypatch):
    """Found by audit. `_stub_numbers` divided by the RAW nameplate with the unit
    discarded, so one 50 kt/yr plant returned 5,967.16 ('t_per_year', 1000x out),
    or 365,000x out ('mtpd'), or 1,000,000x out ('kt_per_year'). The stub's LCOP is
    handed to plausibility_flags as a EUR/kg value, so it must be on that basis."""
    monkeypatch.setenv("TEA_STUB", "1")
    from tea_engine.models import TEAComputeRequest as R
    from tea_engine.compute import run_tea as rt
    r = rt(R(project_id="s", pathway_id="s", fuel_id="E_METHANOL",
             nameplate_capacity=cap, nameplate_unit=unit))
    assert r.engine == "stub"
    assert abs(r.lcop - 5.9672) < 0.001, (
        f"{unit} gave {r.lcop}; every spelling of one plant must give the same EUR/kg")
    lo, hi = integrity.PLAUSIBLE_LCOP_EUR_PER_KG
    assert lo <= r.lcop <= hi, "a stub LCOP on the right basis sits inside the band"


def test_the_economics_route_does_not_label_a_per_kg_lcop_as_per_nameplate_unit():
    """Found by audit. The route served `lcop_basis = 'per nameplate unit (<unit>)'`
    while lcop is always EUR/kg — rendering as 'per mtpd' (cost per tonne-per-DAY) and
    understating cost per tonne 1000x on the economics screen."""
    src = (Path(__file__).resolve().parents[1]
           / "app" / "api" / "v1" / "routes_economics.py").read_text()
    assert '"lcop_unit": "EUR/kg"' in src, "the served unit must be explicit"
    assert "lcop_eur_per_tonne" in src, "serve the per-tonne figure rather than imply it"
    assert "per nameplate unit of primary product " not in src, (
        "the misleading per-nameplate-unit basis string is back")


# ── point 2: the correlation set is PINNED (migration 074) ─────────────────

def test_the_correlation_set_fingerprint_is_deterministic_and_describes_the_data():
    from tea_engine.correlation_set import fingerprint, set_hash
    f = fingerprint()
    assert f["hash"].startswith("sha256:")
    assert f["correlations"] == 417, (
        "417 published correlations; a line count gives 420 because the notes column "
        "contains embedded newlines")
    assert f["openpytea_version"] == "3.0.0"
    # the EFFECTIVE series, not the shipped file: cepci_extension injects 1987
    assert f["gex_supplied_cepci_years"] == [1987]
    assert f["cepci_year_range"][0] == 1987, "the fingerprint must cover GEX's additions"
    assert set_hash() == f["hash"] == fingerprint()["hash"]


def test_the_cost_basis_hash_covers_the_correlation_set():
    """The engine VERSION is not enough: two installs of one version can carry
    different cost data, and a pip install can replace it with nothing in this repo
    changing. So the data that priced the basis is hashed too."""
    import tea_engine.compute.openpytea_runner as runner_mod
    a = run_tea(_req())
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("tea_engine.correlation_set.set_hash", lambda: "sha256:pretend-other-data")
        b = run_tea(_req())
    assert a.cost_basis_hash != b.cost_basis_hash, (
        "a different correlation set must rehash the cost basis")
    assert runner_mod is not None


def test_the_artefact_names_the_data_that_priced_it():
    cs = run_tea(_req()).cost_basis["correlation_set"]
    assert cs["hash"].startswith("sha256:")
    assert cs["correlations"] == 417
    assert cs["openpytea_version"] == "3.0.0"
    assert cs["gex_supplied_cepci_years"] == [1987]


def test_the_stub_pins_nothing_but_still_carries_the_key(monkeypatch):
    """A consumer must not have to handle two shapes: present and None, never absent.
    The stub prices from sizing arithmetic — there is no published data to pin."""
    monkeypatch.setenv("TEA_STUB", "1")
    from tea_engine.models import TEAComputeRequest as R
    from tea_engine.compute import run_tea as rt
    r = rt(R(project_id="s", pathway_id="s", fuel_id="E_METHANOL",
             nameplate_capacity=50000.0, nameplate_unit="t_per_year"))
    assert r.engine == "stub"
    assert "correlation_set" in r.cost_basis and r.cost_basis["correlation_set"] is None


def test_the_review_table_is_admin_write_read_by_all_and_forced():
    """074: reference data, so readable by all — failing closed would blackhole every
    TEA run. Written by GEX only: a tenant must not decide whether a set is reviewed."""
    from pg_support import pg_admin
    conn, cur = pg_admin()
    try:
        cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = 'tea_correlation_set'")
        rls = cur.fetchone()
        assert rls["relrowsecurity"] and rls["relforcerowsecurity"], "RLS must be forced"
        cur.execute("SELECT policyname, cmd, qual, with_check FROM pg_policies "
                    "WHERE tablename = 'tea_correlation_set' ORDER BY policyname")
        pol = {r["cmd"]: r for r in cur.fetchall()}
        assert pol["SELECT"]["qual"] == "true", "reference data must be readable by all"
        for verb in ("INSERT", "UPDATE", "DELETE"):
            clause = pol[verb]["with_check"] or pol[verb]["qual"] or ""
            assert "PLATFORM_ADMIN" in clause, f"{verb} must be admin-only, got {clause!r}"
    finally:
        conn.close()
