"""Add Matrix secure-communications tables

Revision ID: 001
Revises:
Create Date: 2026-03-16

Tables added:
  matrix_rooms    — active and archived Matrix rooms per project/gate
  matrix_members  — current and historical room membership
  matrix_events   — immutable event log (metadata only, never message content)
  admin_log       — admin override log with mandatory justification (ISO 27001 A.12.4.3)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── matrix_rooms ──────────────────────────────────────────────────────────
    op.create_table(
        "matrix_rooms",
        sa.Column("id",          sa.Text,     primary_key=True, comment="Matrix room_id e.g. !abc:gex.internal"),
        sa.Column("project_id",  sa.Text,     nullable=False, index=True),
        sa.Column("gate_id",     sa.Text,     nullable=True,  comment="NULL = project-general room"),
        sa.Column("alias",       sa.Text,     nullable=False),
        sa.Column("topic",       sa.Text,     nullable=True),
        sa.Column("status",      sa.Text,     server_default="active", comment="active | archived"),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── matrix_members ────────────────────────────────────────────────────────
    op.create_table(
        "matrix_members",
        sa.Column("room_id",     sa.Text,    nullable=False),
        sa.Column("user_id",     sa.Text,    nullable=False),
        sa.Column("company_id",  sa.Text,    nullable=False, index=True),
        sa.Column("actor_type",  sa.Text,    nullable=False),
        sa.Column("power_level", sa.Integer, server_default="0"),
        sa.Column("joined_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("left_at",     sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("room_id", "user_id"),
        sa.ForeignKeyConstraint(["room_id"], ["matrix_rooms.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_matrix_members_room", "matrix_members", ["room_id"])

    # ── matrix_events — append-only (A.12.4.1) ───────────────────────────────
    op.create_table(
        "matrix_events",
        sa.Column("id",            sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("timestamp",     sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("event_type",    sa.Text, nullable=False, index=True,
                  comment="room.created|member.joined|member.kicked|room.archived|message.sent|member.denied"),
        sa.Column("room_id",       sa.Text, nullable=True),
        sa.Column("project_id",    sa.Text, nullable=True, index=True),
        sa.Column("gate_id",       sa.Text, nullable=True),
        sa.Column("actor_user_id", sa.Text, nullable=True, index=True),
        sa.Column("company_id",    sa.Text, nullable=True, index=True),
        sa.Column("metadata",      postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment="Metadata only — NEVER message content (E2EE)"),
        sa.Column("abac_decision", sa.Text, nullable=True, comment="ALLOW | DENY | N/A"),
    )

    # ── admin_log — append-only, immutable (A.12.4.3) ────────────────────────
    op.create_table(
        "admin_log",
        sa.Column("id",             sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("timestamp",      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("admin_user_id",  sa.Text, nullable=False, index=True),
        sa.Column("action",         sa.Text, nullable=False,
                  comment="member.override | power.override | room.force_archive"),
        sa.Column("room_id",        sa.Text, nullable=True),
        sa.Column("target_user_id", sa.Text, nullable=True),
        sa.Column("justification",  sa.Text, nullable=False,
                  comment="Mandatory — all admin actions require written justification"),
        sa.Column("before_state",   postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state",    postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # ── Row-Level Security (PostgreSQL — enforces ABAC at DB level) ───────────
    # Enables company-scoped queries: each company can only read their own events
    op.execute("""
        ALTER TABLE matrix_events  ENABLE ROW LEVEL SECURITY;
        ALTER TABLE admin_log      ENABLE ROW LEVEL SECURITY;
    """)

    # Policy: backend service role (gex_user) has full access
    # Application code must set app.current_company_id session variable
    # for per-company filtering at DB level (Tier 2C implementation)
    op.execute("""
        CREATE POLICY matrix_events_company_isolation ON matrix_events
            USING (company_id = current_setting('app.current_company_id', true)
                   OR current_user = 'gex_user');
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS matrix_events_company_isolation ON matrix_events")
    op.drop_table("admin_log")
    op.drop_table("matrix_events")
    op.drop_table("matrix_members")
    op.drop_table("matrix_rooms")
