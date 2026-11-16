# GreenMesh economics — decision memo E1–E9

Drafted 13 Nov 2026 for JML. **Status: all nine DECIDED by JML on 13 Nov, all as recommended.**
**The gate is still closed** on E8's remaining condition, the certifier pre-assessment, which has not
happened. Economics code starts when it has. Source of the questions and of the
recommendations: `../docs/product/GreenMesh_Description_and_Vision.md` v2, *Economic ambition*
(the recommendations are the description's own; facts about the code were measured on 13 Nov).

## The gate

- **No economics or FlowFusion code is written until all nine are answered** (JML, re-confirmed
  13 Nov; `.claude/CLAUDE.md`). Three answers do not open a nine-question gate.
- **Order:** E1, E2 and E5 first, because they shape everything else. Then E3, E4, E6, E7 and E9.
  E8 closes the set.
- **E8 as written:** "after Phase 2 Step 3 and the certifier pre-assessment."
  - **Step 3 is complete** (heads 104–109, stopped before SETTLED).
  - **The certifier pre-assessment has not happened.** It is the only open half of E8. The final
    real-cargo audit (Step 7) is not part of E8.
- **When all nine are answered:** a build brief is written. Its first increment is the one already
  agreed in principle:
  - the allocator ported into the PF engine as a read-only, SCENARIO-labelled module;
  - it reads authorised platform API snapshots and is adapted to GEX's split-token and contract
    model;
  - none of the prototype's own API, authentication, Streamlit app or models is merged;
  - its tests are re-run in that environment.

## Decision record

Write the answer in the **Decision** column. "As recommended" is a valid answer.

| # | Decision | Recommendation (description v2) | Decision |
|---|---|---|---|
| E1 | Baseline | The producer's best confirmed bilateral offer, same volumes, quality and dates | **JML 13 Nov: as recommended.** Before FID, a labelled forecast baseline (SCENARIO, with its evidence grade), never shown as confirmed. |
| E2 | Objective | Producer netback, under the no-worse-off rule | **JML 13 Nov: as recommended.** Zero tolerance: every affected party keeps at least its baseline after costs and compensation. Compensation is budget-balanced and agreed by the parties in the proposal's confirmations. |
| E5 | Where it lives | PF engine, reading the platform's records | **JML 13 Nov: as recommended.** The PF engine reads a new read-only, dated, authorised platform snapshot endpoint scoped to opted-in companies. IRR, NPV and payback are built in the engine, not in the optimiser. Solver: `networkx` min-cost flow for level 1 (added to the engine's venv), SciPy/HiGHS when shared capacities and multi-party bundles need MILP. |
| E3 | Credit treatment | The lenders' own margin grid, never a GEX-invented rating map | **JML 13 Nov: as recommended.** Until a lender supplies a grid, the credit channel is left out (netback only), and every output says so. |
| E4 | Data sources | Reference-registry rows with source, proposed and approved like the hydrogen density; quotes for the pilot route | **JML 13 Nov: as recommended.** Freight, losses and differentials are registry rows through the two-person lifecycle. Pilot route quotes are per-scenario inputs labelled as quotes, not registry rows. |
| E6 | First project | FortaVerde, only with the client's consent; data kept local | **JML 13 Nov: as recommended.** Only after the client's written consent is recorded (JML, on the client's instruction); data local and git-ignored. Until then, synthetic data only. |
| E7 | Use of output | SCENARIO label everywhere; usable externally only with stated inputs and a disclaimer | **JML 13 Nov: as recommended.** SCENARIO on every figure, never shown as VERIFIED. External use only with the stated inputs and a disclaimer worded per the pitch-deck honesty guards. |
| E9 | Destination swaps | Put the question to the certifier in the same pre-assessment | **JML 13 Nov: as recommended.** Asked in the Phase 1 pre-assessment. Level 2 (swaps) is not built until the certifier answers; level 1 does not depend on it. |
| E8 | Timing | After Phase 2 Step 3 and the certifier pre-assessment | **JML 13 Nov: as written.** Step 3 is done. The certifier pre-assessment is the critical path, and economics code waits for it. |

---

## E1 — Baseline (first)

**Question.** Against what is a proposed allocation compared?

**Why it blocks.** Every saving is a difference from the baseline. A weak baseline (the
farthest supplier, an invented plan) manufactures savings.

**Recommendation.** The producer's best CONFIRMED bilateral offer for the same volumes, quality
and dates.

**What GEX has.**
- Confirmed trade terms: order-book and market trades, typed delivery, title, payment and
  commitment clauses (104, Step 4), physical flows per month.
- Offtake frames with buyers' confirmed cards.
- The prototype's baseline is "the existing feasible obligations"; it builds no farthest-supplier
  baseline.

**What the answer must also settle.**
- **Before FID there is no confirmed offer.** Is the baseline then a labelled forecast (a SCENARIO
  input with its evidence grade), or does the module refuse to compare? Recommendation: a labelled
  forecast, never presented as confirmed.
- **When there are several confirmed offers,** is "best" judged by netback or by price?

**Unblocks.** The comparison itself, the first thing the module computes.

## E2 — Objective (first)

**Question.** What does the optimiser maximise?

**Why it blocks.** Producer netback, system-wide transport cost and project IRR give different
"best" answers. Maximising one producer's margin is not minimising market cost.

**Recommendation.** Producer netback, under the no-worse-off rule: a reallocation happens only if
every affected party is at least as well off after costs and compensation.

**What GEX has.**
- Flows priced per contract (`trading_book/flows.py`), and payment-basis clauses.
- **No netback calculation.** Freight, losses and fees are not recorded anywhere.
- **The PF engine computes no IRR, NPV or payback:** `pf_engine/core/engine.py:386` returns
  `"project_irr": "TBD"`. "The PF engine reports the change in IRR" therefore needs that calculation
  built there first, as engine work, not inside the optimiser.

**What the answer must also settle.**
- **Compensation:** budget-balanced transfers between participants. Who agrees the split: the
  parties, in the proposal's confirmations?
- **The tolerance for "no worse off":** zero, or a stated margin each party consents to?

**Unblocks.** The objective function, and what a proposal reports per party.

## E5 — Where it lives (first)

**Question.** Platform backend or PF engine?

**Recommendation.** The PF engine, reading the platform's records.

**What GEX has.**
- **The PF engine** (`../gex_pf_engine`, :8001):
  - its own run log in PostgreSQL (role `gex_engine`, 082);
  - it already reads the platform's public fuel catalogue over the API;
  - it has no read path to contracts, deliveries, tokens or custody.
- **The platform** has the authorised readers: `/trading-book/records/{id}`, `/cashflows`,
  `/take-or-pay`, the deliveries, and the custody and upstream proof routes.
- **`networkx`**, which the prototype solver uses, is in neither the engine's nor the platform's
  environment.

**What the answer must also settle.**
- **The snapshot:** which platform endpoint serves a dated, authorised optimisation snapshot (a new
  read-only route, scoped to the companies that opted in)?
- **The solver library:** add `networkx` to the engine's environment, or use SciPy/HiGHS? The plan
  suggests HiGHS for the later mixed-integer stage.

**Unblocks.** Where the code goes, and the API contract between the two services.

## E3 — Credit treatment

**Question.** How does counterparty quality enter the economics?

**Recommendation.** The lenders' own margin grid, never a GEX-invented rating-to-cost map.

**What GEX has.**
- **No lender margin grid** in the reference registry.
- **`core/contractual_rating_engine.py`** exists. Any mapping it holds is not a lender's grid and
  must not be used as one.

**What the answer must also settle.**
- **Without a grid:** is the credit channel left out (netback only) until a lender supplies one?
  Recommendation: left out, said so in every output.

## E4 — Data sources

**Question.** Where do freight, losses and price differentials come from?

**Recommendation.** Reference-registry rows with their source, proposed and then approved like the
hydrogen density; quotes for the pilot route.

**What GEX has.**
- **The registry's lifecycle:** proposed, approved, superseded, with sources (061).
- **No freight, loss-rate or location-price-differential keys** exist in `reference_catalog.py`.

**What the answer must also settle.**
- **Who may approve these rows:** the same two-person registry approval as other reference data?
- **Whether pilot quotes are registry rows** or per-scenario inputs labelled as quotes.

## E6 — First project

**Question.** Which real case comes first?

**Recommendation.** FortaVerde, only with the client's consent; data kept local and git-ignored
(the co-work repository is public).

**What GEX has.**
- Tenant `mohring_energie`.
- **No recorded consent** for using its data in a scenario.

**What the answer must also settle.**
- **The form of consent and who gives it.** Until it is recorded, only synthetic data.

## E7 — Use of output

**Question.** Where may scenario figures go?

**Recommendation.** SCENARIO on every figure. Usable externally only with stated inputs and a
disclaimer.

**What GEX has.** The VERIFIED / DECLARED / MISSING labelling. SCENARIO would be a fourth label,
never shown as VERIFIED.

**What the answer must also settle.**
- **Decks and client material:** may a scenario figure appear in them at all (the `gex-pitch-deck`
  honesty guards), and with which wording?

## E9 — Destination swaps

**Question.** Is a location swap of intact, certified cargoes acceptable to the scheme?

**Why it matters.** Level 2 (bilateral swaps and novations before COD) depends on it.

**Recommendation.** Put the question to the certifier in the same pre-assessment as the Phase 1
pack.

**What GEX has.** Novation in the contract record (Q13, three confirmations), and per-cargo custody.

**What the answer must also settle.** **Who asks, and which certification body.** This is the same
open step as E8's pre-assessment.

## E8 — Timing (closes the set)

**Question.** When does economics work start?

**As written.** After Phase 2 Step 3 and the certifier pre-assessment.

**Where it stands.**
- **Phase 2 Step 3: done** (13 Nov).
- **Certifier pre-assessment: not done.** No certification body has reviewed a Phase 1 pack.

**What the answer must also settle.**
- **Whether E8 stays as written.** If it does, the pre-assessment (and with it E9's question) is the
  critical path, and nothing in the code can shorten it.

---

## What happens after the nine answers

1. Record the answers in this memo and in `.claude/CLAUDE.md` (which lifts the no-economics rule).
2. Write the economics build brief from them. Its increment A is the read-only, SCENARIO-labelled
   PF-engine module described above, built on GEX's split tokens, contracts and custody.
3. Port the allocator, and re-run its tests in the engine's environment. The prototype's 31 tests
   ran only in its own environment.
