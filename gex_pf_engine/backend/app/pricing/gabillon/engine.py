"""
GEX Gabillon Curve Engine  -  Module 1 of the green-fuel valuation backend.

Scope (locked spec):
  - Gabillon (1991) two-factor forward curve, closed form for the Q pricing curve.
  - P-measure scenario forecast + cone by Monte Carlo (the customer's "where will
    the price go" object), distinct from the Q pricing curve. lambda_S is the wedge.
  - Policy layer:  (2) Markov regime switching on the long-term factor L
                   (3) deterministic manual scenario branches on top.
  - HLR logistics overlay: Henaff-Laachir-Russo storage value repurposed as a
    logistics-optionality proxy, reported as a model-risk *band*, not a point.
  - LCOF-anchored calibration (fundamental target), never dressed as fit-to-market.
  - Calibration WITH MEMORY: results persisted with provenance; optimizer warm-starts
    from the last calibrated parameters.
  - Dormant EKF/UKF hook: swap the calibration target from LCOF to a market futures
    panel the day a liquid index exists, without touching the model.
  - Provenance flags on every output: assumed quantities are declared, never concealed.

Inputs are NOT hard-coded; they live in gabillon_config.json. Edit values, not code.

Dependencies: numpy, scipy.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional, Protocol, Sequence

import numpy as np
from scipy.optimize import least_squares

from app.pricing.memory import ProjectCalibrationMemory


# --------------------------------------------------------------------------- #
#  Parameters and market state
# --------------------------------------------------------------------------- #
PARAM_ORDER = ("kappa", "sigma_S", "sigma_L", "rho", "mu_L", "lambda_S")


@dataclass
class GabillonParams:
    kappa: float       # mean-reversion speed of spot toward L
    sigma_S: float     # short-term (spot) volatility
    sigma_L: float     # long-term volatility
    rho: float         # corr(dW_S, dW_L)
    mu_L: float        # long-term drift of L under the physical measure P
    lambda_S: float    # market price of spot risk  ->  the P -> Q wedge

    def as_array(self) -> np.ndarray:
        return np.array([getattr(self, k) for k in PARAM_ORDER], dtype=float)

    @classmethod
    def from_array(cls, a: Sequence[float]) -> "GabillonParams":
        return cls(**dict(zip(PARAM_ORDER, [float(x) for x in a])))


@dataclass
class MarketState:
    spot: float          # S0  ($/MT)
    long_term: float     # L0  ($/MT)  the Gabillon reversion level


# --------------------------------------------------------------------------- #
#  Closed-form Gabillon forward  (this is the Q / pricing curve)
# --------------------------------------------------------------------------- #
def gabillon_forward(S0: float, L0: float, tau, p: GabillonParams):
    """
    Q-measure forward F(S,L,tau) = A(tau) * S0^B(tau) * L0^(1-B(tau))   (Gabillon 1991).
    Vectorised in tau. Used for pricing and as the fast calibration target evaluator.
    """
    tau = np.asarray(tau, dtype=float)
    B = np.exp(-p.kappa * tau)
    nu = p.sigma_S ** 2 + p.sigma_L ** 2 - 2.0 * p.rho * p.sigma_S * p.sigma_L
    A = np.exp(
        (p.lambda_S * p.sigma_S / p.kappa) * (np.exp(-p.kappa * tau) - 1.0)
        + (nu / (4.0 * p.kappa)) * (2.0 * np.exp(-p.kappa * tau)
                                    - np.exp(-2.0 * p.kappa * tau) - 1.0)
    )
    return A * (S0 ** B) * (L0 ** (1.0 - B))


# --------------------------------------------------------------------------- #
#  Policy layer:  regimes (2) + manual branches (3)
# --------------------------------------------------------------------------- #
@dataclass
class RegimeModel:
    names: list[str]
    mu_L: np.ndarray                 # long-term drift per state
    level_mult: np.ndarray           # one-off jump applied to L on entering state
    rate: np.ndarray                 # CTMC rate matrix (per year), off-diagonal
    initial: int

    @classmethod
    def from_config(cls, cfg: dict) -> Optional["RegimeModel"]:
        if not cfg or not cfg.get("enabled"):
            return None
        states = cfg["states"]
        names = [s["name"] for s in states]
        idx = {n: i for i, n in enumerate(names)}
        n = len(names)
        mu_L = np.array([s["mu_L"] for s in states], float)
        lvl = np.array([s.get("level_mult_on_entry", 1.0) for s in states], float)
        rate = np.zeros((n, n))
        for src, targets in cfg.get("annual_transition_rates", {}).items():
            for dst, r in targets.items():
                rate[idx[src], idx[dst]] = r
        return cls(names, mu_L, lvl, rate, idx[cfg.get("initial_state", names[0])])


@dataclass
class ManualBranch:
    time: float
    target: str          # "L" or "S"
    multiplier: float
    label: str


# --------------------------------------------------------------------------- #
#  HLR logistics overlay  (storage value -> logistics optionality proxy)
# --------------------------------------------------------------------------- #
@dataclass
class HLRLogisticsOverlay:
    enabled: bool
    deliverability: str
    deliverability_factor: dict
    location_spread_vol: float
    model_risk_band_pct: float

    def value_band(self, taus: np.ndarray, curve: np.ndarray) -> dict:
        """
        Logistics optionality value per maturity, expressed as a band.

        Intuition (HLR): storage is worth the option to inject cheap / withdraw dear,
        gated by deliverability. Here the molecule's *transport* deliverability gates
        the option to move it from production node to consumption node. Fast transport
        (pipeline/shipping available) ~ fast storage; stranded molecule ~ slow storage.

        Value scales like a location/timing spread option: factor * spread_vol *
        sqrt(tau) * curve. Reported low/central/high because HLR's headline result is
        that a large slice of storage value is pure model choice -> we never pretend a
        point estimate.
        """
        f = self.deliverability_factor.get(self.deliverability, 0.0)
        central = f * self.location_spread_vol * np.sqrt(taus) * curve
        band = self.model_risk_band_pct
        return {
            "deliverability": self.deliverability,
            "central": central,
            "low": central * (1.0 - band),
            "high": central * (1.0 + band),
        }


# --------------------------------------------------------------------------- #
#  Calibration target abstraction  (LCOF today; market panel = dormant hook)
# --------------------------------------------------------------------------- #
class CalibrationTarget(Protocol):
    source: str
    def taus(self) -> np.ndarray: ...
    def values(self) -> np.ndarray: ...
    def residuals(self, model_curve: np.ndarray) -> np.ndarray: ...


@dataclass
class LCOFTarget:
    """Fundamental anchor: the Levelized-Cost-Of-Fuel curve. NOT a market panel."""
    source: str
    _taus: np.ndarray
    prices: np.ndarray
    weights: np.ndarray

    @classmethod
    def from_config(cls, cfg: dict) -> "LCOFTarget":
        pts = sorted(cfg["lcof_curve"], key=lambda d: d["tau"])
        t = np.array([p["tau"] for p in pts], float)
        px = np.array([p["price"] for p in pts], float)
        return cls("LCOF_fundamental", t, px, np.ones_like(px))

    def taus(self) -> np.ndarray:
        return self._taus

    def values(self) -> np.ndarray:
        return self.prices

    def residuals(self, model_curve: np.ndarray) -> np.ndarray:
        return self.weights * (model_curve - self.prices)


@dataclass
class MarketPanelTarget:
    """
    DORMANT. Activate the day a liquid green-fuel futures panel exists. This is the
    swap point for an EKF/UKF state-space calibration: same model, the estimator and
    target change, the curve math does not. Intentionally not implemented.
    """
    source: str = "MARKET_PANEL_DORMANT"
    def taus(self) -> np.ndarray:
        raise NotImplementedError(
            "Market-panel / EKF-UKF calibration is dormant: no liquid green-fuel "
            "term structure exists yet. Activate when one does."
        )
    def values(self) -> np.ndarray:
        raise NotImplementedError
    def residuals(self, model_curve: np.ndarray) -> np.ndarray:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#  Calibration memory  (persist + warm-start)
# --------------------------------------------------------------------------- #
class CalibrationMemory(ProjectCalibrationMemory):
    """Compatibility alias for the project-scoped memory store."""


# --------------------------------------------------------------------------- #
#  The engine
# --------------------------------------------------------------------------- #
class GabillonCurveEngine:
    def __init__(
        self,
        config: dict,
        memory_store: Optional[ProjectCalibrationMemory] = None,
        project_id: Optional[str] = None,
    ):
        self.cfg = config
        self.project_id = project_id or config.get("project_id") or "default"
        ms = config["market_state"]
        self.market = MarketState(ms["spot"], ms["long_term_anchor"])

        pc = config["params"]
        self.params = GabillonParams(**{k: pc[k]["value"] for k in PARAM_ORDER})
        self.param_status = {k: pc[k]["status"] for k in PARAM_ORDER}
        self.bounds = {k: (pc[k]["min"], pc[k]["max"]) for k in PARAM_ORDER}

        self.regimes = RegimeModel.from_config(config.get("policy_regimes"))
        mb = config.get("manual_branches", {})
        self.branches = (
            [ManualBranch(b["time"], b["target"], b["multiplier"], b.get("label", ""))
             for b in mb.get("branches", [])]
            if mb.get("enabled") else []
        )

        ho = config.get("hlr_logistics_overlay", {})
        self.hlr = HLRLogisticsOverlay(
            ho.get("enabled", False), ho.get("deliverability", "medium"),
            ho.get("deliverability_factor", {}), ho.get("location_spread_vol", 0.0),
            ho.get("model_risk_band_pct", 0.0),
        ) if ho.get("enabled") else None

        self.memory = memory_store or CalibrationMemory()
        self.last_fit: Optional[dict] = None

    # ---- provenance ------------------------------------------------------- #
    def _provenance(self) -> dict:
        prov = dict(self.param_status)
        prov["spot"] = "input"
        prov["long_term_anchor"] = "input"
        if self.last_fit:
            prov["calibration_target"] = self.last_fit["target_source"]
        prov["_warning"] = (
            "Forward curve is anchored to a FUNDAMENTAL (LCOF) target, not a liquid "
            "market panel. Second factor is assumed, not identified. Treat fit stats "
            "as fundamental consistency, not market calibration."
        )
        return prov

    # ---- Q pricing curve -------------------------------------------------- #
    def pricing_curve(self, taus: Sequence[float]) -> dict:
        taus = np.asarray(taus, float)
        f = gabillon_forward(self.market.spot, self.market.long_term, taus, self.params)
        out = {"measure": "Q", "tau": taus.tolist(), "forward": f.tolist(),
               "seed": self.cfg["simulation"]["seed"], "provenance": self._provenance()}
        if self.hlr:
            band = self.hlr.value_band(taus, f)
            out["logistics_value"] = {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                                      for k, v in band.items()}
        return out

    # ---- core Monte Carlo, reused by the forecast AND by module 2 --------- #
    def simulate_paths(self, measure: str = "P", n_paths: Optional[int] = None,
                       steps_per_year: Optional[int] = None,
                       horizon_years: Optional[float] = None,
                       seed: Optional[int] = None,
                       use_policy: Optional[bool] = None) -> dict:
        """
        Simulate spot paths in log space.

        measure='P'  -> physical: L drifts at mu_L, regimes + manual branches ON
                        (the forecast object).
        measure='Q'  -> risk-neutral: L is a martingale (drift 0), spot carries the
                        -lambda_S*sigma_S premium, policy layer OFF by default because
                        regime risk premia are unobservable. This is the object module 2
                        prices options against.

        Returns S of shape (nstep, n_paths) plus the tau grid and (under P) the regime
        state path. Deterministic for a fixed seed -> reproducible for audit.
        """
        sim = self.cfg["simulation"]
        n = int(n_paths or sim["n_paths"])
        spy = int(steps_per_year or sim["steps_per_year"])
        T = float(horizon_years or sim["horizon_years"])
        seed = int(seed if seed is not None else sim["seed"])
        nstep = int(round(T * spy))
        dt = 1.0 / spy
        rng = np.random.default_rng(seed)
        p = self.params

        if use_policy is None:
            use_policy = (measure == "P")
        use_reg = bool(use_policy and self.regimes is not None)
        use_br = bool(use_policy and self.branches)

        Y = np.full(n, math.log(self.market.spot))
        X = np.full(n, math.log(self.market.long_term))
        state = np.full(n, self.regimes.initial) if use_reg else None
        chol = np.array([[1.0, 0.0],
                         [p.rho, math.sqrt(max(1e-12, 1.0 - p.rho ** 2))]])
        taus = np.arange(1, nstep + 1) * dt
        S_path = np.empty((nstep, n))
        regime_state = np.empty((nstep, n), dtype=int) if use_reg else None
        branch_steps = {int(round(b.time * spy)): b for b in self.branches} if use_br else {}

        for k in range(nstep):
            z = rng.standard_normal((n, 2)) @ chol.T
            dW_S, dW_L = z[:, 0] * math.sqrt(dt), z[:, 1] * math.sqrt(dt)

            if use_reg:
                R = self.regimes.rate
                u = rng.random(n)
                new_state = state.copy()
                for s in range(len(self.regimes.names)):
                    mask = state == s
                    if not mask.any():
                        continue
                    cum = np.cumsum(R[s] * dt)
                    draw = u[mask]
                    nxt = np.full(draw.shape, s)
                    for tgt in range(len(self.regimes.names)):
                        hit = (draw < cum[tgt]) & (nxt == s) & (tgt != s)
                        nxt[hit] = tgt
                    changed = nxt != s
                    if changed.any():
                        sub = np.where(mask)[0][changed]
                        X[sub] += np.log(self.regimes.level_mult[nxt[changed]])
                    new_state[mask] = nxt
                state = new_state
                muL = self.regimes.mu_L[state]
            elif measure == "P":
                muL = np.full(n, p.mu_L)
            else:                                   # Q: long factor is a martingale
                muL = np.zeros(n)

            X += (muL - 0.5 * p.sigma_L ** 2) * dt + p.sigma_L * dW_L
            spot_drift = p.kappa * (X - Y) - 0.5 * p.sigma_S ** 2
            if measure == "Q":
                spot_drift = spot_drift - p.lambda_S * p.sigma_S
            Y += spot_drift * dt + p.sigma_S * dW_S

            if k in branch_steps:
                b = branch_steps[k]
                if b.target == "L":
                    X += math.log(b.multiplier)
                else:
                    Y += math.log(b.multiplier)

            S_path[k] = np.exp(Y)
            if use_reg:
                regime_state[k] = state

        return {"measure": measure, "tau": taus, "S": S_path, "dt": dt,
                "steps_per_year": spy, "regime_state": regime_state,
                "regime_names": self.regimes.names if use_reg else None}

    # ---- P forecast + cone (thin wrapper over simulate_paths) ------------- #
    def forecast_cone(self) -> dict:
        sim = self.cfg["simulation"]
        res = self.simulate_paths(measure="P", use_policy=True)
        S = res["S"]
        qs = sim["cone_quantiles"]
        out = {
            "measure": "P",
            "tau": res["tau"].tolist(),
            "seed": sim["seed"],
            "mean": S.mean(axis=1).tolist(),
            "quantile_levels": qs,
            "cone": np.quantile(S, qs, axis=1).tolist(),
            "provenance": self._provenance(),
        }
        if res["regime_state"] is not None:
            nstates = len(res["regime_names"])
            share = np.stack([np.bincount(row, minlength=nstates) / row.size
                              for row in res["regime_state"]])
            out["regime_names"] = res["regime_names"]
            out["regime_share"] = share.T.tolist()
        if self.branches:
            out["manual_branches"] = [asdict(b) for b in self.branches]
        return out

    # ---- LCOF calibration with memory ------------------------------------ #
    def calibrate(self, target: Optional[CalibrationTarget] = None,
                  warm_start: bool = True) -> dict:
        cal = self.cfg["calibration"]
        if target is None:
            target = LCOFTarget.from_config(cal)
        free = [k for k in PARAM_ORDER if self.param_status[k] == "calibrated"]
        if not free:
            raise ValueError("No parameters flagged 'calibrated' in config.")

        base = self.params
        latest = self.memory.latest_params(self.project_id)
        if warm_start and latest is not None:
            base = GabillonParams(**latest)           # <-- calibration with memory
        x0 = np.array([getattr(base, k) for k in free])
        lo = np.array([self.bounds[k][0] for k in free])
        hi = np.array([self.bounds[k][1] for k in free])
        x0 = np.clip(x0, lo + 1e-9, hi - 1e-9)
        t = target.taus()

        def resid(x):
            trial = GabillonParams(**{**asdict(self.params), **dict(zip(free, x))})
            return target.residuals(gabillon_forward(self.market.spot,
                                                      self.market.long_term, t, trial))

        sol = least_squares(resid, x0, bounds=(lo, hi), method="trf")
        fitted = GabillonParams(**{**asdict(self.params), **dict(zip(free, sol.x))})
        self.params = fitted

        model = gabillon_forward(self.market.spot, self.market.long_term, t, fitted)
        prices = target.values()
        err = model - prices
        rmse = float(np.sqrt(np.mean(err ** 2)))
        ss_res = float(np.sum(err ** 2))
        ss_tot = float(np.sum((prices - prices.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        bound_hits = [
            name for name, value in zip(free, sol.x)
            if abs(value - self.bounds[name][0]) <= 1e-7 or abs(value - self.bounds[name][1]) <= 1e-7
        ]

        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project_id": self.project_id,
            "config": self.cfg,
            "params": asdict(fitted),
            "free_params": free,
            "target_source": target.source,
            "warm_started": warm_start and latest is not None,
            "seed": int(self.cfg["simulation"]["seed"]),
            "fit": {"rmse": rmse, "r2_vs_fundamental": r2,
                    "n_points": int(t.size), "converged": bool(sol.success),
                    "params_on_bound": bound_hits},
            "provenance_note": ("R^2 is consistency with the FUNDAMENTAL LCOF anchor, "
                                "NOT market calibration quality."),
        }
        self.memory.append(self.project_id, record)
        self.last_fit = record
        return record


def target_prices(t: CalibrationTarget) -> np.ndarray:  # retained for back-compat
    return t.values()
