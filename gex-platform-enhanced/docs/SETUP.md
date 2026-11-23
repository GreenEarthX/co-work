# GEX — development setup

A working development stack from a fresh checkout: PostgreSQL, the platform backend,
the PF engine, the TEA engine and the frontend.

**Checked against the tree on 22 Nov 2026** (migration head 129). Running it day to
day is covered in `OPERATIONS.md`, and security settings in `SECURITY.md`.
**PostgreSQL is required:** the backend refuses to start on SQLite.

---

## 1. Prerequisites

| Tool | Version in use | Notes |
|---|---|---|
| Python | 3.14 | Backend and PF engine. Each has its own virtualenv. |
| Node.js | 23.9 (20+ works) | Frontend |
| Docker Desktop | — | PostgreSQL 15 + PostGIS. Leave at least 2 GB free on its VM disk. |
| `libolm`, `cmake` | — | Only for `matrix-nio[e2e]` (`brew install libolm cmake`). Nothing imports it. |

`requirements.txt` pins `cryptography==46.0.6`, because newer releases have no Intel
macOS wheel and need Rust to build. `lxml` is required: the connector schema checks
fail without it.

---

## 2. Repositories

The two repositories sit side by side in one folder:

```text
files/
├── gex-platform-enhanced/   backend :8000, tea_engine :8002, frontend :3000
├── gex_pf_engine/           PF engine :8001 (own repo, own venv: micro_service/)
├── gex-demo-compose.yml     PostgreSQL definition (compose project "files")
├── backup_postgres.sh, start_stack.sh, start_pf_engine.sh
└── .env                     database passwords for compose (git-ignored, mode 600)
```

`gex_pf_engine` and `gex-platform-enhanced/deal_engine` are **different services**.
Neither is a copy of the other.

---

## 3. PostgreSQL

1. **Start the database container** (project `files`, so that the forwarder can find it):

   ```bash
   cd files
   docker compose -p files -f gex-demo-compose.yml up -d postgres
   ```

2. **Start the forwarder on :55432, listening on this machine only:**

   ```bash
   docker run -d --name gex-pg-forward --restart unless-stopped --network files_gex_net \
     -p 127.0.0.1:55432:5432 -p '[::1]:55432:5432' \
     alpine/socat TCP-LISTEN:5432,fork,reuseaddr TCP:files-postgres-1:5432
   ```

   Never publish it as `-p 55432:5432`: that opens the database to the whole network.

3. **Create the roles once, before anything else:**

   ```bash
   docker exec -i files-postgres-1 psql -U gex_user -d gex_platform \
     < gex-platform-enhanced/backend/scripts/setup_postgres_rls.sql
   ```

   It creates `gex_app`, `gex_admin`, `gex_engine` and `gex_anchor`. Then set each password to the value in your `.env` (`ALTER ROLE … PASSWORD …`). **Do not run it again after migrations.**

4. **Fill the database.** Choose one:
   - **Restore a dump (preferred).** Restore into a throwaway database, check it, promote it, then re-apply `GRANT CONNECT` and the `app.current_company_id` default. See `OPERATIONS.md` §5.
   - **Build from migrations.** Run `alembic upgrade auth_slice@head` (`OPERATIONS.md` §6), then the post-rebuild data scripts listed in `.claude/CLAUDE.md`.

---

## 4. Environment files

There is no `.env.example`. **Never commit a real value**: the `co-work` mirror is
public. The variables are:

- **`gex-platform-enhanced/backend/.env`:**
  - `DATABASE_URL` (`gex_app` on `localhost:55432`);
  - `ALEMBIC_DATABASE_URL` (`gex_user`);
  - `SECRET_KEY`;
  - the optional settings in `OPERATIONS.md` §4.

  The `Settings` class rejects any variable it does not declare.
- **`gex_pf_engine/backend/.env`:**
  - `GEX_ENGINE_DATABASE_URL` (`gex_engine`);
  - `GEX_PLATFORM_API_URL`;
  - `GEX_JWT_SECRET`, equal to the backend's `SECRET_KEY`.
- **Export as real environment variables**, not only in `.env`:
  - `ALEMBIC_DATABASE_URL` and `DATABASE_URL` for migrations and tests;
  - `CANONICAL_DATABASE_URL` (the `gex_app` credential) for the backend.

---

## 5. Install and run

```bash
# Platform backend (:8000)
cd gex-platform-enhanced/backend
python3 -m venv venv && venv/bin/pip install -r requirements.txt
env CANONICAL_DATABASE_URL="$DATABASE_URL" venv/bin/python -m uvicorn app.main:app --port 8000
```

```bash
# PF engine (:8001): its own venv, package pf_engine (not app)
cd gex_pf_engine/backend
python3 -m venv ../micro_service && ../micro_service/bin/pip install -r requirements.txt
source ../micro_service/bin/activate && uvicorn pf_engine.main:app --reload --port 8001
```

```bash
# TEA engine (:8002), run from the repo root with the backend venv
cd gex-platform-enhanced
backend/venv/bin/pip install -r tea_engine/requirements.txt
env GEX_JWT_SECRET="$SECRET_KEY" GEX_JWT_ISSUER=https://api.greenearthx.com \
    GEX_JWT_AUDIENCE=gex-platform TEA_STUB=0 \
    backend/venv/bin/python -m uvicorn tea_engine.main:app --port 8002
```

```bash
# Frontend (:3000); /api is proxied to VITE_API_URL or http://localhost:8000
cd gex-platform-enhanced/frontend
npm install && npm run dev
```

In Claude Code, start the frontend, backend and TEA engine from `.claude/launch.json`.
The PF engine has no entry there, by design (`.claude/CLAUDE.md`, "Starting the
services").

Then check the health routes in `OPERATIONS.md` §3.

---

## 6. First sign-in

- **Accounts are vetted.** Registration creates a `PENDING` account, and only GEX staff can activate it.
- **First platform administrator:**

  ```bash
  venv/bin/python scripts/create_platform_admin.py --email … --name "…" --dry-run
  ```

  Run it from `backend/`, then again without `--dry-run`.
- **Demo accounts:** created only when `GEX_SEED_DEMO_USERS` is set. They are never created in production, and their password is published.

---

## 7. Tests

See `OPERATIONS.md` §8. Export both database URLs first. Without them, about 125 PostgreSQL tests skip and the run still reports green.

---

## 8. Common problems

| Symptom | Cause |
|---|---|
| Port 55432 accepts connections, but queries fail or hang | PostgreSQL is stopped or Docker Desktop is paused. Run `files/start_stack.sh`. |
| "password authentication failed" for `gex_app` | The role's password does not match `.env`. Use `ALTER ROLE`. |
| A migration ran against the wrong database | `ALEMBIC_DATABASE_URL` was not exported. `alembic.ini` holds a sentinel and aborts. |
| `relation "matrix_rooms" already exists` | You ran `alembic upgrade heads`. Use `auth_slice@head`. |
| The backend exits at start | A `*_DB_BACKEND` switch is `sqlite`, or a variable is not declared in `Settings`. |
| Gate screens say "No access to this project's gates" | A 401/403 from the engine. Check `GEX_JWT_SECRET`, or the account's project access. |
