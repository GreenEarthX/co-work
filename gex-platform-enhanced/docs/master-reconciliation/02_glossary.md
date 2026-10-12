# 02 — Canonical glossary (generated from the engine, rules 4.1.0)

Generated 2026-09-29 from `engine_export_rules_4.1.0.json` (`get_rules()`, `get_gates()`). The first half is the
running software's vocabulary, verbatim. The second half maps every competing term found in the three
documents to it. Where no canonical term exists, the row says so and names the decision.

## Gates

| Gate | Name | Leads to state | Capital decision it makes eligible | Views (personas) | Lender-only | Items |
|---|---|---|---|---|---|---|
| G0 (`G0_SITE_RIGHTS`) | Site Rights & Social License | TECHNICALLY_PLAUSIBLE | Grants & TA (`GRANTS_TA`) | PRODUCER, EXECUTIVE | no | 4 |
| G1 (`G1_GRID_UTILITIES_REALITY`) | Power, Utilities & Technology Basis | TECHNICALLY_PLAUSIBLE | Seed / VC / Angel (`SEED_VC_ANGEL`) | PRODUCER | no | 19 |
| G2 (`G2_CERTIFICATION_PATH_LOCKED`) | Green Certification Pathway | COMMERCIALLY_PLAUSIBLE | — | REGULATOR, OFFTAKER | no | 6 |
| G3 (`G3_INPUTS_SECURED`) | Feedstock & Logistics Terms | COMMERCIALLY_PLAUSIBLE | Strategic Equity (`STRATEGIC_EQUITY`) | PRODUCER | no | 4 |
| G4 (`G4_OFFTAKE_BANKABLE`) | Binding Offtake | BUILDABLE | Project Equity (`PROJECT_EQUITY`) | FINANCE, OFFTAKER | no | 10 |
| G5 (`G5_EPC_RISK_PRICED`) | EPC Risk Priced | BUILDABLE | — | PRODUCER, EXECUTIVE, OFFTAKER | no | 12 |
| G6 (`G6_IE_SIGNOFF`) | Independent Engineer Sign-off | STRUCTURALLY_BANKABLE | DFI / Mezz / Guarantees (`DFI_MEZZ_GUARANTEES`) | FINANCE, REGULATOR | yes | 5 |
| G7 (`G7_INSURANCE_BOUND`) | Insurability Confirmed | STRUCTURALLY_BANKABLE | — | FINANCE | no | 5 |
| G8 (`G8_AUDIT_GRADE_MODEL`) | Audit-Grade Financial Model | CREDIT_APPROVED | Senior Debt Credit Approval (conditional) (`SENIOR_DEBT_COMMITMENT`) | FINANCE | yes | 7 |
| G9 (`G9_PERMITS_SAFE`) | Permits Granted & Appeal Risk Managed | FINANCEABLE | — | PRODUCER, REGULATOR, OFFTAKER | no | 6 |
| G10 (`G10_FINANCIAL_CLOSE_CP`) | Financial Close | FINANCEABLE | Debt Drawdown (`DEBT_DRAWDOWN`) | FINANCE, OFFTAKER | no | 8 |
| G11 (`G11_COD_STABILIZATION`) | COD & Stabilization | OPERATIONAL | Refinance / Bonds / Infra (`REFINANCE_BONDS_INFRA`) | PRODUCER, EXECUTIVE, OFFTAKER | no | 7 |

## States (strictly sequential)

| # | State | Commitment label | Gates required | Commitment requirements (project finance / balance sheet) |
|---|---|---|---|---|
| 0 | SPECULATIVE | Idea stage — nothing can be committed yet | — | — |
| 1 | TECHNICALLY_PLAUSIBLE | Site and technology basis confirmed | G0, G1 | — |
| 2 | COMMERCIALLY_PLAUSIBLE | Commercially defined — offtake term sheets cover most of the output | G2, G3 | PF: offtake O2, offtake terms ≥ 60 % of output · BS: offtake O2, offtake terms ≥ 60 % of output |
| 3 | BUILDABLE | Commitment-ready — producer and offtaker can sign binding-with-conditions | G4, G5 | — |
| 4 | STRUCTURALLY_BANKABLE | Independently validated | G6, G7 | PF: offtake O6 · BS: — |
| 5 | CREDIT_APPROVED | Credit approved — conditional until financial close | G8 | — |
| 6 | FINANCEABLE | Committed — investment decision taken | G9, G10 | PF: offtake O7, offtake effective, epc E6 · BS: offtake O5, offtake effective, epc E6 |
| 7 | OPERATIONAL | Delivering — certified product accepted by the buyer | G11 | — |
| 8 | REFINANCING_ELIGIBLE | Proven — refinancing possible | — | — |

Gate-level commitment requirements: G4 needs offtake O4; G5 needs epc E4.

## Capital decisions

GEX makes a project *eligible for* a capital provider's decision; it never commits, releases or draws capital ("A satisfied gate makes a project eligible for the named capital provider's decision. GEX does not commit, release or draw capital.").

| Identifier | Label (4.1.0) | Gate | Scope |
|---|---|---|---|
| `GRANTS_TA` | Grants & TA | G0 | all projects |
| `SEED_VC_ANGEL` | Seed / VC / Angel | G1 | all projects |
| `STRATEGIC_EQUITY` | Strategic Equity | G3 | all projects |
| `PROJECT_EQUITY` | Project Equity | G4 | all projects |
| `DFI_MEZZ_GUARANTEES` | DFI / Mezz / Guarantees | G6 | project finance only |
| `SENIOR_DEBT_COMMITMENT` | Senior Debt Credit Approval (conditional) | G8 | project finance only |
| `DEBT_DRAWDOWN` | Debt Drawdown | G10 | project finance only |
| `REFINANCE_BONDS_INFRA` | Refinance / Bonds / Infra | G11 | all projects |

## Evidence: status, maturity, scope

- **Status** (per item): NOT_STARTED → IN_PROGRESS → SUBMITTED → UNDER_REVIEW → VERIFIED; REJECTED; EXPIRED; NOT_APPLICABLE (with reason POWER_MODEL or FINANCING_MODEL). Only VERIFIED counts.
- **Maturity** (separate axis): INTENT < INDICATIVE < AGREED < EXECUTED < EFFECTIVE. A VERIFIED instrument counts only at or above its required maturity; undeclared fails closed.
  - INTENT: Plan, mandate, letter of intent, MOU, strategy, or application in preparation.
  - INDICATIVE: Term sheet, quotation, indication of terms, or application submitted.
  - AGREED: Agreed-form document with all terms settled, not yet signed or granted.
  - EXECUTED: Signed, bound, granted, issued or passed.
  - EFFECTIVE: In force: conditions precedent satisfied, policy incepted, appeal period expired.
- **Financing scope**: 23 items protect a lender (`PROJECT_FINANCE`) and are not asked of a balance-sheet project; gates waived whole for balance sheet: G6, G8.

## Commitment ladders (derived, never entered)

| Offtake | Definition |
|---|---|
| O0 | No verified offtake document with a declared maturity. |
| O1 | MoU or letter of intent: a buyer exists; nothing binds. |
| O2 | Term sheet, heads of agreement or agreed form: commercial fit, not binding. |
| O3 | Signed, but not a binding commitment: a framework, volume or price not firm, or conditions with no longstop. |
| O4 | Binding, subject to conditions precedent with a longstop date. |
| O5 | Binding and effective: conditions satisfied; obligations run from COD. |
| O6 | Firm take-or-pay or take-if-tendered from an investment-grade or credit-supported buyer. |
| O7 | Project-finance grade: O6 plus tenor covering debt, assignment, step-in, a termination payment and allocated change in law. |

Firm take-or-pay threshold (O6): 60 % of contract quantity. Offtake coverage bar at COMMERCIALLY_PLAUSIBLE: 60 % of planned output (fallback: EPC guaranteed capacity).

| EPC | Definition |
|---|---|
| E0 | No contracting strategy and no verified EPC document. |
| E1 | Strategy defined: contracting model chosen, contractor candidates identified. |
| E2 | FEED complete (AACE Class 3 or better). |
| E3 | Priced proposal: a verified quotation or term sheet on the FEED basis. |
| E4 | Agreed form: price, schedule, guarantees, damages and caps, security and licence guarantee all agreed. |
| E5 | Executed; long-lead items ordered. |
| E6 | Effective and bankable: notice to proceed issued, security posted. |

## Coherence checks and post-FID triggers

Statuses: PASS / FAIL decide — a FAIL blocks the check's gate; NOT_EVALUABLE (data missing) and NOT_APPLICABLE never block and never pass.

| Check | Gate | Lenses | Test |
|---|---|---|---|
| C1 | G4 | PRODUCER, OFFTAKER | First delivery after guaranteed completion plus commissioning allowance |
| C2 | G4 | PRODUCER, OFFTAKER, CAPITAL | Contracted volume within guaranteed capacity × availability |
| C3 | G4 | PRODUCER, OFFTAKER | Offtake specification guaranteed by the EPC or licensor |
| C4 | G5 | PRODUCER, CAPITAL | Offtake delay exposure backed by EPC damages, contingency and sponsor support |
| C5 | G4 | PRODUCER, OFFTAKER, CAPITAL | Longstop covers permits, investment decision, construction and commissioning |
| C6 | G4 | PRODUCER, CAPITAL | Feedstock and power contracted for the offtake's volume and tenor |
| C7 | G4 | CERTIFIER, OFFTAKER | Power and CO2 sourcing meet the certification the offtake requires |
| C8 | G4 | CERTIFIER, OFFTAKER | Producer certifies under the scheme the offtake requires |
| C9 | G10 | PRODUCER, OFFTAKER, CAPITAL | Force majeure aligned across offtake, EPC and supply contracts |
| C10 | G8 | CAPITAL | Model inputs equal contract terms; offtake tenor covers debt |

| Trigger | Card field | Gates blocked | Meaning |
|---|---|---|---|
| T1 | `supply.support_or_ppa_revoked` | G1 | Power contract or public support terms revoked |
| T2 | `supply.certification_suspended` | G2, G11 | Certification suspended |
| T3 | `epc.counterparty_insolvent` | G5 | EPC contractor or key OEM insolvent |

## Lenses and views

Lenses are views over one evidence base, never separate scores:

- **PRODUCER** — Can the developer build, run, certify and deliver what it is being asked to commit to?
- **OFFTAKER** — Can the buyer rely on receiving certified product, on time and to specification?
- **CAPITAL** — Can equity, lenders, development finance and insurers underwrite the risk allocation?
- **CERTIFIER** — Will the product be certifiable, and certified, under the scheme the market requires?

Gate views (personas on the gate model): PRODUCER: G0, G1, G3, G5, G9, G11; FINANCE: G4, G6, G7, G8, G10; REGULATOR: G2, G6, G9; OFFTAKER: G2, G4, G5, G9, G10, G11; EXECUTIVE: G0, G1, G2, G3, G4, G5, G6, G7, G8, G9, G10, G11.

## Commitment cards

- **offtake**: `counterparty_name`, `counterparty_role`, `planned_output_tonnes_per_year`, `buyer_investment_grade`, `credit_support`, `commitment_form`, `take_or_pay_pct`, `contracted_tonnes_per_year`, `tenor_years`, `price_mechanism`, `cps_satisfied`, `conditions_precedent`, `longstop_date`, `first_delivery_date`, `delay_ld_cap_eur`, `product_spec_standard`, `certification_scheme`, `compliance_regime`, `fm_definition_ref`, `change_in_law_allocated`
- **epc**: `contractor_name`, `contracting_model`, `contract_price_eur`, `guaranteed_completion_date`, `guaranteed_capacity_tonnes_per_year`, `expected_availability_pct`, `delay_ld_cap_eur`, `performance_ld_cap_eur`, `guaranteed_product_spec`, `contingency_eur`, `sponsor_support_eur`, `fm_definition_ref`, `counterparty_insolvent`
- **schedule**: `permits_expected_date`, `appeal_period_months`, `fid_target_date`, `construction_months_p80`, `commissioning_allowance_months`, `forecast_cod_date`
- **supply**: `feedstock_required_tonnes_per_year`, `feedstock_contracted_tonnes_per_year`, `feedstock_tenor_years`, `power_required_mwh_per_year`, `power_contracted_mwh_per_year`, `power_tenor_years`, `power_meets_certification`, `co2_source_eligible`, `certification_scheme`, `fm_definition_ref`, `support_or_ppa_revoked`, `certification_suspended`
- **model**: `debt_tenor_years`, `model_contracted_tonnes_per_year`, `model_offtake_tenor_years`, `model_epc_price_eur`

---

# Aliases found in the documents, mapped to the canonical terms

Each row: the term as written, where it appears, what it maps to, and whether a decision is
needed (D# in `04_decisions_for_JML.md`). "No canonical equivalent" means the running
software has no such concept.

## Gates and states

| Term as written | Where | Canonical mapping | Decision |
|---|---|---|---|
| "G1 · Power, Water & Critical Utility Access" | Master §2 heading | G1 "Power, Utilities & Technology Basis" (renamed 4.0.0) | — |
| Coarse "Gate 1–4" (Concept / Solution / Scaling / Commercial validation) | GREENEARTHX §3 note | Proposed: Gate 1 = G0–G1 (TECHNICALLY_PLAUSIBLE); Gate 2 = G2–G3 (COMMERCIALLY_PLAUSIBLE); Gate 3 = G4–G8 (BUILDABLE → CREDIT_APPROVED); Gate 4 = G9–G11 (FINANCEABLE → OPERATIONAL). The document's own mapping leaves G4, G7–G9 out | D10 |
| "Capital State Gate 1–8" (Gantt milestones) | GREENEARTHX §5.1 | No engine concept. Approximate: CSG1–2 ≈ TECHNICALLY/COMMERCIALLY_PLAUSIBLE; CSG3 ≈ BUILDABLE/STRUCTURALLY_BANKABLE; CSG4 ≈ CREDIT_APPROVED; CSG5 ≈ signing before close; CSG6 ≈ FINANCEABLE; CSG7 ≈ construction (no state); CSG8 ≈ OPERATIONAL | D5 |
| Phases FEL-1 / FEL-2 / FEED / FID readiness / Construction / COD | GREENEARTHX §3, Bridge §3, master §6 | A separate lifecycle axis; a phase contains gates. One reconciled phase × gate × ladder × capital table goes in the master (D-b) | D12 |
| "Structurally bankable / Credit approved / Financeable" | all three | Engine states of the same names; labels per the table above | — |

## Commitments and timing

| Term as written | Where | Canonical mapping | Decision |
|---|---|---|---|
| "Offtaker signs HoT at G4, binding at G10" | GREENEARTHX §2.3 | HoT = O2, needed for **COMMERCIALLY_PLAUSIBLE** with ≥ 60 % coverage (4.1.0); **G4 needs O4** (binding with conditions and longstop); **FINANCEABLE needs the offtake effective** (O5 balance sheet / O7 project finance) | D12 |
| "Offtake LOI signed" (pre-FEED), "Offtake HoT signed" (FEED) | Bridge §3 | LOI = O1; HoT = O2 | D12 |
| "Binding offtake evidence (G4) + Trust Score" | entropy table, both internal docs | O-level (derived) + offtake coverage; no Trust Score in the engine | D4 |
| "Revenue Anchor Score (RAS) 0–100; LOI 30, binding IG 85+; ≥ 75 for G10" | GREENEARTHX §5.10, Bridge §6 | No canonical equivalent; overlaps the O-ladder. FINANCEABLE requires O5/O7 effective, not a score | D4, D11 |
| "EPC approved / EPC verified" | common usage | E-level (derived) — verification, maturity and coherence are three separate facts | — |
| "Insurer binds CAR/EAR/DSU at G7"; "Insurance bound" at FID readiness; "CAR bound at G7" | GREENEARTHX §2.3; Bridge §3, §9 | G7 = **insurability** (quoted terms, market report, exclusions/FOAK backstop, lender deductibles); **bound at G10** (`insurance_certificates_delivered`, EFFECTIVE) | — (evidence: 00 file) |
| "Senior Debt and ECA are gated behind G10"; "Concessional first-loss (DFI at G10) → senior debt commitment" | GREENEARTHX §2.1, entropy table | **G6** → DFI/Mezz/Guarantees; **G8** → Senior Debt Credit Approval (conditional); **G10** → Debt Drawdown. ECA: no engine capital type | D5 |
| "Senior Debt Commitment" | frontend label (before 4.1.0) | **Senior Debt Credit Approval (conditional)** — identifier `SENIOR_DEBT_COMMITMENT` unchanged | done (4.1.0) |
| "Capital approved" (CREDIT_APPROVED label) | engine before 4.1.0 | "Credit approved — conditional until financial close" | done (4.1.0) |
| Funding legal status: Announced / Indicative / Term-sheeted / Credit-approved / Legally committed / CP-satisfied / Available / Drawn / Spent / Verified eligible use; "chain of investment promises" | GREENEARTHX §4, §5 | No engine ladder. Candidate third commitment ladder (capital side), not computed. Maps onto capital decisions: credit-approved ↔ G8; legally committed + CP-satisfied ↔ G10 financial close; drawn ↔ after G10 | D5 |
| Tranche states: proposed → due_diligence → conditional_offer → mandated → signed → committed → partially_drawn → fully_drawn → repaying → repaid | GREENEARTHX App. B | Internal object state; relates to the funding ladder above | D5 |
| Package states: identified → scoped → costed → evidenced → eligible → approved → committed → drawable → drawn → closed (and Bridge's 8-state variant ending "propagated") | GREENEARTHX §5.2 / App. B; Bridge §8 | Internal object state; `unlock_condition` links packages to gate evidence. Two variants in the documents; one should go | D9 |

## Evidence and verification

| Term as written | Where | Canonical mapping | Decision |
|---|---|---|---|
| UNVERIFIED / SUBMITTED / CONFIRMED / AUDITED ("CONFIRMED → gate progress credit awarded") | GREENEARTHX §2.4, §6; `app/core/verification.py` | Gate evidence status: UNVERIFIED ≈ NOT_STARTED / IN_PROGRESS; SUBMITTED ≈ SUBMITTED / UNDER_REVIEW; CONFIRMED ≈ VERIFIED **and** maturity met; AUDITED — no gate equivalent (independent re-verification) | D9 |
| "Verified" used for maturity | common usage | Verified = authentic; maturity = how far the instrument has progressed | — |
| Evidence labels [E] [P] [O] [I] [GEX] | Master front matter | Keep; [I] "My inference" → "GEX inference" if D2; [GEX] needs a date | D2 |

## Scores

| Term as written | Where | Canonical mapping | Decision |
|---|---|---|---|
| "GEX project quality score (67 % → 83 % → 91 %, or BB → A → AA)"; "at threshold 85 %+ matched providers notified" | Bridge, Meher Q&A | No canonical equivalent; conflicts with "readiness is emergent, never authored" and "one determination per gate" | D4 |
| "Trust Score 89/100" | Bridge §9 example; entropy table | No canonical equivalent | D4 |
| "Decomposed Certainty Stack" (cost / revenue / certification / execution / counterparty) | GREENEARTHX §9, App. E | Not in the engine's rules; lenses are the engine's per-party view | D4 |
| Offtake tenor score `min(max_tenor / 10.0 * 60, 60)` | code: `backend/app/core/contractual_rating_engine.py:227` | Conflicts with O7 / C10 (tenor vs the project's own debt tenor) | D15 |

## Parties

| Term as written | Where | Canonical mapping | Decision |
|---|---|---|---|
| "Persona" = 15–16 ABAC actor types (PRODUCER … SETTLEMENT_AGENT) | GREENEARTHX §2.3 | **ABAC actor type** (who may act) | D9 |
| Gate views PRODUCER / FINANCE / REGULATOR / OFFTAKER / EXECUTIVE | engine | **Gate view** (which gates a party sees) | — |
| Lenses PRODUCER / OFFTAKER / CAPITAL / CERTIFIER | engine | **Lens** (what an item means to a party) | — |
| "Independent Engineer signs G6" (all projects) | GREENEARTHX §2.3 | G6 is lender-only (project finance). All projects: `independent_technical_review` in G5 | — |

## Capital vocabularies in code and documents

| Vocabulary | Where | Values | Relation to the canonical decisions |
|---|---|---|---|
| Capital decisions (canonical) | engine `CAPITAL_TYPES` | 8 decision-eligibility types | canonical |
| Funding layers | `backend/app/api/v1/spend_wave.py` `CapitalLayer` | EQUITY_SEED, EQUITY_SPONSOR, GRANT, BRIDGE, DFI_EIB … DFI_AFDB, SENIOR, ECA | who funds a spend row — a different axis |
| Package `capital_eligible` | GREENEARTHX §5.2 | EQUITY, GRANT, BRIDGE, VENDOR(_FINANCE), CONCESSIONAL, SENIOR_DEBT, ECA, DSRA | different axis (funding sources) |
| Capital Eligibility Bar | GREENEARTHX App. E; `CapitalEligibilityBar.tsx` | EQUITY, GRANT, BRIDGE, CONCESSIONAL, SENIOR_DEBT, ECA | presentation grouping; maps decisions to buckets |
| Tranche subtypes | GREENEARTHX §5.8 | EQUITY_SEED … GREEN_BOND (12) | internal |
| Funder type | GREENEARTHX §5 A | Sponsor, Senior Bank, DFI, ECA, Government Grant, Mezzanine, Equipment Lessor | internal |

Clients should see only the canonical decision labels; the other vocabularies describe who
provides money and are internal.
