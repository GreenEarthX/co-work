"""Add verification state taxonomy to bankability_evidence

Revision ID: 010
Revises: 005
Create Date: 2026-03-24

Schema changes:
  bankability_evidence  — adds verification_state + verifier columns
  verification_log      — new append-only, RLS-enabled audit table
  ENUM types            — verification_state, offer_firmness,
                          commitment_level, cert_status, score_basis
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── ENUM definitions ──────────────────────────────────────────────────────────

verification_state_enum = postgresql.ENUM(
    "UNVERIFIED", "SUBMITTED", "CONFIRMED", "AUDITED",
    name="verification_state",
    create_type=True,
)

offer_firmness_enum = postgresql.ENUM(
    "INDICATIVE", "HEADS_OF_TERMS", "BINDING",
    name="offer_firmness",
    create_type=True,
)

commitment_level_enum = postgresql.ENUM(
    "MODELLED", "INDICATIVE", "TERM_SHEET", "COMMITTED", "DRAWN",
    name="commitment_level",
    create_type=True,
)

cert_status_enum = postgresql.ENUM(
    "ASPIRATIONAL", "APPLIED", "ASSESSED", "ISSUED",
    name="cert_status",
    create_type=True,
)

score_basis_enum = postgresql.ENUM(
    "SELF_ASSESSED", "PEER_REVIEWED", "IE_CONFIRMED", "AUDITED",
    name="score_basis",
    create_type=True,
)


def upgrade() -> None:
    # ── Create ENUMs ──────────────────────────────────────────────────────────
    verification_state_enum.create(op.get_bind(), checkfirst=True)
    offer_firmness_enum.create(op.get_bind(), checkfirst=True)
    commitment_level_enum.create(op.get_bind(), checkfirst=True)
    cert_status_enum.create(op.get_bind(), checkfirst=True)
    score_basis_enum.create(op.get_bind(), checkfirst=True)

    # ── Extend bankability_evidence ───────────────────────────────────────────
    op.add_column(
        "bankability_evidence",
        sa.Column(
            "verification_state",
            verification_state_enum,
            nullable=False,
            server_default="UNVERIFIED",
            comment="4-level evidence verification state (R0 reform)",
        ),
    )
    op.add_column(
        "bankability_evidence",
        sa.Column("verifier_user_id", sa.Text, nullable=True,
                  comment="GEX user ID of the verifier (internal or external)"),
    )
    op.add_column(
        "bankability_evidence",
        sa.Column("verifier_firm", sa.Text, nullable=True,
                  comment="Organisation name of the verifying party — required for CONFIRMED/AUDITED"),
    )
    op.add_column(
        "bankability_evidence",
        sa.Column("verifier_date", sa.DateTime(timezone=True), nullable=True,
                  comment="Date the verification was completed"),
    )
    op.add_column(
        "bankability_evidence",
        sa.Column("verifier_scope", sa.Text, nullable=True,
                  comment="Scope of review e.g. FEED review, Full audit, Spot check"),
    )
    op.add_column(
        "bankability_evidence",
        sa.Column("verifier_exceptions", sa.Text, nullable=True,
                  comment="Any exceptions, caveats or qualifications noted by verifier"),
    )
    op.add_column(
        "bankability_evidence",
        sa.Column("verifier_reference", sa.Text, nullable=True,
                  comment="Audit report reference number — required for AUDITED state"),
    )

    op.create_index(
        "ix_be_verification_state",
        "bankability_evidence",
        ["verification_state"],
    )

    # ── Create verification_log (immutable, append-only) ──────────────────────
    op.create_table(
        "verification_log",
        sa.Column("log_id",           sa.Text, primary_key=True,
                  comment="UUID — set by application"),
        sa.Column("resource_type",    sa.Text, nullable=False, index=True,
                  comment="e.g. bankability_evidence, marketplace_offer, capital_tranche"),
        sa.Column("resource_id",      sa.Text, nullable=False, index=True),
        sa.Column("previous_state",   verification_state_enum, nullable=True),
        sa.Column("new_state",        verification_state_enum, nullable=False),
        sa.Column("actor_user_id",    sa.Text, nullable=False, index=True),
        sa.Column("verifier_firm",    sa.Text, nullable=True),
        sa.Column("verifier_reference", sa.Text, nullable=True),
        sa.Column("verifier_scope",   sa.Text, nullable=True),
        sa.Column("verifier_exceptions", sa.Text, nullable=True),
        sa.Column("transitioned_at",  sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True,
                  comment="UTC timestamp of the transition — immutable once written"),
    )

    op.create_index(
        "ix_vlog_resource",
        "verification_log",
        ["resource_type", "resource_id", "transitioned_at"],
    )

    # Immutability: RLS prevents UPDATE/DELETE — enforced at DB + application layer
    op.execute("ALTER TABLE verification_log ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY verification_log_insert_only ON verification_log
            FOR INSERT WITH CHECK (true);
        """
    )
    op.execute(
        """
        CREATE POLICY verification_log_select ON verification_log
            FOR SELECT USING (true);
        """
    )

    # ── Add offer_firmness to marketplace_offers (if table exists) ────────────
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'marketplace_offers'
            ) THEN
                ALTER TABLE marketplace_offers
                    ADD COLUMN IF NOT EXISTS offer_firmness offer_firmness
                    NOT NULL DEFAULT 'INDICATIVE';
            END IF;
        END$$;
        """
    )

    # ── Add commitment_level to capital_stack_tranches (if table exists) ─────
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'capital_stack_tranches'
            ) THEN
                ALTER TABLE capital_stack_tranches
                    ADD COLUMN IF NOT EXISTS commitment_level commitment_level
                    NOT NULL DEFAULT 'MODELLED';
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # Remove policies and RLS
    op.execute("DROP POLICY IF EXISTS verification_log_select ON verification_log;")
    op.execute("DROP POLICY IF EXISTS verification_log_insert_only ON verification_log;")

    op.drop_index("ix_vlog_resource", table_name="verification_log")
    op.drop_table("verification_log")

    op.drop_index("ix_be_verification_state", table_name="bankability_evidence")
    for col in [
        "verifier_reference", "verifier_exceptions", "verifier_scope",
        "verifier_date", "verifier_firm", "verifier_user_id", "verification_state",
    ]:
        op.drop_column("bankability_evidence", col)

    score_basis_enum.drop(op.get_bind(), checkfirst=True)
    cert_status_enum.drop(op.get_bind(), checkfirst=True)
    commitment_level_enum.drop(op.get_bind(), checkfirst=True)
    offer_firmness_enum.drop(op.get_bind(), checkfirst=True)
    verification_state_enum.drop(op.get_bind(), checkfirst=True)
