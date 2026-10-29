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
| **G-08** | **Delivery, routes, transport modes, title transfer.** | `deliveries` exists and is empty; routes deferred to B2/B3; GreenMesh title-transfer handlers are TODO (see G-12) | The physical half of a physical-commodity platform |
| **G-09** | **Order book, positions and swaps.** | No order or position tables; "swap" in the code means debt-for-nature instruments | Offers have a listing state machine, which is not an order book |
| **G-10** | **Counterparty blacklist / sanctions screening.** | Not found; KYC/KYB exist | The 2019 model had one; required for any real counterparty |
| **G-11** | **Take-or-pay, amortising and step-up schedules; novation.** | Deferred to B2/B3 in `trading_book` | Take-or-pay is the core of bankable offtake (see rules 4.1.0, O6) |

## P2 — GreenMesh: decide, then make code and documents agree

| ID | Gap | Evidence |
|---|---|---|
| **G-12** | **GreenMesh is dormant.** Its routes are imported (`main.py:127`, `HAS_GREENMESH`) but never mounted, and every handler is a TODO stub ("For now, return success"). Its engines are imported by nothing: `core/greenmesh_engine.py` (multilateral netting "FlowFusion", mass-balance clearing, certification-premium mapping) and `core/greenmesh_bankable.py` (quality verification before title transfer, take-or-pay compliance, penalties). Its tables (`production_readings`, `deliveries`, `quality_certificates`, `availability_reports`) are empty. | `api/v1/greenmesh.py:71-255` |
| **G-13** | **The documents describe GreenMesh three incompatible ways.** The Vademecum v4.4 marks the API "✅ Built (Tier 3)"; the Vademecum and the technical reference call `greenmesh_bankable.py` "Matrix/Synapse encrypted actor-to-actor rooms" (it is the physical supply-chain layer); the 30 Sep menu map uses "GreenMesh" as the label of the capacity screen. | `docs/product/Vademecum_v4.4.md:337,353`; `docs/GEX_Platform_Technical_Reference_v3.md:37,96`; `docs/menu-architecture-map.md:98,149` |

**Decision needed (JML):** GreenMesh as the physical layer of the platform — production, quality,
title transfer, netting — switched on as part of G-08, or retired and removed from the documents.
Either way, correct G-13.

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
