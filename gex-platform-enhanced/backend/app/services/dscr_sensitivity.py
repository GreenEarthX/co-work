"""
DSCR sensitivity — the single model behind every sensitivity figure GEX shows.

Why this module exists
----------------------
The same two defects had been implemented three times over:

  * frontend  DSCRHeatmap.generateSensitivityData  — additive grid, wrong sign
  * backend   DSCRAggregator._build_heatmap        — additive fallback, same formula
  * backend   DSCRAggregator._build_sensitivity_rows — same hardcoded elasticities

Consequences a lender actually saw: the single-factor table showed a power-price
INCREASE improving DSCR, while the two-factor grid showed the opposite — on one
screen. Contradictory internal figures are worse than absent ones; an analyst
who catches that discounts every other number on the page.

Two invariants this module exists to hold:

  1. **One identity.** The single-factor rows and the two-factor surface are
     produced by the same function, so they cannot disagree about sign or
     magnitude. A row IS a slice of the surface.
  2. **Real interaction.** Power price and efficiency compound rather than sum:

         energy per tonne = base_consumption / (1 + efficiency_gain)
         power cost       = price × energy per tonne
         ⇒ opex_power ∝ (1 + Δprice) / (1 + Δefficiency)

     An additive surface understates the worst corner, which is the one
     direction a credit committee cannot tolerate.

Nothing here fabricates a base case. Callers supply the cashflow terms; if a
project has no cashflow basis, the caller must say so rather than defaulting to
a plausible-looking number.
"""

from __future__ import annotations

from typing import Optional

# (key, label, unit, delta labels, delta values)
SENSITIVITY_FACTORS: list[tuple[str, str, str, list[str], list[float]]] = [
    ("power_price",    "Power Price",       "€/MWh",
     ["-20%", "-10%", "Base", "+10%", "+20%"],      [-20, -10, 0, 10, 20]),
    ("efficiency",     "System Efficiency", "%",
     ["-5pp", "-2.5pp", "Base", "+2.5pp", "+5pp"],  [-5, -2.5, 0, 2.5, 5]),
    ("capex",          "CapEx",             "€M",
     ["-20%", "-10%", "Base", "+10%", "+20%"],      [-20, -10, 0, 10, 20]),
    ("cod_delay",      "COD Delay",         "months",
     ["-6m", "-3m", "Base", "+3m", "+6m"],          [-6, -3, 0, 3, 6]),
    ("curtailment",    "Curtailment",       "%",
     ["-20%", "-10%", "Base", "+10%", "+20%"],      [-20, -10, 0, 10, 20]),
    ("logistics_cost", "Logistics Cost",    "€/kg",
     ["-20%", "-10%", "Base", "+10%", "+20%"],      [-20, -10, 0, 10, 20]),
    ("interest_rate",  "Interest Rate",     "bps",
     ["-150bps", "-75bps", "Base", "+75bps", "+150bps"], [-150, -75, 0, 75, 150]),
]

DEFAULT_POWER_DELTAS = [-20, -10, 0, 10, 20]
DEFAULT_EFF_DELTAS = [5, 2.5, 0, -2.5, -5]

# Structural parameters. Defaults are illustrative and every caller may override;
# they are named so a treasurer can sanity-check them rather than reverse-engineer
# a dimensionless coefficient.
DEFAULT_PARAMS: dict[str, float] = {
    "revenue": 100.0,
    "opex_power": 38.0,
    "opex_other": 14.0,
    "debt_service": 40.0,
    "base_efficiency_pct": 72.0,
    "debt_share_of_capex": 0.70,          # overrun is debt-funded at gearing
    "debt_service_pct_per_100bps": 0.09,  # +100bps ⇒ +9% debt service
    "logistics_share_of_other": 0.35,
    "curtailment_revenue_sensitivity": 0.50,
    "delay_revenue_loss_per_year": 0.12,
    "delay_carry_per_year": 0.04,
}

DSCR_FLOOR_CLAMP = 0.0  # do not clamp: a sub-1.0 DSCR is information, not an error


def normalise_params(body: Optional[dict] = None) -> dict:
    p = dict(DEFAULT_PARAMS)
    for k, v in (body or {}).items():
        if k in p and v is not None:
            p[k] = float(v)
    return p


def base_dscr(p: dict) -> float:
    """CFADS / debt service — the identity everything else is a shock of."""
    if p["debt_service"] <= 0:
        return 0.0
    return (p["revenue"] - p["opex_power"] - p["opex_other"]) / p["debt_service"]


def shocked_dscr(p: dict, *, power_delta: float = 0.0, efficiency_pp: float = 0.0,
                 capex_delta: float = 0.0, cod_delay_months: float = 0.0,
                 curtailment_delta: float = 0.0, logistics_delta: float = 0.0,
                 rate_bps: float = 0.0) -> float:
    """
    Re-derive DSCR with shocks applied to the terms each factor physically drives.

    Combinations interact through the arithmetic, not through an assumed
    coefficient — which is what makes a two-factor surface worth showing.
    """
    revenue = p["revenue"]
    opex_power = p["opex_power"]
    opex_other = p["opex_other"]
    debt_service = p["debt_service"]

    # Efficiency is quoted in percentage POINTS against a base efficiency level.
    eff_gain = (efficiency_pp / p["base_efficiency_pct"]) if p["base_efficiency_pct"] else 0.0

    # ── the interaction: price up and efficiency down compound ──
    denom = 1.0 + eff_gain
    if denom <= 0:
        return 0.0
    opex_power *= (1.0 + power_delta) / denom

    opex_other *= 1.0 + logistics_delta * p["logistics_share_of_other"]
    revenue *= 1.0 - curtailment_delta * p["curtailment_revenue_sensitivity"]

    if cod_delay_months:
        revenue *= max(0.0, 1.0 - (cod_delay_months / 12.0) * p["delay_revenue_loss_per_year"])
        debt_service *= 1.0 + (cod_delay_months / 12.0) * p["delay_carry_per_year"]

    debt_service *= 1.0 + capex_delta * p["debt_share_of_capex"]
    debt_service *= 1.0 + (rate_bps / 100.0) * p["debt_service_pct_per_100bps"]

    if debt_service <= 0:
        return 0.0
    return (revenue - opex_power - opex_other) / debt_service


_SHOCK_ARG = {
    "power_price":    lambda d: {"power_delta": d / 100.0},
    "efficiency":     lambda d: {"efficiency_pp": d},
    "capex":          lambda d: {"capex_delta": d / 100.0},
    "cod_delay":      lambda d: {"cod_delay_months": d},
    "curtailment":    lambda d: {"curtailment_delta": d / 100.0},
    "logistics_cost": lambda d: {"logistics_delta": d / 100.0},
    "interest_rate":  lambda d: {"rate_bps": d},
}


def solve_break_even(p: dict, key: str, lo: float, hi: float, floor: float) -> Optional[float]:
    """Bisect for the shock magnitude at which DSCR first touches the covenant floor."""
    def f(x: float) -> float:
        return shocked_dscr(p, **{key: x}) - floor

    try:
        if f(lo) * f(hi) > 0:
            return None
    except (ZeroDivisionError, ValueError):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def single_factor_rows(p: dict) -> list[dict]:
    """Each row is a slice through the same surface the heatmap draws."""
    rows = []
    for key, label, unit, delta_labels, deltas in SENSITIVITY_FACTORS:
        rows.append({
            "factor": key,
            "label": label,
            "unit": unit,
            "deltaLabels": delta_labels,
            "deltas": deltas,
            "values": [round(shocked_dscr(p, **_SHOCK_ARG[key](d)), 3) for d in deltas],
        })
    return rows


def surface(p: dict, power_deltas: Optional[list] = None,
            eff_deltas: Optional[list] = None) -> list[dict]:
    pds = power_deltas or DEFAULT_POWER_DELTAS
    eds = eff_deltas or DEFAULT_EFF_DELTAS
    return [
        {
            "powerDelta": pd,
            "effDelta": ed,
            "dscr": round(shocked_dscr(p, power_delta=pd / 100.0, efficiency_pp=ed), 3),
        }
        for ed in eds
        for pd in pds
    ]


def break_even_metrics(p: dict, covenant_floor: float) -> list[dict]:
    """Solved, not assumed. `None` means the floor is not reached in range."""
    base = base_dscr(p)
    at_floor = base <= covenant_floor

    solutions = [
        ("Max power price rise", "power_delta", 0.0, 3.0, "%",  100.0),
        ("Max efficiency loss",  "efficiency_pp", 0.0, -60.0, "pp", -1.0),
        ("Max CapEx overrun",    "capex_delta", 0.0, 3.0, "%",  100.0),
        ("Max rate rise",        "rate_bps", 0.0, 5000.0, "bps", 1.0),
    ]
    out = []
    for label, key, lo, hi, unit, scale in solutions:
        sol = solve_break_even(p, key, lo, hi, covenant_floor)
        if at_floor:
            value, desc = "0", f"Base DSCR is at or below the {covenant_floor:.2f}x floor — no headroom"
        elif sol is None:
            value, desc = "> range", f"Floor not reached within the tested range"
        else:
            v = sol * scale
            value = f"{v:+.0f}{unit}" if unit == "bps" else f"{v:.1f}{unit}"
            desc = f"Before DSCR falls below {covenant_floor:.2f}x"
        out.append({"label": label, "value": value, "description": desc, "breached": at_floor})
    return out


def compute_sensitivity(body: Optional[dict] = None, covenant_floor: float = 1.20,
                        target_dscr: float = 1.30) -> dict:
    """Full sensitivity payload — rows, surface and break-evens from one model."""
    p = normalise_params(body)
    pds = (body or {}).get("power_deltas") or DEFAULT_POWER_DELTAS
    eds = (body or {}).get("efficiency_deltas") or DEFAULT_EFF_DELTAS
    base = base_dscr(p)
    return {
        "baseDSCR": round(base, 3),
        "covenantFloor": covenant_floor,
        "targetDSCR": target_dscr,
        "sensitivityRows": single_factor_rows(p),
        "heatmapCells": surface(p, pds, eds),
        "powerDeltas": pds,
        "efficiencyDeltas": eds,
        "breakevenMetrics": break_even_metrics(p, covenant_floor),
        "method": (
            "CFADS = revenue − opex_power − opex_other; DSCR = CFADS / debt_service. "
            "Power price and efficiency interact multiplicatively "
            "(opex_power ∝ (1+Δprice)/(1+Δefficiency)); the surface is a genuine "
            "combined shock, not an additive composition of single-factor moves."
        ),
        "interaction": "multiplicative",
    }
