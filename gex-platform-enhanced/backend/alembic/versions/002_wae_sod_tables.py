"""Add WAE (approval workflow) and SoD tables

Revision ID: 002
Revises: 001
Create Date: 2026-03-17

Tables added:
  approval_policies   — WAE policies: thresholds, required approvers
  approval_requests   — Pending/resolved approval requests (append-mostly)
  approval_decisions  — Immutable approver decisions audit trail
  sod_conflict_pairs  — Conflict pair definitions (seeded)
  sod_action_log      — User action history for conflict detection
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── approval_policies ────────────────────────────────────────────────────
    op.create_table(
        "approval_policies",
        sa.Column("id",                        sa.Text, primary_key=True),
        sa.Column("action_type",               sa.Text, nullable=False, index=True),
        sa.Column("threshold_currency",        sa.Numeric, nullable=True),
        sa.Column("threshold_volume",          sa.Numeric, nullable=True),
        sa.Column("required_roles",            postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment="e.g. [\"RISK_OFFICER\", \"TREASURY_HEAD\"]"),
        sa.Column("min_approvers",             sa.Integer, server_default="2"),
        sa.Column("escalation_timeout_hours",  sa.Integer, server_default="24"),
        sa.Column("escalation_role",           sa.Text, nullable=True),
        sa.Column("active",                    sa.Boolean, server_default="true"),
        sa.Column("created_at",                sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── approval_requests ────────────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id",                  sa.Text, primary_key=True, comment="UUID"),
        sa.Column("policy_id",           sa.Text, nullable=False),
        sa.Column("initiator_user_id",   sa.Text, nullable=False, index=True),
        sa.Column("action_type",         sa.Text, nullable=False, index=True),
        sa.Column("resource_id",         sa.Text, nullable=True, index=True),
        sa.Column("project_id",          sa.Text, nullable=True, index=True),
        sa.Column("payload_json",        postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment="Full action payload for audit — never truncated"),
        sa.Column("status",              sa.Text, server_default="PENDING",
                  comment="PENDING | APPROVED | REJECTED | EXPIRED | ESCALATED"),
        sa.Column("required_roles",      postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("min_approvers",       sa.Integer, server_default="2"),
        sa.Column("created_at",          sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("expires_at",          sa.DateTime(timezone=True), nullable=True),
    )

    # ── approval_decisions — append-only ─────────────────────────────────────
    op.create_table(
        "approval_decisions",
        sa.Column("id",               sa.Text, primary_key=True),
        sa.Column("request_id",       sa.Text, nullable=False, index=True),
        sa.Column("approver_user_id", sa.Text, nullable=False, index=True),
        sa.Column("decision",         sa.Text, nullable=False,
                  comment="APPROVE | REJECT"),
        sa.Column("reason_text",      sa.Text, nullable=True),
        sa.Column("decided_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY;")

    # ── sod_conflict_pairs ───────────────────────────────────────────────────
    op.create_table(
        "sod_conflict_pairs",
        sa.Column("id",             sa.Text, primary_key=True, comment="e.g. SoD-01"),
        sa.Column("action_a",       sa.Text, nullable=False, index=True),
        sa.Column("action_b",       sa.Text, nullable=False, index=True),
        sa.Column("resource_scope", sa.Text, server_default="SAME_RESOURCE",
                  comment="SAME_RESOURCE | SAME_PROJECT | GLOBAL"),
        sa.Column("description",    sa.Text, nullable=True),
        sa.Column("active",         sa.Boolean, server_default="true"),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── sod_action_log — append-only ─────────────────────────────────────────
    op.create_table(
        "sod_action_log",
        sa.Column("id",           sa.Text, primary_key=True),
        sa.Column("user_id",      sa.Text, nullable=False, index=True),
        sa.Column("action_type",  sa.Text, nullable=False, index=True),
        sa.Column("resource_id",  sa.Text, nullable=True, index=True),
        sa.Column("project_id",   sa.Text, nullable=True, index=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sod_action_log")
    op.drop_table("sod_conflict_pairs")
    op.drop_table("approval_decisions")
    op.drop_table("approval_requests")
    op.drop_table("approval_policies")
