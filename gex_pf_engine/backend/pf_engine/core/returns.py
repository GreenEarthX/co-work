"""
returns.py — investor return metrics
====================================
Unlevered (project) IRR, levered (equity) IRR, NPV, ROI, ROE, payback, and the
hurdle rate they are tested against. Pure functions, annual periods, no I/O.

Vocabulary
  FCI    Fixed Capital Investment: the CAPEX committed at FID.
  DEVEX  Pre-FID development spend. It is paid BEFORE year 0 and by equity
         only (equity absorbs first loss; no debt is drawn before FID).

Two cases, always labelled
  SCREENING_FCI_YEAR_0  FCI falls in full at year 0 and operations start in
                        year 1. Simple, and it assumes no construction period.
  SCHEDULED             CAPEX falls by construction year (year 0 = FID) and
                        operations start the year after the last construction
                        year, with an optional ramp-up. A scheduled result
                        carries the screening case beside it, so the effect of
                        the construction period is visible and not asserted.

Timing, stated in every result under "timing"
  Year 0 is the FID date. Project year n is the 12 months ending n years
  after FID. Year-0 flows fall on the FID date; every later flow falls at the
  end of its project year.
  periods -n … -1   pre-FID spend, oldest first
  periods 0 … C-1   CAPEX by construction year (C = 1 in the screening case)
  COD               cod_months_after_fid; by default the end of the last
                    construction year
  operations        N operating years counted from COD. When COD falls inside
                    a project year, the first operating project year holds
                    only the months after COD and the last holds the rest, so
                    revenue, OPEX, depreciation and debt service are pro-rated
                    and the operating life stays N years.

Project flows carry no financing. Equity flows carry all of it. The two are
never mixed. Every result carries DEFINITIONS and LIMITATIONS. This is a
screening calculation, not a lender model.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Optional, Sequence

RETURNS_MODEL_VERSION = "1.3.0"

# Valuation boundary (handoff v4, task 8). A FROM_FID result is a separately
# identified case: pre-FID spend is excluded as sunk, and every figure says so.
BOUNDARY_FULL = "FULL_PROJECT"
BOUNDARY_FROM_FID = "FROM_FID"
BOUNDARIES = {
    BOUNDARY_FULL: "Full project: pre-FID development spend (DEVEX) is included before year 0.",
    BOUNDARY_FROM_FID: "From FID: pre-FID spend is treated as sunk and excluded. This is NOT a "
                       "full-project return and must never be compared with one.",
}

# LLCR (task 5). It is shown only once validated against independently computed
# expectations (tests/test_returns_expectations.py, Part C test 5). A change to
# this status, or to an expected value there, is a model change: record it in
# docs/MODEL_CHANGE_REGISTER.md.
LLCR_VALIDATION = {
    "status": "VALIDATED",
    "against": "tests/test_returns_expectations.py — three cases computed independently of "
               "the engine (docs/validation/returns_expectations.md)",
    "definition": "NPV at the debt interest rate of CFADS over the remaining loan life, "
                  "divided by the debt outstanding at COD",
}

# Downside sensitivities (task 6). The platform's convention (dscr_sensitivity.py):
# every shock re-derives the whole model; a shock is never added to a base figure.
# Magnitudes are an analysis convention, labelled GEX proposed; they are not policy.
SENSITIVITY_SET = (
    ("CAPEX_PLUS_10", "CAPEX overrun +10% (funded by equity; debt unchanged)", {"capex_factor": 1.10}),
    ("CAPEX_PLUS_20", "CAPEX overrun +20% (funded by equity; debt unchanged)", {"capex_factor": 1.20}),
    ("COD_DELAY_6M", "COD 6 months later", {"cod_delay_months": 6}),
    ("COD_DELAY_12M", "COD 12 months later", {"cod_delay_months": 12}),
    ("REVENUE_MINUS_10", "Revenue -10% every year", {"revenue_factor": 0.90}),
    ("REVENUE_MINUS_20", "Revenue -20% every year", {"revenue_factor": 0.80}),
    ("OPEX_PLUS_10", "OPEX +10% every year", {"opex_factor": 1.10}),
    ("OPEX_PLUS_20", "OPEX +20% every year", {"opex_factor": 1.20}),
    ("RATE_PLUS_100BP", "Interest rate +100 bp", {"rate_add": 0.01}),
    ("RATE_PLUS_200BP", "Interest rate +200 bp", {"rate_add": 0.02}),
)
SENSITIVITY_BASIS = ("Each shock re-runs the whole model with one input changed (never added to the "
                     "base figures). NPVs are taken at the BASE case's hurdle rates so the rows compare. "
                     "Shock sizes: GEX proposed analysis convention, not a policy threshold.")

CASE_SCREENING = "SCREENING_FCI_YEAR_0"
CASE_SCHEDULED = "SCHEDULED"
CASE_LABELS = {
    CASE_SCREENING: "Simplified screening case: FCI in full at year 0, full output from year 1. "
                    "Assumes no construction period.",
    CASE_SCHEDULED: "Scheduled case: CAPEX by construction year from FID, operations from the "
                    "stated COD, with a part first year where COD falls inside a year.",
}
RECONCILE_TOLERANCE = 0.005     # scheduled CAPEX must match FCI within 0.5%
MAX_CONSTRUCTION_YEARS = 10

DEFINITIONS = {
    "fci": "Fixed Capital Investment: CAPEX committed at FID. In the screening case it "
           "falls in full at year 0; in the scheduled case it falls by construction year.",
    "devex": "Pre-FID development spend, paid before year 0 by equity. It is never part "
             "of the construction schedule.",
    "total_investment": "FCI + all pre-FID spend, undiscounted.",
    "screening_case": CASE_LABELS[CASE_SCREENING],
    "scheduled_case": CASE_LABELS[CASE_SCHEDULED],
    "unlevered_irr": "Project IRR. Flows: -pre-FID spend, -CAPEX by year, then "
                     "EBITDA - tax on (EBITDA - depreciation) - maintenance capex. "
                     "No financing flows and no interest tax shield.",
    "levered_irr": "Equity IRR. Flows: -pre-FID spend, -equity paid in by construction "
                   "year (including interest during construction), then EBITDA - tax on "
                   "(EBITDA - depreciation - interest) - maintenance capex - interest - principal.",
    "npv_unlevered": "Project flows discounted at the project hurdle rate, valued at year 0 (FID).",
    "npv_levered": "Equity flows discounted at the equity hurdle rate, valued at year 0 (FID).",
    "payback_years": "Years from FID until cumulative project cash flow, pre-FID spend "
                     "included, turns positive. Undiscounted, residual value excluded.",
    "equity_payback_years": "The same measure on equity cash flow.",
    "idc": "Interest during construction: the interest rate on the debt balance at the "
           "start of each construction year. Paid by equity. Zero in the screening case.",
    "ramp_up": "Output in the first operating years as a share of full output. Revenue "
               "scales with it; OPEX scales by its variable share only.",
    "roi_avg_annual": "Average annual net operating profit after tax / total investment.",
    "roi_cumulative": "(Sum of unlevered free cash flow + residual value - total "
                      "investment) / total investment.",
    "roe_avg_annual": "Average annual net income (after depreciation, interest and "
                      "tax) / equity invested.",
    "cost_of_equity": "Stated, or built up as risk-free + beta x equity risk premium "
                      "+ country premium + technology premium.",
    "wacc_after_tax": "E/(E+D) x cost of equity + D/(E+D) x cost of debt x (1 - tax), on "
                      "the planned structure at FID. Grants carry no cost and are outside "
                      "the weights. The same rate applies to both cases.",
    "project_hurdle": "After-tax WACC + project risk premium. Test for unlevered IRR.",
    "equity_hurdle": "Cost of equity. Test for levered IRR.",
    "valuation_boundary": "FULL_PROJECT includes pre-FID spend before year 0; FROM_FID excludes it "
                          "as sunk. They are different cases and are never compared.",
    "cfads": "Cash flow available for debt service, per operating year from COD: EBITDA - tax "
             "(after interest) - maintenance capex.",
    "dscr": "CFADS / (interest + principal) in each operating year with debt service. "
            "min and average are over those years. Deterministic: no P50/P90 here.",
    "llcr": "NPV at the debt interest rate of CFADS over the loan life (years 1..tenor from COD) "
            "/ debt outstanding at COD.",
}

LIMITATIONS = [
    "Annual periods; flows are dated at year ends. A COD inside a year is handled by "
    "pro-rating the first and last operating years, not by dating cash to the month.",
    "With a COD inside a year, CAPEX scheduled for that year is dated at its end, after "
    "COD, while debt service starts at COD on the full debt.",
    "The screening case assumes no construction period, so it brings operating cash "
    "forward. Where a construction schedule exists, read the scheduled case.",
    "In the scheduled case grants are used first, then equity, then debt. Interest "
    "during construction is charged on the opening debt balance, paid by equity, and "
    "is neither capitalised nor depreciated.",
    "Revenue in the first operating year is the stated year-1 figure whatever its "
    "calendar year. Prices are not re-indexed for the construction period.",
    "Debt is a level annual annuity from the first operating year. No sculpting, "
    "grace period, DSRA funding or fees.",
    "Straight-line depreciation on FCI plus pre-FID spend, from the first operating "
    "year. Tax is never negative and losses are not carried forward.",
    "Grants reduce the equity cheque. Their tax treatment is ignored and project "
    "flows are gross of grants.",
    "No working capital, inflation indexation or decommissioning cost.",
    "DSCR and LLCR are computed per operating year counted from COD, on the same annual "
    "annuity; they are not dated to project years when COD falls inside a year.",
    "A verified base case means its assumptions and evidence were reviewed. It does not mean "
    "the forecast outcome is assured.",
]

_SUMMARY_KEYS = ("case", "case_label", "first_operating_period", "unlevered_irr", "levered_irr",
                 "npv_unlevered_eur", "npv_levered_eur", "payback_years", "equity_payback_years",
                 "equity_invested_eur", "idc_eur", "flows")


def npv(rate: float, flows: Sequence[float], first_period: int = 0) -> float:
    """Value at period 0 of flows[i] falling in period first_period + i."""
    return sum(cf / (1.0 + rate) ** (first_period + i) for i, cf in enumerate(flows))


def irr(flows: Sequence[float], first_period: int = 0,
        lo: float = -0.99, hi: float = 10.0) -> Optional[float]:
    """The rate at which npv() is zero, by bisection.

    None when the flows never change sign, or when no root lies in (lo, hi).
    A stream with more than one sign change can have several roots; this
    returns one of them, so check the flows before relying on it.
    """
    if not flows or min(flows) >= 0 or max(flows) <= 0:
        return None
    f_lo, f_hi = npv(lo, flows, first_period), npv(hi, flows, first_period)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)) or f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid, flows, first_period)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2.0


def payback_years(flows: Sequence[float], first_period: int = 0) -> Optional[float]:
    """Years from year 0 until the cumulative flow turns positive; None if it never does."""
    cumulative = 0.0
    for i, cf in enumerate(flows):
        before = cumulative
        cumulative += cf
        period = first_period + i
        if period >= 1 and cf > 0 and before < 0 <= cumulative + 1e-9:
            return (period - 1) + (-before) / cf
    return None


def annuity_schedule(principal: float, rate: float, years: int) -> list[tuple[float, float]]:
    """(interest, principal repaid) per year for a level annual payment."""
    if principal <= 0 or years <= 0:
        return []
    payment = principal / years if rate == 0 else principal * rate / (1.0 - (1.0 + rate) ** -years)
    rows, balance = [], principal
    for _ in range(years):
        interest = balance * rate
        repaid = payment - interest
        balance -= repaid
        rows.append((interest, repaid))
    return rows


def hurdle_rate(*, equity_eur: float, debt_eur: float, cost_of_debt: float, tax_rate: float,
                cost_of_equity: Optional[float] = None,
                risk_free_rate: Optional[float] = None,
                equity_beta: Optional[float] = None,
                equity_risk_premium: Optional[float] = None,
                country_risk_premium: float = 0.0,
                technology_risk_premium: float = 0.0,
                project_risk_premium: float = 0.0) -> dict:
    """Cost of equity, after-tax WACC and the two hurdle rates.

    Cost of equity is taken as stated when given. Otherwise it is built up,
    which needs risk_free_rate, equity_beta and equity_risk_premium.
    """
    if cost_of_equity is not None:
        ke, basis = cost_of_equity, "stated"
    elif None not in (risk_free_rate, equity_beta, equity_risk_premium):
        ke = (risk_free_rate + equity_beta * equity_risk_premium
              + country_risk_premium + technology_risk_premium)
        basis = "build-up"
    else:
        raise ValueError("hurdle rate needs cost_of_equity, or risk_free_rate + "
                         "equity_beta + equity_risk_premium")
    priced = equity_eur + debt_eur
    if priced <= 0:
        raise ValueError("hurdle rate needs equity or debt in the capital structure")
    w_e, w_d = equity_eur / priced, debt_eur / priced
    wacc = w_e * ke + w_d * cost_of_debt * (1.0 - tax_rate)
    return {
        "cost_of_equity": ke,
        "cost_of_equity_basis": basis,
        "equity_weight": w_e,
        "debt_weight": w_d,
        "cost_of_debt_after_tax": cost_of_debt * (1.0 - tax_rate),
        "wacc_after_tax": wacc,
        "project_risk_premium": project_risk_premium,
        "project_hurdle": wacc + project_risk_premium,
        "equity_hurdle": ke,
    }


def _test(actual: Optional[float], hurdle: float) -> dict:
    if actual is None:
        return {"hurdle": hurdle, "irr": None, "spread_bps": None, "clears": None}
    return {"hurdle": hurdle, "irr": actual,
            "spread_bps": round((actual - hurdle) * 10_000, 1), "clears": actual >= hurdle}


def compute_returns(*, fci_eur: float, operating_years: int,
                    revenue_y1_eur: float, opex_y1_eur: float,
                    tax_rate: float, depreciation_years: int,
                    revenue_growth: float = 0.0, opex_growth: float = 0.0,
                    maintenance_capex_eur: float = 0.0, residual_value_eur: float = 0.0,
                    pre_fid_spend_eur: Sequence[float] = (),
                    construction_schedule_eur: Sequence[float] = (),
                    cod_months_after_fid: Optional[int] = None,
                    ramp_up: Sequence[float] = (), opex_variable_share: float = 0.0,
                    debt_eur: float = 0.0, interest_rate: float = 0.0,
                    debt_tenor_years: int = 0, grant_eur: float = 0.0,
                    valuation_boundary: str = BOUNDARY_FULL, scenario: str = "BASE",
                    provenance_inputs: Optional[dict] = None,
                    _compare: bool = True, _downside: bool = True,
                    _fixed_hurdle: Optional[dict] = None, **hurdle_inputs) -> dict:
    """Return metrics for one project. See the module docstring for the two cases.

    construction_schedule_eur  CAPEX by year, year 0 (FID) first. It must total
                               the FCI and hold no pre-FID spend. Empty gives
                               the screening case.
    cod_months_after_fid       Months from FID to COD. Default: the end of the
                               last construction year. A value that is not a
                               multiple of 12 gives a part first operating year.
    ramp_up                    Output share in the first operating years, counted
                               from COD, e.g. [0.6, 0.85]. Later years run at
                               full output.
    """
    if fci_eur <= 0:
        raise ValueError("fci_eur must be positive")
    if not 1 <= operating_years <= 60:
        raise ValueError("operating_years must be between 1 and 60")
    if depreciation_years < 1:
        raise ValueError("depreciation_years must be at least 1")
    if not 0 <= tax_rate < 1:
        raise ValueError("tax_rate must be in [0, 1)")
    if any(s < 0 for s in pre_fid_spend_eur) or min(debt_eur, grant_eur, maintenance_capex_eur) < 0:
        raise ValueError("spend, debt, grant and maintenance capex cannot be negative")
    if debt_eur > 0 and not 1 <= debt_tenor_years <= operating_years:
        raise ValueError("debt_tenor_years must be between 1 and operating_years, or the "
                         "equity flows would leave out part of the repayment")
    equity_at_fid = fci_eur - debt_eur - grant_eur
    if equity_at_fid < 0:
        raise ValueError("debt plus grants exceed the FCI")

    if valuation_boundary not in BOUNDARIES:
        raise ValueError(f"valuation_boundary must be one of {sorted(BOUNDARIES)}")
    if not scenario or not str(scenario).strip():
        raise ValueError("scenario must be named (e.g. BASE, DOWNSIDE)")
    stated = dict({
        "fci_eur": fci_eur, "operating_years": operating_years, "revenue_y1_eur": revenue_y1_eur,
        "opex_y1_eur": opex_y1_eur, "tax_rate": tax_rate, "depreciation_years": depreciation_years,
        "revenue_growth": revenue_growth, "opex_growth": opex_growth,
        "maintenance_capex_eur": maintenance_capex_eur, "residual_value_eur": residual_value_eur,
        "pre_fid_spend_eur": [float(x) for x in pre_fid_spend_eur],
        "construction_schedule_eur": [float(x) for x in construction_schedule_eur],
        "cod_months_after_fid": cod_months_after_fid, "ramp_up": [float(x) for x in ramp_up],
        "opex_variable_share": opex_variable_share, "debt_eur": debt_eur,
        "interest_rate": interest_rate, "debt_tenor_years": debt_tenor_years, "grant_eur": grant_eur,
        "valuation_boundary": valuation_boundary, "scenario": scenario, **hurdle_inputs})
    pre_stated = [float(s) for s in pre_fid_spend_eur]
    # FROM_FID: pre-FID spend is sunk and excluded; the result says how much.
    pre = [] if valuation_boundary == BOUNDARY_FROM_FID else pre_stated
    devex = sum(pre)
    devex_excluded = sum(pre_stated) - devex

    # ── Construction schedule, reconciled to the FCI ────────────────────────
    given = [float(c) for c in construction_schedule_eur]
    if given:
        if any(c < 0 for c in given) or len(given) > MAX_CONSTRUCTION_YEARS:
            raise ValueError(f"construction schedule needs 1 to {MAX_CONSTRUCTION_YEARS} "
                             "years of non-negative CAPEX")
        scheduled_total = sum(given)
        if abs(scheduled_total - fci_eur) > RECONCILE_TOLERANCE * fci_eur:
            hint = (" The difference equals the pre-FID spend: DEVEX belongs in "
                    "pre_fid_spend_eur, not in the schedule."
                    if devex > 0 and abs(scheduled_total - fci_eur - devex) <= RECONCILE_TOLERANCE * fci_eur
                    else "")
            raise ValueError(f"construction schedule totals {scheduled_total:,.0f} but the FCI is "
                             f"{fci_eur:,.0f}; they must reconcile within "
                             f"{RECONCILE_TOLERANCE:.1%}.{hint}")
        capex = [c * fci_eur / scheduled_total for c in given]
    else:
        scheduled_total, capex = fci_eur, [fci_eur]
    ramp = [float(x) for x in ramp_up]
    if any(not 0 < x <= 1 for x in ramp) or len(ramp) > operating_years:
        raise ValueError("ramp_up values must be in (0, 1], one per early operating year")
    if not 0 <= opex_variable_share <= 1:
        raise ValueError("opex_variable_share must be in [0, 1]")

    # ── Timing: when operations start ───────────────────────────────────────
    last_capex_year = len(capex) - 1
    if cod_months_after_fid is None:
        cod_months, cod_basis = 12 * last_capex_year, "end of the last construction year (default)"
    else:
        cod_months, cod_basis = int(cod_months_after_fid), "stated"
        if not 0 <= cod_months <= 12 * MAX_CONSTRUCTION_YEARS:
            raise ValueError(f"cod_months_after_fid must be between 0 and {12 * MAX_CONSTRUCTION_YEARS}")
        if last_capex_year > math.ceil(cod_months / 12):
            raise ValueError("the construction schedule has CAPEX in a year after COD; "
                             "move COD later or shorten the schedule")
    cod_years = cod_months / 12.0
    first_op = cod_months // 12 + 1                 # first project year with operations
    stub = 1.0 - (cod_months % 12) / 12.0           # share of an operating year inside it
    case = CASE_SCHEDULED if (len(capex) > 1 or ramp or cod_months > 0) else CASE_SCREENING

    # ── Funding up to COD: grants, then equity, then debt ───────────────────
    # Interest during construction runs on each year's opening debt balance,
    # for the part of that year before COD.
    construction, grant_left, equity_left, debt_balance = [], grant_eur, equity_at_fid, 0.0
    for year in range(max(last_capex_year, math.ceil(cod_years)) + 1):
        spend = capex[year] if year < len(capex) else 0.0
        before_cod = min(1.0, max(0.0, cod_years - (year - 1))) if year >= 1 else 0.0
        idc = debt_balance * interest_rate * before_cod
        from_grant = min(grant_left, spend)
        from_equity = min(equity_left, spend - from_grant)
        from_debt = spend - from_grant - from_equity
        grant_left -= from_grant
        equity_left -= from_equity
        debt_balance += from_debt
        construction.append({"period": year, "capex": spend, "grant": from_grant,
                             "equity": from_equity, "debt_draw": from_debt, "idc": idc})
    idc_total = sum(row["idc"] for row in construction)

    total_investment = fci_eur + devex
    equity_committed = equity_at_fid + devex            # planned structure; sets the hurdle
    equity_invested = equity_committed + idc_total      # cash equity actually pays in
    depreciation = total_investment / depreciation_years
    debt_rows = annuity_schedule(debt_eur, interest_rate, debt_tenor_years)

    # ── Operating years, counted from COD ───────────────────────────────────
    operating = []
    for t in range(1, operating_years + 1):
        output = ramp[t - 1] if t <= len(ramp) else 1.0
        interest, repaid = debt_rows[t - 1] if t <= len(debt_rows) else (0.0, 0.0)
        operating.append({
            "output": output,
            "revenue": revenue_y1_eur * (1.0 + revenue_growth) ** (t - 1) * output,
            "opex": (opex_y1_eur * (1.0 + opex_growth) ** (t - 1)
                     * (1.0 - opex_variable_share * (1.0 - output))),
            "depreciation": depreciation if t <= depreciation_years else 0.0,
            "interest": interest, "principal": repaid, "maintenance": maintenance_capex_eur,
        })

    # ── Project years: whole operating years, or two part years when COD falls
    # inside a project year ─────────────────────────────────────────────────
    schedule, fcf_u, fcf_e, nopat, net_income = [], [], [], [], []
    for j in range(operating_years if stub == 1.0 else operating_years + 1):
        parts = []
        if j < operating_years:
            parts.append((operating[j], stub))
        if stub < 1.0 and j >= 1:
            parts.append((operating[j - 1], 1.0 - stub))
        share = sum(w for _, w in parts)
        amount = {k: sum(year[k] * w for year, w in parts)
                  for k in ("revenue", "opex", "depreciation", "interest", "principal", "maintenance")}
        ebitda = amount["revenue"] - amount["opex"]
        tax_u = max(0.0, (ebitda - amount["depreciation"]) * tax_rate)
        tax_l = max(0.0, (ebitda - amount["depreciation"] - amount["interest"]) * tax_rate)
        fcf_u.append(ebitda - tax_u - amount["maintenance"])
        fcf_e.append(ebitda - tax_l - amount["maintenance"] - amount["interest"] - amount["principal"])
        nopat.append(ebitda - amount["depreciation"] - tax_u)
        net_income.append(ebitda - amount["depreciation"] - amount["interest"] - tax_l)
        schedule.append({
            "year": j + 1, "period": first_op + j, "operating_share": share,
            "output": sum(year["output"] * w for year, w in parts) / share,
            "revenue": amount["revenue"], "opex": amount["opex"], "ebitda": ebitda,
            "depreciation": amount["depreciation"], "interest": amount["interest"],
            "principal": amount["principal"],
            "tax_unlevered": tax_u, "tax_levered": tax_l,
            "fcf_unlevered": fcf_u[-1], "fcf_equity": fcf_e[-1], "net_income": net_income[-1],
        })

    # ── Flows by project year. A year can hold both CAPEX and operations. ───
    first = -len(pre)
    last_construction = construction[-1]["period"]
    periods = range(first, max(last_construction, schedule[-1]["period"]) + 1)
    project_flow = {p: 0.0 for p in periods}
    equity_flow = {p: 0.0 for p in periods}
    for i, spend in enumerate(pre):
        project_flow[first + i] -= spend
        equity_flow[first + i] -= spend
    for row in construction:
        project_flow[row["period"]] -= row["capex"]
        equity_flow[row["period"]] -= row["equity"] + row["idc"]
    for row in schedule:
        project_flow[row["period"]] += row["fcf_unlevered"]
        equity_flow[row["period"]] += row["fcf_equity"]
    unlevered = [project_flow[p] for p in periods]
    levered = [equity_flow[p] for p in periods]
    project_payback = payback_years(unlevered, first)
    equity_payback = payback_years(levered, first) if equity_invested > 0 else None
    unlevered[-1] += residual_value_eur
    levered[-1] += residual_value_eur

    hurdle = _fixed_hurdle or hurdle_rate(equity_eur=equity_committed, debt_eur=debt_eur,
                                          cost_of_debt=interest_rate, tax_rate=tax_rate, **hurdle_inputs)
    debt = debt_metrics(operating, debt_eur=debt_eur, interest_rate=interest_rate, tax_rate=tax_rate)
    unlevered_irr = irr(unlevered, first)
    levered_irr = irr(levered, first) if equity_invested > 0 else None

    def phase(period: int) -> str:
        if period < 0:
            return "PRE_FID"
        if period < first_op:
            return "CONSTRUCTION"
        return "CONSTRUCTION+OPERATIONS" if period <= last_construction else "OPERATIONS"

    timeline = [{"period": p, "phase": phase(p), "project_flow": unlevered[i], "equity_flow": levered[i]}
                for i, p in enumerate(periods)]

    timing = {
        "period_length_months": 12,
        "cod_months_after_fid": cod_months,
        "cod_basis": cod_basis,
        "first_operating_project_year": first_op,
        "first_year_operating_share": stub,
        "last_year_operating_share": 1.0 if stub == 1.0 else 1.0 - stub,
        "operating_life_years": operating_years,
        "assumptions": [
            "Year 0 is the FID date. Project year n is the 12 months ending n years after FID.",
            "CAPEX scheduled in year 0 is paid at FID. CAPEX in a later year is dated at the end of that year.",
            f"COD is {cod_months} months after FID ({cod_basis}).",
            ("Operations fill whole project years." if stub == 1.0 else
             f"COD falls inside project year {first_op}: that year holds {stub:.0%} of an operating "
             f"year and the last project year holds the remaining {1.0 - stub:.0%}. Revenue, OPEX, "
             f"depreciation, debt service and maintenance capex are pro-rated, and the operating "
             f"life stays {operating_years} years."),
            "Operating cash is dated at the end of each project year.",
            "Growth and ramp-up are applied by operating year counted from COD, not by project year.",
            "Debt is drawn after grants and equity, is fully drawn by COD and is repaid from COD. "
            "Interest during construction runs on each year's opening balance up to COD.",
        ],
    }

    result = {
        "model_version": RETURNS_MODEL_VERSION,
        "valuation_boundary": valuation_boundary,
        "valuation_boundary_label": BOUNDARIES[valuation_boundary],
        "scenario": scenario,
        "devex_excluded_eur": devex_excluded,
        "case": case,
        "case_label": CASE_LABELS[case],
        "first_operating_period": first_op,
        "fci_eur": fci_eur,
        "devex_eur": devex,
        "total_investment_eur": total_investment,
        "debt_eur": debt_eur,
        "grant_eur": grant_eur,
        "equity_at_fid_eur": equity_at_fid,
        "idc_eur": idc_total,
        "equity_invested_eur": equity_invested,
        "unlevered_irr": unlevered_irr,
        "levered_irr": levered_irr,
        "npv_unlevered_eur": npv(hurdle["project_hurdle"], unlevered, first),
        "npv_levered_eur": (npv(hurdle["equity_hurdle"], levered, first)
                            if equity_invested > 0 else None),
        "roi_avg_annual": sum(nopat) / operating_years / total_investment,
        "roi_cumulative": (sum(fcf_u) + residual_value_eur - total_investment) / total_investment,
        "roe_avg_annual": (sum(net_income) / operating_years / equity_invested
                           if equity_invested > 0 else None),
        "payback_years": project_payback,
        "equity_payback_years": equity_payback,
        "debt_metrics": debt,
        "hurdle": hurdle,
        "hurdle_test": {
            "unlevered": _test(unlevered_irr, hurdle["project_hurdle"]),
            "levered": _test(levered_irr, hurdle["equity_hurdle"]),
        },
        "reconciliation": {
            "fci_eur": fci_eur,
            "scheduled_capex_eur": scheduled_total,
            "difference_eur": scheduled_total - fci_eur,
            "devex_eur": devex,
            "note": "Scheduled CAPEX is scaled to the FCI. DEVEX is outside the schedule "
                    "and counted once, before year 0.",
        },
        "timing": timing,
        "construction": construction,
        "flows": {"first_period": first, "unlevered": unlevered, "levered": levered},
        "timeline": timeline,
        "schedule": schedule,
        "definitions": DEFINITIONS,
        "limitations": LIMITATIONS,
    }

    # A scheduled result always shows the screening case it replaces, on the
    # same inputs and the same hurdle, so the difference is explained by the
    # flows and not by a changed assumption.
    if case == CASE_SCHEDULED and _compare:
        screening = compute_returns(
            fci_eur=fci_eur, operating_years=operating_years, revenue_y1_eur=revenue_y1_eur,
            opex_y1_eur=opex_y1_eur, tax_rate=tax_rate, depreciation_years=depreciation_years,
            revenue_growth=revenue_growth, opex_growth=opex_growth,
            maintenance_capex_eur=maintenance_capex_eur, residual_value_eur=residual_value_eur,
            pre_fid_spend_eur=pre_stated, debt_eur=debt_eur, interest_rate=interest_rate,
            debt_tenor_years=debt_tenor_years, grant_eur=grant_eur,
            valuation_boundary=valuation_boundary, scenario=scenario,
            _compare=False, _downside=False, **hurdle_inputs)
        result["screening_case"] = {k: screening[k] for k in _SUMMARY_KEYS}
        result["difference"] = {
            "first_operating_period": {"screening": 1, "scheduled": first_op},
            "cod_months_after_fid": cod_months,
            "project_undiscounted_total_eur": {"screening": sum(screening["flows"]["unlevered"]),
                                               "scheduled": sum(unlevered)},
            "equity_undiscounted_total_eur": {"screening": sum(screening["flows"]["levered"]),
                                              "scheduled": sum(levered)},
            "idc_eur": idc_total,
            "ramp_up_applied": bool(ramp),
        }
    if _downside:
        result["downside"] = downside_sensitivities(stated, hurdle, result)
    result["provenance"] = _provenance(stated, result, provenance_inputs, len(capex) > 1)
    return result


def debt_metrics(operating: list, *, debt_eur: float, interest_rate: float, tax_rate: float) -> dict:
    """DSCR per operating year with debt service, and LLCR at COD.

    CFADS_t = EBITDA_t - tax after interest - maintenance capex, per operating
    year counted from COD (the same years the annuity is scheduled on).
    """
    if debt_eur <= 0:
        return {"dscr_by_year": [], "dscr_min": None, "dscr_avg": None, "llcr": None,
                "cfads_by_year": [], "note": "No debt: DSCR and LLCR do not apply.",
                "llcr_validation": LLCR_VALIDATION}
    cfads, dscr = [], []
    for t, year in enumerate(operating, start=1):
        ebitda = year["revenue"] - year["opex"]
        tax = max(0.0, (ebitda - year["depreciation"] - year["interest"]) * tax_rate)
        cf = ebitda - tax - year["maintenance"]
        cfads.append(cf)
        service = year["interest"] + year["principal"]
        if service > 0:
            dscr.append({"operating_year": t, "cfads_eur": cf, "debt_service_eur": service,
                         "dscr": cf / service})
    tenor = len(dscr)
    loan_life = cfads[:tenor]
    llcr = (sum(cf / (1.0 + interest_rate) ** (t + 1) for t, cf in enumerate(loan_life)) / debt_eur
            if tenor else None)
    values = [d["dscr"] for d in dscr]
    return {
        "dscr_by_year": dscr,
        "dscr_min": min(values) if values else None,
        "dscr_avg": sum(values) / len(values) if values else None,
        "llcr": llcr if LLCR_VALIDATION["status"] == "VALIDATED" else None,
        "llcr_status": "COMPUTED" if LLCR_VALIDATION["status"] == "VALIDATED" else "UNAVAILABLE — not yet validated",
        "llcr_validation": LLCR_VALIDATION,
        "cfads_by_year": cfads,
        "basis": "Deterministic case. P50/P90 DSCR need a distribution and are not computed here.",
    }


def _shock(inputs: dict, change: dict) -> dict:
    shocked = dict(inputs)
    if "capex_factor" in change:
        f = change["capex_factor"]
        shocked["fci_eur"] = inputs["fci_eur"] * f
        shocked["construction_schedule_eur"] = [c * f for c in inputs["construction_schedule_eur"]]
    if "cod_delay_months" in change:
        schedule = inputs["construction_schedule_eur"]
        base_cod = (inputs["cod_months_after_fid"] if inputs["cod_months_after_fid"] is not None
                    else 12 * max(0, len(schedule) - 1))
        shocked["cod_months_after_fid"] = base_cod + change["cod_delay_months"]
    if "revenue_factor" in change:
        shocked["revenue_y1_eur"] = inputs["revenue_y1_eur"] * change["revenue_factor"]
    if "opex_factor" in change:
        shocked["opex_y1_eur"] = inputs["opex_y1_eur"] * change["opex_factor"]
    if "rate_add" in change:
        shocked["interest_rate"] = inputs["interest_rate"] + change["rate_add"]
    return shocked


def downside_sensitivities(inputs: dict, base_hurdle: dict, base: dict) -> dict:
    rows = []
    for sid, label, change in SENSITIVITY_SET:
        try:
            r = compute_returns(**_shock(inputs, change), _compare=False, _downside=False,
                                _fixed_hurdle=base_hurdle)
        except ValueError as exc:
            rows.append({"id": sid, "label": label, "error": str(exc)})
            continue

        def delta_bps(key: str) -> Optional[float]:
            a, b = r.get(key), base.get(key)
            return None if a is None or b is None else round((a - b) * 10_000, 1)

        rows.append({
            "id": sid, "label": label, "change": change,
            "unlevered_irr": r["unlevered_irr"], "levered_irr": r["levered_irr"],
            "delta_unlevered_irr_bps": delta_bps("unlevered_irr"),
            "delta_levered_irr_bps": delta_bps("levered_irr"),
            "npv_unlevered_eur": r["npv_unlevered_eur"], "npv_levered_eur": r["npv_levered_eur"],
            "dscr_min": r["debt_metrics"]["dscr_min"], "llcr": r["debt_metrics"]["llcr"],
        })
    return {"basis": SENSITIVITY_BASIS, "shock_set_status": "GEX proposed", "rows": rows}


def _sign_changes(flows: Sequence[float]) -> int:
    signs = [f > 0 for f in flows if abs(f) > 1e-9]
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


def _provenance(inputs: dict, result: dict, supplied: Optional[dict], scheduled: bool) -> dict:
    """What produced these figures: inputs (hashed), sources supplied by the caller,
    the model, timing and boundary, the checks run and their outcomes, limitations."""
    supplied = supplied or {}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
    checks = [
        {"check": "construction schedule reconciles to FCI within 0.5%",
         "outcome": "PASS" if scheduled else "NOT_APPLICABLE",
         "detail": f"difference {result['reconciliation']['difference_eur']:,.0f} EUR"},
        {"check": "DEVEX outside the construction schedule", "outcome": "PASS",
         "detail": "enforced: a schedule that equals FCI + DEVEX is refused"},
    ]
    for key in ("unlevered", "levered"):
        flows = result["flows"][key]
        n = _sign_changes(flows)
        checks.append({"check": f"{key} IRR has a single root", "outcome":
                       "PASS" if n == 1 else ("NOT_APPLICABLE" if n == 0 else "WARN"),
                       "detail": f"{n} sign change(s) in the flows"})
    dm = result["debt_metrics"]
    checks.append({"check": "LLCR validated against independent expectations",
                   "outcome": "PASS" if dm.get("llcr_validation", {}).get("status") == "VALIDATED" else "WARN",
                   "detail": LLCR_VALIDATION["against"]})
    tea = supplied.get("tea_case")
    assumptions = supplied.get("assumptions") or []
    return {
        "calculation": {"engine": "gex_pf_engine", "module": "pf_engine.core.returns",
                        "model_version": RETURNS_MODEL_VERSION,
                        "computed_at": datetime.now(timezone.utc).isoformat()},
        "inputs_sha256": digest,
        "inputs": inputs,
        "tea_case": tea or {"status": "NOT_SUPPLIED",
                            "note": "No TEA case was named: the inputs are the caller's own."},
        "assumptions": assumptions,
        "valuation_boundary": result["valuation_boundary"],
        "scenario": result["scenario"],
        "timing": {k: result["timing"][k] for k in ("cod_months_after_fid", "cod_basis",
                                                     "first_operating_project_year",
                                                     "first_year_operating_share")},
        "validation_checks": checks,
        "limitations": LIMITATIONS,
        "validity": "A verified base case means its assumptions and evidence were reviewed; it "
                    "does not mean the forecast outcome is assured.",
    }
