# One contract record — Phase 0 report

JML's prompt of 5 Nov 2026 ("GEX — One contract record"). Phase 0 is a report only: no code and no
migration were changed. Every statement below was read from the tree on 2026-11-05. Where a count
is given, it was measured.

---

## 0. Baseline

| Suite | Result | How |
|---|---|---|
| PF engine | **275 pass** | `gex_pf_engine/micro_service/bin/python -m pytest tests -q` |
| Platform | **1307 pass, 15 skip, 0 fail** (3 min 50 s) | `backend/venv/bin/python -m pytest tests/ -q -rs`, both URLs exported, run alone |

The prompt gave 1304 / 15 as the baseline. The tree has since moved to 1307, which matches CLAUDE.md's 2026-11-05 note. The 15 skips were read with `-rs`: 7 auth-store-isolation (no SQLite path on postgres), 1 empty evidence archive, and 7 plant-builder SEC.

---

## 1. Inventory

Format: file:function — route — screen — tests.

### 1.1 `project_contract`, `project_contract_event` (078)

**Writers**
- `core/contract_tokens.py`:`contract()` inserts the (project, kind) row. `append()` adds one hash-chained event. `record_versions()` adds a VERSION for each kind whose terms changed.
- `api/v1/routes_bankability_proxy.py:1409` (card save, `POST /api/v1/bankability/terms`) calls `record_versions`.
- `api/v1/routes_contract_tokens.py`:
  - `set_counterparty`: `PUT /api/v1/contract-tokens/{p}/{kind}/counterparty`. It runs `UPDATE project_contract`, then appends COUNTERPARTY_SET and then DISPUTED.
  - `confirm`: `POST …/confirm` appends CONFIRMED, then `verify_by_counterparty` (`routes_bankability_proxy.py:1626`) writes VERIFIED rows in `bankability_evidence`.
  - `dispute`: `POST …/dispute` appends DISPUTED.

**Readers**
- `routes_bankability_proxy.py:734` `_load_terms`, through `engine_terms` and `confirmed_terms`. This is the **only path to the gate engine**. If the read fails, no terms reach the engine.
- `routes_contract_tokens.py`:`list_tokens`, `GET /api/v1/contract-tokens/{p}`.
- `scripts/export_gex_process.py`, `export_twelve_gates.py` and `preflight_reviewer_appointment.py` read the constants (`FIELD_KIND`, `CONTRACT_EVIDENCE`), not the tables.

**Screen:** `features/executive/ContractTokensPanel.tsx`, mounted in `ProjectReportPage` (`/project-report`).

**Tests:** `test_contract_tokens_pg.py` (8), `test_commitment_terms.py`. There is **no frontend test for `ContractTokensPanel`.**

**Related store, not in JML's table:** `commitment_terms` (058) holds the owner's cards as typed. It is the input that `record_versions` reads, and the "raw" side of `engine_terms`. It is a fourth place where contract terms live (see Q9).

### 1.2 `contracts`, `matches`, `offers`, `rfqs`, `tokens`, `capacities` (036, 063)

**`core/market_engine.py`** is the sole writer of `offers`, `rfqs`, `matches`, `contracts` and the market's token moves. It runs on a PLATFORM_ADMIN connection after authorising the Party.
- `open_offer` / `withdraw_offer`: `POST /api/v1/market/offers/{id}/open|withdraw`.
- `create_rfq` / `transition_rfq`: `POST /market/rfqs`, `/rfqs/{id}/status`.
- `create_match`: `POST /market/matches`.
- `run_matching`: `POST /market/matching/run`. It returns 409 `AUTO_MATCHING_SUSPENDED`.
- `accept_match` / `decline_match`: `POST /market/matches/{id}/accept|decline`. When both sides have accepted: match `accepted`, offer `MATCHED`, RFQ `matched`, token RESERVED→MATCHED. **It does not create a contract.**
- `create_contract`: `POST /market/contracts`. This is a separate, later call by either party. It needs `delivery_terms` and `payment_terms` as free text, and writes `contracts`.
- `create_settlement` / `confirm_settlement`: `POST /market/settlements`, `/settlements/{id}/confirm`. They write `settlement_events`. Confirmation moves the token MATCHED→SETTLED and hands title to the buyer.
- Read functions: `offer_listings`, `rfq_listings`, `my_rfqs`, `my_matches`, `my_contracts`, `trail_for` (`GET /market/listings/*`, `/rfqs/mine`, `/matches/mine`, `/contracts/mine`, `/trail/{correlation_id}`).

**Legacy routes that delegate to the engine**
- `api/v1/contracts_sqlite.py`: `/api/v1/contracts/*`. Its `_visible` joins `capacities ON c.project_id = p.id`.
- `api/v1/trader_rfqs.py`: `/api/v1/trader/rfqs/*`.
- `api/v1/matching_sqlite.py`: `/api/v1/matching/*` and the buyer mandates.
- `api/v1/marketplace_sqlite.py`: `/api/v1/marketplace/offers*`. Offer creation happens here.
- `api/v1/settlement_events.py`: `/settlements*`.

**Capacity and token writers**
- `api/v1/capacity_sqlite.py`:`create_capacity`, `/api/v1/capacities/`.
- `api/v1/tokens_sqlite.py`:`/api/v1/tokens/`, which mints tokens and handles `POST /{id}/transition`.

**Other readers**
- `api/v1/lineage.py`: `/lineage/token/{id}`, `/lineage/project/{id}`.
- `api/v1/marketplace_analytics.py`: `offers`.
- **`api/endpoints/finance.py:231` `get_contracts`, `/api/v1/finance/contracts`.** It reads `contracts` out of **SQLite** (`sqlite3.connect(settings.SQLITE_DB_PATH)`), checks no switch, and turns any error into `[]`. This read is missing from CLAUDE.md's list of unguarded reads (§7.1).

**Screens (routes and `api.ts` calls)**

| Menu label | Path | Component | Calls |
|---|---|---|---|
| Market Discovery | `/market-discovery` | `trader/MarketDiscoveryPage` | `marketAPI.offerListings`, `rfqListings`, `myRFQs`, `proposeMatch`, `commodities` |
| RFQs | `/rfqs` | `trader/RFQManagementPage` | `marketAPI.createRFQ`, `myRFQs`, `setRFQStatus` |
| **RFQ Management** | `/trader-dashboard` | `trader/TraderDashboardPage` | `marketAPI.myMatches`, `acceptMatch`, `declineMatch`, `createContract`, `myContracts`, `myRFQs` |
| Your Matches | `/matching` | `matching/MatchingPage` | `marketAPI.myMatches`, `acceptMatch`, `declineMatch` |
| Contracts | `/contracts` | `contracts/ContractsPage` | `contractsAPI.list` (`/api/v1/contracts/`) |
| Delivery & Settlement | `/settlement` | `settlement/SettlementPage` | `contractsAPI.list` |
| Evidence Lineage | `/finance/lineage` | `finance/LineagePanel` | `marketAPI.myContracts`, `trail` |
| — | `/marketplace` | `marketplace/MarketplacePage` | `marketAPI.myContracts`, `myMatches`, `projectEconomics` |
| — | `/capacity` | `capacity/CapacityPage` | `marketAPI.myMatches`, `offerListings` |
| — | `/tokenisation` | `tokenisation/TokenisationPage` | `capacitiesAPI`, `tokensAPI` |
| — | dashboard | `dashboard/DashboardPage` | `capacitiesAPI`, `offersAPI`, `matchingAPI`, `tokensAPI` |
| Revenue & Offtake | — | `finance/RevenueOfftakePage` | `financeAPI.getContracts` (the SQLite read above) |

Note: the menu label "RFQ Management" opens `TraderDashboardPage`, while `RFQManagementPage` is labelled "RFQs". The prompt's "RFQ Management" is taken to mean both.

**Tests**

Backend:
- `test_market_chain.py`, `test_market_chain_pg.py`, `test_marketplace_slice.py`, `test_marketplace_records_pg.py`, `test_token_lifecycle.py`
- the PostgreSQL-only guards in `test_architecture_guardrails.py`

Frontend:
- `trader/__tests__/MarketScreens.test.tsx`, `CounterpartiesPage.test.tsx`

### 1.3 `tb_*` (036, 064, 065)

- **Writers:** `trading_book/api.py` (`/api/v1/trading-book/*`), which covers assets, counterparties, indices and their history, JTI contracts (`/contracts/fixed-price`, `/contracts/index-linked`), `/contracts/{id}/status`, and project-finance links. Also `trading_book/seed.py`, `scripts/migrate_marketplace_slice.py`, and `scripts/load_marketplace_unverified_20261023.py` (`tb_commodity.registry_pathway`).
- **Code for the 065 model:** `trading_book/{conventions,terms,validation,canonical,pricing}.py`. Nothing writes `tb_terms`, `tb_leg`, `tb_flow`, `tb_order`, `tb_rfq`, `tb_fill`, `tb_contract_version` or `tb_contract_version_token` outside the tests.
- **Readers:** `trading_book/api.py` (`/projects/{id}/cashflows`, `/projects/{id}/contracts`, `/contracts`) and `trading_book/cashflows.py`. `market_engine.commodities` and `project_economics` read `tb_commodity`.
- **Screen:** `trader/CounterpartiesPage` (`tradingBookAPI.counterparties`).
- **Tests:** `test_trading_terms.py` (25), `test_trading_terms_pg.py` (8), `test_trading_book_api.py`, `test_trading_book_pg.py`, `test_tail_slices.py`.

---

## 2. Field mapping: `FIELD_KIND` → the 065 terms schema

Key:
- **Q**: `tb_terms.quality_spec`
- **P**: the party, meaning `tb_counterparty` on the leg (payer/receiver) or the contract's confirming party
- **L/F**: leg/flow
- **C**: a clause attribute. This needs a new home, proposed below.
- **E**: an event, not a term
- **X**: does not map cleanly

### Proposed additions (Phase 1/2, not built)

- **`tb_clause`**: `terms_id`, `clause_type`, `seq`, `attrs jsonb`. Frozen with its terms (the 065 trigger extended), and included in the canonical JSON and `terms_hash`. Clause types:
  - `commitment` (form, take-or-pay floor)
  - `conditions_precedent` (list, satisfied, longstop)
  - `damages` (delay and performance LD caps)
  - `force_majeure` (definition ref)
  - `change_in_law` (allocated)
  - `credit` (investment grade, credit support)
  - `performance` (guaranteed capacity, availability, completion date, guaranteed specification)
  - `price` (mechanism; the EPC lump sum)
  - `declaration` (technical and model, §3)
- **`tb_contract`** gains:
  - `kind` (`trade | offtake | ppa | supply | epc | licence | technical | model`)
  - `project_id` (FK `projects`; nullable only for `trade`)
  - `confirming_company_id` (the registered counterparty, as `project_contract` has it today)
- **`tb_terms`**:
  - `commodity_id` and `settlement` become nullable, with a CHECK that they are present for `trade | offtake | ppa | supply`.
  - A `profile` column (`complete | card`) selects the validation rules (Q3).
- **`tb_commodity`**: power (MWh), CO₂ (t) and the feedstock codes. These are reference data, so JML names the codes.

### offtake (card `offtake`)

| Field | Home | Note |
|---|---|---|
| counterparty_name | P | The receiver of the product leg (`tb_counterparty.name`). **X**: today the owner types a name *and* registers a company separately; the two can disagree. |
| counterparty_role | C `parties.role` | |
| buyer_investment_grade, credit_support | C `credit` | `credit_support` only refers to a third-party instrument. Confirming it verifies nothing (unchanged rule). |
| commitment_form, take_or_pay_pct | C `commitment` | Take-or-pay is not a tolerance: a missed lift creates a payment, so it is not `tolerance_min_pct`. |
| contracted_tonnes_per_year | F | Physical flows on the product leg, one per contract year. **X**: the card value covers *all buyers* (engine comment, `bankability_engine.py:738`). A contract record is bilateral (Q2). |
| tenor_years | derived from F | First `period_start` to last `period_end`. **X** for parity: the derived value can be fractional while the card holds a number (Q4). |
| price_mechanism | C `price` | **X**: the card holds no price. FIXED and INDEX_PLUS_PREMIUM could become `fixed_cash`/`float_cash` flows only if a price exists. COST_PLUS, FLOOR_CAP and OTHER have no flow type. |
| cps_satisfied, conditions_precedent, longstop_date | C `conditions_precedent` | |
| first_delivery_date | F | The first physical flow's `period_start`. |
| delay_ld_cap_eur | C `damages` | |
| product_spec_standard, certification_scheme, compliance_regime | Q | |
| fm_definition_ref | C `force_majeure` | |
| change_in_law_allocated | C `change_in_law` | |
| planned_output_tonnes_per_year | technical, §3 | |

### epc (card `epc`)

| Field | Home | Note |
|---|---|---|
| contractor_name | P | The receiver of the payment leg. Same name-versus-company note as the offtake. |
| contracting_model | C `price` | |
| contract_price_eur | C `price` | **X**: an EPC is works, not a commodity. A `fixed_cash` flow needs quantity × unit price, and `tb_unit` has no "lot". Recommended: a clause now; milestone payments later as CAPEX through `tb_project_finance_link`. |
| guaranteed_completion_date, guaranteed_capacity_tonnes_per_year, expected_availability_pct, guaranteed_product_spec | C `performance` | |
| delay_ld_cap_eur, performance_ld_cap_eur | C `damages` | |
| fm_definition_ref | C `force_majeure` | |
| counterparty_insolvent | **E** | An adverse fact: it applies at once, and clearing it needs a confirmation. |
| contingency_eur, sponsor_support_eur | model, §3 | |

### supply and ppa (card `supply`)

| Field | Kind | Home |
|---|---|---|
| feedstock_contracted_tonnes_per_year, feedstock_tenor_years | supply | F (physical, commodity = feedstock) and derived, as for offtake |
| co2_source_eligible, certification_scheme | supply | Q |
| fm_definition_ref | supply | C `force_majeure` |
| certification_suspended | supply | **E** |
| power_contracted_mwh_per_year, power_tenor_years | ppa | F (physical, MWh, commodity = power) |
| power_meets_certification | ppa | Q |
| support_or_ppa_revoked | ppa | **E** |
| feedstock_required_tonnes_per_year, power_required_mwh_per_year | technical | §3 |

### licence

No card field belongs to it. Today a licence token holds a counterparty and confirmations only: `confirm` allows `licence` with no version. In the new model it is a contract of kind `licence` with clauses only (royalty and process guarantee when someone records them). Its confirmation verifies `technology_licensor_term_sheet` and `technology_licence_process_guarantee`, as today.

### technical and model

- **technical:** the `schedule` card (all seven fields), plus planned output and the two requirements.
- **model:** the `model` card (four fields), plus contingency and sponsor support.
- Both are **C `declaration`** (§3).

### Why the projection is also stored

The card has no price, the offtake volume is an aggregate, and EPC is works. So a card-derived contract can never pass 065's V01–V03 (two legs, priced payment flows). The proposal (Q3):
- Card-derived versions carry `profile = 'card'`. Legs and flows are built where the card supports them and are otherwise absent.
- The version stores the exact `{card.field: value}` it was made from (`card_projection`, covered by the hash).
- The engine reads that projection. A test pins `derive(structured) == projection` for every mapped field.

---

## 3. technical and model in the same record

They are the producer's own declarations. They have no bilateral trade, no payer, no receiver and no cashflow.

- **Contract:** `tb_contract` row with `kind = technical | model` and `project_id`. `confirming_company_id` stays NULL: the confirming party is a **role**, the reviewer appointed for G5 or G8, resolved at confirmation time by `is_appointed_reviewer`, as today.
- **Versions:** `tb_contract_version` → `tb_terms` (`profile = 'card'`, no commodity, no settlement, **zero legs**) → `tb_clause` rows of type `declaration`, one per field. The values are typed in `attrs`.
- **Events:** the same chain as every other contract (§4): VERSION, CONFIRMED by the reviewer, DISPUTED.
- **Refusals:**
  - COUNTERPARTY_SET is refused for these kinds (`REVIEWER_CONFIRMS`, unchanged).
  - The owner's company cannot confirm (`OWNER_CANNOT_CONFIRM`).
  - GEX never confirms.
- **Validation:** a `declaration` profile that requires zero legs, so V01–V13 do not apply.
- **RLS:** party visibility in 065 is computed from legs (`app_tb_terms_party`), so a contract with no legs would be invisible to everyone but its owner. Contracts with a `project_id` therefore also need 078's rule: owner, a company with project access, or GEX. `trade` contracts keep party-only visibility (Q5).

---

## 4. One event chain per contract

### What exists

- **078:** one chain per (project, kind). `event_hash = sha256(json.dumps({contract, seq, type, terms_sha256, actor, company, note, prev}, sort_keys=True))`, where `contract` is the 078 **bigint id**. `chain_intact()` recomputes it.
- **078's terms hash:** `terms_sha256 = sha256(json.dumps({card.field: value}, sort_keys=True, default=str))`. This is not the 065 canonical form.
- **065:** no event table. `tb_contract.token_ref` (unique, fixed once set) and `tb_contract_version.token_event_ref` (fixed once written; required before version 2) are both NULL by design.

### Gaps in 078's chain to close in the fold

1. `at` is outside the hash, so a timestamp can be rewritten without breaking the chain.
2. `chain_intact` never checks `terms_json` against `terms_sha256`, so the stored terms can be rewritten while the chain stays "intact".
3. `append()` reads `max(seq)` and inserts on a separate connection. A concurrent pair fails the `UNIQUE (contract_id, seq)` constraint with a 500.
4. `set_counterparty` runs three separate transactions (the UPDATE, then COUNTERPARTY_SET, then DISPUTED). If it fails after the first commit, the counterparty is changed **with earlier confirmations still standing**.

### Proposal

**New table `tb_contract_event`** (append-only, FORCED RLS, REVOKE UPDATE/DELETE/TRUNCATE from `gex_app`):

- `contract_id`, `seq`, `event_type`, `version_id`, `terms_hash`, `actor`, `company_id`, `note`, `at`
- `prev_hash`, `event_hash`, `hash_scheme`, `legacy_contract_id`
- (Phase 5) `signature`, `signature_scheme`, `signer_key_ref`. These sit beside the hash, not inside it, because the signature covers `event_hash`.

**Event types:** COUNTERPARTY_SET, VERSION, CONFIRMED and DISPUTED as today, plus `CREATED_FROM_MATCH`, `STATUS_CHANGED`, `ADVERSE_FACT_REPORTED` and `ADVERSE_FACT_CLEARED`.

**Two hash schemes, one chain:**
- `hash_scheme = '078'` for migrated rows. The hash is recomputed exactly as today, with `legacy_contract_id` standing in for `contract`. Hashes, order, actors and timestamps are copied verbatim.
- `hash_scheme = '2'` for every new event. The hash covers canonical JSON of `{schema: 2, contract_ref, seq, event_type, version, terms_hash, actor, company, note, at (UTC ISO), prev}`.
- The first new event on a migrated contract takes the last migrated `event_hash` as its `prev`, so each contract has one unbroken chain. `chain_intact` dispatches by scheme. A test proves that every migrated chain verifies both before and after the fold.

**Terms hash:**
- Migrated versions keep the 078 `terms_sha256` as `legacy_terms_sha256` (the compatibility API's `confirm` still names it), and also get the 065 canonical `terms_hash`, extended to clauses and the projection.
- The compatibility API returns whichever hash the version's CONFIRMED event names.

**The 065 token columns.** There will be no HTS token (rule 2), so the columns are reinterpreted rather than dropped:
- `token_ref` = the contract's genesis `event_hash`
- `token_event_ref` = the `event_hash` of the VERSION event that carried that version
- The existing triggers then enforce what JML decided on 23 Oct: one record for the contract's life, and every version anchored in its chain. Internal names keep "token".

**Exact semantics the engine view must keep.** `confirmed_terms()` is **not** "the latest version, if confirmed". It walks the events in order: each CONFIRMED sets "current" to the version named by its `terms_sha256`, and each DISPUTED clears it. A confirmation of v1 therefore still stands after v2 is recorded unconfirmed. `engine_terms` then holds back only the fields whose card value differs from v1's.

`v_engine_contract_terms` must reproduce this exactly: per (project, kind), the version named by the last CONFIRMED event with no DISPUTED after it. Adverse facts are read from the raw card, as `engine_terms` does today, until Phase 3 moves them onto events. Doing it earlier would change behaviour inside a parity phase.

---

## 5. Supply side

**The coupling.**
- `capacity_sqlite.create_capacity` mints `capacities.id = uuid4()`, and `CapacityCreate` has no project field.
- 036's policy is `capacities_tenant_isolation FOR ALL USING (… app_company_can_see_capacity(id, me))`, and that function reads `id` as a project id. With no `WITH CHECK`, the USING clause is also the INSERT check. Every insert by a producer running as `gex_app` is therefore refused by RLS.
- Downstream, `tokens` (`capacity_id`), `offers` and `matches` chain their policies through the same function. `market_engine.seller_company(capacity_id)` (`:136`) and `contracts_sqlite._visible` (`JOIN capacities ON c.project_id = p.id`) read the same assumption.
- Also: `create_capacity` takes `user_id` as a **query parameter defaulting to "system"** and writes it into `capacity.created`. The event's actor is not the caller.

**Does the 065 order model remove it?** For orders and contracts, yes:
- `tb_order.owner_id` → `tb_counterparty.company_id` makes ownership a company.
- `tb_flow.asset_id` → `tb_asset.project_id` (064) ties the product to a project.
- Nothing in the order path needs `capacities`.

**It survives** for the capacity tokens that a contract refers to (`tb_contract_version_token → tokens`, decision 3), and in every 036 policy. Moving the market onto `tb_order` alone would leave `/capacity`, `/tokenisation` and the token lifecycle broken as they are now.

**Proposed fix (Phase 1, own migration):**
1. Add `capacities.project_id text NOT NULL REFERENCES projects`. Backfill `project_id = id` where `id` is a project id, and report every other row without guessing (M5's rule).
2. Rewrite the four 036 policies on `project_id`, splitting each into read and write policies with `WITH CHECK`. The write requires that the caller's company owns the project.
3. `create_capacity` takes `project_id`, refuses unless the caller owns that project, and takes the actor from the token. `seller_company` and `contracts_sqlite` read `capacities.project_id`.
4. M5's other columns (`commodity_id`, `asset_id`, `owner_id`, period, quantity, unit) go in the same migration.

---

## 6. Data

Measured 2026-11-05 by one read-only query as `gex_user` (BYPASSRLS, so every tenant counts). Head **082**.

| Store | Rows | Detail |
|---|---|---|
| `project_contract` | **4** | all `proj_TEST_gates_reference`: offtake, supply, epc, technical. No counterparty registered on any of them. |
| `project_contract_event` | **4** | one VERSION each, actor `TEST_FIXTURE_COMPREHENSION`, written 2026-10-28 17:42 UTC. **0 COUNTERPARTY_SET, 0 CONFIRMED, 0 DISPUTED.** |
| `commitment_terms` | 3 | the same fixture's three cards. **No real project has a card.** |
| `commitment_terms_events` | 0 | |
| `contracts`, `matches`, `offers`, `rfqs`, `tokens`, `buyer_mandates`, `settlement_events`, `deliveries` | 0 each | |
| `capacities` | 5 | `proj_bremen_h2`, `proj_lehavre_eng`, `proj_rotterdam_nh3`, `proj_sansebastian_emethanol`, `proj_wales_saf`. **Every id is an existing project id**, so §5's backfill is clean for all five. |
| `tb_commodity` | 5 | the 065 seed |
| every other `tb_*` | 0 | asset, counterparty, restriction, index definition and history, contract and both JTI children, finance link, terms, leg, flow, rfq, order, invitee, order event, fill, version, version token |
| `projects` | 16 | incl. `proj_TEST_gates_reference` and `proj_TEST_fortaverde_pecem` |
| `bankability_evidence` | 124 | 32 are `TEST_FIXTURE_COMPREHENSION` |

**FortaVerde (Pecém) TEST project:** no contract record, no card, no market row.

**The four chains were re-verified outside the app.** Each `event_hash` recomputes from 078's formula, `prev_hash` is NULL, and each `terms_sha256` matches its `terms_json`. The four records hold 7, 2, 3 and 2 fields.

**What this means for the phases**
- Phase 2's data migration is **4 contracts and 4 events, all TEST**.
- On every project, `confirmed_terms()` is `{}` today, so no real project's gate figures depend on a contract record yet.
- The parity test is still mandatory. It is strong on state and gates for all 16 projects. The fixture's `--verify` is the only check that exercises held-back fields.
- The market and `tb_*` phases convert nothing: M2 and M3 run on empty tables, as M1 did.

Docker VM disk at the time: 7.8 GB, 1.8 GB free (76 %). That is under the ~2 GB line, so prune before any image build.

---

## 7. Found in passing (not fixed: Phase 0 changes nothing)

1. **`/api/v1/finance/contracts` reads `contracts` from SQLite** (`api/endpoints/finance.py:21,231`), checks no switch, and swallows errors into `[]`. `RevenueOfftakePage` therefore always shows an empty list, and it would show the SQLite copy if one existed. It is not in CLAUDE.md's list of unguarded reads. Fix it in Phase 3, with the screens.
2. `create_capacity` takes the actor from a query parameter (§5).
3. 078's chain gaps (§4, items 1–4). Item 4 (a counterparty changed while confirmations survive) is the one with consequences.
4. In `confirm`, the CONFIRMED event and the evidence it verifies are written in two transactions, in two stores. If the evidence write fails, the result is a confirmation with no VERIFIED evidence, and the call returns 500.
5. 078's RLS lets **any** project company INSERT any event type. Only the route decides who confirms. A project party writing directly to the database could insert a CONFIRMED row. That cannot happen through the API, but the database does not enforce it. The fold can add a `WITH CHECK` that limits CONFIRMED/DISPUTED inserts to `confirming_company_id` or an appointed reviewer's company.
6. There is no frontend test for `ContractTokensPanel`.
7. **The comprehension fixture's `--remove` predates 078.** Its `DELETES` (`scripts/load_comprehension_test_project.py:168`) clears `commitment_terms` and then `projects`, but not `project_contract_event` or `project_contract`, both of which reference `projects`. This was found by reading and **not run**. `--remove --execute`, and `--execute` (which removes first), should now fail on the foreign key. The loader also never writes the four VERSION events, so a reload would not recreate them. Phase 2 must fix both: delete the record's rows by project id, and write versions through the same path a card save uses.

---

## 8. Open questions, each with a recommended answer

**Q1. DECIDED by JML, 2026-11-06.** This supersedes the "Proposed additions" list in §2. 065 stays the one contract schema. Everything below comes as new migrations from 083, and no second contract table is created.

*New tables:*
- **`tb_sub_leg`**: one row per buyer within a version's terms. It holds `terms_id`, `seq`, the buyer (`tb_counterparty`), `sub_leg_hash` and `rank` (for tranching). Each buyer's product and payment legs belong to it through **`tb_leg.sub_leg_id`**. **V01 becomes "exactly two legs per sub-leg"**, so a bilateral trade is a frame with one sub-leg.
- **`tb_clause`**: shared or per-sub-leg clauses, frozen with the terms and included in the hash.
- **`tb_contract_event`**: one append-only, hash-chained event log per contract (§4). It includes `NOVATION`, and a confirmation names the `sub_leg_id` it covers.

*New columns:*
- **`tb_contract`**: `kind` (`trade | offtake | ppa | supply | epc | licence | technical | model`), `project_id`, and `confirming_company_id` (single-party kinds only: a frame's buyers sit on their sub-legs).
- **`tb_terms`**: `profile` (`complete | card`), `shared_hash`. `commodity_id` and `settlement` become nullable for legless kinds.
- **`tb_contract_version.terms_hash`**: the Merkle root over `shared_hash` and every `sub_leg_hash`.

*Visibility:*
- As decided in Q5. (The first draft of this answer let GEX read every sub-leg; Q5 corrects that to follow R0P.)

*Cost:* the 065 tests that assume exactly two legs per terms are rewritten to "per sub-leg". Their single-buyer behaviour is unchanged.

**Q2. DECIDED by JML, 2026-11-05: one frame, per-buyer confirmation.**
- A project's offtake is **one multilateral record** (the frame, which works as the cap table). It holds the plant, the total output and the **shared terms**: specification, certification scheme, force majeure, change in law.
- It has **one sub-leg per buyer**: volume per period, price, tenor, take-or-pay and credit.
- **Hashing:** each sub-leg and the shared terms are hashed separately. The version hash is a Merkle root over those parts, and that root is what is anchored on the ledger.
- **Confirmation:** each buyer confirms its own sub-leg's hash plus the shared-terms hash. **Only the buyers whose part changed re-confirm.** A change to the shared terms, or an output cut that leaves the sub-legs above the frame, withdraws every affected confirmation.
- **Visibility:** each buyer reads the shared terms and its own sub-leg. The other sub-legs appear only as a hash and a volume share, which keeps the 23 Oct anonymity decision.
- **Certificates:** each sub-leg refers to the certificate tokens delivered to its buyer (`tb_contract_version_token`). Title passes at settlement and the buyer redeems them as holder. The record itself is not transferable (rule 3).
- **Engine:** coverage is the sum of the confirmed sub-legs, and credit and concentration are read per buyer. This is a rules change, so the exact rule needs JML's word.
- **Phasing:** Phase 2 keeps one record per project for parity, and Phase 3 builds the frame.
- **Transfer (Q13, decided):** a sub-leg changes hands by `NOVATION` only, with no token.

The question as first put, kept for the record: a project's offtake is an aggregate over all buyers (the card), while a contract record is bilateral. How does "a traded offtake exists exactly once" hold?
Recommended:
- **Phase 2:** keep one `offtake` record per project (the card's aggregate) for exact parity.
- **Phase 3:** a project's offtake becomes the **set** of its `offtake` contracts, one per buyer, each confirmed by its own counterparty. A market contract for the project's output *is* one of them (`kind = offtake`, `project_id` = seller's project), not a second record. The engine then sums the confirmed contracts' annual volume, and per-buyer fields are read per contract.

That is a rules change (PF engine minor version) and needs your word on how C-checks treat several buyers. Until then, a traded offtake is held back from the engine.

**Q3. DECIDED by JML, 2026-11-06: card profile plus projection.**
- Card-derived versions have `profile = 'card'`, with their own validation. Legs and flows are built only where the card supports them, and clauses hold the rest.
- Each version stores the exact `{card.field: value}` it was made from (`card_projection`), inside its hash. **The engine reads the projection.**
- A write-time check, pinned by a test, refuses any version whose structured terms and projection disagree on a field they share.
- `complete` (market trades) keeps V01–V13.
- **Phase 2:** the card offtake is a frame with one sub-leg holding the aggregate, as today.
- **Phase 3:** each buyer's sub-leg carries its own projection, and the engine sums them (Q2).

The question as first put, and the recommendation behind it: card-derived terms cannot pass V01–V03 (no price; EPC is works). How should they be stored?
Recommended:
- `profile = 'card'` with its own validation.
- Legs and flows are built only where the card supports them.
- The exact `card_projection` is stored on the version, inside the hash, and is what the engine reads.
- `profile = 'complete'` (market trades) keeps V01–V13 unchanged.

The alternative (derive the engine's fields from flows) puts parity at risk on `tenor_years` and the aggregate volume.

**Q4. DECIDED by JML, 2026-11-06: exact agreement, conservative derivation.**
- **Card contracts:** the structured terms are built from the projection, and the guard requires *exact* agreement.
- **Market contracts that reach the engine (Q7):** the projection is derived from the structured terms at write time, inside the hash the buyer confirms:
  - `first_delivery_date` = the first physical `period_start`;
  - `tenor_years` = whole contract years covered, rounded down;
  - `contracted_tonnes_per_year` = the **smallest** full-year quantity.
- A card field with no structured source stays absent, so its checks read UNRESOLVED.
- **No tolerance between the two representations.** The engine's 1 % tolerance stays a rule for comparing cards (C-checks) only.

The question as first put: when terms come from both sources, which wins for `tenor_years` and `contracted_tonnes_per_year`?
Recommended: the projection (what the counterparty confirmed), never a value recomputed from flows. A version is refused if the flows and the projection disagree beyond the existing 1 % tolerance.

**Q5. DECIDED by JML, 2026-11-06: who reads contract terms.**

| Who | Reads |
|---|---|
| Producer (project owner) | everything on its project's contracts |
| A buyer on a frame | the shared terms and its own sub-leg; other sub-legs only as a hash and a volume share (`security_invoker` view) |
| Lenders and capital providers with project access (not buyers) | everything |
| Appointed reviewers | only the kinds whose evidence falls in the gates they review (`abac.REVIEWER_GATES`) |
| GEX staff | state, chain and hashes; **no terms or prices** (R0P excludes contracts) |
| `trade` contracts with no project | the two parties only |

The buyer restriction applies **before** project access, because every buyer is also a project party (078's rule). RLS enforces the company rules (buyer restriction, party-only trades). The route enforces the role rules (reviewer scope, GEX), as it does for evidence. This is a change from today: through `/contract-tokens`, reviewers currently read every kind.

The question as first put: 078 lets every company on the project (lenders, reviewers) read the terms, while 065 lets only the parties read them.
Recommended:
- Project-bound contracts (`project_id` set): owner, project-access companies, GEX. This is 078's rule and what the gate readout needs.
- `trade` contracts: the parties only.

**Q6. DECIDED by JML, 2026-11-06: acceptance flow.**
1. **The proposal.** A proposal is an invited firm quote: a `tb_order` with `rfq_id` set, invitee = the other party. Creating it is the proposer's acceptance, recorded in `tb_order_event`.
2. **The other party's acceptance**, in one `SELECT … FOR UPDATE` transaction:
   - check status, validity, all-or-nothing and restricted pairs;
   - clone the terms, resolve payer and receiver, freeze and hash;
   - create the fill and the draft contract (v1, `pending_confirmation`, UNVERIFIED, `CREATED_FROM_MATCH`). T14 pins one fill under concurrent accepts.
3. **Clauses before acceptance.** Delivery and payment terms are clauses on the quote before acceptance. `POST /market/contracts` becomes a compatibility no-op that returns the existing contract.
4. **Phasing.**
   - Phase 1: kind `trade`, with `project_id` set for a project's output and one sub-leg. It never reaches the engine.
   - Phase 3: it joins the project's offtake frame as that buyer's sub-leg. An acceptance that would exceed the frame's output is refused.
5. **Token steps** (RESERVED → MATCHED → SETTLED) are unchanged.

The question as first put: two-sided acceptance in the order model. Today a match is proposed and then accepted by each side. 065 has no pending-match object: one acceptance creates the fill.
Recommended:
- A proposal becomes an **invited firm quote**: a `tb_order` with `rfq_id` set and the other party as invitee. Creating it is the proposer's acceptance, recorded in `tb_order_event`.
- The counterparty's accept creates the fill and the draft contract (`trade_status = pending_confirmation`, `verification_state = UNVERIFIED`, `CREATED_FROM_MATCH` naming the order or fill) in one `SELECT … FOR UPDATE` transaction.
- `delivery_terms` and `payment_terms`, now free text typed after the match, become clauses on the order's terms *before* acceptance, so nothing is typed after both sides agree.

**Q7. DECIDED by JML, 2026-11-06: TRADE_CONFIRM and the engine.**
1. **Four eyes on each side.** A contract moves from `pending_confirmation` to `confirmed` when both parties have confirmed. Each party's confirmation needs two distinct ACTIVE accounts of **that party's own company**, at least one EXECUTIVE. The initiator never approves, and GEX accounts are refused.
   - Today `wae.record_decision` checks only self-approval and double decisions. It gains company, role and GEX checks, scoped to `TRADE_CONFIRM`.
   - Each side's completed approval writes a `CONFIRMED` event naming the hash it confirmed.
2. **Phases 1–2.** A confirmed `trade` contract is a commercial record and never reaches the engine, even with `project_id` set.
3. **Phase 3.** As the buyer's sub-leg of the project's offtake frame, the buyer's `CONFIRMED` counts when:
   - the buyer is that sub-leg's counterparty;
   - it confirms the latest version's sub-leg hash and shared-terms hash;
   - no `DISPUTED` event follows it.

   The same refusals as `/contract-tokens/…/confirm` apply.
4. **Evidence.** That confirmation verifies `binding_offtake_contract_executed` (independence and document rules unchanged), and never a third-party instrument.

The question as first put: does a buyer's `TRADE_CONFIRM` count as the counterparty confirmation that reaches the engine?
Recommended: only when all of the following hold:
- the contract has a `project_id` and kind `offtake`;
- the confirming company is that record's registered counterparty;
- the CONFIRMED event names the latest version.

It then follows the same route and refusals as `/contract-tokens/…/confirm`. The four-eye approval is internal to each party and adds no GEX role.

**Q8. DECIDED by JML, 2026-11-06: the state mapping below.**
- **Offers:** DRAFT→draft, OPEN→open, MATCHED→filled, SETTLED→filled, WITHDRAWN→cancelled.
- **RFQs:** draft→draft, open→published, matched→closed, withdrawn→withdrawn, expired→expired, cancelled→withdrawn.
- **Matches:** pending→quote open, accepted→filled plus fill and contract, declined→quote cancelled, superseded→quote cancelled (the reason records what superseded it).

Any other value aborts the run. Today there are 0 rows to convert.

The question as first put: state mapping (no rows to migrate, but the M3 script needs a table).
Recommended:
- Offers: DRAFT→draft, OPEN→open, MATCHED→filled, SETTLED→filled (settlement belongs to the contract's lifecycle), WITHDRAWN→cancelled.
- RFQs: draft→draft, open→published, matched→closed, withdrawn→withdrawn, expired→expired, **cancelled→withdrawn** (065 has no `cancelled` RFQ state).

Any other value aborts the run.

**Q9. DECIDED by JML, 2026-11-06: what happens to the cards.**
- **Phase 2:** the card save and its VERSION are written in **one transaction**, and a failure is an error. Today `routes_bankability_proxy.py:1409` commits the card, then writes the version on another connection, and only logs a warning if that fails.
- **Phase 3:** the card becomes a view over the record: the latest version per kind, confirmed or not. An edit proposes a new version. The offtake card shows the shared terms and one panel per buyer's sub-leg.
  - `commitment_terms` and `commitment_terms_events` are retired, and the record's chain replaces the event log.
  - 058's UPDATE grant goes with the table.
  - The compatibility layer keeps `/bankability/terms` working until the frontend moves.

The question as first put: `commitment_terms` (the owner's cards).
Recommended:
- Phase 2: it stays the owner's input form, with every save still writing a VERSION.
- Phase 3: it becomes a view over each kind's latest version, so the typed card and the record cannot diverge. Its UPDATE grant (058) then goes.

**Q10. DECIDED by JML, 2026-11-06: adverse facts.**
- **Phase 2:** unchanged. They are read from the card, apply at once, and are cleared by confirmation.
- **Phase 3:** they become `ADVERSE_FACT_REPORTED` and `ADVERSE_FACT_CLEARED` events on the contract they concern, or on one **sub-leg** of a frame, so a buyer's insolvency drops only that buyer's volume.
- **Reporting:**
  - Who: the owner, the contract's counterparty, a lender with project access, or an appointed reviewer.
  - A document is required, and the report applies at once.
  - **A buyer reports only about its own sub-leg or the shared terms, never about another buyer.**
- **Clearing:** a document plus confirmations from two parties of different companies, neither being the reporter's company. That is the owner plus the confirming party, or a lender or reviewer when the confirming party is the one affected. GEX never clears one.
- **New fact:** buyer insolvency for offtake sub-legs is added in Phase 3.

The question as first put: adverse facts.
Recommended:
- Phase 2: unchanged (read from the raw card, applied at once).
- Phase 3: they become `ADVERSE_FACT_REPORTED` events, which any project party may report. Clearing one needs a confirmation by the party that would confirm the contract.

**Q11. DECIDED by JML, 2026-11-06: the outbox worker.**
- **Where it runs:** an in-process asyncio loop started at backend startup, active only when `LEDGER_ANCHOR_BACKEND != none`, waking every 30 s. `scripts/drain_anchor_outbox.py --once` handles repairs.
- **Claims:** `SELECT … FOR UPDATE SKIP LOCKED` with a lease, so with several backends a row is submitted by one worker only.
- **Duplicates:** a crash between the ledger's acceptance and the row update may duplicate a message. `verify_anchor.py` takes the first message carrying the event hash and reports the others.
- **Retries:** backoff of 1 min, 5 min, 30 min, 2 h, then 12 h. After 8 attempts the row is `FAILED` and shows on the GEX staff console. Anchoring never blocks the contract event.
- **Role:** a new **`gex_anchor`** role (082's pattern) holds SELECT on the outbox and column-level UPDATE on `status`, `attempts`, the ledger reference and `anchored_at`, and nothing else. Its password lives in `files/.env`. Restores need the role first (`setup_postgres_rls.sql`, restore step 5).

The question as first put: outbox worker (Phase 4) without a new launchd job.
Recommended: an asyncio drain loop started in the backend's startup, active only when `LEDGER_ANCHOR_BACKEND != none`. The same loop works under Docker, and `scripts/drain_anchor_outbox.py` gives a manual run. The existing `com.gex.expiry-sweep` job could call it instead, but that job runs only on this Mac.

**Q13. DECIDED by JML, 2026-11-06: novation, no token.** Rule 3 stands: the record is not a transferable asset, and no ERC-3643 or other security token is built.

A sub-leg changes hands by a `NOVATION` event on the frame's chain, built in Phase 3 with the frame. The event is valid only when all three parties have confirmed it: the producer, the outgoing buyer and the incoming buyer. Each confirmation names the event hash and may carry a party signature from Phase 5.

*Refused:*
- an incoming buyer that is not ACTIVE and vetted;
- an incoming buyer that is the producer's own company, or a restricted counterparty pair;
- any GEX account as a party;
- a novation of a sub-leg that has an open dispute.

*Effects:*
- Until all three have confirmed, the outgoing buyer's confirmed terms keep reaching the engine.
- Once the novation is complete, the incoming buyer is the sub-leg's counterparty and its volume reaches the engine at once, because the incoming buyer's confirmation of the novation also confirms the sub-leg's current terms.
- Certificates already delivered stay with whoever holds them.
- Lenders' consent is recorded as a document on the event, not checked by GEX.

Tokenised sub-legs are not on the roadmap. Reopening them needs counsel first.

The question as raised (JML 2026-11-05: ERC-3643 or security tokens, Token Purchase Agreement logic) and the analysis behind the decision:

*What would transfer:*
- the buyer's right to volume and price per period, and the certificates that come with it;
- with it, the buyer's obligations (payment, take-or-pay, credit support). A transfer that carries obligations is a novation and needs the producer's consent.

*Who else must consent, and what it changes:*
- Lenders usually restrict assignment of offtake through their direct agreements.
- The incoming buyer must be a vetted company.
- A new buyer is a new counterparty, so its volume does not count for G4 until it confirms.
- A freely tradeable entitlement to future physical deliveries may be a MiFID commodity instrument (counsel).

*ERC-3643 against these needs:*
- Its identity registry and compliance modules correspond to vetting and the consent rules.
- But it is an EVM token, so it contradicts rule 3 and moves the source of truth onto a chain.

*Recommended:* keep rule 3 for Phases 1–5. Add a `NOVATION` event to the frame, valid only with the producer's, the outgoing buyer's and the incoming buyer's confirmations, so a sub-leg can change hands with consent, recorded and anchored, without a token. Treat tokenised sub-legs as a separate track, with counsel, built on top of this.

**Q12. DECIDED by JML, 2026-11-06: the pseudonymous id.**
- **The id:** `pseudo_id = HMAC-SHA256(salt, contract_ref)`, computed once at creation, **stored on `tb_contract` and fixed by trigger**. One per contract (a frame is one contract).
- **The salt:** needed only for new ids, so losing it breaks no existing anchor. It lives in `files/.env`, with an off-machine copy (password manager, not git, not the dump). There is one salt per environment.
- **What is anchored:** only the version's Merkle root. A buyer's verification response includes a Merkle proof of its own sub-leg.
- **Payload:** unchanged, `{schema_version, pseudo_id, event_type, event_hash, prev_hash}`, with the key and no-identifier test.

The question as first put, and the recommendation behind it: pseudonymous id scope.
Recommended: `HMAC-SHA256(salt, contract_ref)`, one value per contract for its life, so an outsider can follow one contract's events (that is the point) but cannot link two contracts. The salt must never rotate, or the existing anchors stop matching, so it needs a backup outside the database.
