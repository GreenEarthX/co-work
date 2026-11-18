---
id: hurdle_rate
name: Hurdle rates (project and equity)
unit: fraction/yr
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: def hurdle_rate
---

# Hurdle rates (project and equity)

**Definition.** Project hurdle = after-tax WACC + project risk premium. Equity hurdle = cost of equity.

**Formula.** Ke = stated, or rf + β × ERP + country premium + technology premium; WACC = E/(E+D)·Ke + D/(E+D)·Kd·(1−t) on the structure at FID; grants outside the weights.

**Inputs, units and sources.** cost of equity or rf, β, ERP (owner); country, technology and project premiums (owner; registry keys `project_risk_premium`, `technology_risk_premium` are GEX proposed); equity and debt at FID (EUR); cost of debt; tax rate

**Timing.** A single rate for the life of the case, stated with the result.

**Valuation boundary.** FULL_PROJECT (pre-FID spend before year 0) or FROM_FID (pre-FID spend sunk). Never compared with each other.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections.

**Decision test and policy source.** It IS the threshold of the IRR tests; its premiums are policy values (proposed until JML approves).

**Limitations.** Premiums typed by the owner are the owner's assumptions, labelled so.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`def hurdle_rate`).
