# GEX Platform Enhanced — Current Architecture

Version: **current code review as of 2026-04-08**  
Runtime ports: **frontend 3000**, **backend 8000**

## Scope

`gex-platform-enhanced` is the orchestration shell of GEX.

It combines:
- a React/Vite frontend in [frontend/src](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/frontend/src)
- a FastAPI backend in [backend/app](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app)
- SQLite-backed operational state
- proxy and aggregation routes over `gex_pf_engine`

## High-Level Runtime

```text
Browser
  -> React frontend (3000)
  -> Platform backend (8000)
       -> local SQLite-backed platform services
       -> optional Redis event bus
       -> PF engine proxy calls (8001)
```

## Frontend Architecture

The canonical frontend entrypoint is [App.tsx](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/frontend/src/App.tsx#L1).

Current frontend shape:
- React Router app
- authenticated shell via `RequireAuth`
- shared layout via [Layout.tsx](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/frontend/src/components/Layout.tsx)
- project context via [ProjectContext.tsx](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/frontend/src/contexts/ProjectContext.tsx)
- user role context via [UserRoleContext.tsx](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/frontend/src/contexts/UserRoleContext.tsx)
- top-menu navigation sourced from [menuArchitecture.ts](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/frontend/src/config/menuArchitecture.ts)

Major UI areas currently routed:
- projects and dashboard
- finance and bankability
- commercial and trader workflows
- compliance and evidence hierarchy
- CISO / security workspace
- pricing and structuring

## Backend Architecture

The backend entrypoint is [main.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/main.py#L1).

The backend is modular and uses:
- always-mounted routes for onboarding, decision twin, finance, audit, capacity, trader RFQs
- optional route mounts behind import guards
- optional ABAC middleware
- optional Redis-backed event bus

### Route groups currently present

Core orchestration:
- auth
- onboarding
- decision twin
- finance
- project truth
- fuels

Bankability and finance integration:
- bankability proxy
- finance-model proxy
- workflow
- timeline
- reports
- performance
- IC pack
- data room
- term sheet

Commercial and marketplace:
- capacity, contracts, marketplace, matching, demand, trader RFQs

Security extension:
- CISO routes
- permissions
- matrix comms
- approvals
- plant-data
- commitments

Other:
- verification
- deal killers
- task router
- project activity
- project ratings
- plant builder
- instruments
- structuring
- risk pricing

See mounted imports and router decisions in [main.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/main.py#L377).

## Persistence Model

The platform is not using one single persistence model yet.

### Current database split

`gex_platform.db`
- auth users and login history
- WAE approvals
- SoD logs
- CSS commitments
- DRPL policies
- OT gateway and plant data
- fuel catalogue and conversion rules
- matrix metadata

`greenearth.db`
- bankability proxy evidence and snapshots
- transitional `project_truth` runtime lookups
- some older orchestration state

This split is visible in:
- [auth.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/auth.py#L32)
- [fuel_catalog.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/fuel_catalog.py#L11)
- [routes_bankability_proxy.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/api/v1/routes_bankability_proxy.py#L24)
- [project_truth.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/project_truth.py#L20)

## Security And Access Architecture

The platform contains the real access-control layer.

### Implemented cross-cutting layer

ABAC middleware is the main global enforcement point:
- [abac.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/abac.py)
- [abac_middleware.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/abac_middleware.py)

Feature-level permissions also exist:
- [permission_engine.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/permission_engine.py)

### Implemented service modules

The backend includes explicit service modules for:
- WAE: [wae.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/wae.py)
- SoD: [sod.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/sod.py)
- DRPL: [drpl.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/drpl.py)
- OT boundary: [ot_boundary.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/ot_boundary.py)
- commitment signatures: [css.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/css.py)
- Matrix metadata + membership service: [matrix_service.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/services/matrix_service.py)

Important current limitation:
- these modules are **not** all enforced globally as a single middleware chain
- outside ABAC, many of them are explicit route-level services or CISO/admin views

## PF Engine Integration

The platform is the consumer-facing façade over `gex_pf_engine`.

Current integration path:
- frontend calls platform backend
- backend proxies to PF engine
- PF engine returns bankability or model results

Key files:
- [routes_bankability_proxy.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/api/v1/routes_bankability_proxy.py#L1)
- [routes_finance_model.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/api/v1/routes_finance_model.py)

## Current Truth Layer

The intended product direction is a single project-truth spine, but that is not fully achieved yet.

Current state:
- project truth front-door endpoint exists in [routes_project_truth.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/api/v1/routes_project_truth.py#L1)
- underlying truth model is explicitly transitional in [project_truth.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/project_truth.py#L1)
- some screens still derive truth locally or from older SQLite state

## Fuel Catalogue

The fuel catalogue is now platform-owned and DB-backed.

Key files:
- [fuel_catalog.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/core/fuel_catalog.py#L1)
- [routes_fuels.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/api/v1/routes_fuels.py#L1)

This is one of the few areas already centralized properly.

## Current Integrity Review

What is accurate:
- platform shell on 3000/8000
- PF engine behind proxy on 8001
- modular backend
- ABAC as the main access-control enforcement layer
- growing security extension modules
- DB-backed fuel catalogue

What is still structurally weak:
- split between `gex_platform.db` and `greenearth.db`
- transitional `project_truth`
- optional import guards in `main.py` mean missing modules degrade silently
- backend tree mixes Python backend and mirrored TSX files under `backend/app`
- some CISO/security surfaces are still demo-backed rather than fully enforced runtime state

## Canonical Interpretation

As of now, `gex-platform-enhanced` should be described as:

> a React + FastAPI orchestration platform that owns access control, workflow coordination, reference data, and UI composition, while delegating bankability and model computation to the PF engine, with a still-transitional truth layer and mixed SQLite persistence.
