# Prompt — Reconcile the GEX client master document with GREENEARTHX and the Development-to-Capital Bridge

Written 2026-09-29 after a full read of all three documents and a check of the running
code. Section 4 is a starting register of findings: **verify every item before acting on
it** — the tree and the documents keep moving.

---

## 1. Role and goal

You are working in `files/gex-platform-enhanced` for the platform owner (JML). JML wants
**`docs/GEX-Gates-Multi-Party-Review_JML modified.docx`** to become *the* master document
that any GEX client — producer, offtaker, lender, equity, DFI, EPC, certifier, insurer —
reads when approaching the software. Two other documents cover overlapping ground and
contradict it in places. Decide **whether** and **how** each should be reconciled with the
master, get JML's decisions at one checkpoint, then produce the reconciled material.

## 2. Inputs

| Document | Path (under `files/`) | What it is |
|---|---|---|
| **Master** | `gex-platform-enhanced/docs/GEX-Gates-Multi-Party-Review_JML modified.docx` | JML's edit of Claude's 2026-09-27 multi-party review (~12.1k words), written against **rules 3.0.0**. JML rewrote §1.1 and §1.3, expanded the EU Hydrogen Bank bullet and the debt-lens bullet in §1.4, removed the `[GEX]` labels from §1.2 and the "question put / version" lines, added a hand-typed TOC and a new **§11** (Hydrogen Bank reflection + three templates). §§2–10 are otherwise Claude's original (`…_Claude original.docx`, same folder — diff against it to see JML's intent). **Open in Word** (a `~$…` lock file sits beside it). |
| **GREENEARTHX** | `GEX_Handoff_Reference/design/GREENEARTHX.docx` | INTERNAL architecture working document, "v4.5 · Sep 30 2026" (~19k words): frame (Hidalgo, Sung), scope, Bridge to Capital, disbursement, schemas, tokenisation, trading, lineage, doctrines, UI primitives, a build-status audit, a pasted prompt and a truncated answer. Contains tracked insertions authored "Claude". |
| **Bridge v6** | `docs/word-docs/Development-to-Capital Bridge_v6.docx` | INTERNAL spec "Version 4 · 8 May 2026" (~9.7k words). Most of it reappears in GREENEARTHX; unique parts are the memo "Answer to Marwen" (B1–B7) and "Remarks to Meher's questions" (paying customer, outputs, decision-support vs enforcement, who approves, who sets eligibility). |
| **Ground truth** | `../gex_pf_engine/backend/pf_engine/core/bankability_engine.py` (`get_rules()`, `get_gates()`); `backend/app/core/bankability_engine.py`; `docs/CLAUDE_HANDOFF.md` §8 items 34–36; `../gex_pf_engine/README.md` | Evidence rules **4.0.0**, live since 2026-09-28. |

Copies of the master also exist under `files/docker/…` and `files/co-work/…`. They are build
staging or old; never edit them.

## 3. The answer to "if" — reconcile, do not merge

Test this assessment against the documents; overturn it only with evidence.

- **The three documents have different audiences and jobs.** The master is client-facing
  concept and rationale for the gates. GREENEARTHX is an internal engineering and finance spec
  (schemas, endpoints, doctrines, UI primitives, build status). Bridge v6 is a superseded
  internal spec. Merging them would put internal material in front of clients and bury the
  client story in schema.
- **What "reconcile" means here:** one vocabulary, one set of facts, one answer to each
  doctrinal question. Each fact lives in one place; the others refer to it. Today the same
  concepts exist in two or three versions: the phase table, the entropy table, the offtake
  timeline, capital gating, verification states and scores.
- **Hierarchy of truth:**
  1. Running code, for what the software does. Dated; `[GEX]` claims are re-verified on the day.
  2. The master, for concepts, definitions and rationale addressed to clients. It must agree
     with the code; anything not built is labelled roadmap.
  3. GREENEARTHX, for internal spec. It must use the master's definitions and point to them
     rather than restate them.
  4. Bridge v6, as history. Archive it once its unique decisions are captured.
- **The master itself needs the most work.** It is a critique-and-proposal written against
  3.0.0, and its proposal has since been built as 4.0.0 (with deviations). It has to become an
  as-built client reference that keeps the critique as the "why".

## 4. Findings to verify (seed of the conflict register)

### A. The master is stale against the software (4.0.0, 2026-09-28)

- **A1 — §1.2 "Six facts" and §1.4 "Correct" describe 3.0.0.**
  - They cite `_LENDER_GATES` waiving G4/G6/G7/G8/G10. Now 23 lender items are scoped per
    item, and only G6 and G8 are waived whole.
  - "None of the 77 items concerns the technology…" Now there are 93 items: G1 has the
    technology dossier, licensor term sheet and mass/energy balance; G5 has FEED Class 3,
    licence and process guarantee, long-lead, EPC security and `independent_technical_review`.
  - "No offtaker view": an OFFTAKER persona and lens now exist.
  - "No certificate before OPERATIONAL": G11 now has `certificates_issued` and
    `first_deliveries_accepted`.
- **A2 — §2 still reads as proposal.** The heading "G1 · Power, Water & Critical Utility
  Access" is stale (now "Power, Utilities & Technology Basis"). Each gate needs an "As built
  (4.0.0)" row. Record the deviations:
  - The proposed G6 split was built as `independent_technical_review` in **G5** (all
    projects); G6 stays lender-only.
  - The proposed G10 "FID lock" was built as item-level scope plus state requirements
    (FINANCEABLE: O5 effective + E6 on a balance sheet; O7 + E6 under project finance).
- **A3 — §8 is implemented, with differences.**
  - Blocking rule: proposed "blocking from Buildable when both sides' data exist"; built, a
    FAIL blocks its own gate and NOT_EVALUABLE never blocks and never passes.
  - Placement: C1–C3 and C5–C8 → G4, C4 → G5, C10 → G8, C9 → G10. §8.3 says "C1–C6 at
    Buildable".
  - Post-FID triggers: T1–T3 only. Check whether "schedule forecast past longstop" exists as
    a trigger; C5 tests longstop against schedule at G4.
  - Dual state labels: the wording in `STATE_COMMITMENT_LABELS` is canonical.
- **A4 — §4.1 and §5 ladder wording differs from `OFFTAKE_LEVEL_DEFINITIONS` and
  `EPC_LEVEL_DEFINITIONS`.**
  - O3: the master says "framework or conditional agreement…"; the engine says "signed but not
    binding … or conditions with no longstop".
  - O5: the master names forms (take-if-delivered, take-and-pay); the engine O5 means
    effective (conditions satisfied), whatever the form.
  - O6: the engine threshold is take-or-pay ≥ 60 % (`TAKE_OR_PAY_FIRM_PCT`); the master cites
    60–80 %.
- **A5 — §4.2 offtake card lists fields the built card lacks:** tolerance band,
  make-up/carry-forward, Incoterm/delivery point, acceptance testing, replacement cost, seller
  performance security, ramp-up profile. The built system has **five** cards (offtake, EPC,
  schedule, supply, model: `COMMITMENT_CARD_FIELDS`). Describe what is built; list the rest as
  roadmap.
- **A6 — Now false:** §8.6 "What it would take", §9 "Nothing in GEX was changed", the §10 GEX
  sources ("rules 3.0.0, read 27 Sept", `_LENDER_GATES`, "77 evidence items") and the `[GEX]`
  legend date.

### B. The master's own defects

- **B1 — Voice.** It addresses the questioner ("Your proposition…" §1.4; "answer your
  question directly" §3; "My inference" in the legend) and is framed as GEX critiquing GEX.
  Decide how a client should read it (D1, D2).
- **B2 — §1.1 logic.** JML's rewrite folds both tests into "Test one" and makes "Test two" a
  restatement. The original had two tests: is each party mature enough for the commitment
  asked of it; and do the conditions, dates and quantities agree across the commitments (the
  convergence). Restore the two-test logic in JML's words.
- **B3 — §1.3 definitions** are right in substance. Fix the grammar ("because it has across
  four dimensions", a stray quote mark) and add labels. The four "financed but not ready"
  cases (Fulcrum, NEOM, Stegra, FlagshipONE) were cut here but remain in §7; decide whether
  they return as illustrations.
- **B4 — Hydrogen Bank facts disagree.** §1.4 gives a completion guarantee of "8–10 % of the
  subsidy" and attributes it to "CINEA officials"; §11 says "8 % of the maximum grant". The
  only listed source is S&P, 18 Sep 2025. Verify against the auction terms and conditions and
  Commission/CINEA statements; keep one number and one attribution.
- **B5 — §11 needs verification.**
  - Presentation: typo "Eropean"; missing from the TOC; no evidence labels; secondary sources
    without dates or URLs (S&P, Balkan Green Energy News, "CATF & Tim Harper", EY/Hyvolution).
  - The IF25/IF26 requirement claims must be checked against the primary auction documents
    before any client reads them: 60 % PPA pre-contracts, 60 % offtake, electrolyser MoU,
    permits, 60 % equity, 8 % guarantee, NZIA stack limits, and the "mandatory cross-checks /
    common rejection reasons" table.
  - The three templates are GEX-drafted illustrations. Label them "illustrative, not legal
    advice" and check their technical content: RFNBO 70 % saving, ISO 14687 grade, the
    operating deadline.
  - Opportunity: map §11's requirements onto GEX levels and items. For example, an auction
    offtake HoT ≈ O2; a PPA pre-contract ≈ G1 `ppa_signed_or_term_sheet_evidence` at
    INDICATIVE; grid levels 1–4 ≈ the G1 grid items. That turns the reflection into an
    auction-readiness overlay.
- **B6 — Front matter.** The TOC is hand-typed with page numbers and omits §11. The subtitle
  still says "A multi-stakeholder critique…".
- **B7 — Label policy.** The doc's own rule is to label "every claim that matters", yet §1.2
  lost its `[GEX]` labels. Decide the policy and apply it throughout.

### C. The internal documents contradict the engine or the master

- **C1 — Offtake timing.**
  - GREENEARTHX §2.3: "Offtaker signs HoT at G4, binding at G10"; its §3 phase table puts G4
    under FID readiness.
  - Bridge §3: LOI at pre-FEED, HoT at FEED, G4 at FID readiness.
  - Engine and master: G4 needs **O4** (binding with conditions and a longstop) for
    BUILDABLE; O5–O7 at FINANCEABLE.
- **C2 — Insurance.**
  - GREENEARTHX §2.3 "Insurer binds CAR/EAR/DSU at G7"; Bridge §3 "insurance bound" at FID
    readiness and §9 "bound at G7".
  - Engine: G7 = quoted terms (`insurance_term_sheet` at INDICATIVE, market report,
    exclusions/FOAK backstop, lender deductibles). Bound only at **G10**
    (`insurance_certificates_delivered`, EFFECTIVE).
- **C3 — Capital gating.**
  - GREENEARTHX §2.1: "Senior Debt and ECA gated behind G10". The entropy table in both
    internal docs has concessional first-loss "(DFI at G10)" → senior debt commitment.
  - Engine: **G6** → DFI/mezz/guarantees, **G8** → senior-debt commitment, **G10** →
    drawdown; debt is out of scope for balance-sheet funding. ECA is not an engine capital
    type.
  - There are four capital vocabularies in code: the engine's `CapitalType` (8
    decision-eligibility types), `spend_wave.CapitalLayer` (12 funding layers), package
    `capital_eligible`, and tranche subtypes. GREENEARTHX's eligibility bar adds a fifth (6
    types).
- **C4 — Technology timing.** The entropy table says "Technology/execution → EPC (G5) + IE
  (G6)". 4.0.0 examines technology at **G1**, with the independent technical review at G5.
- **C5 — Coarse gate mapping.** GREENEARTHX §3 maps "Gate 1–4" → G0–G1, G2–G3, G5–G6,
  G10–G11 and leaves G4, G7, G8 and G9 unmapped.
- **C6 — Ladders that share words but not meanings.**
  - G0–G11 and the nine states (engine).
  - "Capital State Gate 1–8" (GREENEARTHX Gantt).
  - The package workflow: 10 states in both docs, plus a different 8-state ladder in Bridge
    ("identified→…→propagated").
  - Funding `legal_status` and the "chain of investment promises".
  - Tranche states.
  Each needs a definition and a mapping to gates and states, or removal.
- **C7 — Verification vocabulary.** GREENEARTHX has UNVERIFIED / SUBMITTED / CONFIRMED /
  AUDITED ("CONFIRMED → gate progress credit awarded"; `app/core/verification.py`). The gates
  use evidence status (…VERIFIED…), maturity (INTENT→EFFECTIVE) and coherence (PASS / FAIL /
  NOT_EVALUABLE / NOT_APPLICABLE). The master (§5) says verification, maturity and coherence
  are three separate facts. One mapping table is needed.
- **C8 — Scores.**
  - Bridge promises a "GEX project quality score (67 %→91 %, BB→A→AA)", automatic provider
    notification "at 85 %+", a "Trust Score 89/100", and RAS 0–100.
  - GREENEARTHX replaces the Trust Score with a five-bar "Decomposed Certainty Stack", yet
    states that readiness is "emergent, never authored".
  - The master: one determination per gate, and lenses are never scored separately.
  - In code: `contractual_rating_engine.py:227` scores offtake tenor against a hardcoded
    10-year target, while the engine's O7/C10 compare tenor with the project's actual debt
    tenor. `gex_project_rating_engine.py` also exists.
- **C9 — Enforcement.** Bridge says "GEX does not block — visibility, not enforcement", with
  soft enforcement by score. The engine blocks gates, and the server refuses maturity raises,
  invalid cards and pre-FID senior-debt spend (GREENEARTHX §5.4). The engine's capital
  semantics: a gate makes a project "eligible for the capital provider's decision; GEX does
  not commit, release or draw capital." Suggested reconciliation: **GEX enforces the evidence
  standard; it never makes or blocks a funding decision.**
- **C10 — Approval and configuration.** Bridge says there is no internal approval role, yet
  its package state "approved" means internal governance has accepted the package. It says
  providers configure their own thresholds and sub-gates can be worked in any order. The
  engine has one fixed standard: items can be worked in any order, but states are
  sequential.
- **C11 — DSCR.** Both internal docs say DSCR is not shown before G10, but G8 (credit
  approved) requires an audited base-case model, and C10 checks it against the contracts.
  Suggested wording: DSCR is a lender metric at credit approval, not a development-stage
  dashboard.
- **C12 — Pre-COD metrics.**
  - Two sets: ECR/FMR/DRE/RAS/TIE in both docs; Bridge adds CEC/CER, FRI, RMR and Cohort
    Burn Multiple.
  - The ECR threshold differs: "≥ 80 % at FEED launch" in one, "< 60 % = lender concern" in
    the other.
  - Bridge also defines ECR once as Bermuda insurers' "Enhanced Capital Requirement".
  - "RAS ≥ 75 for G10" conflicts with the O5/O7 requirement for FINANCEABLE.
  - Code: `backend/app/api/v1/pre_cod_metrics.py`.
- **C13 — The build-status audit contradicts itself and the tree.**
  - Rows are marked IMPLEMENTED with the note "not built".
  - "PostgreSQL migrations DEFERRED", but the head is 058.
  - It says 15 ABAC actor types in one place and 16 in another.
  - "Adjacency complete", while `api/v1/adjacency.py` reads PostgreSQL-owned tables from
    SQLite and fails (see `.claude/CLAUDE.md`).
  - The version trail is confused: v4.5 on the cover, a v4.4 reading note, a v4.2 bottom
    line.
- **C14 — Illustrations presented as data.** Bridge §9's Chile example (IMF swap "CL-2025",
  USD 480M, "Trust Score 89/100"). GREENEARTHX's "71 % adjacent to 14 prior GEX projects,
  1.38×, 86 %", when no such cohort exists. Unsourced tranche rates and equity-return targets.
- **C15 — Three axes both called "persona" or "lens".** ABAC actor types (15–16), gate
  views (PRODUCER/FINANCE/REGULATOR/OFFTAKER/EXECUTIVE), and lenses
  (PRODUCER/OFFTAKER/CAPITAL/CERTIFIER).

### D. Client-relevant content in the internal docs (absorb into the master if JML agrees)

- **D-a — The capital side of conditional convergence.** GREENEARTHX §4's "chain of
  investment promises" and its announced-vs-available capital states are the funding
  analogue of the O and E ladders. They are not computed today; label them as a concept.
- **D-b — One phase × gates × ladders × capital table.** Replace GREENEARTHX §3, Bridge §3 and
  the master's §6 with a single table that agrees with the engine's capital unlocks.
- **D-c — The doctrine.** "Pre-COD financeability is a package-definition and capital-release
  problem before it is an operating-ratio problem", with the AACE and TRL anchors from Bridge
  Appendix A.
- **D-d — "What GEX does and does not decide."** Built from the C9/C10 reconciliation and
  Bridge's use-case table: the developer produces the evidence, the capital provider
  evaluates it, and post-FID governance uses it.
- **D-e — "After the gates: how capital is actually released".** GREENEARTHX §4.0–4.2:
  accounts, drawdown triggers, practice by investor type. As an annex for CFOs, if JML wants
  it.
- **D-f — One paragraph on where the gates sit.** Bridge to Capital → Tokenisation →
  Trading, one project identity.

### E. Never in the client master

- Code paths, file names, endpoints, schemas and build status.
- Internal candour: the "General comments" ("You did the schlep", the two-clock wedge).
- The pasted "29 July 2026 question to Claude" and its answer.
- Internal names (Marwen, Meher, Philippe).
- Fictional examples presented as data, and unsourced constants.
- Fee language, unless JML decides otherwise.

## 5. Decisions for JML — one batch, each with a recommended default

- **D1 — Audience and purpose.** Recommended: the master becomes the *as-built* client
  reference for rules 4.0.0. The critique is kept as "why the gates look like this", with the
  3.0.0 → 4.0.0 history dated.
- **D2 — Voice.** Recommended: neutral or "GEX"; no "you / your hypothesis / I". The `[I]`
  label becomes "GEX inference".
- **D3 — Enforcement sentence.** Recommended: "GEX enforces the evidence standard; capital
  providers make every funding decision."
- **D4 — Scores.** Recommended: no composite or quality score in client material; show
  determinations, O/E levels and coherence results. Internal scores are derived, never
  authored. The 10-year tenor hardcode becomes a separate code task.
- **D5 — Capital-commitment ladder (D-a).** Recommended: include it as a concept beside O and
  E, labelled "not yet computed".
- **D6 — §11.** Recommended: keep it after verification, as "Lessons from the EU Hydrogen
  Bank" mapped to gates and levels. The templates move to an annex marked illustrative.
- **D7 — CFO annex (D-e).** Recommended: a short annex, with no code.
- **D8 — Bridge v6.** Recommended: archive it, marked superseded, after moving its unique Q&A
  into a decision log.
- **D9 — GREENEARTHX.** Recommended: a tracked-change redline limited to gate, state, capital
  and verification vocabulary, plus pointers to the master. Move the build-status appendix
  into `docs/CLAUDE_HANDOFF.md` after re-verifying it.
- **D10 — Where the master and the engine disagree (A4, A5).** Recommended: the master adopts
  the engine's definitions verbatim. Richer items become roadmap. Where the document is
  better than the code, open a separate code task; never quietly rewrite the doc to promise
  it.
- **D11 — Pre-COD metrics (C12).** Recommended: keep them out of the client master until one
  set is canonical and derived.
- **D12 — Offtake timing (C1).** Recommended: the engine/master timing is canonical; correct
  the internal timelines.

## 6. Method

**Phase 0 — Guardrails and setup.**
- Copy the three `.docx` files to your scratchpad. **Never write to the originals.** The
  master is open in Word; record SHA-256 checksums now and re-check them at the end.
- Load the `docx` skill. `pandoc` is not installed: extract text with Python
  (`zipfile` + XML), keeping headings, tables, tracked changes (`w:ins` / `w:del`), comments
  and footnotes.
- Export the engine's truth as dated JSON. In `../gex_pf_engine/backend`, with
  `source ../micro_service/bin/activate`, call `get_rules()` and `get_gates()`. Every `[GEX]`
  statement is checked against this export.

**Phase 1 — Inventory.** One row per section of each document, recording:
- audience: client or internal;
- kind: concept / as-built fact / proposal / market evidence / spec / status / working note /
  template;
- proposed disposition: master body / master annex / stays internal / archive / drop.

**Phase 2 — Canonical glossary.** Generate it from the engine export and the master's
definitions. Cover:
- gates and names, states and commitment labels, capital unlocks;
- O and E levels, evidence status, maturity, coherence statuses;
- lenses vs gate views vs ABAC actor types;
- phases, package / tranche / funding states, verification states.
Map every alias found in the three documents to one canonical term.

**Phase 3 — Conflict register.** Seed it with §4 and add anything new. Each row: ID; document
and section; statement; conflicting statement; ground truth (code path and line, or a primary
source URL); proposed resolution; decision needed (D#).

**CHECKPOINT.** Send JML, in one message: the inventory summary, the glossary, the register,
and D1–D12 with your recommendations. **Edit no document before the answers.**

**Phase 4 — Produce, according to the decisions.** Suggested master structure:
- Cover and how to read the evidence labels.
- What the gates are and do (as built).
- Definitions (JML's §1.3, polished).
- Why the gates look like this: the critique, conditional convergence, and the dated
  3.0.0 → 4.0.0 history.
- Gate by gate, by party, each with an "as built" row.
- Producer readiness.
- Offtaker readiness and the O-ladder.
- The E-ladder.
- The capital-commitment ladder (if D5).
- The single phase × gates × ladders × capital map.
- Coherence checks and post-FID triggers, as built.
- Market evidence.
- Lessons from the EU Hydrogen Bank (if D6).
- What GEX does and does not decide.
- Limits.
- Sources.
- Annexes: templates, capital release for CFOs, glossary.

**Phase 5 — Verify, automated where possible.**
- Re-extract every output.
- Every gate name, state label, capital unlock and O/E definition in the master equals the
  engine export.
- Every `[E]` has a Sources entry; every `[GEX]` is dated.
- No forbidden strings remain in the master: `_LENDER_GATES`; "77 evidence items" outside
  dated history; "Power, Water & Critical Utility Access"; "Nothing in GEX was changed";
  "Trust Score"; "your hypothesis"; "Eropean"; `.py`; `backend/`; Marwen; Meher.
- The TOC is regenerated and includes every section.
- Each file passes the skill's `validate.py` and renders.
- All tracked changes carry a single author.
- The originals' checksums are unchanged.
- Report every check you could not run.

## 7. Deliverables — in `gex-platform-enhanced/docs/master-reconciliation/`

- `01_inventory.md`
- `02_glossary.md`, plus the engine export `.json` it was generated from
- `03_conflict_register.md` (or `.xlsx`)
- `04_decisions_for_JML.md`
- `GEX-Gates-Master_v2_redline.docx`: tracked changes against the JML version, so JML accepts
  or rejects each edit
- `GREENEARTHX_redline.docx` (if D9)
- `05_bridge_v6_disposition.md`: the archive note plus the decision log of its unique Q&A
- `05_change_summary.md`

## 8. Hard rules

- No fabrication. A claim you cannot verify is flagged in the register; it is neither kept
  silently nor deleted silently.
- Evidence labels on every claim that matters. Re-verify time-sensitive market facts and
  state "as of <date>".
- JML's own text (§1.1, §1.3, §11) keeps its substance. Every change to it is a tracked,
  explained edit.
- No code changes in this task. Where a document is better than the engine, record a
  separate proposed code task.
- Keep "no new gates": twelve gates, nine states, one determination per gate.
- Nothing from list E reaches the client master.
- Internal documents stay marked INTERNAL.
