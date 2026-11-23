# GEX operations runbook

How to run, check, back up, restore and migrate GEX. Its purpose is to remove the
dependency on any one person: if a step is missing, fix this page.

**Checked against the tree and the running development stack on 22 Nov 2026**
(migration head 129, PostgreSQL 15). The traps behind each step, and their history,
are in `.claude/CLAUDE.md` ("Database", "Backups"). Security settings are in
`SECURITY.md`.

---

## 1. Services

| Port | Service | Code | Entry point | Store |
|---|---|---|---|---|
| 8000 | Platform API (FastAPI) | `gex-platform-enhanced/backend` | `app.main:app` | PostgreSQL as `gex_app` |
| 8001 | PF engine: gates, project finance, Gabillon | sibling repo `gex_pf_engine/backend` | `pf_engine.main:app` | Run log in PostgreSQL as `gex_engine` (migration 082) |
| 8002 | TEA engine (OpenPyTEA 3.2.3) | `gex-platform-enhanced/tea_engine` | `tea_engine.main:app` | None (stateless) |
| 3000 | Frontend (Vite, React, TypeScript) | `gex-platform-enhanced/frontend` | `npm run dev` | None; `/api` is proxied to :8000 |
| 55432 | PostgreSQL 15 + PostGIS | container `files-postgres-1`, volume `files_postgres_data` | via forwarder `gex-pg-forward` | — |

On the development Mac, **55432 is not a typo.** A different, non-GEX PostgreSQL
runs on 5432. Since 22 Nov the forwarder listens on `127.0.0.1` / `[::1]` only.

**How the backend reaches the engines:**
- **PF engine:** `GEX_ENGINE_URL` (default `http://localhost:8001`). The pricing proxy reads `PF_ENGINE_URL` first.
- **TEA engine:** `TEA_ENGINE_URL` (default `http://localhost:8002`).
- **Authentication:** both engines check the platform's JWT, so the PF engine needs `GEX_JWT_SECRET` equal to the backend's `SECRET_KEY`, and the TEA engine needs `GEX_JWKS_URL`.

---

## 2. Start and stop (development Mac)

| Service | How it starts |
|---|---|
| Frontend, backend, TEA engine | `.claude/launch.json` entries `frontend`, `backend`, `tea_engine`. Started from the Browser pane, or with the same command lines in a terminal. |
| PF engine | launchd job `com.gex.pf-engine` keeps it running (`files/start_pf_engine.sh`, no `--reload`). By hand: see below. |
| PostgreSQL | launchd job `com.gex.stack-up` runs `files/start_stack.sh` at login and every 15 minutes. It never re-creates a container (exit 12 means the container is missing). |

Starting the PF engine by hand:

```bash
cd files/gex_pf_engine/backend
source ../micro_service/bin/activate
uvicorn pf_engine.main:app --reload --port 8001
```

After changing engine code, restart the launchd copy:

```bash
launchctl kickstart -k gui/$UID/com.gex.pf-engine
```

Check the jobs with `launchctl list | grep gex`. The second column is the last exit
status. All four jobs were installed and at 0 on 22 Nov.

**After a Docker Desktop restart PostgreSQL stays stopped** (restart policy `no`),
while the forwarder still accepts connections. Run `files/start_stack.sh`, or
`docker start files-postgres-1`. **If the container or volume is missing,
`docker start` cannot help:** restore from a dump (§5).

---

## 3. Health checks

| Check | What it proves |
|---|---|
| `GET :8000/health` | The API process answers. It does **not** touch the database. |
| `GET :8000/api/v1/bankability/health` | The backend and the PF engine are reachable from each other. |
| `GET :8000/api/v1/onboarding/reference-data/fuels` | The backend can read PostgreSQL (public route). |
| `GET :8001/health` | PF engine, per-module status. |
| `GET :8002/healthz` | TEA engine. |

To check the database itself, use `pg_isready` or run a query; an open port does not mean the database is up.

---

## 4. Configuration

`Settings` (`backend/app/core/config.py`) **refuses any variable it does not declare.**

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` / `staging` turns on the start-up guards (`SECURITY.md` §1). |
| `DATABASE_URL` | port **5432**, `gex_app` | Runtime role. **Always set it.** The default points at the wrong port on the development Mac. |
| `ALEMBIC_DATABASE_URL` | empty | Migrator role (`gex_user`). Must be **exported**: Alembic reads `os.environ`, not `.env`. |
| `CANONICAL_DATABASE_URL` | unset | Read with `os.getenv` at import, so it must be a real environment variable. Use the `gex_app` credential. |
| `*_DB_BACKEND` (ten switches) | `postgres` | The backend refuses to start if any is `sqlite`. |
| `SECRET_KEY` / `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH` | dev key / empty | HS256 or RS256 signing (`scripts/generate_jwt_keys.sh`). |
| `GEX_DEMO_MODE` | `True` | Must be `False` on any shared server (`SECURITY.md` §2.1). |
| `GEX_SEED_DEMO_USERS` | `False` | Creates missing demo accounts; refused in production. |
| `CORS_ORIGINS` | localhost:3000, :5173 | Set to the real domain on the server. |
| `GEX_ENGINE_URL`, `PF_ENGINE_URL`, `TEA_ENGINE_URL` | localhost | See §1. |
| `GEX_EVIDENCE_DOCS_DIR` | `data/evidence_docs` | Evidence files on disk, beside the database rows (§5). |
| `LEDGER_ANCHOR_BACKEND` | `none` | `hedera_testnet` only; mainnet is not a value. `LEDGER_ANCHOR_SALT` is never rotated. |
| `REGISTRY_CONNECTOR_BACKEND` | `none` | Export only. |
| `REQUIRE_PARTY_SIGNATURE` | `False` | |
| `TEA_COST_BASE_YEAR` | 2026 | TEA runs are refused until `cepci_forward_2026` is approved on the GEX staff console. |
| `MARKET_AUTO_MATCHING` | `False` | Off, pending counsel. |
| `PGCONNECT_TIMEOUT` | 10 | Stops a paused Docker Desktop from hanging the backend. |

**The PF engine** reads `files/gex_pf_engine/backend/.env` (git-ignored, loaded by `start_pf_engine.sh`):
- `GEX_ENGINE_DATABASE_URL`, the `gex_engine` role (without it, runs are stamped `run_logged: false`);
- `GEX_PLATFORM_API_URL`;
- `GEX_JWT_SECRET`.

---

## 5. Database, backups, restore

**Database roles:**

| Role | Purpose |
|---|---|
| `gex_app` | Runtime. RLS applies. |
| `gex_user` | Migrations, dumps, restore. SUPERUSER + BYPASSRLS. |
| `gex_admin` | Administration. BYPASSRLS. |
| `gex_engine` | PF engine run log only. |
| `gex_anchor` | Ledger outbox only. |

**Never point `DATABASE_URL` at `gex_user`.** Doing so switches off tenant isolation, and `tests/test_gex_app_runtime_role.py` will catch it.

**Back up with `pg_dump`, never by copying files.** The volume lives inside Docker Desktop's VM disk, which Time Machine excludes.

- **Script:** `files/backup_postgres.sh`.
  - Dumps `-Fc` as `gex_user`, so that every tenant's rows are included.
  - Verifies the dump by a full read (not only `pg_restore -l`) before installing it.
  - Keeps 7 daily dumps in `files/db_backups/daily/` and 4 weekly ones (hardlinks).
- **Schedule:** launchd `com.gex.postgres-backup`, daily at 12:30. The last run, on 21 Nov 12:55, kept 7 daily and 4 weekly.
- **Exit codes:** 10–14 Docker/container, 20–24 dump/verify, 30 install, 40 lock. 13 (container stopped) is the usual one.
- **Verify an existing dump:**

  ```bash
  files/backup_postgres.sh --verify files/db_backups/daily/<file>.dump
  ```

- **Evidence files** live in `GEX_EVIDENCE_DOCS_DIR`, not in the dump. Back them up together with the dump: the database holds the sha256 and the directory holds the bytes.

**Restore:** follow `.claude/CLAUDE.md`, "To restore" and "Done for real 2026-10-13". In short:

1. Restore into a throwaway database (`gex_restore_test`) and compare:
   - table count and FORCED RLS count (178 / 171 at head 129);
   - `alembic_version` against `alembic heads`;
   - the append-only grants query.
2. If the roles are missing, run `backend/scripts/setup_postgres_rls.sql` **once, before** the restore. Never run it after Alembic. Then set each role's password to match the environment.
3. Promote: drop `gex_platform`, then rename the test database to `gex_platform`.
4. Re-apply the settings a dump does not carry:
   - `GRANT CONNECT ON DATABASE gex_platform TO gex_app, gex_admin, gex_engine, gex_anchor;`
   - `ALTER DATABASE gex_platform SET app.current_company_id = 'GUEST';`
5. Take a fresh backup.

Do not run migrations as part of a restore: the dump carries its own schema.

---

## 6. Migrations

```bash
cd gex-platform-enhanced/backend
export ALEMBIC_DATABASE_URL=...   # gex_user
export DATABASE_URL=...           # gex_app
venv/bin/alembic upgrade auth_slice@head
```

- **Upgrade with `auth_slice@head`, never bare `head` or `heads`.** There are two roots: `030` is labelled `auth_slice`, and a legacy `001→011` chain exists alongside it.
- **Take a backup first.** After any restore, compare `alembic_version` with `alembic heads`.
- **Some data is not created by migrations.** After a full **Alembic rebuild** (not a dump restore), several data scripts must be re-run in order; `.claude/CLAUDE.md` lists them per migration. Reference values are then approved by a person on the GEX staff console: no script approves them.
- **`gex-platform-enhanced-part-a`** (branch `greenmesh-part-a`, not merged) has its own migration **124**, which clashes with main's `124_calculation_chain.py`. Renumber it before merging.

---

## 7. Scheduled jobs (launchd, development Mac)

| Job | When | Does | Failure codes |
|---|---|---|---|
| `com.gex.stack-up` | at login, every 15 min | `start_stack.sh` | 10–12 Docker / container missing |
| `com.gex.pf-engine` | always (KeepAlive) | `start_pf_engine.sh` | — |
| `com.gex.postgres-backup` | daily 12:30 | `backup_postgres.sh` | see §5 |
| `com.gex.expiry-sweep` | daily 07:30 | `backend/scripts/expire_evidence.py --apply` | 2 database unreadable, 3 a project not re-evaluated |

Logs are in `files/db_backups/`: `backup.log`, `stack.log`, and the `*.out` / `*.err` files of each job.
**`ProcessType` must stay `Standard`.** With `Background`, launchd throttled the backup to minutes.

---

## 8. Tests

Run each suite alone: two pytest runs share the test database `gex_test_suite`.

**Platform** (export both URLs first; otherwise about 125 PostgreSQL tests skip and the run still looks green):

```bash
cd gex-platform-enhanced/backend
export DATABASE_URL=... ALEMBIC_DATABASE_URL=...
./venv/bin/python -m pytest tests/ -q -rs
```

**PF engine:**

```bash
cd gex_pf_engine/backend
../micro_service/bin/python -m pytest tests/ -q
```

**Frontend:**

```bash
cd gex-platform-enhanced/frontend
npm test && npx tsc --noEmit
```

`npm run build` also runs the menu, causal-ways and Supabase audits.

Read the skip reasons (`-rs`): a skip is not a pass.

---

## 9. Docker images and deployment

- **Images:** `jmlamay/gex-backend`, `gex-frontend`, `gex-pf-engine` and `gex-tea-engine` on Docker Hub (public).
  - Built from `files/docker/` after `files/sync-to-docker.sh`.
  - Published by the procedure in `files/PUBLISH_PROMPT.md`.
  - Current tag: **v1.13.0**, pinned in `files/gex-demo-compose.yml`.
- **Before building, check the Docker VM disk** (7.8 GB, shared with PostgreSQL), then run `docker builder prune -a -f`.
- **What goes in the images:** only `backend/`, `frontend/` (built), `tea_engine/` and the PF engine's `backend/`, never `docs/`.
- **`files/gex-demo-compose.yml`** is the pinned stack. It publishes only the frontend, on 8080; nginx proxies `/api/` to the backend. It is **not ready for a public server** as written:
  - `ENVIRONMENT: development`;
  - literal secrets in the file;
  - no `GEX_ENGINE_URL` for the backend. Only `PF_ENGINE_URL` is set, so the bankability proxy, the finance model and the onboarding model call `localhost:8001` inside the container.

  See `SECURITY.md` §2.
- **`gex-platform-enhanced/docker-compose.prod.yml`** is older than the pinned stack: it has no TEA engine, and it publishes 5432 and 6379. Do not use it.

---

## 10. Accounts and projects (no code edit)

- **Accounts.** A client registers, and the account is `PENDING`. GEX staff vet and activate it on the GEX staff console (`/gex-console`), with separation of duties. The first platform admin is created with `backend/scripts/create_platform_admin.py` (try `--dry-run` first).
- **Reviewers** (independent engineer, certifier, and the others) are appointed by GEX staff on "Who verifies" (Gates & Evidence), on a named party's instruction.
- **Projects** are created by the client on `/projects/new`, never loaded by script. Test fixtures are marked `proj_TEST_…` and have their own `--remove` scripts.
