---
id: levered_irr
name: Levered (equity) IRR
unit: fraction/yr
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: def compute_returns
---

# Levered (equity) IRR

**Definition.** The IRR of the cash flows to equity.

**Formula.** IRR of: −pre-FID spend, −equity paid in by construction year (IDC included), then EBITDA − tax on (EBITDA − depreciation − interest) − maintenance capex − interest − principal, + residual value.

**Inputs, units and sources.** FCI (EUR, owner's TEA case); pre-FID spend by year (EUR, owner's DEVEX register or spend wave); revenue and OPEX (EUR/yr, TEA case); ramp-up (fraction of full output, owner); COD year and month (owner); construction schedule (EUR by year, reconciles to FCI within 0.5%); tax rate and depreciation life (owner); residual value (EUR, owner); debt amount (EUR), interest rate (fraction/yr), tenor (years) — owner's financing terms

**Timing.** Annual periods, year 0 = FID; part-year COD pro-rated; stated with every result (`timing`).

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** Against the equity hurdle = cost of equity (stated, or built up). `sponsor_equity_hurdle` is a GEX-proposed registry value; no approved value means no pass/fail.

**Limitations.** Annual periods; no monthly dating. A model result, not an assured outcome: valid only on the stated case, inputs and assumptions. Kept separate from project returns.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`def compute_returns`).
