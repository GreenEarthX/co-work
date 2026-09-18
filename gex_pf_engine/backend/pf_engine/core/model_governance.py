"""
Model governance for the Gabillon pricing engine.

Three obligations, all append-only:

1. VERSIONING — `GABILLON_MODEL_VERSION` is stamped into every priced
   response. Bump on ANY change to the forward formula, decomposition,
   seed parameters, or invariants — and add a register entry below.

2. RUN AUDIT TRAIL — every priced response carries a `governance` block
   (model version, calibration fingerprint, input hash, run id) and the
   run is logged to an insert-only SQLite table. "Trust the number"
   becomes "reproduce the number".

3. RUNTIME INVARIANTS — the engine refuses to emit outputs that violate
   its own documented properties (GABILLON_MODEL.md §2). The 2026-06-11
   formula bug produced 98–4,676× forward/spot ratios that only a
   FRONTEND sanity check caught; these guards put that net in the engine,
   where it belongs.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

GABILLON_MODEL_VERSION = "1.1.0"

# Human-readable model change register — served via GET /model/changelog.
# Append entries; never rewrite history. `approved_by` is the human who
# signed off the change, not the committer.
MODEL_CHANGE_REGISTER: list[dict[str, Any]] = [
    {
        "version": "1.0.0",
        "effective_date": "2026-05-01",
        "change": "Initial Gabillon two-factor implementation (spot + convenience "
                  "yield, mean-reverting in log space) with green-fuel extensions: "
                  "seasonality, CAPEX-floor pull, SEED parameters per molecule.",
        "reason": "No liquid forward market exists for green molecules; the model "
                  "provides a structural prior for offtake reference pricing.",
        "expected_impact": "Baseline.",
        "approved_by": "jean-marie.lamay",
    },
    {
        "version": "1.1.0",
        "effective_date": "2026-06-11",
        "change": "Forward formula corrected: μ is a LOG PRICE LEVEL, not an annual "
                  "drift rate. Replaced GBM-style τ·μ drift term with mean-reverting "
                  "level term (1−e^{−ατ})(μ−ln S) and convenience-yield term "
                  "−((1−e^{−κτ})/κ)(δ−θ). Decomposition residual now reconciles "
                  "market terms only; cost stack added separately.",
        "reason": "Old formula produced 98–4,676× forward/spot ratios — economically "
                  "impossible; detected by inspection during pricing-lineage debugging.",
        "expected_impact": "Forwards drop from absurd levels to spot-anchored curves "
                  "pulled toward exp(μ); decomposition waterfall residual becomes small.",
        "approved_by": "jean-marie.lamay",
    },
]

# ── Run audit log (append-only) ──────────────────────────────────────────────

_RUNS_DB = os.getenv("GEX_ENGINE_RUNS_DB", "engine_model_runs.db")


def _runs_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_RUNS_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_runs (
            run_id TEXT PRIMARY KEY,
            endpoint TEXT NOT NULL,
            molecule TEXT,
            model_version TEXT NOT NULL,
            calibration_id TEXT NOT NULL,
            calibration_status TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            n_violations INTEGER NOT NULL DEFAULT 0,
            violations_json TEXT,
            computed_at TEXT NOT NULL
        )
    """)
    return conn


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def calibration_fingerprint(params_dict: dict, n_observations: int) -> dict:
    """Identify exactly which parameter set priced this run."""
    return {
        "calibration_id": _stable_hash(params_dict),
        "calibration_status": "MARKET" if n_observations > 0 else "SEED",
        "n_observations": n_observations,
    }


# ── Runtime invariants ───────────────────────────────────────────────────────
# Hard bounds block (HTTP 422 at the route); soft bounds annotate the output.

RATIO_MAX = 20.0   # forward/spot beyond this is economically impossible
RATIO_MIN = 0.05


def check_invariants(
    spot: float,
    points: list[tuple[float, float]],
    capex_floor: Optional[float] = None,
) -> list[dict]:
    """
    points = [(tau_years, forward_eur)]. Returns violations; severity
    'blocking' means the engine must refuse to serve the number.
    """
    violations: list[dict] = []
    for tau, fwd in points:
        if not math.isfinite(fwd):
            violations.append({
                "code": "NON_FINITE", "severity": "blocking", "tau_years": tau,
                "message": f"Forward at τ={tau:.3f}y is not finite ({fwd}).",
            })
            continue
        if fwd <= 0:
            violations.append({
                "code": "NON_POSITIVE", "severity": "blocking", "tau_years": tau,
                "message": f"Forward at τ={tau:.3f}y is {fwd:.2f} ≤ 0.",
            })
            continue
        if spot > 0:
            ratio = fwd / spot
            if ratio > RATIO_MAX or ratio < RATIO_MIN:
                violations.append({
                    "code": "RATIO_BOUND", "severity": "blocking", "tau_years": tau,
                    "message": f"Forward/spot ratio {ratio:.1f}× at τ={tau:.3f}y outside "
                               f"[{RATIO_MIN}, {RATIO_MAX}] — the 2026-06-11 bug class.",
                })
            # Short-end convergence: F(τ→0) → S
            elif tau < 0.1 and abs(ratio - 1.0) > 0.10:
                violations.append({
                    "code": "SHORT_END_DIVERGENCE", "severity": "warning", "tau_years": tau,
                    "message": f"F/S = {ratio:.3f} at τ={tau:.3f}y — short end should "
                               f"converge to spot (±10%).",
                })
        if capex_floor and capex_floor > 0 and fwd < 0.3 * capex_floor:
            violations.append({
                "code": "FAR_BELOW_COST_FLOOR", "severity": "warning", "tau_years": tau,
                "message": f"Forward {fwd:.0f} < 30% of CAPEX floor {capex_floor:.0f} — "
                           f"economically implausible for a cost-anchored molecule.",
            })
    return violations


def blocking(violations: list[dict]) -> list[dict]:
    return [v for v in violations if v["severity"] == "blocking"]


# ── Governance stamp + run logging ───────────────────────────────────────────

def governance_stamp(
    endpoint: str,
    molecule: Optional[str],
    params_dict: dict,
    n_observations: int,
    inputs: dict,
    violations: list[dict],
) -> dict:
    """
    Build the `governance` block for a response and log the run
    (append-only). Logging failure never blocks pricing — the stamp
    is still returned with `run_logged: false`.
    """
    fp = calibration_fingerprint(params_dict, n_observations)
    run_id = uuid.uuid4().hex[:12]
    computed_at = datetime.now(timezone.utc).isoformat()
    stamp = {
        "model_version": GABILLON_MODEL_VERSION,
        **fp,
        "input_hash": _stable_hash(inputs),
        "run_id": run_id,
        "computed_at": computed_at,
        "invariants_checked": True,
        "invariant_warnings": [v for v in violations if v["severity"] == "warning"],
        "run_logged": True,
    }
    try:
        conn = _runs_conn()
        conn.execute(
            "INSERT INTO model_runs (run_id, endpoint, molecule, model_version, calibration_id, "
            "calibration_status, input_hash, n_violations, violations_json, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, endpoint, molecule, GABILLON_MODEL_VERSION, fp["calibration_id"],
             fp["calibration_status"], stamp["input_hash"], len(violations),
             json.dumps(violations) if violations else None, computed_at),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        stamp["run_logged"] = False
    return stamp


def recent_runs(limit: int = 100) -> list[dict]:
    conn = _runs_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM model_runs ORDER BY computed_at DESC LIMIT ?", (min(limit, 500),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Parameter governance ─────────────────────────────────────────────────────
# Parameter changes ARE model changes. Bounds reject absurd calibrations;
# every accepted change is logged old → new, append-only.

PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "alpha":        (0.01, 5.0),    # spot mean-reversion speed (1/years)
    "kappa":        (0.01, 5.0),    # convenience-yield mean-reversion speed
    "mu_base":      (math.log(10.0), math.log(100_000.0)),  # log €/t level
    "sigma_s":      (0.001, 3.0),   # spot vol (annualised)
    "sigma_delta":  (0.0, 3.0),     # convenience-yield vol
    "rho":          (-1.0, 1.0),    # spot/yield correlation
    "theta_0":      (-1.0, 1.0),    # convenience-yield level
}


def validate_params(params_dict: dict) -> list[dict]:
    """Bounds check on a fitted/seeded parameter set. Out-of-bounds = blocking."""
    violations = []
    for name, (lo, hi) in PARAM_BOUNDS.items():
        value = params_dict.get(name)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            violations.append({
                "code": "PARAM_NON_FINITE", "severity": "blocking", "parameter": name,
                "message": f"{name} = {value!r} is not a finite number.",
            })
        elif not (lo <= value <= hi):
            violations.append({
                "code": "PARAM_OUT_OF_BOUNDS", "severity": "blocking", "parameter": name,
                "message": f"{name} = {value:.4f} outside sanity bounds [{lo:.4f}, {hi:.4f}].",
            })
    return violations


def _param_events_conn() -> sqlite3.Connection:
    conn = _runs_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS param_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            molecule TEXT NOT NULL,
            old_calibration_id TEXT,
            new_calibration_id TEXT NOT NULL,
            changed_fields_json TEXT NOT NULL,
            n_observations INTEGER NOT NULL,
            source TEXT NOT NULL,
            at TEXT NOT NULL
        )
    """)
    return conn


def log_param_change(molecule: str, old_params: Optional[dict], new_params: dict,
                     n_observations: int, source: str) -> dict:
    """Append-only register of parameter-set changes (old → new per field)."""
    old_id = _stable_hash(old_params) if old_params else None
    new_id = _stable_hash(new_params)
    changed = {}
    if old_params:
        for k, new_v in new_params.items():
            old_v = old_params.get(k)
            if old_v != new_v and isinstance(new_v, (int, float, str, type(None))):
                changed[k] = {"old": old_v, "new": new_v}
    else:
        changed = {"_initial": {"old": None, "new": "seeded"}}
    try:
        conn = _param_events_conn()
        conn.execute(
            "INSERT INTO param_change_events (molecule, old_calibration_id, new_calibration_id, "
            "changed_fields_json, n_observations, source, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (molecule, old_id, new_id, json.dumps(changed, default=str), n_observations,
             source, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass
    return {"old_calibration_id": old_id, "new_calibration_id": new_id, "changed_fields": changed}


def param_change_history(molecule: Optional[str] = None, limit: int = 100) -> list[dict]:
    conn = _param_events_conn()
    conn.row_factory = sqlite3.Row
    if molecule:
        rows = conn.execute(
            "SELECT * FROM param_change_events WHERE molecule = ? ORDER BY id DESC LIMIT ?",
            (molecule, min(limit, 500)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM param_change_events ORDER BY id DESC LIMIT ?", (min(limit, 500),)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Challenger: engineering cost floor vs market-stochastic forward ─────────
# Two independent derivations of the same number from disjoint assumptions.
# Divergence is the signal — this gate would have caught the 2026-06-11 bug.

CHALLENGER_HIGH_MULTIPLE = 2.0   # forward > 2× cost floor → challenge
CHALLENGER_LOW_FRACTION = 0.6    # forward < 60% of cost floor → challenge


def challenger_assessment(fwd_12m: float, cost_floor: Optional[float]) -> dict:
    """Compare the 12M Gabillon forward against the LCOF engineering floor."""
    if not cost_floor or cost_floor <= 0:
        return {"challenger": "LCOF_COST_FLOOR", "verdict": "NO_FLOOR_AVAILABLE",
                "divergence_pct": None, "cost_floor_eur_t": None}
    ratio = fwd_12m / cost_floor
    if ratio > CHALLENGER_HIGH_MULTIPLE:
        verdict = "CHALLENGED_HIGH"
        note = (f"12M forward is {ratio:.2f}× the engineering cost floor — "
                f"either the market premium assumption or the cost model is wrong.")
    elif ratio < CHALLENGER_LOW_FRACTION:
        verdict = "CHALLENGED_LOW"
        note = (f"12M forward is {ratio:.2f}× the cost floor — pricing below "
                f"producible cost is unsustainable; check calibration.")
    else:
        verdict = "ALIGNED"
        note = f"12M forward within [{CHALLENGER_LOW_FRACTION}×, {CHALLENGER_HIGH_MULTIPLE}×] of the cost floor."
    return {
        "challenger": "LCOF_COST_FLOOR",
        "cost_floor_eur_t": round(cost_floor, 2),
        "forward_12m_eur_t": round(fwd_12m, 2),
        "ratio_to_floor": round(ratio, 3),
        "divergence_pct": round(100 * (ratio - 1), 1),
        "verdict": verdict,
        "note": note,
    }


# ── Benchmark models (deliberately simple) ───────────────────────────────────

def one_factor_forward(mu_base: float, alpha: float, spot: float, tau: float) -> float:
    """Nested challenger: one-factor Schwartz — mean reversion only, no
    convenience yield, no seasonality, no Jensen, no floor pull."""
    e = math.exp(-alpha * tau)
    return math.exp(e * math.log(spot) + (1 - e) * mu_base)


def benchmark_curves(model, params, spot: float, delta: float,
                     cost_floor: Optional[float], tenors_months: list[int]) -> dict:
    """
    Gabillon vs three transparent baselines at each tenor:
      flat        — F = S (the naive curve any model must beat)
      cost_plus   — LCOF floor (engineering derivation)
      one_factor  — nested Schwartz (is the 2nd factor earning its parameters?)
    """
    rows = []
    for m in tenors_months:
        tau = m / 12.0
        gab = model.forward_price(params, spot, delta, tau)
        of = one_factor_forward(params.mu_base, params.alpha, spot, tau)
        rows.append({
            "tenor_months": m,
            "gabillon_eur_t": round(gab, 2),
            "flat_eur_t": round(spot, 2),
            "cost_plus_eur_t": round(cost_floor, 2) if cost_floor else None,
            "one_factor_eur_t": round(of, 2),
            "two_factor_premium_pct": round(100 * (gab / of - 1), 2) if of > 0 else None,
        })
    premiums = [abs(r["two_factor_premium_pct"]) for r in rows if r["two_factor_premium_pct"] is not None]
    return {
        "rows": rows,
        "summary": {
            "max_abs_two_factor_premium_pct": max(premiums) if premiums else None,
            "mean_abs_two_factor_premium_pct": round(sum(premiums) / len(premiums), 2) if premiums else None,
            "interpretation": (
                "two_factor_premium_pct isolates what the convenience-yield factor, "
                "seasonality, Jensen and floor terms add over plain mean reversion. "
                "If it stays near zero everywhere, the extra parameters are not "
                "earning their complexity for this molecule."
            ),
        },
    }


# ── Model card ────────────────────────────────────────────────────────────────
# Served via GET /model/card together with LIVE calibration status, so the
# card can never silently drift from the model.

MODEL_CARD: dict[str, Any] = {
    "name": "GEX Gabillon Two-Factor Forward Curve Engine (green-fuel extended)",
    "model_version_field": "see /model/changelog — stamped on every response",
    "purpose": (
        "Generate forward price curves and price decompositions for green "
        "molecules (H2, e-methanol, e-SAF, e-NH3, …) where no liquid forward "
        "market exists, as a structural reference for offtake negotiation and "
        "scenario analysis."
    ),
    "methodology": (
        "Gabillon (1991) two-factor model — spot and convenience yield, "
        "mean-reverting in log space — extended with seasonality, a CAPEX-floor "
        "pull and learning-rate effects. μ is a log price LEVEL, not a drift rate."
    ),
    "epistemic_status": (
        "Until calibration_status = MARKET for a molecule, outputs are a "
        "STRUCTURAL PRIOR (scenario generator), not a calibrated market model. "
        "Gabillon was built to fit observed oil futures; applied to markets "
        "without futures, its role inverts: it encodes economic structure "
        "(cost floors, mean reversion, seasonality), it does not measure a market."
    ),
    "intended_use": [
        "Indicative reference pricing in offtake negotiation",
        "Scenario and sensitivity analysis (spot overrides, tenor structure)",
        "Cost-driver decomposition (Information Lineage waterfall)",
        "Internal bankability screening alongside the LCOF cost floor",
    ],
    "prohibited_use": [
        "Marking a trading book or any fair-value measurement",
        "Collateral valuation or margin calls",
        "Financial reporting under IFRS 13 / ASC 820",
        "Any binding price commitment without independent validation",
        "Credit decisions without the using institution's own model validation "
        "(SR 11-7 / ECB TRIM obligations sit with the user institution)",
    ],
    "limitations": [
        "SEED parameters are expert priors, not fitted values (n_observations = 0)",
        "No liquid market data exists for most target molecules — backtesting "
        "of price levels is impossible today; structural properties are tested instead",
        "Short end converges to spot × seasonal factor (±10% band), not to spot exactly",
        "Long-run asymptote sits above exp(μ) by Jensen-variance and floor terms "
        "(measured +0.35 to +0.72 in log terms across seeded molecules)",
        "Subsidy/regulatory inputs are user-declared, not verified",
        "Not independently validated (self-assessed; see SECURITY.md posture)",
    ],
    "model_risk_tier": (
        "HIGH — unobservable parameters, no market benchmark, outputs may "
        "inform capital decisions downstream"
    ),
    "governance_controls": [
        "Runtime invariant guards (HTTP 422 on violation) — /model/changelog",
        "Append-only run audit trail — /model/runs",
        "Parameter bounds + append-only parameter change register — /model/param-changes",
        "LCOF cost-floor challenger on every curve — governance.challenger",
        "Property-test suite (40 tests) encoding documented invariants",
    ],
}
