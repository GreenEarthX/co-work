"""Pure ratio computations.

These functions are numerically aligned with their TypeScript counterparts
in src/lib/finance/financeFormulas.ts. The TS code stays canonical for live
preview; Python mirrors it for authoritative compute. Drift between them is
prevented by golden test fixtures (tests/test_compute.py) that both
implementations must agree on.

The TS code is well-written and has been kept verbatim in behaviour where
possible. The only intentional differences:
  - DSCR uses CFADS rather than (EBITDA − tax); for Sprint 2, CFADS still
    excludes working-capital movement and maintenance capex, but the
    contract uses the right name so Sprint 3 can extend without renaming.
  - Rating band is more granular than the TS three-bucket version (IG /
    Spec / Distressed): we extend with BBB-/BBB/BBB+/A subdivision when
    LLCR is also provided.
"""
from __future__ import annotations

import math
from typing import Optional


def annuity_payment(principal: float, annual_rate: float, n_periods: int) -> float:
    """Annual annuity payment matching TS annuityPayment()."""
    if n_periods <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / n_periods
    return principal * annual_rate / (1.0 - math.pow(1.0 + annual_rate, -n_periods))


def npv_of_stream(cashflows: list[float], rate: float) -> float:
    """NPV with cashflows[0] at t=0. Matches TS npvOfStream()."""
    return sum(cf / math.pow(1.0 + rate, t) for t, cf in enumerate(cashflows))


def compute_npv(operating_cfads: list[float], discount_rate: float, capex: float) -> float:
    """NPV from operations CFADS stream, with capex as t=0 outflow."""
    return npv_of_stream([-capex] + list(operating_cfads), discount_rate)


def irr_of_stream(cashflows: list[float]) -> Optional[float]:
    """Newton-Raphson IRR with bisection fallback, matching TS irrOfStream().
    Returns None if no sign change is detected in cashflows."""
    lo, hi = -0.99, 1.0
    f_lo = npv_of_stream(cashflows, lo)
    f_hi = npv_of_stream(cashflows, hi)
    if not math.isfinite(f_lo) or not math.isfinite(f_hi) or f_lo * f_hi > 0:
        return None

    r = 0.10
    for _ in range(100):
        eps = 1e-6
        f = npv_of_stream(cashflows, r)
        fp = (npv_of_stream(cashflows, r + eps) - f) / eps
        nxt = r - f / fp if fp != 0 else r
        if not math.isfinite(nxt) or nxt <= lo or nxt >= hi:
            nxt = (lo + hi) / 2.0
        f_nxt = npv_of_stream(cashflows, nxt)
        if abs(f_nxt) < 1e-4:
            return nxt
        if f_lo * f_nxt < 0:
            hi, f_hi = nxt, f_nxt
        else:
            lo, f_lo = nxt, f_nxt
        r = nxt
    return (lo + hi) / 2.0


def compute_irr(operating_cfads: list[float], capex: float) -> Optional[float]:
    """Project IRR from operations CFADS stream and total capex at t=0."""
    return irr_of_stream([-capex] + list(operating_cfads))


def compute_equity_irr(distributions: list[float], equity_contributed: float) -> Optional[float]:
    """Equity IRR: equity outflow at t=0, distributions thereafter."""
    return irr_of_stream([-equity_contributed] + list(distributions))


def compute_dscr(cfads: float, debt_service: float) -> Optional[float]:
    """Period DSCR. Returns None when debt service is zero (avoiding NaN)."""
    if debt_service <= 0:
        return None
    return cfads / debt_service


def compute_llcr(
    cfads_stream: list[float],
    interest_rate: float,
    outstanding_debt: float,
) -> Optional[float]:
    """LLCR = NPV(CFADS over loan life @ interest_rate) / outstanding debt.
    Matches TS computeLLCR() definition exactly."""
    if outstanding_debt <= 0 or not cfads_stream:
        return None
    npv = sum(cf / math.pow(1.0 + interest_rate, t + 1) for t, cf in enumerate(cfads_stream))
    return npv / outstanding_debt


def compute_rating_band(
    min_dscr: Optional[float],
    llcr: Optional[float] = None,
) -> str:
    """Extended rating bands. The TS version uses three buckets:
       IG (minDSCR >= 1.4), Speculative (>=1.1), Distressed.
    We refine when LLCR is also available:

       A          : minDSCR ≥ 1.50 AND llcr ≥ 1.80
       BBB+       : minDSCR ≥ 1.40 AND llcr ≥ 1.60
       BBB        : minDSCR ≥ 1.30 AND llcr ≥ 1.50
       BBB-       : minDSCR ≥ 1.20 AND llcr ≥ 1.40
       BB         : minDSCR ≥ 1.10
       B / lower  : minDSCR ≥ 1.05
       Distressed : otherwise

    These thresholds reflect standard PF rating-agency ranges; bank
    internal-rating models may use different cutoffs.
    """
    if min_dscr is None or not math.isfinite(min_dscr):
        return "Distressed"

    if llcr is not None and math.isfinite(llcr):
        if min_dscr >= 1.50 and llcr >= 1.80: return "A"
        if min_dscr >= 1.40 and llcr >= 1.60: return "BBB+"
        if min_dscr >= 1.30 and llcr >= 1.50: return "BBB"
        if min_dscr >= 1.20 and llcr >= 1.40: return "BBB-"
        if min_dscr >= 1.10:                   return "BB"
        if min_dscr >= 1.05:                   return "B"
        return "Distressed"
    # Fallback to TS three-bucket scheme when LLCR is absent
    if min_dscr >= 1.40: return "Investment Grade"
    if min_dscr >= 1.10: return "Speculative"
    return "Distressed"


def cost_to_complete_coverage(
    cash_on_hand: float,
    undrawn_debt: float,
    undrawn_equity: float,
    contingent_equity: float,
    cost_remaining: float,
) -> Optional[float]:
    """Pre-COD: (available funds) / (cost remaining). Re-exported here for
    use outside pre_cod.py (e.g. UI quick checks via /ratios endpoint)."""
    if cost_remaining <= 0:
        return None
    return (cash_on_hand + undrawn_debt + undrawn_equity + contingent_equity) / cost_remaining


def taghizadeh_hesary_split(
    bank_debt_eur: float,
    bond_debt_eur: float,
    optimal_bank_pct: float = 56.0,
    optimal_bond_pct: float = 44.0,
) -> dict:
    """Compare a deal's bank/bond split against Taghizadeh-Hesary (2022)
    optimal for renewable infrastructure. Returns commentary, not advice."""
    total = bank_debt_eur + bond_debt_eur
    if total <= 0:
        return {
            "current_bank_pct": 0.0,
            "current_bond_pct": 0.0,
            "optimal_bank_pct": optimal_bank_pct,
            "optimal_bond_pct": optimal_bond_pct,
            "deviation_bps": 0.0,
            "interpretation": "No long-term debt; bank/bond mix not applicable.",
        }
    cb = 100.0 * bank_debt_eur / total
    cbond = 100.0 * bond_debt_eur / total
    dev = abs(cb - optimal_bank_pct) * 100  # in basis points (1% = 100bps)

    if dev < 500:
        interp = (
            f"Near the Taghizadeh-Hesary optimum ({cb:.0f}/{cbond:.0f} vs "
            f"{optimal_bank_pct:.0f}/{optimal_bond_pct:.0f})."
        )
    elif cb > optimal_bank_pct:
        interp = (
            f"Bank-heavy ({cb:.0f}%) vs optimal {optimal_bank_pct:.0f}%. "
            f"Consider a take-out bond at COD to lengthen tenor and reduce "
            f"interest-rate sensitivity."
        )
    else:
        interp = (
            f"Bond-heavy ({cbond:.0f}%) vs optimal {optimal_bond_pct:.0f}%. "
            f"Bank component may be light for construction-phase flexibility; "
            f"consider commercial-bank tranche for ramp-up."
        )

    return {
        "current_bank_pct": cb,
        "current_bond_pct": cbond,
        "optimal_bank_pct": optimal_bank_pct,
        "optimal_bond_pct": optimal_bond_pct,
        "deviation_bps": dev,
        "interpretation": interp,
    }
