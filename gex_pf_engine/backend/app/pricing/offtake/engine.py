"""
GEX Offtake / Contract Engine  -  Module 2 of the green-fuel valuation backend.

Values a long-dated indexed take-or-pay offtake as three economically distinct objects,
exactly as scoped:

  1. Linear indexed leg   - indexation is a deterministic pass-through map defining the
                            floating leg; valued off the Q-forward (no optionality).
  2. Collar (floor/ceiling) - vanilla options ON the indexed leg; floor = long put to the
                            project, ceiling = short call; priced by Monte Carlo on the
                            Q-paths from module 1. Floor and ceiling reported separately.
  3. Volume flex          - the buyer's swing/real option over per-period nomination with
                            a take-or-pay global constraint; valued by Least-Squares Monte
                            Carlo (Longstaff-Schwartz with a cumulative-volume grid).

Then a GreenMesh rollup aggregates contract value (+ a merchant tail) into plant value.

Consumes module 1 (gabillon_engine) for measure-consistent Q-paths and forwards. Carries
the same provenance discipline: assumed quantities are declared, never concealed.

Dependencies: numpy. Imports gabillon_engine (module 1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

from app.pricing.gabillon.engine import GabillonCurveEngine, gabillon_forward


# --------------------------------------------------------------------------- #
#  Indexation: the deterministic floating-leg map
# --------------------------------------------------------------------------- #
@dataclass
class Indexation:
    base: float
    spread: float
    beta: float

    def price(self, S):
        """P_index(S) = base + spread + beta * S.  Linear -> E^Q[P_index] = base+spread+beta*F."""
        return self.base + self.spread + self.beta * np.asarray(S, float)


# --------------------------------------------------------------------------- #
#  The offtake engine
# --------------------------------------------------------------------------- #
class OfftakeEngine:
    def __init__(self, config: dict, curve: GabillonCurveEngine):
        self.cfg = config
        self.curve = curve
        self.perspective = config.get("perspective", "project")
        self.r = float(config["discounting"]["risk_free_rate"])
        self.tenors = np.array(config["tenor"]["delivery_years"], float)
        self.idx = Indexation(**{k: config["indexation"][k] for k in ("base", "spread", "beta")})
        self.collar = config.get("collar", {})
        self.vol = config["volume"]
        self.gm = config.get("greenmesh_rollup", {})
        self.n_paths = int(config["simulation"]["n_paths"])
        self.seed = int(config["simulation"]["seed"])

    # ---- shared building blocks ------------------------------------------ #
    def _df(self, t):
        return np.exp(-self.r * np.asarray(t, float))

    def _q_paths_at_tenors(self) -> np.ndarray:
        """Q-measure price S at each delivery date, shape (n_periods, n_paths)."""
        spy = int(self.curve.cfg["simulation"]["steps_per_year"])
        T = float(self.tenors.max())
        sim = self.curve.simulate_paths(measure="Q", n_paths=self.n_paths,
                                        horizon_years=T, seed=self.seed, use_policy=False)
        S = sim["S"]                                    # (nstep, n_paths)
        step_idx = np.round(self.tenors * spy).astype(int) - 1
        step_idx = np.clip(step_idx, 0, S.shape[0] - 1)
        return S[step_idx, :]                            # (n_periods, n_paths)

    def _forwards_at_tenors(self) -> np.ndarray:
        return gabillon_forward(self.curve.market.spot, self.curve.market.long_term,
                                self.tenors, self.curve.params)

    # ---- 1. linear indexed leg (deterministic) --------------------------- #
    def linear_leg(self, q_per_year: Optional[float] = None) -> dict:
        q = self.vol["baseline_per_year"] if q_per_year is None else q_per_year
        F = self._forwards_at_tenors()
        price = self.idx.price(F)                        # E^Q[P_index] (linear)
        pv = float(np.sum(self._df(self.tenors) * q * price))
        return {"value": pv, "per_period_price": price.tolist(),
                "volume_per_year": q, "tenors": self.tenors.tolist()}

    # ---- 2. collar: floor and ceiling as vanilla options ----------------- #
    def collar_value(self, q_per_year: Optional[float] = None) -> dict:
        if not self.collar.get("enabled"):
            return {"value": 0.0, "floor_value": 0.0, "ceiling_value": 0.0}
        q = self.vol["baseline_per_year"] if q_per_year is None else q_per_year
        floor, ceil = float(self.collar["floor"]), float(self.collar["ceiling"])
        S = self._q_paths_at_tenors()
        P = self.idx.price(S)                            # indexed price on each path
        df = self._df(self.tenors)[:, None]

        # floor = long put for the project: buyer pays at least `floor`
        floor_pp = np.maximum(floor - P, 0.0)
        # ceiling = short call for the project: price capped at `ceiling`
        ceil_pp = np.maximum(P - ceil, 0.0)
        floor_val = float(np.sum(df * q * floor_pp.mean(axis=1)[:, None]))
        ceil_val = float(np.sum(df * q * ceil_pp.mean(axis=1)[:, None]))
        sign = 1.0 if self.perspective == "project" else -1.0
        # project is LONG the floor, SHORT the ceiling
        value = sign * (floor_val - ceil_val)
        mc_se = float(np.std((floor_pp - ceil_pp), axis=1).mean() / math.sqrt(self.n_paths))
        return {"value": value, "floor_value": floor_val, "ceiling_value": ceil_val,
                "mc_std_err_per_unit": mc_se}

    # ---- 3. volume flex: swing option by LSMC ---------------------------- #
    def volume_flex_value(self) -> dict:
        """
        Buyer's nomination swing valued by Longstaff-Schwartz with a cumulative-volume
        grid (Boogert-De Jong style - the same LSMC family HLR use for gas storage).

        Per-unit economics to the buyer of taking one unit at t: (S_t - P_paid_t).
        Buyer takes max when the molecule is worth more than the collared contract price,
        min otherwise, subject to per-period [q_min,q_max] and life [total_min,total_max].
        The swing value is the optimised expectation MINUS the baseline-nomination value
        (the pure optionality). Project is SHORT this, so it is subtracted from project value.
        """
        q_min, q_max = float(self.vol["min_per_year"]), float(self.vol["max_per_year"])
        q_base = float(self.vol["baseline_per_year"])
        tot_min, tot_max = float(self.vol["total_min"]), float(self.vol["total_max"])
        K = int(self.vol.get("take_levels", 3))
        G = int(self.vol.get("volume_grid_points", 26))

        S = self._q_paths_at_tenors()                    # (T, n_paths)
        nT, nP = S.shape
        Pcollar = self._collared_price_paths(S)          # (T, n_paths)
        per_unit = S - Pcollar                            # buyer's per-unit value
        df = self._df(self.tenors)

        take_levels = np.linspace(q_min, q_max, K)
        vol_grid = np.linspace(0.0, tot_max, G)
        # value[g, path] = optimal continuation value from current period given cum-vol grid g
        value = np.zeros((G, nP))

        # backward induction
        for t in range(nT - 1, -1, -1):
            disc = df[t]
            new_value = np.full((G, nP), -1e18)
            # regress continuation on price basis (Longstaff-Schwartz), per grid node
            basis = np.vstack([np.ones(nP), S[t], S[t] ** 2]).T   # (nP, 3)
            cont_coef = None
            if t < nT - 1:
                cont_coef = [np.linalg.lstsq(basis, value[g], rcond=None)[0]
                             for g in range(G)]
            for g in range(G):
                cur_vol = vol_grid[g]
                best = np.full(nP, -1e18)
                for q in take_levels:
                    nxt_vol = cur_vol + q
                    if nxt_vol > tot_max + 1e-9:
                        continue
                    # feasibility: must still be able to reach tot_min by the end
                    max_future = (nT - 1 - t) * q_max
                    if nxt_vol + max_future < tot_min - 1e-9:
                        continue
                    immediate = disc * q * per_unit[t]
                    if cont_coef is not None:
                        g_next = int(np.clip(np.searchsorted(vol_grid, nxt_vol), 0, G - 1))
                        cont = basis @ cont_coef[g_next]
                    else:
                        cont = 0.0
                    cand = immediate + cont
                    best = np.maximum(best, cand)
                new_value[g] = best
            value = new_value

        g0 = int(np.clip(np.searchsorted(vol_grid, 0.0), 0, G - 1))
        optimised = float(value[g0].mean())
        # baseline: nominate q_base every period (clipped feasible)
        baseline = float(np.sum(df * q_base * per_unit.mean(axis=1)))
        flex = max(optimised - baseline, 0.0)            # optionality is non-negative
        mc_se = float(value[g0].std() / math.sqrt(nP))
        sign = -1.0 if self.perspective == "project" else 1.0   # project is short the swing
        return {"value": sign * flex, "swing_to_buyer": flex,
                "optimised_buyer_value": optimised, "baseline_value": baseline,
                "mc_std_err": mc_se, "take_levels": take_levels.tolist(),
                "vol_grid_points": G}

    def _collared_price_paths(self, S: np.ndarray) -> np.ndarray:
        P = self.idx.price(S)
        if self.collar.get("enabled"):
            P = np.clip(P, float(self.collar["floor"]), float(self.collar["ceiling"]))
        return P

    # ---- full contract value (the three legs, no double counting) -------- #
    def value_contract(self) -> dict:
        linear = self.linear_leg()
        collar = self.collar_value()
        flex = self.volume_flex_value()
        total = linear["value"] + collar["value"] + flex["value"]
        return {
            "contract_id": self.cfg.get("contract_id"),
            "project_id": self.cfg.get("project_id"),
            "perspective": self.perspective,
            "seed": self.seed,
            "total_value": total,
            "decomposition": {
                "linear_indexed_leg": linear["value"],
                "collar": collar["value"],
                "floor_component": collar.get("floor_value", 0.0),
                "ceiling_component": collar.get("ceiling_value", 0.0),
                "volume_flex": flex["value"],
            },
            "diagnostics": {
                "collar_mc_std_err_per_unit": collar.get("mc_std_err_per_unit"),
                "flex_mc_std_err": flex.get("mc_std_err"),
                "swing_to_buyer": flex.get("swing_to_buyer"),
            },
            "provenance": self._provenance(),
        }

    # ---- GreenMesh rollup: contracts -> plant/enterprise value ----------- #
    def greenmesh_rollup(self, contracts: Optional[list[dict]] = None) -> dict:
        if not self.gm.get("enabled"):
            return {"enabled": False}
        if contracts is None:
            contracts = [self.value_contract()]
        contracted = sum(c["total_value"] for c in contracts)

        cap = float(self.gm["plant_capacity_per_year"])
        margin = float(self.gm["merchant_margin"])
        H = int(self.gm["merchant_horizon_years"])
        merch_tenors = np.arange(1, H + 1, dtype=float)
        F = gabillon_forward(self.curve.market.spot, self.curve.market.long_term,
                             merch_tenors, self.curve.params)
        uncontracted = max(cap - float(self.vol["baseline_per_year"]), 0.0)
        merchant_tail = float(np.sum(self._df(merch_tenors) * uncontracted * F * margin))

        return {
            "enabled": True,
            "n_contracts": len(contracts),
            "seed": self.seed,
            "contracted_value": contracted,
            "merchant_tail_value": merchant_tail,
            "uncontracted_capacity_per_year": uncontracted,
            "enterprise_value": contracted + merchant_tail,
            "provenance": self._provenance(),
            "_note": "Enterprise value = sum(contract values) + merchant tail. Merchant "
                     "tail values uncontracted capacity at the Q-forward * merchant_margin.",
        }

    # ---- provenance ------------------------------------------------------ #
    def _provenance(self) -> dict:
        prov = dict(self.curve._provenance())
        prov["indexation_beta_spread"] = "contract_terms"
        prov["collar_floor_ceiling"] = "contract_terms"
        prov["volume_bands_and_ToP"] = "contract_terms"
        prov["merchant_margin"] = "assumed"
        prov["_pricing_measure"] = ("Collar and volume flex priced under Q using module 1 "
                                    "Q-paths (smooth diffusion; regime risk premia NOT priced).")
        return prov

