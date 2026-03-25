# GEX Project Finance Engine — Architecture

Version: **v6.0 R2** · Port: **8001**

---

## Overview

The GEX Project Finance Engine is a Python/FastAPI microservice that provides:

1. **Bankability evaluation** — 12-gate, 9-state lifecycle state machine with verification-weighted scores
2. **Financial modelling** — CFADS, debt waterfall, DSCR sculpting, covenant checks
3. **Audit trail** — cryptographic SHA-256 event chain for tamper-evident history

It is called exclusively by the GEX Platform Backend (port 8000). The frontend never contacts this service directly.

---

## State Machine

### 9 States

```text
SPECULATIVE
  → TECHNICALLY_PLAUSIBLE      (G0 + G1 gates cleared)
  → COMMERCIALLY_PLAUSIBLE     (G2 + G3 gates cleared)
  → BUILDABLE                  (G4 + G5 gates cleared)
  → STRUCTURALLY_BANKABLE      (G6 + G7 gates cleared)
  → CREDIT_APPROVED            (G8 gate cleared)
  → FINANCEABLE                (G9 + G10 gates cleared)
  → OPERATIONAL                (G11 gate cleared)
  → REFINANCING_ELIGIBLE       (all gates AUDITED, DSCR ≥ 1.35 sustained)
```

Transitions are **forward-only**. Regression to a lower state is not supported by the state machine; it is surfaced as a deal-killer flag instead.

### 12 Gates (G0–G11)

| Gate | Name | Min Effective Score | Gate Owners |
| --- | --- | --- | --- |
| G0 | Site Rights & Social License | 0.70 | PRODUCER, EXECUTIVE |
| G1 | Grid Connection & Water/Utilities | 0.70 | PRODUCER |
| G2 | Green Certification Pathway | 0.75 | REGULATOR |
| G3 | Feedstock & Logistics | 0.70 | PRODUCER |
| G4 | Binding Offtake | 0.80 | FINANCE |
| G5 | EPC & Construction | 0.75 | PRODUCER, EXECUTIVE |
| G6 | Independent Engineer Signoff | 0.85 | FINANCE, REGULATOR |
| G7 | Insurance Package | 0.80 | FINANCE |
| G8 | Audit-Grade Financial Model | 0.90 | FINANCE |
| G9 | Permits & Approvals | 0.80 | PRODUCER, REGULATOR |
| G10 | Financial Close | 0.95 | FINANCE |
| G11 | Commercial Operations Date | 0.85 | PRODUCER, EXECUTIVE |

---

## Verification-Weighted Scores (R2)

Raw evidence scores are multiplied by verification weights before gate evaluation. This prevents unverified self-reported data from unlocking capital or advancing state.

### Weights

| Verification State | Weight |
| --- | --- |
| UNVERIFIED | 0.25 |
| SUBMITTED | 0.50 |
| CONFIRMED | 0.85 |
| AUDITED | 1.00 |

### Formula

```text
effective_score = raw_score × mean(verification_weights_for_gate_evidence)
```

The state machine evaluates **effective scores**, not raw scores. A gate with raw score 1.0 but all evidence UNVERIFIED yields effective score 0.25 — below every gate threshold.

---

## Persona Views

Each persona sees only the gates relevant to their role:

| Persona | Gates |
| --- | --- |
| PRODUCER | G0, G1, G3, G5, G9, G11 |
| FINANCE | G4, G6, G7, G8, G10 |
| REGULATOR | G2, G6, G9 |
| EXECUTIVE | G0, G5, G11 + portfolio summary |

The `/evaluate/persona` endpoint filters gate_evaluations and capital_unlocks to the requesting persona.

---

## Capital Unlocks

Each state transition releases specific capital tranches:

| State Reached | Capital Event |
| --- | --- |
| TECHNICALLY_PLAUSIBLE | Pre-development equity eligible |
| COMMERCIALLY_PLAUSIBLE | Offtake negotiation funding |
| BUILDABLE | Development capital, EPC tender |
| STRUCTURALLY_BANKABLE | Senior debt term sheet eligible |
| CREDIT_APPROVED | Credit committee mandate |
| FINANCEABLE | Financial close, drawdown |
| OPERATIONAL | Operational working capital |
| REFINANCING_ELIGIBLE | Refi / green bond issuance |

---

## Deal-Killer System (R1)

Eight pre-seeded blockers that halt capital deployment regardless of gate scores:

| ID | Severity | Trigger |
| --- | --- | --- |
| DK-001 | FATAL | No site control documented |
| DK-002 | FATAL | Offtake counterparty < investment grade |
| DK-003 | FATAL | IE report withheld or not commissioned |
| DK-004 | FATAL | Insurance gap > 10% of capex |
| DK-005 | CRITICAL | DSCR < 1.20 in any model year |
| DK-006 | CRITICAL | Green certification pathway unresolved |
| DK-007 | CRITICAL | EPC contractor not appointed |
| DK-008 | CRITICAL | Permits outstanding at financial close |

FATAL blockers prevent all capital unlocks. CRITICAL blockers block the specific gate they are tied to.

---

## Module Responsibilities

```text
app/
├── main.py                    Entry point — FastAPI app, CORS, router mounts
├── api/
│   ├── routes_bankability.py  POST /evaluate, POST /evaluate/persona,
│   │                          GET /gates, GET /rules, GET /health
│   └── routes_model.py        POST /cfads/calculate, POST /model/lifetime,
│                              POST /covenants/check, POST /waterfall/execute,
│                              POST /metrics/calculate, GET /health
└── core/
    ├── bankability_engine.py  State machine, gate evaluation, capital unlocks
    ├── cfads.py               Cash Flow Available for Debt Service calculator
    ├── waterfall.py           Senior / junior / mezzanine priority distribution
    ├── audit.py               SHA-256 chained event log (append-only)
    ├── verification.py        Verification state enum and weight lookup
    └── debt/
        ├── sculpting.py       DSCR-sculpted repayment schedule generator
        └── tranche.py         Debt tranche objects (senior, junior, mezz)
```

---

## Audit Trail

Every state transition and gate evaluation is appended to an in-memory (or persisted) event chain:

```text
event_n.hash = SHA-256(event_n-1.hash + event_n.payload)
```

This makes retrospective tampering detectable: any change to a historical event invalidates all subsequent hashes.

The `GET /api/v1/bankability/audit/{project_id}` endpoint returns the full chain with verification status for each link.

---

## Financial Model

### CFADS Calculator (`cfads.py`)

Inputs: revenue assumptions, opex, capex schedule, tax, working capital movements.
Output: period-by-period cash flow available for debt service.

### Waterfall Engine (`waterfall.py`)

Distributes CFADS according to priority:

```text
1. Senior debt service (interest + scheduled principal)
2. Debt service reserve account top-up
3. Junior / mezzanine debt service
4. Equity distributions (if DSCR ≥ lock-up threshold)
```

### Debt Sculpting (`debt/sculpting.py`)

Generates a repayment schedule where each period's principal is sized so that DSCR equals the target ratio (typically 1.30), rather than using flat amortisation.

### Covenant Check (`routes_model.py → covenants/check`)

Evaluates DSCR and LLCR against thresholds:

| Covenant | Default Threshold |
| --- | --- |
| DSCR (annual) | ≥ 1.20 (lock-up), ≥ 1.10 (default trigger) |
| LLCR | ≥ 1.30 |

---

## Key Design Decisions

- **No external database** — state is passed in request bodies; persistence is the caller's responsibility (platform backend owns the evidence store).
- **Stateless per request** — each `/evaluate` call receives full evidence array and returns full evaluation; no session state held between calls.
- **SQLite-free** — this service has no database of its own; it is a pure computation engine.
- **Port isolation** — always on 8001, never exposed to the browser directly; all calls are proxied through the platform backend on 8000.
