# 05 — Development-to-Capital Bridge v6: archive note and decision log

Decision D8 (accepted 29 Sep 2026): archive Bridge v6, renamed `…_SUPERSEDED`, with a decision
log of its unique content. INTERNAL.

## Archive note

| | |
|---|---|
| Was | `files/docs/word-docs/Development-to-Capital Bridge_v6.docx` (15 May 2026) |
| Now | `files/docs/archive/Development-to-Capital Bridge_v6_SUPERSEDED.docx` (moved 30 Sep 2026) |
| Content | Unchanged: SHA-256 `e2bdebc5…bb3a9a` before and after the move, same bytes as at the 29 Sep read |
| Superseded by | GREENEARTHX v4.5 (`GEX_Handoff_Reference/design/GREENEARTHX.docx`, §4–5) for the internal spec; the gates master (`GEX-Gates-Master_v2_redline.docx`) for anything a client reads |
| Index | `files/docs/README.md` updated to point at GREENEARTHX and list Bridge v6 under Superseded, as that file's own rule requires |
| Version trail | The file is named v6; its cover says "Version 4 · 8 May 2026"; the memo inside says "Version 3.1 · 28 April 2026"; its footer says "v3.0, April 2026". Archived as is |

## Decision log — what happened to each position

Status: **Kept** (lives on, where) · **Superseded** (replaced by a later document) · **Rejected**
(overruled by a decision of 29 Sep 2026) · **Open** (no decision yet).

### Memo "Answer to Marwen" (v3.1, 28 Apr 2026)

| # | Bridge v6 position | Status | Where it lives now / why |
|---|---|---|---|
| 1 | Two problems: project definition and capital release are not expressed in one language; early projects are forced into late-stage financial logic | Kept | GREENEARTHX §4 intent ("why the next draw is or is not releasable") |
| 2 | Chain: package → spend → evidence → risk removed → capital eligible → unlock condition → next package | Kept | GREENEARTHX §4–5 (development packages, spend wave, unlock conditions) |
| 3 | Scope: development-stage capital logic only, not plant operations or covenant reporting | Kept | GREENEARTHX scope ("Out of scope") |
| 4 | One-line doctrine: "Pre-COD financeability is a package-definition and capital-release problem before it is an operating-ratio problem" | Kept, internal | GREENEARTHX §9, row 1, aligned in its redline: DSCR is a lender metric at credit approval (G8), not a development dashboard. Not in the client master |
| 5 | "The rating doesn't enforce — it reveals … doesn't block but helps via presenting quality score" | **Rejected** (D3, D4) | GEX enforces the evidence standard; capital providers make every funding decision (master §8.6). No quality score |
| 6 | B1 Development financial-package object | Kept | GREENEARTHX §5.2; built as `api/v1/development_packages.py` |
| 7 | B2 Cost maturity: every package carries a cost state; estimate class is distinct from phase | Kept | GREENEARTHX §5.2 (`aace_class`, `aace_class_history`); master §5 (E-ladder, AACE table) |
| 8 | B3 Capital eligibility per package | Kept | GREENEARTHX §5.2 `capital_eligible`; client-facing capital decisions by gate in the master's front section |
| 9 | B4 Unlock logic: capital is released because a condition has been met and evidenced | Kept | GREENEARTHX §9 doctrine; `unlock_condition` |
| 10 | B5 Drawdown logic: availability, commitment, release and drawdown are different things | Kept, extended | Master: capital-commitment ladder (§6, D5) and Annex A; GREENEARTHX §4 chain of investment promises |
| 11 | B6 Owner, state engine, ten states `identified → … → closed` | Kept | GREENEARTHX Appendix B (the one package ladder). Bridge §8's other ladder (`… → propagated`) is retired with this file (C6) |
| 12 | B7 Views: packages, spend wave, capital eligibility and unlock chain before any waterfall | Kept | GREENEARTHX §1–2 (four linked views) |
| 13 | Acceptance standard: answer in minutes what must be funded next, why, what risk it removes, who can fund it, what it unlocks | Kept as history | Consistent with GREENEARTHX §4; recorded here |
| 14 | Appendix A fields | Superseded | GREENEARTHX §5.2 field table |
| 15 | Appendix B: package state `approved` = "internal governance has accepted the package" | **Open** (O1 below) | Contradicts the same document's answer to Meher (#23): "no internal governance approval role" |
| 16 | Appendix C product rule: never show a package as funded while evidence, eligibility or release conditions are unresolved | Kept | GREENEARTHX Appendix C invariants |

### "Remarks to Meher's questions"

| # | Question — Bridge v6 answer | Status | Where it lives now / why |
|---|---|---|---|
| 17 | Who pays? A multi-sided market: every party pays, by role and stage | Kept, internal | Commercial terms stay out of the master (D17); the throughput fee is not settled in any of the three documents |
| 18 | Primary use case: the developer structures, the capital provider evaluates gate by gate, the post-approval investor governs release | Kept | Master §8.6: "The developer produces the evidence, the capital provider evaluates it, and after the investment decision the same evidence base supports monitoring" |
| 19 | Output 1, capital release package: CAPEX decomposition, gate status, **quality score "67 % → 83 % → 91 %, or BB → A → AA"**, tranche schedule "unlocked at which threshold", provider list "configurable per provider criteria" | Split | Gate status: **Kept** (one determination per gate). Quality score: **Rejected** (D4). Per-provider thresholds: **Rejected** (D16). Tranche schedule: now the capital-commitment ladder, a concept (D5). Matched provider list: not built, roadmap |
| 20 | Output 2, Production Profile Handoff at FID | Kept | GREENEARTHX Tokenisation §5.5. Bridge v6 itself calls it "a post-COD answer to a pre-FID question" |
| 21 | Inputs: user entries, plant-builder CAPEX, open benchmarks | Kept, refined | GREENEARTHX "TEA & cost-basis service": the cost basis is computed (TEA), then approved by an IE or CFO; benchmarks are a plausibility check |
| 22 | Journey after GEX: "each completed sub-gate raises the score"; "at threshold (e.g. 85 %+) matched capital providers are notified automatically" | **Rejected** (D4) | No score. Nothing is notified on a score threshold. The rest of the journey (structured CAPEX, gate sequence, agreed release schedule) is kept |
| 23 | Who approves? "External capital providers approve funding decisions … No internal governance approval role" | Kept | D3: capital providers make every funding decision; GEX never approves funding. GEX does decide gate determinations |
| 24 | Decision support or enforcement? "GEX does not block … visibility, not enforcement … soft enforcement" by score | **Rejected** (D3) | The engine blocks gates, and the platform refuses invalid evidence, reviewer maturity raises and invalid cards. Funders enforce hard conditions too (IF25 guarantee and termination, UK SAF milestones, lenders' conditions precedent): `00_market_evidence_gate_timing.md` |
| 25 | Granularity: standard package library; sub-gates in any order; "+90 % rating" thresholds | Split | Items in any order, states strictly sequential: **Kept** (engine). Rating thresholds: **Rejected** (D4) |
| 26 | Who defines packages: GEX templates define the gate sequence; "capital providers configure their minimum score thresholds per tranche" | Split | One GEX standard: **Kept**. Provider-configured thresholds: **Rejected** (D16): each provider applies its own credit criteria to the evidence GEX shows |
| 27 | Eligibility rules: a standard project-quality protocol "not a regulated financial rating"; "the GEX score is the calibration baseline" | Split | The protocol is the twelve gates: **Kept**. The score: **Rejected** (D4) |
| 28 | Integration: certification feeds gate evidence; Geomap feeds site data; Tokenisation receives the FID handoff; "certification status raises quality score" | Split | The links: **Kept** (GREENEARTHX three layers). The score: **Rejected** (D4) |

### Spec sections (Bridge v6 §1–11)

| # | Section | Status | Where it lives now / why |
|---|---|---|---|
| 29 | §3 Lender-grade timeline: LOI pre-FEED, HoT at FEED, G4 at FID readiness; insurance bound at FID readiness | **Superseded** (D12, C2) | HoT (O2) for ≥ 60 % of output at Commercially plausible; binding with conditions (O4) at G4; effective at Financeable. Insurability at G7, bound at G10 |
| 30 | §4 Capital stack build-up, 200 MW e-methanol, indicative numbers | Not carried forward | Unsourced illustration (C14) |
| 31 | §6 Pre-COD metrics, second set (adds CEC/CER, FRI, RMR, Cohort Burn Multiple); ECR "< 60 % = lender concern" against GREENEARTHX's "≥ 80 % at FEED launch"; ECR once defined as the Bermuda insurers' Enhanced Capital Requirement | Not carried forward | Two sets conflict (C12); none canonical; out of client material (D11). GREENEARTHX §5.10 now says so |
| 32 | §7 Concessional finance and additionality; §8 Debt-for-nature swaps | Kept | GREENEARTHX §5.8–5.9 and the sovereign-provenance pathway |
| 33 | §9 Lineage example: Chile swap "CL-2025", USD 480M, "Trust Score 89/100", "CAR bound at G7" | **Rejected** | Illustration read as data (C14); Trust Score rejected (D4); insurance is bound at G10 (C2) |
| 34 | §10 Integration map | Superseded | GREENEARTHX §8; build status now in `docs/CLAUDE_HANDOFF.md` §8 item 39 |
| 35 | §11 Doctrines: "DSCR is not shown before G10" | Superseded (C11) | DSCR is a lender metric at credit approval (G8, audited base case, check C10) |
| 36 | §11 Doctrines: "GEX is infrastructure, not a broker"; fee wording | Kept, internal | Not in client material (D17) |
| 37 | Appendix A external discipline anchors (AACE, TRL) | Kept | Master §5 (AACE classes, TRL and CRI) |

## Open item created by this log

**O1 — What does the package state `approved` mean?** Bridge v6 Appendix B defines it as
"internal governance has accepted the package for progression", and GREENEARTHX Appendix B keeps
the state, yet Bridge v6's own answer to "who approves?" says GEX has no internal approval role.
Proposed reading, for JML to confirm or overrule: `approved` records the **developer's own**
governance (sponsor board or investment committee) accepting a package. It is not a GEX approval,
and not a capital provider's decision. Until confirmed, no screen should label it as a GEX approval.
