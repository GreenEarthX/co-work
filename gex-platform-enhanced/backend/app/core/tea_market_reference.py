"""The product's Gabillon price, set beside a TEA run's required price (20 Nov 2026).

The TEA answers "what price recovers the plant's costs" (LCOP). The PF engine's Gabillon
two-factor model answers "what does the market model expect the product to fetch". Both are
recorded WITH the run, on the same basis, so the comparison reprints unchanged:

  · the Gabillon annual price deck in REAL terms (the TEA is in constant cost-base money),
  · levelised over the run's own production years at the run's own discount rate:
        sum(P_t * Q_t * d_t) / sum(Q_t * d_t)
    which is the same arithmetic that makes the LCOP, so the two figures are comparable.

What it is not: a market quote, an offtake price or a forecast GEX stands behind. While the
molecule is SEED (expert priors, no market observations) every figure says so. A molecule
the engine prices per MWh is not converted: no energy content is stated for it here.
"""
from __future__ import annotations

from typing import Any, Optional

MODEL = "Gabillon two-factor (PF engine)"


def levelise(prices: list[float], production: list[float], discount: list[float]) -> Optional[float]:
    den = sum(q * d for q, d in zip(production, discount))
    if den <= 0:
        return None
    return sum(p * q * d for p, q, d in zip(prices, production, discount)) / den


def build(breakdown: dict, lcop: Optional[float], molecule: str, params: dict, deck: dict,
          unit: str) -> dict[str, Any]:
    """Pure: the reference from the run's breakdown and the engine's answers."""
    years = [y for y in breakdown.get("years") or [] if (y.get("production_kg") or 0) > 0]
    status = params.get("calibration_status") or "UNKNOWN"
    p = params.get("params") or {}
    head = {"model": MODEL, "molecule": molecule, "calibration_status": status,
            "n_observations": p.get("n_observations"), "last_calibrated": p.get("last_calibrated")}
    if (breakdown.get("currency") or "").upper() != "EUR":
        return {**head, "applies": False,
                "reason": f"The Gabillon deck is in EUR; this run is in {breakdown.get('currency')}."}
    if not unit.startswith("€/t"):
        return {**head, "applies": False,
                "reason": f"Gabillon prices {molecule} in {unit}; the TEA is per kg and no energy content "
                          "is stated to convert it."}
    annual = deck.get("annual_prices") or []
    if len(annual) < len(years) or not years:
        return {**head, "applies": False, "reason": "The Gabillon deck does not cover the run's production years."}
    real = [a["price_real_eur_t"] / 1000.0 for a in annual[:len(years)]]
    lev = levelise(real, [y["production_kg"] for y in years], [y["discount_factor"] for y in years])
    return {**head, "applies": True, "unit": "EUR/kg",
            "spot": deck.get("spot_eur_t", 0) / 1000.0,
            "long_term_equilibrium": (deck.get("long_term_equilibrium_eur_t") or 0) / 1000.0,
            "capex_floor": (deck.get("capex_floor_eur_t") or 0) / 1000.0,
            "half_life_months": deck.get("mean_reversion_half_life_months"),
            "years": [{"year": y["year"], "operating_year": i + 1, "price_real": real[i],
                       "price_nominal": annual[i]["price_eur_t"] / 1000.0} for i, y in enumerate(years)],
            "levelised_price": lev, "required_price": lcop,
            "difference": (lcop - lev) if (lcop is not None and lev is not None) else None,
            "basis": ("Real Gabillon price per operating year (the PF engine deflates its nominal forward at "
                      "2%/yr), levelised over this run's production and discount factors: the LCOP's own "
                      "arithmetic."),
            "standing": ("SEED: expert priors, no market observations. A model reference, not a market quote "
                         "or an offtake price.") if status == "SEED" else
                        f"{status}: fitted to {p.get('n_observations')} market observations."}


async def fetch(fuel_id: Optional[str], breakdown: Optional[dict], lcop: Optional[float]) -> dict[str, Any]:
    """Ask the PF engine for the molecule's parameters and deck; a failure is recorded, never zero."""
    from fastapi import HTTPException

    from app.api.v1.routes_pricing_proxy import _call_pricing
    if not fuel_id or not breakdown:
        return {"model": MODEL, "applies": False, "reason": "No product or breakdown recorded for this run."}
    try:
        cat = await _call_pricing("/molecules")
        units = {c["key"]: c.get("unit", "€/t") for c in cat.get("catalog", [])}
        params = await _call_pricing(f"/params/{fuel_id}")
        molecule = params.get("molecule") or fuel_id
        n = sum(1 for y in breakdown.get("years") or [] if (y.get("production_kg") or 0) > 0)
        deck = await _call_pricing(f"/cfads-integration/{molecule}?project_life_years={max(n, 1)}")
    except HTTPException as e:
        return {"model": MODEL, "applies": False,
                "reason": f"The PF engine gave no Gabillon price for {fuel_id}: {str(e.detail)[:300]}"}
    return build(breakdown, lcop, molecule, params, deck, units.get(molecule, "€/t"))
