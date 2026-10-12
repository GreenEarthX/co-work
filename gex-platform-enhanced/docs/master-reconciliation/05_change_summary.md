# 05 — Change summary (Phase 4 and 5)

Reconciliation of the three documents per decisions D1–D17 (accepted by JML, 29 Sep 2026).
Written 30 Sep 2026. Conflict IDs refer to `03_conflict_register.md`.

## Deliverables

| File | What | Checked |
|---|---|---|
| `GEX-Gates-Master_v2_redline.docx` | The client master: tracked changes (author Claude) against the JML version, plus 26 comments giving the reason for each cluster of edits | Skill validator with `--original` and `--author`: XSD, IDs, relationships, content types, comment markers, whitespace; **1,316 changes, every one tracked**. Forbidden strings: none in the accepted text. Voice: no "you/your/I" left, except "what we could call" (JML's) and one table header (N26). **JML has since edited this file** (below) |
| `GREENEARTHX_redline.docx` | GREENEARTHX v4.5: vocabulary aligned with rules 4.1.0, pointers to the master, illustrations labelled, build status moved out; 12 comments | Same validator: all checks passed, **381 changes, every one tracked**; accepted text read in every edited area |
| `05_bridge_v6_disposition.md` | Archive note and decision log for Bridge v6 (37 positions: kept / superseded / rejected / open) | — |
| `03_conflict_register.md` | Updated statuses; N15–N26 added | — |
| `docs/CLAUDE_HANDOFF.md` §8 items 39–40 | GREENEARTHX's build-status audit, **re-verified against the tree** and moved; the state of this reconciliation | Every claim either verified with the file or symbol that proves it, or marked "not re-verified" |
| `files/docs/archive/Development-to-Capital Bridge_v6_SUPERSEDED.docx` | Bridge v6, moved from `word-docs/` per D8; `files/docs/README.md` updated per its own rule | SHA-256 identical before and after the move |
| `tools/` | The scripts that produced the redlines (see `tools/README.md`) | — |

The three originals were checked against their recorded SHA-256 at the start of the day's work and
were never written. Bridge v6 was then moved, unchanged.

## The master — what changed, by section

- **Front:** new subtitle (D1); legend: [I] = GEX inference (D2), [GEX] dated 30 Sep with
  [GEX 27 Sep] for history (B7); TOC entries edited and six added; the field is marked to update on
  opening.
- **New front section, "The twelve gates today (evidence rules 4.1.0)":** the rules as they run.
  States in order, one determination per gate, verified ≠ mature, scope by financing and power
  model, the two ladders, checks and triggers, lenses, eligibility-not-money, the enforcement sentence
  (D3), no scores (D4). Then a state table with the engine's labels, requirements and capital
  decisions. Refinancing eligible is marked "not yet computed" (N22).
- **§1 → "Why the gates look like this: the September 2026 review" (D1):** dated history; two tests
  restored (B2); six facts with `[GEX 27 Sep]` plus what changed (A1); definitions polished (B3);
  hypothesis voice neutral (B1); Hydrogen Bank facts verified (B4); §1.6 rewritten as what 4.0.0 and
  4.1.0 built (A3).
- **§2:** "As built (4.1.0)" row in every gate table, including the G6 and G10 deviations (A2); G1
  renamed; subtitles corrected for per-item scope.
- **§3–§5:** "what GEX checks" states what the engine computes (D10); O- and E-level definitions quoted
  from the engine, with derivation, coverage and the captive-offtake rule (A4, N8, D13, D14); the
  offtake card as built plus roadmap (A5).
- **§6:** the phase map marked canonical; 60 % at pre-FEED; new **capital-commitment ladder**
  (concept, not computed), with dated evidence and the internal funding and tranche states mapped
  to it (D5).
- **§7:** "as known on 27 September 2026"; IF24 outcome added.
- **§8:** proposal → as built (A3): "Built:" per change, rows 9–10 for 4.1.0, the "as built" ladder,
  engine check titles with gates, triggers, two new "what not to do" rules (D4, D16); §8.6 is now
  **"What GEX does and does not decide"** (D3, D16).
- **§9:** limits updated (A6); market facts dated.
- **§10 (new) "Lessons from the EU Hydrogen Bank"** (D6), from the IF24 T&C, IF25 draft T&C and
  CINEA Q&A. Corrections to JML's §11: the 60 % HoT rules predate the withdrawals (N15); equity 60 % is of
  projected equity (N16); non-China, not non-EU (N3); guarantee 8 % (B4). Unverifiable commentary was
  removed and logged (N18). A requirement → GEX mapping table replaces the unsourced cross-check
  table (N5).
- **§11 Sources:** new dated entries; GEX sources without code paths (N13, list E).
- **Annex A** "After the gates: how capital is released" (D7, from GREENEARTHX §4.0–4.2, no code, no
  unsourced constants). **Annex B**: JML's three templates, marked illustrative, with the deadline
  corrected (N20). **Annex C**: glossary from the engine.
- **Footers** dated 30 Sept 2026.

## Notes on JML's edits (30 Sep, saved 14:38, Track Changes off)

JML's changes are all in §1 so far and are JML's text; nothing here was applied to the working copy.
Because Track Changes was off, these edits do not show as revisions. Turning it on
(Review → Track Changes) keeps the record the redline was built to give. Items worth a look:

1. **No subtitle.** Both the old and the new subtitle are gone from the title block. Intended?
2. **§1.1, test 2** now reads "Test 2 is the convergence the GEX mantra (Done now since 27Sep)."
   It lacks a verb, and "done" overstates: the engine computes convergence for the commitments on
   the cards, not for document content. Suggested: *"Test 2 is whether the conditions, dates and
   quantities in each party's commitment line up with the evidence in the other gates: the
   convergence the GEX mantra promises. Since rules 4.0.0 the engine computes it for the commitments
   recorded on the cards. [GEX]"* "Test 1 … asked of it" also needs a full stop.
3. **§1.1, first paragraph:** "Current evidence supports a "conditional convergence", not solely on
   the … as a one-way sequence." Suggested: *"Current evidence supports a "conditional convergence",
   not the one-way sequence "project maturity → … → financing"."*
4. **§1.2:** each fact now ends "[GEX 27 Sep] [GEX]". The trailing [GEX] belonged to the removed
   "Since rules 4.0.0 …" sentence; remove it. Fact 2 has "decision. .[GEX 27 Sep]".
5. **§1.4, EU Hydrogen Bank bullet** (B4 reopened): the European Commission, the only verified
   speaker, was dropped, so the quote has no attribution; a closing parenthesis after "€993m" is
   missing; "a bank guarantee 8%" lacks "of"; "policy and infrastructure and uncertainty" lost
   "delays"; "the EU auction" should name the Hydrogen Bank's second auction. Suggested: *"Of the 15
   winners of the EU Hydrogen Bank's second auction, 7 withdrew in 2025 (1.88 GW of 2.33 GW; €755m of
   €993m). The European Commission said they "chose not to proceed … completion guarantee" (a bank
   guarantee of 8% of the maximum grant); the companies cited policy and infrastructure delays and
   uncertainty."*
6. **§1.4 "Wrong":** "Buyers refrain from signing a binding L-T offtake before EPC certainty." now
   states as fact the belief that the paragraph refutes. It reads as a contradiction. Restore it as a
   quoted belief, e.g. *"Buyers will not sign a binding long-term offtake before EPC certainty."*;
   "“Good” buyers shy giving" → "shy away from giving"; there is a double full stop before it.
7. **§1.3:** "L-T" in a client document reads as shorthand; "creditworthiness capacity" lost a comma.
8. **From my build, still in the working copy:** in §9 the lead-in "The review changed GEX." is bold
   through "…section 2;" (N25), and the §4.1 header says "What it tells you" (N26). Both are fixed in
   the tools; I left JML's file alone.
9. **TOC** shows page 1 for every entry: update the field (F9) after editing.

## GREENEARTHX — what changed

Vocabulary aligned with rules 4.1.0 (C1–C8, C11, C15, N10): entropy table; §2.1 capital note; §2.3
participants (offtaker O2/O4/effective, insurer quotes at G7 and binds at G10, IE lender-only,
senior lender credit approval at G8, "ABAC actor type"); §2.4 verification mapping; §3 DSCR
doctrine, gate mapping correction and phase table; §5.1 Gantt offtake milestones and a Capital State
Gate mapping; §5.10 metrics flagged non-canonical; §6, §8, §9 and appendices aligned. Pointers to the
master throughout. Illustrations labelled (C14). Version trail made one (N6). The build-status section
is deleted as a tracked change and points to the handoff (C13). Left untouched: the pending June
insertions (dated corrections follow the wrong ones), the internal working notes and the pasted
29 July prompt (they stay internal; D9 scoped the redline to vocabulary and pointers).

## What could not be checked

- **Rendering and pagination.** LibreOffice and Poppler are not installed, so no page was rendered.
  Layout is unverified beyond the XML; the TOC page numbers need Word.
- **S&P Global, 18 Sep 2025:** paywalled (HTTP 403). The facts it carried were verified through
  Argus, Balkan Green Energy News and the Commission's IF24 page instead.
- **Montana Renewables' first DOE tranche** (N21): left at JML's figure; needs a primary source.
- **Handoff item 39:** three GREENEARTHX status claims are marked not re-verified.

## Follow-ups, not done here

- Code (D15): (a) finance-screen gate → capital reasons for the other capital types (N12);
  (b) the offtake-tenor hardcode, `contractual_rating_engine.py:227`; (c) the `customerProjects.ts`
  fixture. Also N22: compute or retire REFINANCING_ELIGIBLE.
- Decisions: O1, the meaning of the package state `approved` (proposed reading in
  `05_bridge_v6_disposition.md`); a single canonical pre-COD metric set (C12).
- `files/docs/README.md` is an index "accurate as of 2026-06-26". Only its Bridge v6 entries were
  updated. Its key-doctrine line "pre-COD metrics replace DSCR before G10" contradicts C11.
