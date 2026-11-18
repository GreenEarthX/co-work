---
id: wacc
name: WACC (after tax)
unit: fraction/yr
computed_in: gex_pf_engine/backend/pf_engine/core/returns.py
probe: wacc_after_tax
---

# WACC (after tax)

**Definition.** The weighted after-tax cost of equity and debt on the planned structure at FID.

**Formula.** E/(E+D)·Ke + D/(E+D)·Kd·(1−t); grants outside the weights.

**Inputs, units and sources.** as for the hurdle rate

**Timing.** One rate at FID.

**Valuation boundary.** Independent of the boundary.

**Access.** RETURNS: the owner's finance and executive functions; anyone else only through a RETURNS share of a published case version (`RETURNS_SHARE:<version>`). RETURNS never opens DEVEX sections. The structuring WACC is a recorded figure under project access.

**Decision test and policy source.** WACC against `wacc_target_max` (equity investors' ceiling; GEX proposed). Feeds PROJECT_EQUITY and STRATEGIC_EQUITY, never a gate.

**Limitations.** Structuring reads a recorded WACC; the engine computes its own on a returns case. They are labelled separately.

**Where computed.** `gex_pf_engine/backend/pf_engine/core/returns.py` (`wacc_after_tax`).
