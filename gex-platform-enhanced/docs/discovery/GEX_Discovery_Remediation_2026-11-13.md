# GEX commercial discovery: weakness assessment and UX remediation

*Assessment and remediation design · 13 November 2026 · responds to `GEX_Discovery_UX_Anti_Entropy_Prompt.md`*

| | |
|---|---|
| **Branch** | `greenmesh-phase2` |
| **Commit** | `1bad329` plus uncommitted working-tree changes from this session: migrations 112 and 113, their tests, two screen wording fixes, and `tests/probe_discovery_pg.py` |
| **Migration head** | **113** on the dev database (`gex_platform`, PostgreSQL 15 via `localhost:55432`) |
| **Environment** | Local development. Backend `:8000` (`app.main:app`, PostgreSQL runtime as `gex_app`). Frontend Vite dev server `:3001`. No production system was touched. |
| **Data handling** | Business data was read only. Every check that needed writes ran in the throwaway database the test suite builds from the migrations and drops afterwards (`conftest.pg_store`), using TEST-labelled tenants. The only writes to the dev database were sign-in records (login history, refresh tokens) and the two migrations you approved (112, 113), each taken after a verified backup. |
| **Evidence assets** | `docs/discovery/assets/`: annotated click paths (`journeys/`), role menus (`menus/`) and probe output (`probe_results_2026-11-13.json`). The probe source is `backend/tests/probe_discovery_pg.py`; re-run it with `PROBE_OUT=<file> pytest tests/probe_discovery_pg.py`. The earlier screenshot review is the private page "GEX Discovery Readiness Review". |

---

## 1. Verdict, principal risks and product decisions

**Verdict.** GEX is **not ready to sell discovery** to paying customers. The anonymised order model, four-eye trade confirmation, the contract record, custody and the RFNBO evidence chain are sound foundations, and this plan builds on them. Four things block a paid release:

1. **Integrity.** A seller can mint a token already marked "Verified". Minting can over-issue a capacity. Every mint reports HTTP 500 to the caller even when it succeeded.
2. **Authorisation.** What the server allows does not match what the menu shows.
3. **Journey.** No screen publishes supply, and there is no way to make a non-binding enquiry.
4. **Assessment.** Neither side can state or compare specification, certification or logistics.

The two confidentiality leaks this review found are now closed (112, 113).

**Update (Phase 0, same day, migration 114):** integrity point 1 is fixed. Minting now refuses a declared verification state, answers 201, locks the capacity and checks rates per delivery window. Listings and acceptances carve the token to the exact quantity traded, so title no longer passes for more than was sold. Creates accept an idempotency key. Still open in Phase 0: the server-side role policy (D-B) and the unsupported CONFIRMED marketplace records (D-A).

**Principal risks if released as is**

| Risk | Why it matters | Where |
|---|---|---|
| A buyer relies on a "Verified" label nobody checked | Mis-sold green attributes; reputational and regulatory exposure | F06 |
| The same quantity is sold twice | A contract that can't be delivered | F10, F11, F13 |
| A user acts outside their role through the API | Commitments made by the wrong function; four-eye bypass in spirit | F04 |
| Demo-origin records shown as CONFIRMED, naming real companies as buyers | False statements about third parties | F07 |
| A first contact can only be a binding offer | Buyers won't use it, or will commit by mistake | F18 |

**Decisions needed from JML** (each with a recommendation). **Decided 14 Nov:** D-B, D-C, D-D and D-F as recommended; D-E follows its recommendation (tokens may be for a future window; a listing is Indicative or Firm). D-A, D-G and D-H are open.

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| D-A | How the 41 marketplace records marked CONFIRMED with "provenance not recorded" should be labelled, and whether named third parties stay | Demote to *Claimed* and remove named third-party buyers until each confirms | Phase 0 |
| D-B | Which function may list, request, propose and accept | Commercial creates; Executive and Finance approve (second pair of eyes); Engineering and Operations read only | Phase 0 |
| D-C | What an anonymous listing may disclose | Country and region of production, named delivery place, membership and vetting badge, evidence status. Identity on accepted enquiry. | Phase 1 |
| D-D | Non-binding enquiry | Introduce it, separate from a proposal. Contact is released only by the receiving party's consent. (The 23 Oct venue concern was about GEX pairing parties; an enquiry is bilateral.) | Phase 1 |
| D-E | Planned supply | Pre-FID interest stays on the open-interest board. Forecast production may be listed as **Indicative**, with certification shown as *Planned*. A **Firm** listing needs a token. | Phase 1 |
| D-F | Who reviews product certificates | Reuse the independent-reviewer model (`REVIEWER_GATES` / appointments): a named certifier or inspector, never GEX and never the seller | Phase 1 |
| D-G | Geomap contacts | Exclude personal contact fields until a lawful basis is recorded per person | Phase 2 |
| D-H | The paid discovery entitlement | Server-side plan entitlement, checked alongside tenant, project and role, on screens, APIs and exports | Phase 1–2 |

---

## 2. Finding register

**Classification**

- **Observed:** seen in the interface or an API response.
- **Probe:** observed in the isolated throwaway database.
- **Code:** established by code inspection.
- **Inferred:** awaiting reproduction.
- **Resolved / Superseded / Unverifiable:** as stated.

**Type:** *Defect* (wrong behaviour), *Gap* (missing feature), *Data* (record quality), *Risk* (design exposure).

Severity: C critical, H high, M medium, L low. Confidence: high, med, low.

| ID | Finding | Type | Class | Evidence | Sev | Conf | Status |
|---|---|---|---|---|---|---|---|
| F01 | A buyer with project access read the seller's suppliers, unit prices, margin, break-even and another buyer's pending deal | Defect | Observed (UI, API) | Screenshot `journeys/leak_before_1.jpg`; `GET /api/v1/market/project-economics` as BremenThree returned `proj_hamburgone_emethanol` input lines and `in_market` with Vitol | C | high | **Resolved** by 112. Live API: buyers 0 rows, owners theirs. `test_marketplace_records_pg.py` +2, negative-verified. |
| F02 | A project's buyer list was readable by any company with project access | Defect | Observed (API) | `GET /projects/{id}/datasets/demand_buyers` 200 for a buyer, then 404 after 113 | H | high | **Resolved** by 113. Owner, mandated lender and GEX only. `test_demand_buyers_access_pg.py` (6), negative-verified twice. |
| F03 | Other `project_dataset` kinds, `project_profile`, `project_risk_flag` and `tb_asset` still use the "may see the project" rule. `deal_inputs` (DSCR P90, offtake %) is readable by stakeholders under RLS. | Risk | Code | `pg_policies`; `routes_projects.SCREEN_DATASET_KINDS` excludes `deal_inputs`, so it's not served | M | high | Open. Review kind by kind. |
| F04 | The server doesn't apply the menu's role rules: a producer CFO and a producer engineer can create RFQs | Defect | Probe | Probes `03a`, `03b`: **201**. `market_engine._trader()` checks only company and not-GEX (`market_engine.py:98`). Menu denies RFQs to producer CFO (`menuArchitecture.ts:263`). | H | high | **Resolved** (Phase 1, 14 Nov, D-B): one table, `core/market_policy.py`, enforced in the market engine, the order book and the token and capacity routes; TRADE_CONFIRM approved by the CEO or the CFO; screens read `GET /market/policy` and hide what the user may not do. `test_market_policy_pg.py` (14) and two frontend tests, negative-verified. |
| F05 | `/tokenisation` opens for every role and has no menu entry; the route guard only covers menu-registered paths | Defect | Observed | Walk: opens for all 7 accounts. `MenuAccessGuard.tsx` returns children when no item matches. | M | high | Open |
| F06 | A seller can mint a token with `verification_state = CONFIRMED`, which the canonical vocabulary displays as "Verified — a named third party has checked" | Defect | Probe | Probe `01c`: stored `CONFIRMED`. `tokens_sqlite.py:215, :459`. `vocabulary.py` crosswalk CONFIRMED → verified. | C | high | **Resolved** (Phase 0, 13 Nov): a declared trusted state is refused with 422; the server writes UNVERIFIED. `test_token_mint_pg.py`, negative-verified. |
| F07 | 8 sales records and 33 input lines are CONFIRMED although their source reads "MarketplacePage.tsx constant … provenance not recorded". They name Lufthansa, ThyssenKrupp, Linde, Maersk, Vitol, Engie, TotalEnergies, Yara and RFOcean as sold or pending buyers. | Data | Observed (data) | `project_sales_detail`, `project_input_line`; `scripts/apply_marketplace_decisions_20261025.py` | H | high | Open. Decision D-A. |
| F08 | 5 spot prices are "approved" from former frontend constants | Data | Observed (data) | `reference_parameter` rows, `source_name` | M | high | Open |
| F09 | `POST /api/v1/tokens/` writes the token, then fails response validation (`created_at` null), so the caller always gets **500** | Defect | Probe | Probes `01b` (500) and `01c` (row exists). `ResponseValidationError` on `TokenResponse.created_at`. | H | high | **Resolved** (Phase 0): `created_at` set by the server; mint answers 201. Retry-safety needs idempotency (F12). |
| F10 | The capacity check at mint is read-then-insert without a lock, so two concurrent mints over-issue | Defect | Probe | Probe `06`: 40 existing, plus 40 in flight, plus 40 via API: **120 on a 100 MTPD capacity** | H | high | **Resolved for the API** (Phase 0): `SELECT … FOR UPDATE` on the capacity; the race test waits for the lock and is refused 409, negative-verified. **And at the database** (migration 115): a deferred constraint trigger on `tokens` locks the capacity and refuses, at commit, any day whose live tokens exceed it, whoever writes them. Before 115 the re-run probe showed a lock-skipping writer reaching 120 MTPD on 100. Tests: a raw writer and a single over-tokenising transaction are both refused; both negative-verified. It also refused two test fixtures that had been over-tokenised all along (10 and 100 MTPD capacities carrying several 50 MTPD tokens). |
| F11 | The mint check compares rates (MTPD) and ignores delivery windows | Defect | Code | `tokens_sqlite.py` (old lines 376–388) | M | high | **Resolved** (Phase 0): peak committed rate on any day of the new window; SPLIT parents and VOIDED excluded. Negative-verified. |
| F12 | No idempotency on create endpoints: the same RFQ posted twice makes two | Defect | Probe | Probe `04`: 201, 201, two distinct IDs | M | high | **Resolved** (Phase 0, 114): `Idempotency-Key` on capacity, mint, listing, listing open, RFQ, proposal, acceptance and settlement; replay returns the first response, a reused key with another body gets 422. The RFQ form sends one key per filled-in form. Negative-verified. |
| F13 | Opening a listing reserves the whole token, even when the listing is smaller, so the remainder is stranded | Defect | Code | `market_engine.open_offer` moves the token MINTED → RESERVED. `token_split` exists (109) but isn't used here. | M | med | **Resolved** (Phase 0, 114): the token is carved at listing open and at acceptance; the remainder returns to MINTED. The database refuses a split that loses tonnes. Negative-verified. |
| F14 | Quantities use six representations: MTPD rate (tokens, listings, RFQs), t per month (terms), kg (custody), t/yr (screens), tpa (open interest), and kt/y or Nm³/h (Geomap) | Risk | Code | Files cited in §4.3 | M | high | Open |
| F15 | Declared availability percentages don't reconcile with tokens: the chart shows "Tokenised" while the tokens table has 0 rows | Data | Observed | `project_sales_detail.tokenised` vs `tokens` | M | high | Open |
| F16 | No screen creates a capacity, token or listing; "List on Market" and "Create Capacity" form a loop | Gap | Observed (UI) | `journeys/seller_publish_*.jpg`; no screen calls `offersAPI.create` | C | high | Open |
| F17 | Four buttons land on Your Matches instead of the market, and `?mode` is ignored | Defect | Observed (UI) | `journeys/buyer_purchase_3.jpg`, `seller_sales_3.jpg` | M | high | **Resolved** (14 Nov): the four buttons open Market Discovery on the side they name (`?side=supply|demand`, filtered to the molecule; an unknown molecule shows all with a note) and appear only for a role that may open it; Your Matches honours `?mode=sell`. `MarketLinks.test.tsx` (6), three breaks caught; checked in the browser as buyer, seller and producer CFO. |
| F18 | No non-binding enquiry exists; the only contact is a binding proposal | Gap | Probe | Probe `05a`: `POST /market/enquiries` **404**. `05b`: proposal 201. | H | high | **Resolved** (119, 14 Nov): `POST /market/enquiries` on one listing or RFQ, a thread, Share contact / Decline by the receiver only; Deals inbox (`/deals`), "Ask (non-binding)" on Market Discovery. `test_enquiry_pg.py` (14), `Deals.test.tsx` (5). |
| F19 | The RFQ form promises location and contact "shown once matched", but the seller never receives them | Defect | Probe | Probe `05d`: false. `market_engine._match` keys. | M | high | **Resolved** (14 Nov): the form no longer promises a reveal at match (step 3); an RFQ's location and contact are released to a seller whose enquiry the buyer answers with Share contact (119), recorded in the ledger. |
| F20 | The offer API accepts `country_of_origin`, `esg_score`, `dfi_funded` and `sovereign_cert_scheme`, then drops them | Defect | Probe | Probe `01d`: sent DE / 80, returned null | L | high | Open |
| F21 | A listing shows buyers 16 fields: no evidence status, CI basis, specification, form, Incoterm, location band, validity or firm/indicative | Gap | Probe | Probe `02` field list | H | high | **Resolved** (117, 14 Nov): D-C fields on the listing, the product with each claim's evidence status, typed Incoterm; `test_listing_fields_pg.py`. Region finer than country still has no source. |
| F22 | A buyer cannot state requirements: the form has no certification, CI limit, specification or Incoterm. `compliance_requirements` is accepted by the API but never collected or shown. | Gap | Observed + Code | `journeys/buyer_find_5.jpg`; `RFQIn` | H | high | **Resolved** (117, 14 Nov): `tb_rfq.requirements`, validated, fixed once published, shown to sellers; the form collects them. |
| F23 | The only comparator ignores mandatory requirements: an offer failing certification and CI limits scores **100** | Defect | Probe | Probe `07`; `matching_sqlite.calculate_match_score` | H | high | **Resolved** (118, 14 Nov): eligibility before score (`core/compatibility.py`); a mandatory failure excludes at any price, auto-matching skips it, a seller's proposal is refused; the score still ranks the eligible (2B). |
| F24 | The counterparty "register" isn't a profile: 5 entities, no LEI, no client companies, no vetting state | Gap | Observed | `/counterparties`; `tb_counterparty` | M | high | Open |
| F25 | Geomap isn't connected; the ecosystem feed answers 500; there's no map | Gap | Observed (API) | `GET /api/v1/ecosystem/projects` 500. `ecosystem_store._conn()` always opens SQLite, and its tables don't exist there. | H | high | Open |
| F26 | No external-organisation entity and no "GEX outsider" status; the external corpus is empty and holds projects only | Gap | Code | `external_projects` 0 rows; no organisation columns | M | high | Open |
| F27 | The open-interest board (pre-FID interest with publisher confidentiality) has an API but no screen, and 0 rows | Gap | Observed (API) | `GET /api/v1/open-interest` 200 `[]` | M | high | Open. Reuse it (§5.6). |
| F28 | No subscription entitlement concept | Gap | Code | `core/entitlements.py` covers finance review only | M | high | Open. Decision D-H. |
| F29 | "Purchase" shows a visible project's feedstock inputs, not supply | Defect | Observed (UI) | `journeys/buyer_purchase_2.jpg` | M | high | Open |
| F30 | A non-owner mint is refused by RLS, but surfaced as **500** with the database message | Defect | Probe | First probe run: 500 "new row violates row-level security policy for table tokens" | L | high | **Resolved** (Phase 0): 403 `NOT_YOUR_CAPACITY` before any write; no database text in errors. |
| F31 | Commercial Overview showed "0 inputs" for some roles and "3" for others on the same project | — | Inferred | Earlier walk | — | low | **Superseded**: after 112, non-owners correctly see none |
| F34 | Acceptance moved the WHOLE reserved token to MATCHED, and settlement passed its whole title to the buyer, though the contract was for min(listing, RFQ) over the overlap | Defect | Observed (test) | `test_market_chain`: 50 MTPD for 2027–2029 sold to an RFQ for 40 MTPD for 2027–2028; title passed to all of it | C | high | **Resolved** (Phase 0, 114): the contract and settlement carry exactly the agreed piece. The evidence pack traces it back through the split (pack version 3). |
| F36 | A carved token could not be delivered: the draw limit (trigger 103/107 and application) counted only allocations made to that very token, and the closed-custody-period check matched allocations by token, so a split child's period went unchecked | Defect | Code + test | `delivery_draw_guard`, `delivery_record._closed_period_at` | H | high | **Resolved** (114): limit = `app_token_kg` (the split's recorded kg); period found through the token's root. `test_delivery_record_pg.py` carved-trade test, both fixes negative-verified. |
| F35 | `fetchAPI` let a caller's `headers` replace the auth and JSON headers | Defect | Code | `frontend/src/api.ts` | L | high | **Resolved**: merge order fixed; test negative-verified |
| F33 | A refused mint still left a `token.minted` event: the event was appended before the insert | Defect | Code | `tokens_sqlite.create_token` order of calls | M | high | **Resolved** (Phase 0): insert, then event, then commit; a refusal leaves neither. Covered by the stakeholder test (event count unchanged). |
| F32 | No company has Commercial, CEO and CFO accounts together; no pure-buyer Commercial or CEO exists | Limitation | Observed (data) | `auth_users` | — | high | Role comparison done server-side in the probe (same company, three functions) |

---

## 3. Authoritative records and rules

### 3.1 One product definition

**Principle.** The *token* is the product unit, not the listing. It is one defined quantity of one fuel, from one site and production period. Everything a buyer assesses hangs off it through links, and every later record (listing, proposal, contract, delivery, evidence pack) refers to the same token ID. Tokenisation, payment or membership never sets a certification or verification state.

| Concept | Authoritative record | Exists today | Permitted writers | States (reuse first) | Dependent views | Change and staleness |
|---|---|---|---|---|---|---|
| Molecule and pathway | `tb_commodity` (molecule) + `tokens.production_pathway` (**new**; split from `certification_pathway`) | Partly: one field mixes pathway and scheme | Owner at mint; immutable after listing opens | — | Listing row, detail, compatibility | A change means a new token version (§3.4) |
| Technical specification | `token_quality_spec` (**new**, typed parameters, same shape as Phase 2 `quality_spec.parameters`, V16) | Contract-side only (107) | Owner (declared); inspector (measured) | Value basis: `declared` / `measured` / `verified` | Detail ▸ Product; compatibility | Measured beats declared. Old values kept. |
| Regulatory applicability | `token_regulatory_claim` (**new**: regime RFNBO / RED III / FuelEU / ReFuelEU / 45V, intended use) linked to `rfnbo_correlation` results (099) | RFNBO computed per closed custody period only | Owner claims; **computed** result from custody | evidence_state: `asserted` → `submitted` → `verified` / `failed` / `expired` | Detail ▸ Qualification; evidence pack | Recomputed when the period closes. The claim stays `asserted` until then. |
| Certification | `product_certificate` (**new**: scheme, body, reference, **scope** = organisation / site / batch-period, valid_from / until, document sha256) + `token_certificate_coverage` (quantity, period) | No | Seller submits; **only an appointed reviewer verifies** (D-F, the Attack A rules); expiry by sweep | Canonical `evidence_state` (`vocabulary.py`) | Listing badge, detail, compatibility | `valid_until` past means *expired* (reuse `scripts/expire_evidence.py`). A site certificate never shows as quantity coverage. |
| Inspection and lab report | `product_certificate` with scope `sample` or `batch` and `kind = inspection` (same table: scope, inspector, date, results) | Per delivery only (Phase 2, 107) | Inspector (by agreed appointment) | Same | Detail ▸ Evidence | Kept separate from sustainability certification by `kind` |
| Environmental attributes | `tokens.carbon_intensity_gco2e_mj` + `ci_basis` (**new**: method, boundary, calc date, basis estimate / calculated / measured / verified) | Number only | Owner (estimate); verifier (verified) | `evidence_state` | Listing CI cell shows value and basis | A new calculation is a new row; the listing shows the latest, and history stays |
| Commercial offer | `tb_order` (sell, firm or indicative) + `tb_terms` (frozen on open) + `tb_order_event` | Yes (087) | Owner, Commercial function (D-B), optional second approver | `tb_order_status` | Market, detail, Deals | A price or term change means withdraw and a new order with `supersedes` (**new column**). History is kept by freezing. |

**Why new tables rather than reuse.** `bankability_evidence` is scoped to a project's gate items, not to a quantity or period, so reusing it would blur exactly the site-versus-batch distinction the brief requires. The document store (`POST /evidence/document`, sha256), the reviewer appointments and the expiry sweep are reused unchanged.

### 3.2 Identity, provenance and membership

Three identities are kept apart:

- **Organisation:** `tenants` for clients, `tb_counterparty` for booking, plus a **new** `prospect_organisation` for outsiders.
- **Site:** `coc_facility_profile` (097/099) gains coordinates.
- **Project:** `projects`.

Each organisation carries four **independent** axes:

| Axis | Values | Source of truth | Who sets it |
|---|---|---|---|
| Membership | `client_vetted` · `client_pending` · **`outsider`** | `auth_users.account_state` / tenant; outsider = prospect row with no tenant | Vetting process (existing `account_lifecycle`) |
| Provenance (per field) | `external_source` · `client_asserted` · `verified` | Field-level provenance (`kyc_profiles.provenance` vocabulary reused) | Ingestion, client, reviewer |
| Verification (per claim) | canonical `evidence_state` | Certificate or evidence rows | Appointed reviewer only |
| Commercial readiness | `announced_project` · `potential_counterparty` · `open_interest` · `indicative_offer` · `firm_offer` · `firm_requirement` | Derived from records, never stored by hand | Derived |

**Precedence when evidence conflicts:** verified beats client-asserted, which beats external-source. Within a rank, the newest *dated source* wins, not the newest write. Registration never overwrites: when a prospect becomes a client, its client-asserted values are **attached** beside the external ones, and the screen shows both until a reviewer resolves them. The source history is append-only.

### 3.3 Quantity and availability

| Quantity | Record | Unit (canonical) | Notes |
|---|---|---|---|
| Nameplate capacity | `capacities.capacity_mtpd` | t/day | Plant fact; not saleable |
| Forecast production | `capacity_forecast` (**new**: period, tonnes, basis) | t per period | Feeds indicative listings; keeps forecast status |
| Produced | custody lots (097, metered 098) | kg → t | Evidence of physical existence |
| Tokenised | `tokens` (period, tonnes) | t per period | **Partition key** |
| Offered | open sell `tb_order` naming the token | t | |
| Reserved | token state RESERVED | t | |
| Contracted | token state MATCHED / SETTLED; `tb_contract` flows | t | |

**Consistency rule: each tonne is in exactly one bucket.** Availability for a period is the sum of tokens in state MINTED. Listing a token moves it to RESERVED, so the same tonnes are never subtracted twice. A partial listing first **splits** the token (`token_split`, 109) so only the listed part is reserved. That fixes F13 by reusing the Phase 2 primitive.

**Atomicity.** Minting takes `SELECT … FOR UPDATE` on the capacity row and checks tonnes per overlapping period (fixes F10, F11). Listing already locks (`open_offer`, `FOR UPDATE`). Every create endpoint accepts an `Idempotency-Key` stored with the result for 24 h (fixes F12, and makes the F09 retry safe).

**Display.** Store tonnes per period; show the rate (t/day) beside it. Geomap capacity estimates stay `external_source` / `forecast` and never enter any of these buckets.

### 3.4 Rules that stop drift (anti-entropy)

| Rule | Enforced by | Drift detection |
|---|---|---|
| One label vocabulary | Existing `vocabulary.py` and its CI guardrail. New states (availability, membership, offer) are added there. | `tests/test_vocabulary_guardrails.py` |
| Verification only by an appointed third party | Server sets `UNVERIFIED` on create; transitions only through the reviewer route (Attack A pattern) | New test: create with any trusted state gets 422. Nightly query: trusted states without a reviewer row. |
| Menu equals server | One policy table (`market_policy`, §4.2) read by both the menu config and `market_engine` | Contract test enumerating role × action against the API and `menuArchitecture` |
| Terms freeze on publish | Existing `record.freeze` | Existing triggers |
| Decisions keep their inputs | Compatibility assessments are stored with the token version and requirement version they used (§6.3) | A re-run never updates a stored assessment; it adds one |
| Availability is derived | View `v_token_availability`; no stored percentages | Remove `project_sales_detail.available/tokenised/in_market` from screens; parity test |

---

## 4. Field inventory and permission matrix

### 4.1 Commercial field inventory

**Table A: business view.** Stage: D discovery, A assessment, N negotiation, T transaction. Disclosure: *Anon* (any entitled member, without identity), *Enq* (after an accepted enquiry), *Party* (to a proposal or contract), *Owner*.

| ID | Field | Seller value | Buyer requirement / tolerance | Stage | Disclosure |
|---|---|---|---|---|---|
| C1 | Legal entity | Name, LEI | Acceptable counterparties (vetted only, rating floor) | A | Enq |
| C2 | Commercial role / authority to sell | Producer, authorised seller (mandate document) | Producer only, or traders allowed | D | Anon (role badge) |
| C3 | Membership and vetting | client_vetted / outsider | Vetted only | D | Anon |
| C4 | Site and project association | Site (facility), project | — | A | Enq |
| C5 | Contact permission | Release on accepted enquiry | Same | N | Party |
| P1 | Fuel | Molecule | Molecule | D | Anon |
| P2 | Production pathway | e.g. PEM electrolysis + DAC methanol synthesis | Allowed pathways | D | Anon |
| P3 | Physical form | Gas / liquid / compressed / liquefied | Required form | D | Anon |
| P4 | Purity / composition | e.g. ≥ 99.85 % MeOH | Minimum | A | Anon |
| P5 | Contaminants | e.g. water ≤ 0.1 %, S, Cl | Maxima | A | Anon |
| P6 | Specification standard | e.g. IMPCA, ISO 14687 grade D | Required standard | A | Anon |
| P7 | Pressure / temperature | Where material (H₂, NH₃) | Delivery conditions | A | Anon |
| E1 | Carbon intensity | Value, gCO₂e/MJ | Maximum | D | Anon |
| E2 | CI methodology and boundary | e.g. DA 2023/1185, well-to-wheel | Required method | A | Anon |
| E3 | CI calculation date and basis | Estimate / calculated / measured / verified | Minimum basis | A | Anon |
| Q1 | RFNBO / RED III applicability | Claimed regime, status | Required regime | D | Anon |
| Q2 | Scheme, body, certificate ref | ISCC EU / CertifHy, body, ref | Accepted schemes | A | Anon (ref at Enq) |
| Q3 | Certificate scope and validity | Organisation / site / batch-period; dates | Batch or period coverage required | A | Anon |
| Q4 | Inspection or lab report | Inspector, date, scope, result | Required inspection | A | Enq |
| V1 | Expected production | t/day, start date | — | D | Anon |
| V2 | Offered quantity and schedule | t per period | Required t per period | D | Anon |
| V3 | Minimum parcel | t | Parcel size | D | Anon |
| V4 | Available balance | Derived (MINTED tonnes) | — | D | Anon |
| V5 | Existing commitments | Contracted tonnes (count only) | — | A | Owner (count Anon) |
| R1 | Price, currency, unit | €/t | Max €/t | D | Anon |
| R2 | Fixed / index basis | Fixed or index + spread | Acceptable bases | A | Anon |
| R3 | Included attributes | e.g. certificates bundled, GoO | Required inclusions | A | Anon |
| R4 | Indicative / firm | Order type | Firm only? | D | Anon |
| R5 | Validity | Valid until | — | D | Anon |
| L1 | Plant coordinates | Lat / long | — | A | Enq (country/region Anon) |
| L2 | Pickup / delivery place | Named place | Delivery place | D | Anon (named place) |
| L3 | Incoterm | e.g. FOB, DAP | Acceptable terms | D | Anon |
| L4 | Storage, loading, transport | Tanks, berth, rail, pipeline | Required mode | A | Enq |
| L5 | Lead time and constraints | Days; constraints | Required by date | A | Enq |
| T1 | Source and owner | Who stated it | — | D | Anon (source class) |
| T2 | Last update | Timestamp | Freshness tolerance | D | Anon |
| T3 | Token / batch / period ref | Buyer-safe reference | — | N | Party |
| T4 | History | Versions of token, offer, certificate | — | A | Enq |

**Table B: technical view** (same IDs).

| ID | DB / API source today | Unit | Evidence basis today | Editor | Display today | Status | Remedy |
|---|---|---|---|---|---|---|---|
| C1 | `tb_counterparty.legal_name`, `.lei` (all null) | — | declared | any user (register) | Counterparties; match reveal | Stored, not linked to tenants | Link to tenant; LEI via GLEIF; profile page |
| C2 | `auth_users.company_type`, `capabilities_json` | — | declared | GEX staff | not in market | Stored, unused | Role badge on row |
| C3 | `auth_users.account_state`, `activated_by` | — | verified (vetting) | GEX staff (SoD) | not in market | Stored, unused | Membership badge |
| C4 | `capacities.project_id`, `coc_facility_profile` | — | declared | owner | Capacity (owner) | Stored | Shown at Enq |
| C5 | `tb_rfq.buyer_contact`; none for seller | — | declared | owner | RFQs (own) | **Promised, never released (F19)** | Enquiry consent release |
| P1 | `tb_terms.commodity_id` | — | declared | owner | Market Discovery | **Shown** | — |
| P2 | `tokens.certification_pathway` (mixed) | — | declared | owner | Market Discovery "Certification" | Conflated | Split into `production_pathway` |
| P3–P7 | none for listings; `quality_spec` on contracts (107) | per parameter | — | — | — | **Missing** | `token_quality_spec` |
| E1 | `tokens.carbon_intensity_gco2e_mj` | gCO₂e/MJ | declared (shown as plain number) | owner | Market Discovery | Shown without basis | Add `ci_basis` |
| E2–E3 | none | — | — | — | — | Missing | `ci_basis` |
| Q1 | `capacities.compliance_certifications`; `rfnbo_correlation` (period) | — | declared / computed | owner / engine | not in market | Stored, unused | `token_regulatory_claim` |
| Q2–Q3 | `project_sales_detail.certifier` (text) | — | declared | GEX import | Commercial Overview (owner) | Missing as a record | `product_certificate` |
| Q4 | Delivery inspection (107–109) | — | verified (agreed inspector) | inspector | Delivery API | Post-trade only | Same table, `kind = inspection` |
| V1 | `capacities.capacity_mtpd`, `production_start` | t/day | declared | owner | Capacity (owner) | Stored | Show on row |
| V2 | listing `volume_mtpd` + window | **rate** | declared | owner | Market Discovery | Rate only | Tonnes per period |
| V3 | `tb_order.min_fill_quantity` | t | declared | owner | not rendered | Stored, unused | Show; set in wizard |
| V4 | none (declared % in `project_sales_detail`) | % | declared | GEX import | chart | **Inconsistent (F15)** | `v_token_availability` |
| V5 | `tb_contract` flows | t | verified (contract) | parties | Contracts | Stored | Count on detail |
| R1 | `tb_terms` payment leg `unit_price` | €/t (shown €/kg) | declared | owner | Market Discovery | **Shown** | Show €/t too |
| R2 | price clause `price_basis` | — | declared | owner | not rendered | Stored, unused | Show |
| R3 | none | — | — | — | — | Missing | Clause `included_attributes` |
| R4 | `tb_order.order_type` | — | declared | owner | not in listing | Stored, unused | Show |
| R5 | `tb_order.valid_until` (forced = delivery end) | date | declared | system | not shown | Stored, not settable | Settable; show |
| L1 | Geomap `production_plants.latitude/longitude` (separate DB); `projects.lat/lng` | WGS84 | declared | owner / external | Projects API | Not in market | Region band Anon; coords at Enq |
| L2 | `tb_order.location`, `tb_rfq.location` | text | declared | owner | own screens only | Hidden even after match | Named place, UN/LOCODE |
| L3 | typed delivery clause (104) on contracts; free-text at proposal | — | declared | parties | Market Discovery free text | Partial | Typed on listing and RFQ |
| L4–L5 | Geomap ports and pipelines (separate DB) | — | external | — | — | Missing | Logistics section |
| T1 | `created_by_user`; record `source` | — | — | system | not rendered | Stored, unused | Source class chip |
| T2 | `created_at`; `updated_at` on RFQs | ts | — | system | not rendered | Stored, unused | "Updated …" |
| T3 | `tokens.id`, `mass_balance_lot_id`, `coc_period` | — | — | system | withheld | Stored | Buyer-safe reference at Party |
| T4 | `tb_order_event`, contract versions | — | — | system | not rendered | Stored | History panel |

### 4.2 Role, action and API permission matrix

**Proposed** (decision D-B). "Today" records what the probe and walk observed.

| Action | API | Producer Commercial | Producer CEO | Producer CFO | Offtaker Commercial | Offtaker CEO | Offtaker CFO | Engineer / Ops | Today (server) |
|---|---|---|---|---|---|---|---|---|---|
| Search market | `GET /market/listings/*` | ✔ | ✔ | ✔ read | ✔ | ✔ | ✔ read | ✖ | any member (✔ for CFO and engineer) |
| Create capacity / mint | `POST /capacities`, `/tokens` | ✔ | approve | approve | — | — | — | Ops ✔ capacity | owner company (RLS); function not checked (code); non-owner 403, mint 201 (fixed 13 Nov) |
| Create / open listing | `POST /marketplace/offers` | ✔ | approve | approve | — | — | — | ✖ | owner company; function not checked (code) |
| Create RFQ | `POST /market/rfqs` | ✔ (prosumer) | approve | approve | ✔ | approve | approve | ✖ | **any function (probe 03a/b)** |
| Send enquiry | `POST /market/enquiries` (new) | ✔ | ✔ | ✖ | ✔ | ✔ | ✖ | ✖ | **missing (404)** |
| Propose (binding) | `POST /market/matches` | ✔ | ✔ | ✖ | ✔ | ✔ | ✖ | ✖ | any function |
| Accept proposal | `POST /market/matches/{id}/accept` | ✔ | ✔ | ✖ | ✔ | ✔ | ✖ | ✖ | any function |
| Confirm trade (four eyes) | `/market/contracts/{id}/confirm…` | 1st | 2nd | 2nd | 1st | 2nd | 2nd | ✖ | WAE TRADE_CONFIRM (exists) |
| Verify certificate | reviewer route (new) | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | appointed reviewer only |
| Read seller economics | `GET /market/project-economics` | own | own | own | ✖ | ✖ | ✖ | ✖ | **owner only (112) ✔** |

Direct URL and menu follow the same table through one `market_policy` module read by `menuArchitecture` (via `/api/v1/vocabulary`-style endpoint) and by `market_engine`.

---

## 5. The journey

### 5.1 Status labels: one small set, one meaning each

| Axis | Labels shown | Meaning | Source |
|---|---|---|---|
| Evidence (per claim) | **Claimed** · **Submitted** · **Verified** · **Expired** · **Rejected** | Canonical `evidence_state` (`vocabulary.py`) | Certificate and claim rows |
| Planned production | **Planned** (attached to a claim or quantity) | Not yet produced; attributes are expected | Forecast and token period in the future |
| Offer | **Indicative** · **Firm** · **Expired** · **Withdrawn** | Order type and status | `tb_order` |
| Availability | **Available** · **Reserved** · **Contracted** | Token bucket | Token lifecycle |
| Membership | **GEX member · vetted** · **GEX outsider** | Membership axis | Tenant / prospect |
| Match outcome | **Compatible** · **Incompatible** · **Needs evidence** | Per requirement | Assessment |

Colour is never the only signal: each label is a word, with an icon for evidence.

### 5.2 Screens

The annotated click paths of today's behaviour are in `assets/journeys/`. The wireframes below are **proposed** and are not implemented.

**Market (`/market?side=supply|demand`): find and filter**

```
┌ Market ─────────────────────────────────── [Supply] [Demand] ───────────┐
│ Molecule [e-Methanol▾] Region [NW Europe▾] Window [2028-Q1 → 2028-Q4]   │
│ Volume ≥ [500 t/month]  Evidence [Verified only ☐]  Incoterm [any▾]     │
│ Include prospects (GEX outsider) ☐            Matches my requirement [RFQ-12▾]
├─────────────────────────────────────────────────────────────────────────┤
│ ● e-Methanol · PEM+DAC · liquid   DE, Lower Saxony   FOB Hamburg        │
│   2,400 t over 2028   min 500 t   €1,100/t fixed   Firm · valid 31 Jan  │
│   CI 9.0 g/MJ (Calculated)  RFNBO Claimed  ISCC EU Submitted            │
│   GEX member · vetted       Compatible 6 · Needs evidence 2   [Compare] │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Row fields:** molecule, pathway, form, region band, named place and Incoterm, total tonnes with window, minimum parcel, price with basis, indicative/firm with validity, CI with basis, qualification and certificate status, membership, and the compatibility summary when a requirement is selected.
- **Filters** apply instantly and live in the URL (shareable, back-button safe). "Verified only" hides Claimed and Submitted rows. "Include prospects" adds Geomap outsiders in a visually separate group.
- **Primary action:** select a row to open its detail. Keyboard: arrows move between rows, Enter opens the detail, and `c` adds the row to the compare tray (up to 4).
- **Empty state:** "No firm e-Methanol supply for 2028 in NW Europe. 3 indicative listings and 5 announced projects match. [Show indicative] [Publish a requirement so sellers can find you]"

**Listing detail (side panel, progressive disclosure)**

Sections, in order: **Summary** (the row) → **Product** (P1–P7, each with its basis) → **Qualification & evidence** (Q1–Q4, each certificate with scope, validity and status; "covers this quantity" vs "covers the site") → **Volume & timing** (V1–V5, per-period chart) → **Price & terms** (R1–R5, L2–L3) → **Logistics** (L4–L5, shown at Enq) → **History** (T4). Primary action: **Send enquiry**. Secondary: **Propose (binding)**, enabled only when the user has a matching requirement, and confirmed by a dialog ("This is a firm offer to buy 2,400 t at €1,100/t. It binds when the seller accepts.").

**Compare (up to 4 candidates)**

A table with rows = requirement fields and columns = candidates. Each cell shows the value and a *Compatible* / *Incompatible: reason* / *Needs evidence: what* outcome. Mandatory failures sort the candidate to the right, whatever its price.

**New listing (wizard, `/market/mine/new?project=`)**

1. Source
2. Product & evidence
3. Commercial terms
4. Preview

(Steps as in the review's §9.) Validation runs per step, with the reason and the fix: "Quantity exceeds what is available for 2028-Q2 (1,200 t free). Reduce it or extend the period." "Planned production can only be listed as Indicative." Publishing writes the order; if the company requires two approvers, it goes to Deals ▸ Waiting on you for the second.

**New requirement (RFQ)**

The same field groups, as limits: max CI with method, required regimes and schemes with minimum evidence state, specification limits, form, tonnes per period, place and Incoterm, price ceiling and basis, validity.

**Enquiry (`/deals/{id}`)**

A structured, non-binding thread on one listing or requirement. The first message can request specific evidence ("Send the ISCC EU certificate covering 2028-Q1"). The receiving party chooses **Share contact** (identity and contact released, recorded) or **Decline**. From an enquiry: **Make a firm proposal** carries the agreed fields into a proposal (existing `POST /market/matches`) with terms prefilled.

**Prospect profile (GEX outsider)**

The header reads "**GEX outsider** · data from IEA Hydrogen Projects (CC BY 4.0), retrieved 2026-06-29 · not verified". It shows the announced project, phase, capacity (forecast) and site. Primary action: **Request introduction**, which goes to GEX staff (§7.3). There is no enquiry or proposal, because an outsider has no account.

### 5.3 Who sees identity, location and contact

| Stage | Identity | Location | Contact | Price and terms |
|---|---|---|---|---|
| Discovery (Anon) | Role and membership badge only | Country and region; named place | ✖ | ✔ |
| Enquiry sent | ✖ | same | ✖ | ✔ |
| Enquiry accepted (consent) | ✔ legal entity | site and coordinates | ✔ the named person | ✔ |
| Proposal / contract (Party) | ✔ | ✔ | ✔ | ✔ + token reference |
| Owner | ✔ | ✔ | ✔ | ✔ + economics |

### 5.4 Errors and blockers: what, why, who, next

| Situation | Message (what, why) | Who resolves | Next action shown |
|---|---|---|---|
| Listing without a certificate | "RFNBO is Claimed. Buyers filtering for Verified won't see this listing." | Seller, then reviewer | [Upload certificate] |
| Certificate expired | "ISCC EU certificate expired on 30 Apr. Verified status removed from 3 listings." | Seller | [Upload renewal] |
| Requirement mismatch | "Incompatible: CI 32 g/MJ exceeds your 28.2 limit (RED III threshold)." | — | [Show compatible only] |
| Role not allowed | "Proposals are made by Commercial. Ask a colleague, or approve one in Deals." | Commercial colleague | [Go to Deals] |
| Over-allocation | "Only 1,200 t are free in 2028-Q2; 400 t are reserved by an open listing." | Seller | [Edit quantity] |

### 5.5 Navigation without loops

Six Commercial entries: **Market** · **My listings & RFQs** · **Deals** · **Contracts** · **Counterparties** · **Portfolio**. Every button lands where its label says, in the stated state. Replacements and redirects are as in the review's §9. Old URLs redirect, so deep links keep working.

### 5.6 The open-interest board for pre-FID discovery

`/api/v1/open-interest` already models pre-FID interest: side, molecule, volume (tpa), target COD year, minimum term, jurisdiction, counterparty rating, and indicative €/t. Publisher confidentiality rules (deny or allow companies, jurisdictions, minimum rating) are enforced server-side, and the viewer identity is derived from the session.

**Fit:** good for "we will need 50 kt/y of e-methanol from 2030". **Keep it separate** from offers. The ladder is interest → indicative offer → firm offer → agreed transaction → physical delivery, and each rung is a different record with a different commitment. The board appears in Market as a third tab, **Interest**. Its only action is **Send enquiry**; a proposal is never allowed there.

**Gaps to close:** units (move tpa to t per period), a screen, and a display of the publisher's rules to the publisher.

---

## 6. Matching: understandable and defensible

### 6.1 Two stages

1. **Eligibility (mandatory, per requirement).** Each buyer requirement is marked mandatory or preferred. Mandatory requirements produce **Compatible**, **Incompatible (reason)** or **Needs evidence (next step)**. One Incompatible mandatory requirement excludes the candidate, and no price compensates.
2. **Ranking (commercial, only among the eligible).** Price, volume fit, timing, logistics distance and evidence strength. The existing score weights stay in code as documented (JML, 23 Oct) but move to this stage.

### 6.2 Comparison rules

| Dimension | Compatible when | Needs evidence when |
|---|---|---|
| Fuel and pathway | Molecule equal; pathway in the allowed set | Pathway Claimed and the buyer requires Verified |
| Specification | Each parameter within limits | Value declared and the buyer requires measured |
| Form | Equal, or convertible at the named place (flag) | — |
| Carbon intensity | value ≤ max, method accepted | Basis below the buyer's minimum |
| Qualification | Regime claimed; evidence state ≥ required | Claimed or Submitted where Verified is required |
| Certificate | Scheme accepted, scope covers the quantity and period, valid on the delivery dates | Site-only scope where batch is required |
| Volume | Available tonnes per period ≥ required, and parcel ≥ minimum | Forecast only (Indicative) |
| Timing | Windows overlap and lead time fits | — |
| Logistics | Incoterm accepted; place within the buyer's set | Place unspecified |

External (outsider) data may rank and appear in exploratory results, labelled with uncertainty, but **never** yields *Compatible* on a mandatory evidence requirement.

### 6.3 Reassessment without rewriting history

An assessment row stores `(requirement version, token version, offer version, certificate states, outcome per field, computed_at)`. It is computed on view and **stored** when a user acts on it (enquiry, proposal, acceptance). A change to a specification, certificate state (including expiry), availability or requirement marks dependent open items **"Changed since you looked"**, with a diff. Stored assessments are never updated; a new one is added. Proposals and contracts keep the assessment they were made on.

---

## 7. The Geomap–GEX boundary

### 7.1 Permitted flows

| Flow | Origin → destination | Approved fields | Visibility | Validation | Authority |
|---|---|---|---|---|---|
| Prospect import | Geomap `production_plants`, `ports`, `pipelines` → GEX `prospect_organisation` and the external corpus | Organisation, site, country, coordinates, molecule, technology, maturity, capacity with unit, source, retrieved_at, licence | Entitled members only (D-H), labelled **GEX outsider** | Licence present; unit normalised (Pint); vocabulary mapped or quarantined (as `external_corpus`); duplicate check (§7.2); freshness ≤ source cadence | GEX data steward; feeds no gate or score (EXTERNAL_PRIOR leak guard) |
| Personal contacts | Geomap → GEX | **None** until D-G | — | Lawful-basis record per person | DPO |
| Client publication to map | GEX → Geomap / public map | Only the publisher's `visible_fields` (`ecosystem_store.redact_for_viewer`, enforced even against GEX admins) | Publisher's choice | Allowlist; no economics, prices, counterparties, membership associations | Client executive, four eyes |
| Market listings | GEX → members | `OFFER_LISTING_FIELDS` plus the new Anon fields (§4.1) | Entitled members | Server allowlist | Market engine |
| Exports | GEX → file | The same allowlists as the screen the export comes from | Entitled, logged | Same | Same |

**Membership confidentiality:** a public map never reveals that an organisation is a GEX client, or which projects it has with whom.

### 7.2 Controlled ingestion

Snapshot import (`external_corpus.import_snapshot`, built and empty) records licence, attribution, retrieval date and a hash. For each record, entity resolution tries LEI (GLEIF) first, then name plus country plus coordinates (the `userProjects.ts` cascade rules moved server-side), with a score. Each match falls into one of three bands:

- **Above the auto band:** linked.
- **In the review band:** queued for GEX staff.
- **Below:** new prospect.

Conflicts between a client's assertion and an external value are kept side by side (§3.2). Freshness: a record not seen in two consecutive snapshots is marked *stale*, never deleted.

### 7.3 Linking and onboarding an outsider

1. A member presses **Request introduction** on a prospect, or GEX staff choose **Propose link**.
2. A second staff member approves the entity match. This four-eye step is justified because a wrong link attaches a third party's data to a client.
3. The prospect registers. The account is PENDING and goes through the existing vetting (telephone, agreement, separation of duties).
4. On activation, the tenant is linked to the prospect. External values remain as `external_source`; the client's own values attach as `client_asserted`; nothing is overwritten.
5. The **GEX outsider** label switches to **GEX member · vetted**. Verification states don't change, because membership is not evidence.

### 7.4 Entitlement

A plan entitlement (`discovery`) is checked in one server dependency on every market, open-interest, prospect and export route, **in addition to** tenant RLS, project access and role policy. The UI reads the same entitlement to hide or upsell. One tier change should not require code changes in more than one place.

---

## 8. Remedies, consistency rules and checks

| # | Weakness | Root cause and affected decision | Smallest coherent change | Interface wording | Consistency rule and drift detection | Dependencies / migration | Acceptance check | Remaining limits |
|---|---|---|---|---|---|---|---|---|
| R1 | F06 self-verified tokens | Request model carries a trusted field. Buyers can't tell claimed from checked. | Drop `verification_state` from `TokenCreate`; server sets UNVERIFIED; transitions only via the reviewer route | "Claimed by the seller · not yet verified" | Test: any trusted state on create gets 422. Nightly: CONFIRMED tokens without a reviewer event. | Backfill: none (0 tokens live) | Probe 01 shows the stored state UNVERIFIED | Reviewer route for products is new (R7) |
| R2 | F09 mint 500 | `created_at` null in the response model | Return the row as stored (RETURNING), or make the field optional | — | Contract test on 201 body | None | Mint returns 201 with the token | — |
| R3 | F10, F11, F12 over-allocation, replay | Read-then-insert; rate arithmetic; no idempotency | `FOR UPDATE` on the capacity; tonnes per period; `Idempotency-Key` table | "Only 1,200 t are free in 2028-Q2" | Concurrency test (probe 06 inverted); replay test | Migration: idempotency table | Probe 06 ends at ≤ capacity; probe 04 gives one RFQ | Clock-skew edge cases |
| R4 | F13 stranded remainder | Listing reserves the whole token | Split before reserve (`token_split`) | "30 of 40 t listed; 10 t still available" | Sum of buckets = minted (test) | None | A partial listing leaves the rest MINTED | — |
| R5 | F04, F05 role drift | Menu-only policy | `market_policy` table used by `market_engine` and menu; guard `/tokenisation` | "Proposals are made by Commercial…" | Role × action contract test | D-B | Probe 03 gives 403 for CFO and engineer | — |
| R6 | F07, F08 unprovenanced CONFIRMED | Records confirmed by a decision, not by evidence | Demote per D-A; split badge "accepted by GEX" vs "verified" | "Claimed · source not recorded" | Guard: CONFIRMED requires `verified_by` that is not the importer **and** a document | D-A | No CONFIRMED row without a document hash | — |
| R7 | F21, F22, F23 assessment gap | No product, certificate or requirement records | `token_quality_spec`, `ci_basis`, `product_certificate` (+ coverage), RFQ requirement clauses; eligibility engine | §5.2, §6 | Assessment rows immutable; reassessment on change | New tables; D-F | Mismatch Incompatible at any price (check 6) | Scheme APIs (Phase 2 connectors) are export-only |
| R8 | F16 no publication | Screen not rebuilt after 087 | Listing wizard on existing APIs + R1–R4 | §5.2 wizard | — | R1–R4 | Check 10 | — |
| R9 | F18, F19 no enquiry | Only binding proposals exist | `market_enquiry` (thread, consent release) | §5.2 enquiry | Consent event in ledger | D-D | Check 10 | — |
| R10 | F17, F29 navigation | Buttons predate 23 Oct | Retarget 4 buttons, honour `?mode`; then the six-entry menu | §5.5 | `audit-menu.mjs` SIGNATURE updated | None for the retarget | Each button lands in the promised tab and filter (UI test) | — |
| R11 | F25–F27 Geomap and interest | No connector, no map, empty corpus | §7 flows; ecosystem storage to PostgreSQL with RLS; Interest tab | §5.2 prospect | Snapshot diff, stale marking | D-G, D-H; licence | Checks 7, 8 | Map library choice (MapLibre) |
| R12 | F03 dataset rule | Generic project rule on commercial data | Per-kind rule, as 113 did | — | Policy test per kind | JML per kind | Stakeholder can't read `deal_inputs` | — |

### 8.1 The ten required checks: where they stand today

| # | Check | Today | Evidence | Proposed acceptance test |
|---|---|---|---|---|
| 1 | A buyer sees approved offer data without seller economics or third-party deals | **Pass** (verified) | 112, 113 tests (negative-verified); live API | Keep both tests; add a listing-detail allowlist test |
| 2 | Menu, direct URL and API follow one policy | **Pass for market actions** (D-B, 14 Nov): the server refuses, the screens hide. Screen visibility itself still comes from `menuArchitecture` | `test_market_policy_pg.py`, `MarketPolicyScreens.test.tsx` | Keep; extend to enquiry routes as they are built |
| 3 | Ordinary users can't assign trusted verification states | **Pass** for tokens (Phase 0, 13 Nov). Open for the 41 marketplace records (F07, D-A). | `test_token_mint_pg.py` (3 cases, negative-verified) | Keep; add a nightly trusted-state-without-reviewer query |
| 4 | Concurrent allocations and repeats keep availability correct | **Pass** (Phase 0, migrations 114–115; the capacity rule now holds for any writer): mint lock and window, exact carving at listing and acceptance, idempotent replays; the database refuses a split that loses tonnes | `test_token_mint_pg.py`, `test_market_split_and_idempotency_pg.py`, `test_market_chain.py` | Inverted probe 06 and 04 |
| 5 | A pending or expired certificate can't appear verified | **Pass for product records** (116, 14 Nov): expiry derived at read time, submitter never verifies; `test_product_records_pg.py`. Was **not verifiable**: no product certificate exists. Self-declared CONFIRMED would display as "Verified" (F06). Gate evidence expiry works (rules 4.5.0). | `vocabulary.py`; `expire_evidence.py` | Expiry sweep test on `product_certificate` |
| 6 | A mandatory spec mismatch stays incompatible despite price | **Pass** (14 Nov, Phase 1 step 5): excluded at any price; a seller's proposal refused; auto-matching skips it | Probe 07 (before): score 100 | `test_compatibility.py`, `test_compatibility_pg.py` |
| 7 | An outsider with evidenced attributes keeps its outsider label | **Not implemented** | No prospect entity | Membership-axis test |
| 8 | Public Geomap views expose approved fields only | **Not implemented**; `redact_for_viewer` exists in code, but the endpoint 500s | `GET /ecosystem/projects` 500 | Public-view allowlist test |
| 9 | Changed data updates views and assessments without rewriting history | **Partial**: terms freeze, order events and contract versions keep history; there are no assessments | `record.freeze`, `tb_order_event` | Assessment immutability test |
| 10 | Producer and buyer complete publication, assessment and non-binding enquiry in an isolated scenario | **Pass** (14 Nov, Phase 1): capacity → mint → CI → listing (the wizard's calls) → anonymous search → compare (a cheaper rival over the CI limit excluded, its proposal refused) → enquiry → consent → binding proposal, both assessments stored | Probes 01, 02, 05 (before) | `test_discovery_journey_pg.py` |

---

## 9. Phased plan

| Phase | Scope | Owner roles | Depends on | Acceptance | Consequence of deferring |
|---|---|---|---|---|---|
| **0: Integrity and confidentiality** (before any paid user) | R1, R2, R3, R4, R5, R6, R12; 112 and 113 (done). **Done 13 Nov:** R1, R2, R3 (lock, window check, idempotency), R4 (exact carving), F30, F33, F34 — migration 114. **Waiting:** R5 on D-B, R6 on D-A, R12 per dataset kind. | Backend lead; CISO for the policy table; JML for D-A, D-B | — | Checks 1–4 pass; probes inverted to tests | Self-verified and double-sold product reaches buyers; role bypass. **Not deferrable.** |
| **1: Complete commercial journey** | R7, R8, R9, R10; Market, Detail, Compare, Wizard, Requirement, Enquiry, Deals; status labels; entitlement (D-H) | Product designer, frontend lead, backend lead; certifier liaison for D-F | Phase 0; D-C, D-D, D-E, D-F | Checks 5, 6, 9, 10 pass | Without it there is nothing to sell: users can't publish, compare or contact |
| **2: Geomap discovery** | R11; prospect model, ingestion, map, onboarding link, Interest tab | Data steward, backend, frontend; DPO for D-G | Phase 1; licences | Checks 7, 8 pass | Discovery limited to members; the network effect delayed |
| **3: Improvements** | Index pricing, scheme connectors inbound, notifications, Splink matching, LEI, exports | Various | Phase 2 | — | Manual effort; lower match quality |

The cheapest first step is still R10's retarget of four buttons, which is safe to do at any time. It doesn't change what the market can hold, so it doesn't by itself make anything sellable.

## 10. The smallest coherent paid release

**Promise:** "Find vetted e-fuel counterparties, see what is verified and what is only claimed, check fit against your requirement, and start a confidential, non-binding conversation."

| Capability | Needed | Today |
|---|---|---|
| Confidential economics and buyer lists | ✔ | **Satisfied** (112, 113, verified) |
| One permission policy across menu, URL and API | ✔ | **Fails** (F04, F05) |
| Trusted evidence states set only by reviewers | ✔ | **Satisfied for tokens** (F06 fixed); **fails** for marketplace records (F07, D-A) |
| Correct availability under concurrency | ✔ | **Satisfied** (F10–F13, F34 fixed in Phase 0) |
| Publish a firm or indicative listing from a screen | ✔ | **Fails** (F16); the mint API itself now answers 201 (F09 fixed) |
| Requirements with mandatory limits | ✔ | **Fails** (F22) |
| Search, filter, compare with explicit outcomes | ✔ | **Fails** (F21, F23) |
| Non-binding enquiry with consented contact | ✔ | **Fails** (F18, F19) |
| Paid entitlement on the server | ✔ | **Fails** (F28) |
| Binding proposal, four-eye confirmation, contract record | ✔ | **Satisfied** (`test_market_chain`, Phase 1 gate) |
| Evidence pack per contract | Nice to have | **Satisfied** (Phase 1/2) |
| Geomap outsiders | Only if promised | **Fails** (F25–F27); Phase 2 |
| Certifier-reviewed product certificates | ✔ for "verified" claims | **Unverified**: needs D-F and a reviewer appointed (none is today) |

Release 1 equals Phases 0 and 1. If the commercial promise includes outsiders, Phase 2 becomes part of the first paid release.

## 11. Limits of this assessment

- **Role comparison.** It was done server-side in the throwaway database: same company, three functions on the seller side and two on the buyer side. No live company has all three roles, and no live pure-buyer Commercial or CEO account exists (F32).
- **Interface for proposed features.** The wireframes are proposals and have not been tested with users.
- **Geomap's own hosting, access control and data** weren't available; only the schema template was.
- **Not exercised:** concurrency of listing acceptance under load, beyond the row-lock code and the existing chain test.
- **Probe state.** The probe file stays in `backend/tests/` as a re-runnable characterisation; it isn't collected by the suite. When R1–R5 land, invert its expectations into real tests.


## Appendix A. Annotated evidence (observed, 13 Nov 2026)

Orange numbered markers are clicks in order; red outlines are findings. Captured from the running application with the accounts in §2 (F32).

**buyer find 1.** Buyer Commercial opens Commercial menu (1), expands Negotiation (2), chooses Market Discovery (3).

![Buyer Commercial opens Commercial menu (1), expands Negotiation (2), chooses Market Discovery (3)](assets/journeys/buyer_find_1.jpg)

**buyer find 2.** Market Discovery: molecule is the only filter (4), zero listings with no detail page (5), free-text terms sent only with a binding proposal (6).

![Market Discovery: molecule is the only filter (4), zero listings with no detail page (5), free-text terms sent only with a binding proposal (6)](assets/journeys/buyer_find_2.jpg)

**buyer find 3.** Commercial menu again: Negotiation, RFQs (7–8).

![Commercial menu again: Negotiation, RFQs (7–8)](assets/journeys/buyer_find_3.jpg)

**buyer find 4.** RFQs screen: press Create RFQ.

![RFQs screen: press Create RFQ](assets/journeys/buyer_find_4.jpg)

**buyer find 5.** Create RFQ form: location and contact promised after match but never shown; no certification, CI, specification, Incoterm or validity fields.

![Create RFQ form: location and contact promised after match but never shown; no certification, CI, specification, Incoterm or validity fields](assets/journeys/buyer_find_5.jpg)

**buyer purchase 1.** Buyer opens Commercial menu and chooses Purchase.

![Buyer opens Commercial menu and chooses Purchase](assets/journeys/buyer_purchase_1.jpg)

**buyer purchase 2.** Purchase lists another project's feedstock inputs, not supplier offers; press Scan Supplier Offers.

![Purchase lists another project's feedstock inputs, not supplier offers; press Scan Supplier Offers](assets/journeys/buyer_purchase_2.jpg)

**buyer purchase 3.** Lands on the buyer's own matches (Buying tab), not on supply; Market discovery is one more click.

![Lands on the buyer's own matches (Buying tab), not on supply; Market discovery is one more click](assets/journeys/buyer_purchase_3.jpg)

**seller publish 1.** Seller opens Commercial, expands Market Data, chooses Capacity & Logistics.

![Seller opens Commercial, expands Market Data, chooses Capacity & Logistics](assets/journeys/seller_publish_1.jpg)

**seller publish 2.** Capacity & Logistics: four projects not listed; press List on Market.

![Capacity & Logistics: four projects not listed; press List on Market](assets/journeys/seller_publish_2.jpg)

**seller publish 3.** Lands on Commercial Overview, which has no listing form.

![Lands on Commercial Overview, which has no listing form](assets/journeys/seller_publish_3.jpg)

**seller publish 4.** Typed /tokenisation (no menu entry): press Create Capacity.

![Typed /tokenisation (no menu entry): press Create Capacity](assets/journeys/seller_publish_4.jpg)

**seller publish 5.** Back on Capacity & Logistics: a loop; no capacity, token or listing can be created.

![Back on Capacity & Logistics: a loop; no capacity, token or listing can be created](assets/journeys/seller_publish_5.jpg)

**seller sales 1.** Seller opens Commercial and chooses Sales.

![Seller opens Commercial and chooses Sales](assets/journeys/seller_sales_1.jpg)

**seller sales 2.** Sales: no buyer recorded; press Review Market Bids.

![Sales: no buyer recorded; press Review Market Bids](assets/journeys/seller_sales_2.jpg)

**seller sales 3.** Lands on Your Matches with Buying selected; the mode=sell parameter is ignored.

![Lands on Your Matches with Buying selected; the mode=sell parameter is ignored](assets/journeys/seller_sales_3.jpg)

**seller cfo 1.** Producer CFO's Commercial menu: no Market Discovery, RFQs or Matches.

![Producer CFO's Commercial menu: no Market Discovery, RFQs or Matches](assets/journeys/seller_cfo_1.jpg)

**seller cfo 2.** Typed /market-discovery is refused on screen, while the market API accepts this user's calls.

![Typed /market-discovery is refused on screen, while the market API accepts this user's calls](assets/journeys/seller_cfo_2.jpg)

**leak before 1.** Before migration 112: buyer sees seller's cost and margin (1), another buyer's pending deal (2), suppliers and unit prices (3).

![Before migration 112: buyer sees seller's cost and margin (1), another buyer's pending deal (2), suppliers and unit prices (3)](assets/journeys/leak_before_1.jpg)

**leak after 1.** After 112: buyer opens Commercial Overview.

![After 112: buyer opens Commercial Overview](assets/journeys/leak_after_1.jpg)

**leak after 2.** After 112: seller's cost, margin and break-even withheld (3); suppliers and prices withheld, with an explanatory note (4).

![After 112: seller's cost, margin and break-even withheld (3); suppliers and prices withheld, with an explanatory note (4)](assets/journeys/leak_after_2.jpg)

### Commercial menus by role

![Offtaker Commercial (prosumer) Commercial menu: 13 entries](assets/menus/buyer_commercial__menu_commercial.jpg)

![Offtaker CFO Commercial menu](assets/menus/buyer_cfo__menu_commercial.jpg)

![Producer CEO Commercial menu](assets/menus/seller_ceo__menu_commercial.jpg)

![Producer CFO Commercial menu](assets/menus/seller_cfo__menu_commercial.jpg)

### Probe output

`assets/probe_results_2026-11-13.json`: raw responses for probes 01–07 and 05e, run in the throwaway database.
