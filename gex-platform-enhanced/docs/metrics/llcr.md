---
id: llcr
name: LLCR (loan-life coverage ratio)
unit: x
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: def debt_metrics
---

# LLCR (loan-life coverage ratio)

**Definition.** NPV of CFADS over the loan life, at the debt interest rate, over debt outstanding at COD.

**Formula.** LLCR = Σ_{t=1..tenor} CFADS_t / (1 + i)^t / debt at COD.

**Inputs, units and sources.** FCI (EUR, owner's TEA case); pre-FID spend by year (EUR, owner's DEVEX register or spend wave); revenue and OPEX (EUR/yr, TEA case); ramp-up (fraction of full output, owner); COD year and month (owner); construction schedule (EUR by year, reconciles to FCI within 0.5%); tax rate and depreciation life (owner); residual value (EUR, owner); debt amount (EUR), interest rate (fraction/yr), tenor (years) — owner's financing terms

**Timing.** Annual periods, year 0 = FID; part-year COD pro-rated; stated with every result (`timing`).

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** `llcr_floor` is a GEX-proposed registry value; no decision test is wired to it yet.

**Limitations.** Annual periods; no monthly dating. A model result, not an assured outcome: valid only on the stated case, inputs and assumptions. Validated against independent expectations (tests/test_returns_expectations.py). Unavailable in structuring, which shows no LLCR estimate.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`def debt_metrics`).
