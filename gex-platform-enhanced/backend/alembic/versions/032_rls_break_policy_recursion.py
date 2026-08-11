"""RLS — break the mutual recursion between the projects and project_access policies.

Revision ID: 032
Revises: 031

THE BUG
-------
Migration 020's two policies reference each other:

    projects        USING (... OR EXISTS (SELECT 1 FROM project_access ...))
    project_access  USING (... OR EXISTS (SELECT 1 FROM projects ...))

Evaluating the `projects` policy requires reading `project_access`, which
applies the `project_access` policy, which requires reading `projects`, and so
on. PostgreSQL detects it and refuses:

    infinite recursion detected in policy for relation "projects"

This was invisible for as long as the application connected as a SUPERUSER
(see 031): superusers bypass RLS, so these policies had never once been
evaluated. Fixing the bypass is what surfaced the defect — which is the whole
argument for measuring isolation rather than asserting it.

THE FIX
-------
Two SECURITY DEFINER helpers. They execute as the function owner (the schema
owner), so their internal reads are not themselves subject to RLS, which cuts
the cycle. Each is:

  · STABLE — same result within a statement, so the planner may cache it.
  · search_path pinned to 'public, pg_temp' — a SECURITY DEFINER function with
    a mutable search_path is a privilege-escalation vector: a caller could
    create a shadowing object in a schema earlier on the path and have it run
    with the owner's rights. This is the standard hardening and is not optional.
  · EXECUTE granted to gex_app only.

The policy LOGIC is unchanged — same three branches, same semantics. Only the
evaluation strategy changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION app_company_has_project_access(
            p_project_id text, p_company_id text
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM project_access
                WHERE project_id = p_project_id
                  AND company_id = p_company_id
            )
        $$;
    """))

    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION app_company_owns_project(
            p_project_id text, p_company_id text
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM projects
                WHERE project_id = p_project_id
                  AND owner_tenant_id = p_company_id
            )
        $$;
    """))

    # Not PUBLIC — only the application role needs these.
    conn.execute(sa.text(
        f"REVOKE ALL ON FUNCTION app_company_has_project_access(text, text) FROM PUBLIC"))
    conn.execute(sa.text(
        f"REVOKE ALL ON FUNCTION app_company_owns_project(text, text) FROM PUBLIC"))
    conn.execute(sa.text(
        f"GRANT EXECUTE ON FUNCTION app_company_has_project_access(text, text) TO {APP_ROLE}"))
    conn.execute(sa.text(
        f"GRANT EXECUTE ON FUNCTION app_company_owns_project(text, text) TO {APP_ROLE}"))

    # ── Replace both policies, same semantics, no cross-table reads ──────────
    conn.execute(sa.text("DROP POLICY IF EXISTS projects_tenant_isolation ON projects"))
    conn.execute(sa.text("""
        CREATE POLICY projects_tenant_isolation
        ON projects
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'
            OR owner_tenant_id = current_setting('app.current_company_id', true)
            OR app_company_has_project_access(
                   project_id, current_setting('app.current_company_id', true))
        )
    """))

    conn.execute(sa.text(
        "DROP POLICY IF EXISTS project_access_tenant_isolation ON project_access"))
    conn.execute(sa.text("""
        CREATE POLICY project_access_tenant_isolation
        ON project_access
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'
            OR company_id = current_setting('app.current_company_id', true)
            OR app_company_owns_project(
                   project_id, current_setting('app.current_company_id', true))
        )
    """))

    # NOTE: the '' (empty string) branch from 020 is GONE. It read
    #     current_setting(...) IN ('', 'PLATFORM_ADMIN')
    # so any session that set the GUC to an empty string saw every row. An
    # UNSET GUC yields NULL (which fails closed, correctly), but '' was a
    # silent full bypass reachable by an ordinary caller. There is no
    # legitimate use for it: admin access has its own explicit sentinel.


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP POLICY IF EXISTS projects_tenant_isolation ON projects"))
    conn.execute(sa.text(
        "DROP POLICY IF EXISTS project_access_tenant_isolation ON project_access"))
    conn.execute(sa.text("""
        CREATE POLICY projects_tenant_isolation ON projects FOR ALL
        USING (
            current_setting('app.current_company_id', true) IN ('', 'PLATFORM_ADMIN')
            OR owner_tenant_id = current_setting('app.current_company_id', true)
            OR EXISTS (
                SELECT 1 FROM project_access pa
                WHERE pa.project_id = projects.project_id
                  AND pa.company_id = current_setting('app.current_company_id', true))
        )
    """))
    conn.execute(sa.text("""
        CREATE POLICY project_access_tenant_isolation ON project_access FOR ALL
        USING (
            current_setting('app.current_company_id', true) IN ('', 'PLATFORM_ADMIN')
            OR company_id = current_setting('app.current_company_id', true)
            OR EXISTS (
                SELECT 1 FROM projects p
                WHERE p.project_id = project_access.project_id
                  AND p.owner_tenant_id = current_setting('app.current_company_id', true))
        )
    """))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS app_company_has_project_access(text, text)"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS app_company_owns_project(text, text)"))
