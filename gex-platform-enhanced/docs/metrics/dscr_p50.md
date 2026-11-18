---
id: dscr_p50
name: DSCR P50 (recorded)
unit: x
computed_in: gex-platform-enhanced/backend/app/core/structuring_context.py
probe: dscr_p50
---

# DSCR P50 (recorded)

**Definition.** The base-case DSCR as recorded for the project.

**Formula.** Not computed by GEX. Read from the project's recorded structuring inputs (`project_dataset` kind `structuring_context`).

**Inputs, units and sources.** dscr_p50 (x), recorded by the owner; UNVERIFIED unless verified

**Timing.** As recorded; no timing stated by the record.

**Valuation boundary.** Not stated by the record.

**Access.** Project access (069 rule for `project_dataset`).

**Decision test and policy source.** DSCR_P50 against `dscr_floor_p50` (senior lender; GEX proposed). Feeds SENIOR_DEBT_COMMITMENT, never a gate.

**Limitations.** A recorded figure, not an engine result. Missing → not assessable.

**Where computed.** `gex-platform-enhanced/backend/app/core/structuring_context.py` (`dscr_p50`).
