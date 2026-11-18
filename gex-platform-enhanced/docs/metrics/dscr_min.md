---
id: dscr_min
name: DSCR (minimum and average, deterministic)
unit: x
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: def debt_metrics
---

# DSCR (minimum and average, deterministic)

**Definition.** CFADS over debt service in each operating year with debt service; minimum and average.

**Formula.** DSCR_t = (EBITDA − tax after interest − maintenance capex)_t / (interest + principal)_t; annuity debt from COD.

**Inputs, units and sources.** FCI (EUR, owner's TEA case); pre-FID spend by year (EUR, owner's DEVEX register or spend wave); revenue and OPEX (EUR/yr, TEA case); ramp-up (fraction of full output, owner); COD year and month (owner); construction schedule (EUR by year, reconciles to FCI within 0.5%); tax rate and depreciation life (owner); residual value (EUR, owner); debt amount (EUR), interest rate (fraction/yr), tenor (years) — owner's financing terms

**Timing.** Annual periods, year 0 = FID; part-year COD pro-rated; stated with every result (`timing`).

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** DSCR_P50 / DSCR_DEFAULT tests take recorded P50/P90 figures, not this deterministic value. The registry floors (`dscr_floor_p50`, `dscr_default_floor`, `dscr_covenant_floor`) are GEX proposed.

**Limitations.** Annual periods; no monthly dating. A model result, not an assured outcome: valid only on the stated case, inputs and assumptions. Deterministic: no P50/P90 here. No DSRA, sculpting or sweep in this model.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`def debt_metrics`).
