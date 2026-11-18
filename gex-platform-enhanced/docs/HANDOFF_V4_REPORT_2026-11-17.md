# Handoff v4 — report to JML (17 Nov 2026)

Branch `readiness-returns-v4` in `gex-platform-enhanced` and `gex_pf_engine`. **Nothing is
committed or pushed.** Other people's uncommitted work in the tree was not touched or staged.
Detail: `docs/CLAUDE_HANDOFF.md` §8 item 92.

## 1. Test counts

| Suite | Result |
|---|---|
| PF engine (`gex_pf_engine/backend`, micro_service venv) | **376 pass**, 0 fail |
| Platform, both URLs exported, run alone | **1975 pass, 15 skip, 0 fail** (15 min); the same 15 skips as before (7 auth isolation, 7 plant builder, 1 evidence archive). Morning baseline 1896: +79 from the new and extended test files. |
| Frontend vitest | **314 pass**, 0 fail (53 files) |
| `tsc --noEmit` | clean |
| `audit-menu.mjs --check` (now includes the metric registry) | pass |
| `audit-causal-ways.mjs --check` | pass |

New test files: `test_readiness_authority.py` (8), `test_gaps_and_decision_tests.py` (20),
`test_pre_fid_derived_reads.py` (12), `test_no_store.py` (13), `test_returns_cases.py` (16),
`test_returns_case_store_pg.py` (3); `test_no_breizh_data_points.py` +6; `test_dscr_sensitivity.py` +1;
engine `test_returns_expectations.py`, `test_returns_cases.py`; frontend `sensitiveQueries.test.ts` (5),
`decisionPolicy.test.ts` (4). Each new rule was broken on purpose and its test failed (readiness
fingerprint, no-threshold passing, verified requirement kept as a gap, package promoting state, IRR
establishing additionality, CEC gated on the wrong section, lineage and capital-bridge originals,
G8 registry parity, metric registry staleness, cache clearing, all-withheld register).

**Tests changed, and the rule behind each:**

| Test | Change | Rule |
|---|---|---|
| `test_structuring_context.py` | retired fields ignored; incomplete inputs named, not refused; `llcr` None | tasks 2, 5 |
| `test_project_records.py` | engine snapshot via `readiness.current`; record tests use Le Havre; Bremen now refused | tasks 1, 7 |
| `test_commitment_terms.py::test_every_evaluation_sends_the_cards_to_the_engine` | persona view evaluates via `/evaluate`, not `/evaluate/persona` | task 1: one snapshot |
| `test_evidence_expiry.py` (`_stale_run`) | fixture snapshot carries a matching fingerprint | task 1: a snapshot without one is re-evaluated |
| engine `test_bankability_gates.py` | rules 4.9.0; G8 carries `engine_returns_case` | task 6 (G8) |

## 2. Data steps

1. Backup `files/db_backups/daily/gex_platform_2026-11-17_1442.dump` before migrations 121–123
   (each round-tripped; head **123**, 174 tables, 167 FORCED).
2. Strip dry run: **Bremen 9/9, Le Havre 0/9, Wales 0/9** — as expected.
3. Backup `files/db_backups/daily/gex_platform_2026-11-17_1500.dump` (verified, full read).
4. Quarantine: `backend/scripts/data/quarantine/proj_bremen_h2_structuring_context_20261117.json`,
   payload sha256 `43f92972beab19343d31ebff29185c757f3e656159607ca489753f09b349fadf`, source
   `routes_structuring.DEMO_CONTEXTS`, state UNVERIFIED.
5. Audit table: **none exists** for `project_dataset` (checked `entitlement_audit`,
   `marketplace_record_history`, `project_premise_change`); the quarantine file is the audit copy.
6. Row deleted; load file corrected; loader fixed; strip run with `--execute` (Le Havre, Wales).
7. Policy proposals: 23 rows, all `proposed`, by `POLICY_PROPOSAL_20261117`.
8. Live verification on North Sea e-Methanol (illustrative inputs): two published versions and
   two shares (now revoked) remain in the database; versions are immutable by design.
   **Correction (18 Nov):** two further North Sea shares created for screenshots 10–11 were left
   active on 17 Nov; they were revoked on 18 Nov through the owner's routes. 0 active shares now.

## 3. Screenshots

21 annotated screenshots (numbered markers, arrows, legend) and the flow diagram:
[`docs/screenshots/handoff_v4/README.md`](screenshots/handoff_v4/README.md). Owner Lisa
Friedrich (HamburgOne); bank Henrik Vost (NORD/LB); illustrative inputs. Every owner step and
every bank step of Part D is shown, including revocation closing each path. Not shown: Gap
Analysis with requirement-level gaps (no account can open a project holding structuring
inputs) and a live "needs review" trigger (covered by tests). Four findings (A–D) are listed
there, including the demo-password reset on every backend start.

**18 Nov — JML's decisions on A–D applied** (handoff §8 item 93): D fixed and verified across a
restart; A shared projects listed with only what was shared; B owner-only write controls; C one
DEVEX Brief page. Open from A: no record of a bank's participation exists, and
`capital_stack_tranches` would let one financier read another's terms.

## 4. Defects fixed (file and line as of this report)

- Readiness drawn from different evaluations per screen; `state_map` promotion in structuring
  (`core/readiness.py`; `core/structuring_engine.py` `conditional_outcome`).
- Missing DSCR fired the deal killer as a breach; 1.10 a fourth floor (`core/deal_killers.py` `_dscr_outcome`).
- Additionality decided on typed IRRs against hard-coded hurdles (`api/v1/additionality.py` `_compute_additionality`).
- Typed DSCR/LLCR floors on five screens and in `services/dscr_sensitivity.py` `compute_sensitivity` (default 1.20/1.30).
- CEC and portfolio summary ignored the pre-FID rule (`api/v1/pre_cod_metrics.py` `_packages`).
- Lineage named a project after a package (`api/v1/lineage.py` `_fetch_identity`).
- Capital-bridge one-shot view never read shared rows in the owner's tenant (`api/v1/capital_bridge.py` `get_full_project`).
- Package register answered 404 "no packages" when everything was withheld (`api/v1/development_packages.py` both summary routes).
- No `Cache-Control` on pre-FID responses; frontend showed cached figures after a refusal.
- Returns: "DEVEX €0" beside a full-project IRR for a non-owner (`features/finance/ReturnsPage.tsx`).
- Loader recreated Bremen's Breizh copy (`scripts/move_project_datasets_20261025.py` `refusals`).
- Returns-case export was a plain link without the bearer token (`features/finance/PublishedCases.tsx`).

## 5. For JML's review — nothing here is approved

**Proposed policy values** (all "GEX proposed", source: code constants, no external source):

| Key | Party | Value |
|---|---|---|
| `dscr_floor_p50` | GEX | 1.30 |
| `dscr_floor_p90` | GEX | 1.20 |
| `dscr_covenant_floor` | GEX | 1.25 |
| `dscr_default_floor` | GEX | 1.10 |
| `llcr_floor` | GEX | 1.20 (no decision test wired) |
| `wacc_target_max` | GEX | 8 % |
| `offtake_coverage_min` | GEX | 70 % |
| `regulatory_premium_max` | GEX | 30 bps |
| `project_risk_premium` | GEX | 1 % |
| `technology_risk_premium` | GEX | 3 % |
| `sponsor_equity_hurdle` | GEX | 12 % |
| `dfi_irr_hurdle` | EIB 9.2 %, KfW 9 %, IFC 8.5 %, Bpifrance 9 %, DFC 10 %, AfDB 8 % | |
| `dfi_catalytic_ratio_min` | EIB 2.5, KfW 2, IFC 3, Bpifrance 2, DFC 2.5, AfDB 2 | |

The DFI values are attributed to each DFI as party but have no reference, so they can never
display as that DFI's policy until one is recorded.

**Proposed audience templates** (`backend/app/core/audience_templates.py`, grant nothing):
senior lender (SUMMARY; IRR, NPV, DSCR, LLCR, payback, downside), DFI (SUMMARY, FUNDING; IRRs,
NPV, DSCR, downside), equity investor (SUMMARY, BREAKDOWN; levered IRR, equity NPV, ROE, equity
payback, downside), insurer (nothing), lenders' adviser / IE (SUMMARY, PACKAGES; IRR, DSCR, LLCR,
provenance).

**Decisions needed:**
1. Approve, change or reject each policy value and template above.
2. CEC status bands (50 % warn, 85 % target) are typed in `pre_cod_metrics.py`, unattributed.
3. The IC pack routes are demo stubs; its JSON export claims `"verified": true` over a hash of the project id and time.
4. The downside shock set is "GEX proposed".
5. Commit: on your word, a branch per repo with only this work staged.

## 6. What the document got wrong, or did not cover

- Part A is committed on the platform's main, not uncommitted as stated.
- `development_packages` is read through `capital_connection` and `pre_cod_metrics` through `domain_connection`; equivalent on PostgreSQL only.
- `dscr_covenant_floor` had no decision test; `DSCR_COVENANT` was added for the covenant screens.
- The PF engine (launchd, no `--reload`) had been running since 15 Nov; none of the engine work was live until it was restarted.
- `com.gex.expiry-sweep` last exited 4 (its watchdog code for a database hang).
- LLCR differs slightly between the two boundaries (1.8863 vs 1.8858) in the live run: pre-FID spend affects depreciation and so tax, and CFADS is after tax. Correct on the model's definitions; worth confirming it is the intended treatment.
