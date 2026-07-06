# GEX Platform — Dependency Map & Architecture Graph

> Generated 2026-04-03 | Covers `gex-platform-enhanced` + `gex_pf_engine`

---

## 1. SERVICE TOPOLOGY (AS-IS)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BROWSER (port 3000)                         │
│  Vite + React 18 + TypeScript + Tailwind                           │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │UserRole  │  │Project   │  │Visible   │  │Auth      │           │
│  │Context   │  │Context   │  │Projects  │  │Session   │           │
│  │(local    │  │(local    │  │(ABAC     │  │(JWT in   │           │
│  │ Storage) │  │ Storage) │  │ filter)  │  │ lStorage)│           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                 │
│       └──────────────┴──────────────┴──────────────┘                │
│                          │                                          │
│              fetch() + x-demo-* headers                             │
│              Authorization: Bearer {JWT}                            │
└──────────────┬──────────────────────────────────────────────────────┘
               │  /api/v1/*
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    MAIN BACKEND (port 8000)                          │
│  FastAPI + SQLite/PostgreSQL                                        │
│                                                                      │
│  Middleware Stack:                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐              │
│  │ CORS        │→ │ GZip         │→ │ ABAC           │              │
│  │ (origins)   │  │ (>1KB)       │  │ Middleware      │              │
│  └─────────────┘  └──────────────┘  │ R0-R9 rules    │              │
│                                      │ 165 perms ×    │              │
│                                      │ 30 profiles    │              │
│                                      └────────────────┘              │
│                                                                      │
│  40 route modules  ──→  34 core modules  ──→  SQLite/PostgreSQL     │
│                                                                      │
│  ┌──────────────────────────────────────┐                            │
│  │ PROXY BRIDGE (httpx)                 │                            │
│  │  routes_finance_model.py      ──┐    │                            │
│  │  routes_bankability_proxy.py  ──┤    │                            │
│  │  bankability_client.py        ──┤    │                            │
│  │  onboarding.py                ──┘    │                            │
│  └──────────────┬───────────────────────┘                            │
└─────────────────┼────────────────────────────────────────────────────┘
                  │  http://localhost:8001/api/v1/*
                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  FINANCE ENGINE (port 8001)                           │
│  FastAPI — isolated, no browser exposure                             │
│                                                                      │
│  4 route modules:                                                    │
│    routes_model.py        CFADS, waterfall, covenants, lifetime      │
│    routes_bankability.py  Gate scoring, verification weighting        │
│    routes_pricing.py      Gabillon two-factor model                  │
│    routes_bankability_abac.py  ABAC-scoped gate visibility           │
│                                                                      │
│  11 core modules:                                                    │
│    engine.py, cfads.py, waterfall.py, gabillon.py,                   │
│    debt/tranche.py, debt/sculpting.py, timebase.py,                  │
│    bankability_engine.py, greenmesh.py, audit.py                     │
└──────────────────────────────────────────────────────────────────────┘
```

**Key observation:** Communication is strictly one-directional:
`Browser → 8000 → 8001`. Finance engine never calls back.

---

## 2. FRONTEND MODULE DEPENDENCY GRAPH

```
                    ┌─────────────────────┐
                    │  menuArchitecture.ts │  ← Single source of truth
                    │  (5 tabs + CISO)     │     for navigation visibility
                    └──────────┬──────────┘
                               │ filters by
                    ┌──────────▼──────────┐
                    │   UserRoleContext    │  ← company_type × business_function
                    │   (3 dimensions)     │     × service_type
                    └──┬───────┬───────┬──┘
                       │       │       │
          ┌────────────┘       │       └────────────┐
          ▼                    ▼                     ▼
  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐
  │ useVisible    │  │ ProjectContext  │  │ authSession      │
  │ Projects()    │  │ (selected      │  │ (JWT token)      │
  │ ABAC filter   │  │  project ID)   │  │                  │
  └───────┬───────┘  └───────┬────────┘  └────────┬─────────┘
          │                  │                     │
          └──────────────────┼─────────────────────┘
                             │ consumed by ALL pages
                             ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     91 ROUTE COMPONENTS                     │
  │                                                             │
  │  PROJECTS tab (9 screens)                                   │
  │  COMMERCIAL tab (11 screens)                                │
  │  FINANCE tab (22 screens)                                   │
  │  COMPLIANCE tab (8 screens)                                 │
  │  OPERATIONS tab (7 screens)                                 │
  │  CISO ADMIN (12 screens)                                    │
  │  AUTH (login, onboarding, account)                          │
  └─────────────────────────────────────────────────────────────┘
```

---

## 3. SCREEN PATH DEPENDENCIES — GATED TIMELINE

This is the critical graph. It shows how screens depend on each other
through bankability gates, and the natural timeline progression.

```
TIMELINE ──────────────────────────────────────────────────────────────►
          ADVISORY              BUILD             FIN CLOSE    OPS

 ┌─────────────────────── PHASE 1: ADVISORY ───────────────────────┐
 │                                                                  │
 │  /onboarding ─────► /projects ─────► /dashboard                 │
 │  (intake)           (registry)       (portfolio overview)        │
 │       │                                    │                     │
 │       ▼                                    ▼                     │
 │  /finance-plant-builder            /bankability-scores           │
 │  (CAPEX/OPEX config)              (G0-G11 status board)         │
 │       │                                    │                     │
 │       │              ┌─────────────────────┼──────────────┐      │
 │       │              │                     │              │      │
 │       ▼              ▼                     ▼              ▼      │
 │   G0: SITE      G1: GRID           G9: PERMITS     G3: FEEDSTOCK│
 │   RIGHTS        CONNECTION          REGULATORY      LOGISTICS   │
 │       │              │                     │              │      │
 │       └──────────────┴─────────────────────┴──────────────┘      │
 │                              │                                   │
 │              /stage-gates (evidence upload per gate)              │
 │              /producer-bankability (producer evidence view)       │
 │              /reports (document upload)                           │
 └──────────────────────────────────────────────────────────────────┘
                                │
                    gates G0,G1,G3,G9 ≥ 60%
                                │
 ┌────────────────────── PHASE 2: COMMERCIAL ──────────────────────┐
 │                                                                  │
 │  /marketplace ──────► /offtaker-supply ──────► /matching         │
 │  (overview)           (feedstock offers)        (matching engine) │
 │       │                      │                       │           │
 │       ▼                      ▼                       ▼           │
 │  /finance-demand      /offtake-quality        /trader-dashboard  │
 │  (demand pipeline)    (5 bankability tests)   (RFQ management)   │
 │       │                      │                       │           │
 │       │                      │                       │           │
 │       └──────────────────────┴───────────────────────┘           │
 │                              │                                   │
 │                     G4: BINDING OFFTAKE                          │
 │                     (coverage ≥ 70%)                             │
 │                              │                                   │
 │                              ▼                                   │
 │                      /term-sheet                                 │
 │                      (term sheet tracker)                        │
 │                              │                                   │
 │                              ▼                                   │
 │                      /contracts                                  │
 │                      (contract execution)                        │
 │                              │                                   │
 │                     G4 completion → unlocks G5, G6, G7           │
 └──────────────────────────────────────────────────────────────────┘
                                │
 ┌────────────────────── PHASE 3: STRUCTURING ─────────────────────┐
 │                                                                  │
 │  G5: EPC          G6: IE             G7: INSURANCE               │
 │  CONTRACT         SIGNOFF            PROGRAMME                   │
 │       │              │                     │                     │
 │       ▼              ▼                     ▼                     │
 │  /capital-stack   /evidence-hierarchy  /insurance-schedule       │
 │  /finance-gaps    /stage-gates         /insurance-coverage       │
 │  /finance-package                      /insurance-assets         │
 │  /finance-risk-matrix                                            │
 │  /finance-instruments                                            │
 │                                                                  │
 │       └──────────────┴─────────────────────┘                     │
 │                              │                                   │
 │                     G8: MODEL AUDIT                              │
 │                     (independent model review)                   │
 │                              │                                   │
 │                              ▼                                   │
 │                      /dscr-sensitivity                           │
 │                      /covenants                                  │
 │                      /cfo-report                                 │
 │                      /bankability-snapshot                       │
 └──────────────────────────────────────────────────────────────────┘
                                │
 ┌────────────────────── PHASE 4: FINANCIAL CLOSE ─────────────────┐
 │                                                                  │
 │  G10: FINANCIAL CLOSE READINESS                                  │
 │  (all prior gates ≥ 80%)                                        │
 │       │                                                          │
 │       ▼                                                          │
 │  /ic-pack ──────► /approval-queue ──────► /commitment-signing    │
 │  (IC package)     (WAE approval)          (digital signatures)   │
 │                                                  │               │
 │                                                  ▼               │
 │                                          /commitment-verifier    │
 │                                          (verify + countersign)  │
 │                                                  │               │
 │                                          /data-room              │
 │                                          (investor data room)    │
 │                                                  │               │
 │                              G11: COD (Certificate of Deposit)   │
 └──────────────────────────────────────────────────────────────────┘
                                │
 ┌────────────────────── PHASE 5: OPERATIONS ──────────────────────┐
 │                                                                  │
 │  /production ──────► /plant-data ──────► /capacity               │
 │  (batch tracking)    (OT telemetry)      (GreenMesh)             │
 │                                                                  │
 │  /finance-timeline (milestones & drawdown)                       │
 │  /transfer-readiness (asset transfer)                            │
 └──────────────────────────────────────────────────────────────────┘
```

---

## 4. CROSS-CUTTING DEPENDENCIES (THE SAP PROBLEM)

These modules are referenced by nearly every screen — changing them
has blast radius across the entire platform:

```
                   ┌─────────────────────────┐
                   │  CUSTOMER_PROJECTS      │ ← 19 files import directly
                   │  (customerProjects.ts)  │    THE canonical data registry
                   └────────────┬────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           │                    │                     │
           ▼                    ▼                     ▼
  useVisibleProjects    useSelectedProject      getProjectById
  (ABAC filter)        (ProjectContext)         (direct lookup)
  ── 5 pages use ──    ── 15+ pages use ──     ── 10+ pages use ──

  ┌─────────────────────────────────────────────────────────────┐
  │  OTHER CROSS-CUTTING CONCERNS:                              │
  │                                                             │
  │  ProductionRoadmapGantt  → 5 pages (Dashboard, Finance,    │
  │                             Executive, Timeline, Structure) │
  │  DealKillerBanner        → global (all bankability pages)   │
  │  DecisionFirstEntry      → Dashboard                        │
  │  MoleculeGatingAlert     → finance + compliance pages       │
  │  InfoTooltip             → 12+ pages                        │
  │  WorkflowBadge           → finance + commercial pages       │
  └─────────────────────────────────────────────────────────────┘
```

### Backend Cross-Cutting:

```
  ┌──────────────────────────────────────────────────────┐
  │  HIGH COUPLING MODULES (change = ripple everywhere)  │
  │                                                      │
  │  auth.py            → every authenticated endpoint   │
  │  abac.py            → every protected resource       │
  │  abac_middleware.py  → every HTTP request             │
  │  project_truth.py   → deal_killers, task_router,     │
  │                       activity, verification         │
  │  verification.py    → stage_gates, bankability,      │
  │                       evidence, certification        │
  │  event_store.py     → audit trail everywhere         │
  │  config.py          → JWT secret, DB URL, flags      │
  │                                                      │
  │  MODERATE COUPLING:                                  │
  │  deal_killers.py    → bankability, task_router       │
  │  workflow.py        → approvals, commitments, IC     │
  │  permission_engine  → ABAC middleware, CISO admin    │
  │  bankability_engine → proxy to port 8001             │
  └──────────────────────────────────────────────────────┘
```

---

## 5. AS-IS vs TO-BE ARCHITECTURE

### AS-IS: Current State (the SAP trauma pattern)

```
┌──────────────────────────────────────────────────────────────┐
│                         AS-IS                                │
│                                                              │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐             │
│  │ Frontend │────►│ Backend  │────►│ Finance  │             │
│  │ port 3000│     │ port 8000│     │ port 8001│             │
│  └──────────┘     └──────────┘     └──────────┘             │
│                                                              │
│  PROBLEMS:                                                   │
│                                                              │
│  1. MONOLITH RISK                                            │
│     40 route files + 34 core modules in one FastAPI app      │
│     One bad deploy breaks everything                         │
│                                                              │
│  2. DATA COUPLING                                            │
│     CUSTOMER_PROJECTS imported raw by 19 frontend files      │
│     No central data service — each page DIYs its own filter  │
│     ┌──────┐ ┌──────┐ ┌──────┐                              │
│     │Page A│ │Page B│ │Page C│  each imports                 │
│     │ CP[] │ │ CP[] │ │ CP[] │  CUSTOMER_PROJECTS            │
│     └──┬───┘ └──┬───┘ └──┬───┘  and filters differently     │
│        │        │        │                                   │
│        ▼        ▼        ▼                                   │
│     CUSTOMER_PROJECTS (static array, no API)                 │
│                                                              │
│  3. AUTH GAP                                                 │
│     JWT is HS256 (symmetric key)                             │
│     No refresh tokens — 30min hard expiry                    │
│     x-demo-* headers = role impersonation in dev             │
│     No OIDC provider — can't federate with Tier-1 partners   │
│                                                              │
│  4. GATE COUPLING                                            │
│     Gate IDs hardcoded in 8+ frontend files                  │
│     No gate registry API — frontend assumes gate names       │
│     Gate → screen mapping is implicit (no config)            │
│                                                              │
│  5. SCREEN ISOLATION                                         │
│     Screens don't know their gate prerequisites              │
│     No workflow enforcement — user can jump to any URL       │
│     Timeline phases exist only in the Gantt component        │
│                                                              │
│  6. NO EVENT-DRIVEN UI                                       │
│     Backend has event_bus + event_store                       │
│     Frontend never subscribes — no real-time updates         │
│     User must manually refresh to see state changes          │
└──────────────────────────────────────────────────────────────┘
```

### TO-BE: Target Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         TO-BE                                │
│                                                              │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐             │
│  │ Frontend │◄═══►│ API GW   │────►│ Services │             │
│  │ SPA      │ SSE │ + Auth   │     │ (bounded │             │
│  │          │     │ (OIDC)   │     │ contexts)│             │
│  └──────────┘     └──────────┘     └──────────┘             │
│                                                              │
│  CHANGES REQUIRED:                                           │
│                                                              │
│  1. PROJECT DATA SERVICE                                     │
│     Replace raw CUSTOMER_PROJECTS imports with               │
│     a single useProjectStore() (Zustand or React Query)      │
│                                                              │
│     ┌──────┐ ┌──────┐ ┌──────┐                              │
│     │Page A│ │Page B│ │Page C│  all consume                  │
│     └──┬───┘ └──┬───┘ └──┬───┘                              │
│        │        │        │                                   │
│        └────────┼────────┘                                   │
│                 ▼                                             │
│     ┌───────────────────────┐                                │
│     │  useProjectStore()    │ ← single data layer            │
│     │  - fetches from API   │    with ABAC built in          │
│     │  - caches via RQ      │    invalidates on events       │
│     │  - ABAC pre-filtered  │                                │
│     └───────────────────────┘                                │
│                                                              │
│  2. OIDC + RS256 JWT                                         │
│     ┌──────────────────────────────────────┐                 │
│     │  OIDC Provider (Keycloak / Auth0)    │                 │
│     │  - RS256 asymmetric signing          │                 │
│     │  - Refresh token rotation            │                 │
│     │  - MFA enforcement                   │                 │
│     │  - Federation for partner SSO        │                 │
│     │  - Token claims carry ABAC attrs     │                 │
│     └──────────────────────────────────────┘                 │
│     Backend validates with public key (no shared secret)     │
│     Finance engine validates same JWT (no proxy needed)      │
│                                                              │
│  3. GATE REGISTRY + WORKFLOW ENGINE                          │
│     ┌──────────────────────────────────────┐                 │
│     │  GET /api/v1/gates/registry          │                 │
│     │  → { gateId, prerequisites, phase,   │                 │
│     │      linked_screens[], min_completion │                 │
│     │      for_next_phase }                │                 │
│     └──────────────────────────────────────┘                 │
│     Frontend reads gate→screen mapping from API              │
│     Screens show "locked" state when prerequisite            │
│     gates are below threshold                                │
│                                                              │
│  4. EVENT-DRIVEN UI (SSE)                                    │
│     Backend event_bus ──► SSE endpoint                        │
│     Frontend subscribes: gate changes, approvals,            │
│     commitment signatures → live badges + toasts             │
│                                                              │
│  5. BOUNDED CONTEXT SEPARATION (backend)                     │
│     ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│     │ AUTH       │  │ PROJECT    │  │ COMMERCIAL  │          │
│     │ context    │  │ context    │  │ context     │          │
│     │ auth.py    │  │ truth.py   │  │ matching    │          │
│     │ abac.py    │  │ verify.py  │  │ contracts   │          │
│     │ perms.py   │  │ gates.py   │  │ marketplace │          │
│     └────────────┘  └────────────┘  └────────────┘          │
│     ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│     │ FINANCE    │  │ COMPLIANCE │  │ OPS        │          │
│     │ context    │  │ context    │  │ context    │          │
│     │ model.py   │  │ cert.py    │  │ plant.py   │          │
│     │ capital.py │  │ audit.py   │  │ greenmesh  │          │
│     │ structuring│  │ regulatory │  │ telemetry  │          │
│     └────────────┘  └────────────┘  └────────────┘          │
│     Each context owns its routes, models, and events         │
│     Inter-context communication via event_bus only           │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. WHAT NEEDS TO BE MODIFIED (RECURSIVE REASONING)

### Layer 0: Foundation (must change first — everything depends on it)

| # | Module | Change | Blast Radius | Why |
|---|--------|--------|-------------|-----|
| 0a | `backend/core/auth.py` | HS256 → RS256, add refresh tokens, OIDC discovery | ALL endpoints | Every API call validates JWT |
| 0b | `backend/core/config.py` | Add OIDC issuer URL, JWKS URI, RS256 public key | ALL services | Config feeds auth + middleware |
| 0c | `frontend/contexts/UserRoleContext.tsx` | Store refresh token, add silent renewal, map OIDC claims to role | ALL pages | Every page reads role from here |

### Layer 1: Data Access (depends on Layer 0)

| # | Module | Change | Blast Radius | Why |
|---|--------|--------|-------------|-----|
| 1a | `frontend/data/customerProjects.ts` | Deprecate static import, replace with API fetch | 19 files | Static data = no server-side ABAC |
| 1b | `frontend/hooks/useVisibleProjects.ts` | Fetch from `/api/v1/projects/visible` instead of client-side filter | 5 pages directly, all pages indirectly | Client-side ABAC is advisory, not enforced |
| 1c | `backend/core/project_truth.py` | Add `GET /projects/visible` endpoint with RLS | New endpoint | Server must be authoritative |
| 1d | `frontend/contexts/ProjectContext.tsx` | Validate selectedProject against visible set from server | 15+ pages | Prevents unauthorized project access |

### Layer 2: Gate & Workflow (depends on Layer 1)

| # | Module | Change | Blast Radius | Why |
|---|--------|--------|-------------|-----|
| 2a | `backend/core/verification.py` | Expose gate registry API with prerequisites | StageGates, Bankability, Gantt | Gates are hardcoded in frontend |
| 2b | `frontend/components/gantt/ProductionRoadmapGantt.tsx` | Fetch gate registry, make bars clickable to linked screens | Dashboard, Finance, Executive, Timeline | Gantt is display-only today |
| 2c | `frontend/config/menuArchitecture.ts` | Add `gate_prerequisite` field per menu item | All nav items | Screens don't know their gate deps |
| 2d | Create `frontend/hooks/useGateAccess.ts` | Hook that checks if user can access a screen based on gate progress | All gated screens | No workflow enforcement today |

### Layer 3: Screen-Level (depends on Layer 2)

| # | Module | Change | Files Affected | Why |
|---|--------|--------|---------------|-----|
| 3a | 19 files importing CUSTOMER_PROJECTS | Replace with `useProjectStore()` or `useVisibleProjects()` | 19 frontend files | Eliminate raw static imports |
| 3b | Pages with navigate() calls | Add gate-check before navigation | ~12 pages | Prevent jumping to locked screens |
| 3c | DealKillerBanner | Read killers from API instead of hardcoded | Global | Killers are seeded but static |
| 3d | All finance pages | Add "locked" empty state when gates below threshold | ~15 finance pages | User sees "complete G4 first" |

### Layer 4: Real-Time (depends on Layer 3)

| # | Module | Change | Why |
|---|--------|--------|-----|
| 4a | `backend/core/event_bus.py` | Add SSE endpoint `/api/v1/events/stream` | Enable push updates |
| 4b | Create `frontend/hooks/useEventStream.ts` | SSE subscription hook | Live gate/approval/commitment updates |
| 4c | Dashboard, BankabilityScores, ApprovalQueue | Subscribe to relevant event streams | Remove manual refresh pattern |

---

## 7. MODIFICATION PRIORITY (AGILE SPRINTS)

```
SPRINT 1 (Foundation)          SPRINT 2 (Data)             SPRINT 3 (Workflow)
━━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━             ━━━━━━━━━━━━━━━━━━
 0a. RS256 JWT                  1a. Projects API            2a. Gate registry API
 0b. Config + OIDC              1b. Server-side ABAC        2b. Clickable Gantt
 0c. Refresh tokens             1c. /projects/visible       2c. Menu gate prereqs
                                1d. ProjectContext fix       2d. useGateAccess hook

SPRINT 4 (Screens)             SPRINT 5 (Real-time)
━━━━━━━━━━━━━━━━━━             ━━━━━━━━━━━━━━━━━━━
 3a. Kill raw CP imports        4a. SSE endpoint
 3b. Gate-check navigation      4b. useEventStream
 3c. Dynamic deal killers       4c. Live dashboard
 3d. Locked-screen states
```

---

## 8. FILES REQUIRING MODIFICATION (COMPLETE LIST)

### Frontend (by priority)

**P0 — Auth Foundation:**
- `src/contexts/UserRoleContext.tsx` — OIDC token management
- `src/features/auth/LoginPage.tsx` — OIDC redirect flow
- `src/features/auth/AccountPage.tsx` — session display
- `src/main.tsx` — remove x-demo-* header injection
- `src/App.tsx` — add silent token renewal wrapper

**P1 — Data Layer:**
- `src/hooks/useVisibleProjects.ts` — server-side fetch
- `src/contexts/ProjectContext.tsx` — server validation
- `src/data/customerProjects.ts` — deprecate direct usage

**P2 — 19 files importing CUSTOMER_PROJECTS directly:**
```
src/features/marketplace/MarketplacePage.tsx      ✅ already fixed
src/features/trader/OfftakerSupplyTable.tsx       ✅ already fixed
src/features/finance/DemandPipeline.tsx           ✅ already fixed
src/features/capacity/CapacityPage.tsx            ✅ already fixed
src/features/finance/OfftakeQuality.tsx           ✅ already fixed
src/features/dashboard/DashboardPage.tsx          ✅ already uses hook
src/features/trader/TraderDashboardPage.tsx       ⚠️  needs fix
src/features/finance/BankabilityScorePage.tsx     ⚠️  needs fix
src/features/finance/CapitalStack.tsx             ⚠️  needs fix
src/features/finance/BankersSnapshot.tsx          ⚠️  needs fix
src/features/finance/CertReadiness.tsx            ⚠️  needs fix
src/features/finance/CovenantsPage.tsx            ⚠️  needs fix
src/features/finance/TransferReadiness.tsx        ⚠️  needs fix
src/features/finance/TermSheetTracker.tsx         ⚠️  needs fix
src/features/finance/InsuranceSchedule.tsx        ⚠️  needs fix
src/features/finance/DataRoom.tsx                 ⚠️  needs fix
src/features/finance/ICPackBuilder.tsx            ⚠️  needs fix
src/features/production/ProductionPage.tsx        ⚠️  needs fix
src/features/reviews/AdversarialReviewPage.tsx    ⚠️  needs fix
src/features/executive/CFOReport.tsx              ⚠️  needs fix
src/features/insurance/InsuranceAssetRegister.tsx  ⚠️  needs fix
src/features/insurance/InsuranceCoverageBuilder.tsx ⚠️  needs fix
src/components/gantt/ProductionRoadmapGantt.tsx   ⚠️  needs fix
src/features/finance/ProjectTimeline.tsx          ⚠️  needs fix
```

### Backend (by priority)

**P0 — Auth:**
- `app/core/auth.py` — RS256, refresh tokens, OIDC
- `app/core/config.py` — OIDC settings
- `app/api/v1/routes_auth.py` — token refresh endpoint

**P1 — Data:**
- `app/core/project_truth.py` — visible projects endpoint
- `app/core/project_registry.py` — RLS enforcement

**P2 — Events:**
- `app/core/event_bus.py` — SSE stream endpoint
- `app/api/v1/routes_events.py` — SSE route

---

## 9. RISK ASSESSMENT

| Risk | Severity | Mitigation |
|------|----------|------------|
| Changing auth breaks all endpoints | CRITICAL | Feature flag: `ENABLE_OIDC=false` default, dual-path validation |
| Removing CUSTOMER_PROJECTS breaks 19 files | HIGH | Gradual: add API, switch files one by one, keep static as fallback |
| Gate registry changes break Gantt | MEDIUM | Gantt already has fallback data, API is additive |
| SSE adds server load | LOW | Redis pub/sub already exists, SSE is lightweight |
| OIDC provider adds infra dependency | MEDIUM | Start with self-hosted Keycloak, migrate to managed later |

---

## 10. INTEGRITY REVIEW (2026-04-05)

### Qualified strengths

- The platform has moved beyond mock screens into an operational shell: navigation, role filtering, bankability, evidence, approvals, commitments, and guided decision flows are in place.
- The new project-truth route improves screen consistency compared with the previous one-size-fits-all demo payload pattern.
- The menu model is explicit enough to support ownership decisions, including moving the CEO report into `Operations`.

### Integrity findings

| Finding | Evidence | Why it matters |
|---------|----------|----------------|
| Mirrored React tree inside backend | `backend/app/App.tsx`, `backend/app/main.tsx`, `backend/app/components/`, `backend/app/features/` | Duplicates the frontend source tree and creates drift risk |
| Transitional truth layer | `backend/app/core/project_truth.py` | The platform itself says this is not the final system of record |
| Structuring still uses demo contexts | `backend/app/api/v1/routes_structuring.py`, `backend/app/api/v1/routes_instruments.py` | Instrument and package decisions can diverge from real project truth |
| Startup still soft-fails critical routes | `backend/app/main.py` | Missing routers can produce a partially alive app that looks healthy |
| Static project registry still leaks into screens | `src/data/customerProjects.ts` and direct imports listed above | ABAC and scope consistency still depend on screen-by-screen discipline |
| Bankability logic exists in two places | platform `backend/app/core/bankability_engine.py` and PF engine `gex_pf_engine/backend/app/core/bankability_engine.py` | Weighted scoring and completion semantics can drift |

### Immediate cleanup sequence

1. Remove the mirrored UI tree from `backend/app` or make it explicitly non-runtime.
2. Promote `project_truth.py` from transitional bridge to the only database-backed truth service.
3. Replace structuring demo contexts with project-truth-backed queries and owner-aware gate logic.
4. Consolidate bankability scoring semantics into one authoritative implementation path.
5. Change critical router registration from skip-on-missing to fail-fast or explicit degraded-mode health.

---

*This map should be reviewed after each sprint. Gate dependencies
and screen coupling will evolve as the platform matures.*
