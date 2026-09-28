# GEX platform — working notes

Everything here was verified against the tree or the live database on
**2026-09-24**. Where a number is stated it was measured, not remembered. If
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

**`gex_pf_engine` and `deal_engine` are DIFFERENT services, not copies.**
`../gex_pf_engine` (sibling) is the Gabillon project-finance engine serving
`:8001` — cfads.py, waterfall.py, debt/sculpting.py. `./deal_engine` (renamed
2026-09-09 from `gex_pf_engine`, which is why the confusion existed) computes
deals — pre-COD, phases, ratios, COD test, TEA adapter. **They share not one
module name.** `deal_engine` has no launch.json entry and no caller: dormant,
not dead. Do not delete either as "the duplicate".

### Starting the services

Frontend, backend and TEA engine have `.claude/launch.json` entries — start those via the
Browser pane, not `Bash`.

**The PF engine has NO launch.json entry.** It is a sibling repo with its own virtualenv
and this is the agreed sequence — do not substitute another venv, port or path:

```bash
cd files/gex_pf_engine/backend
source ../micro_service/bin/activate     # gex_pf_engine/micro_service, not a repo venv
uvicorn pf_engine.main:app --reload --port 8001
```

**The package moved 2026-09-09: `app` → `pf_engine`**, so the command is
`pf_engine.main:app`, not `app.main:app`. Both repos previously had a top-level
package called `app`; whichever imported first won and the other's submodules
became unreachable. The sibling was renamed because it is 19 files against the
platform's 152. Nothing else about the sequence changed.

`micro_service` lives inside `gex_pf_engine/`, is excluded from `sync-to-docker.sh`, and is
the only interpreter this service runs under. If a future note says "run servers via
launch.json", it does not apply here — there is nothing there to run.

---

## Database — two credentials, never one

```
DATABASE_URL          gex_app    runtime.  No SUPERUSER, no BYPASSRLS,
                                 no CREATE on schema public. RLS APPLIES.
ALEMBIC_DATABASE_URL  gex_user   DDL and migrations only.
```

Migration 045 made this real. Before it, the runtime connected as a superuser
and every RLS policy was decorative. Measured on a live `gex_app` connection:
`projects` returns 14 rows as `PLATFORM_ADMIN`, **4** as tenant `etfuels_sa`,
**0** with no tenant context. (Naming the tenant matters — the number is that
tenant's, not a constant.)

**Do not collapse these back into one variable.** DDL is not subject to RLS, so
a migration running with the runtime credential — or a runtime holding DDL
rights — turns any injection into a full read of every tenant. Pointing
`DATABASE_URL` at a superuser to make a permissions error go away will be caught
by `tests/test_gex_app_runtime_role.py`, which asserts against whatever
`DATABASE_URL` is actually configured.

### Traps that cost real time

- **`ALEMBIC_DATABASE_URL` must be EXPORTED**, not merely present in `.env`.
  pydantic's `env_file` populates `settings`, *not* `os.environ`, and Alembic
  reads `os.getenv`. `alembic.ini` no longer carries a working fallback: its
  `sqlalchemy.url` is the sentinel `EXPORT_ALEMBIC_DATABASE_URL_FIRST://` so an
  unexported run aborts. It used to hold a REAL dsn on port **5432** — a
  different, non-GEX PostgreSQL that is usually listening — so an unexported
  migration did not fail, it silently migrated the wrong database.
- **`DATABASE_URL` must be exported too, for the TEST SUITE.** Same mechanism,
  different victim: ~20 tests gate on `os.environ["DATABASE_URL"]`, so running
  the documented pytest line with only `.env` present silently skips **125**
  tests — including the RLS and tenant-isolation ones — and still reports green.
  Export both before measuring anything.
- **Alembic uses branches.** `030` is an independent root labelled `auth_slice`.
  Upgrade with `alembic upgrade auth_slice@head`, never bare `head`.
- **`Settings` forbids extra inputs.** A new environment variable must be
  declared in `app/core/config.py` or the app refuses to start.
- **WAL-mode SQLite.** Copying only the `.db` file does not capture state; the
  `-wal` sidecar carries changes forward and silently reverts part of a restore.
  Copy/remove `-wal` and `-shm` too, or use `VACUUM INTO`.

### Migration state

PostgreSQL holds **120** tables in schema `public` (incl. `alembic_version`) at head
**058**, **113** under FORCED RLS — measured 2026-09-28 by `pg_class relkind='r'`. 058
added the two commitment-card tables (rules 4.0.0; `docs/CLAUDE_HANDOFF.md` §8 item 34).
(This file once said 119 at 053 by another method. Re-measure rather than reconcile.)

**Docker Desktop restarts leave PostgreSQL stopped.** `files-postgres-1` has restart
policy `no`; after a Docker restart the forwarder on 55432 is up but refuses queries.
`docker start files-postgres-1` (happened 2026-09-14 and 2026-09-28, nothing lost).

**New tables inherit full DML for `gex_app`.** Migration 031 set DEFAULT PRIVILEGES, so a
`GRANT SELECT` on a new table restricts nothing — only `REVOKE` does. 056 found the
"append-only" `evidence_events` updatable and deletable by the runtime since 034.

**All evidence rows before 2026-09-26 were invented** — the 125 `demo_seed` rows and the two
under Anna Keller's and Thierry Groell's names alike. They are archived in
`bankability_evidence_archive`; the live table holds 85 open requests assigned to real
accounts (`scripts/convert_invented_evidence.py`). Do not restore them, and do not treat
any archived row as a client submission.

**The switches are done — the cutover is not.** All **ten** backend switches now
read `postgres`: `AUTH_`, `CAPITAL_`, `DOMAIN_`, `ENTITLEMENT_`, `EVENTSTORE_`,
`EVIDENCE_`, `FUELREF_`, `GOVERNANCE_`, `MARKET_`, `WORKSPACE_DB_BACKEND`. (This
file previously said all eight read `sqlite`; there are ten, and none do.)

**One module is switch-blind; the real defect is elsewhere.** An earlier version
of this file named four — `ecosystem_store`, `ot_boundary`, `adversarial_reviews`,
`canonical_ledger` — from a `grep` for `sqlite3.connect` that did not check
whether the call sites were guarded. Three of the four were already correct
(verified by AST 2026-09-24):

- `ot_boundary` and `adversarial_reviews` both open with
  `if domain_is_postgres(): return domain_connection()` and both `init_*_db()`
  return early on postgres because **044** owns their tables. Their remaining
  `sqlite3.connect` lines are the SQLite *branch* of that conditional.
- `canonical_ledger` takes its SQLite path only under `if sub == "sqlite-dev"`,
  and `substrate()` *refuses* that waiver when `domain_is_postgres()` — it was
  written to prevent exactly this split-brain. It currently resolves to
  `unconfigured` (no `CANONICAL_DATABASE_URL`), so it raises `SubstrateError`
  rather than touching SQLite at all. Note that means `routes_tea.py` paths
  through it fail closed.
- `ecosystem_store._conn()` **is** unguarded. Its `init_db()` correctly refuses
  to create tables on postgres ("refusing to create them unprotected") but its
  data path always opens SQLite. Its switch is read with `os.getenv
  ("ECOSYSTEM_DB_BACKEND")` and is **not** declared in `config.py`, so it is not
  one of the ten. Its two tables exist in neither store, so it is dormant.

**The defect that matters is unguarded READS.** 8 modules read **18**
PostgreSQL-owned tables out of SQLite with no `*_is_postgres()` check:

    api/v1/adjacency.py               adjacency_cache, evidence_ledger, projects
    api/v1/lineage.py                 capacities, carbon_attribution_events,
                                      development_packages, evidence_ledger, offers,
                                      projects, sovereign_instruments, tokens
    api/v1/next_best_action.py        drawdown_schedules, model_base_case, pathway_claims
    api/v1/routes_project_activity.py bankability_evidence, bankability_snapshots
    api/v1/routes_project_truth.py    capacities
    api/v1/marketplace_analytics.py   offers
    api/v1/contracts_sqlite.py        matches
    core/ecosystem_store.py           (tables in neither store)

`test_no_module_opens_sqlite_without_consulting_a_backend_switch` does **not**
catch these, and that is deliberate, not a false green: it is scoped to modules
that *write* a PostgreSQL-owned table, and it is satisfied module-wide by any one
`*_is_postgres()` call. Reads were out of scope when it was written for the
write-divergence defect. Do not "fix" it by widening it blindly — several of
these tables are absent from SQLite, so those reads already fail rather than lie.

**The tenant-isolation hole — FIXED 2026-09-24.**
`GET /api/v1/project-activity/{project_id}` (`main.py:759`) takes `project_id`
from the path and performs no project-level authorization in the handler, so the
database filter *is* the access control. It read `bankability_evidence` and
`bankability_snapshots` from SQLite, which has no RLS. The SQLite copy held **127**
rows across **5** projects owned by **three** tenants — `hamburgone_com`,
`etfuels_sa`, `rheinwerk_industries_ag` — all readable by any authenticated caller
who could guess a project id.

Both readers now go through `_evidence_store()` -> `evidence_connection()` (034
owns those tables). Measured against `proj_hamburgone_emethanol` (49 rows, owner
`hamburgone_com`):

    before, any caller, no tenant context  49 rows readable
    after,  as etfuels_sa                  BLOCKED
    after,  as rheinwerk_industries_ag     BLOCKED
    after,  as hamburgone_com (owner)      allowed
    after,  as PLATFORM_ADMIN              allowed, and logged by _tenant_context
    after,  no tenant bound                BLOCKED (deny sentinel)

Two portability points the port had to handle, and the next one will too:
`sqlite_master` does not exist on PostgreSQL (the `_table_exists` probe is now
SQLite-only, since 034 owns the tables there), and `ORDER BY datetime(updated_at)`
is a SQLite function that `_to_pg()` does **not** rewrite — it only handles
`datetime('now')`. Every stored value is ISO-8601 and text ordering was verified
byte-identical before the `datetime()` wrapper was dropped. Check that before
copying this pattern; do not assume it.

**Still unfixed — 7 modules, same shape:** `adjacency`, `lineage`,
`next_best_action`, `routes_project_truth`, `marketplace_analytics`,
`contracts_sqlite`, `ecosystem_store`. Of these, `lineage` reads eight PG-owned
tables and is the largest. Note `projects` is ABSENT from the SQLite file, so
`adjacency` and `lineage` reading `FROM projects` fail rather than lie — they are
broken, not leaking.

### Where the bytes actually are

The database is **not a file you can copy**. It is a Docker named volume:

    container   files-postgres-1  (postgis/postgis:15-3.3)
    defined in  files/gex-demo-compose.yml   <- NOT gex-platform-enhanced/docker-compose.yml
    volume      files_postgres_data
    reached at  localhost:55432 -> container gex-pg-forward -> 5432

`docker inspect` reports the mount as `/var/lib/docker/volumes/.../_data`, but
**that path does not exist on macOS** — it is inside the Docker Desktop VM. On
the host the bytes live in one blob,
`~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw`. So back up
with `pg_dump`, never `cp`; `docker volume rm files_postgres_data` or a Docker
Desktop factory reset destroys the database outright.

---

## Tenant isolation — how the caller reaches the database

Two paths, one identity. `app/core/request_tenant.py` is the single derivation;
`ABACMiddleware` binds a request-scoped `ContextVar` and unbinds it in a
`finally`.

- `Depends(get_db)` — SQLAlchemy, **115** sites (was ~109 on 2026-08-10)
- `*_connection()` — the shim in `app/core/db_backend.py`, **~121** call sites
  across **48** files, excluding the shim's own definitions (was ~64)

Shim resolution is **explicit argument → bound caller → deny sentinel**. The
default is `NO_TENANT_CONTEXT`, which matches no tenant-scoped policy, so code
with no caller reveals nothing. It used to default to `PLATFORM_ADMIN` and no
call site overrode it.

**`PLATFORM_ADMIN` disables tenant isolation for a whole connection.** Pass it
only for a genuine bootstrap — reading the rules you are using to decide access.
**Nine** call sites do, not seven, and the composition has changed — measured
2026-09-24 by `_connection\([^)]*PLATFORM_ADMIN`:

    core/entitlements.py      core/permission_engine.py   core/sod.py
    core/css.py               core/event_store.py         core/wae.py
    core/drpl.py              core/break_glass.py         core/open_interest.py

Each says why, and every use is logged by `_tenant_context`.
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

`auth_users` now holds **20** rows, all `ACTIVE`, and the marker no longer
accounts for all of them (measured 2026-09-24):

    17  activated_by = 'SEED_GRANDFATHERED'   predate vetting
     2  activated_by = 'MANUAL_ADMIN_GRANT'
     1  activated_by = (none)                 <- u_admin

Do not backfill the grandfathered rows' NULL phone/agreement columns; that marker
is how you find them.

**`u_admin` carries no marker at all** — `activated_by`, `activated_at`,
`phone_verified_at` and `agreement_signed_at` are all empty, so it satisfies none
of the four activation requirements above and is invisible to the
`SEED_GRANDFATHERED` search that is documented as the way to find unvetted rows.
It is the admin account. Decide whether to grandfather it explicitly or take it
through activation; leaving it unattributed means the separation-of-duties record
has a hole exactly where it matters most.

Deal and product data belongs **behind the backend**, not the frontend's
Supabase `.from()`. Do not "fix" a frontend data path by wiring it to PostgREST.

---

## Tests

```bash
cd backend && ./venv/bin/python -m pytest tests/ -q
```

Export `DATABASE_URL` and `ALEMBIC_DATABASE_URL` FIRST — see the traps above.
Without them the same command reports **593 pass, 140 skip**, having silently
skipped the entire PostgreSQL path while looking green.

**844 pass, 17 skip** against PostgreSQL as `gex_app` with both exported, zero
failures — measured 2026-09-28. (Counts move — this tree has more than one session
writing to it; re-measure rather than trust a number you did not just run.)

`isolated_store` is **module-scoped**: every test in a file shares one throwaway store.
A new test must not assume an empty table or a key no earlier test has touched —
run it alone *and* in its file before believing it.

Three conditions, all measured 2026-09-24. The middle one is the trap:

    exports + database up        716 pass,  17 skip,  0 fail
    NO exports + database up     591 pass, 142 skip,  0 fail   <- 125 skipped
    exports + database absent    592 pass, 141 skip,  0 fail

**Zero failures with the database absent — restored.** It held on 2026-08-10,
had broken by 2026-09-24, and is fixed. The two offenders were in
`tests/test_open_interest_routes.py`:

    test_confidentiality_identity_is_not_the_tenancy_identity
    test_the_admin_flag_is_carried_but_still_does_not_bypass_confidentiality

They reach PostgreSQL *indirectly through the app* —
`roi.viewer_from_request` -> `_profile_columns` -> `psycopg2.connect` — and the
file called `requires_pg()` zero times, so an unreachable database FAILED them.
The cost was never the red: it was that two *confidentiality* tests read as "the
admin bypasses confidentiality" when the only real problem was a stopped
database. Both now call `requires_pg()`.

Note what that guard gates on: the `DATABASE_URL` **environment variable**, not
reachability. So these two also skip when the database is up but the variable is
unexported — that is the 593 -> 591 difference in the middle row above.
`requires_pg()` buys the absent-database invariant at the price of needing the
export. Export it.

The other two `viewer_from_request` tests in that file need no guard: they pass
payloads with no `company_id`, and `viewer_from_request` returns
`ViewerProfile(company_id=None)` before it reaches `_profile_columns`.

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
- **A guardrail can be killed by the fix it was written to check.**
  `test_rls_isolation.py::test_platform_admin_sees_everything_and_a_tenant_sees_less`
  gated on `SELECT count(*) FROM projects` taken on the fixture connection. When
  045 repointed `DATABASE_URL` from superuser to `gex_app`, that count became 0
  via the deny sentinel, so the test skipped unconditionally — "no projects
  seeded" against 14 projects — from 045 until 2026-09-24. RLS working correctly
  was what disabled the test that checks RLS. Fixed to gate on PLATFORM_ADMIN
  visibility, with the "sees EVERY project" assertion taken against a BYPASSRLS
  count via `pg_support.pg_bypassrls_connect()`. **A skip is not a pass.** Read
  skip reasons with `-rs` before believing a green run.

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
