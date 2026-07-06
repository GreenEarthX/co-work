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
| Bankability Engine | `app/core/bankability_engine.py` | 12-gate state machine, SHA-256 event chain |
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

**Gates (G0–G11):**

| Gate | Name | Owners |
| --- | --- | --- |
| G0 | Site Rights & Social License | PRODUCER, EXECUTIVE |
| G1 | Grid Connection & Water/Utilities | PRODUCER |
| G2 | Green Certification Pathway | REGULATOR |
| G3 | Feedstock & Logistics | PRODUCER |
| G4 | Binding Offtake | FINANCE |
| G5 | EPC & Construction | PRODUCER, EXECUTIVE |
| G6 | Independent Engineer Signoff | FINANCE, REGULATOR |
| G7 | Insurance Package | FINANCE |
| G8 | Audit-Grade Financial Model | FINANCE |
| G9 | Permits & Approvals | PRODUCER, REGULATOR |
| G10 | Financial Close | FINANCE |
| G11 | Commercial Operations Date | PRODUCER, EXECUTIVE |

**Persona views:**

| Persona | Gates |
| --- | --- |
| PRODUCER | G0, G1, G3, G5, G9, G11 |
| FINANCE | G4, G6, G7, G8, G10 |
| REGULATOR | G2, G6, G9 |
| EXECUTIVE | G0, G5, G11 + portfolio summary |

**Current completion logic (2026-04-05):** the engine returns `overall_completion_pct` and gate completion based on verified evidence coverage. Verification-weighted effective scoring remains the intended R2 consolidation model, but it is not yet the only implementation path across the codebase.

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
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
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
