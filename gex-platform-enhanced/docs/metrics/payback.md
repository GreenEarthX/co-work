---
id: payback
name: Payback (project and equity)
unit: years from FID
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: payback_years
---

# Payback (project and equity)

**Definition.** Years from FID until cumulative cash flow, pre-FID spend included, turns positive.

**Formula.** First t at which Σ_{s≤t} CF_s ≥ 0, interpolated within the year. Undiscounted, residual value excluded.

**Inputs, units and sources.** FCI (EUR, owner's TEA case); pre-FID spend by year (EUR, owner's DEVEX register or spend wave); revenue and OPEX (EUR/yr, TEA case); ramp-up (fraction of full output, owner); COD year and month (owner); construction schedule (EUR by year, reconciles to FCI within 0.5%); tax rate and depreciation life (owner); residual value (EUR, owner)

**Timing.** Annual periods, year 0 = FID; part-year COD pro-rated; stated with every result (`timing`).

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** None.

**Limitations.** Annual periods; no monthly dating. A model result, not an assured outcome: valid only on the stated case, inputs and assumptions. Null when never reached within the operating life.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`payback_years`).
