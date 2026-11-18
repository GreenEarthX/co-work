---
id: dscr_p90
name: DSCR P90 (recorded)
unit: x
computed_in: gex-platform-enhanced/backend/app/core/structuring_context.py
probe: dscr_p90
---

# DSCR P90 (recorded)

**Definition.** The downside (P90) DSCR as recorded for the project.

**Formula.** Not computed by GEX. Read from the recorded structuring inputs.

**Inputs, units and sources.** dscr_p90 (x), recorded by the owner

**Timing.** As recorded.

**Valuation boundary.** Not stated by the record.

**Access.** Project access (069 rule for `project_dataset`).

**Decision test and policy source.** DSCR_P90 against `dscr_floor_p90`; DSCR_DEFAULT (the deal killer) against `dscr_default_floor`. Both GEX proposed: no pass/fail until approved.

**Limitations.** A recorded figure. Missing → not assessable, never a breach.

**Where computed.** `gex-platform-enhanced/backend/app/core/structuring_context.py` (`dscr_p90`).
