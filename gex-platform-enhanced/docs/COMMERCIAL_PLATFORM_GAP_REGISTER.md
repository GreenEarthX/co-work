# GEX commercial platform — gap register

**Measured 2026-10-23** against the code and the live database (head 062; **064** after the P0
work below — see the status table). Where this file and
the code disagree, the code wins: re-measure, then fix this file.

**The aim.** GEX as a solid, current commercial platform for e-fuels and biofuels — buying and
selling physical green-fuel products, with tokens recording and following every transaction.
("Trading" is avoided as a headline word because it has too many meanings; `app/trading_book`
defines it for GEX as *"Buy/Sell physical tokenised green-fuel products plus optional
paper/derivatives"*.)

**Starting point.** The 2019 CFS data model (`Obsolete_GEX/GEX_ex_CFS/CFS_graph_from_2019.pdf`): products
(planned position, fixed-price contract, index-linked contract, swap) → legs (pay/receive) → dated
flows (physical, fixed cash, floating cash on index + spread); index definitions and history;
deliveries with routes and container types; orders (side, all-or-nothing, maturity, status);
accounts, customers and a counterparty blacklist. `app/trading_book` is its declared phase B1.

**How to read the gaps.** They are ordered by what unblocks the **first real tokenised trade**:
capacity → token → offer/RFQ → match → contract → settlement → carbon attribution → retirement,
with every step recorded. P0 blocks that trade. P1 is needed for a commercial platform beyond it.
P2 and P3 concern GreenMesh and the molecule-to-asset pathway.

---

## The foundations that are sound

- **Token lifecycle with no double counting.** `tokens_sqlite.py:122` — MINTED → RESERVED →
  MATCHED → SETTLED → RETIRED; VOIDED and ANNULLED terminal; no path from RETIRED back to a
  claimable state, proven by graph reachability in `tests/test_token_lifecycle.py`. Annulling a
  retirement needs named authority, a rationale and separation of duties.
- **Tokens carry their provenance.** Minted from a capacity, inheriting its `correlation_id`;
  molecule, certifications, carbon intensity, certification pathway, `mass_balance_lot_id`.
- **The chain is modelled end to end.** Token IDs appear in offers, matches, contracts, settlement
  events and carbon attribution. Settlement is the cash leg (PENDING → CONFIRMED → RECONCILED, or
  DISPUTED), keyed to contract and token; carbon attribution requires a settlement.
- **The 2019 contract core is ported.** `app/trading_book/models.py`: Asset, Counterparty,
  IndexDefinition/IndexHistory, Contract → FixedPriceContract | IndexLinkedContract,
  ProjectFinanceLink, and a cashflow generator feeding the project-finance engine.
- **Accounts and access.** Vetted accounts, KYC/KYB, tenant isolation (RLS), separation of duties,
  evidence gates and reviewer appointments — the permissioned layer a commercial platform needs.

## What the live database shows

Every commercial table is empty: `offers`, `matches`, `offtake_contracts`, `tokens`,
`settlement_events`, `carbon_attribution_events`, `mass_balance_allocations`, `deliveries`,
`quality_certificates`, `production_readings`, `tb_contract`, `tb_asset`, `tb_counterparty`,
`tb_index_history`, `sovereign_instruments`, `open_interests`, `buyer_mandates` — all **0**.
Only `capacities` (5, created 27 May 2026), `mass_balance_lots` (72) and `development_packages`
(3) hold rows. **The chain has never carried a transaction.** There was no `rfqs` table in
PostgreSQL or in the SQLite file. *(Since 063 `rfqs` exists in PostgreSQL only — see below.)*

---

## P0 — blocks the first tokenised trade

| ID | Gap | Evidence | What done looks like |
|---|---|---|---|
| **G-01** | **RFQs and the matching run fail on every call.** Both RFQ endpoints write to `rfqs`, and the matching run reads it; no migration, script or module creates that table in either store. | `trader_rfqs.py:23-25` (always opens SQLite), `matching_sqlite.py:109` (POST /rfqs), `matching_sqlite.py:255` (POST /run reads `FROM rfqs`); `to_regclass('rfqs')` is null | A migration owns `rfqs` with RLS; both modules use the market connection; a test creates an RFQ and runs a match |
| **G-02** | **Trades do not move tokens.** Matching, contracts and settlement never update a token's state; a token changes only through `POST /tokens/{id}/transition` by hand. | No `UPDATE tokens` in `matching_sqlite.py`, `contracts_sqlite.py`, `settlement_events.py` | Accepting a match reserves/matches the token; confirming settlement settles it; retirement follows the attribution — each in the same transaction as the trade step |
| **G-03** | **The audit trail breaks partway.** Matching and settlement emit no events; `correlation_id` stops at contracts, so settlement and attribution cannot be traced back to the capacity. | Event emits: matching 0, settlement 0, carbon attribution 0; `correlation_id`: settlement 0, attribution 0 | One `correlation_id` from capacity to retirement; every state change written to the event ledger |
| **G-04** | **Half the trading screens show built-in sample data.** | Capacity (`CapacityPage.tsx:87`), Marketplace (`MarketplacePage.tsx:331`), Matching, Trader dashboard, Lineage call no trading API; RFQs and Market discovery are placeholders (`App.tsx:196-197`) | Every screen in the chain reads and writes through the API; sample arrays removed |
| **G-05** | **The trading book cannot record a contract.** Its API has three read endpoints — health, contract list, cashflow projection — and no create or update. | `app/trading_book/api.py` | Create/update for asset, counterparty, index definition and history, fixed-price and index-linked contracts, with the access rules the rest of the platform applies |
| **G-06** | **No test exercises the chain.** Four test files touch it (`test_token_lifecycle`, `test_marketplace_slice`, `test_open_interest`, `…_routes`); matching, contracts, settlement, mass balance and carbon attribution have none. | `backend/tests/` | One end-to-end test: capacity → token → offer → match → contract → settlement → attribution → retirement, asserting token state and the event trail at each step; negative-verified |

### Status — 2026-10-23 (G-01 to G-05 addressed; JML: anonymised listings, both parties accept)

| ID | State | What changed | Proof |
|---|---|---|---|
| G-01 | **Closed** | Alembic **063** creates `rfqs` and `contracts` (FORCED RLS, every policy with WITH CHECK); The market is **PostgreSQL only** (JML, 2026-10-23): the engine refuses without it and no SQLite definition exists. `trader_rfqs`, `matching_sqlite` and `contracts_sqlite` delegate to `core/market_engine.py` | `test_market_chain.py` (12, in a throwaway PostgreSQL database), `test_market_chain_pg.py` (6), `test_marketplace_slice.py` (tables exist; engine has no SQLite path; refuses without PostgreSQL) |
| G-02 | **Closed to settlement** | Listing reserves the token (MINTED→RESERVED); withdrawal releases it; BOTH acceptances → MATCHED; the payee's confirmation → SETTLED and `tokens.holder_company_id` = buyer. Status can no longer be set by hand (`PATCH …/status` → 409) | `test_market_chain.py` steps 1, 5, 7, 12 |
| G-03 | **Closed to settlement** | One `correlation_id` from token to settlement and attribution (063 adds it to `settlement_events` and `carbon_attribution_events`); every step written to the event ledger; `GET /api/v1/market/trail/{id}` for the two parties only | `test_market_chain.py::test_8` (one id, 3 token transitions, outsider 404) |
| G-04 | **Closed, one honest gap** | Market Discovery and RFQs routed and live; Trader dashboard, Matching, Lineage, Capacity, Marketplace procurement read the market API; sample arrays deleted. Feedstock pooling (GreenMesh upstream) has no backend, so its tab now says so instead of showing six invented pools | `MarketScreens.test.tsx` (5); browser check 2026-10-23 against the live database |
| G-05 | **Closed** | Alembic **064**: `tb_asset.project_id`, `tb_contract.owner_company_id`, real tenant policies replacing 036's admin-only lock. Create/update for assets, counterparties, indices (GEX staff), fixed-price and index-linked contracts, project-finance links. The trading book now runs on PostgreSQL as `gex_app` | `test_trading_book_api.py` (7), `test_trading_book_pg.py` (6) |

**PostgreSQL only — JML, 2026-10-23.** The whole market and trading area has no SQLite path:
capacities, tokens, offers, RFQs, matches and buyer mandates, contracts, settlements, carbon
attribution, chain of custody and the trading book. Each module calls
`db_backend.require_postgres()`; with its switch not `postgres` it answers **503
POSTGRES_REQUIRED** instead of opening `gex_platform.db`. No runtime DDL remains for these
tables (the migrations own them). Unused legacy code went with it: the `RFQ` model in
`app/db/models.py` and `app/services/matching_engine.py`. Tests run in a throwaway PostgreSQL
database built by the migrations (`conftest.pg_store`); guarded by
`test_marketplace_slice.py` (no `sqlite3` in 12 modules; each refuses without PostgreSQL),
negative-verified.

**The trading-book revision supersedes part of this (JML, 2026-10-23).** The market tables of
063 (`offers`, `rfqs`, `matches`, `contracts`) are to be **replaced** by the spec's single
terms → legs → flows model (migration 065 built it; the engine moves in M3/M4). Automated
matching is **switched off** pending counsel — matching is bilateral, a company proposes to a
specific listing and both accept. The contract token is separate from the capacity token and
refers to it. Details and next steps: `docs/CLAUDE_HANDOFF.md` §8 item 46.

**Data held in code (audit of 2026-10-23, JML: "all variables and data points in PostgreSQL").**
Fixed for the market screens (handoff §8 item 47): Marketplace records now in PostgreSQL as
UNVERIFIED (066), placeholders and synthetic charts removed, Counterparties built. **Progress 2026-10-25 (handoff §8 item 48):** project access, profiles,
context seeds, risk flags and profile intelligence moved to PostgreSQL (067/068); spot prices
approved and Marketplace records confirmed. **Part 2 done (069, item 49):** project truth,
structuring, drawdowns, adjacency, aliases. **Still open:** the frontend's own per-project data
(about 15 screens) — **done 2026-10-25 (071, item 51)**: per-project datasets in PostgreSQL,
UNVERIFIED, awaiting confirmation. **CISO workspace done (070, item 50):** real accounts, sign-ins, barriers;
not-recorded where nothing is stored. **Was open:** projects themselves — `frontend/src/data/customerProjects.ts` still supplies bankability,
gates and offtakes to most screens, and `project_registry.PROJECT_ACCESS_PROFILES` (owners,
lenders) is code; vocabulary lists `trading_book/schemas.py` KNOWN_*. The match threshold and
score weights stay in code by decision (method, not data).

Not done: retirement through the market (G-02/G-03 stop at settlement; retirement stays the
evidenced `POST /tokens/{id}/transition`), and G-06's attribution → retirement leg.

**First milestone:** G-01 to G-06 closed, and one synthetic, labelled TEST trade carried through
the chain in a throwaway store — the same method as the comprehension fixture.

## P1 — needed beyond the first trade (the rest of the 2019 model)

| ID | Gap | Evidence | Note |
|---|---|---|---|
| **G-07** | **Legs and flows** — physical, fixed-cash and floating-cash flows per contract. | Deferred to B2/B3, `trading_book/models.py:15-20` | Needed for index-linked pricing per delivery period and for swaps |
| **G-08** | **PARTLY CLOSED 2026-11-12 (Phase 2 Step 2, migration 103):** deliveries are a typed record on the contract chain (schedule, dispatch, receipt, inspection, dispute; mode, route, Incoterm from the confirmed terms; draws bounded by custody allocation). **2026-11-13 (Step 3 sub-steps 1–3, heads 104–107):** typed risk/title/payment clauses, risk derived from the Incoterm, the inspector, certificate, ACCEPTED/REJECTED and waivers. **Still open:** the DISPUTED exit, title transfer and the token split (Step 3 sub-steps 4–5), settlement on a delivery; routes beyond origin and destination. **Delivery, routes, transport modes, title transfer.** | `deliveries` exists and is empty; routes deferred to B2/B3; the GreenMesh stub's title-transfer handlers were TODO and were retired 2026-11-12 (G-12); Phase 2 builds delivery and title transfer on the market engine and the chain-of-custody ledger, with `docs/design/greenmesh_physical_layer_reference.py` as its design source | The physical half of a physical-commodity platform |
| **G-09** | **Order book, positions and swaps.** | No order or position tables; "swap" in the code means debt-for-nature instruments | Offers have a listing state machine, which is not an order book |
| **G-10** | **Counterparty blacklist / sanctions screening.** | Not found; KYC/KYB exist | The 2019 model had one; required for any real counterparty |
| **G-11** | **Take-or-pay, amortising and step-up schedules; novation.** *(2026-11-13, Phase 2 Step 4: take-or-pay SHORTFALL built for trade contracts: a typed `commitment` clause (TAKE_OR_PAY, take_or_pay_pct, optional shortfall_price), contract years from the first physical period, accepted deliveries counted in the year of the flow they fulfil; an amount only with a stated price; waivers count DECLARED; `GET /trading-book/records/{id}/take-or-pay`. Still open: amortising and step-up schedules; take-or-pay on offtake-frame CARDS, whose sub-legs carry no deliveries; availability guarantees and penalties (no such terms exist).)* | Deferred to B2/B3 in `trading_book` | Take-or-pay is the core of bankable offtake (see rules 4.1.0, O6) |

## P2 — GreenMesh: decide, then make code and documents agree

| ID | Gap | Evidence |
|---|---|---|
| **G-12** | **GreenMesh is dormant.** Its routes are imported (`main.py:127`, `HAS_GREENMESH`) but never mounted, and every handler is a TODO stub ("For now, return success"). Its engines are imported by nothing: `core/greenmesh_engine.py` (multilateral netting "FlowFusion", mass-balance clearing, certification-premium mapping) and `core/greenmesh_bankable.py` (quality verification before title transfer, take-or-pay compliance, penalties). Its tables (`production_readings`, `deliveries`, `quality_certificates`, `availability_reports`) are empty. | `api/v1/greenmesh.py:71-255` (as of 2026-11-11). **Decided and done 2026-11-12 (JML; Phase 1 Step 1):** GreenMesh is kept only as the physical-delivery and clearing extension of `core/market_engine.py` and `api/v1/mass_balance.py`. The stub router was unimported and retired; `greenmesh_engine.py` retired, its certification premiums ported to the reference registry as 13 INDICATIVE `proposed` rows (`certification_premium_<regime>`, none in force); `greenmesh_bankable.py` moved to `docs/design/` as the Phase 2 reference, not wired; the PF engine's "GreenMesh rollup" is `portfolio_rollup` (`/pf/offtake/portfolio-rollup`, old route a deprecated alias for one release). Netting is Phase 3. Retired files: `../_claude_backups/2026-11-12_greenmesh_phase1/_to_delete/`. **Open:** the four tables listed here are untouched and still empty; Phase 2 decides their fate. |
| **G-13** | **The documents describe GreenMesh three incompatible ways.** The Vademecum v4.4 marks the API "✅ Built (Tier 3)"; the Vademecum and the technical reference call `greenmesh_bankable.py` "Matrix/Synapse encrypted actor-to-actor rooms" (it is the physical supply-chain layer); the 30 Sep menu map uses "GreenMesh" as the label of the capacity screen. | `docs/product/Vademecum_v4.4.md:337,353`; `docs/GEX_Platform_Technical_Reference_v3.md:37,96`; `docs/menu-architecture-map.md:98,149`. **Corrected 2026-11-12:** Vademecum lines 337, 353, 368, 420, 451; both copies of the technical reference (diagram, three tree entries, the `greenmesh_bankable.py` section); both menu documents; the screen and menu are now "Capacity & Logistics". **Left as written:** version-history entries (Vademecum lines 16 and 1011, technical reference v2.0 row), and the copy at `files/GEX_Handoff_Reference/design/menu-architecture-map.md` (a handoff snapshot). |

**Decided (JML, 2026-11-12): kept as the physical extension of the market engine, separate engine retired — see G-12.** The question was: GreenMesh as the physical layer of the platform — production, quality,
title transfer, netting — switched on as part of G-08, or retired and removed from the documents.
Either way, correct G-13.

Analysis and proposal for this decision (draft, 2026-11-12): `../../docs/product/GreenMesh_Description_and_Vision.md`.

**GreenMesh Phase 1, Step 2 (2026-11-12, migration 097): the chain of custody is period-based.**
Accounting periods per facility, molecule and pathway; input consignments with evidence
references, hash-chained; declared conversion factors, versioned; a lot beyond inputs x
conversion is flagged; a withdrawal beyond the period balance is refused; closing writes the
statement (opening + inputs x conversion − withdrawals = closing) and its hash, and a closed
period never changes (trigger); a period lot carries validated characteristics. Allocations
link the token (`tokens.mass_balance_lot_id`). **Still declared, not verified:** inputs,
characteristics and factors (Steps 3–5 address metering, correlation and the evidence pack).
**Scheme rules** (period length, carry-forward, negative interim balance) are a table that ships
EMPTY: the certifier's values are not yet recorded, so the ledger applies the conservative reading.

| ID | Gap | Evidence |
|---|---|---|
| **G-19** | **CLOSED 2026-11-12 (Phase 2 Step 1, JML D8):** backup `gex_platform_2026-11-12_1616.dump`, the 72 rows archived to `_claude_backups/2026-11-12_greenmesh_phase2/G-19_mass_balance_lots_test_72.csv`, then deleted; nothing referenced them (no allocation, token or period). **72 TEST lots sit on a real client project.** `mass_balance_lots` holds 72 rows with `created_by = 'test'`, all on `proj_etf_pecos1` (ETFuels), created 8–22 Sep 2026 — left by test runs before the custody tests moved to a throwaway database. No allocations. Not removed (no deletion without JML). | `SELECT count(*) FROM mass_balance_lots WHERE created_by = 'test'` |
| **G-20** | **CLOSED 2026-11-12 (Phase 2 Step 1):** every custody write records `request_tenant.current_user()`; body `*_by` values are ignored (logged when different); no signed-in user → 401. **Chain-of-custody actors come from the request body.** `created_by`, `allocated_by`, `opened_by`, `recorded_by` and `closed_by` are whatever the caller sends, not the token's user, unlike evidence review. | `api/v1/mass_balance.py` |
| **G-21** | **CLOSED 2026-11-12 (Phase 2 Step 1, migration 100):** reads unchanged, writes owner or GEX only, on `mass_balance_lots` AND `deliveries` (the same hole); reproduced first, `test_custody_write_policies_pg.py`. **`mass_balance_lots` lets project-access holders write.** Its 044 policy is FOR ALL with no WITH CHECK, so a reviewer or lender with `project_access` may create lots. The 097 tables and allocations allow only the owner and GEX to write. | `044_domain_tail_slice.py:651-662` |
| **G-22** | **CLOSED 2026-11-12 (Phase 2 Step 1, migration 102):** hydrogen Nm³ and Nm³/h convert with the APPROVED row `h2_density_normal_0c_101325pa` and the reading keeps its id; actual m³ stays refused. The density is PROPOSED (0.08988 kg/m³, not checked against NIST): Nm³ is refused until someone confirms and approves it. **Volumetric meter readings are refused.** Hydrogen meters often report Nm³ or m³/h; converting to kg needs a density (and its reference conditions) that nobody has agreed, so since 098 such a reading is refused rather than converted. Decide the density, record it as reference data, then accept the unit. | `core/ot_boundary.py` `normalise_metered` |
| **G-23** | **CLOSED 2026-11-13 (migration 110; JML: "build the G-23 upstream proof"):** an H2 input may name `source_token_id`, a hydrogen token its company HOLDS by title transfer (109), in state SETTLED. Its RFNBO result is carried by `core/upstream_proof.py`: on the operator connection, after checking the holder, token -> root -> lot -> period, the CLOSED statement re-verified, and only the proof fields returned (`GET /chain-of-custody/upstream-proof/{token}`, 404 to a non-holder). Inputs citing a token never exceed its kg, and a cited token can no longer be RETIRED (110's triggers). `test_upstream_proof_pg.py`. *Earlier notes:* *(2026-11-13: still open. Step 3's title moves TOKENS, not custody lots, so a buyer still cannot name the seller's hydrogen lot as an input. Candidate fix, from the FlowFusion plan of 13 Nov: a permissioned upstream proof the buyer reads but never writes (lot and period reference, quantity allocated, rules, verified statement hash, result), resolved through the custody and access services; missing proof stays UNVERIFIED.)* **A hydrogen input can name only a source lot its company may write.** `coc_input.source_lot_id` (101) locks the source lot `FOR UPDATE`, which RLS allows only to the lot's owner or GEX, so a company buying hydrogen from ANOTHER company's lot cannot name it and its hydrogen stays UNVERIFIED downstream. Fine for an integrated producer (the D7 pilot); needs a buyer-side read of the seller's lot, or a transfer of the lot on title (Phase 2 Step 3), before a merchant hydrogen supply can carry its correlation. | `core/custody_ledger.py` `_source_lot` |
| **G-24** | **Market trades carry no typed delivery, title or payment clause.** Corrected 2026-11-12 (ruling R1: the Incoterm governs RISK only; title follows a title clause). The market writes free-text clauses (`delivery_terms`, `delivery_type`, `delivery_basis`, `payment_terms`), which are never read as typed clauses (`trading_book/clauses.py`). A delivery on a market trade therefore reports `risk_basis`, `title_basis` and `payment_basis` all MISSING: risk cannot pass, title cannot pass (no title clause), no payment clause governs. The market's listing, RFQ and match terms must capture the typed fields before a market trade can do any of the three. Market trades are unchanged in Step 3 (B6), except R2: on a contract with deliveries, the market settlement no longer moves token or holder. | `core/market_engine.py` clauses, `trading_book/clauses.py` |
| **G-25** | **CLOSED 2026-11-13 (JML P2, migration 105):** an order-book sell order may name one MINTED token of the seller's own project (firm, all-or-nothing, same commodity); open reserves it, cancel releases it, acceptance puts it on the contract and matches it; `tb_order.origin_book` keeps it out of the market's listing views. `test_order_book_token_pg.py`. **No path makes a contract with both tokens and typed clauses.** Found 2026-11-12 (Step 3 sub-step 1). A delivery draws on the contract's TOKENS (103). Only market listings put a token on a contract, and market terms carry no typed clauses (G-24). Order-book orders carry typed clauses, but neither their route nor `order_book.create_order` takes a token, although `tb_order.token_id` exists (087: a listing is a firm sell `tb_order`). So no contract can yet schedule a delivery AND have risk, title or payment governed. Step 3 sub-steps 2–5 need one; waiting on JML. | `core/order_book.py` `create_order`, `api/v1/routes_order_book.py` `OrderIn` |
| **G-26** | **Partial acceptance by quantity.** Step 3 accepts or rejects a delivery as a whole (amendment B4). Accepting part of a cargo (part on-spec, part rejected) is out of scope. | `core/delivery_record.py` |
| **G-27** | **Title on payment in full is not built.** A title clause `ON_PAYMENT_IN_FULL` (retention of title) waits for a payment-in-full record on the delivery, and settlement comes after Step 3. Such a delivery stays ACCEPTED, saying why (`DELIVERY_TITLE_ON_PAYMENT_NOT_BUILT`). The payment clause's quantity basis and trigger (P1) are not applied yet either. | `core/delivery_title.py`, alembic 109 |

## P3 — molecule to asset

The thesis lives in one document, `docs/MOLECULE_TO_ASSET_KILLER_PROMPT.md` (2026-03-26), linked
from the platform README; it is absent from the documents index (`files/docs/README.md`). Its
product lane, against the software:

| ID | Element | State |
|---|---|---|
| — | Permissioned review | ✅ Access rules, gates, data room, reviewer appointments |
| **G-14** | Token passport | ⚠️ The data is on the token (certifications, carbon intensity, mass-balance lot, provenance); no passport view or endpoint |
| **G-15** | Cash-flow bridge | ⚠️ WACC, forward curves, the PF engine and trading-book cashflows exist, not tied to token exposure |
| **G-16** | Policy simulator (RFNBO, 45V, CCfD, export premium, freight) | ⚠️ Thin; nothing for CCfD |
| **G-17** | **Transition gate, asset slices, capital release from a slice sale, portfolio constructor** | ❌ Absent. "Capital release" in the code means project drawdown |
| **G-18** | The thesis in the strategy documents | ❌ Only the March prompt; not in the index, the Vademecum or the 12-gates reference. Its companion, `OBJECTIVE_LED_PRODUCT_PATHWAY.md` (same day), is about molecule-specific screens and does not address the pathway, tokens as transaction records, or GreenMesh |

**Decision needed (JML), before any build:** what an "asset slice" is legally. A transferable
share in a project company offered to investors is likely to be a security (in the EU,
MiFID II and the Prospectus Regulation; elsewhere their equivalents), unlike a token recording
title to a molecule. That decides whether G-17 is a product feature or a regulated activity —
take legal advice first.

---

## Order of work

1. **P0, in order G-01 → G-06**, ending with the first synthetic tokenised trade in a throwaway store.
2. **The GreenMesh decision (G-12)** and the document fixes (G-13), which are cheap either way.
3. **P1**, starting with G-11 (take-or-pay) and G-08 (delivery and title transfer), which the
   bankability rules already depend on.
4. **P3** only after the legal question on asset slices is answered.

## Sources

Code: `backend/app/api/v1/{tokens_sqlite,marketplace_sqlite,matching_sqlite,contracts_sqlite,settlement_events,carbon_attribution,mass_balance,trader_rfqs,greenmesh}.py`
(the `_sqlite` file names are historical — since 2026-10-23 none of them uses SQLite),
`backend/app/core/market_engine.py`,
`backend/app/trading_book/`, `backend/app/core/greenmesh_*.py`, `frontend/src/App.tsx` and the
pages named above. Data: live database 2026-10-23 (counts above) and backup
`gex_platform_2026-10-23_1124.dump`. Documents: `docs/MOLECULE_TO_ASSET_KILLER_PROMPT.md`,
`docs/OBJECTIVE_LED_PRODUCT_PATHWAY.md`, the Vademecum v4.4, the technical reference v3 and the
menu-architecture map.

**2026-10-28 — gate pathway loopholes closed (handoff §8 item 52).** Displayed gate figures are the
engine's only; unrunnable cross-checks hold a gate UNRESOLVED; every change re-evaluates and reports;
premises need a document and a second party; contract terms count only once confirmed on the
contract token by the counterparty (or an appointed reviewer). Open: merge with the trading-book
token (M2–M6); appoint reviewers on real projects.
