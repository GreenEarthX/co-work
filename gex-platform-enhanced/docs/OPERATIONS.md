# GEX Operations Runbook

Purpose: remove key-person dependency. Everything needed to run, back up,
restore, and harden GEX is on this page. If a step is missing, fix the page,
not the person.

## Topology

| Process | Port | Repo / entry | Store |
|---|---|---|---|
| Platform API | 8000 | `gex-platform-enhanced/backend` (FastAPI, uvicorn) | `greenearth.db` + `gex_platform.db` (SQLite, WAL) |
| PF / Bankability engine | 8001 | `../gex_pf_engine/backend` (FastAPI, uvicorn) | stateless |
| Frontend dev server | 3000 | `gex-platform-enhanced/frontend` (Vite) | — |

The platform proxies all bankability calls to the engine
(`GEX_ENGINE_URL`, default `http://localhost:8001`). The engine is stateless:
evidence and snapshots live in the platform DB; the engine only evaluates.

## Start / stop

```bash
# engine (must be up before bankability screens are authoritative)
cd gex_pf_engine/backend && uvicorn app.main:app --port 8001 --reload

# platform
cd gex-platform-enhanced/backend && uvicorn app.main:app --port 8000 --reload

# frontend
cd gex-platform-enhanced/frontend && npm run dev
```

Health: `GET :8001/api/v1/bankability/health`, `GET :8000/api/v1/bankability/health`
(reports both platform DB and engine reachability).

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `development` | `production`/`staging` enables fail-fast guardrails (see SECURITY.md) |
| `SECRET_KEY` | dev default | JWT HS256 signing key. Production refuses to start on the default. |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | empty | RS256 keys; preferred over HS256 in production |
| `GEX_DEMO_MODE` | `True` | `x-demo-user` header fallback. Production refuses to start when True. |
| `GEX_SEED_DEMO_USERS` | `1` | `0` disables demo-user seeding (production) |
| `GEX_DEMO_PASSWORD` | `demo1234` | Demo password override (dev only) |
| `GEX_DB_PATH` | `greenearth.db` | Bankability/evidence/context SQLite |
| `GEX_ENGINE_URL` | `http://localhost:8001` | Engine base URL |
| `GEX_EVIDENCE_DOCS_DIR` | `data/evidence_docs` | Evidence document storage root |

## Data stores & backup

SQLite in WAL mode. Back up by copying **all three** files per DB
(`*.db`, `*.db-wal`, `*.db-shm`) while the process is idle, or use
`sqlite3 greenearth.db ".backup backup/greenearth-$(date +%F).db"` online.

What lives where:
- `greenearth.db` — bankability evidence + status events, evidence document
  index, bankability snapshots, project context (+ audit), risk-flag status
  overlay (+ audit)
- `gex_platform.db` — auth users, login history, platform modules
- `data/evidence_docs/` — uploaded evidence documents, content-addressed
  (`{sha256[:12]}_{filename}`). Back up alongside the DB; the DB stores the
  hash, the directory stores the bytes — they are only meaningful together.

Restore = stop process → replace files → start → check `/health`.

## Audit trails (append-only — never UPDATE/DELETE)

- `evidence_events` — every evidence status transition (actor, old→new, doc hash)
- `project_context_events` — power model / phase / financing model changes
- `risk_flag_events` — risk flag lifecycle transitions (incl. waiver notes)
- Every engine snapshot carries `rules_version` — the rules changelog is in
  `gex_pf_engine/backend/app/core/bankability_engine.py`. Bump on ANY rule change.

## Key rotation

1. Generate new key / RS256 pair.
2. Set `SECRET_KEY` (or key paths) in the environment.
3. Restart platform. Existing access tokens become invalid (30-min TTL);
   users re-login. Refresh tokens are invalidated likewise — this is the
   intended behaviour on rotation.

## Onboarding a project (no code edit)

1. Add the access profile + meta (currently still code: `project_registry.py`,
   `routes_projects.py` `_PROJECT_META` — known remaining gap, tracked).
2. Declare context via API (this part IS data):
   `PATCH /api/v1/projects/{id}/context` with
   `{"power_model": …, "phase": …, "financing_model": …}` —
   owner-company EXECUTIVE or platform admin; change is audited.
3. Seed evidence statuses via `POST /api/v1/bankability/evidence`; attach
   documents via `POST /api/v1/bankability/evidence/document`.
