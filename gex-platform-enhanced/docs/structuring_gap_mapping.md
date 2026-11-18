# Structuring gaps — the one mapping table

Handoff v4, tasks 2–4 (17 Nov 2026). Code: `backend/app/core/structuring_engine.py`
(`GAP_MAPPING`, `analyze_gaps`, `conditional_outcome`, `package_estimates`) and
`backend/app/core/decision_policy.py` (`DECISION_TESTS`). If this page and the code
disagree, the code wins: fix this page.

## Principle

Gates certify facts, not investment merit. A structuring gap is one of three kinds.
None of them moves a state: the state is the gate engine's, from one snapshot
(`app/core/readiness.py`).

| Kind | What it concerns | Closes when | Feeds |
|---|---|---|---|
| `REQUIREMENT` | one open requirement of G1, G2, G4, G5 or G7, in the engine's words | that requirement is VERIFIED (at its required maturity) | its gate; the gate completes only when all its applicable requirements do |
| `COMMITMENT` | a gate's open commitment or coherence reason (`blocked_reasons`) | the engine no longer reports it | its gate |
| `DECISION_TEST` | a metric against an attributed policy value | the metric meets an APPROVED value | the capital decision it affects — never a gate |

## Requirement gaps

| Gate | gap_type | risk category |
|---|---|---|
| G1_GRID_UTILITIES_REALITY | GRID | GRID |
| G2_CERTIFICATION_PATH_LOCKED | CERTIFICATION | CERTIFICATION |
| G4_OFFTAKE_BANKABLE | OFFTAKE | OFFTAKE |
| G5_EPC_RISK_PRICED | EPC_WRAP | CONSTRUCTION |
| G7_INSURANCE_BOUND | INSURANCE | CONSTRUCTION |

Severity follows the item's tier: deal-killer → BLOCKING, "Required" (warning) →
DEGRADING, advisory → ADVISORY. One gap per open, applicable requirement; each names the
gate's remaining requirements. The five typed statuses that used to stand in for these
gates (`cert_readiness`, `epc_status`, `insurance_status`, `grid_status`, and a typed
`llcr`) are retired: ignored if present in a stored record.

## Decision-test gaps

| Test | Metric | Policy key (registry) | Comparator | Capital decision |
|---|---|---|---|---|
| DSCR_P50 | recorded `dscr_p50` | `dscr_floor_p50` | ≥ | SENIOR_DEBT_COMMITMENT |
| DSCR_P90 | recorded `dscr_p90` | `dscr_floor_p90` | ≥ | SENIOR_DEBT_COMMITMENT |
| DSCR_DEFAULT (deal killer) | recorded `dscr_p90` | `dscr_default_floor` | ≥ | SENIOR_DEBT_COMMITMENT, DEBT_DRAWDOWN |
| DSCR_COVENANT (screens) | engine or CFADS DSCR | `dscr_covenant_floor` | ≥ | DEBT_DRAWDOWN |
| WACC | recorded `wacc` | `wacc_target_max` | ≤ | PROJECT_EQUITY, STRATEGIC_EQUITY |
| OFFTAKE_COVERAGE | recorded `offtake_coverage_pct` | `offtake_coverage_min` | ≥ | SENIOR_DEBT_COMMITMENT (names the open G4 requirements) |
| REGULATORY_PREMIUM | jurisdiction premium | `regulatory_premium_max` | ≤ | PROJECT_EQUITY, STRATEGIC_EQUITY |
| DFI_IRR | engine IRR without the DFI's terms | `dfi_irr_hurdle` (per DFI) | ≤ | DFI_MEZZ_GUARANTEES (one input only) |
| DFI_CATALYTIC | evidenced commercial / DFI money | `dfi_catalytic_ratio_min` (per DFI) | ≥ | DFI_MEZZ_GUARANTEES |

Outcomes: PASS, FAIL (BLOCKING), NO_APPROVED_THRESHOLD ("no approved threshold — no
pass/fail", NOT_JUDGED), NOT_ASSESSABLE ("not assessable — required inputs missing",
NOT_JUDGED). A missing input is never a pass and never a confirmed breach. The metric is
always computed and shown.

Policy status: "GEX proposed" (every value on 17 Nov 2026), "GEX default (approved by
JML)", or "institution policy (established, with reference)". A GEX default is never shown
as a lender's, insurer's or DFI's policy.

## Packages

A package of instruments changes no state, closes no gap, completes no requirement and
passes no decision test. Its after-figures (WACC, DSCR P50/P90) are ESTIMATES with the
method shown; LLCR has none. The next state is shown as **conditional — not achieved**,
listing the gates and requirements the engine says it would need.
