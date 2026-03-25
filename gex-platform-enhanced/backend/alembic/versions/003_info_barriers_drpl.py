"""Add Information Barriers and DRPL tables

Revision ID: 003
Revises: 002
Create Date: 2026-03-17

Tables added:
  info_barriers            — Barrier definitions between desk/role pairs
  barrier_access_log       — Access attempts across barrier boundaries
  drpl_policies            — Data residency rules per company+data_category
  drpl_audit_log           — All residency check outcomes
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── info_barriers ─────────────────────────────────────────────────────────
    # Domain 3: Segregation of Information (Chinese Walls within companies)
    op.create_table(
        "info_barriers",
        sa.Column("id",               sa.Text, primary_key=True, comment="e.g. IB-01"),
        sa.Column("company_id",       sa.Text, nullable=False, index=True,
                  comment="Barrier applies within this company"),
        sa.Column("side_a",           sa.Text, nullable=False,
                  comment="Desk or role identifier (e.g. 'TRADING')"),
        sa.Column("side_b",           sa.Text, nullable=False,
                  comment="Opposing desk or role identifier (e.g. 'ORIGINATION')"),
        sa.Column("barrier_type",     sa.Text, server_default="HARD",
                  comment="HARD (block) | SOFT (log+warn) | CHINESE_WALL"),
        sa.Column("applies_to_data",  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="[]",
                  comment="List of DataCategory values this barrier covers"),
        sa.Column("description",      sa.Text, nullable=True),
        sa.Column("active",           sa.Boolean, server_default="true"),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_barriers_company_sides", "info_barriers", ["company_id", "side_a", "side_b"])

    # ── barrier_access_log — append-only ──────────────────────────────────────
    op.create_table(
        "barrier_access_log",
        sa.Column("id",           sa.Text, primary_key=True),
        sa.Column("barrier_id",   sa.Text, nullable=False, index=True),
        sa.Column("user_id",      sa.Text, nullable=False, index=True),
        sa.Column("user_desk",    sa.Text, nullable=True),
        sa.Column("resource_id",  sa.Text, nullable=True),
        sa.Column("data_category",sa.Text, nullable=True),
        sa.Column("outcome",      sa.Text, nullable=False,
                  comment="BLOCKED | PERMITTED | WARNED"),
        sa.Column("reason",       sa.Text, nullable=True),
        sa.Column("accessed_at",  sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.execute("ALTER TABLE barrier_access_log ENABLE ROW LEVEL SECURITY;")

    # ── drpl_policies ─────────────────────────────────────────────────────────
    # Domain 5: Data Residency Policy Layer
    op.create_table(
        "drpl_policies",
        sa.Column("id",                    sa.Text, primary_key=True),
        sa.Column("company_id",            sa.Text, nullable=False, index=True),
        sa.Column("data_category",         sa.Text, nullable=False, index=True,
                  comment="PERSONAL | CONTRACT | FINANCIAL_MODEL | CERTIFICATION | "
                          "COMMS_METADATA | PLANT_DATA | AUDIT_LOG"),
        sa.Column("required_jurisdiction", sa.Text, nullable=False,
                  comment="EU | CH | GB | US — governs storage zone selection"),
        sa.Column("storage_zone",          sa.Text, nullable=False,
                  comment="e.g. eu-west-1, ch-zurich-1"),
        sa.Column("note",                  sa.Text, nullable=True),
        sa.Column("active",                sa.Boolean, server_default="true"),
        sa.Column("created_at",            sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",            sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )
    op.create_index(
        "ix_drpl_company_category", "drpl_policies", ["company_id", "data_category"], unique=True
    )

    # ── drpl_audit_log — append-only ──────────────────────────────────────────
    op.create_table(
        "drpl_audit_log",
        sa.Column("id",                    sa.Text, primary_key=True),
        sa.Column("company_id",            sa.Text, nullable=False, index=True),
        sa.Column("data_category",         sa.Text, nullable=False),
        sa.Column("requested_zone",        sa.Text, nullable=False),
        sa.Column("outcome",               sa.Text, nullable=False,
                  comment="ALLOWED | BLOCKED | NEEDS_CONSENT"),
        sa.Column("required_jurisdiction", sa.Text, nullable=True),
        sa.Column("policy_id",             sa.Text, nullable=True),
        sa.Column("reason",                sa.Text, nullable=True),
        sa.Column("checked_at",            sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.execute("ALTER TABLE drpl_audit_log ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_table("drpl_audit_log")
    op.drop_index("ix_drpl_company_category", table_name="drpl_policies")
    op.drop_table("drpl_policies")
    op.drop_table("barrier_access_log")
    op.drop_index("ix_barriers_company_sides", table_name="info_barriers")
    op.drop_table("info_barriers")
