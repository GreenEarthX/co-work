---
id: cec
name: CEC — Capital Eligibility Coverage
unit: fraction
computed_in: gex-platform-enhanced/backend/app/api/v1/pre_cod_metrics.py
probe: def _compute_cec
---

# CEC — Capital Eligibility Coverage

**Definition.** The share of development-package cost in an eligible-or-later workflow state.

**Formula.** Σ cost(packages in evidenced…closed) / Σ cost(all packages).

**Inputs, units and sources.** development packages: cost_amount (EUR), workflow_state — the owner's register

**Timing.** Live, at the time of the request.

**Valuation boundary.** All packages, or post-FID packages only (labelled).

**Access.** SUMMARY: the owner and GEX staff get every package; anyone else gets post-FID packages only, labelled, unless the owner shares SUMMARY (read in the owner's tenant).

**Decision test and policy source.** None attributed. Its status bands (50% warn, 85% target) are typed in pre_cod_metrics.py, not policy values — for JML's review.

**Limitations.** Counts cost, not evidence quality. Typed status bands.

**Where computed.** `gex-platform-enhanced/backend/app/api/v1/pre_cod_metrics.py` (`def _compute_cec`).
