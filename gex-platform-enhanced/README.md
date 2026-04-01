# GreenEarthX Platform — v6.1

Production-grade orchestration platform for green fuels (H₂, NH₃, SAF, e-MeOH) — covering production, commercial, finance, compliance, and operations. Architecture as of **March 2026**.

Strategic direction: see [docs/OBJECTIVE_LED_PRODUCT_PATHWAY.md](docs/OBJECTIVE_LED_PRODUCT_PATHWAY.md) for the short objective-led product pathway and [docs/MOLECULE_TO_ASSET_KILLER_PROMPT.md](docs/MOLECULE_TO_ASSET_KILLER_PROMPT.md) for the investor-side molecule-to-asset thesis and reusable prompt.

---

## Architecture

```text
Browser (port 3000)
  │
  ▼
Frontend  Vite + React 18 + TypeScript + Tailwind CSS
  │  /api/* proxied to 8000
  ▼
Platform Backend  FastAPI + SQLite                port 8000
  │
  ▼
Finance Engine  gex_pf_engine (microservice)      port 8001
```

---

## Navigation Model (v6.1 — Top-Bar Dropdowns)

Five role-filtered top-bar dropdown menus replace the old workspace sidebar:

| Tab | Who sees it | Key items |
| --- | --- | --- |
| **Projects** | All | Task Flow, Status & Blockers, Plant Builder, Telemetry |
| **Commercial** | Producer/Offtaker/Bank | Market Discovery, Supply Offers, Demand Pipeline, Contracts |
| **Finance** | Producer FT / Bank / Insurer | Bankability Status, Capital Stack, IC Pack, Deal Room |
| **Compliance** | All | Cert Readiness, Evidence Hierarchy, Audit Trail |
| **Operations** | All | Project Timeline, Plant Telemetry, Performance Matrix |

A password-gated **CISO** gear (⚙) exposes security admin (Information Barriers, OT Gateways, Data Residency, Access Monitor).

User role is selected on first visit (`/onboarding`) and persisted to `localStorage`. Items are filtered per `company_type × business_function × service_type`.

---

## Quick Start

### Prerequisites

- Node 20+
- Python 3.11+

### 1. Finance Engine (port 8001)

```bash
cd ../gex_pf_engine/backend
source ../micro_service/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Platform Backend (port 8000)

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend (port 3000)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` — set your role on first visit.
API docs: `http://localhost:8000/docs`

---

## Architectural Reforms (v6.0 → v6.1)

### v6.0 — Architectural Reform (R0–R10)

| Ref | Reform | Key file |
| --- | --- | --- |
| R0  | Verification State Engine (UNVERIFIED / SUBMITTED / CONFIRMED / AUDITED) | `backend/app/core/verification.py` |
| R1  | Deal-Killer System (8 pre-seeded fatal/critical blockers) | `backend/app/core/deal_killers.py` |
| R2  | Verification-weighted gate scores (effective = raw × mean weight) | `backend/app/core/bankability_engine.py` |
| R3  | Named Reviewer Gate (REVIEWED/EXPORTED require named human) | `backend/app/core/workflow.py` |
| R4  | Provenance Banner on exports | `backend/app/core/provenance.py` |
| R5  | Score Subordination (arc gauge → collapsible Advanced panel) | `frontend/src/features/finance/BankabilityScorePage.tsx` |
| R6  | Task Router (decision-question entry per actor type) | `frontend/src/components/TaskRouter.tsx` |
| R7  | Finance Dashboard landing replaced by Task Router | `frontend/src/features/finance/FinanceDashboardPage.tsx` |
| R8  | 4-Column Supply Table (DELIVERY/CERT/LOGISTICS/COMMITMENT) | `frontend/src/features/trader/OfftakerSupplyTable.tsx` |
| R9  | Evidence Hierarchy (per-gate AUDITED/CONFIRMED/SUBMITTED/UNVERIFIED) | `frontend/src/features/finance/EvidenceHierarchy.tsx` |
| R10 | IC Pack Export Gate (5-condition hard gate) | `backend/app/api/v1/routes_deal_killers.py` |

### v6.1 — Menu Architecture Reform

- Replaced 6-workspace sidebar with 5 top-bar role-filtered dropdown menus
- `UserRoleContext` (localStorage-persisted) drives all item visibility
- `menuArchitecture.ts` is single source of truth for nav items + visibility rules
- CISO workspace password-gated (`Enter-123` default, overridable via `gex_ciso_password` localStorage key)
- Onboarding wizard shows RoleSelector on first visit

---

## Backend API

| Prefix | Module | Description |
| --- | --- | --- |
| `/api/v1/capacities` | `capacity_sqlite.py` | Production capacity |
| `/api/v1/tokens` | `tokens_sqlite.py` | Token minting & allocation |
| `/api/v1/marketplace` | `marketplace_sqlite.py` | Offer discovery |
| `/api/v1/matching` | `matching_sqlite.py` | Buyer/seller matching |
| `/api/v1/contracts` | `contracts_sqlite.py` | Contract lifecycle |
| `/api/v1/trader/rfqs` | `trader_rfqs.py` | RFQ management |
| `/api/v1/finance` | `endpoints/finance.py` | Finance & risk |
| `/api/v1/bankability` | `routes_bankability_proxy.py` | Proxy → gex_pf_engine |
| `/api/v1/finance-model` | `routes_finance_model.py` | Proxy → gex_pf_engine |
| `/api/v1/verification` | `routes_verification.py` | R0 verification state engine |
| `/api/v1/deal-killers` | `routes_deal_killers.py` | R1 deal-killer system |
| `/api/v1/task-flow` | `routes_task_router.py` | R6 task router flows |
| `/api/v1/approvals` | `routes_approvals.py` | WAE workflow |
| `/api/v1/commitments` | `routes_commitments.py` | CSS commitment signing |
| `/api/v1/ic-pack` | `routes_ic_pack.py` | IC pack assembly |
| `/api/v1/data-room` | `routes_data_room.py` | Virtual data room |
| `/api/v1/ciso` | `routes_ciso.py` | CISO security & compliance |
| `/api/v1/audit` | `audit.py` | Audit trails |

---

## Frontend Structure

```text
frontend/src/
├── main.tsx                       # Entry — wraps in UserRoleProvider
├── App.tsx                        # Router + all route definitions
├── config/
│   └── menuArchitecture.ts        # Navigation tabs, items, visibility rules
├── contexts/
│   ├── UserRoleContext.tsx         # Role state (company/function/service)
│   └── ProjectContext.tsx          # Selected project state
├── components/
│   ├── TopBar.tsx                  # 5 top-bar tabs + CISO gear
│   ├── TopBarDropdown.tsx          # Role-filtered dropdown (React Router)
│   ├── CISOGate.tsx                # Password modal
│   ├── Layout.tsx                  # TopBar + full-width Outlet
│   ├── RoleSelector.tsx            # Company/function/service picker
│   ├── TaskRouter.tsx              # R6 decision-question flows
│   ├── DealKillerBanner.tsx        # R1 non-dismissable fatal/critical banner
│   ├── VerificationBadge.tsx       # R0 state badge (UNVERIFIED→AUDITED)
│   └── ProvenanceBanner.tsx        # R4 export provenance header
└── features/
    ├── finance/                    # 25+ pages: BankabilityScorePage,
    │                               #   EvidenceHierarchy, ICPackBuilder,
    │                               #   BankersSnapshot, DSCRHeatmap, …
    ├── trader/                     # OfftakerSupplyTable, TraderDashboard
    ├── ciso/                       # CISODashboard, ABACManagement,
    │                               #   BarrierManagement, GatewayStatus, …
    ├── executive/                  # ExecutiveBankabilityDashboard, CFOReport
    ├── producer/                   # ProducerBankabilityView, PlantDataDashboard
    ├── regulator/                  # RegulatorDashboardPage
    └── onboarding/                 # OnboardingWizard (RoleSelector step 0)
```

---

## Reference Documents (`_docs/`)

| File | Description |
| --- | --- |
| `ANALYSIS.pages` | Platform analysis document |
| `GEX-DATABASE_CONFIGURATION.pages` | Database schema design |
| `Last Prompts March2.pages` | Agent prompt library |
| `finance engine.pages` | Finance engine specification |
| `bankability_schema.sql` | Bankability evidence schema |
| `DATABASE_CONFIGURATION.pdf` | DB configuration reference |

---

## License

Proprietary — GreenEarthX
