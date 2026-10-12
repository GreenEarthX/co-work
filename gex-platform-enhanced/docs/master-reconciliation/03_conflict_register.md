# 03 — Conflict register

Seeded from §4 of the reconciliation prompt, re-verified 2026-09-29 against the engine
(rules 4.1.0, `engine_export_rules_4.1.0.json`) and the market evidence
(`00_market_evidence_gate_timing.md`), and extended with what this run found (N-series).
**Statuses updated 2026-09-30 after Phase 4** (decisions D1–D17 accepted 29 Sep).

**Status:** Open · Resolved (where, in which deliverable) · Resolved in code (4.1.0) · Evidenced ·
Verify (needs a primary source) · Reopened (a later edit undid the resolution).
**Owner:** M = master (`GEX-Gates-Master_v2_redline.docx`) · G = GREENEARTHX
(`GREENEARTHX_redline.docx`) · B = Bridge v6 (archived; `05_bridge_v6_disposition.md`) · H =
`docs/CLAUDE_HANDOFF.md` · Code = separate code task.

**About the master:** JML edited the delivered redline in Word on 30 Sep (saved 14:38, Track
Changes off, §1 only). Statuses marked **Reopened** refer to that working copy; the details are in
`05_change_summary.md`, "Notes on JML's edits".

## A — The master is stale against the software

| ID | Where | Statement | Ground truth | Resolution | D# | Owner | Status |
|---|---|---|---|---|---|---|---|
| A1 | M §1.2, §1.4 "Correct", §4.4 | Six facts about rules 3.0.0: `_LENDER_GATES` waives G4/G6/G7/G8/G10; none of 77 items on technology; no offtaker view; no certificate before OPERATIONAL | 4.0.0 (27–28 Sep): item-level scope (23 lender items; only G6, G8 waived whole); 93 items with technology in G1 and FEED/licence/long-lead/EPC security/ITR in G5; OFFTAKER view and lens; G11 `certificates_issued`, `first_deliveries_accepted` | Facts kept as dated history (`[GEX 27 Sep]`), each followed by "Since rules 4.0.0 …"; §1.4 in past tense; §4.4 updated | D1 | M | Resolved — the per-fact "Since" notes were removed in JML's edit; the as-built facts remain in the front section and §1.6 |
| A2 | M §2 | Gate rows are proposals; G1 heading stale | G6 split built as `independent_technical_review` in **G5**; G10 "FID lock" built as item scope + FINANCEABLE requirements (O5/O7 effective, E6); G1 renamed | "As built (4.1.0)" row in every gate table; "Current lens" → "Lens in 3.0.0"; G1 heading and gate subtitles corrected; deviations recorded | D1, D10 | M | Resolved |
| A3 | M §1.6, §8.2–8.3 | Proposed changes; "coherence C1–C6 pass at Buildable"; "blocking from Buildable when both sides' data exist" | Implemented; C1–C3, C5–C8 at G4, C4 at G5, C10 at G8, C9 at G10; a FAIL blocks its gate, NOT_EVALUABLE never blocks and never passes; triggers T1–T3 only | §1.6 rewritten as what changed in 4.0.0/4.1.0; §8 renamed; §8.2 "Built:" per change + rows 9–10 (4.1.0); §8.3 "As built" column; §8.4 engine titles, gates, statuses, triggers | D1 | M | Resolved |
| A4 | M §4.1, §5 | O- and E-ladder wording | Engine definitions (glossary) | Definitions quoted verbatim; market ranges kept as context; derivation paragraphs added | D10 | M | Resolved |
| A5 | M §4.2 | Offtake card with fields the built card lacks | Five cards; offtake card per glossary incl. `planned_output_tonnes_per_year` | Proposed card kept as the table; "Built (rules 4.1.0)" and "Roadmap" paragraphs added | D10 | M | Resolved |
| A6 | M §8.6, §9, §10, legend | "What it would take in GEX"; "Nothing in GEX was changed"; source "rules 3.0.0"; `[GEX]` = 27 Sep | False since 4.0.0 | §8.6 replaced by "What GEX does and does not decide"; §9 rewritten; GEX sources restated without code paths; legend dated 30 Sep | D1 | M | Resolved |

## B — The master's own defects

| ID | Where | Statement | Problem | Resolution | D# | Owner | Status |
|---|---|---|---|---|---|---|---|
| B1 | M §1.4, §3 | "Your proposition…", "answer your question directly", "My inference" | Addressed to the questioner | Neutral voice; [I] → "GEX inference" | D2 | M | Resolved |
| B2 | M §1.1 | Test one contains both tests; test two restates the convergence | Logic folded in the rewrite | Two tests restored in JML's words | — | M | **Reopened** — JML's edit reduced test two to "the convergence the GEX mantra (Done now since 27Sep)" |
| B3 | M §1.3 | Definitions table | Grammar; no labels | Polished and labelled; the four "financed but not ready" cases stay in §7 | D1 | M | Resolved (JML's edit re-worded two cells; see change summary) |
| B4 | M §1.4 vs §11 | Guarantee "8–10 % of the subsidy" (CINEA officials) vs "8 % of the maximum grant" | Two numbers, unverified attribution | **Verified:** IF24 terms: 8 % of the maximum grant (up from 4 % in IF23); the quote is the European Commission's (Argus, 18 Sep 2025), which gave no reasons | — | M | **Reopened** — JML's edit removed the attribution and a closing parenthesis; the number (8 %) survived |
| B5 | M §11 | Unlabelled secondary sources; IF25 requirement list; cross-check table; three templates | Needed primary verification | Rewritten as §10 "Lessons from the EU Hydrogen Bank" from IF24 T&C, IF25 draft T&C and CINEA Q&A; unverifiable claims removed (N18); templates → Annex B, "illustrative, not legal advice"; template deadline corrected (N20) | D6 | M | Resolved |
| B6 | M front matter | Static TOC; §11 missing; subtitle "critique" | — | TOC entries edited, new entries added, field set to update on opening; new subtitle | D1 | M | Resolved — JML's copy has no subtitle and the TOC shows page 1 throughout: update the field (F9) once edits are done |
| B7 | M §1.2 | `[GEX]` labels removed | Document's own rule | Restored with dates | D2 | M | Resolved — JML's edit leaves a dangling `[GEX]` after each fact |

## C — The internal documents contradict the engine or the master

| ID | Where | Statement | Ground truth | Resolution | D# | Owner | Status |
|---|---|---|---|---|---|---|---|
| C1 | G §2.3, §3; B §3 | Offtaker HoT at G4, binding at G10; LOI pre-FEED, HoT at FEED, G4 at FID readiness | O2 + 60 % at COMMERCIALLY_PLAUSIBLE, O4 at G4, effective at FINANCEABLE; every financed deal sampled | G §2.3 row, §3 phase table and Gantt corrected; B archived | D12 | G, B | Resolved |
| C2 | G §2.3; B §3, §9 | Insurer binds at G7 | G7 insurability; G10 bound | G §2.3 "quotes terms at G7; binds at G10"; B archived | — | G, B | Resolved |
| C3 | G §2.1 note; entropy table | Senior debt and ECA gated behind G10; DFI at G10 | G6 DFI/Mezz/Guarantees; G8 Senior Debt Credit Approval (conditional); G10 Debt Drawdown; ECA not an engine type | G §2.1 note and entropy table corrected | D5 | G | Resolved |
| C4 | entropy table | Technology risk reduced by EPC (G5) + IE (G6) | Technology basis at G1; ITR in G5 | Entropy table corrected | — | G | Resolved |
| C5 | G §3 note | Coarse Gate 1–4 leaves G4, G7–G9 out | Glossary mapping | Dated correction after the (pending June) note | D10 | G | Resolved |
| C6 | G §5.1, §5.2, App. B; B §8 | Capital State Gates; two package ladders; funding and tranche states | No engine equivalents | Mappings added (CSG, tranche, funding → capital-commitment ladder); one package ladder (Bridge variant retired) | D5, D9 | G | Resolved |
| C7 | G §2.4, §6 | UNVERIFIED / SUBMITTED / CONFIRMED / AUDITED | Status + maturity + coherence | Mapping paragraph (§2.4) and pointer (§6); "AUDITED required for G10" corrected | D9 | G | Resolved |
| C8 | B; G §9, App. E | Quality score, Trust Score, Decomposed Certainty Stack, RAS | One determination per gate; derived ladders | No scores in client material; internal certainty stack marked derived (it is: `certainty_stack` from gate results); Trust Score removed from the entropy table; B rejected in the decision log | D4 | G, B | Resolved |
| C9 | B | "GEX does not block — visibility, not enforcement" | Engine blocks; funders enforce | Master §8.6 and front section; B decision log rows 5 and 24 | D3 | B, M | Resolved |
| C10 | B | No approval role, yet `approved` = internal governance; configurable thresholds | One standard | D16: no provider-configurable thresholds. The meaning of `approved` is open (O1 in `05_bridge_v6_disposition.md`) | D16 | B, G | Resolved in part — O1 open |
| C11 | G §9, B §11 | "DSCR is not shown before G10" | G8 audited base case; C10 | "DSCR is a lender metric at credit approval (G8), not a development dashboard" in G §3 and §9 | — | G | Resolved |
| C12 | G §5.10; B §6 | Two pre-COD metric sets; conflicting ECR; RAS ≥ 75 for G10 | FINANCEABLE needs O5/O7 effective | Flagged in G §3 and §5.10; kept out of the master; B's set not carried forward | D11 | G, B | Contained — one canonical, derived set still to be chosen |
| C13 | G front note, "The Future…", Bottom Line | Self-contradictory build status | Tree on 30 Sep | Re-verified and moved to H §8 item 39; section deleted (tracked) in G with a pointer | D9 | G, H | Resolved |
| C14 | B §4, §9; G §3.1, §5.8, App. E | Illustrations read as data | No cohort; no sources | Labelled "Illustrative" in G; B archived | D9 | G, B | Resolved |
| C15 | G §2.3 | "Persona" = actor types | Three axes | Column renamed "ABAC actor type"; terminology note (15 members verified) | D9 | G | Resolved |

## N — Found in Phases 1–4

| ID | Where | Finding | Resolution | D# | Owner | Status |
|---|---|---|---|---|---|---|
| N3 | M §11 table | "NZIA non-EU stack sourcing limits" | IF25: ≥ 75 % of electrolysers, stacks included, from outside **China**; IF24: Chinese stacks ≤ 25 % of capacity | — | M | Resolved |
| N5 | M §11 table | "Common rejection reason" column | No source found; table replaced by a requirement → GEX mapping | D6 | M | Resolved (removed) |
| N6 | G front matter | Version trail v4.5 / v4.4 / v4.2 | Reading note now v4.5; the v4.2 Bottom Line left with the status section | — | G | Resolved |
| N7 | engine 4.1.0 | New state labels | Master quotes them | — | M | Resolved |
| N8 | M §4.1, §6 | No 60 % coverage bar | Added (front section, §4.1, §6, §8.2 row 9, §10) | D13 | M | Resolved |
| N10 | G §2.3 | IE signs G6 for every project | Corrected | — | G | Resolved |
| N12 | frontend `FinanceBankabilityView.tsx` | Gate → capital "reasons" wrong for other capital types | Code task | D15 | Code | Open |
| N13 | M §10 | §11 sources lack dates and URLs | Sources added with dates | D6 | M | Resolved |
| N14 | engine 4.1.0 | Captive offtake needs a card | Decided: intra-group offtake card, no exemption; stated in master §4.1 and §10 (the Hydrogen Bank asks integrated projects for a director's letter reserving 60 %) | D14 | M | Resolved |
| N15 | M §11 | "The Commission adjusted the rules for IF25 and IF26: bidders must now submit HoTs for power and offtake" | IF24 T&C (25 Sep 2024) already required HoTs for ≥ 60 % of offtake and electricity. IF25 tightened recency (≤ 1 year), permits (submitted, timeline before FC), equity letters, the China rule | — | M | Resolved (§10) |
| N16 | M §11 | "Equity support for at least 60 % of total financing" | IF25: letters for ≥ 60 % of the total **projected equity** funding | — | M | Resolved (§10) |
| N17 | M §1.4 | "CINEA officials confirmed … due to permitting bottlenecks, grid delays, and unviable PPA pricing" | The Commission's statement gave no reasons (Argus, 18 Sep 2025); companies cited policy and infrastructure delays and uncertainty (Balkan Green Energy News, 23 Sep 2025); "unviable PPA pricing" not found | — | M | Resolved in redline; Reopened with B4 |
| N18 | M §11 | Unverifiable commentary: three reasons attributed to S&P (paywalled; not in the Commission's statement); "bidders treat auctions like free options" (not in Harper or CATF); EY/Hyvolution claim (the report is dated Feb 2025, before the withdrawals); "over half the budget sat idle", "severe market churn" (not in BGEN) | Removed; replaced by sourced views (EU official via BGEN; T. Harper, May 2026; CATF, Jul 2026; national associations via pv magazine, Jun 2026) | D6 | M | Resolved (removed, logged here) |
| N19 | M §1.4, §7, §10 | IF24 outcome missing | EC IF24 page: six grant agreements, €270.6m, 20 Jan 2026 | — | M | Resolved |
| N20 | M templates | First-gas date "not later than 5 years post-Auction Award" | IF24/IF25: entry into operation within 5 years of **grant-agreement signature** | D6 | M | Resolved (Annex B) |
| N21 | M §7 | Montana Renewables' DOE first tranche "~US$782m" | The Phase 0 research recorded ~US$778m; no primary source in hand | — | M | **Verify** (left unchanged) |
| N22 | engine | REFINANCING_ELIGIBLE is defined but never computed: it has no gates and the state climb skips states without requirements | Stated in the master's front table ("not yet computed"); implementing "OPERATIONAL + time" is a code decision | — | Code | Open |
| N23 | M working copy (JML, 30 Sep) | Untracked edits in §1: see B2, B4, B6, B7; also "Buyers refrain from signing a binding L-T offtake before EPC certainty" now asserted as fact under "Wrong" | Notes and suggested wording in `05_change_summary.md` | — | M | Open (for JML) |
| N24 | G June 2026 insertions (pending) | The v4.3 notes on gate mapping, personas and namespace are wrong (the namespace note describes `deal_engine`) | Left untouched; dated corrections follow each | D9 | G | Resolved |
| N25 | M §9 (my build) | The replacement lead-in "The review changed GEX. Rules 4.0.0 … section 2;" is bold beyond its first sentence | Redline library fixed; the working copy needs the bold removed after the first sentence | — | M | Open (cosmetic) |
| N26 | M §4.1 table | Header "What it tells you about project maturity" | D2 voice: "What it says about project maturity" | D2 | M | Open (cosmetic) |
