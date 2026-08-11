# GEX Platform — Engineering Handoff

**Generated:** 2026-08-09 · **Derived from:** repository inspection, not conversation history.
**Scope:** state of the tree at `files/gex-platform-enhanced` and its siblings.

Where this document states a number (table counts, test counts, occurrence counts), it was
measured against the working tree or the live database at the time of writing. Where it
states an intention, it is marked as such.

---

## 1. Architecture and service boundaries

Four processes, all currently running locally:

| Port | Service | Tree | Role |
|---|---|---|---|
| 8000 | GEX backend (FastAPI) | `gex-platform-enhanced/backend` | Product logic, authz, persistence, proxying |
| 8001 | PF engine (FastAPI) | `files/gex_pf_engine/backend` *(sibling repo)* | Project-finance / Gabillon cashflow engine |
| 8002 | TEA engine (FastAPI) | `gex-platform-enhanced/tea_engine` | Techno-economic analysis (OpenPyTEA-derived) |
| 3000 | Frontend (Vite/React/TS) | `gex-platform-enhanced/frontend` | UI |
| 55432 | PostgreSQL (via socat) | container `files-postgres-1` | Primary datastore |

**Port 55432 is not a typo.** A different, non-GEX PostgreSQL occupies `:5432` on this
machine. `55432` is a socat forwarder to the GEX container. `backend/.env` overrides the
`config.py` default (which still says `:5432`) for this reason. Any new environment must
make the same distinction or it will silently migrate the wrong database.

**There are two `gex_pf_engine` directories.** `files/gex_pf_engine` (sibling, the real
engine serving `:8001`) and `gex-platform-enhanced/gex_pf_engine` (an in-repo copy).
The sibling is authoritative. Do not edit the in-repo copy expecting `:8001` to change.

`efuel_truth_stack/` is a self-contained event-sourced/CQRS/bitemporal reference core.
It is not wired into the running backend and is not part of the migration.

`backend/app/main.py` registers **66 routers**. There is no single registry object; the
list in `main.py` is the registry.

---

## 2. Authentication and authorization

Four distinct layers. They are not interchangeable and each fails differently.

### 2.1 Account lifecycle (the vetting gate) — authoritative

`backend/app/core/account_lifecycle.py` defines five states:

```
PENDING → IN_VETTING → ACTIVE ⇄ SUSPENDED
                    ↘ REJECTED (terminal)
```

`LOGIN_PERMITTED_STATES = frozenset({ACTIVE})`. Nothing else may authenticate. This is
enforced in `authenticate_user` (`app/core/auth.py`), which raises `AccountNotActive`.

`backend/app/api/v1/routes_account_vetting.py` exposes nine endpoints. **Only
`POST /register` is public**, and it can produce a `PENDING` account and nothing else.
The remaining eight (`/status`, `/vetting-queue`, `/{user_id}/claim`,
`/telephone-verification`, `/usage-agreement`, `/activate`, `/reject`, `/suspend`)
require GEX staff. Activation asserts three things independently: activator is GEX staff,
required evidence exists (telephone verification **and** signed usage agreement), and
separation of duties (the activator is not the claimant).

Accounts live in **`auth_users`** (there is no `users` table). It currently holds
**17 rows, all `ACTIVE`, all with `activated_by = 'SEED_GRANDFATHERED'`** and NULL
phone/agreement columns — i.e. every account in the system predates vetting and none has
yet been through it. **That marker is how you find them.** Do not backfill those NULLs.

### 2.2 Token authentication

HS256 JWT. `SECRET_KEY` defaults to `dev_secret_key_change_in_production` in
`config.py:20` — still the dev default in this environment.
`ACCESS_TOKEN_EXPIRE_MINUTES = 30`.

Service-to-service calls carry a service-role token. `get_user_payload_from_token`
has an explicit service branch assigning `company_id = "__platform_service__"`; before
that branch existed, service tokens crashed the ABAC middleware on a missing key.

### 2.3 ABAC middleware

`ABACMiddleware` is added in `main.py:558` with `phase=settings.ABAC_PHASE`, currently
**2**. This is middleware-level, not per-route dependency. A route added to `main.py`
is covered by default — which is the safe direction, but it also means route-level
authorization intent is not visible at the route.

`app/core/domain_authorization.py`, `entitlements.py`, `permission_engine.py`,
`route_security.py` sit above it for domain/project/action scoping.

### 2.4 PostgreSQL Row-Level Security (defence in depth)

**89 of 98 tables have RLS enabled, and it is FORCED** (`relforcerowsecurity`), so the
table owner does not bypass it. Policies key on
`current_setting('app.current_company_id', true)`.

Two roles, and since migration 045 they are used for different things:

- `gex_app` — **the runtime identity.** LOGIN, not superuser, no BYPASSRLS, USAGE but
  **not CREATE** on schema public. `DATABASE_URL` points here. RLS applies.
- `gex_user` — SUPERUSER, BYPASSRLS. **Migrations only**, via `ALEMBIC_DATABASE_URL`.

**RLS now binds at runtime.** Measured on a live `gex_app` connection: `projects` returns
14 rows as `PLATFORM_ADMIN`, **3** as `hamburgone_com`, **0** with no tenant context.
Before 045 all three were 14, because the runtime connected as a superuser and no policy
was ever evaluated — "89 tables under forced RLS" described the schema, not the running
system.

Verified refused on that same connection: `CREATE TABLE`, `DROP TABLE`,
`ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, `SET ROLE gex_user`, and reading
`pg_authid`. Pinned by `tests/test_gex_app_runtime_role.py`, which asserts against
**whatever `DATABASE_URL` is actually configured** — so repointing it at a superuser, the
quickest way to make a permissions error disappear, fails loudly instead of silently
making every policy decorative.

Migration 032 introduced `SECURITY DEFINER` helper functions with pinned `search_path`
to break mutually-recursive policies from 020 (which had never been evaluated before
`gex_app` existed, so the recursion was latent). The same migration removed an
empty-string bypass in which an unset GUC granted visibility.

Four RLS shapes are in use, deliberately (see `tests/test_governance_slice.py`):
global-readable reference/rules, project-scoped via the 032 helpers, **admin-only for
user-scoped tables**, and direct company comparison. User-scoped tables are admin-only
because no `app.current_user_id` GUC exists — company-scoping them would let a colleague
read another user's permission overrides.

---

## 3. Databases actually used by each service

| Service | Store |
|---|---|
| GEX backend | Dual: PostgreSQL (schema complete) **and** SQLite `backend/gex_platform.db` (still serving) |
| PF engine `:8001` | SQLite only — 12 `sqlite3` sites, no PostgreSQL client |
| TEA engine `:8002` | **Stateless.** No database of any kind. Verified: no `sqlite3`, no `psycopg2`, no `DATABASE_URL` |
| Frontend | Supabase JS client, plus the backend API |

### The backend's dual-store state — read this before touching anything

The SQLite→PostgreSQL migration is **complete in schema and data; the per-slice switches
are not yet flipped.** PostgreSQL is at Alembic head **045**, holds **98 tables**, and
`migration_watermarks` records **53 copied tables** with their exact copied keys. The
runtime already connects to PostgreSQL as `gex_app` for the SQLAlchemy paths — it is the
eight *shim* switches that still read SQLite.

Eight independent backend switches exist in `config.py`:

```
AUTH_DB_BACKEND  EVIDENCE_DB_BACKEND  CAPITAL_DB_BACKEND    MARKET_DB_BACKEND
ENTITLEMENT_DB_BACKEND  EVENTSTORE_DB_BACKEND  FUELREF_DB_BACKEND  GOVERNANCE_DB_BACKEND
```

**All eight are `"sqlite"`.** `.env` sets `AUTH_DB_BACKEND=sqlite` explicitly; the rest
default. This is intentional — flipping before the target database is the real one would
migrate identity and evidence twice.

`app/core/db_backend.py` is the shim: `PostgresConnection` presents a `sqlite3`-shaped
API over psycopg2 (including `?`→`%s` rewriting), so call sites are backend-agnostic.

**Two database credentials, deliberately different roles — never collapse them:**

```
DATABASE_URL          gex_app    runtime. No SUPERUSER/BYPASSRLS/CREATE. RLS applies.
ALEMBIC_DATABASE_URL  gex_user   DDL and migrations only.
```

`alembic/env.py` prefers `ALEMBIC_DATABASE_URL`, so pointing `DATABASE_URL` at the
unprivileged role does not break migrations. DDL is not subject to RLS, so a migration
running with the runtime credential — or a runtime holding DDL rights — turns any
injection into a full read of every tenant. Both are asserted by tests.

**`ALEMBIC_DATABASE_URL` must be EXPORTED, not merely present in `.env`.** pydantic's
`env_file` populates `settings`, not `os.environ`, and Alembic reads `os.getenv`.

Alembic uses branches. `030_auth_slice` is an **independent root** with
`branch_labels='auth_slice'`; `020` was re-parented onto `030`. Upgrade with
`alembic upgrade auth_slice@head`, not bare `head`.

Raw `sqlite3.connect` occurrences in `backend/app/`: **68**, down from a guardrail
baseline of 97 in `tests/test_architecture_guardrails.py:300`. The baseline is a
ratchet — it may only decrease.

---

## 4. Communication paths

```
Browser
  ├─ /api/*  ──► vite proxy ──► backend :8000        (VITE_API_URL, default localhost:8000)
  └─ Supabase JS client ──► Supabase PostgREST       (9 lib files, see §5)

backend :8000
  ├─ ──► PF engine :8001      GEX_ENGINE_URL  (MODEL_ENGINE_URL / BANKABILITY_ENGINE_URL)
  ├─ ──► TEA engine :8002
  └─ ──► trading book         GEX_TRADING_BOOK_URL
```

Backend→engine calls forward the caller's bearer token. TEA verifies it with
`tea_engine/auth/gex_jwt.py` using shared-secret HS256 (`GEX_JWT_SECRET`, defaulting to
the platform dev secret and logging a warning when it does). The PF engine has an
equivalent bridge at `files/gex_pf_engine/backend/app/auth/gex_jwt.py`.

Frontend token reads are consolidated: `frontend/src/lib/authToken.ts` is the single
reader of the `gex_auth_session` key. `engineClient.ts` imports `getAuthToken` from it
(line 27/128). Only `main.tsx`, `UserRoleContext.tsx`, and `authToken.ts` itself touch
that storage key.

---

## 5. Security decisions that are now authoritative

These are settled. Do not re-open without Jim.

1. **Deal and product data belongs behind the GEX backend, not the frontend's Supabase
   `.from()`.** Vetted status, signed agreement, organisation role, project access and
   audit logging are product-policy decisions and live in the backend. Supabase/Postgres
   remains the persistence layer; RLS remains defence in depth — neither is the policy.
2. **Registration creates a `PENDING` account only.** Creating credentials or typing
   data into the UI confers no trust. A GEX employee must complete onboarding, including
   at least one telephone verification and exchange/signature of the software usage
   agreement, before activation. Thereafter, login plus security code suffices, subject
   to role and project permissions.
3. **Retirement is irreversible.** In `tokens_sqlite.py`, `RETIRED` has exactly one
   outgoing edge — `ANNULLED`, which is terminal and non-claimable. `SETTLED` cannot be
   voided; delivery is a fact. `tests/test_token_lifecycle.py` proves this by graph
   reachability (`_reachable(RETIRED) & CLAIMABLE_STATES` must be empty), not by
   enumerating edges — so a new state cannot smuggle a path back.
4. **The audit event is appended before the projection is written**, matching
   `create_token`. Reversing this reintroduces a self-deadlock, because `append_event`
   opens its own connection.
5. **Concurrent appends to `platform_events` serialise on a PostgreSQL advisory lock.**
   The unique constraint and single-root partial index (migration 040) are backstops
   that should never fire. Measured before the fix: 12 concurrent appends → 9 written,
   **3 rejected**, 1 fork. A rejected audit event is data loss, so the constraint alone
   was not a fix. After: 30/30, 0 rejected, 0 forks.
6. **RLS is enabled even where access is deliberately open** (reference data, approval
   rules), with an explicitly named permissive policy. "Deliberately public" must be
   distinguishable from "forgotten".
7. **A compliance rule you cannot read is a trap.** `approval_policies` and
   `sod_conflict_pairs` are readable by every tenant and writable only by admin.
8. **Tables with no `project_id` are admin-only.** No honest tenant policy exists for
   them; a policy that only appears to isolate is worse than none.
9. **Dead tables are quarantined, not dropped.** All 12 were renamed
   `<table>_quarantined_20260809` after confirming 0 rows. Backup:
   `backend/data/db_backups/gex_platform.pre-quarantine.20260809.db`.
10. **Supabase stays.** Leaving it would mean giving up the managed layers and running
    Postgres, auth, and the API by hand.

### Operational trap worth keeping

`cp` of the main `.db` file does **not** restore a WAL-mode SQLite database — the `-wal`
sidecar carries uncommitted state forward and silently reverts part of your restore.
Copy or remove `-wal`/`-shm` alongside it, or use `VACUUM INTO`.

---

## 6. Files materially changed

Grouped by intent. Full mtime-derived list is reproducible with
`find backend/app backend/tests backend/alembic/versions frontend/src docs tea_engine -mtime -14`.

**New modules**
- `backend/app/core/account_lifecycle.py` — vetting state machine and assertions
- `backend/app/core/projects_store.py` — canonical projects accessor
- `backend/app/core/db_backend.py` — dual-backend shim and the eight switches
- `backend/app/api/v1/routes_account_vetting.py` — nine vetting endpoints
- `frontend/src/lib/authToken.ts` — single reader of `gex_auth_session`
- `backend/.env` — `DATABASE_URL` on 55432, `AUTH_DB_BACKEND`

**Migrations 030–044** (plus 020/021 re-parented and JSONB defaults corrected):
auth · RLS role · policy recursion · projects collision · evidence · capital bridge ·
marketplace · entitlements · watermarks · event store · chain root · fuel reference ·
governance · chained ledgers · domain tail.

**Behaviour changes**
- `capital_bridge.py` — **1000× units defect fixed** (MWh→kWh conversion was missing
  before dividing by electrolyser SEC)
- `event_store.py` — advisory lock; `init_event_store()` guarded against running SQLite
  DDL at import under PostgreSQL
- `auth.py` — vetting gate, `auth_db_connection()`, lifecycle column grandfathering
- `tokens_sqlite.py` — `ANNULLED`, terminal-state sets, event-before-projection
- `project_truth.py`, `routes_projects.py` — repointed at `projects_store`
- `core/{wae,sod,css,drpl,permission_engine,fuel_catalog,vocabulary,entitlements}.py` —
  backend-aware `init_*` guards
- `tea_engine/{routes/tea.py,compute/openpytea_runner.py,cepci_extension.py}` — restored
  and hardened

**Tests added:** 13 files, plus `tests/pg_support.py` (the single PostgreSQL entry point) — token lifecycle (18), TEA (19), account lifecycle (22),
projects canonical (14), RLS isolation, evidence (12), slice-5 characterization (41),
marketplace (10), entitlements (12), event store (10), fuel reference (9),
governance (17), tail slices (13).

---

## 7. Tests and guardrails

Run from `backend/` with `./venv/bin/python -m pytest tests/ -q`.

| Configuration | Result |
|---|---|
| `DATABASE_URL` → `gex_app` (the runtime role) | **429 passed, 0 failed, 4 skipped** |
| `DATABASE_URL` unset (all SQLite) | **329 passed, 0 failed, 104 skipped** |
| `DATABASE_URL` → PostgreSQL, **container stopped** | **329 passed, 0 failed, 104 skipped** |

> **Counts move — this tree has concurrent writers.** On 2026-08-11 the suite went
> from 326 to 429 with no code change of mine: six test files (`test_client_billing`,
> `test_open_interest`, `test_throughput_billing`, `test_commitment_taxonomy`,
> `test_open_interest_routes`, `test_rating_engine_expiry_blindness`) appeared from
> another session, contributing exactly 103 tests. All pass. Re-measure rather than
> trusting a number you did not just run.

**The suite is fully green in all three configurations as of 2026-08-10.** The
long-standing compose failure was resolved by deleting the stale tree (below).

### The runtime no longer connects as a superuser (2026-08-10, migration 045)

`gex_app` was created by 031 and left NOLOGIN, usable only via `SET ROLE` from a
superuser session. 045 grants LOGIN and re-asserts its privilege envelope, including
`ALTER DEFAULT PRIVILEGES` so tables added by later migrations inherit it — otherwise the
runtime silently loses access to new tables and it looks like a bug in the feature.

The migration deliberately **does not set a password**: a password in a migration is a
credential in version control. Set one per environment:

```sql
ALTER ROLE gex_app WITH PASSWORD '<from your secret store>';
```

The local development password is `gex_app_password_dev`, committed in `backend/.env`
alongside the pre-existing `gex_password_dev` so a fresh checkout runs. **Both are
development-only.**

Three tests would have been unwritable before this change, because the runtime connected
as a superuser and tenant isolation was therefore unfalsifiable: a tenant sees a strict
subset of admin's rows; no tenant context reveals nothing; not every tenant sees every
project.

### The caller's tenant now reaches both database paths (2026-08-10)

`app/core/request_tenant.py` is the single derivation of "who is calling", plus the
request-scoped `ContextVar` the shim needs (it has no `Request` to read).
`ABACMiddleware` binds it once the JWT is verified and unbinds it in a `finally`;
`route_security` binds it for the three routes that authenticate by dependency instead.
Resolution order in the shim: **explicit argument → bound caller → deny sentinel.**

**A second defect was found while doing this.** `ABACMiddleware` set
`request.state.auth_user_payload`, but `db/session.py::_company_id_from_request` read
`request.state.user_payload` — a different attribute. `route_security` sets both, but is
imported in only three places, so for most of the 109 SQLAlchemy sites the payload was
never found and the tenant resolved to `'GUEST'`.

Under `gex_user` neither defect is visible, because RLS is not evaluated at all. Under
`gex_app` the first exposes everything and the second hides everything — an outage and a
breach, discovered on the same afternoon. The middleware now sets both names and
`payload_from_request` reads both, until one is retired deliberately.

Pinned by `tests/test_request_tenant.py` (11 tests) against a real ASGI stack, including
the load-bearing assumption that a `ContextVar` set inside a Starlette
`BaseHTTPMiddleware` reaches the route handler — true today, not documented API, so
asserted rather than reasoned about.

> **A guardrail here passed for the wrong reason, and negative verification is the only
> reason that is known.** The cross-request test originally claimed the `finally` reset
> was what prevented tenant leakage. Deleting the reset changed nothing: each request runs
> in its own asyncio task and a `ContextVar` set there dies with the task. Task-context
> isolation is the mechanism; the reset is defence-in-depth for callers that do not get a
> fresh task. The test now says so, and the reset's existence is pinned separately over
> the AST — because no HTTP-level test can see it.

### The shim's tenant-context default now fails closed (2026-08-10)

Found during the credential-architecture review. Every `*_connection()` accessor in
`app/core/db_backend.py` defaulted to `company_id=PLATFORM_ADMIN`, and an audit of all
**64 call sites found that not one overrode it**. 88 of the 93 RLS policies grant
`PLATFORM_ADMIN` full visibility.

So the day the eight switches flipped to PostgreSQL, those 64 sites would have read every
tenant's rows — while every RLS test still passed, because the tests set their own
context rather than exercising the application's. **Policies existing is not policies
binding.**

The default is now `NO_TENANT_CONTEXT = "__no_tenant_context__"`, which matches no
tenant-scoped policy. Measured under role `gex_app`:

| table | as PLATFORM_ADMIN | with the sentinel |
|---|---|---|
| `projects` | 14 | **0** |
| `finance_entitlements` | 838 | **0** |
| `fuel_catalog` / `fuel_unit_conversions` | 10 / 120 | 10 / 120 (unchanged) |
| `approval_policies` / `sod_conflict_pairs` | 8 / 8 | 8 / 8 (unchanged) |

Deliberately-public data is unaffected — its policies never consult the company. Auth
tables carry no RLS at all, so login is unaffected.

Seven call sites with a genuine bootstrap need — entitlement checks, governance policy
evaluation (`wae`, `sod`, `css`, `drpl`, `permission_engine`) and the audit-ledger write
path — now pass `company_id=PLATFORM_ADMIN` **explicitly**, and every such connection is
logged once per call site by `_tenant_context()`. Everything else gets no tenant context,
so a premature flip fails loudly instead of silently exposing data.

Pinned by `tests/test_tenant_context_default.py` (16 tests): no accessor may default to
admin (AST), the sentinel must deny tenant data *and* must not break public data, the
denial must be measurably stricter than admin (so an empty table can't pass it vacuously),
no real tenant may hold the sentinel value, and escalation must stay logged.

**This change is inert at runtime today** — all eight switches are on SQLite, and the
SQLite branch ignores `company_id`. Verified live: backend healthy, all switches `sqlite`.

### `tests/pg_support.py` — the one PostgreSQL entry point

Added 2026-08-10. Previously seven files each defined their own `_pg()` and 24 call sites
guarded database access with only a DSN *string* check, which says nothing about whether
anything is listening. Helpers that caught the connection error skipped; raw
`psycopg2.connect` sites raised it and **failed**. With the container stopped the suite
reported *8 failed, 209 passed, 70 skipped* — an outage that reads exactly like a
regression.

`pg_support.py` is now the only `psycopg2.connect` call site in the suite and exports
`pg_dsn`, `pg_connect`, `pg_admin` (the former `_pg`), `pg_as_tenant`, and `requires_pg`
(for tests that reach the database indirectly through the application shim). Reachability
is probed once per session and cached, so a down database costs one timeout rather than
seventy. **The rule: absent or unreachable is a SKIP; only a reachable database that
answers incorrectly is a FAILURE.**

Enforced by `test_pg_support_is_the_only_postgres_connect_site_in_the_suite`, which walks
the **AST** rather than the text — its own explanation contains both offending patterns
verbatim, and earlier guardrails in this repo repeatedly matched their own prose. It
excludes only itself, since a scanner must name the pattern it hunts. Negative-verified
in both directions: reintroducing a raw connect, and reintroducing a DSN-string guard,
each make it fail.

The 78 SQLite-mode skips are PostgreSQL-only guardrails (RLS, advisory locking,
cross-backend agreement) that correctly self-skip.

**The single failure is the same in both:**
`tests/test_architecture_guardrails.py::test_compose_runs_the_tree_that_tests_inspect`.
Long-standing and pre-existing. **Diagnosed 2026-08-09 — cause is now known.**

The test makes two assertions. The first (the blessed `REPO/docker-compose.yml` builds
and mounts from this backend tree) **passes**. The second fails, with exactly one
offender:

```
files/docker/gex-platform-enhanced/docker-compose.yml
  builds backend from files/docker/gex-platform-enhanced/backend
```

That is a **stale whole-platform copy**. Decisive evidence is content, not mtime (the
mtimes were reset by a copy operation and are misleading): the copy has **zero
migrations numbered 030+** and **no `account_lifecycle.py`**. It therefore predates the
entire auth slice, the vetting gate, and the whole PostgreSQL migration. Running it
would start a backend with no vetting and no RLS.

Nothing uses it: `docker ps` shows only `gex-pg-forward` (socat) and `files-postgres-1`
(postgis) — no container is built from that tree — and `docker/push.sh` contains no
compose reference.

**RESOLVED 2026-08-10 — deleted on Jim's instruction.** `files/docker/gex-platform-enhanced/`
was removed; `files/docker/` itself was kept (it holds the live production assets
`Dockerfile.*.prod`, `nginx.conf`, `push.sh` used by the Docker Hub flow). The guardrail
file now passes 13/13 and the full suite is green.

Before deleting, every non-code asset in the stale tree was confirmed to have a live
counterpart, and all 21 of its markdown docs were content-compared. Exactly one differed
— `postgres-migration-plan.md`, 3,370 bytes stale against 59,229 live, i.e. the live copy
is a superset. Nothing was lost.

Because neither `files/` nor `files/docker/` is a git repository, deletion was
unrecoverable, so the non-regenerable content (excluding venv/node_modules/caches — 319M
of the 356M was a virtualenv) was archived first to:

```
files/_retired/docker-gex-platform-enhanced-20260810.tar.gz   (4.3M, 806 entries)
```

`_retired/` is in the guardrail's `skip_parts`, so the archived compose files inside it
cannot re-trigger the test. Delete the archive once a release has passed.

**Guardrails to be aware of when editing:**
- SQLite ratchet, `BASELINE = 97`, currently at 68 — may only decrease.
- One-`.db`-file guardrail — flips to *no*-`.db`-file at the end of slice 7.
- `test_the_dead_tables_are_quarantined_not_dropped` — asserts both directions: none
  dropped, none revived under the original name. **Delete this test in the same commit
  that drops the quarantined tables.**
- `test_the_two_specific_energy_fields_are_different_quantities` — see §8/§9.
- Several guardrails deliberately match *definition lines* or strip docstrings rather
  than matching prose, because earlier versions passed on explanatory comments. Preserve
  that when editing them.

---

## 8. Known unresolved defects

1. **`contracts` exists in neither store.** `contracts_sqlite.py` queries it at lines
   150, 200, 258. Verified absent from both SQLite and PostgreSQL.
   `/api/v1/contracts/summary` returns 500. **This needs CREATE, not DROP** — it is
   routed and called, unlike the 12 quarantined tables.
2. **`_log_event` hash defect.** `development_packages.py:616` and `spend_wave.py:240`
   hash a typed object but store `str(new_val)`. The stored row therefore cannot
   reproduce its own digest. **7 of 18 existing package events are permanently
   unverifiable** — a fix helps future events only, and cannot repair history.
   (`projects_store.py:178` uses `str()` similarly but writes an unhashed audit row, so
   it does not share this defect.)
3. **No `app.current_user_id` GUC.** Keeps `permission_user_overrides` and
   `user_signing_keys` admin-only. Documented in migration 042 and asserted by a test so
   it stays discoverable.
4. **Both stores are live and diverging, and tests that compare them must account for
   it.** `finance_entitlements`: SQLite 1128 rows, PostgreSQL 838, watermark records 744
   actually copied. `test_a_sampled_entitlement_matches_column_for_column` sampled "first
   by `entitlement_id`" and demanded the row exist in PostgreSQL; on 2026-08-10 it picked
   a row created after the copy and reported drift where there was none. It now samples
   from the recorded `copied_keys` — the only population where fidelity can hold. **Any
   new cross-store comparison must do the same**; identical key sets is not a property
   that can hold while SQLite is still the active backend.

4. ~~PostgreSQL tests do not fail uniformly when the database is unreachable.~~
   **FIXED 2026-08-10.** See §7 — the suite now skips cleanly through an outage.

   Still open, related and operational: `files-postgres-1` exits (255) on its own —
   it did so twice during this work. Its healthcheck logs
   `FATAL: database "gex_user" does not exist` continuously because the probe omits the
   dbname and defaults to the role name. That is noise rather than the cause, but it
   buries the real cause. Worth fixing the compose healthcheck to pass `-d gex_platform`,
   and worth finding out why the container exits.
5. **`SECRET_KEY` is the dev default**, and `GEX_JWT_SECRET` on the TEA engine falls back
   to the same. Fine locally; blocking for any deployed environment.
6. **Nine frontend lib files still call Supabase `.from()` directly** —
   `dealClient.ts` (3: `equation_engine_runs`, `v_latest_engine_run`), `iterations.ts`
   (8), `backendClient.ts` (2), `projectAccess.ts` (2), `siteInfrastructure.ts` (2),
   `customLibrary.ts` (2), `equipmentCatalog.ts` (1), `plantStore.ts` (1),
   `seedInitialCanvas.ts` (1). Under decision §5.1 these must move behind backend
   endpoints. **`dealClient.ts` was not migrated** — the decision was taken but the work
   was not done. `projectAccess.ts` is the highest-risk of these, since it is an access
   path.

---

## 9. Rejected and superseded — do not reintroduce

- **Patching `dealClient.ts` by wiring it to Supabase PostgREST — REJECTED.** Replace
  with backend deal endpoints. Recorded here because it is the obvious quick fix and it
  is the wrong one.
- **Leaving Supabase — REJECTED.** See §5.10.
- **Trusting a self-registered account — REJECTED.** See §5.2.
- **Voiding a `SETTLED` token, or any recovery path out of `RETIRED` — REJECTED.**
  Error correction is `ANNULLED`, terminal and non-claimable.
- **Relying on `UNIQUE(previous_hash)` alone to prevent chain forks — SUPERSEDED.** SQL
  UNIQUE permits many NULLs, so two events could both claim to be first; and rejection
  loses audit events. The advisory lock is the mechanism.
- **The empty-string GUC bypass in the 020 policies — REMOVED in 032.** An unset
  `app.current_company_id` must not grant visibility.
- **DROPping the 12 dead tables — SUPERSEDED by quarantine.** Reversible, free (they
  were empty), and proves absence of callers over a release cycle rather than by grep.
- **Merging the two "specific energy" fields — REJECTED, and actively guarded.**
  `fuel_catalog.specific_energy_value` is the fuel's own LHV in kWh/kg and *varies*
  (H2 33.3 · NH3 5.2 · e-methanol 5.5 · SAF 11.9).
  `FUEL_DEFAULTS[...]["specific_energy_kwh_per_kg_h2"]` is the *electrolyser's*
  consumption and is *constant* at 50.0. They read alike and are different physics.
  Merging them corrupts either every fuel's energy content or the production formula.
- **Copying a WAL-mode SQLite database by copying the `.db` file — DOES NOT WORK.**

---

## 10. Current task

Slice 6b-7 (quarantine the 12 dead tables) is **complete and verified**. The
SQLite→PostgreSQL migration is finished through 6b: every live table exists in
PostgreSQL, 89 under forced RLS, watermarks recorded for 53 copied tables.

**No slice is in flight.** All eight backend switches remain on SQLite by design. The
next step is slice 7 (flip and retire), which is blocked on one input from Jim.

---

## 11. Recommended next five actions

1. **Fix `contracts` (unblocked, ~1 hour).** A live 500. Create the table in PostgreSQL
   via a new migration and in SQLite, derived from the columns
   `contracts_sqlite.py` actually selects. Do not drop the route.

2. **Replace `dealClient.ts`'s Supabase path with backend endpoints (unblocked).** The
   decision is made and the code still contradicts it. Add
   `GET/POST /api/v1/deals/engine-runs` (and the `v_latest_engine_run` equivalent) behind
   ABAC, then delete the three `.from()` calls. Do `projectAccess.ts` next — it is an
   access path, so a direct client call is a policy bypass, not just an inconsistency.

3. **Obtain the Supabase service-role `DATABASE_URL` and run slice 7.** Set it
   server-side in `backend/.env` — Jim sets it; it must never be the anon key and must
   not be pasted into a chat or committed. Then: re-run every migrator against the target
   (all idempotent, all record watermarks), verify watermark counts, and flip the eight
   switches **one at a time**, running the suite between each. `AUTH_DB_BACKEND` last —
   it is the one that can lock everyone out.

4. ~~Move the runtime connection to `gex_app`.~~ **DONE 2026-08-10** (migration 045).
   Three tests did depend on superuser visibility, as expected — whole-store fidelity
   comparisons that read through the shim with no caller bound. They now declare
   `as_platform_admin()` explicitly, the same way the seven production bootstrap sites do.

5. **Fix the `_log_event` hash and retire SQLite.** Hash exactly what is stored in
   `development_packages.py` and `spend_wave.py`; record in the migration that the 7
   historical events remain unverifiable. Then ratchet the SQLite baseline to 0, remove
   `SQLITE_DB_PATH`, drop the quarantined tables, and delete
   `test_the_dead_tables_are_quarantined_not_dropped` in that same commit.

---

## 12. Assumptions requiring Jim's decision

1. **The Supabase target and its credential.** Which project, and the service-role
   connection string. Slice 7 cannot start without it and I must not handle it.
2. ~~`files/docker/` disposition.~~ **RESOLVED 2026-08-10** — deleted on Jim's
   instruction; archived to `files/_retired/`. See §7. No decision outstanding.
3. **Whether `app.current_user_id` is worth introducing.** Without it, two governance
   tables stay admin-only and users cannot read their own permission overrides. It is a
   real product limitation, not just a schema one.
4. **What `contracts` should contain.** I can infer columns from the queries, but not
   whether it should be seeded, nor whether the route was ever meant to ship.
5. **How far the "no direct Supabase from the frontend" rule reaches.** Deal data is
   settled. Whether it also covers canvas/iteration state (`iterations.ts`, 8 calls;
   `seedInitialCanvas.ts`; `plantStore.ts`) is a scope call — those are editor state, not
   commercial records, and routing them through the backend is real work.
6. **Whether the seed accounts should be re-vetted.** Every account that exists — all 17
   in `auth_users` — is `ACTIVE` via `SEED_GRANDFATHERED`, with no telephone verification
   and no signed agreement. Under §5.2 not one of them would qualify today. The vetting
   pipeline has therefore never been exercised end-to-end on a real applicant.
