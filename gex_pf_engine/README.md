# GEX Project Finance Engine

Microservice providing financial modelling and bankability evaluation for green fuel projects (H₂, NH₃, SAF, e-MeOH). Runs on **port 8001**, called exclusively by the GEX platform backend (port 8000).

---

## Architecture

```text
Frontend (port 3000)
    │
    ▼
GEX Platform Backend (port 8000)   ← orchestration, evidence store, user auth
    │
    ▼
GEX Project Finance Engine (port 8001)   ← this service
```

---

## Core Modules

| Module | Location | Purpose |
| --- | --- | --- |
| Bankability Engine | `pf_engine/core/bankability_engine.py` | 12-gate state machine, evidence rules 4.1.0: maturity axis, offtake/EPC ladders, offtake coverage, coherence checks, lenses |
| CFADS Calculator | `app/core/cfads.py` | Cash flow available for debt service |
| Waterfall Engine | `app/core/waterfall.py` | Senior/junior/mezz priority distribution |
| Debt Sculpting | `app/core/debt/sculpting.py` | DSCR-sculpted repayment schedules |
| Audit | `app/core/audit.py` | Cryptographic audit trail |

---

## API Surface

| Prefix | Routes file | Description |
| --- | --- | --- |
| `/api/v1/bankability` | `app/api/routes_bankability.py` | 12-gate evaluation, persona views, rules |
| `/api/v1/model` | `app/api/routes_model.py` | CFADS, lifetime model, covenants, waterfall |

---

## Bankability Engine

**9-state, 12-gate** lifecycle:

`SPECULATIVE` → `TECHNICALLY_PLAUSIBLE` → `COMMERCIALLY_PLAUSIBLE` → `BUILDABLE` → `STRUCTURALLY_BANKABLE` → `CREDIT_APPROVED` → `FINANCEABLE` → `OPERATIONAL` → `REFINANCING_ELIGIBLE`

**Gates (G0–G11).** Two ownership axes, deliberately distinct: `personas` is who
SEES the gate (platform visibility); `accountable_functions` is who DOES the work
(organisational function). They were once a single `owners` field meaning
different things here and in the platform's registry, which is how the two
drifted until only 2 of 12 gate ids matched. `tests/test_gate_registries_agree.py`
in the platform repo now fails if they diverge again.

| Gate | id | Name | Kind | Personas (see) | Accountable functions (do) | Items |
| --- | --- | --- | --- | --- | --- | --- |
| G0 | `G0_SITE_RIGHTS` | Site Rights & Social License | achievement | PRODUCER, EXECUTIVE | PROJECT, LEGAL | 4 |
| G1 | `G1_GRID_UTILITIES_REALITY` | Power, Utilities & Technology Basis | readiness | PRODUCER | ENGINEERING, PROJECT, FINANCE | 19 |
| G2 | `G2_CERTIFICATION_PATH_LOCKED` | Green Certification Pathway | readiness | REGULATOR, OFFTAKER | ENGINEERING, LEGAL | 6 |
| G3 | `G3_INPUTS_SECURED` | Feedstock & Logistics Terms | readiness | PRODUCER | ENGINEERING, PROJECT, FINANCE | 4 |
| G4 | `G4_OFFTAKE_BANKABLE` | Binding Offtake | achievement | FINANCE, OFFTAKER | SALES, LEGAL, FINANCE | 10 |
| G5 | `G5_EPC_RISK_PRICED` | EPC Risk Priced | achievement (agreed form) | PRODUCER, EXECUTIVE, OFFTAKER | PROJECT, ENGINEERING, LEGAL | 12 |
| G6 | `G6_IE_SIGNOFF` | Independent Engineer Sign-off | achievement | FINANCE, REGULATOR | INDEPENDENT_ENGINEER, LENDERS | 5 |
| G7 | `G7_INSURANCE_BOUND` | Insurability Confirmed | readiness | FINANCE | TREASURY, LEGAL, LENDERS | 5 |
| G8 | `G8_AUDIT_GRADE_MODEL` | Audit-Grade Financial Model | achievement | FINANCE | FINANCE, LENDERS | 7 |
| G9 | `G9_PERMITS_SAFE` | Permits Granted & Appeal Risk Managed | achievement | PRODUCER, REGULATOR, OFFTAKER | PROJECT, LEGAL | 6 |
| G10 | `G10_FINANCIAL_CLOSE_CP` | Financial Close | achievement | FINANCE, OFFTAKER | LENDERS, LEGAL, TREASURY, FINANCE | 8 |
| G11 | `G11_COD_STABILIZATION` | COD & Stabilization | achievement | PRODUCER, EXECUTIVE, OFFTAKER | PROJECT, ENGINEERING, FINANCE | 7 |

**Evidence rules 3.0.0 — "the stronger bar" (2026-09-25).** Where a gate's name
claims an achieved condition, its evidence requires the achievement, not an
intention: permits GRANTED not submitted, CPs SATISFIED not drafted, tests PASSED
not planned, the model AUDITED not merely engaged. Readiness gates stay readiness
gates at the maturity their stage allows — and every readiness instrument (PPA,
feedstock supply, EPC, insurance) must be EXECUTED at G10, where the ladder turns
terms into commitments. 77 evidence items; 26 keys retired, each with a named
replacement in `RETIRED_EVIDENCE`. G3's and G7's ids keep "SECURED" / "BOUND" for
identifier stability; their names state what is actually tested.

**Evidence rules 4.0.0 — every gate through every party's eyes (2026-09-27).**
Decision and evidence: `docs/GEX-Twelve-Gates-Multi-Party-Review.docx` in the
platform repo. Still twelve gates; what changed is what a gate asks and of whom.

- **Financing scope is per item, not per gate.** 23 items protect an external
  lender (`EVIDENCE_SCOPE`); a `BALANCE_SHEET` project is not asked for them. G6
  and G8 consist only of such items and are waived whole (`LENDER_ONLY_GATES`);
  G4, G7 and G10 keep their commercial and legal items. Debt capital
  (`CAPITAL_SCOPE`) is out of scope for balance-sheet funding.
- **Commitment ladders.** The offtake is graded O0–O7 and the EPC E0–E6, derived
  from verified evidence maturity plus the commitment cards — never entered. G4
  needs O4 (binding, conditions with a longstop), G5 needs E4 (agreed form).
  `STRUCTURALLY_BANKABLE` needs O6 under project finance; `FINANCEABLE` needs
  O7, an effective offtake and E6 (O5, effective, E6 on a balance sheet). O6
  means firm (take-or-pay ≥ `TAKE_OR_PAY_FIRM_PCT` = 60 %, or take-if-tendered)
  from a creditworthy buyer; O7 adds tenor ≥ debt tenor, assignment, step-in, a
  termination payment and allocated change in law.
- **Commitment cards** — `offtake`, `epc`, `schedule`, `supply`, `model`
  (`COMMITMENT_CARD_FIELDS`). The platform stores them (migration 058) and sends
  them with every evaluation as `terms`.
- **Ten coherence checks** (C1–C10) compare one commitment with another:
  delivery date vs guaranteed completion, contracted volume vs capacity ×
  availability, spec, damages backing, longstop vs schedule, supply vs offtake,
  certification sourcing and scheme, force-majeure alignment, model vs
  contracts. `PASS`/`FAIL` decide and a FAIL blocks its gate; `NOT_EVALUABLE`
  (data missing) and `NOT_APPLICABLE` never block but are never a pass. They
  compare what the cards record — the producer's statement of its contracts —
  not the documents themselves.
- **Post-FID triggers** T1–T3 (power or support revoked, certification
  suspended, contractor insolvent) block the gates they undermine.
- **Lenses** PRODUCER, OFFTAKER, CAPITAL, CERTIFIER on every item
  (`EVIDENCE_LENSES`, `lens_readouts` per gate): views over one evidence base,
  never separate scores. OFFTAKER is also a persona.
- **16 items added** (77 → 93): technology basis, FEED, licence guarantee,
  long-lead orders, EPC security, independent technical review, product
  qualification, seller-side offtake terms, certificates issued, deliveries
  accepted. G1 renamed "Power, Utilities & Technology Basis".
- **Dual state labels.** Each state also names the commitment it makes possible
  (`STATE_COMMITMENT_LABELS`), e.g. `BUILDABLE` — "Commitment-ready — producer
  and offtaker can sign binding-with-conditions".

A gate is now complete when its items are (`items_complete`) *and* its commitment
level is met *and* no coherence check fails *and* no trigger is active;
`blocked_reasons` says which. Snapshot additions: `offtake`, `epc`,
`coherence_checks`, `regression_triggers`, `commitment_requirements`,
`state_label`, `next_state_label`, `commitments_blocking_next_state`; per item
`scope`, `lenses`, `not_applicable_reason` (`POWER_MODEL` / `FINANCING_MODEL`).

**Evidence rules 4.1.0 (2026-09-29) — stricter, can lower a state.** Evidence:
`docs/master-reconciliation/00_market_evidence_gate_timing.md` in the platform repo.
COMMERCIALLY_PLAUSIBLE now also needs offtake terms (O2 or better) covering at least
`OFFTAKE_COVERAGE_MIN_PCT` = 60 % of planned output — the bar the EU Hydrogen Bank sets at
application. Coverage = offtake card `contracted_tonnes_per_year` ÷ `planned_output_tonnes_per_year`
(new field; EPC guaranteed capacity as fallback); an uncomputable coverage fails closed. Capital
decisions carry display labels (`CAPITAL_TYPE_LABELS`, sent as `label` on each capital unlock);
`SENIOR_DEBT_COMMITMENT` reads "Senior Debt Credit Approval (conditional)" and CREDIT_APPROVED's
commitment label "Credit approved — conditional until financial close". Identifiers unchanged.

**Maturity is a separate axis from verification.** `INTENT < INDICATIVE < AGREED
< EXECUTED < EFFECTIVE`. Verification says a document is authentic; it does not
make a term sheet into a contract. 31 instrument items (24 before 4.0.0) carry a `REQUIRED_MATURITY`;
a VERIFIED item counts only at or above it, and undeclared maturity fails closed.
The submitter declares maturity; a reviewer may confirm or lower it, never raise it
(enforced on the platform write path).

**Capital.** A satisfied gate makes a project *eligible for the capital provider's
decision*. The engine does not commit, release or draw capital — `decision_eligible`
says so; `is_unlocked` is a deprecated alias kept for existing consumers.

**Determinations.** Every gate evaluation carries one of `SATISFIED`, `BLOCKED`,
`INCOMPLETE` or `WAIVED`. A gate waived by financing model counts toward the state
ladder but is never presented as satisfied by evidence.

`is_complete` is `verified == applicable_total`, not a threshold.

**Persona views:**

| Persona | Gates |
| --- | --- |
| PRODUCER | G0, G1, G3, G5, G9, G11 |
| FINANCE | G4, G6, G7, G8, G10 |
| REGULATOR | G2, G6, G9 |
| OFFTAKER | G2, G4, G5, G9, G10, G11 |
| EXECUTIVE | all twelve + portfolio summary |

Persona filtering drops gates from an already-computed snapshot. State, capital
unlocks and overall completion are still calculated across all twelve, so a
persona sees a subset of gates alongside a percentage that answers a different
question.

**Current completion logic (rules 4.0.0, 2026-09-27):** an item counts when it is VERIFIED *and*, for instruments, at or above its required maturity; `completion_pct` counts items meeting both. A gate is complete when all its applicable items count *and* the commitment and coherence conditions above hold. Convergence is now measured only as far as the coherence checks reach: they compare the commitment cards with each other, not the content of the evidence documents (IE production against the model, for instance, is still unchecked). An empty card makes its checks `NOT_EVALUABLE`, which is shown, never counted as coherent.

**Tests.** `tests/test_bankability_gates.py` — 96 collected; every 4.0.0 and 4.1.0 rule mutation-tested (7 + 7 caught). Engine suite 239 pass on 2026-09-29. The engine had no tests of its own before 3.0.0.

---

## Integrity Status (2026-04-05)

- Core bankability and financial-model modules compile and remain usable through the platform proxy.
- `app/api/routes_model.py` still contains placeholder project-summary integration, so model outputs are not yet fully grounded in one shared project truth.
- `app/core/engine.py` still carries the shared event-store TODO, so engine events are not yet integrated into a broader operational event spine.
- `micro_service/` exists in this workspace as local runtime material. It should be treated as environment state, not source architecture.

---

## Quick Start

```bash
cd backend

# Install dependencies
python -m venv ../micro_service
source ../micro_service/bin/activate
pip install -r requirements.txt

# Start the engine
uvicorn pf_engine.main:app --host 0.0.0.0 --port 8001 --reload
```

API docs: `http://localhost:8001/docs`

---

## Key Endpoints

### Bankability

```text
POST /api/v1/bankability/evaluate
     Body: { "project_id": "...", "evidence": [...], "previous_state": "..." }
     Returns: current_state, gate_evaluations, capital_unlocks, overall_completion_pct

POST /api/v1/bankability/evaluate/persona
     Body: { "project_id": "...", "evidence": [...], "persona": "FINANCE", "previous_state": "..." }
     Returns: persona-filtered gate_evaluations, capital_unlocks

GET  /api/v1/bankability/gates    → all 12 gate definitions
GET  /api/v1/bankability/rules    → state machine rules
GET  /api/v1/bankability/health
```

### Financial Model

```text
POST /api/v1/model/cfads/calculate         → CFADS for a period
POST /api/v1/model/model/lifetime          → full project lifetime model
POST /api/v1/model/covenants/check         → DSCR / LLCR covenant check
POST /api/v1/model/waterfall/execute       → debt waterfall distribution
POST /api/v1/model/metrics/calculate       → key financial metrics
GET  /api/v1/model/health
```

---

## Project Structure

```text
gex_pf_engine/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── api/
│   │   │   ├── routes_bankability.py  # Bankability endpoints
│   │   │   └── routes_model.py        # Financial model endpoints
│   │   └── core/
│   │       ├── bankability_engine.py  # 12-gate engine
│   │       ├── cfads.py               # CFADS calculator
│   │       ├── waterfall.py           # Waterfall distribution
│   │       ├── audit.py               # Audit trail (stub)
│   │       └── debt/
│   │           ├── sculpting.py       # Debt sculpting (stub)
│   │           └── tranche.py         # Tranche management (stub)
│   └── requirements.txt
├── micro_service/                     # Local venv present in this workspace; runtime material, not source
└── docs/
    └── ARCHITECTURE.md
```

---

## License

Proprietary — GreenEarthX
