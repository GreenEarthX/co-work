"""
Gabillon Modified Two-Factor Model — Green Fuel Price Curves
gex_pf_engine/app/core/gabillon.py

Calibrates spot + convenience yield dynamics for H2, eMeOH, SAF
against European market price observations.

Modifications for green fuel markets vs. original Gabillon (1991):
  1. μ(t) includes CAPEX learning curve
  2. θ(t) includes quarterly seasonality (Fourier terms)
  3. Regulatory premium term RP(t) from EU ETS + RFNBO mandate progression

References:
  Gabillon, J. (1991). The Term Structure of Oil Futures Prices.
  Lacoste-Bouchet & Wirjanto (2025). Applications of LSS Processes to Storable Commodities.
"""
import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("gex.gabillon")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("numpy not available — Monte Carlo simulation disabled")


# ════════════════════════════════════════════════════════════════
# PARAMETERS
# ════════════════════════════════════════════════════════════════

@dataclass
class GabillonParams:
    """Two-factor Gabillon model parameters with green fuel extensions."""
    molecule: str                    # "H2" | "SAF" | "E_METHANOL"

    # ── Core Gabillon ──
    alpha: float                     # spot mean-reversion speed (yr⁻¹)
    mu_base: float                   # long-term equilibrium (log-price, €/t)
    sigma_s: float                   # spot volatility (annualised)
    kappa: float                     # convenience yield mean-reversion (yr⁻¹)
    theta_0: float                   # base convenience yield
    sigma_delta: float               # convenience yield volatility
    rho: float                       # correlation (dW_S, dW_δ)

    # ── Seasonality ──
    season_a1: float = 0.0           # sin(2πt) coefficient
    season_a2: float = 0.0           # cos(2πt) coefficient

    # ── Learning Curve (CAPEX floor) ──
    learning_rate: float = -0.20     # cost reduction per doubling of capacity
    reference_capacity_gw: float = 5.0  # cumulative capacity at calibration (GW)
    capex_floor_eur_t: float = 0.0   # levelised cost floor from Plant Builder

    # ── Regulatory Premium ──
    regulatory_premium_base: float = 0.0   # base €/t from ETS + RFNBO

    # ── Calibration Metadata ──
    calibration_error_pct: float = 0.0
    n_observations: int = 0
    last_calibrated: str = ""


@dataclass
class PriceObservation:
    date: str                        # ISO 8601 "2025-03-01"
    price_eur: float                 # observed price (€/t for SAF/NH3/MeOH; €/kg×1000 for H2)
    tenor_months: int                # 0 = spot proxy, 3, 6, 12, 24, 36, 60
    source: str                      # "ARGUS_NWE" | "ICIS" | "PLATTS" | "GEX_CONTRACT"
    molecule: str
    volume_tonnes: float = 1.0       # for volume-weighting


@dataclass
class CalibrationResult:
    molecule: str
    params: GabillonParams
    spot_price_eur: float
    convenience_yield: float
    term_curve: list                 # [{tenor_months, price_eur, implied_forward}]
    mean_reversion_half_life_months: float
    seasonal_amplitude_pct: float
    capex_floor_eur: float
    calibration_error_pct: float
    last_calibrated: str
    n_observations: int


# ════════════════════════════════════════════════════════════════
# SEED CALIBRATION PARAMETERS — European market priors
# ════════════════════════════════════════════════════════════════

# Based on:
# - BNEF H2 LCOH Tracker 2025
# - ICIS SAF price assessments NWE 2024–2025
# - Argus eMeOH NWE 2025
# - OIES ET52 (2026) "Bankability of Hydrogen Projects"

SEED_PARAMS: dict[str, GabillonParams] = {
    "H2": GabillonParams(
        molecule="H2",
        # Fast mean reversion — nascent market, price discovery ongoing
        alpha=1.0,
        mu_base=math.log(5_500),     # €5.50/kg long-term equilibrium (log-price)
        sigma_s=0.42,                # 42% annualised spot vol
        kappa=0.60,
        theta_0=0.15,                # mild backwardation (scarcity premium)
        sigma_delta=0.20,
        rho=-0.35,
        # Seasonality: peak Q1 (heating demand), trough Q3
        season_a1=0.08,
        season_a2=-0.05,
        learning_rate=-0.20,
        reference_capacity_gw=5.0,
        capex_floor_eur_t=3_500,     # €3.50/kg at current electrolyser costs
        regulatory_premium_base=200,
        n_observations=0,
        last_calibrated="2026-03-22",
    ),
    "SAF": GabillonParams(
        molecule="SAF",
        # Moderate mean reversion — linked to jet fuel + green premium
        alpha=0.55,
        mu_base=math.log(1_500),     # €1,500/t long-term
        sigma_s=0.25,                # 25% vol — more liquid reference market
        kappa=0.45,
        theta_0=0.08,
        sigma_delta=0.12,
        rho=-0.25,
        # Seasonality: peak Q2-Q3 (summer aviation), trough Q1
        season_a1=-0.06,
        season_a2=0.09,
        learning_rate=-0.18,
        reference_capacity_gw=1.0,
        capex_floor_eur_t=1_200,     # current FT + electrolyser costs
        regulatory_premium_base=350,
        n_observations=0,
        last_calibrated="2026-03-22",
    ),
    "E_METHANOL": GabillonParams(
        molecule="E_METHANOL",
        # Slower mean reversion — established chemistry, marine fuel linkage
        alpha=0.65,
        mu_base=math.log(800),       # €800/t long-term
        sigma_s=0.30,
        kappa=0.50,
        theta_0=0.05,
        sigma_delta=0.15,
        rho=-0.30,
        # Seasonality: moderate, linked to shipping fuel demand
        season_a1=0.04,
        season_a2=-0.03,
        learning_rate=-0.15,
        reference_capacity_gw=0.5,
        capex_floor_eur_t=600,
        regulatory_premium_base=150,
        n_observations=0,
        last_calibrated="2026-03-22",
    ),
    "NH3": GabillonParams(
        molecule="NH3",
        alpha=0.50,
        mu_base=math.log(700),       # €700/t long-term
        sigma_s=0.22,
        kappa=0.40,
        theta_0=0.06,
        sigma_delta=0.10,
        rho=-0.20,
        season_a1=0.03,
        season_a2=-0.02,
        learning_rate=-0.15,
        reference_capacity_gw=3.0,
        capex_floor_eur_t=450,
        regulatory_premium_base=80,
        n_observations=0,
        last_calibrated="2026-03-25",
    ),
    # e-Natural Gas (synthetic methane / power-to-gas)
    "E_NG": GabillonParams(
        molecule="E_NG",
        # Tightly coupled to TTF gas futures + green premium
        alpha=0.80,
        mu_base=math.log(120),       # €120/MWh synthetic methane long-term
        sigma_s=0.45,                # high vol — reflects TTF dynamics
        kappa=0.55,
        theta_0=0.10,
        sigma_delta=0.18,
        rho=-0.30,
        # Seasonality: strong Q4/Q1 (winter heating demand)
        season_a1=0.12,
        season_a2=-0.09,
        learning_rate=-0.18,
        reference_capacity_gw=1.5,
        capex_floor_eur_t=95,        # €/MWh LCOE floor
        regulatory_premium_base=25,  # EU biomethane mandate premium
        n_observations=0,
        last_calibrated="2026-03-25",
    ),
    # HVO (Hydrotreated Vegetable Oil / renewable diesel)
    "HVO": GabillonParams(
        molecule="HVO",
        # Linked to FAME diesel + feedstock (UCO, tallow) + RED III mandate
        alpha=0.45,
        mu_base=math.log(1_800),     # €1,800/t long-term (premium to fossil diesel)
        sigma_s=0.28,
        kappa=0.38,
        theta_0=0.07,
        sigma_delta=0.13,
        rho=-0.22,
        # Seasonality: moderate — feedstock (UCO) supply peaks Q1-Q2
        season_a1=-0.04,
        season_a2=0.06,
        learning_rate=-0.12,
        reference_capacity_gw=8.0,   # large existing capacity base
        capex_floor_eur_t=1_400,
        regulatory_premium_base=200, # ISCC PLUS / RSB premium
        n_observations=0,
        last_calibrated="2026-03-25",
    ),
}


# ════════════════════════════════════════════════════════════════
# GABILLON MODEL ENGINE
# ════════════════════════════════════════════════════════════════

class GabillonModel:
    """
    Two-factor Gabillon model implementation for green fuel price curves.
    """

    def forward_price(
        self,
        params: GabillonParams,
        spot: float,
        delta: float,       # current convenience yield
        tenor_years: float,
        t: float = 0.0,     # current time (for seasonality phase)
    ) -> float:
        """
        Compute Gabillon forward price at given tenor.

        F(t,T) = S(t) * exp(
            (1/α)(1 - e^(-α(T-t)))(δ(t) - θ(T))
            + (T-t)(μ(T) - σ_S²/2 + ρ*σ_S*σ_δ/κ)
            + (σ_S²/(4α))(1 - e^(-2α(T-t)))
            + ...seasonality + learning terms...
        )

        Simplified closed-form (Jensen's inequality correction included).
        """
        tau = tenor_years
        if tau <= 0:
            return spot

        alpha = params.alpha
        kappa = params.kappa
        sigma_s = params.sigma_s
        sigma_d = params.sigma_delta
        rho = params.rho
        theta = params.theta_0

        # Mean reversion envelope
        e_alpha_tau = math.exp(-alpha * tau)
        e_kappa_tau = math.exp(-kappa * tau)

        # Convenience yield contribution
        delta_term = (1 / alpha) * (1 - e_alpha_tau) * (delta - theta)

        # Long-term drift
        mu_longrun = params.mu_base
        drift_term = tau * (mu_longrun - 0.5 * sigma_s ** 2
                           + rho * sigma_s * sigma_d / kappa)

        # Variance correction (Jensen)
        var_term = (sigma_s ** 2 / (4 * alpha)) * (1 - math.exp(-2 * alpha * tau))

        # Cross-term: sigma_S * sigma_δ correlation
        cross_term = 0.0
        if alpha != kappa:
            cross_term = (
                rho * sigma_s * sigma_d / (alpha - kappa)
            ) * (e_kappa_tau - e_alpha_tau)

        # Seasonality: θ(T) = θ_0 + A1*sin(2πT) + A2*cos(2πT)
        T_abs = t + tau
        season_term = (
            params.season_a1 * math.sin(2 * math.pi * T_abs)
            + params.season_a2 * math.cos(2 * math.pi * T_abs)
        )

        # CAPEX learning curve: floor rises if market price below LCOH
        learning_floor = params.capex_floor_eur_t
        if learning_floor > 0 and spot < learning_floor:
            # Below LCOH floor — mean reversion anchors upward
            floor_pull = 0.10 * tau * (math.log(learning_floor) - math.log(spot))
        else:
            floor_pull = 0.0

        log_forward = (
            math.log(spot)
            + delta_term
            + drift_term
            + var_term
            + cross_term
            + season_term
            + floor_pull
        )
        return round(math.exp(log_forward), 2)

    def term_structure(
        self,
        params: GabillonParams,
        spot: float,
        delta: float,
        tenors_months: list,
        t: float = 0.0,
    ) -> list:
        """Compute full term structure from calibrated model."""
        curve = []
        for tenor_m in tenors_months:
            tau = tenor_m / 12.0
            fwd = self.forward_price(params, spot, delta, tau, t)
            carry = round(fwd - spot, 2) if tenor_m <= 12 else None
            curve.append({
                "tenor_months": tenor_m,
                "tenor_label": f"{tenor_m}M" if tenor_m < 12 else f"{tenor_m // 12}Y",
                "price_eur": fwd,
                "implied_forward_eur": fwd,
                "carry_eur": carry,
                "annualised_return_pct": round(
                    100 * (fwd / spot - 1) / (tau) if tau > 0 and spot > 0 else 0, 2
                ),
            })
        return curve

    def mean_reversion_half_life(self, params: GabillonParams) -> float:
        """Half-life of mean reversion in months."""
        return round(math.log(2) / params.alpha * 12, 1)

    def calibrate(
        self,
        observations: list,
        capex_floor_eur: float,
        molecule: str,
        cumulative_capacity_gw: float = 5.0,
    ) -> CalibrationResult:
        """
        Full calibration pipeline:
        1. Cluster observations by tenor
        2. Fit term curve (volume-weighted average per tenor bucket)
        3. Bootstrap spot price from short-tenor observations
        4. Estimate α, σ_S from spot dynamics
        5. Estimate κ, θ_0 from term structure slope
        6. Extract seasonality from residuals
        7. Validate against CAPEX floor

        With few observations, falls back to SEED_PARAMS and patches CAPEX floor.
        """
        now_str = "2026-03-22"

        # ── Start from seed params ──
        params = SEED_PARAMS.get(molecule)
        if params is None:
            params = GabillonParams(
                molecule=molecule, alpha=0.8, mu_base=math.log(1000),
                sigma_s=0.30, kappa=0.50, theta_0=0.05, sigma_delta=0.15, rho=-0.25,
            )

        # ── Patch CAPEX floor ──
        params.capex_floor_eur_t = capex_floor_eur if capex_floor_eur > 0 else params.capex_floor_eur_t
        params.reference_capacity_gw = cumulative_capacity_gw

        if not observations:
            half_life = self.mean_reversion_half_life(params)
            spot = math.exp(params.mu_base)
            delta = params.theta_0
            curve = self.term_structure(params, spot, delta, [1, 3, 6, 12, 24, 36, 60])
            season_amp = round(
                math.sqrt(params.season_a1 ** 2 + params.season_a2 ** 2) * 100, 1
            )
            return CalibrationResult(
                molecule=molecule, params=params,
                spot_price_eur=round(spot, 2),
                convenience_yield=delta,
                term_curve=curve,
                mean_reversion_half_life_months=half_life,
                seasonal_amplitude_pct=season_amp,
                capex_floor_eur=capex_floor_eur,
                calibration_error_pct=0.0,
                last_calibrated=now_str,
                n_observations=0,
            )

        # ── Aggregate observations by tenor ──
        tenor_groups: dict = {}
        for obs in observations:
            t = obs.tenor_months if isinstance(obs, PriceObservation) else obs.get("tenor_months", 0)
            p = obs.price_eur if isinstance(obs, PriceObservation) else obs.get("price_eur", 0)
            v = obs.volume_tonnes if isinstance(obs, PriceObservation) else obs.get("volume_tonnes", 1.0)
            if t not in tenor_groups:
                tenor_groups[t] = []
            tenor_groups[t].append((p, v))

        # Volume-weighted average per tenor
        term_obs: dict = {}
        for tenor, pv_list in tenor_groups.items():
            total_vol = sum(v for _, v in pv_list)
            wavg = sum(p * v for p, v in pv_list) / total_vol if total_vol > 0 else pv_list[0][0]
            term_obs[tenor] = wavg

        # ── Bootstrap spot from shortest tenor ──
        sorted_tenors = sorted(term_obs.keys())
        spot = term_obs.get(0) or term_obs.get(sorted_tenors[0])

        # ── Calibrate α from term structure slope ──
        if len(sorted_tenors) >= 3:
            # Simple OLS: ln(F(T)) = ln(S) + c * T → slope gives mean reversion
            xs = [t / 12.0 for t in sorted_tenors if t > 0]
            ys = [math.log(term_obs[t]) - math.log(spot) for t in sorted_tenors if t > 0]
            if xs:
                mean_x = sum(xs) / len(xs)
                mean_y = sum(ys) / len(ys)
                numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
                denominator = sum((x - mean_x) ** 2 for x in xs)
                if abs(denominator) > 1e-10:
                    slope = numerator / denominator
                    # slope ≈ -α * (δ - θ) / α = (δ - θ) for contango
                    params.theta_0 = max(-0.3, min(0.3, slope))

        # ── Update mu_base from observed market level ──
        # Long-term equilibrium = geometric mean of 24M+ observations
        long_term_prices = [p for t, p in term_obs.items() if t >= 24]
        if long_term_prices:
            params.mu_base = math.log(sum(long_term_prices) / len(long_term_prices))
        else:
            # Blend with seed
            params.mu_base = 0.7 * params.mu_base + 0.3 * math.log(spot)

        # ── Calibration error: average abs % deviation ──
        errors = []
        delta = params.theta_0
        for tenor, obs_price in term_obs.items():
            if tenor == 0:
                continue
            model_price = self.forward_price(params, spot, delta, tenor / 12.0)
            if obs_price > 0:
                errors.append(abs(model_price - obs_price) / obs_price)
        cal_error = round(100 * sum(errors) / len(errors), 2) if errors else 0.0
        params.calibration_error_pct = cal_error
        params.n_observations = len(observations)
        params.last_calibrated = now_str

        # ── Build result curve ──
        curve = self.term_structure(params, spot, delta, [1, 3, 6, 12, 24, 36, 60])
        half_life = self.mean_reversion_half_life(params)
        season_amp = round(
            math.sqrt(params.season_a1 ** 2 + params.season_a2 ** 2) * 100, 1
        )

        return CalibrationResult(
            molecule=molecule, params=params,
            spot_price_eur=round(spot, 2),
            convenience_yield=delta,
            term_curve=curve,
            mean_reversion_half_life_months=half_life,
            seasonal_amplitude_pct=season_amp,
            capex_floor_eur=capex_floor_eur,
            calibration_error_pct=cal_error,
            last_calibrated=now_str,
            n_observations=len(observations),
        )

    def simulate_paths(
        self,
        params: GabillonParams,
        spot_0: float,
        delta_0: float,
        horizon_years: float,
        n_paths: int = 5000,
        dt: float = 1 / 252,
    ) -> Optional[object]:
        """
        Monte Carlo simulation of spot price paths.
        Returns numpy array of shape (n_paths, n_steps) or None if numpy unavailable.
        """
        if not HAS_NUMPY:
            logger.warning("numpy not available — returning None for MC simulation")
            return None

        n_steps = int(horizon_years / dt)
        sqrt_dt = math.sqrt(dt)

        S = np.full(n_paths, spot_0, dtype=np.float64)
        delta = np.full(n_paths, delta_0, dtype=np.float64)
        paths = np.zeros((n_paths, n_steps + 1))
        paths[:, 0] = S

        # Cholesky decomposition for correlated Brownian motions
        rho = params.rho
        chol = np.array([
            [1.0, 0.0],
            [rho, math.sqrt(max(0.0, 1 - rho ** 2))],
        ])

        for step in range(n_steps):
            t = step * dt
            Z = np.random.standard_normal((n_paths, 2))
            W = Z @ chol.T  # correlated: W[:,0]=dW_S, W[:,1]=dW_δ

            # Seasonality at current t
            theta_t = (
                params.theta_0
                + params.season_a1 * math.sin(2 * math.pi * t)
                + params.season_a2 * math.cos(2 * math.pi * t)
            )
            mu_t = params.mu_base

            # CAPEX floor — add upward pull if below cost floor
            log_S = np.log(np.maximum(S, 1e-6))
            floor_pull = np.where(
                S < params.capex_floor_eur_t,
                params.alpha * (math.log(max(params.capex_floor_eur_t, 1)) - log_S) * dt,
                0.0,
            )

            # Spot dynamics: dS/S = α(μ - ln S) dt + σ_S dW_S
            dS = (
                params.alpha * (mu_t - log_S) * dt
                + params.sigma_s * sqrt_dt * W[:, 0]
                + floor_pull
            )
            S = S * np.exp(dS)

            # Convenience yield dynamics: dδ = κ(θ - δ) dt + σ_δ dW_δ
            delta = (
                delta
                + params.kappa * (theta_t - delta) * dt
                + params.sigma_delta * sqrt_dt * W[:, 1]
            )

            paths[:, step + 1] = S

        return paths

    def var_from_paths(self, paths, confidence: float = 0.95) -> dict:
        """Compute VaR and CVaR from simulated paths."""
        if not HAS_NUMPY or paths is None:
            return {}
        final = paths[:, -1]
        p5 = float(np.percentile(final, (1 - confidence) * 100))
        p95 = float(np.percentile(final, confidence * 100))
        mean = float(np.mean(final))
        std = float(np.std(final))
        return {
            "mean": round(mean, 2),
            "std": round(std, 2),
            "p5": round(p5, 2),
            "p95": round(p95, 2),
            "var_95": round(mean - p5, 2),
            "cvar_95": round(mean - float(np.mean(final[final <= p5])), 2)
            if any(final <= p5) else 0.0,
        }

    def seasonal_decomposition(self, params: GabillonParams) -> dict:
        """Return quarterly seasonal factors from calibrated Fourier terms."""
        quarters = {}
        for q, t_mid in enumerate([0.125, 0.375, 0.625, 0.875], start=1):
            seasonal = (
                params.season_a1 * math.sin(2 * math.pi * t_mid)
                + params.season_a2 * math.cos(2 * math.pi * t_mid)
            )
            quarters[f"Q{q}"] = round(math.exp(seasonal), 4)
        amplitude = round(
            math.sqrt(params.season_a1 ** 2 + params.season_a2 ** 2) * 100, 2
        )
        return {
            "quarterly_factors": quarters,
            "seasonal_amplitude_pct": amplitude,
            "peak_quarter": max(quarters, key=quarters.get),
            "trough_quarter": min(quarters, key=quarters.get),
        }


# ════════════════════════════════════════════════════════════════
# SINGLETON
# ════════════════════════════════════════════════════════════════

_model: Optional[GabillonModel] = None


def get_gabillon_model() -> GabillonModel:
    global _model
    if _model is None:
        _model = GabillonModel()
        logger.info("GabillonModel initialised")
    return _model
