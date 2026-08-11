# GEX platform — working notes

Everything here was verified against the tree or the live database on
**2026-08-10**. Where a number is stated it was measured, not remembered. If
something below contradicts the code, the code wins — and fix this file.

Deeper background: `docs/CLAUDE_HANDOFF.md` (current state, defects, open
decisions). `../docs/CLAUDE.md` is an older architecture reference — useful for
product intent, stale on infrastructure, and **not** auto-loaded.

---

## Services

| Port | Service | Tree |
|---|---|---|
| 8000 | GEX backend (FastAPI) | `backend/` |
| 8001 | PF engine — project finance | **`../gex_pf_engine/backend`** (sibling repo) |
| 8002 | TEA engine — techno-economic | `tea_engine/` (stateless, no database) |
| 3000 | Frontend (Vite/React/TS) | `frontend/` |
| 55432 | PostgreSQL | container `files-postgres-1` |

**Port 55432 is not a typo.** A different, non-GEX PostgreSQL occupies `:5432`
on this machine; `55432` is a socat forwarder to the GEX container. Do not
"correct" it to 5432 — you will read or migrate the wrong database.

**There are two `gex_pf_engine` directories.** `../gex_pf_engine` (sibling) is
the one serving `:8001`. `./gex_pf_engine` is an in-repo copy. Editing the copy
changes nothing at runtime.

Run servers via the Browser pane / `.claude/launch.json`, not `Bash`.

---

## Database — two credentials, never one

```
DATABASE_URL          gex_app    runtime.  No SUPERUSER, no BYPASSRLS,
                                 no CREATE on schema public. RLS APPLIES.
ALEMBIC_DATABASE_URL  gex_user   DDL and migrations only.
```

Migration 045 made this real. Before it, the runtime connected as a superuser
and every RLS policy was decorative. Measured on a live `gex_app` connection:
`projects` returns 14 rows as `PLATFORM_ADMIN`, **3** as a tenant, **0** with no
tenant context.

**Do not collapse these back into one variable.** DDL is not subject to RLS, so
a migration running with the runtime credential — or a runtime holding DDL
rights — turns any injection into a full read of every tenant. Pointing
`DATABASE_URL` at a superuser to make a permissions error go away will be caught
by `tests/test_gex_app_runtime_role.py`, which asserts against whatever
`DATABASE_URL` is actually configured.

### Traps that cost real time

- **`ALEMBIC_DATABASE_URL` must be EXPORTED**, not merely present in `.env`.
  pydantic's `env_file` populates `settings`, *not* `os.environ`, and Alembic
  reads `os.getenv`. A migration run without the export silently targets
  whatever `alembic.ini` says.
- **Alembic uses branches.** `030` is an independent root labelled `auth_slice`.
  Upgrade with `alembic upgrade auth_slice@head`, never bare `head`.
- **`Settings` forbids extra inputs.** A new environment variable must be
  declared in `app/core/config.py` or the app refuses to start.
- **WAL-mode SQLite.** Copying only the `.db` file does not capture state; the
  `-wal` sidecar carries changes forward and silently reverts part of a restore.
  Copy/remove `-wal` and `-shm` too, or use `VACUUM INTO`.

### Migration state

PostgreSQL holds all 98 tables at head **045**, 89 under FORCED RLS. But **all
eight backend switches still read `sqlite`** (`AUTH_`, `EVIDENCE_`, `CAPITAL_`,
`MARKET_`, `ENTITLEMENT_`, `EVENTSTORE_`, `FUELREF_`, `GOVERNANCE_DB_BACKEND`).
Both stores are live and **diverging, continuously**. `finance_entitlements`:
**838** in PostgreSQL, **744** recorded as actually copied, and SQLite somewhere
above both and climbing — it was 1128 one morning and 1332 by the afternoon,
because running the test suite adds rows. Do not treat the SQLite count as a
fixed number.

Any cross-store comparison must sample from `migration_watermarks.copied_keys`.
"Both stores hold the same rows" is not a property that can hold while SQLite is
still the active backend, and a test asserting it will fail for the wrong reason.

---

## Tenant isolation — how the caller reaches the database

Two paths, one identity. `app/core/request_tenant.py` is the single derivation;
`ABACMiddleware` binds a request-scoped `ContextVar` and unbinds it in a
`finally`.

- `Depends(get_db)` — SQLAlchemy, ~109 sites
- `*_connection()` — the shim in `app/core/db_backend.py`, ~64 sites

Shim resolution is **explicit argument → bound caller → deny sentinel**. The
default is `NO_TENANT_CONTEXT`, which matches no tenant-scoped policy, so code
with no caller reveals nothing. It used to default to `PLATFORM_ADMIN` and no
call site overrode it.

**`PLATFORM_ADMIN` disables tenant isolation for a whole connection.** Pass it
only for a genuine bootstrap — reading the rules you are using to decide access.
Seven call sites do (entitlements, the five governance policy readers, the audit
ledger write path); each says why, and every use is logged by `_tenant_context`.
If you need it in a test, use `as_platform_admin()` from `tests/pg_support.py`.

Auth tables carry no RLS, so login works regardless of tenant context. Reference
data (`fuel_catalog`, `approval_policies`, …) is deliberately readable by all —
failing closed must not blackhole it.

---

## Accounts are vetted, not self-served

`POST /register` creates a **`PENDING`** account and nothing else.
`LOGIN_PERMITTED_STATES` is `{ACTIVE}` only. Activation requires GEX staff,
telephone verification, a signed usage agreement, and separation of duties
(activator ≠ claimant). See `app/core/account_lifecycle.py`.

All 17 rows in `auth_users` are `ACTIVE` via `activated_by='SEED_GRANDFATHERED'`
— they predate vetting. Do not backfill those NULL phone/agreement columns; that
marker is how you find them.

Deal and product data belongs **behind the backend**, not the frontend's
Supabase `.from()`. Do not "fix" a frontend data path by wiring it to PostgREST.

---

## Tests

```bash
cd backend && ./venv/bin/python -m pytest tests/ -q
```

**429 pass** against PostgreSQL as `gex_app`; **329 pass, 104 skip** on all
SQLite. Zero failures in both, and zero with the database stopped. (Counts move —
this tree has more than one session writing to it; re-measure rather than trust
a number you did not just run.)

- `tests/pg_support.py` is the only place that **calls** `psycopg2.connect`
  (the architecture guardrail names the pattern in prose, which is why that
  guardrail matches the AST rather than the text). An absent or
  unreachable database is a **SKIP**; only a reachable database answering
  incorrectly is a FAILURE. Tests reaching PostgreSQL indirectly through the app
  must call `requires_pg()`.
- Guardrails match the **AST, not the text** — several here discuss the very
  pattern they forbid, and earlier versions repeatedly matched their own prose.
- **Tests must not write the dev database.** Use the `isolated_store` fixture in
  `tests/conftest.py`.
- Negative-verify a new guardrail: break the thing deliberately and confirm it
  fails. One in this repo passed for a reason nobody had checked until it was.

---

## Style

Function over design. Concise and direct. Incremental changes over monolith
patterns.

---

## vexp — context-aware orientation <!-- vexp v2.5.3 -->

Canonical vexp guidance lives in the parent `files/.claude/CLAUDE.md`, which
also loads. It is not repeated here — this file previously carried a stale
v2.0.12 copy that contradicted it.

In short: `run_pipeline({ "task": "..." })` for orientation when a task does
**not** name the files or symbols to touch. If it does, skip vexp and use your
normal tools. `get_skeleton` for structure you only need to understand;
`verify_done` once before declaring a multi-file task complete.

Anchor queries on real identifiers or paths:
`run_pipeline({ "task": "fix JWT expiry in AuthService.validateToken" })`

<!-- /vexp -->
<!-- The marker pair above delimits a vexp-managed block. Keep the vexp section
     LAST in this file: if vexp regenerates it, only the trailing block is
     replaced and the GEX notes above survive. An unclosed opening marker risks
     a rewrite swallowing everything to end-of-file. -->
