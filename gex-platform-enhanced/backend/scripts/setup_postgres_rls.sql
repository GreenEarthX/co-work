-- ============================================================================
-- GEX Platform — PostgreSQL RLS bootstrap
-- Run once as a superuser after creating the database and before running
-- Alembic migrations.
-- ============================================================================
-- Usage:
--   psql $DATABASE_URL -f scripts/setup_postgres_rls.sql

-- ── Application role ─────────────────────────────────────────────────────────
-- gex_app  — used by the FastAPI app (pool user).  Cannot bypass RLS.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gex_app') THEN
    CREATE ROLE gex_app LOGIN PASSWORD 'gex_app_password_change_in_prod';
  END IF;
END $$;

GRANT CONNECT ON DATABASE gex_platform TO gex_app;
GRANT USAGE   ON SCHEMA public         TO gex_app;

-- ── Platform-admin role ───────────────────────────────────────────────────────
-- gex_admin — used by migration runner and tenant_admin CLI.  BYPASSRLS.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gex_admin') THEN
    CREATE ROLE gex_admin LOGIN PASSWORD 'gex_admin_password_change_in_prod' BYPASSRLS;
  END IF;
END $$;

GRANT CONNECT ON DATABASE gex_platform TO gex_admin;
GRANT USAGE   ON SCHEMA public         TO gex_admin;

-- ── Set default for app.current_company_id ───────────────────────────────────
-- If a connection forgets to SET LOCAL, the default is 'GUEST' so RLS
-- returns nothing rather than everything.
ALTER DATABASE gex_platform SET app.current_company_id = 'GUEST';

-- ── After migrations run, grant table-level permissions ──────────────────────
-- (Run this block again after every Alembic migration adds new tables.)
DO $$
DECLARE
  tbl TEXT;
BEGIN
  FOR tbl IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I TO gex_app', tbl);
    -- Append-only tables (audit trails) — no UPDATE/DELETE for app role
    IF tbl IN ('audit_log', 'commitment_records', 'verification_log') THEN
      EXECUTE format('REVOKE UPDATE ON %I FROM gex_app', tbl);
    END IF;
  END LOOP;

  FOR tbl IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('GRANT ALL PRIVILEGES ON %I TO gex_admin', tbl);
  END LOOP;
END $$;

-- Sequences
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gex_app;
GRANT ALL           ON ALL SEQUENCES IN SCHEMA public TO gex_admin;

-- ── Verify RLS is enabled ─────────────────────────────────────────────────────
SELECT tablename, rowsecurity, forcerowsecurity
FROM pg_tables t
JOIN pg_class c ON c.relname = t.tablename
WHERE schemaname = 'public'
  AND t.tablename IN ('projects', 'project_access');
