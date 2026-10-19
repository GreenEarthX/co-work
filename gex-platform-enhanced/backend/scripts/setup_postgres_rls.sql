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
-- Safe to re-run at any point, including after Alembic. It was not always:
-- until 2026-09-30 the first loop ran an unconditional
--
--     GRANT SELECT, INSERT, UPDATE ON <every table> TO gex_app
--
-- which handed UPDATE straight back to every table a migration had deliberately
-- made append-only. Re-running this script after the 2026-09-30 rebuild undid
-- migration 056's revokes on bankability_evidence_archive and evidence_events
-- and 058's on commitment_terms_events; three tests caught it, and migration
-- 059 had to put them back.
--
-- THE MIGRATIONS ARE THE AUTHORITY ON PRIVILEGES. This script bootstraps the
-- roles and covers tables that have no grants at all; it must never restore a
-- privilege a migration revoked. Hence two rules below:
--   1. gex_app is granted only on tables where it currently holds NOTHING.
--   2. the append-only set is REVOKEd unconditionally. A REVOKE can only ever
--      be more restrictive, so a stale list here under-protects but can never
--      un-protect — which is the asymmetry the old GRANT did not have.
DO $$
DECLARE
  tbl TEXT;
BEGIN
  FOR tbl IN
    SELECT t.tablename
    FROM pg_tables t
    WHERE t.schemaname = 'public'
      AND NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants g
        WHERE g.grantee = 'gex_app'
          AND g.table_schema = 'public'
          AND g.table_name = t.tablename
      )
  LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I TO gex_app', tbl);
  END LOOP;

  -- Append-only tables (audit trails) — never UPDATE/DELETE for the app role.
  -- Keep in step with the migrations that own them: 005 commitment_records,
  -- 056 evidence_events + bankability_evidence_archive, 058
  -- commitment_terms_events, 061 reference_version. The archive is read-only,
  -- so it loses INSERT too.
  FOR tbl IN
    SELECT unnest(ARRAY[
      'audit_log',
      'commitment_records',
      'verification_log',
      'evidence_events',
      'commitment_terms_events',
      'reference_version'
    ])
    INTERSECT
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM gex_app', tbl);
  END LOOP;

  -- 061 reference_parameter: UPDATE is granted by COLUMN (lifecycle only), so
  -- only DELETE/TRUNCATE are revoked here. A table-level REVOKE UPDATE would also
  -- strip those column grants and break approval.
  IF EXISTS (SELECT 1 FROM pg_tables
             WHERE schemaname = 'public' AND tablename = 'reference_parameter') THEN
    EXECUTE 'REVOKE DELETE, TRUNCATE ON reference_parameter FROM gex_app';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_tables
             WHERE schemaname = 'public' AND tablename = 'bankability_evidence_archive') THEN
    EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON bankability_evidence_archive FROM gex_app';
  END IF;

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
-- forcerowsecurity lives on pg_class (relforcerowsecurity), not pg_tables.
-- Selecting it from pg_tables made this script exit non-zero on every run under
-- ON_ERROR_STOP, so a successful bootstrap read as a failed one.
SELECT t.tablename, t.rowsecurity, c.relforcerowsecurity AS forcerowsecurity
FROM pg_tables t
JOIN pg_class c ON c.relname = t.tablename
JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.schemaname
WHERE t.schemaname = 'public'
  AND t.tablename IN ('projects', 'project_access');
