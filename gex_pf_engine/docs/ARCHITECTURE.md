# GEX Project Finance Engine — Current Architecture

Version: **current code review as of 2026-04-08**  
Runtime port: **8001**

## Scope

`gex_pf_engine` is the computation service behind the platform.  
It is a FastAPI service mounted from [main.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/main.py).

Current mounted API groups:
- `/api/v1/model`
- `/api/v1/bankability`
- `/api/v1/pricing`

## Current Role In The Stack

The engine is not the product shell. It provides:
- bankability evaluation
- financial model calculations
- price curve and lineage calculations

The browser should not call this service directly. The intended path is:

```text
Frontend (3000) -> Platform backend (8000) -> PF engine (8001)
```

The platform proxy for bankability is in [routes_bankability_proxy.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex-platform-enhanced/backend/app/api/v1/routes_bankability_proxy.py#L1).

## What Is Actually Implemented

### 1. Bankability engine

Live bankability logic is in [bankability_engine.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/bankability_engine.py#L1).

Current semantics:
- 12 gates
- 9 states
- persona-filtered views
- capital unlock flags
- regression detection
- `overall_completion_pct`

Current scoring is **binary verified evidence completion**, not verification-weighted scoring.

A gate is complete only when every required evidence item has `status == "VERIFIED"` in [bankability_engine.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/bankability_engine.py#L224).

This means the engine currently computes:
- `verified_count`
- `completion_pct`
- `is_complete`

It does **not** currently compute:
- verification weights
- effective scores
- threshold-based gate passing

### 2. Financial model

Mounted under `/api/v1/model` from [routes_model.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/api/routes_model.py).

Core modules present:
- [cfads.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/cfads.py)
- [waterfall.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/waterfall.py)
- [debt/sculpting.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/debt/sculpting.py)
- [debt/tranche.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/debt/tranche.py)
- [engine.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/engine.py)

### 3. Pricing engine

Mounted under `/api/v1/pricing` from [routes_pricing.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/api/routes_pricing.py#L1).

Current behaviour:
- Gabillon-based price curves
- price lineage support
- supported molecule aliases
- offered molecule list loaded from the **platform fuel catalogue DB** when available
- fallback to the shared JSON seed if the platform DB is unavailable

See:
- [gabillon.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/gabillon.py)
- [price_lineage.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/core/price_lineage.py)
- DB resolution in [routes_pricing.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/api/routes_pricing.py#L34)

## What Is Not Accurate In Older Descriptions

The following are not the current reality:
- verification-weighted gate scoring is **not** the active PF engine path
- the engine is not exposing a mounted audit-chain endpoint today
- the service is not fully version-aligned internally:
  - FastAPI app version in [main.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/main.py#L29) is `1.0.0`
  - `/health` reports `5.1.0` in [main.py](/Users/jean-marie.lamay/GreenEarthX-Front-Jan26/files/gex_pf_engine/backend/app/main.py#L56)

## Persistence Model

The PF engine is still mostly stateless:
- bankability evaluation accepts request payloads
- financial model routes compute from request data
- no internal PF-engine-owned SQLite schema is mounted for business state

One exception now exists in practice:
- pricing uses the platform fuel catalogue database as an upstream reference source when present

This makes the engine computationally stateless, but no longer fully isolated from platform reference data.

## File Layout

```text
backend/app/
├── main.py
├── api/
│   ├── routes_bankability.py
│   ├── routes_model.py
│   ├── routes_pricing.py
│   └── routes_bankability_abac.py   present but not mounted
└── core/
    ├── bankability_engine.py
    ├── cfads.py
    ├── waterfall.py
    ├── audit.py                     present but not mounted through main.py
    ├── engine.py
    ├── gabillon.py
    ├── greenmesh.py
    ├── price_lineage.py
    └── debt/
        ├── sculpting.py
        └── tranche.py
```

## Current Integrity Review

Strengths:
- clean service boundary for compute-heavy finance and pricing logic
- explicit bankability and model APIs
- no browser coupling

Current gaps:
- binary verification semantics in PF engine vs weighted scoring in parts of the platform backend
- version drift in `main.py`
- `routes_bankability_abac.py` exists but is not part of the mounted runtime path
- `audit.py` exists but is not part of the current exposed runtime contract
- `micro_service/` is a local virtualenv/runtime artifact, not architecture source

## Canonical Interpretation

As of now, `gex_pf_engine` should be described as:

> a FastAPI computation service for bankability, finance-model, and pricing calculations, consumed through the platform backend, with binary verified-evidence completion logic and partial integration to platform reference data.
