"""Independent computation of the expected returns and debt metrics (Part C test 5).

This file must never import pf_engine. It implements the conventions written in
docs/validation/returns_expectations.md from scratch, year by year, with a
different root finder (Newton with a numerical derivative, not bisection), and
writes the expected values to returns_expectations.json. The engine test compares
the engine against that JSON. Re-running this script and getting different values
is a model change: record it in docs/MODEL_CHANGE_REGISTER.md.

    python tests/validation/independent_returns.py --write
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent

CASES = {
    "REFERENCE_BREIZH_SAF": {
        "source": "Breizh SAF Project Workbook v1.4 (pre-COD), sheets Project Data, Financial Model, "
                  "Capital Stack. Reference case only. Values not in the workbook are marked ASSUMED.",
        "inputs": {
            "fci_eur": 285_000_000.0,
            "pre_fid_spend_eur": [18_500_000.0],          # owner's costs, one year before FID
            "construction_schedule_eur": [142_500_000.0, 142_500_000.0],  # ASSUMED even split
            "cod_months_after_fid": 24,                   # construction period 24 months
            "operating_years": 25,                        # ASSUMED
            "revenue_y1_eur": 52_000_000.0, "revenue_growth": 0.02,
            "opex_y1_eur": 20_800_000.0, "opex_growth": 0.0,   # fixed 8.2M + variable 12.6M
            "opex_variable_share": 12.6 / 20.8,
            "tax_rate": 0.25, "depreciation_years": 20,   # depreciation life ASSUMED
            "debt_eur": 195_000_000.0, "interest_rate": 0.055, "debt_tenor_years": 15,
            "grant_eur": 20_000_000.0,                    # EU Innovation Fund 12M + ADEME 8M
            "maintenance_capex_eur": 0.0, "residual_value_eur": 0.0,
            "cost_of_equity": 0.12, "project_risk_premium": 0.02,   # premium ASSUMED
        },
    },
    "WEAK_INVENTED": {
        "source": "Invented: a project that does not cover its costs of capital.",
        "inputs": {
            "fci_eur": 100_000_000.0, "pre_fid_spend_eur": [2_000_000.0, 3_000_000.0],
            "construction_schedule_eur": [], "cod_months_after_fid": None,
            "operating_years": 20, "revenue_y1_eur": 9_000_000.0, "revenue_growth": 0.0,
            "opex_y1_eur": 4_000_000.0, "opex_growth": 0.0, "opex_variable_share": 0.0,
            "tax_rate": 0.25, "depreciation_years": 20,
            "debt_eur": 60_000_000.0, "interest_rate": 0.07, "debt_tenor_years": 15,
            "grant_eur": 0.0, "maintenance_capex_eur": 0.0, "residual_value_eur": 0.0,
            "cost_of_equity": 0.14, "project_risk_premium": 0.03,
        },
    },
    "OPERATING_INVENTED": {
        "source": "Invented: an operating plant valued with no construction period, with "
                  "maintenance capex and a residual value.",
        "inputs": {
            "fci_eur": 50_000_000.0, "pre_fid_spend_eur": [],
            "construction_schedule_eur": [], "cod_months_after_fid": None,
            "operating_years": 20, "revenue_y1_eur": 14_000_000.0, "revenue_growth": 0.015,
            "opex_y1_eur": 5_000_000.0, "opex_growth": 0.02, "opex_variable_share": 0.0,
            "tax_rate": 0.30, "depreciation_years": 15,
            "debt_eur": 30_000_000.0, "interest_rate": 0.05, "debt_tenor_years": 10,
            "grant_eur": 0.0, "maintenance_capex_eur": 500_000.0, "residual_value_eur": 5_000_000.0,
            "cost_of_equity": 0.10, "project_risk_premium": 0.01,
        },
    },
}

TOLERANCES = {"irr": 1e-5, "npv_relative": 1e-6, "ratio": 1e-6, "payback": 1e-4}


def present_value(rate, flows_by_period):
    return sum(cf / (1 + rate) ** p for p, cf in flows_by_period.items())


def newton_irr(flows_by_period, guess=0.08):
    """Newton's method on NPV(r) = 0 with a central-difference derivative."""
    r = guess
    for _ in range(200):
        f = present_value(r, flows_by_period)
        h = 1e-7
        d = (present_value(r + h, flows_by_period) - present_value(r - h, flows_by_period)) / (2 * h)
        if d == 0:
            break
        step = f / d
        r -= step
        if r <= -0.99:
            r = -0.98
        if abs(step) < 1e-13:
            return r
    return r


def compute(i):
    fci, life = i["fci_eur"], i["operating_years"]
    pre = list(i["pre_fid_spend_eur"])
    devex = sum(pre)
    capex = list(i["construction_schedule_eur"]) or [fci]
    total = sum(capex)
    capex = [c * fci / total for c in capex]
    cod = i["cod_months_after_fid"] if i["cod_months_after_fid"] is not None else 12 * (len(capex) - 1)
    assert cod % 12 == 0, "the validation cases use whole-year COD only"
    first_op = cod // 12 + 1
    debt, rate, tenor = i["debt_eur"], i["interest_rate"], i["debt_tenor_years"]
    grant = i["grant_eur"]
    equity_at_fid = fci - debt - grant

    # funding by construction year: grants, then equity, then debt; IDC on the opening balance
    project, equity = {}, {}
    for k, s in enumerate(pre):
        p = -len(pre) + k
        project[p] = project.get(p, 0.0) - s
        equity[p] = equity.get(p, 0.0) - s
    g_left, e_left, balance, idc_total = grant, equity_at_fid, 0.0, 0.0
    for year in range(0, max(len(capex) - 1, cod // 12) + 1):
        spend = capex[year] if year < len(capex) else 0.0
        idc = balance * rate if (year >= 1 and year * 12 <= cod) else 0.0
        from_g = min(g_left, spend)
        from_e = min(e_left, spend - from_g)
        from_d = spend - from_g - from_e
        g_left, e_left, balance = g_left - from_g, e_left - from_e, balance + from_d
        idc_total += idc
        project[year] = project.get(year, 0.0) - spend
        equity[year] = equity.get(year, 0.0) - from_e - idc

    total_investment = fci + devex
    equity_committed = equity_at_fid + devex
    equity_invested = equity_committed + idc_total
    dep = total_investment / i["depreciation_years"]

    # level annuity
    pay = debt * rate / (1 - (1 + rate) ** -tenor) if debt > 0 else 0.0
    bal = debt
    nopat_sum = fcf_sum = ni_sum = 0.0
    cfads, dscr = [], []
    for t in range(1, life + 1):
        rev = i["revenue_y1_eur"] * (1 + i["revenue_growth"]) ** (t - 1)
        opx = i["opex_y1_eur"] * (1 + i["opex_growth"]) ** (t - 1)
        ebitda = rev - opx
        d = dep if t <= i["depreciation_years"] else 0.0
        if debt > 0 and t <= tenor:
            interest = bal * rate
            principal = pay - interest
            bal -= principal
        else:
            interest = principal = 0.0
        tax_u = max(0.0, (ebitda - d) * i["tax_rate"])
        tax_l = max(0.0, (ebitda - d - interest) * i["tax_rate"])
        m = i["maintenance_capex_eur"]
        fcf_u = ebitda - tax_u - m
        fcf_e = ebitda - tax_l - m - interest - principal
        p = first_op + t - 1
        project[p] = project.get(p, 0.0) + fcf_u
        equity[p] = equity.get(p, 0.0) + fcf_e
        nopat_sum += ebitda - d - tax_u
        fcf_sum += fcf_u
        ni_sum += ebitda - d - interest - tax_l
        cf = ebitda - tax_l - m
        cfads.append(cf)
        if interest + principal > 0:
            dscr.append(cf / (interest + principal))

    def payback(flows):
        cum = 0.0
        for p in sorted(flows):
            before, cum = cum, cum + flows[p]
            if p >= 1 and flows[p] > 0 and before < 0 <= cum + 1e-9:
                return (p - 1) + (-before) / flows[p]
        return None

    pb_project, pb_equity = payback(project), payback(equity)
    last = max(project)
    project[last] += i["residual_value_eur"]
    equity[last] += i["residual_value_eur"]

    ke = i["cost_of_equity"]
    w_e = equity_committed / (equity_committed + debt)
    wacc = w_e * ke + (1 - w_e) * rate * (1 - i["tax_rate"])
    project_hurdle = wacc + i["project_risk_premium"]

    llcr = (sum(cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cfads[:len(dscr)])) / debt
            if debt > 0 else None)
    return {
        "unlevered_irr": newton_irr(project),
        "levered_irr": newton_irr(equity, 0.10),
        "npv_unlevered_eur": present_value(project_hurdle, project),
        "npv_levered_eur": present_value(ke, equity),
        "payback_years": pb_project,
        "equity_payback_years": pb_equity,
        "roi_avg_annual": nopat_sum / life / total_investment,
        "roi_cumulative": (fcf_sum + i["residual_value_eur"] - total_investment) / total_investment,
        "roe_avg_annual": ni_sum / life / equity_invested,
        "dscr_min": min(dscr) if dscr else None,
        "dscr_avg": sum(dscr) / len(dscr) if dscr else None,
        "llcr": llcr,
        "wacc_after_tax": wacc,
        "project_hurdle": project_hurdle,
        "idc_eur": idc_total,
    }


def main():
    out = {"method": "docs/validation/returns_expectations.md", "tolerances": TOLERANCES, "cases": {}}
    for name, case in CASES.items():
        out["cases"][name] = {"source": case["source"], "inputs": case["inputs"],
                              "expected": compute(case["inputs"])}
    text = json.dumps(out, indent=2)
    if "--write" in sys.argv:
        (HERE / "returns_expectations.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
