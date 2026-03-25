"""Add CSS (Commitment Signature Service) tables

Revision ID: 005
Revises: 004
Create Date: 2026-03-17

Tables added:
  commitment_records  — Non-deletable signed commitment log (CSS)
  user_signing_keys   — Per-user signing key registry (dev: derived, Tier4: HSM)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── commitment_records — append-only, non-deletable ───────────────────────
    # Domain 6: Commitment Signature Service
    # eIDAS 910/2014 compliance (Tier 4: QTSP-backed RSA-2048/Ed25519)
    op.create_table(
        "commitment_records",
        sa.Column("commitment_id",          sa.Text, primary_key=True, comment="UUID"),
        sa.Column("action_type",            sa.Text, nullable=False, index=True,
                  comment="e.g. SAF_FORWARD_SALE, PPA_EXECUTION, FINANCING_DRAWDOWN"),
        sa.Column("project_id",             sa.Text, nullable=False, index=True),
        sa.Column("initiator_user_id",      sa.Text, nullable=False, index=True),
        sa.Column("initiator_company_id",   sa.Text, nullable=False, index=True),
        sa.Column("initiator_timestamp",    sa.Text, nullable=False,
                  comment="ISO-8601 UTC timestamp of initiator signing"),
        sa.Column("initiator_signature",    sa.Text, nullable=False,
                  comment="hmac-sha256:<hex> in dev; RSA/Ed25519 in Tier 4"),
        sa.Column("approvers_json",         postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="[]",
                  comment="Snapshot of WAE approver decisions at signing time"),
        sa.Column("counterparty_user_id",   sa.Text, nullable=True, index=True),
        sa.Column("counterparty_company_id",sa.Text, nullable=True),
        sa.Column("counterparty_timestamp", sa.Text, nullable=True),
        sa.Column("counterparty_signature", sa.Text, nullable=True),
        sa.Column("payload_hash",           sa.Text, nullable=False,
                  comment="SHA-256 of canonical payload JSON (sorted keys)"),
        sa.Column("record_hash",            sa.Text, nullable=False,
                  comment="SHA-256 of full record excluding this field — tamper detection"),
        sa.Column("status",                 sa.Text, server_default="SIGNED_BY_INITIATOR",
                  comment="SIGNED_BY_INITIATOR | COUNTERSIGNED | DISPUTED"),
        sa.Column("created_at",             sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_commit_project_time", "commitment_records", ["project_id", "created_at"])
    op.create_index("ix_commit_initiator",    "commitment_records", ["initiator_user_id"])
    op.create_index("ix_commit_counterparty", "commitment_records", ["counterparty_user_id"])

    # Immutability: no UPDATE/DELETE — enforced by RLS + application layer
    op.execute("ALTER TABLE commitment_records ENABLE ROW LEVEL SECURITY;")

    # ── user_signing_keys ──────────────────────────────────────────────────────
    op.create_table(
        "user_signing_keys",
        sa.Column("user_id",         sa.Text, primary_key=True),
        sa.Column("algorithm",       sa.Text, nullable=False, server_default="HMAC-SHA256",
                  comment="HMAC-SHA256 (dev) | RSA-2048 | Ed25519 (Tier 4: HSM)"),
        sa.Column("public_key",      sa.Text, nullable=True,
                  comment="PEM-encoded public key — NULL in HMAC-SHA256 mode"),
        sa.Column("key_fingerprint", sa.Text, nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rotated_at",      sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_signing_keys")
    op.drop_index("ix_commit_counterparty", table_name="commitment_records")
    op.drop_index("ix_commit_initiator",    table_name="commitment_records")
    op.drop_index("ix_commit_project_time", table_name="commitment_records")
    op.drop_table("commitment_records")
