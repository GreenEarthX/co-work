# 04 — Decisions for JML (checkpoint)

**DECIDED 2026-09-29: JML accepted all recommendations (D1–D17) as written below.**

The reconciliation stops here until these are answered. No document has been edited. Each
decision has a recommended default; "accept all" is a valid answer. Evidence for D3, D5, D12
and D13 is in `00_market_evidence_gate_timing.md`; conflict IDs refer to `03_conflict_register.md`.

| # | Decision | Recommended default | Why | Conflicts |
|---|---|---|---|---|
| D1 | What the master is | The **as-built client reference** for rules 4.1.0. The September critique stays as dated history: "why the gates look like this". New subtitle, e.g. *How GEX judges a green-fuel project, and why*. | The software now implements the critique's proposal; a client needs today's rules, with the reasoning. | A1–A3, A6, B3, B6 |
| D2 | Voice and labels | Neutral, "GEX" as author; no "you / your hypothesis / I". `[I]` becomes "GEX inference"; restore dated `[GEX]` labels. | A client reads a reference, not a reply to a question. | B1, B7 |
| D3 | Enforcement sentence | "GEX enforces the evidence standard; capital providers make every funding decision." | Funders enforce hard conditions (IF25 termination and guarantee, UK SAF milestones, lenders' CPs); Bridge v6's "never blocks" contradicts the software. | C9 |
| D4 | Scores | No composite, quality or trust score in client material. Show gate determinations, O/E levels, offtake coverage and coherence results. Internal scores must be derived, never typed. | One determination per gate; "readiness is emergent, never authored". Three competing score concepts exist today. | C8 |
| D5 | Capital-commitment ladder | Add it to the master as a **concept** beside the offtake and EPC ladders: credit approval → signing with conditions → financial close → drawdown. Label "not yet computed". Map the internal funding and tranche states to it. | Every financing sampled ran these stages months apart, and conditional commitments lapse (Gevo, Plug). | C3, C6 |
| D6 | Master §11 (EU Hydrogen Bank) | Keep the verified content as "Lessons from the EU Hydrogen Bank", mapped to gates and levels. Move the three templates to an annex marked "illustrative, not legal advice". Drop the unsourced "rejection reason" column unless a source is found. | IF25's primary documents confirm most of §11; one error (non-China, not non-EU). | B4, B5, N3, N5, N13 |
| D7 | CFO annex | Add a short annex, "After the gates: how capital is released", from GREENEARTHX §4.0–4.2, with no code. | Useful to producers' CFOs and funders; currently internal only. | — |
| D8 | Bridge v6 | Archive it, renamed `…_SUPERSEDED`, with a decision log capturing its Q&A. | GREENEARTHX supersedes it; its unique positions need decisions (D3, D4, D16). | C9, C10 |
| D9 | GREENEARTHX | Tracked-change redline limited to vocabulary alignment (gates, states, capital, verification, "persona") plus pointers to the master. Move build status to `docs/CLAUDE_HANDOFF.md` after re-verification. Label illustrations. Fix the version trail. | Keeps the internal spec internal while stopping it from contradicting the software. | C1–C8, C11, C13–C15, N6, N10 |
| D10 | Master vs engine wording | The master quotes the engine's definitions verbatim (O/E levels, cards, checks). Richer proposals become roadmap. Where the document is better than the code, open a separate code task. | One canonical source. | A2, A4, A5, C5 |
| D11 | Pre-COD metrics | Keep them out of the client master until one derived set is canonical. | Two sets with conflicting thresholds and a mis-defined ECR. | C12 |
| D12 | Offtake timing | Canonical: heads of terms (O2) for ≥ 60 % of output at Commercially Plausible; binding with conditions (O4) at G4; effective at Financeable. Correct the internal timelines. | Matches every financed deal sampled and the EU funder's own rules. | C1 |
| D13 | Describe rules 4.1.0 in the master | Yes: the 60 % heads-of-terms bar, the conditional senior-debt label and the new state labels. | Live since today. | N7, N8 |
| D14 | Captive offtake under 4.1.0 | Require an intra-group offtake card; no exemption for now. | Offtake is commercial substance whoever the buyer is; an exemption can come later if a real captive client needs it. | N14 |
| D15 | Code follow-ups | Separate tasks: (a) the finance screen's remaining gate → capital reasons; (b) the offtake tenor hardcode in `contractual_rating_engine.py:227`; (c) the `customerProjects.ts` fixture (handoff item 28). | Out of the documents' scope; each is a small, testable change. | N12, C8 |
| D16 | Provider-configurable thresholds (Bridge) | No. One GEX standard; each capital provider applies its own credit criteria to the evidence GEX shows. At most a roadmap idea. | The engine has one standard; configurable thresholds would split "one determination per gate". | C10 |
| D17 | Fees in the master | Leave fees out of the master; commercial terms belong in the client contract. | Bridge v6's fee wording is internal; the throughput fee is not settled in any of the three documents. | — |

## Status, 30 Sep 2026

- **Phase 4 done.** Deliverables and checks: `05_change_summary.md`. The original master was never
  modified; the redline is a new file, `GEX-Gates-Master_v2_redline.docx`, which JML has since
  edited in Word (see the change summary).
- **Database.** The development PostgreSQL database, reset on 28 Sep, was rebuilt on 30 Sep by
  another session (`docs/CLAUDE_HANDOFF.md` §8 item 38). The 4.1.0 labels were then checked on the
  live screen (G8 reads "Senior Debt Credit Approval (conditional)"; offtake reads "O0 · coverage
  not recorded"). Nothing in the documents work depends on the database.
- **Open after the decisions:** O1, the meaning of the package state `approved`
  (`05_bridge_v6_disposition.md`), and the items marked Open or Reopened in `03_conflict_register.md`.
