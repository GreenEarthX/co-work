---
id: npv
name: NPV (project and equity)
unit: EUR at year 0
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: npv_unlevered
---

# NPV (project and equity)

**Definition.** Net present value at FID of the project flows (at the project hurdle) and of the equity flows (at the equity hurdle).

**Formula.** Σ CF_t / (1 + r)^t, t = 0 at FID; pre-FID flows compounded forward to year 0.

**Inputs, units and sources.** FCI (EUR, owner's TEA case); pre-FID spend by year (EUR, owner's DEVEX register or spend wave); revenue and OPEX (EUR/yr, TEA case); ramp-up (fraction of full output, owner); COD year and month (owner); construction schedule (EUR by year, reconciles to FCI within 0.5%); tax rate and depreciation life (owner); residual value (EUR, owner); hurdle rates (computed from the WACC inputs)

**Timing.** Annual periods, year 0 = FID; part-year COD pro-rated; stated with every result (`timing`).

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** None. The sign is shown; GEX sets no NPV threshold.

**Limitations.** Annual periods; no monthly dating. A model result, not an assured outcome: valid only on the stated case, inputs and assumptions.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`npv_unlevered`).
