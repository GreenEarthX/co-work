"""
Property tests for Gabillon model invariants (GABILLON_MODEL.md §2)
and the runtime guards in model_governance.py.

These are the executable form of the documented "audit checks". The
2026-06-11 formula bug (98–4,676× forward/spot) would have failed
test_forward_spot_ratio_bounded on every molecule — this suite is the
regression net for that bug class.
"""

import math

import pytest

from app.core.gabillon import SEED_PARAMS, GabillonModel
from app.core.model_governance import (
    GABILLON_MODEL_VERSION,
    MODEL_CHANGE_REGISTER,
    RATIO_MAX,
    RATIO_MIN,
    blocking,
    check_invariants,
)

MODEL = GabillonModel()

# Spot scenarios per molecule: at equilibrium, well below, well above.
def _spots(params):
    eq = math.exp(params.mu_base)
    return [eq, eq * 0.5, eq * 1.8]


TENORS_Y = [1 / 12, 0.25, 0.5, 1, 2, 3, 5, 10]


@pytest.mark.parametrize("molecule", sorted(SEED_PARAMS.keys()))
def test_short_end_anchors_at_spot_within_seasonal_band(molecule):
    """F(τ→0) → S × seasonal(t). The forward is SEASONAL, so exact spot
    convergence is wrong — the true invariant is the seasonal band:
    measured F(0)/S across all seeded molecules is 0.95–1.09."""
    params = SEED_PARAMS[molecule]
    for spot in _spots(params):
        fwd = MODEL.forward_price(params, spot, 0.02, 1e-6)
        assert math.isfinite(fwd)
        assert 0.85 < fwd / spot < 1.15, (
            f"{molecule}: F(τ≈0)/S = {fwd / spot:.3f} outside the seasonal band "
            f"— short-end anchoring is broken"
        )


@pytest.mark.parametrize("molecule", sorted(SEED_PARAMS.keys()))
def test_forward_spot_ratio_bounded(molecule):
    """No tenor up to 10y may produce an economically impossible ratio.

    Regression net for the 2026-06-11 τ·μ drift bug (98–4,676×)."""
    params = SEED_PARAMS[molecule]
    for spot in _spots(params):
        for tau in TENORS_Y:
            fwd = MODEL.forward_price(params, spot, 0.02, tau)
            assert math.isfinite(fwd), f"{molecule} τ={tau}: non-finite forward"
            assert fwd > 0, f"{molecule} τ={tau}: forward {fwd} ≤ 0"
            ratio = fwd / spot
            assert RATIO_MIN < ratio < RATIO_MAX, (
                f"{molecule} τ={tau}y spot={spot:.0f}: F/S={ratio:.1f}× "
                f"outside [{RATIO_MIN}, {RATIO_MAX}]"
            )


@pytest.mark.parametrize("molecule", sorted(SEED_PARAMS.keys()))
def test_mean_reversion_pulls_up_from_below_to_bounded_asymptote(molecule):
    """Starting at 0.5×equilibrium the curve must rise (pull direction), and
    the 10y point must stay within e^1 of μ. The asymptote sits ABOVE μ by
    the Jensen variance + CAPEX-floor terms (GABILLON_MODEL.md §2) — measured
    ln F(10y) − μ is +0.35…+0.72 across seeded molecules — so 'distance to μ
    shrinks monotonically' is NOT an invariant of this model; boundedness and
    direction are."""
    params = SEED_PARAMS[molecule]
    eq = math.exp(params.mu_base)
    spot = eq * 0.5  # start well below equilibrium
    f_q = MODEL.forward_price(params, spot, 0.02, 0.25)
    f_2y = MODEL.forward_price(params, spot, 0.02, 2.0)
    f_10y = MODEL.forward_price(params, spot, 0.02, 10.0)
    assert f_2y > f_q, (
        f"{molecule}: from 0.5×eq the curve must rise (F(2y)={f_2y:.0f} ≤ F(3M)={f_q:.0f})"
    )
    assert abs(math.log(f_10y) - params.mu_base) < 1.0, (
        f"{molecule}: ln F(10y) − μ = {math.log(f_10y) - params.mu_base:+.3f} — "
        f"long end unbounded relative to equilibrium"
    )


class TestInvariantGuards:
    def test_catches_the_2026_06_11_bug_class(self):
        """A 98× forward/spot ratio must be a BLOCKING violation."""
        v = check_invariants(800.0, [(1.0, 800.0 * 98)])
        assert blocking(v), "98× ratio not blocked — the shipped bug would pass again"
        assert any(x["code"] == "RATIO_BOUND" for x in v)

    def test_catches_non_finite(self):
        v = check_invariants(800.0, [(1.0, float("nan"))])
        assert any(x["code"] == "NON_FINITE" and x["severity"] == "blocking" for x in v)

    def test_catches_non_positive(self):
        v = check_invariants(800.0, [(1.0, -5.0)])
        assert any(x["code"] == "NON_POSITIVE" and x["severity"] == "blocking" for x in v)

    def test_sane_curve_passes_clean(self):
        v = check_invariants(800.0, [(0.5, 820.0), (1.0, 850.0), (5.0, 1100.0)])
        assert blocking(v) == []

    def test_short_end_divergence_warns_not_blocks(self):
        v = check_invariants(800.0, [(0.05, 1000.0)])
        assert blocking(v) == []
        assert any(x["code"] == "SHORT_END_DIVERGENCE" for x in v)


class TestParameterGovernance:
    def test_seed_params_pass_bounds(self):
        """Every seeded parameter set must satisfy its own sanity bounds."""
        from app.core.model_governance import validate_params
        for mol, p in SEED_PARAMS.items():
            d = {"alpha": p.alpha, "kappa": p.kappa, "mu_base": p.mu_base,
                 "sigma_s": p.sigma_s, "sigma_delta": p.sigma_delta,
                 "rho": p.rho, "theta_0": p.theta_0}
            assert validate_params(d) == [], f"{mol}: seed params violate bounds"

    def test_absurd_params_blocked(self):
        from app.core.model_governance import validate_params
        v = validate_params({"alpha": -1.0, "rho": 2.0, "mu_base": math.log(5.0)})
        codes = {x["parameter"] for x in v}
        assert codes == {"alpha", "rho", "mu_base"}
        assert all(x["severity"] == "blocking" for x in v)


class TestChallenger:
    def test_aligned_within_band(self):
        from app.core.model_governance import challenger_assessment
        assert challenger_assessment(900.0, 800.0)["verdict"] == "ALIGNED"

    def test_2026_06_11_bug_is_challenged_high(self):
        """A 98× forward against an €800 floor must be CHALLENGED_HIGH."""
        from app.core.model_governance import challenger_assessment
        a = challenger_assessment(800.0 * 98, 800.0)
        assert a["verdict"] == "CHALLENGED_HIGH"

    def test_below_cost_is_challenged_low(self):
        from app.core.model_governance import challenger_assessment
        assert challenger_assessment(300.0, 800.0)["verdict"] == "CHALLENGED_LOW"

    def test_no_floor_is_explicit(self):
        from app.core.model_governance import challenger_assessment
        assert challenger_assessment(900.0, None)["verdict"] == "NO_FLOOR_AVAILABLE"


class TestBenchmarkModels:
    def test_one_factor_converges_to_equilibrium(self):
        """The nested challenger must hit exp(μ) exactly at the long end."""
        from app.core.model_governance import one_factor_forward
        mu = math.log(800.0)
        f = one_factor_forward(mu, 1.2, 400.0, 50.0)
        assert abs(f - 800.0) < 1.0

    def test_one_factor_anchors_at_spot(self):
        from app.core.model_governance import one_factor_forward
        f = one_factor_forward(math.log(800.0), 1.2, 400.0, 1e-9)
        assert abs(f - 400.0) < 0.01

    @pytest.mark.parametrize("molecule", sorted(SEED_PARAMS.keys()))
    def test_benchmark_rows_finite(self, molecule):
        from app.core.model_governance import benchmark_curves
        p = SEED_PARAMS[molecule]
        spot = math.exp(p.mu_base)
        b = benchmark_curves(MODEL, p, spot, 0.02, p.capex_floor_eur_t, [1, 12, 60])
        for r in b["rows"]:
            assert math.isfinite(r["gabillon_eur_t"]) and r["gabillon_eur_t"] > 0
            assert math.isfinite(r["one_factor_eur_t"]) and r["one_factor_eur_t"] > 0


class TestChangeRegister:
    def test_current_version_is_registered(self):
        versions = [e["version"] for e in MODEL_CHANGE_REGISTER]
        assert GABILLON_MODEL_VERSION in versions, (
            "MODEL_VERSION bumped without a register entry — the register is "
            "the audit source, not git"
        )

    def test_entries_carry_governance_fields(self):
        for e in MODEL_CHANGE_REGISTER:
            for field in ("version", "effective_date", "change", "reason",
                          "expected_impact", "approved_by"):
                assert e.get(field), f"register entry {e.get('version')} missing {field}"
