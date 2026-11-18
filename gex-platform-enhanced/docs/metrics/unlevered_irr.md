---
id: unlevered_irr
name: Unlevered (project) IRR
unit: fraction/yr
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: def compute_returns
---

# Unlevered (project) IRR

**Definition.** The discount rate at which the project's unlevered cash flows have zero NPV.

**Formula.** IRR of: −pre-FID spend (years before 0), −CAPEX by year, then EBITDA − tax on (EBITDA − depreciation) − maintenance capex, + residual value in the last year. No financing flows, no interest tax shield. Bisection on NPV.

**Inputs, units and sources.** FCI (EUR, owner's TEA case); pre-FID spend by year (EUR, owner's DEVEX register or spend wave); revenue and OPEX (EUR/yr, TEA case); ramp-up (fraction of full output, owner); COD year and month (owner); construction schedule (EUR by year, reconciles to FCI within 0.5%); tax rate and depreciation life (owner); residual value (EUR, owner)

**Timing.** Annual periods, year 0 = FID; part-year COD pro-rated; stated with every result (`timing`).

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** Against the project hurdle (after-tax WACC + `project_risk_premium`, registry, GEX proposed). The hurdle is computed; the premium is a policy value. Also the DFI_IRR test (without the DFI's terms) against `dfi_irr_hurdle` of the DFI, as one input only.

**Limitations.** Annual periods; no monthly dating. A model result, not an assured outcome: valid only on the stated case, inputs and assumptions. Not the sole indicator: always shown with NPV and the downside sensitivities. Undefined when the flows change sign more than once (reported).

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`def compute_returns`).
