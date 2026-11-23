# Returns and debt metrics — independent expectations (Part C test 5)

**Rule.** The engine's returns and debt metrics must equal values computed independently
of the engine, within the tolerances below. The calculator is
`tests/validation/independent_returns.py`. It never imports `pf_engine`. It writes
`tests/validation/returns_expectations.json`, and `tests/test_returns_expectations.py`
compares the engine against that file.

## Method (written once, implemented separately)

1. **Periods.** Year 0 is FID. Pre-FID spend falls in periods -n … -1, oldest first.
   CAPEX falls by construction year from year 0. The cases use whole-year COD only.
2. **Funding up to COD.** Grants first, then equity, then debt. Interest during
   construction (IDC) is each construction year's opening debt balance × the rate, for
   years 1 … COD year. Equity pays the IDC.
3. **Operations.** N operating years from COD. Revenue and OPEX grow from year 1.
   Depreciation is (FCI + pre-FID spend) / depreciation years, straight line. Debt is a
   level annual annuity from the first operating year.
4. **Flows.**
   - Project: −pre-FID, −CAPEX, then EBITDA − max(0, (EBITDA − D) × tax) − maintenance.
   - Equity: −pre-FID, −equity draws − IDC, then EBITDA − max(0, (EBITDA − D − interest)
     × tax) − maintenance − interest − principal.
   - Residual value is added to the last period, after payback is taken.
5. **Hurdles.** WACC = E/(E+D) × Ke + D/(E+D) × Kd × (1 − tax), with E = equity at FID +
   pre-FID spend and D = debt. Project hurdle = WACC + project premium. Equity hurdle = Ke.
6. **IRR** by Newton's method on NPV(r) = 0 (central-difference derivative). The engine
   uses bisection, so agreement checks the flows, not a shared algorithm.
7. **NPV** at the hurdle, valued at year 0.
8. **Payback.** The first period ≥ 1 in which cumulative flow turns positive,
   interpolated within that period.
9. **ROI.** Average NOPAT / total investment, and (Σ project FCF + residual − total) /
   total.
10. **ROE.** Average net income / (equity committed + IDC).
11. **DSCR.** CFADS / debt service per operating year with debt service. CFADS = EBITDA −
    tax after interest − maintenance. Min and average are over those years.
12. **LLCR.** Σ CFADS_t / (1 + Kd)^t over the loan years, divided by the debt at COD.

## Cases

| Case | Source |
|---|---|
| REFERENCE_BREIZH_SAF | Breizh SAF workbook v1.4 (reference case only). The construction split, operating life, depreciation life and project premium are ASSUMED and marked in the JSON. |
| WEAK_INVENTED | Invented. Returns are below the cost of capital and DSCR is below 1. |
| OPERATING_INVENTED | Invented. No construction period, with maintenance capex and a residual value. |

## Tolerances

| Measure | Tolerance |
|---|---|
| IRR | ±1e-5 (0.1 bp) |
| NPV and IDC | relative 1e-6 |
| Ratios (DSCR, LLCR, ROI, ROE, WACC) | ±1e-6 |
| Payback | ±1e-4 years |
