"""Governance / access control — slice 6b-4.

Revision ID: 042
Revises: 041

Seven small tables, 16 rows — but they decide **who may approve what**, so they
get auth-slice scrutiny rather than domain-tail treatment.

FOUR DIFFERENT POLICY SHAPES, BECAUSE THE SCOPES GENUINELY DIFFER
-----------------------------------------------------------------
Every previous slice used one shape. Here, using one shape would be wrong four
different ways:

1. GLOBAL RULE DEFINITIONS — approval_policies, sod_conflict_pairs
   The rules everyone is subject to ("payments over X need 2 approvers").
   READ-OPEN, admin writes. Hiding them would leave the UI unable to explain
   why an action was refused; a compliance rule you cannot read is not a
   control, it is a trap. Not secret — binding.

2. PROJECT-SCOPED — approval_requests, sod_action_log
   Standard delegation to the 032 helpers.

3. USER-SCOPED — permission_user_overrides, user_signing_keys
   ADMIN-ONLY, and this is a KNOWN LIMITATION rather than a design.
   The tenancy of these rows is a USER, but the only tenant GUC that exists is
   `app.current_company_id`. There is no `app.current_user_id`, so "a user may
   read their own row" CANNOT be expressed today.
   Admin-only is correct for now because both are consumed platform-internally
   (permission_engine.py evaluates overrides while deciding authorisation; it
   cannot itself be filtered by that decision). If either ever needs
   self-service reads, add the GUC and a real policy — do NOT widen these to
   company scope, which would let a colleague read another user's overrides.

4. COMPANY-SCOPED — data_residency_policies
   company_id compared directly.

user_signing_keys stores PUBLIC keys and fingerprints only — no private key
material — so this is not a secrets migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"


def upgrade() -> None:
    op.create_table(
        "approval_policies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("action_type", sa.Text()),
        sa.Column("threshold_currency", sa.Float()),
        sa.Column("threshold_volume", sa.Float()),
        sa.Column("required_roles", sa.Text()),
        sa.Column("min_approvers", sa.Integer()),
        sa.Column("escalation_timeout_hours", sa.Integer()),
        sa.Column("escalation_role", sa.Text()),
        sa.Column("active", sa.Integer()),
        sa.Column("created_at", sa.Text()),
        # A policy demanding fewer than one approver is not an approval policy.
        sa.CheckConstraint("min_approvers IS NULL OR min_approvers >= 1",
                           name="ck_approval_policies_min_approvers"),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("policy_id", sa.Text()),
        sa.Column("initiator_user_id", sa.Text()),
        sa.Column("action_type", sa.Text()),
        sa.Column("resource_id", sa.Text()),
        sa.Column("project_id", sa.Text()),
        sa.Column("payload_json", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("required_roles", sa.Text()),
        sa.Column("min_approvers", sa.Integer()),
        sa.Column("created_at", sa.Text()),
        sa.Column("expires_at", sa.Text()),
    )
    op.create_index("idx_ar_project", "approval_requests", ["project_id"])
    op.create_index("idx_ar_status", "approval_requests", ["status"])

    op.create_table(
        "sod_conflict_pairs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("action_a", sa.Text()),
        sa.Column("action_b", sa.Text()),
        sa.Column("resource_scope", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Integer()),
        sa.Column("created_at", sa.Text()),
        # An action cannot conflict with itself — that would block every actor
        # from ever performing it twice, which is not segregation of duties.
        sa.CheckConstraint("action_a IS DISTINCT FROM action_b",
                           name="ck_sod_pair_distinct"),
    )

    op.create_table(
        "sod_action_log",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text()),
        sa.Column("action_type", sa.Text()),
        sa.Column("resource_id", sa.Text()),
        sa.Column("project_id", sa.Text()),
        sa.Column("performed_at", sa.Text()),
    )
    op.create_index("idx_sal_project", "sod_action_log", ["project_id"])
    op.create_index("idx_sal_user_action", "sod_action_log", ["user_id", "action_type"])

    op.create_table(
        "permission_user_overrides",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("perm_string", sa.Text(), primary_key=True),
        sa.Column("granted", sa.Integer()),
        sa.Column("updated_at", sa.Text()),
    )
    op.create_index("idx_puo_user", "permission_user_overrides", ["user_id"])

    op.create_table(
        "user_signing_keys",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("algorithm", sa.Text()),
        sa.Column("public_key", sa.Text()),
        sa.Column("key_fingerprint", sa.Text()),
        sa.Column("created_at", sa.Text()),
        sa.Column("rotated_at", sa.Text()),
    )

    op.create_table(
        "data_residency_policies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("company_id", sa.Text()),
        sa.Column("data_category", sa.Text()),
        sa.Column("required_jurisdiction", sa.Text()),
        sa.Column("storage_zone", sa.Text()),
        sa.Column("active", sa.Integer()),
        sa.Column("consented_at", sa.Text()),
        sa.Column("created_at", sa.Text()),
    )
    op.create_index("idx_drp_company", "data_residency_policies", ["company_id"])

    conn = op.get_bind()

    def rls(table: str, using: str, extra_admin_write: bool = False):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        if extra_admin_write:
            conn.execute(sa.text(
                f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({using})"))
            conn.execute(sa.text(
                f"CREATE POLICY {table}_admin_writes ON {table} FOR ALL USING ({ADMIN})"))
        else:
            conn.execute(sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL USING ({using})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))

    # 1. Global rule definitions — readable by all, written by admin.
    rls("approval_policies", "true", extra_admin_write=True)
    rls("sod_conflict_pairs", "true", extra_admin_write=True)

    # 2. Project-scoped.
    project_scoped = (f"{ADMIN} OR app_company_owns_project(project_id, {ME}) "
                      f"OR app_company_has_project_access(project_id, {ME})")
    rls("approval_requests", project_scoped)
    rls("sod_action_log", project_scoped)

    # 3. User-scoped — admin-only until an app.current_user_id GUC exists.
    rls("permission_user_overrides", ADMIN)
    rls("user_signing_keys", ADMIN)

    # 4. Company-scoped.
    rls("data_residency_policies", f"{ADMIN} OR company_id = {ME}")


def downgrade() -> None:
    conn = op.get_bind()
    for t in ("approval_policies", "sod_conflict_pairs"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {t}_read ON {t}"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {t}_admin_writes ON {t}"))
    for t in ("approval_requests", "sod_action_log", "permission_user_overrides",
              "user_signing_keys", "data_residency_policies"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {t}_tenant_isolation ON {t}"))
    for t in ("data_residency_policies", "user_signing_keys",
              "permission_user_overrides", "sod_action_log", "sod_conflict_pairs",
              "approval_requests", "approval_policies"):
        op.drop_table(t)
