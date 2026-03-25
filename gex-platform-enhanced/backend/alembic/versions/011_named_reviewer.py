"""Add named reviewer fields to workflow_states

Revision ID: 011
Revises: 010
Create Date: 2026-03-24

Changes:
  workflow_states — reviewer_user_id, reviewer_name, reviewer_title,
                    review_scope, review_date
  Constraint: state REVIEWED or EXPORTED requires reviewer_user_id NOT NULL
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REVIEW_SCOPE_ENUM = sa.Enum(
    "FULL_REVIEW", "SPOT_CHECK", "METHODOLOGY_ONLY",
    name="review_scope_type",
)


def upgrade() -> None:
    REVIEW_SCOPE_ENUM.create(op.get_bind(), checkfirst=True)

    # ── Add reviewer columns to workflow_states ───────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'workflow_states'
            ) THEN
                ALTER TABLE workflow_states
                    ADD COLUMN IF NOT EXISTS reviewer_user_id  UUID,
                    ADD COLUMN IF NOT EXISTS reviewer_name     VARCHAR(200),
                    ADD COLUMN IF NOT EXISTS reviewer_title    VARCHAR(200),
                    ADD COLUMN IF NOT EXISTS review_scope      review_scope_type,
                    ADD COLUMN IF NOT EXISTS review_date       TIMESTAMPTZ;

                -- Enforce: REVIEWED state requires reviewer identity
                ALTER TABLE workflow_states
                    DROP CONSTRAINT IF EXISTS reviewed_needs_reviewer;
                ALTER TABLE workflow_states
                    ADD CONSTRAINT reviewed_needs_reviewer
                    CHECK (
                        state NOT IN ('REVIEWED', 'EXPORTED')
                        OR reviewer_user_id IS NOT NULL
                    );
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'workflow_states'
            ) THEN
                ALTER TABLE workflow_states
                    DROP CONSTRAINT IF EXISTS reviewed_needs_reviewer;
                ALTER TABLE workflow_states
                    DROP COLUMN IF EXISTS review_date,
                    DROP COLUMN IF EXISTS review_scope,
                    DROP COLUMN IF EXISTS reviewer_title,
                    DROP COLUMN IF EXISTS reviewer_name,
                    DROP COLUMN IF EXISTS reviewer_user_id;
            END IF;
        END$$;
        """
    )
    REVIEW_SCOPE_ENUM.drop(op.get_bind(), checkfirst=True)
