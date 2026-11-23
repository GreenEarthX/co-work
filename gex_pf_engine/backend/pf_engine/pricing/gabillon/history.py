"""
Gabillon two-factor model calibrated to a HISTORICAL index series; P-measure forwards (20 Nov 2026).

JML, 20 Nov 2026: "the CEPCI index limitation ... fails to consider a forward price via a curve.
Calibrate the forward curve using the past CEPCI indices, with the Gabillon forward curve." The
TEA engine prices in a fixed cost year and the published CEPCI ends there, so a quote dated later
cannot be converted. This module supplies the missing years.

Same model as engine.py (GabillonCurveEngine.simulate_paths), in logs Y = ln S, X = ln L:
    dX = (mu_L - sigma_L^2 / 2) dt + sigma_L dW_L
    dY = (kappa (X - Y) - sigma_S^2 / 2) dt + sigma_S dW_S,     corr(dW_S, dW_L) = rho
The spot S is the published index; L, the long-term level it reverts to, is latent. The system
is linear and Gaussian, so it is discretised EXACTLY (Van Loan) over each gap between
observations (CEPCI has 1987 then 1990 onwards) and fitted by maximum likelihood with a Kalman
filter. No market quotes a cost index: there is no market price of risk, so the forward used for
escalation is the P-measure expectation E[S_T] (lambda_S = 0, declared), with a band.

What it is not: a forecast anyone guarantees. ~35 annual points identify mu_L (the long-run
growth) reasonably and kappa, sigma_L, rho weakly; the standard errors and the band say so.
A published index value always replaces the forward for its year.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Sequence

import numpy as np
from scipy.linalg import expm
from scipy.optimize import minimize

from pf_engine.pricing.gabillon.engine import GabillonParams

MEASUREMENT_SD = 0.002          # log noise of a published annual average (0.2%), fixed and declared
# Bounds on the parameters, economically meaningful for an annual cost index. Without them the
# likelihood runs to a degenerate corner (kappa -> 0: the latent level stops influencing the index,
# and sigma_L, rho, mu_L become unidentified). A parameter that ends ON a bound is reported.
BOUNDS = {"kappa": (0.05, 5.0), "sigma_S": (0.002, 0.5), "sigma_L": (0.002, 0.5), "rho": (-0.95, 0.95),
          "mu_L": (-0.05, 0.15)}
PRIOR_L_SD = 0.5                # diffuse-ish prior on the latent long-term level at the first year
Z90 = 1.6448536269514722


def _system(p: GabillonParams, dt: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(Phi, c, Q): z_{t+dt} = Phi z_t + c + eta, eta ~ N(0, Q), exact for the linear SDE."""
    A = np.array([[-p.kappa, p.kappa], [0.0, 0.0]])
    b = np.array([-0.5 * p.sigma_S ** 2, p.mu_L - 0.5 * p.sigma_L ** 2])
    cov = p.rho * p.sigma_S * p.sigma_L
    S = np.array([[p.sigma_S ** 2, cov], [cov, p.sigma_L ** 2]])
    M = np.zeros((3, 3))
    M[:2, :2], M[:2, 2] = A, b
    E = expm(M * dt)
    Phi, c = E[:2, :2], E[:2, 2]
    V = np.zeros((4, 4))
    V[:2, :2], V[:2, 2:], V[2:, 2:] = -A, S, A.T
    F = expm(V * dt)
    Q = F[2:, 2:].T @ F[:2, 2:]
    return Phi, c, 0.5 * (Q + Q.T)


def _params(theta: Sequence[float]) -> GabillonParams:
    lk, lss, lsl, arho, mu = theta
    return GabillonParams(kappa=math.exp(lk), sigma_S=math.exp(lss), sigma_L=math.exp(lsl),
                          rho=math.tanh(arho), mu_L=mu, lambda_S=0.0)


def _filter(p: GabillonParams, years: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """(log-likelihood of observations 2..n, filtered mean, filtered covariance at the last year)."""
    H = np.array([1.0, 0.0])
    systems: dict = {}
    R = MEASUREMENT_SD ** 2
    m = np.array([y[0], y[0]])
    P = np.diag([R, PRIOR_L_SD ** 2])
    ll = 0.0
    for k in range(1, len(y)):
        dt = float(years[k] - years[k - 1])
        if dt not in systems:
            systems[dt] = _system(p, dt)
        Phi, c, Q = systems[dt]
        m = Phi @ m + c
        P = Phi @ P @ Phi.T + Q
        v = y[k] - H @ m
        s = H @ P @ H + R
        if s <= 0:
            return -1e12, m, P
        K = P @ H / s
        m = m + K * v
        P = P - np.outer(K, H @ P)
        ll += -0.5 * (math.log(2 * math.pi * s) + v * v / s)
    return ll, m, P


def calibrate(years: Sequence[int], values: Sequence[float]) -> dict:
    """Maximum likelihood over (kappa, sigma_S, sigma_L, rho, mu_L), several starts."""
    yr = np.asarray(years, float)
    order = np.argsort(yr)
    yr, y = yr[order], np.log(np.asarray(values, float)[order])
    if len(y) < 10 or np.any(np.diff(yr) <= 0):
        raise ValueError("calibrate needs at least 10 strictly increasing yearly observations")
    growth = (y[-1] - y[0]) / (yr[-1] - yr[0])

    def nll(theta):
        try:
            ll, _, _ = _filter(_params(theta), yr, y)
        except (np.linalg.LinAlgError, ValueError, OverflowError):
            return 1e12
        return -ll if np.isfinite(ll) else 1e12

    b = BOUNDS
    tb = [(math.log(b["kappa"][0]), math.log(b["kappa"][1])), (math.log(b["sigma_S"][0]), math.log(b["sigma_S"][1])),
          (math.log(b["sigma_L"][0]), math.log(b["sigma_L"][1])), (math.atanh(b["rho"][0]), math.atanh(b["rho"][1])),
          b["mu_L"]]
    best = None
    for k0 in (0.2, 1.0, 3.0):
        for r0 in (-0.3, 0.3):
            x0 = [math.log(k0), math.log(0.04), math.log(0.02), math.atanh(r0), min(max(growth, -0.04), 0.14)]
            res = minimize(nll, x0, method="L-BFGS-B", bounds=tb)
            if best is None or res.fun < best.fun:
                best = res
    theta = best.x
    p = _params(theta)
    ll, m, P = _filter(p, yr, y)
    at_bound = [name for name, (lo, hi), v in zip(("kappa", "sigma_S", "sigma_L", "rho", "mu_L"), tb, theta)
                if abs(v - lo) < 1e-6 or abs(v - hi) < 1e-6]
    return {"params": p, "theta": theta, "loglik": ll, "state_mean": m, "state_cov": P,
            "last_year": int(yr[-1]), "first_year": int(yr[0]), "n": int(len(y)), "at_bound": at_bound,
            "standard_errors": _standard_errors(nll, theta, at_bound), "observed_growth": growth}


def _standard_errors(nll, theta: np.ndarray, at_bound: Sequence[str] = ()) -> dict:
    """Approximate SEs from a numerical Hessian over the parameters NOT on a bound, natural scale."""
    names = ("kappa", "sigma_S", "sigma_L", "rho", "mu_L")
    free = [i for i, n_ in enumerate(names) if n_ not in at_bound]
    full = np.array(theta, float)

    def sub_nll(x):
        t = full.copy()
        t[free] = x
        return nll(t)
    out = _hessian_se(sub_nll, full[free])
    se = dict.fromkeys(names)
    lk, lss, lsl, arho, _ = theta
    scale = {"kappa": math.exp(lk), "sigma_S": math.exp(lss), "sigma_L": math.exp(lsl),
             "rho": 1 - math.tanh(arho) ** 2, "mu_L": 1.0}
    for i, sd in zip(free, out):
        se[names[i]] = None if sd is None else scale[names[i]] * sd
    return se


def _hessian_se(nll, theta: np.ndarray) -> list:
    n, h = len(theta), 1e-4
    Hm = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            e_i, e_j = np.eye(n)[i] * h, np.eye(n)[j] * h
            Hm[i, j] = (nll(theta + e_i + e_j) - nll(theta + e_i - e_j)
                        - nll(theta - e_i + e_j) + nll(theta - e_i - e_j)) / (4 * h * h)
    try:
        diag = np.diag(np.linalg.inv(Hm))
    except np.linalg.LinAlgError:
        return [None] * n
    return [math.sqrt(d) if d > 0 else None for d in diag]


def p_forward(fit: dict, horizon_years: int) -> list[dict]:
    """E[S] and a 90% band for each year after the last observation, P-measure, with the
    filtered uncertainty of the latent level carried forward."""
    p = fit["params"]
    out = []
    for tau in range(1, horizon_years + 1):
        Phi, c, Q = _system(p, float(tau))
        m = Phi @ fit["state_mean"] + c
        V = Phi @ fit["state_cov"] @ Phi.T + Q
        mY, vY = float(m[0]), float(max(V[0, 0], 0.0))
        out.append({"year": fit["last_year"] + tau, "expected": math.exp(mY + 0.5 * vY),
                    "p05": math.exp(mY - Z90 * math.sqrt(vY)), "p95": math.exp(mY + Z90 * math.sqrt(vY)),
                    "median": math.exp(mY)})
    return out


def history_forward(series: Sequence[dict], horizon_years: int, index_name: str, source: str) -> dict:
    """The calibration and the forward table, with provenance."""
    years = [int(s["year"]) for s in series]
    values = [float(s["value"]) for s in series]
    fit = calibrate(years, values)
    p = fit["params"]
    return {
        "index": index_name,
        "measure": "P",
        "model": "Gabillon (1991) two-factor, spot reverting to a drifting long-term level (pf_engine.pricing.gabillon)",
        "calibration": {"method": "Kalman-filter maximum likelihood, exact discretisation over each gap",
                        "observations": fit["n"], "first_year": fit["first_year"], "last_year": fit["last_year"],
                        "source": source, "loglik": fit["loglik"],
                        "params": {k: float(v) for k, v in asdict(p).items() if k != "lambda_S"},
                        "standard_errors": fit["standard_errors"], "bounds": BOUNDS,
                        "parameters_on_a_bound": fit["at_bound"],
                        "observed_log_growth_per_year": fit["observed_growth"],
                        "filtered_long_term_level": math.exp(float(fit["state_mean"][1])),
                        "fixed": {"lambda_S": 0.0, "measurement_sd": MEASUREMENT_SD, "prior_L_sd": PRIOR_L_SD}},
        "forward": p_forward(fit, horizon_years),
        "provenance": {"lambda_S": "fixed 0: a cost index has no market price of risk; the forward is E_P[S_T]",
                       "forward": "MODEL: replaced by the published value for its year as soon as one exists",
                       "band": "90% P-measure interval from the calibrated dynamics and the filtered state"},
    }
