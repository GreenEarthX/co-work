"""
GEX Price Curve Engine — API Routes
/api/v1/pricing

Publishes the current GreenEarthX offered molecule catalogue and
keeps legacy molecule aliases operational.
"""
import logging
import json
import os
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.core.gabillon import (
    get_gabillon_model,
    GabillonParams,
    PriceObservation,
    SEED_PARAMS,
)
from app.core.price_lineage import PriceLineageEngine
from app.core.debt.tranche import (
    Tranche, TrancheType, DFIProvider, FinancingStructure,
)
from app.core.model_governance import (
    GABILLON_MODEL_VERSION,
    MODEL_CARD,
    MODEL_CHANGE_REGISTER,
    benchmark_curves,
    blocking,
    challenger_assessment,
    check_invariants,
    governance_stamp,
    log_param_change,
    param_change_history,
    recent_runs,
    validate_params,
)

logger = logging.getLogger("gex.routes.pricing")
router = APIRouter()

LEGACY_CATALOG_PATH = Path(__file__).resolve().parents[4] / "gex_fuel_catalog.json"


def _resolve_platform_db_path() -> str | None:
    candidates = [
        os.getenv("GEX_PLATFORM_DB_PATH"),
        str(Path(__file__).resolve().parents[4] / "gex-platform-enhanced" / "backend" / "gex_platform.db"),
        str(Path(__file__).resolve().parents[2] / "gex_platform.db"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists() and Path(candidate).stat().st_size > 0:
            return candidate
    return None


PLATFORM_DB_PATH = _resolve_platform_db_path()
SUPPORTED_MOLECULES = list(SEED_PARAMS.keys())
MOLECULE_ALIASES = {
    "e-methane": "E_METHANE",
    "e_methane": "E_METHANE",
    "emethane": "E_METHANE",
    "e-methanol": "E_METHANOL",
    "e_methanol": "E_METHANOL",
    "emethanol": "E_METHANOL",
    "ch3oh": "E_METHANOL",
    "e-nh3": "E_NH3",
    "e_nh3": "E_NH3",
    "enh3": "E_NH3",
    "nh3": "NH3",
    "h2": "H2",
    "hvo": "HVO",
    "saf": "SAF",
    "e-gasoline": "E_GASOLINE",
    "e_gasoline": "E_GASOLINE",
    "egasoline": "E_GASOLINE",
    "e-lg": "E_LG",
    "e_lg": "E_LG",
    "elg": "E_LG",
    "e-naphtha": "E_NAPHTHA",
    "e_naphtha": "E_NAPHTHA",
    "enaphtha": "E_NAPHTHA",
    "e-ng": "E_NG",
    "e_ng": "E_NG",
    "eng": "E_NG",
}


def normalize_molecule(value: str) -> str:
    key = value.strip()
    if key in SUPPORTED_MOLECULES:
        return key
    return MOLECULE_ALIASES.get(key.lower(), key.upper())


def _load_offered_molecules() -> list[str]:
    if PLATFORM_DB_PATH:
        conn = sqlite3.connect(PLATFORM_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT label
                FROM fuel_catalog
                WHERE offered = 1 AND is_active = 1
                ORDER BY sort_order, label
                """
            ).fetchall()
            labels = [row["label"] for row in rows]
            supported = [label for label in labels if normalize_molecule(label) in SUPPORTED_MOLECULES]
            if supported:
                return supported
        except sqlite3.Error:
            logger.warning("Fuel catalogue table not available in %s", PLATFORM_DB_PATH)
        finally:
            conn.close()

    with LEGACY_CATALOG_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [fuel["label"] for fuel in payload.get("fuels", []) if fuel.get("offered")]


# ════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ════════════════════════════════════════════════════════════════

class PriceObservationRequest(BaseModel):
    """One market price observation used to calibrate a molecule curve."""
    date: str = Field(description="Observation date, ISO-8601 (e.g. '2026-03-01').")
    price_eur: float = Field(ge=0, description="Observed price in €/t (€/MWh for E_NG; H2 quoted as €/kg × 1000).")
    tenor_months: int = Field(ge=0, le=360, description="Delivery tenor of the quote. 0 = spot proxy; 3/6/12/24/36/60 = forwards.")
    source: str = Field(default="GEX_CONTRACT", description="Provenance of the quote: ARGUS_NWE | ICIS | PLATTS | GEX_CONTRACT. Kept in the audit trail.")
    molecule: str = Field(description="Molecule the quote belongs to. Canonical key or alias (see GET /molecules).")
    volume_tonnes: float = Field(default=1.0, ge=0, description="Traded/contracted volume — observations are volume-weighted within each tenor bucket.")


class CalibrateRequest(BaseModel):
    """Calibrate the per-molecule Gabillon curve from market observations."""
    molecule: str = Field(description="Canonical key (H2, NH3, E_METHANOL, SAF, E_NG, HVO, …) or alias such as 'e-Methanol'. See GET /molecules.")
    observations: list[PriceObservationRequest] = Field(default=[], description="Market quotes to fit. EMPTY list = keep SEED expert priors (calibration_status stays SEED).")
    capex_floor_eur_t: float = Field(default=0.0, ge=0, description="Levelised production cost floor in €/t from Plant Builder (LCOH/LCOF). 0 = keep the seeded floor.")
    cumulative_capacity_gw: float = Field(default=5.0, ge=0, description="Installed global capacity (GW) anchoring the learning curve that erodes the CAPEX floor.")


class ForwardPriceRequest(BaseModel):
    """Price a single forward (also available via GET /forward query params)."""
    molecule: str = Field(description="Canonical key or alias — see GET /molecules.")
    tenor_months: int = Field(ge=1, le=360, description="Delivery tenor in months (converted to years internally: τ = months/12).")
    spot_override: Optional[float] = Field(default=None, description="Scenario spot in €/t. Default: implied spot from the current calibration.")
    delta_override: Optional[float] = Field(default=None, description="Scenario convenience yield δ. Default: calibrated value (θ₀ at seed).")


class SimulateRequest(BaseModel):
    """Monte-Carlo simulation of correlated spot + convenience-yield paths."""
    molecule: str = Field(description="Canonical key or alias — see GET /molecules.")
    horizon_years: float = Field(default=5.0, ge=0.5, le=30, description="Simulation horizon in years.")
    n_paths: int = Field(default=2000, ge=100, le=20000, description="Number of Monte-Carlo paths. More paths → tighter percentiles, slower response.")
    spot_override: Optional[float] = Field(default=None, description="Scenario starting spot in €/t. Default: implied spot from calibration.")
    capex_floor_override: Optional[float] = Field(default=None, description="Scenario LCOH/LCOF floor in €/t — paths below it get an upward mean-reversion pull.")


class TrancheInput(BaseModel):
    """One debt tranche of the financing structure (drives WACC + DFI components)."""
    name: str = Field(description="Tranche label, kept verbatim in the lineage audit trail (e.g. 'EIB Concessional').")
    tranche_type: str = Field(default="senior", description="senior | junior | mezzanine | green_bond | concessional | concessional_first_loss. Concessional tranches generate the DFI absorption credit.")
    amount: float = Field(ge=0, description="Tranche principal in EUR.")
    rate: float = Field(ge=0, le=1, description="All-in interest rate as a decimal (0.041 = 4.1%).")
    tenor: int = Field(ge=1, le=50, description="Tranche maturity in years — used in the capital-recovery factor.")
    grace_period_years: int = Field(default=0, ge=0, description="Interest-only years; feeds the Grace Period Benefit component.")
    dfi_provider: Optional[str] = Field(default=None, description="DFI behind the tranche (EIB, KFW, …). Listed in the lineage and the WACC card.")
    is_first_loss: bool = Field(default=False, description="Marks catalytic first-loss capital — used in the catalytic ratio.")


class DecompositionRequest(BaseModel):
    """
    Request for the Information Lineage (Cost DNA waterfall).

    Only `molecule` is required. Everything else is OPTIONAL deal context:
    financing fields add the WACC/DFI components, subsidies add the bridge
    to effective offtaker cost, insurance adds a €/t premium line.
    """
    molecule: str = Field(description="Canonical key (H2, NH3, E_METHANOL, SAF, E_NG, HVO, …) or alias like 'e-Methanol'. Valid inputs: GET /molecules.")
    tenor_months: int = Field(default=12, ge=1, le=360, description="Delivery tenor in months for the decomposed forward.")
    spot_override: Optional[float] = Field(default=None, description="Scenario spot in €/t. Default: implied spot from the current calibration (= long-run equilibrium at SEED).")
    # Financing structure (optional — when provided, adds financing components)
    tranches: list[TrancheInput] = Field(default=[], description="Debt tranches. Empty list + equity_amount 0 = no financing components in the waterfall.")
    equity_amount: float = Field(default=0.0, ge=0, description="Equity in the capital stack, EUR — weighted at equity_cost in the blended WACC.")
    equity_cost: float = Field(default=0.12, ge=0, le=1, description="Required return on equity as a decimal (default 12%).")
    grants_amount: float = Field(default=0.0, ge=0, description="Non-repayable grants, EUR — reduce the financed base, carry no return requirement.")
    # Subsidies (optional — EUR/kg values)
    subsidies: dict[str, float] = Field(default={}, description="Subsidy name → value in €/kg OF PRODUCT (engine multiplies ×1000 to €/t). {'45V': 3.0} = €3,000/t — correct for H2, must be scaled down for derived molecules. Subsidies do NOT change the forward; they bridge to effective offtaker cost.")
    # Insurance (optional)
    insurance_annual_eur: float = Field(default=0.0, ge=0, description="Annual insurance premium in EUR/year — converted to €/t via annual_production_tonnes.")
    insurance_provider: str = Field(default="", description="Insurer name shown as the source of the insurance lineage row.")
    # Production context
    annual_production_tonnes: float = Field(default=18_250, ge=0, description="Plant output in t/year used to allocate annual costs per tonne (default 18,250 = 50 t/day × 365).")
    certifications: list[str] = Field(default=[], description="Display context (RED_III, RFNBO, 45V, …) listed on the subsidy card — does not change the numbers.")
    correlation_id: str = Field(default="", description="Caller-supplied trace ID propagated into every component for audit joins across systems.")


# ════════════════════════════════════════════════════════════════
# IN-MEMORY CALIBRATION STORE
# ════════════════════════════════════════════════════════════════

_calibrated: dict = {}   # molecule → CalibrationResult


def _get_or_default_calibration(molecule: str):
    """Return stored calibration or compute from seed params."""
    molecule = normalize_molecule(molecule)
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

_MOLECULE_UNITS = {
    "E_NG": "€/MWh",
    "E_METHANE": "€/MWh",
    "E_LG": "€/MWh",
    "H2": "€/t (≡ €/kg × 1000)",
}


@router.get(
    "/molecules",
    summary="Molecule catalogue — the valid `molecule` inputs for every other endpoint",
)
async def list_molecules():
    """
    Returns the molecules this engine can price, in two forms:

    - **`molecules`** — display labels from the platform fuel catalogue
      (`fuel_catalog` table; falls back to the bundled legacy JSON).
      Kept for backward compatibility.
    - **`catalog`** — one entry per molecule with everything needed to call
      the other endpoints:
        - `label` — human display name (e.g. "e-Methanol")
        - `key` — canonical engine key to pass as `molecule`
          (e.g. "E_METHANOL"). Aliases like "e-methanol" or "CH3OH" are
          also accepted and normalised server-side.
        - `unit` — price unit of every €-figure returned for this molecule
          (€/t for most; €/MWh for gas-like; H2 is €/t ≡ €/kg × 1000)
        - `calibration_status` — "SEED" (expert priors, n_observations = 0)
          or "MARKET" (fitted to observations via POST /calibrate)
        - `spot_eur` — current implied spot in `unit`

    Example: `catalog[i].key` → `GET /term-curve/{key}`,
    `POST /decomposition {"molecule": key, ...}`.
    """
    labels = _load_offered_molecules()
    catalog = []
    for label in labels:
        key = normalize_molecule(label)
        if key not in SUPPORTED_MOLECULES:
            continue
        result = _get_or_default_calibration(key)
        catalog.append({
            "label": label,
            "key": key,
            "unit": _MOLECULE_UNITS.get(key, "€/t"),
            "calibration_status": "MARKET" if result.n_observations > 0 else "SEED",
            "spot_eur": result.spot_price_eur,
        })
    return {"molecules": labels, "catalog": catalog}


@router.post(
    "/calibrate",
    summary="Fit the molecule curve to market observations (replaces SEED priors)",
)
async def calibrate(req: CalibrateRequest):
    """
    Calibrate the Gabillon model for ONE molecule from market price quotes.

    Pipeline:
    1. Cluster observations by tenor
    2. Volume-weighted average per tenor bucket
    3. Bootstrap spot price from the shortest tenor
    4. Estimate convenience-yield level θ₀ from the term-structure slope
    5. Update the long-run equilibrium μ from ≥24-month observations
    6. Apply the CAPEX floor constraint

    Pass an EMPTY `observations` list to (re)apply seed parameters — useful
    for patching only the CAPEX floor from a new Plant Builder run.

    Response: fitted parameters (see `docs/GABILLON_MODEL.md` §3 for what
    each one means), the implied spot, mean-reversion half-life in months,
    seasonal amplitude %, fit error % (`calibration_error_pct`), and the
    full 1M–60M term curve. `n_observations > 0` flips every downstream
    endpoint from SEED to MARKET status.
    """
    molecule = normalize_molecule(req.molecule)
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(
            status_code=400,
            detail=f"Molecule '{req.molecule}' not supported. Use: {_load_offered_molecules()}",
        )

    obs_objs = [
        PriceObservation(
            date=o.date,
            price_eur=o.price_eur,
            tenor_months=o.tenor_months,
            source=o.source,
            molecule=normalize_molecule(o.molecule),
            volume_tonnes=o.volume_tonnes,
        )
        for o in req.observations
    ]

    model = get_gabillon_model()
    result = model.calibrate(obs_objs, req.capex_floor_eur_t, molecule, req.cumulative_capacity_gw)

    # Parameter governance: bounds-check the FITTED set before accepting it.
    # A calibration that lands outside sanity bounds is rejected, not stored —
    # garbage quotes must not silently become the live parameter set.
    new_params = _serialize_params(result.params)
    bounds_violations = validate_params(new_params)
    if bounds_violations:
        raise HTTPException(status_code=422, detail={
            "error": "PARAM_OUT_OF_BOUNDS",
            "message": "Fitted parameters violate sanity bounds — calibration rejected.",
            "violations": bounds_violations,
        })

    # Append-only parameter change register (old → new per field).
    old = _calibrated.get(molecule)
    old_params = _serialize_params(old.params) if old else None
    change = log_param_change(
        molecule, old_params, new_params,
        n_observations=result.n_observations,
        source="POST /calibrate" + (" (seed re-apply)" if not obs_objs else ""),
    )
    _calibrated[molecule] = result

    return {
        "molecule": molecule,
        "status": "calibrated",
        "param_change": change,
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


@router.get(
    "/spot/{molecule}",
    summary="Implied spot price + curve anchors for a molecule",
)
async def get_spot_price(molecule: str):
    """
    Current implied spot price from the molecule's calibration (SEED priors
    if never calibrated — check the `source` field in the response).

    Response fields: `spot_price_eur_t` (implied spot), `convenience_yield`
    (current δ), `capex_floor_eur_t` (LCOH/LCOF floor),
    `long_term_equilibrium_eur_t` (e^μ — where the curve flattens),
    `mean_reversion_half_life_months` (ln2/α), quarterly `seasonal` factors,
    and `source`: SEED_CALIBRATION | MARKET_CALIBRATION.
    """
    molecule = normalize_molecule(molecule)
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


@router.get(
    "/term-curve/{molecule}",
    summary="Full forward term structure (1M–60M) — offtake reference pricing",
)
async def get_term_curve(
    molecule: str,
    spot_override: Optional[float] = Query(default=None, description="Scenario spot in €/t — shifts the whole curve; default is the calibrated implied spot."),
):
    """
    Forward curve at tenors 1, 3, 6, 9, 12, 18, 24, 30, 36, 48, 60 months.

    Each curve point: `tenor_months`, `price_eur` (the forward),
    `carry_eur` (forward − spot, ≤12M only), `annualised_return_pct`.
    `market_structure` classifies the 12M point: CONTANGO (forward > spot),
    BACKWARDATION (forward < spot) or FLAT (±0.5%).

    Used as the reference curve in offtake negotiations.
    """
    molecule = normalize_molecule(molecule)
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

    # Governance: invariant guards (engine-side, blocking) + audited run stamp.
    violations = check_invariants(
        spot, [(c["tenor_months"] / 12.0, c["price_eur"]) for c in curve],
        capex_floor=result.capex_floor_eur,
    )
    if blocking(violations):
        raise HTTPException(status_code=422, detail={
            "error": "MODEL_INVARIANT_VIOLATION",
            "message": "Engine refuses to serve a curve violating its own invariants.",
            "violations": blocking(violations),
        })
    stamp = governance_stamp(
        "term-curve", molecule, _serialize_params(params), result.n_observations,
        {"molecule": molecule, "spot": spot, "spot_override": spot_override, "tenors": tenors},
        violations,
    )
    # Challenger: the engineering cost floor is an independent derivation of
    # the same number — divergence is the signal, on every curve served.
    stamp["challenger"] = challenger_assessment(fwd_12m, result.capex_floor_eur)

    return {
        "molecule": molecule,
        "spot_price_eur": spot,
        "market_structure": market_structure,
        "term_curve": curve,
        "capex_floor_eur_t": result.capex_floor_eur,
        "long_term_equilibrium_eur_t": round(__import__('math').exp(params.mu_base), 2),
        "last_calibrated": result.last_calibrated,
        "governance": stamp,
    }


@router.get(
    "/forward",
    summary="Single forward price at one tenor",
)
async def get_forward_price(
    molecule: str = Query(..., description="Canonical key or alias — see GET /molecules."),
    tenor_months: int = Query(..., ge=1, le=360, description="Delivery tenor in months (τ = months/12 years internally)."),
    spot_override: Optional[float] = Query(default=None, description="Scenario spot in €/t; default = calibrated implied spot."),
):
    """
    One Gabillon forward price. Response: `forward_price_eur_t`,
    `carry_eur_t` (forward − spot) and `carry_pct` (carry as % of spot —
    positive = contango, negative = backwardation).
    """
    molecule = normalize_molecule(molecule)
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")

    result = _get_or_default_calibration(molecule)
    model = get_gabillon_model()

    spot = spot_override if spot_override and spot_override > 0 else result.spot_price_eur
    delta = result.convenience_yield

    fwd = model.forward_price(result.params, spot, delta, tenor_months / 12.0)

    violations = check_invariants(spot, [(tenor_months / 12.0, fwd)], capex_floor=result.capex_floor_eur)
    if blocking(violations):
        raise HTTPException(status_code=422, detail={
            "error": "MODEL_INVARIANT_VIOLATION",
            "message": "Engine refuses to serve a forward violating its own invariants.",
            "violations": blocking(violations),
        })
    stamp = governance_stamp(
        "forward", molecule, _serialize_params(result.params), result.n_observations,
        {"molecule": molecule, "spot": spot, "tenor_months": tenor_months, "spot_override": spot_override},
        violations,
    )

    return {
        "molecule": molecule,
        "spot_eur_t": spot,
        "tenor_months": tenor_months,
        "forward_price_eur_t": fwd,
        "carry_eur_t": round(fwd - spot, 2),
        "carry_pct": round(100 * (fwd / spot - 1), 2) if spot > 0 else 0.0,
        "governance": stamp,
    }


@router.post(
    "/simulate",
    summary="Monte-Carlo price paths → VaR + annual percentile cone",
)
async def simulate_price_paths(req: SimulateRequest):
    """
    Simulate correlated spot/convenience-yield paths under the calibrated
    parameters (real-world P-measure, with CAPEX-floor pull).

    Response: `terminal_stats` (mean, std, p5/p95, VaR-95, CVaR-95 of the
    terminal price) and `annual_percentiles` (p5/p25/median/p75/p95/mean at
    each year) — the forecast cone. Full paths are NOT returned (too large).
    Requires numpy; returns status NUMPY_UNAVAILABLE otherwise.
    """
    molecule = normalize_molecule(req.molecule)
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=400, detail=f"Molecule '{req.molecule}' not supported")

    result = _get_or_default_calibration(molecule)
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
            "molecule": molecule,
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
        "molecule": molecule,
        "horizon_years": req.horizon_years,
        "n_paths": req.n_paths,
        "spot_price_eur": spot,
        "terminal_stats": stats,
        "annual_percentiles": checkpoints,
        "capex_floor_eur_t": params.capex_floor_eur_t,
    }


@router.get(
    "/seasonal/{molecule}",
    summary="Quarterly seasonal factors (Fourier decomposition)",
)
async def get_seasonal_decomposition(molecule: str):
    """
    Quarterly multiplicative factors from the calibrated Fourier terms
    (a₁·sin + a₂·cos). Factor 1.04 = Q prices 4% above the deseasonalised
    curve. Also returns `seasonal_amplitude_pct` (peak-to-mid swing),
    `peak_quarter`, `trough_quarter`, and the raw `season_a1`/`season_a2`
    coefficients for audit.
    """
    molecule = normalize_molecule(molecule)
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


@router.get(
    "/params/{molecule}",
    summary="Raw Gabillon parameters — the audit view",
)
async def get_model_params(molecule: str):
    """
    The full parameter set behind every price for this molecule:
    α (mean-reversion speed, yr⁻¹), μ (long-run equilibrium as LOG level —
    e^μ is the anchor price), σ_S (spot vol), κ/θ₀/σ_δ (convenience-yield
    dynamics), ρ (factor correlation), seasonal a₁/a₂, learning rate,
    CAPEX floor, regulatory premium, and calibration metadata.

    Parameter-by-parameter meaning, units, and the audit questions to ask:
    `docs/GABILLON_MODEL.md` §3. `calibration_status` SEED means expert
    priors — no market observations loaded yet.
    """
    molecule = normalize_molecule(molecule)
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")
    result = _get_or_default_calibration(molecule)
    return {
        "molecule": molecule,
        "params": _serialize_params(result.params),
        "calibration_status": "MARKET" if result.n_observations > 0 else "SEED",
    }


@router.get(
    "/cfads-integration/{molecule}",
    summary="Annual price deck for the CFADS revenue line",
)
async def get_cfads_price_inputs(
    molecule: str,
    project_life_years: int = Query(default=20, ge=1, le=50, description="Number of operating years to project."),
    start_year: int = Query(default=1, ge=1, description="First operating year (1 = COD year)."),
):
    """
    Annual price projections feeding `ProjectFinanceEngine.compute_cfads()`.

    For each year: `price_eur_t` (mid-year Gabillon forward, nominal) and
    `price_real_eur_t` (deflated at 2%/yr real). Long-dated points converge
    to the long-run equilibrium e^μ — they are MODEL extrapolation, not
    market quotes; check `calibration_status` via GET /params first.
    """
    molecule = normalize_molecule(molecule)
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


# ════════════════════════════════════════════════════════════════
# PRICE DECOMPOSITION — Information Lineage
# ════════════════════════════════════════════════════════════════

def _build_financing_structure(req: DecompositionRequest) -> Optional[FinancingStructure]:
    """Build FinancingStructure from request tranches."""
    if not req.tranches and req.equity_amount <= 0:
        return None

    tranche_type_map = {
        "senior": TrancheType.SENIOR,
        "junior": TrancheType.JUNIOR,
        "mezzanine": TrancheType.MEZZANINE,
        "green_bond": TrancheType.GREEN_BOND,
        "concessional": TrancheType.CONCESSIONAL,
        "concessional_first_loss": TrancheType.CONCESSIONAL_FIRST_LOSS,
    }
    dfi_map = {p.value.upper(): p for p in DFIProvider}

    tranches = []
    for t in req.tranches:
        tt = tranche_type_map.get(t.tranche_type.lower(), TrancheType.SENIOR)
        dfi = None
        if t.dfi_provider:
            dfi = dfi_map.get(t.dfi_provider.upper(), DFIProvider.OTHER)
        tranches.append(Tranche(
            name=t.name,
            tranche_type=tt,
            amount=t.amount,
            rate=t.rate,
            tenor=t.tenor,
            grace_period_years=t.grace_period_years,
            dfi_provider=dfi,
            is_first_loss=t.is_first_loss,
        ))

    return FinancingStructure(
        tranches=tranches,
        equity_amount=req.equity_amount,
        equity_cost=req.equity_cost,
        grants_amount=req.grants_amount,
    )


@router.post(
    "/decomposition",
    summary="Information Lineage — decompose one forward into auditable cost drivers",
)
async def price_decomposition(req: DecompositionRequest):
    """
    Decompose a forward price into its constituent cost drivers (the Cost
    DNA waterfall). Reconciliation identity, enforced:

        MARKET (Gabillon): spot basis + convenience yield + mean reversion
                           + seasonality + CAPEX floor + residual
        COST STACK:        + regulatory premium + financing spread
                           + concessional absorption + grace period benefit
                           + insurance premium
                           = forward_price_eur_t  (the contract forward)
        BRIDGE:            + Σ subsidies (negative)
                           = effective offtaker cost

    The `residual` reconciles ONLY the market terms (Jensen + cross-term
    non-linearity) and must stay small. Subsidies never change the forward.
    Each component carries `source`, `explanation`, and the request's
    `correlation_id` for tracing to the originating event.
    Formulas per component: `docs/GABILLON_MODEL.md` §5.
    """
    molecule = normalize_molecule(req.molecule)
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(
            status_code=400,
            detail=f"Molecule '{req.molecule}' not supported. Use: {_load_offered_molecules()}",
        )

    financing = _build_financing_structure(req)

    engine = PriceLineageEngine()
    decomposition = engine.decompose(
        molecule=molecule,
        tenor_months=req.tenor_months,
        spot_override=req.spot_override,
        financing=financing,
        subsidies=req.subsidies if req.subsidies else None,
        insurance_annual_eur=req.insurance_annual_eur,
        insurance_provider=req.insurance_provider,
        annual_production_tonnes=req.annual_production_tonnes,
        certifications=req.certifications,
        correlation_id=req.correlation_id,
    )

    d = decomposition.to_dict()
    violations = check_invariants(
        d.get("spot_price_eur_t", 0.0),
        [(req.tenor_months / 12.0, d.get("forward_price_eur_t", 0.0))],
    )
    if blocking(violations):
        raise HTTPException(status_code=422, detail={
            "error": "MODEL_INVARIANT_VIOLATION",
            "message": "Engine refuses to serve a decomposition violating its own invariants.",
            "violations": blocking(violations),
        })
    cal = _get_or_default_calibration(molecule)
    stamp = governance_stamp(
        "decomposition", molecule, _serialize_params(cal.params), cal.n_observations,
        req.model_dump() if hasattr(req, "model_dump") else req.dict(),
        violations,
    )

    return {
        "success": True,
        "decomposition": d,
        "governance": stamp,
    }


@router.post(
    "/decomposition/multi-tenor",
    summary="Information Lineage across the whole term structure",
)
async def price_decomposition_multi_tenor(req: DecompositionRequest):
    """
    Same decomposition as POST /decomposition, repeated at the standard
    tenors 1M, 3M, 6M, 12M, 24M, 36M, 60M (`tenor_months` in the request is
    ignored). Returns one decomposition per tenor — shows how each cost
    driver evolves along the curve.
    """
    molecule = normalize_molecule(req.molecule)
    if molecule not in SUPPORTED_MOLECULES:
        raise HTTPException(
            status_code=400,
            detail=f"Molecule '{req.molecule}' not supported. Use: {_load_offered_molecules()}",
        )

    financing = _build_financing_structure(req)

    engine = PriceLineageEngine()
    results = engine.decompose_multi_tenor(
        molecule=molecule,
        financing=financing,
        spot_override=req.spot_override,
        subsidies=req.subsidies if req.subsidies else None,
        insurance_annual_eur=req.insurance_annual_eur,
        insurance_provider=req.insurance_provider,
        annual_production_tonnes=req.annual_production_tonnes,
        certifications=req.certifications,
        correlation_id=req.correlation_id,
    )

    return {
        "success": True,
        "molecule": molecule,
        "tenor_count": len(results),
        "decompositions": results,
    }


@router.get(
    "/model/changelog",
    summary="Model change register — what changed, why, approved by whom",
)
async def model_changelog():
    """
    Human-readable model change register, independent of git. Auditors and
    model-risk reviewers read THIS, not commit history. Every priced response
    carries `governance.model_version` referencing an entry here.
    """
    return {
        "current_version": GABILLON_MODEL_VERSION,
        "register": MODEL_CHANGE_REGISTER,
    }


@router.get(
    "/model/runs",
    summary="Append-only pricing run audit log",
)
async def model_runs(limit: int = Query(default=100, ge=1, le=500)):
    """
    Every priced response is logged with model version, calibration
    fingerprint, input hash and run id — any number GEX has ever served
    can be traced back to exactly what produced it.
    """
    runs = recent_runs(limit)
    return {"count": len(runs), "runs": runs}


@router.get(
    "/model/card",
    summary="Model card — purpose, permitted/prohibited use, limitations, live status",
)
async def model_card():
    """
    The model card is served BY the engine so it can never silently drift
    from the model. `live_status` carries each molecule's CURRENT calibration
    state — the card's prohibited-use list applies in full while a molecule
    is in SEED status.
    """
    live = {}
    for mol in sorted(SUPPORTED_MOLECULES):
        try:
            r = _get_or_default_calibration(mol)
            live[mol] = {
                "calibration_status": "MARKET" if r.n_observations > 0 else "SEED",
                "n_observations": r.n_observations,
                "last_calibrated": r.last_calibrated,
                "capex_floor_eur_t": r.capex_floor_eur,
            }
        except HTTPException:
            continue
    return {
        "model_version": GABILLON_MODEL_VERSION,
        "card": MODEL_CARD,
        "live_status": live,
    }


@router.get(
    "/model/benchmark",
    summary="Benchmark Gabillon against transparent baselines (flat / cost-plus / one-factor)",
)
async def model_benchmark(molecule: str = Query(...)):
    """
    Compares the Gabillon curve against three deliberately simple baselines
    at standard tenors. `two_factor_premium_pct` isolates what the second
    factor (+ seasonality + Jensen + floor pull) adds over plain one-factor
    mean reversion — the parsimony question: do the extra parameters earn
    their complexity for this molecule?

    No market data exists for most molecules, so this is a STRUCTURAL
    benchmark (model vs model), not an accuracy benchmark. Accuracy
    benchmarking begins when transaction/proxy observations accumulate.
    """
    mol = normalize_molecule(molecule)
    if mol not in SUPPORTED_MOLECULES:
        raise HTTPException(status_code=404, detail=f"Molecule '{molecule}' not supported")
    result = _get_or_default_calibration(mol)
    model = get_gabillon_model()
    bench = benchmark_curves(
        model, result.params, result.spot_price_eur, result.convenience_yield,
        result.capex_floor_eur, [1, 3, 6, 12, 24, 36, 60],
    )
    return {
        "molecule": mol,
        "model_version": GABILLON_MODEL_VERSION,
        "calibration_status": "MARKET" if result.n_observations > 0 else "SEED",
        "spot_eur_t": result.spot_price_eur,
        **bench,
    }


@router.get(
    "/model/param-changes",
    summary="Append-only parameter change register",
)
async def model_param_changes(
    molecule: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Every accepted calibration logs which parameters changed, old → new,
    with the calibration fingerprints before and after. Parameter changes
    are model changes; this register is their audit trail.
    """
    mol = normalize_molecule(molecule) if molecule else None
    events = param_change_history(mol, limit)
    return {"count": len(events), "events": events}
