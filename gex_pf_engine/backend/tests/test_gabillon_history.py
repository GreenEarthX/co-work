"""Gabillon calibrated to a historical index series (pricing/gabillon/history.py, 20 Nov 2026)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from pf_engine.pricing.gabillon.engine import PARAM_ORDER, GabillonCurveEngine, GabillonParams
from pf_engine.pricing.gabillon import history as h


def _simulate(p: GabillonParams, years: int, S0=400.0, L0=420.0, seed=7):
    rng = np.random.default_rng(seed)
    y, x, out = math.log(S0), math.log(L0), []
    for _ in range(years):
        Phi, c, Q = h._system(p, 1.0)
        z = Phi @ np.array([y, x]) + c + rng.multivariate_normal([0, 0], Q)
        y, x = z
        out.append(math.exp(y))
    return out


def test_the_long_run_growth_is_recovered_from_a_simulated_history():
    true = GabillonParams(kappa=0.8, sigma_S=0.04, sigma_L=0.02, rho=0.2, mu_L=0.03, lambda_S=0.0)
    vals = _simulate(true, 40)
    fit = h.calibrate(list(range(1985, 2025)), vals)
    assert abs(fit["params"].mu_L - 0.03) < 0.02
    assert fit["standard_errors"]["mu_L"] is not None


def test_the_closed_form_p_expectation_matches_the_curve_engines_own_monte_carlo():
    p = GabillonParams(kappa=0.5, sigma_S=0.06, sigma_L=0.03, rho=0.3, mu_L=0.025, lambda_S=0.0)
    S0, L0 = 800.0, 900.0
    cfg = {"market_state": {"spot": S0, "long_term_anchor": L0},
           "params": {k: {"value": getattr(p, k), "status": "test", "min": -10, "max": 10} for k in PARAM_ORDER},
           "simulation": {"n_paths": 40000, "steps_per_year": 52, "horizon_years": 3, "seed": 11,
                          "cone_quantiles": [0.05, 0.95]}}
    sim = GabillonCurveEngine(cfg).simulate_paths(measure="P", use_policy=False)
    mc = {round(t, 6): v for t, v in zip(sim["tau"], sim["S"].mean(axis=1))}
    fit = {"params": p, "state_mean": np.array([math.log(S0), math.log(L0)]), "state_cov": np.zeros((2, 2)),
           "last_year": 2024}
    for f in h.p_forward(fit, 3):
        tau = f["year"] - 2024
        assert f["expected"] == pytest.approx(mc[round(float(tau), 6)], rel=0.01)   # Euler weekly vs exact


def test_a_degenerate_corner_is_bounded_and_reported_and_too_short_a_series_refused():
    flat = [500 * (1.02 ** i) for i in range(20)]                 # no noise at all
    fit = h.calibrate(list(range(2000, 2020)), flat)
    assert fit["params"].kappa >= h.BOUNDS["kappa"][0] - 1e-9
    assert fit["at_bound"]                                         # the data cannot identify everything: said
    with pytest.raises(ValueError):
        h.calibrate([2020, 2021, 2022], [1, 2, 3])


def test_the_route_returns_the_forward_with_its_provenance(service_client):
    client = service_client
    series = [{"year": 1990 + i, "value": 360 * (1.024 ** i) * (1 + 0.03 * math.sin(i))} for i in range(35)]
    r = client.post("/pf/index/forward", json={"index_name": "TEST index", "source": "synthetic",
                                               "series": series, "horizon_years": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [f["year"] for f in body["forward"]] == [2025, 2026]
    assert all(f["p05"] < f["expected"] < f["p95"] for f in body["forward"])
    assert body["measure"] == "P" and "lambda_S" in body["provenance"]
    bad = client.post("/pf/index/forward", json={"index_name": "x", "source": "x", "series": series[:5]})
    assert bad.status_code == 422
