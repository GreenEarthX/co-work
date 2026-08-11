# GEX Platform — Current State & Capabilities

**July 2026 · Technical companion to the Capital Bridge Intelligence Blueprint (V1.5) and the GEX Operating Architecture (v4.3)**

> Every figure in this document was extracted from the codebase on 2026-07-17 and is
> reproducible — the Verification Appendix lists the exact command behind each claim.
> Source of truth: `gex-platform-enhanced/docs/CURRENT_STATE_AND_CAPABILITIES_2026-07.md`;
> the Word copy in `docs/word-docs/` is generated from this file.

---

## 1. Executive Summary

GEX is a working multi-service platform for taking green-fuel projects from concept to
committed capital. It integrates producers, financiers, insurers, certifiers, logistics,
traders and regulators around one project so that each party's evidence compounds the
others', compressing time-to-FID into measurable NPV.

The platform today comprises **three running services** (platform API, project-finance
engine, techno-economic engine), a **shared event-sourced trust core**, a **React
front-end spanning 29 business domains**, and a **single canonical database of 95
tables** — behind a defense-in-depth security doctrine (authentication by default,
domain-level write authorization, attribute-based access control, one identity issuer)
that is **enforced by 13 architecture guardrail tests in continuous integration**, not
by convention.

Scale, measured from source on 2026-07-17:

| Metric | Value |
|---|---|
| Backend API | 62 route modules · 401 HTTP routes · ~51,600 lines of Python |
| Domain/core services | 47 core modules (ABAC, bankability, structuring, provenance, …) |
| Front-end | 335 TypeScript files · ~101,000 lines · 29 feature domains |
| Canonical database | 95 tables, single file, single resolved path |
| Trust core (truth stack) | Event-sourced, bitemporal · 60 tests passing |
| Deployment | 9-service Docker Compose topology · reviewed release channel |
| Architecture guardrails | 13 CI tests enforcing the platform doctrine |

## 2. System Topology

| Service | Port | Role |
|---|---|---|
| **Platform API** (FastAPI) | 8000 | Orchestration, marketplace, capital bridge, evidence, ABAC, identity issuer |
| **PF Engine** (FastAPI) | 8001 | Phase-aware project finance: bankability gates, CFADS/drawdown/covenants, Gabillon price curves |
| **TEA Engine** (FastAPI) | 8002 | Techno-economic assessment wrapping the peer-reviewed OpenPyTEA engine; upstream of the PF engine |
| **Truth stack** (library) | — | Event-sourced / CQRS / bitemporal ledger core shared by platform and engines |
| Infrastructure | — | PostgreSQL/PostGIS, Redis, Celery worker + beat, Synapse (secure comms) |

All inter-service calls carry a platform-issued identity (user bearer token forwarded,
or a short-lived service token). The engines verify **only** GEX-issued JWTs.

## 3. Functional Capabilities (live in code today)

**Capital formation & finance.** Capital bridge (20 routes), development packages with
an enforced workflow state machine (costed → evidenced → eligible), capital stack
tranches, drawdown scheduling, spend-wave planning, instruments & sovereign
instruments, deal structuring workbench, risk pricing, IC pack generation, DFI criteria
tracking, settlements, trading book, tokenisation.

**Bankability & evidence.** 12-gate bankability framework (G0 site rights → G11 COD
stabilization) with verification-weighted gate scoring; 9-state bankability ladder
(SPECULATIVE → FINANCEABLE → OPERATIONAL); hash-chained (SHA-256) immutable evidence
ledger with chain-verification endpoint; CEC (Capital Eligibility Coverage) and FRI
(FID Readiness Index) pre-COD metrics; independent-verifier states feeding gate scores.

**Trust core.** The truth stack models facts, decisions and derived results as an
append-only ledger with a formally specified 9-state claim machine (asserted →
submitted → verified → satisfied / waived / expired / rejected / superseded), legal
transition sets, reconciliation, and release/drawstop decisions. Bitemporal by design:
the platform can answer "what did we know on date X" — the basis for lender reliance.

**Market & operations.** Marketplace, matching engine, RFQs/offers, demand aggregation,
contracts, capacity management, carbon attribution, mass balance, fuel lineage
(8-source database fan-out), additionality assessment, plant builder, performance
tracking, project activity timelines.

**Intelligence surfaces.** Decision twin, next-best-action, adjacency benchmarking,
adversarial reviews, deal-killer screening — the reasoning surfaces the Capital Bridge
Intelligence blueprint (V1.5) will unify over the Risk–Evidence Pair.

**Governance.** CISO workspace (27 routes), approvals with segregation-of-duties
conflict pairs, entitlements with per-project grants, immutable audit trail, permission
engine (165-permission × 30-profile matrix).

## 4. Security & Governance Doctrine (consolidated July 2026)

Layered, outermost first — each layer holds even if another fails:

1. **Authentication by default.** Every route requires a verified identity; the only
   public endpoints are those in an explicit registry, each with a written reason.
2. **Domain write-authorization.** All 61 API prefixes map to 8 business domains
   (finance, projects, marketplace, sustainability, verification, governance,
   intelligence, platform); writes are checked against business-function policies;
   unmapped routes fail closed.
3. **ABAC policy engine.** Attribute-based evaluation on every API request (user,
   resource, action, context), with every decision logged to the audit trail.
4. **One identity issuer.** The platform mints all tokens (RS256/HS256 with JWKS
   endpoint); both engines verify platform tokens only; backend→engine calls carry
   forwarded user identity or short-lived service tokens.
5. **Row-level security backstop.** PostgreSQL RLS policies and per-request tenant
   context are written and staged; they activate slice-by-slice with the Postgres
   migration (see §6).
6. **CI guardrails.** 13 tests fail the build on doctrine regressions: a second
   database file, a module-owned DB path, an unregistered public route, a bypassed
   registry, a new evidence-state enum in the engines, growth in raw SQLite call
   sites, or a Docker Compose file that builds a different backend than the one the
   tests inspect ("reviewed code = running code").

Production hard-stops: the platform refuses to boot in production with a development
signing key or with demo-mode authentication enabled.

## 5. Engineering Quality & Delivery

- **Tests:** backend suite 49 tests; truth stack 60 tests (100% passing); guardrail
  suite runs as part of CI via `backend/scripts/ci_guardrails.sh`.
- **Reproducible product surface:** the menu architecture (v6.1) is generated from the
  real front-end config with an audit script checking per-role visibility and
  door↔screen coherence.
- **Release discipline:** one blessed source tree; deployment artifacts (the co-work
  repository consumed for remote Docker builds) are refreshed through a reviewed
  release flow — freeze branch, exclusion-listed copy, staged diff review, tagged
  commit. No silent sync anywhere in the pipeline.
- **Docker:** 9-service compose topology validated and buildable; engine images build
  clean from the release tree; production images publish via a source-built push
  script (backend, frontend, PF engine, TEA engine).

## 6. Known Limitations & Near-Term Roadmap (stated plainly)

| Item | State | Plan |
|---|---|---|
| SQLite as transitional store | Single canonical file; raw call sites frozen under a CI ratchet (may only decrease) | Strangler migration to PostgreSQL, slice-by-slice, RLS activating with the projects slice (plan in `docs/postgres-migration-plan.md`) |
| Evidence state models | Multiple parallel state machines (ledger, truth stack, verification weights) | Consolidate on the truth-stack claim machine as canonical; chained transitions with recorded verifiers; findings & 8 recommendations documented in the Blueprint's Compliance Annex |
| Risk–Evidence Pair | Not yet a first-class object (linkage is implicit via gates/packages) | The core net-new build of Capital Bridge Intelligence V1 — additive, not a rewrite |
| Front-end auth in demo flows | Demo-user context in development; production hard-fails demo mode | Wire login flow to the platform JWT (backend fully supports it today) |
| Published Docker Hub images | Last pushed April (pre-doctrine) | Re-publish as v2.0.0 from the release tree (script ready) |

## 7. Verification Appendix — reproduce every number

```bash
# 62 route modules / 47 core modules / ~51.6k LOC / 401 routes
ls backend/app/api/v1/*.py | grep -v __init__ | wc -l
ls backend/app/core/*.py | wc -l
find backend/app -name '*.py' -not -path '*__pycache__*' | xargs wc -l | tail -1
venv/bin/python -c "from app.main import app; print(len(app.routes))"

# 335 front-end files / 29 domains
find frontend/src \( -name '*.tsx' -o -name '*.ts' \) | wc -l
ls -d frontend/src/features/*/ | wc -l

# 95 tables, single canonical DB
sqlite3 backend/gex_platform.db \
  'SELECT count(name) FROM sqlite_master WHERE type="table";'

# Test suites & guardrails
cd backend && venv/bin/python -m pytest tests/ -q        # 49 tests
cd efuel_truth_stack && python -m pytest tests/ -q        # 60 tests
backend/scripts/ci_guardrails.sh                          # 13 doctrine guards

# 9 compose services
awk '/^services:/,/^networks:/' docker-compose.yml | grep -cE '^  [a-z_]+:'
```

*Suite status on 2026-07-17: 48 of 49 backend tests green. The single failure is the
compose-identity guardrail correctly flagging a snapshot tree (`files/docker/`)
recreated outside the release flow — the guardrail working as designed; disposition
pending an owner decision.*
