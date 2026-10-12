# 01 — Inventory of the three documents

Phase 1 of `docs/GEX_MASTER_DOC_RECONCILIATION_PROMPT.md`, run 2026-09-29 against:

| Document | File | SHA-256 (at read) | Words |
|---|---|---|---|
| Master (JML modified) | `gex-platform-enhanced/docs/GEX-Gates-Multi-Party-Review_JML modified.docx` (28 Sep 22:40) | `a311a7b7…666639` | ~12.1k |
| GREENEARTHX v4.5 | `GEX_Handoff_Reference/design/GREENEARTHX.docx` (29 Sep 16:46) | `630d5130…084e94` | ~19.0k |
| Development-to-Capital Bridge v6 | `docs/word-docs/Development-to-Capital Bridge_v6.docx` (15 May) | `e2bdebc5…bb3a9a` | ~9.7k |

Fact base: engine rules **4.1.0** (`engine_export_rules_4.1.0.json`). Market evidence:
`00_market_evidence_gate_timing.md`. Conflict IDs refer to `03_conflict_register.md`.

**Kinds:** concept · as-built fact · proposal · market evidence · spec · status · working note · template.
**Dispositions:** master body · master annex · stays internal · archive · drop.

## Master — JML modified (client-facing target)

| Section | Words | Kind | State against 4.1.0 | Disposition | Conflicts |
|---|---|---|---|---|---|
| Front matter: title, tagline, evidence legend, hand-typed TOC | 422 | framing | subtitle still "A multi-stakeholder critique"; TOC static, omits §11; `[GEX]` dated 27 Sep | master body — regenerate TOC, new subtitle, legend date | B6, B7 |
| 1.1 GEX Current view | 148 | concept (critique) | says the engine "does not yet compute" convergence — it does, partly, since 4.0.0; two tests folded into one | master body as dated "why the gates look like this" | B2, A1 |
| 1.2 Six facts from the engine | 322 | as-built fact (3.0.0) | all six superseded by 4.0.0; `[GEX]` labels removed | master body → dated history of the 3.0.0 review | A1, B7 |
| 1.3 Terms Conflation Avoidance — Definitions | 109 | concept | valid; grammar; unlabelled | master body (polish, labels) | B3 |
| 1.4 Correct / incomplete / wrong | 715 | concept + market evidence | addressed to "you"; H2 Bank guarantee "8–10 %" | master body, re-voiced; guarantee 8 % (IF25) | B1, B4 |
| 1.5 Conditional convergence | 247 | concept | valid; market evidence now supports the sequence | master body | — |
| 1.6 What should change | 164 | proposal | implemented in 4.0.0; 4.1.0 adds the 60 % HoT bar | master body → "what changed, 4.0.0–4.1.0" | A3 |
| 2 Gate-by-gate, G0–G11 | ~1,900 | proposal + as-built | "Proposed" rows now built, with deviations (G6 split → ITR in G5; G10 → item scope + state requirements); G1 heading stale | master body; add an "As built" row per gate | A2 |
| 3 Producer readiness, 3.1, 3.2 | 922 | concept + practice | valid; "what GEX should check" now computed (C1–C10) | master body | — |
| 4.1 Offtake ladder | 468 | concept | wording ≠ engine definitions; no mention of 60 % coverage bar | master body, engine definitions verbatim | A4, N8 |
| 4.2 Offtake quality card | 203 | proposal | built card has fewer fields plus `planned_output_tonnes_per_year` | master body (as built + roadmap) | A5 |
| 4.3 Offtaker readiness | 251 | concept + evidence | valid | master body | — |
| 4.4 New offtakers | 219 | concept | "give those accounts an offtaker view" — built | master body (update) | A1 |
| 5 EPC maturity + AACE table | 538 | concept + practice | E-ladder wording vs engine; AACE table duplicated in GREENEARTHX §4.1.1 | master body (engine definitions; one AACE table) | A4, C6 |
| 6 Dependency map + two sequences | 579 | concept + evidence | conflicts with the internal phase tables; now evidenced by the deal sample | master body — the single phase map | C1, C5, D-b |
| 7 Market evidence + statistics | 1,283 | market evidence | time-sensitive; restate "as of" | master body | — |
| 8.1–8.6 Proposed modification | 1,194 | proposal | implemented; 8.6 obsolete | master body → dated history + current rules; drop 8.6 | A3, A6 |
| 9 Limits | 191 | method | "Nothing in GEX was changed" false | master body (update) | A6 |
| 10 Sources | 512 | sources | GEX source "rules 3.0.0" | master body (update, add §11 sources) | A6, N13 |
| 11 Reflection on EU H2 Bank + 3 templates | 1,330 | market evidence (unlabelled) + templates | most thresholds verified against IF25 T&C; "non-EU" wrong (non-China); rejection reasons unsourced | evidence → master body mapped to gates; templates → annex, marked illustrative | B4, B5, N3, N5 |

## GREENEARTHX v4.5 (INTERNAL architecture working document)

| Section | Words | Kind | Notes | Disposition | Conflicts |
|---|---|---|---|---|---|
| Front matter: cover, doctrine, reading note, TOC | 710 | framing / status | cover v4.5 "Sep 30 2026", note v4.4, bottom line v4.2 | stays internal; fix version trail | N6 |
| Key words | 99 | framing | — | stays internal | — |
| GEX's thought process (open questions, general comments) | 616 | working note | candid assessment addressed to "you"; code references | stays internal; never client | E |
| Governing frame: Hidalgo, Sung (entropy table) | 340 | concept | entropy table: DFI at G10, technology at G5/G6, "Trust Score" | stays internal; align table to engine | C3, C4, C8 |
| Scope + one platform, three modules | 474 | concept | three layers, one project identity | stays internal; one paragraph → master | D-f |
| 1 Key components layer (certification repository, flow, geography, technology) | 492 | spec / roadmap | largely unbuilt (certifier APIs, QR, blockchain) | stays internal | — |
| 2.1 Three bridge layers | 488 | concept / spec | "Senior Debt and ECA gated behind G10" | stays internal; fix note | C3 |
| 2.3 Participants and access surface | 352 | spec | offtaker HoT at G4 / binding G10; insurer binds at G7; IE signs G6 for all | stays internal; fix per engine | C1, C2, N10, C15 |
| 2.4 Operative principle | 78 | doctrine | UNVERIFIED…AUDITED vocabulary | stays internal; map in glossary | C7 |
| 3 Naming phases — capital eligibility (+ gate vocabulary note) | 377 | concept | phase ↔ gate table conflicts; coarse "Gate 1–4" mapping leaves G4, G7–G9 out | client-relevant: one table in master; GREENEARTHX points to it | C1, C5, D-b |
| 3.1 Adjacency doctrine | 635 | spec + doctrine | illustrative cohort numbers read as data; backend claims contradict the tree | stays internal; label illustrative | C13, C14 |
| 4 Bridge to Capital: chain of investment promises, 4.0 CFO constraints | 323 | concept / practice | funding ladder = capital-side analogue of O/E | chain → master concept (D5); CFO → annex (D7) | D-a |
| 4.1 Capital management & control; 4.1.1 AACE; 4.1.2 triggers; accounts | 1,013 | practice | AACE table duplicates master §5 | CFO annex (D7); one AACE table | D-e |
| 4.2 Investor disbursement practices | 366 | practice | — | CFO annex (D7) | D-e |
| 5 GEX model categories … 5.11 (objects, Gantt, packages, spend wave, invariants, drawdown, capital stack, DFI criteria, pre-COD metrics) | 3,153 | spec | "Capital State Gate 1–8"; RAS ≥ 75 for G10; unsourced tranche rates | stays internal | C6, C12, C14 |
| 6 Verification taxonomy | 142 | spec | UNVERIFIED…AUDITED | stays internal; glossary mapping | C7 |
| TEA & cost basis; 8 per-molecule process function | 447 | spec / doctrine | consistent with the evidence doctrine | stays internal (one sentence in master optional) | — |
| 5 Tokenisation; 6 Trading; 7 Lineage | ~1,500 | spec | status claims | stays internal; D-f paragraph in master | C13 |
| 8 Software integration map | 658 | status / plan | stale paths | stays internal → status to handoff | C13 |
| 9 Governing doctrines | 294 | doctrine | "five decomposed certainties"; "DSCR not before G10" | stays internal; align where overlapping | C8, C11 |
| Appendix A–C (schema, state machines, invariants) | ~500 | spec | — | stays internal | C6 |
| Appendix D intellectual scaffolding | 372 | concept | — | stays internal | — |
| Appendix E design primitives | 2,153 | spec | Decomposed Certainty Stack, Adjacency Card | stays internal | C8, C14 |
| "The Future and where the current project development is now" | 1,504 | status | self-contradictory; "PostgreSQL migrations DEFERRED" | move to handoff after re-verification, or drop | C13 |
| Appendix F navigation; pasted "29 July 2026 question to Claude"; truncated answer | 1,383 | working note | pasted prompt and partial AI answer | stays internal; move out of the spec | E |

## Development-to-Capital Bridge v6 (INTERNAL, 8–15 May 2026)

| Section | Words | Kind | Notes | Disposition | Conflicts |
|---|---|---|---|---|---|
| Front matter: cover "Version 4", doctrine, design intent 1–10, Appendix A anchors | 1,945 | concept / spec | superseded by GREENEARTHX; AACE/TRL anchors already in master §5 | archive; doctrine line → master (D-c) | D-c |
| 1 Source documents | 46 | working note | — | archive | — |
| 2 Hidalgo + Sung | 281 | concept | duplicate of GREENEARTHX | archive | C3, C4 |
| 3 Lender-grade timeline | 546 | concept | LOI pre-FEED, HoT at FEED, G4 at FID readiness; insurance bound | archive (superseded by the single phase map) | C1, C2 |
| 4 Capital stack build-up (200 MW e-MeOH, indicative) | 395 | illustrative numbers | unsourced | archive | C14 |
| 5 Development package object | 549 | spec | superseded by GREENEARTHX §5.2 | archive | — |
| 6 Pre-COD metrics (incl. CEC, FRI, RMR, CBM; ECR defined as Bermuda insurance ECR) | 816 | spec | second metric set; conceptual confusion | archive; record conflict | C12 |
| 7 Concessional finance; 8 Debt-for-nature; 9 Lineage example | 1,237 | spec + illustrative | Chile example with "Trust Score 89/100", "CAR bound at G7" | archive | C2, C8, C14 |
| 10 Integration map | 438 | plan | superseded | archive | — |
| 11 Governing doctrines | 291 | doctrine | "infrastructure, not a broker" fee wording | archive → decision log | — |
| Answer to Marwen (problem, framing, governing principle, B1–B7, summary, acceptance, doctrine, appendices A–C) | ~1,650 | decision memo | "doesn't block"; package state "approved = internal governance" | archive → decision log | C9, C10 |
| Remarks to Meher's questions (customer, use case, outputs, inputs, journey, recommend vs visible, who approves, enforcing, granularity, packages, eligibility, integration) | ~1,150 | positioning Q&A | quality score 67 %→91 %; "at 85 %+ providers notified"; providers configure thresholds | archive → decision log; D-d content to master after decisions | C8, C9, C10 |

## Observations

- Nothing in GREENEARTHX or Bridge v6 is fit to hand to a client as written: both carry code
  paths, build status, working notes or pasted prompts (list E in the prompt).
- What clients need from them is small: the funding-commitment ladder (D-a), one phase map
  (D-b), the pre-COD doctrine (D-c), "what GEX does and does not decide" (D-d), an optional
  CFO annex (D-e) and one paragraph on the three layers (D-f).
- Bridge v6's unique content is its Q&A with Marwen and Meher. Most of it is superseded;
  its positions on enforcement, scores and configurable thresholds conflict with the code and
  need JML's decisions (D3, D4, D16).
