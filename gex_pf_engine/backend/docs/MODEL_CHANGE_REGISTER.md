# Model change register — pf_engine

A change to a calculation, or to an expected value in
`tests/validation/returns_expectations.json`, is recorded here before it ships: what
changed, why, the expected values before and after, and who approved it.

| Date | Model | Change | Expected values | Approved |
|---|---|---|---|---|
| 2026-11-17 | returns 1.3.0 | Added `valuation_boundary` (FULL_PROJECT / FROM_FID), `scenario`, debt metrics (DSCR per operating year, LLCR at COD), downside sensitivities, calculation provenance. LLCR status set to VALIDATED against the three independent cases. Existing figures unchanged (46 pre-existing tests pass unchanged). | Created: 3 cases × 15 metrics | Pending JML review |
