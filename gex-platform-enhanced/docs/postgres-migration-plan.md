# PostgreSQL Migration Plan (ADR 2026-07-06)

**Decision:** PostgreSQL is the committed system of record. SQLite
(`backend/gex_platform.db`, the single canonical file) is transitional.

**Doctrine already enforced by CI** (`backend/tests/test_architecture_guardrails.py`):
no hidden database, no relative path, no second database, no module-owned
path, and a ratchet that only lets raw `sqlite3.connect` call sites decrease
(baseline 98 on 2026-07-06).

## Assets already in place — do not rebuild

| Asset | Location | Status |
|---|---|---|
| Async engine + RLS session dependency | `backend/app/db/session.py` | Written, unused — this is the target layer |
| RLS policies + hardening | `migrations/20260518120001_sprint1_rls_hardening.sql`, `migrations/setup_postgres_rls.sql` | Written |
| Alembic scaffold | `backend/alembic/` (10 versions) | Needs reconciliation with live SQLite schema |
| Postgres service (postgis 15) | `../docker-compose.yml` | Provisioned, healthchecked |
| Tenant identity for RLS | `request.state.user_payload`, set by `app/core/route_security.py` on every authenticated request | Live as of 2026-07-06 |

## Strangler sequence

Migrate **one module per slice**; each slice ends with the ratchet baseline
lowered and the module's tables live in Postgres.

1. **Schema truth first.** Autogenerate an alembic revision from the live
   SQLite schema (89 tables) so Postgres DDL matches reality, not the stale
   10 revisions. Park unused tables in a `legacy` schema rather than dropping.
2. **Identity & auth tables** (`auth_users`, `auth_login_history`,
   `auth_user_project_roles`, refresh tokens). Small, hot, security-critical,
   and owned by 3 modules (`auth.py`, `refresh_tokens.py`, `routes_auth.py`).
   Proves the sync-session path (`get_sync_db_for_company`).
3. **Projects + project_access + project_context** (`project_registry.py`,
   `project_truth.py`, `routes_projects.py`). This is the slice that turns
   RLS on for real — the policies in migration 020 target exactly these
   tables. From here, every later slice inherits tenant isolation for free.
4. **Evidence & bankability** (`bankability_evidence`, `bankability_snapshots`,
   `evidence_*`). Highest business value under RLS (investor-facing data).
5. **Capital bridge + development packages** (biggest modules, 1,200+ lines
   each — write characterization tests BEFORE migrating these).
6. **Marketplace/trading tail** (`*_sqlite.py` modules, trading_book). Bulk
   but low coupling; mechanical.
7. **Retire SQLite.** Ratchet baseline reaches 0; delete `SQLITE_DB_PATH`
   from config; the guardrail test flips from "at most one .db file" to
   "no .db file".

## Per-slice checklist

- [ ] Alembic revision for the slice's tables (+ data copy script from SQLite)
- [ ] Module rewritten against `get_db` / `get_sync_db_for_company`
- [ ] RLS policy exists for any tenant-scoped table in the slice
- [ ] Ratchet baseline lowered in `test_architecture_guardrails.py`
- [ ] Dual-run smoke: read parity between SQLite backup and Postgres

## Rules during transition

- New tables go to Postgres only. The guardrail forbids new raw SQLite sites.
- No module may read both stores; a slice migrates atomically.
- `DATABASE_URL` comes from environment in deployed contexts (compose already
  injects it); the dev default in config.py is for local convenience only.
