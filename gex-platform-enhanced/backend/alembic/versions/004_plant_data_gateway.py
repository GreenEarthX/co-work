"""Add OT/IT boundary tables: plant data and gateway registry

Revision ID: 004
Revises: 003
Create Date: 2026-03-17

Tables added:
  ot_gateways        — Registered OT gateways with IP allowlists
  plant_data_records — Inbound plant telemetry (append-only, immutable)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ot_gateways ───────────────────────────────────────────────────────────
    # Domain 4: OT/IT Boundary — registered inbound gateways
    op.create_table(
        "ot_gateways",
        sa.Column("id",              sa.Text, primary_key=True,
                  comment="e.g. gw-breizh-001"),
        sa.Column("project_id",      sa.Text, nullable=False, index=True),
        sa.Column("name",            sa.Text, nullable=False),
        sa.Column("location",        sa.Text, nullable=True),
        sa.Column("allowed_ips",     postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="[]",
                  comment="IP/CIDR list — empty means any IP allowed (dev only)"),
        sa.Column("allowed_data_types", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="[]",
                  comment="Subset of ALLOWED_DATA_TYPES this gateway may push"),
        sa.Column("cert_fingerprint",sa.Text, nullable=True,
                  comment="mTLS cert SHA-256 fingerprint (production)"),
        sa.Column("active",          sa.Boolean, server_default="true"),
        sa.Column("last_seen_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_gateways_project", "ot_gateways", ["project_id"])

    # ── plant_data_records — append-only ─────────────────────────────────────
    op.create_table(
        "plant_data_records",
        sa.Column("id",              sa.Text, primary_key=True, comment="UUID"),
        sa.Column("project_id",      sa.Text, nullable=False, index=True),
        sa.Column("gateway_id",      sa.Text, nullable=False, index=True),
        sa.Column("data_type",       sa.Text, nullable=False, index=True,
                  comment="PRODUCTION_VOLUME | POWER_CONSUMPTION | ELECTROLYSER_EFFICIENCY | "
                          "QUALITY_CERTIFICATE | METERED_DELIVERY | PLANT_STATUS | ALARM_EVENT | "
                          "GHG_MEASUREMENT"),
        sa.Column("payload_json",    postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False,
                  comment="Full OT payload — never overwritten"),
        sa.Column("sha256_hash",     sa.Text, nullable=False,
                  comment="SHA-256 of canonical payload JSON — integrity check"),
        sa.Column("source_ip",       sa.Text, nullable=True),
        sa.Column("received_at",     sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    # Composite index for typical CISO/producer query pattern
    op.create_index(
        "ix_plant_data_project_type_time",
        "plant_data_records",
        ["project_id", "data_type", "received_at"],
    )
    # Immutability enforced at application layer; RLS ensures no cross-company reads
    op.execute("ALTER TABLE plant_data_records ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_plant_data_project_type_time", table_name="plant_data_records")
    op.drop_table("plant_data_records")
    op.drop_index("ix_gateways_project", table_name="ot_gateways")
    op.drop_table("ot_gateways")
