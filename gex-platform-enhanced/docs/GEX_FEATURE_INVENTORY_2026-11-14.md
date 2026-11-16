# GEX feature inventory — 2026-11-14

Measured from the working tree on 2026-11-14. Secrets, tenant names and client data are left out.

## 1. Snapshot

| Item | Value |
|---|---|
| Platform repo | `gex-platform-enhanced`, branch `greenmesh-phase2`, HEAD `3a3da28` (2026-11-14, "Retarget the four Purchase and Sales buttons to Market Discovery (F17)") |
| Uncommitted | 43 paths: market role policy (`core/market_policy.py`), product records (migration 116, `core/product_record.py`, `routes_products.py`) and their tests. **The inventory includes this uncommitted work.** |
| PF engine repo | `gex_pf_engine`, branch `greenmesh-phase2`, HEAD `22aecf7` (2026-11-12), clean |
| Database | Alembic head **116**; 169 tables, 162 under FORCED RLS |
| Backend API | 618 routes in 79 `/api/v1` prefixes (FastAPI, :8000) |
| Frontend | 118 routes; 70 menu entries (67 distinct screens) (Vite/React/TS, :3000) |
| TEA engine | 9 endpoints (:8002, stateless) |
| PF engine | 49 endpoints (:8001) |

### Test results (run 2026-11-14)

| Suite | Result | Command / condition |
|---|---|---|
| Platform backend | **1699 pass, 15 skip, 0 fail** (16 min). Skips: 7 auth-isolation (no SQLite path on PostgreSQL), 7 plant-builder energy (electrolysers state no SEC), 1 evidence archive empty | `pytest tests/ -q -rs`, `DATABASE_URL` and `ALEMBIC_DATABASE_URL` exported, run on its own |
| Frontend | **278 pass**, 45 files, 0 fail | `npx vitest run` |
| PF engine | **278 pass**, 0 fail | `pytest tests/` under `micro_service` |
| TEA engine | No suite of its own. Covered by 99 platform tests in `test_tea_*.py` | — |

## 2. Status labels

- **Tested**: a dedicated automated test exercises the feature and passed today.
- **Unverified**: the code is built and mounted, but no direct test was found. It may work, but nothing proves it does.
- **Placeholder**: a stub, a 501, hard-coded content, or state kept only in `localStorage`.
- **Planned**: not built. It is decided, or recorded in `docs/COMMERCIAL_PLATFORM_GAP_REGISTER.md`.

Each test mapping was found by searching the tests for the route prefix or module name. A screen is "Tested" only if a frontend test renders it.

## 3. Roles

- **Company types:** PRODUCER, OFFTAKER, THIRD_PARTY. A THIRD_PARTY has a service type: BANK, INSURER, DFI, ENGINEER, CERTIFIER, LEGAL, LOGISTICS, EQUIPMENT or PLATFORM (GEX staff).
- **Functions:** ENGINEERING, FINANCE_TREASURY, COMMERCIAL, COMPLIANCE_LEGAL, OPERATIONS, EXECUTIVE. An EXECUTIVE sees every screen open to its company type.
- **Project reviewers** (verify evidence for their assigned gates only): certifier, independent engineer, lenders' adviser, insurer, grant assessor, seed adviser, strategic-investor adviser.
- **Market acts** (`core/market_policy.py`): COMMERCIAL acts, the CEO or CFO approves a trade confirmation, OPERATIONS declares capacity.
- **Enforcement:** the menu is navigation only. Access is enforced by ABAC middleware, by row-level security as the `gex_app` role, and by route-level guards.

## 4. Platform features

### 4.1 Identity, access, administration

| Feature | Purpose | Roles | Screen / API | Status | Source |
|---|---|---|---|---|---|
| Sign-in, refresh, password change, telephone | Session lifecycle; a temporary password must be changed | All | `/login`, `/account/password`; `/api/v1/auth` | **Tested** | `api/v1/routes_auth.py`, `core/auth.py`; `test_change_password`, `test_refresh_reads_the_auth_store`, `test_telephone`, `test_password_policy` |
| Account vetting | Registration creates a PENDING account; GEX staff activate it after telephone and agreement checks, with separation of duties | GEX staff | `/api/v1/account` | **Tested** | `core/account_lifecycle.py`, `routes_account_vetting.py`; `test_account_lifecycle` |
| Account page 2FA button | — | All | `/account` | **Placeholder**: the button does nothing, and the page invents three sign-ins when the history call fails | `features/auth/AccountPage.tsx` |
| KYC / KYB | Identity and company checks | All | `/kyc`, `/kyb`; `/api/v1/kyc` | Store **Tested**; routes and screens **Unverified** | `routes_kyc.py`; `test_kyc_store` |
| Onboarding wizard | Self-registration and first project | Prospects | `/onboarding`; `/api/v1/onboarding` | **Unverified** | `onboarding.py`, `features/onboarding/OnboardingWizard.tsx` |
| ABAC, entitlements, finance entitlement | Policy decisions per resource and verb | All | middleware; `/api/v1/entitlements` | **Tested** | `core/abac*.py`, `core/entitlements.py`; `test_route_authorization`, `test_entitlements_slice`, `test_finance_entitlements`, `test_rls_isolation` |
| CISO workspace | Information barriers, residency, identity, screen access, OT gateways | Client CISO, GEX staff | `/ciso-*` (11 screens); `/api/v1/ciso` | API **Tested**. Screens **Unverified**. Gantt config **Placeholder** (localStorage). "Policy Matrix" and "Compliance" open the same screen. | `routes_ciso.py`, `routes_screen_access.py`, `features/ciso/*`; `test_ciso_real_data_pg` |
| GEX staff console | Read-only view of admins, companies, staff rights and onboarding steps | GEX staff | `/gex-console`; `/api/v1/gex-console` | **Tested** | `routes_gex_console.py`, `features/gexConsole/GexStaffConsolePage.tsx`; `test_gex_console_pg` + 1 frontend test |
| Break-glass, audit, event store | Logged admin override; append-only event ledger | GEX staff | `/api/v1/audit`, `/api/v1/events` | **Tested** | `core/break_glass.py`, `core/event_store.py`; `test_break_glass`, `test_event_store_slice` |
| Live event stream (SSE) | Push gate and evidence changes | All | `/api/v1/events/stream` | **Placeholder**: returns 501 "DEFERRED" | `routes_events.py:166` |
| Client billing | Fee schedule frozen into the terms version | GEX, payer | `/api/v1/billing` | **Unverified** (only mentioned in a route test) | `routes_client_billing.py` |
| Matrix comms | Messaging rooms | All | `/ciso-communications`; `/api/v1/comms` | **Unverified** | `routes_matrix.py`, `services/matrix_service.py` |

### 4.2 Projects and bankability gates

| Feature | Purpose | Roles | Screen / API | Status | Source |
|---|---|---|---|---|---|
| Project registry, profile, datasets | One record per project; datasets by kind; owner-only commercial data | All (scoped by RLS) | `/projects`, `/projects/new`; `/api/v1/projects`, `/api/v1/premises` | **Tested** (backend and screen) | `routes_projects.py`; `test_projects_canonical`, `test_premises_pg`, `test_project_records`, `test_frontend_datasets_pg`, `test_demand_buyers_access_pg` |
| Twelve-gate engine (G0–G11, rules 4.8.0) | Evaluate bankability from evidence; the gate figures come only from the engine | All | `/stage-gates`, `/bankability-scores`, `/finance/bankability`; `/api/v1/bankability` → PF `/api/v1/bankability` | **Tested** | `routes_bankability_proxy.py`, `core/engine_view.py`, PF `core/bankability_engine.py`; `test_gate_registries_agree`, `test_engine_view_and_reports_pg`, PF `test_bankability_gates` |
| Evidence and review | Submit evidence, attach documents, expiry, reviewer separation of duties | Producer submits; appointed reviewer verifies | `/stage-gates`; `/api/v1/bankability/evidence`, `/api/v1/evidence` | **Tested** | `abac_middleware.py`, `core/abac.py` `REVIEWER_GATES`; `test_evidence_review_separation`, `test_evidence_expiry`, `test_evidence_slice` |
| Reviewer appointments | GEX appoints a reviewer on a named party's instruction | GEX staff | "Who verifies" panel; `/api/v1/projects/{id}/reviewers` | **Tested**. No live reviewer is assigned yet, so nobody can verify (by design). | `core/reviewer_appointments.py`, `ReviewersPanel.tsx`; `test_reviewer_appointments` |
| Bankability reports, premise changes | Engine view of one project and what changed | Producer | `/project-report`; `/api/v1/projects/.../reports`, `/api/v1/bankability-updates` | Backend **Tested**; screen **Unverified** | `routes_bankability_reports.py`, `features/executive/ProjectReportPage.tsx` |
| Deal killers, state and blockers | Blocking conditions per project | All | `/bankability-scores`; `/api/v1/deal-killers` | **Tested** | `routes_deal_killers.py`; `test_commitment_taxonomy` |
| Evidence hierarchy | Explains evidence tiers per gate | All | `/evidence-hierarchy` | **Unverified** (mostly static gate definitions) | `features/finance/EvidenceHierarchy.tsx` |
| Challenge review | Adversarial review of claims | All | `/adversarial-review`; `/api/v1/adversarial-reviews` | **Unverified** | `routes_adversarial_reviews.py`, `features/reviews/AdversarialReviewPage.tsx` |
| Reference data registry | Versioned parameters with a proposed → approved lifecycle | GEX proposes and approves; all read | `/api/v1/reference` | **Tested** | `core/reference_registry.py`, `routes_reference.py`; `test_reference_registry_pg`, `test_reference_routes` |
| Fuel catalogue | Public list of fuels; the PF engine reads it | All | `/api/v1/fuels`, `/api/v1/onboarding/reference-data/fuels` | **Tested** | `routes_fuels.py`; `test_fuel_reference_slice` |
| Expiry sweep | Re-evaluates projects when evidence lapses | Scheduled job | `scripts/expire_evidence.py` | **Tested** | `test_evidence_expiry` |

### 4.3 Market and trading

| Feature | Purpose | Roles | Screen / API | Status | Source |
|---|---|---|---|---|---|
| Capacity and token mint | Declare capacity; mint UNVERIFIED tokens within that capacity (enforced by a database trigger) | Producer OPERATIONS / COMMERCIAL | `/capacity`; `/api/v1/capacities`, `/api/v1/tokens` | **Tested** backend; `/capacity` screen **Unverified** | `capacity_sqlite.py`, `tokens_sqlite.py` (PostgreSQL only despite the names); `test_token_mint_pg`, `test_token_lifecycle` |
| Market listings, RFQs, proposals, acceptance | Anonymised discovery; acceptance carves the exact quantity; idempotent creates | COMMERCIAL; CEO/CFO approves | `/market-discovery`, `/rfqs`, `/matching`, `/trader-dashboard`, `/counterparties`; `/api/v1/market`, `/api/v1/matching`, `/api/v1/trader` | **Tested** (backend and screens) | `core/market_engine.py`, `core/token_partition.py`, `core/idempotency.py`, `core/market_policy.py`*; `test_market_chain`, `test_market_split_and_idempotency_pg`, `test_market_policy_pg`*, `MarketScreens.test.tsx`, `MarketPolicyScreens.test.tsx`* |
| Settlement | Payee confirms, title moves | Parties | `/settlement`; `/api/v1/settlements`, `/api/v1/market/settlements` | Backend **Tested**; screen **Unverified** | `settlement_events.py`; `test_market_chain_pg` |
| Trading book / contract record | One contract model: terms → legs → flows, versions, four-eye TRADE_CONFIRM | Parties | `/contracts`; `/api/v1/trading-book` | Backend **Tested**; `/contracts` screen **Unverified** | `trading_book/record.py`, `flows.py`, `core/order_book.py`, `core/wae.py`; `test_trading_book_api`, `test_order_book_pg`, `test_order_book_token_pg` |
| Contract cards and offtake frame | Confirmed commitment terms per buyer; novation; adverse facts | Parties | `/api/v1/contract-tokens` (deprecated layer) | **Tested** | `core/contract_tokens.py`; `test_contract_tokens_pg`, `test_offtake_frame_pg`, `test_novation_pg`, `test_adverse_facts_pg` |
| Party signatures | Optional ed25519 signatures on confirm/dispute events | Executives | `/account`; `/api/v1/trading-book/party-keys` | **Tested**; not required (`REQUIRE_PARTY_SIGNATURE=false`) | `test_party_signatures_pg` |
| Ledger anchor | Hash every contract event to an outbox for a public anchor | Worker role | `scripts/drain_anchor_outbox.py` | **Tested**; **switched off** (`LEDGER_ANCHOR_BACKEND=none`) | `core/ledger_anchor.py`; `test_ledger_anchor_pg` |
| Commercial overview, Purchase, Sales | Entry points into the market | COMMERCIAL, offtakers, banks | `/marketplace`, `/offtaker-supply`, `/finance-demand` | **Tested** (1 frontend test each) | `MarketplacePage.tsx`, `OfftakerSupplyTable.tsx`, `DemandPipeline.tsx`; `MarketLinks.test.tsx` |
| Marketplace analytics, lineage, next best action | Read-only analytics | All | `/finance/lineage`; `/api/v1/marketplace`, `/api/v1/lineage`, `/api/v1/nba` | **Unverified**. These still read SQLite with no backend-switch guard (`lineage.py`, `next_best_action.py`, `marketplace_analytics.py`). | `api/v1/*` |
| Open-interest board | Indications of interest, with publisher confidentiality | All | `/api/v1/open-interest` | **Tested** | `routes_open_interest.py`; `test_open_interest_routes` |

\* uncommitted.

### 4.4 Physical delivery and compliance (GreenMesh Phases 1–2)

| Feature | Purpose | Roles | Screen / API | Status | Source |
|---|---|---|---|---|---|
| Chain of custody to RED III grade | Accounting periods, inputs, conversion factors, period statements, hash chain | Owner writes; project access reads | API only: `/api/v1/chain-of-custody` | **Tested** | `api/v1/mass_balance.py`, `core/custody_ledger.py`; `test_custody_periods_pg`, `test_chain_of_custody` |
| Metered reconciliation | Compare declared lots with metered output: RECONCILED, VARIANCE or UNVERIFIED | Owner, OT gateway | `/plant-data`; `/api/v1/plant-data` | Backend **Tested**; screen **Unverified** | `core/ot_boundary.py`, `core/meter_reconciliation.py`; `test_metered_reconciliation_pg` |
| RFNBO correlation (computed) | Temporal, geographic and additionality checks against a versioned rule table | Owner, reviewers | `.../periods/{id}/rfnbo-correlation`; `/api/v1/decision-twin` (declared path) | **Tested**. Rule rows follow DA 2023/1184 as written; counsel has not confirmed them. | `core/rfnbo_correlation.py`, `core/decision_twin.py`; `test_rfnbo_correlation_pg` |
| Upstream hydrogen proof | Carries an upstream period's RFNBO result through to the next lot | Holder of a settled H2 token | custody inputs | **Tested** | `core/upstream_proof.py`; `test_upstream_proof_pg` |
| Deliveries, risk, quality, title | Delivery record; Incoterm risk; agreed inspector; waiver or rejection; title and token split | Seller, buyer, inspector | API only: `/api/v1/trading-book/records/{id}/deliveries` | **Tested** up to TITLE_TRANSFERRED. SETTLED is refused. | `core/delivery_record.py`, `core/delivery_title.py`, `trading_book/clauses.py`; `test_delivery_*_pg`, `test_contract_clauses*` |
| Take-or-pay shortfall | Shortfall computed from the trade's commitment clause | Parties | API only | **Tested** | `test_take_or_pay_pg` |
| Lender evidence pack | Per-contract JSON with a SHA-256 manifest; every item VERIFIED, DECLARED or MISSING | Contract parties | API only: `/api/v1/evidence-pack/contract/{id}` | **Tested**; Phase 1 gate closed | `core/evidence_pack.py`; `test_evidence_pack_pg`, `test_evidence_pack_delivery_pg` |
| Registry connectors | Export of VERIFIED items only, through an outbox | Seller | API only | **Tested**. Backend is `none`, and no scheme payload exists (no public spec was found). | `test_registry_connectors_pg` |
| Product records | Product certificates verified only by an appointed independent reviewer; expiry derived from `valid_until` | Owner, certifier | `/api/v1/products` | **Tested** (uncommitted, migration 116) | `core/product_record.py`, `routes_products.py`; `test_product_records_pg` |
| Carbon attribution, additionality | Attribution events per trade | Parties | `/api/v1/carbon-attribution`, `/api/v1/additionality` | **Tested** (through the slice and pack tests) | `carbon_attribution.py`, `additionality.py` |

### 4.5 Finance and structuring

| Feature | Purpose | Roles | Screen / API | Status | Source |
|---|---|---|---|---|---|
| Capital bridge, structuring, instruments | Capital-taxonomy fit, instrument compatibility, structuring context | Producer finance, banks | `/instrument-compatibility`, `/finance-instruments`, `/finance-structuring-timeline`; `/api/v1/capital-bridge`, `/api/v1/structuring`, `/api/v1/instruments` | Backend **Tested**; screens **Unverified** | `capital_bridge.py`, `routes_structuring.py`; `test_capital_bridge_projects_routes`, `test_project_records` |
| Financial model (CFADS, waterfall, DSRA, covenants) | Engine-computed debt cashflow | Producer finance, banks, DFIs | `/finance/debt-waterfall`, `/covenants`, `/capital-stack`; `/api/v1/finance-model` → PF `/api/v1/model` | Engine **Tested**; platform route **Tested** (multicurrency, authorization); screens **Unverified**. LLCR, PLCR and sources & uses are not computed and are shown as gaps. | PF `core/cfads.py`, `core/waterfall.py`, `core/debt/`; `test_finance_multicurrency`, PF `test_model_invariants`, `test_cfads_multi_currency` |
| DSCR sensitivity, pre-COD metrics | Projected DSCR, restricted by finance entitlement | Finance function, lenders, insurers | `/dscr-sensitivity`; `/api/v1/pre-cod-metrics` | Backend **Tested**; screen **Unverified** | `pre_cod_metrics.py`, `DSCRHeatmap.tsx`; `test_dscr_llcr_characterization` |
| Gabillon pricing, offtake valuation, portfolio roll-up | Forward curves, price decomposition, offtake contract value | Finance, banks; CISO admin | `/pricing-curves`, `/pricing-lineage`, `/ciso-pricing`; `/api/v1/pricing` → PF `/api/v1/pricing` | Engine **Tested**; `/pricing-curves` **Tested**; `/pricing-lineage` **Unverified**; `/ciso-pricing` keeps state in localStorage | PF `core/gabillon.py`, `pricing/offtake`; PF `test_gabillon`, `test_offtake` |
| Development packages, spend wave | Pre-FID spend phasing | Producer finance, banks | `/finance-package`, `/finance/spend-wave`; `/api/v1/packages`, `/api/v1/spend-wave` | Backend **Tested** (characterisation); screens **Unverified** | `development_packages.py`, `spend_wave.py`; `test_slice5_characterization` |
| Drawdown schedule | Capital drawdown timeline | Producer finance, banks | `/finance/drawdown-timeline`; `/api/v1/drawdown-schedule` | **Unverified** | `drawdown_schedule.py` |
| Commitments (eIDAS CSS) | Signing and verifying commitments | Finance, commercial | `/commitment-signing`, `/commitment-verifier`; `/api/v1/commitments` | Taxonomy **Tested**. **Known defect:** countersigning issues `UPDATE commitment_records`, which is revoked for `gex_app`. | `core/css.py:272`; `test_commitment_taxonomy` |
| Approvals queue | Four-eye approvals | Executives, banks | `/approval-queue`; `/api/v1/approvals` | **Tested** (through the market and governance tests) | `routes_approvals.py`; `test_governance_identity_pg` |
| IC pack, data room, banker's snapshot, transfer readiness, gap analysis, risk matrix, term sheet | Diligence views over project datasets | Producer finance, banks, legal | `/ic-pack`, `/data-room`, `/bankability-snapshot`, `/transfer-readiness`, `/finance-gaps`, `/finance-risk-matrix`, `/term-sheet` | **Unverified** | `features/finance/*`, `routes_ic_pack.py`, `routes_data_room.py` |
| Sovereign instruments, DFI criteria, risk pricing | DFI and sovereign support screening | DFIs, banks | `/finance/dfi-dashboard`; `/api/v1/sovereign-instruments`, `/api/v1/dfi-criteria`, `/api/v1/risk-pricing` | **Unverified** | `sovereign_instruments.py`, `dfi_criteria.py`, `routes_risk_pricing.py` |
| Insurance schedule, coverage lines, asset register | Conditions precedent for insurers | Insurers, producer finance | `/insurance-schedule`, `/insurance-coverage`, `/insurance-assets` | Schedule **Unverified**. Coverage and asset register are **Placeholders** (per-molecule tables hard-coded in the screen). | `features/insurance/*` |
| Finance dashboard, task flow, CEO report | Portfolio overview | All, executives | `/dashboard`, `/finance-dashboard`, `/cfo-report`; `/api/v1/task-flow` | **Unverified** | `FinanceDashboardPage.tsx`, `CFOReport.tsx`, `routes_task_router.py` |

### 4.6 Engineering, operations, compliance screens

| Feature | Purpose | Roles | Screen / API | Status | Source |
|---|---|---|---|---|---|
| Plant builder, canvas, plants, equipment equations | Equipment sizing and CAPEX/LCOF basis | Engineering, finance, equipment vendors | `/finance-plant-builder`, `/canvas/:plantId`, `/plants`; `/api/v1/plant-builder`, `/api/v1/plant-canvas`, `/api/v1/plants`, `/api/v1/equipment-equations` | **Tested**, but 7 energy tests skip because catalogue electrolysers state no SEC | `routes_plant_*.py`; `test_plant_canvas_endpoints`, `test_plants_endpoints`, `test_equipment_equations`, `test_plant_builder_energy` |
| Construction progress | Producer bankability view with capital stack | Engineering, operations, finance | `/producer-bankability` | **Tested** (1 frontend test) | `ProducerBankabilityView.tsx` |
| Project timeline | Milestones and drawdown | All | `/finance-timeline`; `/api/v1/timeline` | **Unverified** | `ProjectTimeline.tsx`, `routes_timeline.py` |
| Certification readiness | Distance to certification | Compliance, certifiers | `/cert-readiness`; TEA `/certification-gate` | **Unverified** | `CertReadiness.tsx` |
| Regulatory registry, Reports hub | Regulator view; links hub | Compliance, legal; all | `/regulator-dashboard`, `/reports`; `/api/v1/reports` | **Unverified** | `RegulatorDashboardPage.tsx`, `ReportsPage.tsx` |
| Demand, ecosystem, performance, project truth, workflow, verification, vocabulary, corpus | Supporting reads | Various | `/api/v1/{demand,ecosystem,performance,project-truth,workflow,verification,vocabulary,corpus}` | Vocabulary and corpus **Tested** (`test_vocabulary_guardrails`, `test_external_corpus`); the rest **Unverified**. `ecosystem_store` is dormant (its tables exist in neither store). | `api/v1/*` |
| Off-menu screens | Production, tokenisation, procurement simulator, revenue, executive dashboard, economics | Various | `/production`, `/tokenisation`, `/procurement-simulator`, `/revenue`, `/executive-dashboard`, `/economics/:projectId` | **Unverified**; reachable by URL only | `features/*` |

## 5. TEA engine (:8002)

Stateless techno-economic analysis behind the platform's `/api/v1/tea` bridge. JWT-authenticated.

| Feature | API | Status | Source |
|---|---|---|---|
| TEA compute (CAPEX, OPEX, LCOP), co-product credit, input-quality flags | `POST /compute` | **Tested**. Runs OpenPyTEA 3.0.0, which is installed; a labelled `engine="stub"` path exists for CI. The docstring's "TODO: wire API" is stale: the real path is wired. | `compute/openpytea_runner.py`, `integrity.py`; `test_tea_engine`, `test_tea_bridge` |
| Regulatory regimes by pathway | `GET /regime/{fuel_id}`, `GET /regimes` | **Tested** (the regime fork in compute) | `regimes.py`; `test_tea_engine` |
| LCA | `POST /lca/compute` | **Unverified** (the platform only tests reading a stored LCA value) | `lca.py`; `test_economics_snapshot` |
| Certification gate | `POST /certification-gate/{fuel_id}` | **Unverified** | `routes/tea.py` |
| Monte Carlo | `POST /monte-carlo` | **Tested** | `routes/tea.py`; `test_tea_engine` |
| Sensitivity | `POST /sensitivity` | **Unverified** | `routes/tea.py` |
| Escalation, CEPCI, FX governance, mass balance | internal | **Tested** | `escalation.py`, `cepci_extension.py`; `test_tea_escalation_seam`, `test_tea_fx_governed`, `test_tea_mass_balance`, `test_tea_equipment_spec` |

## 6. PF engine (:8001, sibling repo)

The Gabillon project-finance engine. It keeps its run log in PostgreSQL (role `gex_engine`), and reads fuels from the platform with no fallback.

| Feature | API | Status | Source |
|---|---|---|---|
| Bankability gate evaluation (rules 4.8.0) | `/api/v1/bankability/{evaluate,evaluate/persona,evaluate/abac,gates,rules,regression/check}` | **Tested** | `core/bankability_engine.py`; `test_bankability_gates` |
| CFADS, drawdown, waterfall, lifetime model, covenants | `/api/v1/model/*` (11 endpoints) | **Tested** | `core/cfads.py`, `waterfall.py`, `debt/`; `test_model_invariants`, `test_cfads_multi_currency`, `test_debt_sculptor_characterization` |
| Contract–debt coverage | internal | **Tested** | `core/coverage`; `test_contract_debt_coverage` |
| Gabillon curves: calibrate, spot, term, forward, seasonal, decomposition, model card, runs | `/api/v1/pricing/*` (20 endpoints) | **Tested** | `core/gabillon.py`, `pricing/gabillon`, `core/model_governance.py`; `test_gabillon`, `test_tenor_label` |
| Offtake value, portfolio roll-up | `/pf/offtake/value`, `/pf/offtake/portfolio-rollup` (`/rollup` is a deprecated alias) | **Tested** | `pricing/offtake`; `test_offtake` |
| Run log in PostgreSQL, fuel catalogue | internal | **Tested** | `test_run_log_and_fuels` |
| JWT fail-closed | all | **Tested** | `auth/`; `test_gex_jwt_fail_closed` |
| Example project | `GET /api/v1/model/examples/green-h2-project` | **Placeholder** (sample data) | `api/routes_model.py:378` |

`deal_engine/` (in the platform tree) is dormant: no caller and no launch entry.

## 7. Planned and open work

| Item | State | Reference |
|---|---|---|
| Delivery SETTLED; title on payment in full | Not built (Step 3 stopped before SETTLED) | G-27 |
| Partial acceptance of a cargo by quantity | Out of scope | G-26 |
| Typed delivery, title and payment clauses on market trades | Market trades carry free text only | G-24 |
| Legs/flows for swaps; positions and swaps | Partly built (order book); swaps not built | G-07, G-09 |
| Sanctions / blacklist screening | Not built | G-10 |
| Amortising and step-up schedules | Not built (take-or-pay and novation are built) | G-11 |
| Token passport view, cash-flow bridge, policy simulator (CCfD), transition gate / asset slices | Absent or thin | G-14 – G-17 |
| GreenMesh economics (netback, IRR, swaps) | All decisions E1–E9 made; code waits on the certifier's pre-assessment of a Phase 1 pack (E8) | `docs/GREENMESH_ECONOMICS_DECISIONS_E1_E9.md` |
| Netting (FlowFusion) | Phase 3 | GreenMesh brief |
| Scheme registry payloads (CertifHy, ISCC, UDB) and inbound checks | No public spec found yet | Phase 2 Step 6 |
| SSE event stream | Deferred (returns 501) | `routes_events.py` |
| Live reviewer appointments | None assigned yet, so nothing can be verified | §4.2 |
| Mandatory party signatures; live ledger anchor | Built and switched off | `REQUIRE_PARTY_SIGNATURE`, `LEDGER_ANCHOR_BACKEND` |
| Unguarded SQLite reads | Still in `lineage`, `next_best_action`, `marketplace_analytics` (`adjacency` has one guard) | `.claude/CLAUDE.md` |
| Commitment countersign | Design decision needed (state transition or rewrite) | `core/css.py:272` |
| Screen menu for grant assessors and investors' advisers | They have no service type, so they reach Gates & Evidence only as an EXECUTIVE | §4.2 |

## 8. Caveats

- "Unverified" means no direct test was found. It does not mean the feature is broken.
- Frontend screen tests cover 15 of the 67 distinct menu screens. Most screens have no frontend test.
- Test counts move. Re-measure before quoting them. A skip is not a pass: the skip reasons are listed in §1.
