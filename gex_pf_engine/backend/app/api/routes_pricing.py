"""
GEX Price Curve Engine — API Routes
/api/v1/pricing

Gabillon Modified Two-Factor Model for H2, SAF, eMeOH, NH3.
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.core.gabillon import (
    get_gabillon_model,
    GabillonParams,
    PriceObservation,
    SEED_PARAMS,
)

logger = logging.getLogger("gex.routes.pricing")
router = APIRouter()

SUPPORTED_MOLECULES = list(SEED_PARAMS.keys())   # H2, SAF, E_METHANOL, NH3


# ════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ════════════════════════════════════════════════════════════════

class PriceObservationRequest(BaseModel):
    date: str
    price_eur: float = Field(ge=0)
    tenor_months: int = Field(ge=0, le=360)
    source: str = "GEX_CONTRACT"
    molecule: str
    volume_tonnes: float = Field(default=1.0, ge=0)


class CalibrateRequest(BaseModel):
    molecule: str
    observations: list[PriceObservationRequest] = []
    capex_floor_eur_t: float = Field(default=0.0, ge=0)
    cumulative_capacity_gw: float = Field(default=5.0, ge=0)


class ForwardPriceRequest(BaseModel):
    molecule: str
    tenor_months: int = Field(ge=1, le=360)
    spot_override: Optional[float] = None
    delta_override: Optional[float] = None


class SimulateRequest(BaseModel):
    molecule: str
    horizon_years: float = Field(default=5.0, ge=0.5, le=30)
    n_paths: int = Field(default=2000, ge=100, le=20000)
    spot_override: Optional[float] = None
    capex_floor_override: Optional[float] = None


# ════════════════════════════════════════════════════════════════
# IN-MEMORY CALIBRATION STORE
# ════════════════════════════════════════════════════════════════

_calibrated: dict = {}   # molecule → CalibrationResult


def _get_or_default_calibration(molecule: str):
    """Return stored calibration or compute from seed params."""
    if molecule in _calibrated:
        return _calibrated[molecule]
    # Calibrate from seed (no observations)
    model = get_gabillon_model()
    params = SEED_PARAMS.get(molecule)
    if not params:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported. Use: {SUPPORTED_MOLECULES}")
    result = model.calibrate([], params.capex_floor_eur_t, molecule)
    _calibrated[molecule] = result
    return result


def _serialize_params(params: GabillonParams) -> dict:
    return {
        "molecule": params.molecule,
        "alpha": params.alpha,
        "mu_base": params.mu_base,
        "mu_equilibrium_eur_t": round(__import__('math').exp(params.mu_base), 2),
        "sigma_s": params.sigma_s,
        "kappa": params.kappa,
        "theta_0": params.theta_0,
        "sigma_delta": params.sigma_delta,
        "rho": params.rho,
        "season_a1": params.season_a1,
        "season_a2": params.season_a2,
        "learning_rate": params.learning_rate,
        "reference_capacity_gw": params.reference_capacity_gw,
        "capex_floor_eur_t": params.capex_floor_eur_t,
        "regulatory_premium_base": params.regulatory_premium_base,
        "calibration_error_pct": params.calibration_error_pct,
        "n_observations": params.n_observations,
        "last_calibrated": params.last_calibrated,
    }


# ════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════

@router.get("/molecules")
async def list_molecules():
    """List supported molecules for pricing."""
    return {"molecules": SUPPORTED_MOLECULES}


@router.post("/calibrate")
async def calibrate(req: CalibrateRequest):
    """
    Calibrate Gabillon model from price observations.

    Pipeline:
    1. Cluster observations by tenor
    2. Volume-weighted average per tenor bucket
    3. Bootstrap spot price
    4. Estimate α from term structure slope
    5. Update μ_base from long-term observations
    6. Apply CAPEX floor constraint

    Pass empty observations list to use seed parameters.
    """
    if req.molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(
            status_code=400,
            detail=f"Molecule '{req.molecule}' not supported. Use: {SUPPORTED_MOLECULES}",
        )

    obs_objs = [
        PriceObservation(
            date=o.date,
            price_eur=o.price_eur,
            tenor_months=o.tenor_months,
            source=o.source,
            molecule=o.molecule,
            volume_tonnes=o.volume_tonnes,
        )
        for o in req.observations
    ]

    model = get_gabillon_model()
    result = model.calibrate(obs_objs, req.capex_floor_eur_t, req.molecule, req.cumulative_capacity_gw)
    _calibrated[req.molecule] = result

    return {
        "molecule": req.molecule,
        "status": "calibrated",
        "n_observations": result.n_observations,
        "spot_price_eur": result.spot_price_eur,
        "convenience_yield": result.convenience_yield,
        "mean_reversion_half_life_months": result.mean_reversion_half_life_months,
        "seasonal_amplitude_pct": result.seasonal_amplitude_pct,
        "capex_floor_eur": result.capex_floor_eur,
        "calibration_error_pct": result.calibration_error_pct,
        "last_calibrated": result.last_calibrated,
        "params": _serialize_params(result.params),
        "term_curve": result.term_curve,
    }


@router.get("/spot/{molecule}")
async def get_spot_price(molecule: str):
    """
    Current implied spot price from calibrated model.
    Falls back to seed parameters if not yet calibrated.
    """
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")

    result = _get_or_default_calibration(molecule)
    model = get_gabillon_model()
    season = model.seasonal_decomposition(result.params)

    import math
    return {
        "molecule": molecule,
        "spot_price_eur_t": result.spot_price_eur,
        "convenience_yield": result.convenience_yield,
        "capex_floor_eur_t": result.capex_floor_eur,
        "long_term_equilibrium_eur_t": round(math.exp(result.params.mu_base), 2),
        "mean_reversion_half_life_months": result.mean_reversion_half_life_months,
        "seasonal": season,
        "calibration_error_pct": result.calibration_error_pct,
        "last_calibrated": result.last_calibrated,
        "source": "SEED_CALIBRATION" if result.n_observations == 0 else "MARKET_CALIBRATION",
    }


@router.get("/term-curve/{molecule}")
async def get_term_curve(
    molecule: str,
    spot_override: Optional[float] = Query(default=None, description="Override spot price for scenario analysis"),
):
    """
    Full term structure for a molecule (1M–60M tenors).
    Used for offtake negotiation reference pricing.
    """
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")

    result = _get_or_default_calibration(molecule)
    model = get_gabillon_model()
    params = result.params

    spot = spot_override if spot_override and spot_override > 0 else result.spot_price_eur
    delta = result.convenience_yield

    tenors = [1, 3, 6, 9, 12, 18, 24, 30, 36, 48, 60]
    curve = model.term_structure(params, spot, delta, tenors)

    # Market structure signal
    fwd_12m = next((c["price_eur"] for c in curve if c["tenor_months"] == 12), spot)
    market_structure = "CONTANGO" if fwd_12m > spot * 1.005 else (
        "BACKWARDATION" if fwd_12m < spot * 0.995 else "FLAT"
    )

    return {
        "molecule": molecule,
        "spot_price_eur": spot,
        "market_structure": market_structure,
        "term_curve": curve,
        "capex_floor_eur_t": result.capex_floor_eur,
        "long_term_equilibrium_eur_t": round(__import__('math').exp(params.mu_base), 2),
        "last_calibrated": result.last_calibrated,
    }


@router.get("/forward")
async def get_forward_price(
    molecule: str = Query(...),
    tenor_months: int = Query(..., ge=1, le=360),
    spot_override: Optional[float] = Query(default=None),
):
    """Single forward price at given tenor for a molecule."""
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")

    result = _get_or_default_calibration(molecule)
    model = get_gabillon_model()

    spot = spot_override if spot_override and spot_override > 0 else result.spot_price_eur
    delta = result.convenience_yield

    fwd = model.forward_price(result.params, spot, delta, tenor_months / 12.0)

    return {
        "molecule": molecule,
        "spot_eur_t": spot,
        "tenor_months": tenor_months,
        "forward_price_eur_t": fwd,
        "carry_eur_t": round(fwd - spot, 2),
        "carry_pct": round(100 * (fwd / spot - 1), 2) if spot > 0 else 0.0,
    }


@router.post("/simulate")
async def simulate_price_paths(req: SimulateRequest):
    """
    Monte Carlo price path simulation for VaR and scenario analysis.
    Returns path statistics (not full paths — too large for HTTP).
    Requires numpy in the gex_pf_engine environment.
    """
    if req.molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=400, detail=f"Molecule '{req.molecule}' not supported")

    result = _get_or_default_calibration(req.molecule)
    model = get_gabillon_model()
    params = result.params

    if req.capex_floor_override:
        params.capex_floor_eur_t = req.capex_floor_override

    spot = req.spot_override if req.spot_override and req.spot_override > 0 else result.spot_price_eur
    delta = result.convenience_yield

    paths = model.simulate_paths(
        params=params,
        spot_0=spot,
        delta_0=delta,
        horizon_years=req.horizon_years,
        n_paths=req.n_paths,
    )

    if paths is None:
        return {
            "molecule": req.molecule,
            "status": "NUMPY_UNAVAILABLE",
            "message": "numpy not installed in gex_pf_engine — install numpy to enable MC simulation",
        }

    # Compute percentile statistics at each annual checkpoint
    import math
    n_steps = paths.shape[1] - 1
    checkpoints = []
    for yr in range(1, int(req.horizon_years) + 1):
        step_idx = min(int(yr / req.horizon_years * n_steps), n_steps)
        col = paths[:, step_idx]
        import numpy as np
        checkpoints.append({
            "year": yr,
            "p5": round(float(np.percentile(col, 5)), 2),
            "p25": round(float(np.percentile(col, 25)), 2),
            "median": round(float(np.percentile(col, 50)), 2),
            "p75": round(float(np.percentile(col, 75)), 2),
            "p95": round(float(np.percentile(col, 95)), 2),
            "mean": round(float(np.mean(col)), 2),
        })

    stats = model.var_from_paths(paths)

    return {
        "molecule": req.molecule,
        "horizon_years": req.horizon_years,
        "n_paths": req.n_paths,
        "spot_price_eur": spot,
        "terminal_stats": stats,
        "annual_percentiles": checkpoints,
        "capex_floor_eur_t": params.capex_floor_eur_t,
    }


@router.get("/seasonal/{molecule}")
async def get_seasonal_decomposition(molecule: str):
    """Seasonal decomposition — quarterly factors from calibrated Fourier terms."""
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")

    result = _get_or_default_calibration(molecule)
    model = get_gabillon_model()
    seasonal = model.seasonal_decomposition(result.params)

    return {
        "molecule": molecule,
        **seasonal,
        "model_params": {
            "season_a1": result.params.season_a1,
            "season_a2": result.params.season_a2,
        },
    }


@router.get("/params/{molecule}")
async def get_model_params(molecule: str):
    """Return calibrated model parameters for a molecule."""
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")
    result = _get_or_default_calibration(molecule)
    return {
        "molecule": molecule,
        "params": _serialize_params(result.params),
        "calibration_status": "MARKET" if result.n_observations > 0 else "SEED",
    }


@router.get("/cfads-integration/{molecule}")
async def get_cfads_price_inputs(
    molecule: str,
    project_life_years: int = Query(default=20, ge=1, le=50),
    start_year: int = Query(default=1, ge=1),
):
    """
    Generate revenue price inputs for CFADS model in gex_pf_engine.
    Returns annual price projections for each year of project life.
    Used by ProjectFinanceEngine.compute_cfads() for revenue line.
    """
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")

    result = _get_or_default_calibration(molecule)
    model = get_gabillon_model()
    params = result.params
    spot = result.spot_price_eur
    delta = result.convenience_yield

    annual_prices = []
    for yr in range(start_year, start_year + project_life_years):
        # Price at mid-year
        t_mid = yr - start_year + 0.5
        fwd = model.forward_price(params, spot, delta, t_mid)
        annual_prices.append({
            "year": yr,
            "price_eur_t": fwd,
            "price_real_eur_t": round(fwd * (1 - 0.02) ** t_mid, 2),  # 2% real deflation
        })

    import math
    return {
        "molecule": molecule,
        "spot_eur_t": spot,
        "long_term_equilibrium_eur_t": round(math.exp(params.mu_base), 2),
        "capex_floor_eur_t": params.capex_floor_eur_t,
        "annual_prices": annual_prices,
        "mean_reversion_half_life_months": result.mean_reversion_half_life_months,
    }
