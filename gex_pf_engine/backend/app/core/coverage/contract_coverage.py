"""
Contract–Debt Coverage — does contracted revenue outlive the senior debt?

Spec: gex-platform-enhanced/docs/contract-debt-coverage-spec.md

No engine in the platform can currently represent contract expiry: OfftakeContract
carries `tenor_years` but no start date, OCR is a timeless scalar, the tenor score uses
max(tenor) so one long thin contract carries a whole portfolio, and
`calculate_lifetime_cfads` applies one flat price for every operating year. This module
supplies the missing time dimension.

THE HEADLINE METRIC TAKES NO PRICE VIEW. Contracted-only CFADS counts revenue solely
from contracts live in that year — no merchant curve, no escalation, no refinancing. So
`min_dscr_contracted < 1.00` while debt is outstanding is a fact about the contract
portfolio, not a forecast. That is the whole point; do not "improve" this module by
adding a merchant price assumption, because that dissolves the finding it exists to make.

Production basis is PRODUCE-TO-CONTRACT: uncontracted capacity is assumed not produced,
so variable opex scales with contracted volume while fixed opex is incurred regardless.
This is the lender's downside convention and it requires no price forecast.

DSCR here is measured against SCHEDULED debt service, deliberately NOT against
DebtSculptor's sculpted service. Sculpting reduces debt service to hit a target DSCR, so
scoring the verdict on it would be circular — it flatters exactly the number being
measured. Measured on the §9.1 fixture: scheduled DSCR 0.078 in the uncovered years, and
the sculptor reports 0.15 for the same year because it floors service at interest-only.
The sculptor's output is returned alongside as context (`sculpted`), never as the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.debt.tranche import FinancingStructure, Tranche

VERDICT_COVERS = "CONTRACT_COVERS_DEBT"
VERDICT_TAIL = "MERCHANT_TAIL"
VERDICT_DEPENDENT = "MERCHANT_DEPENDENT"
VERDICT_INSUFFICIENT = "INSUFFICIENT_DATA"

DEFAULT_THETA = 0.80  # matches the rating engine's existing `ocr / 0.8` full-credit line


@dataclass
class CoverageContract:
    """One offtake contract, placed on a timeline.

    `start_year` is an absolute calendar year because that is how contracts are written.
    None means "starts at COD", which is the common early-stage case.
    """

    volume_tpa: float
    price_floor_eur_t: float
    tenor_years: int
    start_year: Optional[int] = None
    counterparty_rating: str = "NR"
    take_or_pay: bool = False
    contract_id: str = ""


@dataclass
class CoverageInputs:
    contracts: List[CoverageContract]
    nameplate_tpa: float
    financing: Optional[FinancingStructure]
    cod_year: Optional[int]
    opex_fixed_eur: float = 0.0
    opex_var_eur_per_t: float = 0.0
    subsidies_by_year: Dict[int, float] = field(default_factory=dict)  # key = operating year
    ramp: List[float] = field(default_factory=list)  # ramp[t-1]; absent → 1.0
    theta: float = DEFAULT_THETA
    min_turndown_fraction: Optional[float] = None


# ── primitives ────────────────────────────────────────────────────────────────


def outstanding_principal(tranche: Tranche, year: int) -> float:
    """Principal outstanding at the START of operating `year` (1-indexed).

    Tranche exposes annual_debt_service but no balance, so this derives it from the same
    convention: interest-only through grace, standard annuity thereafter.
    """
    amt = tranche.amount_in_base
    if year <= 1:
        return amt
    if year > tranche.tenor:
        return 0.0

    completed = year - 1
    if completed <= tranche.grace_period_years:
        return amt

    n = tranche.tenor - tranche.grace_period_years
    k = completed - tranche.grace_period_years
    if n <= 0:
        return amt
    if tranche.rate == 0:
        return max(amt * (1 - k / n), 0.0)

    r = tranche.rate
    return max(amt * (((1 + r) ** n - (1 + r) ** k) / ((1 + r) ** n - 1)), 0.0)


def _ramp_factor(inputs: CoverageInputs, t: int) -> float:
    if 1 <= t <= len(inputs.ramp):
        return inputs.ramp[t - 1]
    return 1.0


def available_production(inputs: CoverageInputs, t: int) -> float:
    return inputs.nameplate_tpa * _ramp_factor(inputs, t)


def _is_live(contract: CoverageContract, calendar_year: int, cod_year: int) -> bool:
    start = contract.start_year if contract.start_year is not None else cod_year
    return start <= calendar_year < start + contract.tenor_years


def contracted_volume(inputs: CoverageInputs, t: int) -> float:
    """Σ volume of contracts live in operating year t."""
    if inputs.cod_year is None:
        return 0.0
    calendar_year = inputs.cod_year + t - 1
    return sum(
        c.volume_tpa
        for c in inputs.contracts
        if _is_live(c, calendar_year, inputs.cod_year)
    )


def contracted_revenue(inputs: CoverageInputs, t: int) -> float:
    """Revenue from live contracts only, pro-rata capped when oversold."""
    if inputs.cod_year is None:
        return 0.0
    calendar_year = inputs.cod_year + t - 1
    live = [c for c in inputs.contracts if _is_live(c, calendar_year, inputs.cod_year)]
    volume = sum(c.volume_tpa for c in live)
    if volume <= 0:
        return 0.0

    sold = min(volume, available_production(inputs, t))
    cap_factor = sold / volume
    return sum(c.volume_tpa * c.price_floor_eur_t for c in live) * cap_factor


def contracted_cfads(inputs: CoverageInputs, t: int) -> float:
    """Contracted-only CFADS. Produce-to-contract: variable opex scales with sold volume."""
    sold = min(contracted_volume(inputs, t), available_production(inputs, t))
    opex = inputs.opex_fixed_eur + inputs.opex_var_eur_per_t * sold
    return contracted_revenue(inputs, t) + inputs.subsidies_by_year.get(t, 0.0) - opex


def coverage_ratio(inputs: CoverageInputs, t: int) -> float:
    production = available_production(inputs, t)
    if production <= 0:
        return 0.0
    return min(contracted_volume(inputs, t), production) / production


def scheduled_debt_service(financing: FinancingStructure, t: int) -> float:
    return sum(tr.annual_debt_service(t) for tr in financing.tranches)


# ── the computation ───────────────────────────────────────────────────────────


def compute_coverage(inputs: CoverageInputs) -> Dict:
    financing = inputs.financing
    if financing is None or not financing.tranches:
        return _insufficient("no financing structure — debt tenor unknown")
    if inputs.cod_year is None:
        return _insufficient("COD year unknown")
    if inputs.nameplate_tpa <= 0:
        return _insufficient("nameplate capacity unknown")

    debt_maturity_year = max(tr.tenor for tr in financing.tranches)

    # Evaluate past debt maturity so a cliff always exists and a negative gap
    # (contracts outliving the debt) is expressible.
    last_contract_end = 0
    for c in inputs.contracts:
        start = c.start_year if c.start_year is not None else inputs.cod_year
        start_op = start - inputs.cod_year + 1
        last_contract_end = max(last_contract_end, start_op + c.tenor_years - 1)
    horizon = max(debt_maturity_year, last_contract_end) + 1

    curve = []
    for t in range(1, horizon + 1):
        ds = scheduled_debt_service(financing, t)
        cfads = contracted_cfads(inputs, t)
        ocr = coverage_ratio(inputs, t)
        curve.append(
            {
                "year": t,
                "calendar_year": inputs.cod_year + t - 1,
                "contracted_volume_tpa": round(contracted_volume(inputs, t), 2),
                "available_production_tpa": round(available_production(inputs, t), 2),
                "ocr": round(ocr, 4),
                "contracted_cfads_eur": round(cfads, 2),
                "scheduled_debt_service_eur": round(ds, 2),
                "dscr_contracted": round(cfads / ds, 4) if ds > 0 else None,
                "debt_outstanding": ds > 0,
            }
        )

    cliff = next((row["year"] for row in curve if row["ocr"] < inputs.theta), None)

    naive_gap = debt_maturity_year - last_contract_end if inputs.contracts else None

    serviced = [r for r in curve if r["year"] <= debt_maturity_year and r["scheduled_debt_service_eur"] > 0]
    dscrs = [r["dscr_contracted"] for r in serviced if r["dscr_contracted"] is not None]
    min_dscr = min(dscrs) if dscrs else None
    min_dscr_year = (
        next(r["year"] for r in serviced if r["dscr_contracted"] == min_dscr)
        if min_dscr is not None
        else None
    )

    uncovered_years = [r["year"] for r in serviced if r["ocr"] < inputs.theta]

    if cliff is not None and cliff <= debt_maturity_year:
        exposed = sum(outstanding_principal(tr, cliff) for tr in financing.tranches)
    else:
        exposed = 0.0
    original_debt = sum(tr.amount_in_base for tr in financing.tranches)

    if not uncovered_years:
        verdict = VERDICT_COVERS
    elif min_dscr is not None and min_dscr >= 1.0:
        verdict = VERDICT_TAIL
    else:
        verdict = VERDICT_DEPENDENT

    below_turndown = (
        [r["year"] for r in curve if r["ocr"] < inputs.min_turndown_fraction]
        if inputs.min_turndown_fraction is not None
        else []
    )

    return {
        "verdict": verdict,
        "reason": None,
        "coverage_curve": curve,
        "debt_maturity_year": debt_maturity_year,
        "coverage_cliff_year": cliff,
        "tenor_gap_years": (debt_maturity_year - cliff) if cliff is not None else None,
        "naive_tenor_gap_years": naive_gap,
        "merchant_exposed_debt_eur": round(exposed, 2),
        "merchant_exposed_debt_pct": (
            round(exposed / original_debt, 4) if original_debt > 0 else None
        ),
        "uncovered_debt_years": len(uncovered_years),
        "min_dscr_contracted": min_dscr,
        "min_dscr_contracted_year": min_dscr_year,
        "below_min_turndown_years": below_turndown,
        "inputs_echo": {
            "theta": inputs.theta,
            "cod_year": inputs.cod_year,
            "nameplate_tpa": inputs.nameplate_tpa,
            "opex_fixed_eur": inputs.opex_fixed_eur,
            "opex_var_eur_per_t": inputs.opex_var_eur_per_t,
            "production_basis": "PRODUCE_TO_CONTRACT",
            "dscr_basis": "SCHEDULED_DEBT_SERVICE",
            "contract_count": len(inputs.contracts),
        },
    }


def _insufficient(reason: str) -> Dict:
    """Every quantitative field is None. A fabricated 0 here reads as 'fully covered'."""
    return {
        "verdict": VERDICT_INSUFFICIENT,
        "reason": reason,
        "coverage_curve": [],
        "debt_maturity_year": None,
        "coverage_cliff_year": None,
        "tenor_gap_years": None,
        "naive_tenor_gap_years": None,
        "merchant_exposed_debt_eur": None,
        "merchant_exposed_debt_pct": None,
        "uncovered_debt_years": None,
        "min_dscr_contracted": None,
        "min_dscr_contracted_year": None,
        "below_min_turndown_years": [],
        "inputs_echo": {},
    }
