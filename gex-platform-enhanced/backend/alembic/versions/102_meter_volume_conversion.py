"""Meter readings — a converted hydrogen volume keeps the density row it used (G-22).

Revision ID: 102
Revises: 101

Since 098 a hydrogen meter reading in Nm3 was refused, because no density had been agreed.
GreenMesh Phase 2 Step 1 (JML, D8): the density is reference data — a
`reference_parameter` row under `h2_density_normal_0c_101325pa`, proposed with its source
and in force only once approved. app/core/ot_boundary.py converts Nm3 and Nm3/h of hydrogen
to kg with the approved row in force on the interval's first day, and refuses the reading
when there is none. `plant_data.conversion_ref_id` records which row converted the reading,
so a reading can always be traced to the value that turned it into kilograms. NULL for every
reading stated in a mass unit. plant_data stays append-only for gex_app (098).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "102"
down_revision: Union[str, None] = "101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE plant_data ADD COLUMN conversion_ref_id text REFERENCES reference_parameter(ref_id)"))
    conn.execute(sa.text(
        "ALTER TABLE plant_data ADD CONSTRAINT ck_plant_data_conversion_production "
        "CHECK (conversion_ref_id IS NULL OR (data_type = 'PRODUCTION_VOLUME' AND molecule = 'H2'))"))
    bad = conn.execute(sa.text(
        "SELECT string_agg(privilege_type, ',') FROM information_schema.role_table_grants "
        "WHERE grantee = 'gex_app' AND table_name = 'plant_data' "
        "AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')")).scalar()
    if bad:
        raise RuntimeError(f"gex_app holds {bad} on plant_data: append-only is off")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE plant_data DROP CONSTRAINT IF EXISTS ck_plant_data_conversion_production"))
    conn.execute(sa.text("ALTER TABLE plant_data DROP COLUMN IF EXISTS conversion_ref_id"))
