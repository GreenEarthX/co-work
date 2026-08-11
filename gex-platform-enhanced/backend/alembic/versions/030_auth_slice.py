"""Auth slice — identity tables move to PostgreSQL.

Strangler slice 2 of docs/postgres-migration-plan.md: auth_users,
auth_user_project_roles, auth_login_history, refresh_tokens.

TYPE FIDELITY IS DELIBERATE
---------------------------
Timestamps are TEXT and booleans are INTEGER, exactly as in SQLite — not
TIMESTAMPTZ/BOOLEAN. That looks wrong for a Postgres schema, and it is
temporary on purpose:

  · app/core/auth.py stores ISO-8601 strings and compares them AS STRINGS
    (refresh-token expiry, login history ordering). Handing it datetime
    objects would change behaviour in the same change that moves the data.
  · A slice that migrates storage AND rewrites the type system has ambiguous
    failures — you cannot tell a copy bug from a coercion bug.

Parity first, then a separate revision modernises the types with the
application code changed alongside it. Recorded as an open item.

RLS IS NOT ENABLED HERE
-----------------------
Deliberate, and consistent with the migration plan, which says slice 3
(projects) "is the slice that turns RLS on for real".

`auth_users` is the table that ESTABLISHES tenancy, so it cannot be filtered
by it: the login lookup runs before any identity exists, when
app.current_company_id is 'GUEST'. A naive company_id policy would deny the
credential check and lock everyone out. Getting that right needs a deliberate
authentication-path exemption (a second GUC, or a dedicated role), which
belongs with the projects slice where the policy model is being built anyway.

Enabling RLS wrongly here would be worse than not enabling it: it would read
as protection while either breaking login or silently permitting everything.

INDEPENDENT ROOT — DELIBERATE
-----------------------------
down_revision is None, not "021". The existing chain (010_verification_state
onward) targets tables from OTHER slices that are not in Postgres yet, so
`alembic upgrade head` against a fresh database dies on
  relation "bankability_evidence" does not exist
That is the "stale revisions" problem the migration plan calls out in step 1.

The auth slice genuinely does not depend on those tables, so chaining to them
would encode a dependency that does not exist and would block this slice on
unrelated work. It is its own branch, applied with:

    alembic upgrade auth_slice@head

When the schema-truth revision lands, the branches can be merged.

Revision ID: 030
Revises: (none — independent branch "auth_slice")
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("auth_slice",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("company_type", sa.Text(), nullable=False),
        sa.Column("service_type", sa.Text()),
        sa.Column("business_function", sa.Text(), nullable=False),
        sa.Column("user_name", sa.Text(), nullable=False),
        sa.Column("company_logo_url", sa.Text()),
        sa.Column("clearance_level", sa.Text(), nullable=False, server_default="STANDARD"),
        sa.Column("jurisdiction", sa.Text(), nullable=False, server_default="EU"),
        # NOTE: no server_default 'VERIFIED'. The SQLite table defaulted this to
        # VERIFIED, which made every row trusted by construction. New accounts
        # are UNVERIFIED until a GEX employee says otherwise.
        sa.Column("kyc_status", sa.Text(), nullable=False, server_default="UNVERIFIED"),
        sa.Column("nda_signed_with_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("assigned_audits_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("credit_rating", sa.Text(), nullable=False, server_default="NR"),
        sa.Column("credit_rating_source", sa.Text(), nullable=False, server_default="GEX"),
        sa.Column("export_licenses_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("token_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transformation_license", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aggregation_limit_mt", sa.Float()),
        sa.Column("is_platform_admin", sa.Integer(), nullable=False, server_default="0"),
        # is_active defaults to 0, NOT 1 — see account_lifecycle.py. A row that
        # exists is not a row that may log in.
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text("to_char(now() at time zone 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')")),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text("to_char(now() at time zone 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')")),
        # ── Vetting-before-trust (core/account_lifecycle.py) ────────────────
        sa.Column("account_state", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("registered_at", sa.Text()),
        sa.Column("phone_verified_at", sa.Text()),
        sa.Column("phone_verified_by", sa.Text()),
        sa.Column("agreement_signed_at", sa.Text()),
        sa.Column("agreement_ref", sa.Text()),
        sa.Column("activated_at", sa.Text()),
        sa.Column("activated_by", sa.Text()),
        sa.Column("vetting_note", sa.Text()),
        sa.CheckConstraint(
            "account_state IN ('PENDING','IN_VETTING','ACTIVE','SUSPENDED','REJECTED')",
            name="ck_auth_users_account_state",
        ),
    )
    op.create_index("idx_auth_users_email", "auth_users", ["email"])
    op.create_index("idx_auth_users_company", "auth_users", ["company_id"])
    op.create_index("idx_auth_users_state", "auth_users", ["account_state"])

    op.create_table(
        "auth_user_project_roles",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "project_id", "actor_type"),
    )
    op.create_index("idx_aupr_user", "auth_user_project_roles", ["user_id"])

    op.create_table(
        "auth_login_history",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False, server_default="signin"),
        sa.Column("ip_address", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("success", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("idx_login_history_user", "auth_login_history", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", sa.Text(), primary_key=True),
        sa.Column("family_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_at", sa.Text()),
        sa.Column("revoked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_family", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("auth_login_history")
    op.drop_table("auth_user_project_roles")
    op.drop_table("auth_users")
