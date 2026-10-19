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

**2026-10-13: the database was RESTORED FROM DUMP after a second loss.** By 09:45 UTC on
13 Oct, both `files-postgres-1` and the `files_postgres_data` volume no longer existed —
only `gex-pg-forward` survived, so :55432 accepted connections and then dropped them
("server closed the connection unexpectedly"). What removed them is not recorded. It was
restored from `db_backups/daily/gex_platform_2026-10-12_1236.dump`; **writes after 12 Oct
12:36 local are lost.** This time no migrations and no copiers ran — the dump carries schema
at 059 and every row. See `docs/CLAUDE_HANDOFF.md` §8 item 43 and the restore steps under
*Backups* below.
**When the container is MISSING, `docker start` cannot fix it.** Check `docker ps -a` and
`docker volume ls` first. If the volume is gone, restore from the newest dump. Do not run the
Alembic rebuild drill.

**2026-09-30: the database was REBUILT after the 28 Sep reset.** It was empty from
28 Sep 16:14 (compose project `files` recreated on a new `files_postgres_data` volume,
fresh `initdb`) until 30 Sep. `docs/CLAUDE_HANDOFF.md` §8 item 38 records the rebuild and
what it cost. Schema is back to the pre-reset measurement exactly; **103 of 114** tables
match the 23 Sep baseline (`backend/db_backups/pg_after_kyc.json`) row for row.

**A Time Machine restore of the volume was never possible.** Item 38 used to offer one.
`Docker.raw` is **excluded** from Time Machine — Docker Desktop sets that exclusion itself —
so no backup of the volume has ever existed on this machine. Verify with
`tmutil isexcluded ~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw`
before anyone proposes that route again. **`pg_dump` is the only backup that works here.**

**2026-10-19: head is 061** (branch `reference-data-registry`). 060 added
`screen_access_rules`; 061 adds `reference_parameter` and `reference_version`, the
reference data registry (`app/core/reference_registry.py`, `/api/v1/reference`). Measured
after 061 by `pg_class relkind='r'`: **123** tables, **116** FORCED. 061's value columns are
immutable for every role (trigger); `gex_app` holds SELECT, INSERT and column-level UPDATE
on the lifecycle columns only. Seed rows carry `proposed_by = 'MIGRATION_061'`; four are
`proposed`, not approved, because their source could not be confirmed on 10-19.

PostgreSQL holds **120** tables in schema `public` (incl. `alembic_version`) at head
**059**, **113** under FORCED RLS — measured 2026-09-28 before the reset and again
2026-09-30 after the rebuild, by `pg_class relkind='r'`; both runs agree. 058
added the two commitment-card tables (rules 4.0.0; `docs/CLAUDE_HANDOFF.md` §8 item 34).
059 adds no table — it only restores privileges, so the count is unchanged.
(This file once said 119 at 053 by another method. Re-measure rather than reconcile.)

**Rebuilding is a known drill — it has now been done twice** (2026-09-08 and 2026-09-30).
The order matters and two steps are easy to get wrong:

1. `scripts/setup_postgres_rls.sql` runs **FIRST, before Alembic, and ONCE** — 24
   migrations reference `gex_app`. It creates the role with its own default password; if
   `.env` carries a different one (it did), set the `.env` password or the runtime still
   cannot log in and the failure reads as "password authentication failed".
   **Do not re-run it after Alembic.** Its own comment used to invite that, and doing so
   on 30 Sep silently re-granted UPDATE on three append-only audit tables, undoing
   migrations 056 and 058 — see the Tests section. The script is now safe to re-run
   (it grants only to tables holding no `gex_app` privilege at all), but the migrations,
   not this script, are the authority on privileges. If you re-run it, re-check grants:

       docker exec files-postgres-1 psql -U gex_user -d gex_platform -c "SELECT table_name, \
         string_agg(privilege_type, ', ' ORDER BY privilege_type) FROM \
         information_schema.role_table_grants WHERE grantee='gex_app' AND table_name IN \
         ('evidence_events','bankability_evidence_archive','commitment_terms_events') \
         GROUP BY 1;"

   Correct answer: archive `SELECT`, the other two `INSERT, SELECT`. Any `UPDATE` there
   means the append-only guarantee is off again.
2. `alembic upgrade auth_slice@head`, **never `heads`**. There are two roots: `auth_slice`
   (030→059) and a legacy `001→011` whose tables 042/044 already own. Upgrading `011`
   fails on `relation "matrix_rooms" already exists` — that is correct, not a problem.
   `alembic_version` holds **059 alone**. `cutover_postgres.py:116` corroborates the
   branch point in a comment ("auth_slice@head, never 'heads'") — it names no revision
   number, so it does not go stale as the head moves.
3. `scripts/cutover_postgres.py --execute` runs 8 copiers. It does **not** run
   `migrate_directory_slice.py` or `migrate_workspace_slice.py` — run those separately or
   `directory_roles`, `canvas_blobs` and `user_plants` stay at 0.
4. **Do not override `DATABASE_URL` for `migrate_workspace_slice.py`.** It copies with
   `ALEMBIC_DATABASE_URL` but verifies with `DATABASE_URL`, which must be the `gex_app`
   runtime role — 050's policies have no admin clause. Verified as `gex_user` it reports
   4× the rows (500→2000: every owner seeing all 500, summed over 4 owners) and claims the
   owner policy does nothing. Both are artifacts of the wrong verify role, not bad data.
5. `scripts/restore_registry_projects.py --execute` returns 5 projects + 2 tenants from
   `frontend/src/data/customerProjects.ts`, then
   `scripts/restore_retired_collision_projects.py --execute` returns the last 2 from
   SQLite's `projects_retired_pg_collision_20260807`. 7 (migration 020) + 5 + 2 = **14**.

**Docker Desktop restarts leave PostgreSQL stopped.** `files-postgres-1` has restart
policy `no`; after a Docker restart the forwarder on 55432 is up but refuses queries.
`docker start files-postgres-1` (happened 2026-09-14 and 2026-09-28, nothing lost).

**New tables inherit full DML for `gex_app`.** Migration 031 set DEFAULT PRIVILEGES, so a
`GRANT SELECT` on a new table restricts nothing — only `REVOKE` does. 056 found the
"append-only" `evidence_events` updatable and deletable by the runtime since 034.

**One project in the database is a TEST fixture, and 32 evidence rows with it.**
`proj_TEST_gates_reference` ("TEST — Gates Comprehension Reference (synthetic)", owner
`hamburgone_com`) was loaded 2026-10-02 on JML's instruction for the first-use comprehension test
(`docs/usability/`). That is why `projects` holds **15** and `bankability_evidence` **117** — the
85 real open requests are untouched. Every fixture row carries
`submitted_by = 'TEST_FIXTURE_COMPREHENSION'`; that marker is how you find them, and
`backend/scripts/load_comprehension_test_project.py --remove --execute` deletes the lot by project
id. The item list is derived from the running engine, so the fixture cannot drift from the rules;
`--verify` re-checks it against the published answer key, and caught a prefix bug the first time
it ran (`"G10"[:2] == "G1"` had pulled G10 and G11 into the fixture). The rows exist in
PostgreSQL only, which is the single tolerated break in SQLite↔PostgreSQL evidence parity:
`test_evidence_slice.py` excludes the marker and a second test pins the exception to projects
named `proj_TEST_`. Both were negative-verified. **Do not treat a fixture row as a client
submission**, and do not copy them into SQLite to "restore parity".

**A second TEST fixture: FortaVerde (Pecém), loaded 2026-10-12** by
`backend/scripts/load_fortaverde_test_project.py` from `fortaverde_knowledge_v2.json` (route
chosen by JML 2026-10-09). It adds project `proj_TEST_fortaverde_pecem` (tenant
`test_fortaverde`) and two stand-in accounts, `usr_test_fv_p1` and `usr_test_fv_p2`, and
**no** evidence rows. That brings `projects` to **16**; `bankability_evidence` stays at
**117**. `usr_test_fv_p1` is ACTIVE on purpose (`--activate`, JML 2026-10-12). It bypasses
vetting and its row records that with `activated_by = 'TEST_FIXTURE_FORTAVERDE'`.
`--remove --execute` deletes the fixture. Measured in the 13 Oct restore.

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

### Backups — where they land and how to restore one

`files/backup_postgres.sh` is the backup. It dumps with `pg_dump -Fc` out of the
container, **verifies the dump, and only then** installs it. Run it by hand any
time; it is also the thing the scheduler runs.

    files/db_backups/daily/    gex_platform_<YYYY-mm-dd_HHMM>.dump   keep 7
    files/db_backups/weekly/   gex_platform_<ISOweek>_<stamp>.dump   keep 4
    files/db_backups/backup.log

Weekly is a **hardlink** to the first good daily of each ISO week, so the four
weekly copies cost no extra disk. A dump is ~1.0 MB, so the whole rotation is
~8 MB. The pre-existing loose dumps at the top of `db_backups/` are untouched.

**Verification is two steps, and the second is the one that counts.**
`pg_restore -l` reads only the archive TOC. Measured 2026-09-30 against a
known-good dump: a copy missing its **last 500 bytes**, and a copy with a
**byte-flip at 60%**, BOTH passed `pg_restore -l` with exit 0. Only a full read
(`pg_restore -f /dev/null`, which decompresses every data block) caught them. So
the script does both. Do not "simplify" it back to `-l` alone.

A dump is staged in `db_backups/.staging/` and moved into `daily/` **only after
it verifies**, so a failed run leaves no file that could be mistaken for a
backup. Verify any existing dump without changing anything:

```bash
files/backup_postgres.sh --verify files/db_backups/daily/<file>.dump
```

**It dumps as `gex_user`, and it must.** 113 of 120 public tables carry FORCED
RLS, which applies even to the table owner; `gex_user` is SUPERUSER + BYPASSRLS
so it reads every tenant's rows. Dumping as `gex_app` would silently produce a
partial database. This does **not** change `DATABASE_URL`, which stays `gex_app`.

**Failures are loud and distinguishable** — never a 0-byte file and exit 0:

    10 docker CLI not found      20 pg_dump failed
    11 Docker Desktop not up     21 empty / not a PGDMP archive
    12 container missing         22 TOC unreadable
    13 container STOPPED  <-     23 too few TABLE DATA entries
    14 up but refuses queries    24 truncated or corrupt (full read failed)
                                 30 could not install   40 another run in progress

13 is the recurring one: `files-postgres-1` has restart policy `no`, so a Docker
Desktop restart leaves it stopped while the forwarder on :55432 still accepts
connections and refuses queries. Fix with `docker start files-postgres-1`.

**To restore.** Restore into a THROWAWAY database first and compare — never
straight over `gex_platform`:

```bash
docker exec files-postgres-1 psql -U gex_user -d postgres -c "CREATE DATABASE gex_restore_test;"
docker exec -i files-postgres-1 pg_restore -U gex_user -d gex_restore_test --no-owner < files/db_backups/daily/<file>.dump
```

Verified end to end 2026-09-30: restored clean (exit 0, zero errors), **120 of
120 tables, 19,984 rows**. The only two tables that differed from live —
`auth_login_history` and `refresh_tokens`, +3 rows each — were writes that
happened *after* the snapshot (live rows timestamped 08:17–08:18 UTC against an
08:16 UTC dump). That is a correct point-in-time snapshot, not data loss; expect
the same shape when you compare.

To promote a restore over the live database, drop and recreate `gex_platform`
itself — `pg_restore -c` into a live database leaves RLS policies and grants in
a half-replaced state. Re-run `scripts/setup_postgres_rls.sql` **before** the
restore if the roles are gone, and do not run migrations as part of a restore:
the dump already carries schema at its own head.

**Done for real 2026-10-13, after the container and volume were deleted** (handoff §8
item 43). The steps were:

1. `docker compose -p files -f files/gex-demo-compose.yml up -d postgres`. Use project
   `files` because the forwarder dials `files-postgres-1` on `files_gex_net`.
2. `setup_postgres_rls.sql` into the empty `gex_platform`. It creates only the roles. Then
   `ALTER ROLE gex_app PASSWORD` to match `.env`.
3. Restore into `gex_restore_test` and check it: table count, FORCED RLS count,
   `alembic_version`, and the append-only grants query above.
4. Promote it: `DROP DATABASE gex_platform; ALTER DATABASE gex_restore_test RENAME TO
   gex_platform;`. This skips a second restore.
5. **Re-apply the database-level settings. A `-Fc` dump does not carry them.**
   `GRANT CONNECT ON DATABASE gex_platform TO gex_app, gex_admin;` and
   `ALTER DATABASE gex_platform SET app.current_company_id = 'GUEST';`. Without the first,
   the runtime cannot connect. Without the second, the RLS default changes.
6. Take a fresh backup straight away.

Result: 120 tables, 113 FORCED, head 059, 20,080 rows. `gex_app` connects through :55432
as a non-superuser, and `projects` returns 0 with no tenant context.

Note: `backup_postgres.sh --verify` itself needs the container running. It runs
`pg_restore` inside `files-postgres-1`, so with the container gone it exits 13. You cannot
pre-check a dump before step 1.

**Scheduling.** `files/com.gex.postgres-backup.plist` is a launchd agent, daily
at 12:30 local. Note it is **not installed unless someone ran the two commands
in it** — check with `launchctl list | grep gex`. Install / remove:

```bash
cp files/com.gex.postgres-backup.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.gex.postgres-backup.plist
launchctl unload ~/Library/LaunchAgents/com.gex.postgres-backup.plist && rm ~/Library/LaunchAgents/com.gex.postgres-backup.plist
```

Three things about this job were learned the hard way on 2026-09-30, all
verified by running it:

- launchd gives jobs `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, which does **not**
  contain `docker` — `/usr/local/bin/docker` is a symlink into Docker.app. The
  script resolves docker by absolute path itself, which is why it works under
  launchd. Keep that if you rewrite it.
- **`ProcessType` must stay `Standard`.** It was first written as `Background`
  (with `LowPriorityIO` and `Nice 5`), which makes the job eligible for
  aggressive CPU and I/O throttling: one run was still unfinished after 2m09s
  having consumed 0.31s of CPU, and a second took 27s, against ~4s by hand.
  With `Standard` the scheduled run finishes in ~9s. Do not add those keys back.
- **The lock is stale-aware, and must stay that way.** `db_backups/.lock` is
  taken per run and carries the holder's pid. A run killed with SIGKILL, or a
  reboot mid-dump, leaves the directory behind; the first version then exited 40
  on every subsequent run, which would have quietly stopped backups on this
  machine forever. `take_lock()` now clears a lock whose holder is not running
  and logs that it did. A lock held by a *live* process is still respected.

Check a scheduled run afterwards with `launchctl list | grep gex` — second
column is the last exit status, and the codes above say what a non-zero one
means. `db_backups/launchd.err` catches anything that fails before the script
can log.

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

`auth_users` now holds **23** rows (measured 2026-10-13, in the restore of the 12 Oct
dump):

    17  ACTIVE   activated_by = 'SEED_GRANDFATHERED'        predate vetting
     4  ACTIVE   activated_by = 'MANUAL_ADMIN_GRANT'        t-marwenc, t-mohamedk (09-20),
                                                           you_, jean-marie_ (10-11)
     1  ACTIVE   activated_by = 'TEST_FIXTURE_FORTAVERDE'   usr_test_fv_p1, vetting bypassed
     1  PENDING  (none)                                    usr_test_fv_p2, fixture stand-in

Do not backfill the grandfathered rows' NULL phone/agreement columns; that marker
is how you find them. None of the four `MANUAL_ADMIN_GRANT` rows has a phone or
agreement date either.

**`u_admin` no longer exists.** On 2026-09-24 it was the one account with no
marker at all. In the 12 Oct dump it is absent. The platform admins are
`admin_greenearthx_com` (`SEED_GRANDFATHERED`) and the four `MANUAL_ADMIN_GRANT`
accounts. Nothing records when `u_admin` went or whether it was re-keyed, so
the separation-of-duties question it raised is closed only if someone confirms
that.

Deal and product data belongs **behind the backend**, not the frontend's
Supabase `.from()`. Do not "fix" a frontend data path by wiring it to PostgREST.

---

## Evidence review — who may verify (Attack A, decided 2026-10-01)

A producer could walk its own claims to VERIFIED
(`docs/adversarial/2026-09-30_attack_A_producer_advance.md`). Since 2026-10-01:

- A reviewer status (UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED) on
  `POST /bankability/evidence` is a **VERIFY**, classified from the body
  (`abac_middleware._is_evidence_review`). The URL test (`"/verify" in path`)
  never matched it, so R5 was never reached.
- **Who reviews which gate is JML's decision**, settled 2026-10-02:
  `abac.REVIEWER_GATES` — **certifier** (G2, G11), **independent engineer**
  (G0, G1, G3, G5, G6, G11), **lenders' adviser** (G0, G4, G7, G8, G9, G10),
  **insurer** (G7). Four roles, every one independent of GEX: the platform
  enforces the standard and verifies nothing itself. A GEX desk-review role was
  built on 10-01 and removed on 10-02 — do not reintroduce it. Change the table
  only on JML's word, together with `DECIDED` in
  `tests/test_evidence_review_separation.py` (mirrored, and negative-verified:
  widening the insurer to G10 fails 2 tests).
  Two consequences, both deliberate: **G0, G1 and G3 need an appointed
  independent engineer** (G0 also takes a lenders' adviser), so a concept-stage
  project with neither verifies nothing and stays SPECULATIVE; and **insurance
  bound at G10** (`insurance_certificates_delivered`) stays with the lenders'
  adviser, because gate-level scope cannot hand the insurer that one item
  without also handing it the legal opinions and the security package.
- Never the submitter or its company (`_independence_refusal`, in the handler),
  and never the project owner's company (R5). The actor is the token's user id;
  the body's `submitted_by` is ignored. VERIFIED must name the sha256 of a
  document on file (`POST /evidence/document`).
- A reviewer reads `GET /evaluate` (resource type `GATE_EVALUATION`) and the
  evidence and documents of its own gates, nothing else. Other gates' items are
  withheld from its screen.
- **Assigned** = the role on the project (`auth_user_project_roles`) AND the
  project in `assigned_audits`. On PostgreSQL its company also needs a
  `project_access` row, or RLS refuses the write. **No live account is assigned**
  (measured 2026-09-30), so nobody can verify yet. That is fail-closed, not a bug.

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

**2026-09-30: 853 pass, 18 skip, 0 fail** at head **059**. The arithmetic against
the 28 Sep row closes exactly: 844 + **9** new
(`tests/test_capital_bridge_projects_routes.py`) = 853. The 18th skip is the
empty `bankability_evidence_archive` (`test_evidence_history_pg.py:69`, handoff
item 38).

**2026-10-01: 898 pass, 18 skip, 0 fail**, both exported. 853 + **45**
(`tests/test_evidence_review_separation.py`, the Attack A fix) = 898; same 18 skips.

**2026-10-02: 899 pass, 18 skip, 0 fail.** 898 + **1**
(`test_evidence_slice.py::test_the_only_divergence_is_the_labelled_fixture`). The reviewer-table
swap (insurer in, GEX desk review out) changed no count. The +1 pins the one deliberate
PostgreSQL-only divergence — see the comprehension fixture below.

**2026-10-19: 956 pass, 18 skip, 0 fail** at head 061, both exported. 899 + **57**
(`test_reference_registry_pg.py`, `test_reference_catalog.py`, `test_reference_routes.py`,
two guardrails in `test_fuel_reference_slice.py`). The same 18 skips, read with `-rs`.

**2026-10-13: 899 pass, 18 skip, 0 fail**, run against the database restored from the
12 Oct dump with both URLs exported. The counts are unchanged from 10-02, and the same 18
skips were read with `-rs`.

**The three append-only failures are FIXED (migration 059).** Earlier the same
day this file recorded 850 pass / 3 FAIL, the failures being the `UPDATE`
variants of the parametrized append-only tests in `test_commitment_terms_pg.py`
and `test_evidence_history_pg.py`. Head was 058 and both 056 and 058 had run, yet
`gex_app` held `INSERT, SELECT, UPDATE` on `evidence_events`,
`bankability_evidence_archive` and `commitment_terms_events`, with DELETE and
TRUNCATE correctly gone.

**The cause was NOT 031's DEFAULT PRIVILEGES, and NOT a missing REVOKE in 058.**
Both guesses were written here and both were wrong; `058:79` does
`REVOKE UPDATE, DELETE, TRUNCATE ON commitment_terms_events`, and 056 revokes the
other two. A REVOKE is atomic, so nothing "half-applied" — DELETE surviving while
UPDATE came back means something re-GRANTed UPDATE *after* Alembic, and granted
UPDATE without granting DELETE. Exactly one thing in this tree does that:

**`backend/scripts/setup_postgres_rls.sql` was re-run after Alembic during the
30 Sep rebuild.** Its second block looped over every table in `public` running
`GRANT SELECT, INSERT, UPDATE ON <tbl> TO gex_app`, exempting only a hardcoded
list — `audit_log`, `commitment_records`, `verification_log` — and only from
UPDATE. Its own comment invited the re-run ("Run this block again after every
Alembic migration adds new tables"). The proof it ran against a populated schema:
`gex_admin` holds ALL PRIVILEGES on **120** tables, which it can only have got
from that same loop. The resulting grant shape was that script's output exactly —
UPDATE back everywhere except `commitment_records`, the only name on its list
that exists in this database, and DELETE nowhere, because the loop never granted
DELETE. Confirm the diagnosis on any future recurrence with:

    SELECT c.relname, c.relacl FROM pg_class c JOIN pg_namespace n
      ON n.oid = c.relnamespace WHERE n.nspname='public' AND c.relkind='r'
      AND c.relname IN ('evidence_events','bankability_evidence_archive',
                        'commitment_terms_events','commitment_records');

`arw` (INSERT, SELECT, UPDATE) with no `d` is the signature of that script; full
`arwd` would instead mean the table really was dropped and recreated. **The tables
were never dropped and recreated** — had they been, 031's DEFAULT PRIVILEGES would
have handed back DELETE too, and it was absent.

Both ends are now closed:

- **Migration 059** restores the three revokes, and *asserts* afterwards that
  `gex_app` holds no UPDATE/DELETE/TRUNCATE on any of them, so a silent re-grant
  cannot pass unnoticed again. Its downgrade returns the database to the
  `INSERT, SELECT, UPDATE` state 059 found, not to 031's full DML.
- **`setup_postgres_rls.sql` can no longer undo a migration's revoke.** Its grant
  loop now touches only tables on which `gex_app` holds *nothing*, and its
  append-only set is REVOKEd unconditionally. A REVOKE can only be more
  restrictive, so a stale list there under-protects but can never un-protect —
  the asymmetry the old blanket GRANT lacked. Verified by re-running the script
  against the live database after 059: the revokes survived.

`commitment_terms` deliberately KEEPS UPDATE — cards are replaced in place (058
grants it on purpose). Only its *history* is append-only.

**Known conflict, not fixed here:** `app/core/css.py:272` issues
`UPDATE commitment_records` on the countersign path, and `commitment_records` has
had UPDATE revoked since well before 059 (by the old script's hardcoded list).
That path cannot have worked as `gex_app` on PostgreSQL. 059 did not cause it and
does not change it — it is a genuine design question (is countersigning a state
transition or a rewrite of history?) and needs its own decision.

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
