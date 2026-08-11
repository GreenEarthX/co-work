"""Fuel reference data — slice 6b-3.

Revision ID: 041
Revises: 040

`fuel_catalog` (10) and `fuel_unit_conversions` (120). Reference data: the same
rows for every tenant, keyed by fuel rather than by project.

RLS: enabled with a read-open policy, as `fuel_defaults` got in 035. A table
with RLS off in a schema where everything else has it on reads as an oversight —
the next person cannot tell "deliberately public" from "forgotten". Writes stay
with the app role.

THE FOREIGN KEY IS REAL AND IS CARRIED OVER
-------------------------------------------
`fuel_unit_conversions.fuel_id -> fuel_catalog.fuel_id ON DELETE CASCADE`
actually exists in SQLite here, unlike `package_evidence` in 035 where no
constraint existed and inventing one would have made an FK rejection look like
a copy failure. Preserving a real constraint is not the same as adding one, so
it comes across — including the CASCADE, and the UNIQUE(fuel_id, from_unit,
to_unit) that stops a duplicate conversion rule.

A NAMING COLLISION, DELIBERATELY NOT "RECONCILED"
-------------------------------------------------
`fuel_catalog.specific_energy_value` and
`capital_bridge.FUEL_DEFAULTS[...]["specific_energy_kwh_per_kg_h2"]` both read
as "specific energy" and hold DIFFERENT physical quantities:

  · fuel_catalog  — the fuel's own energy density (LHV): H2 33.3, NH3 5.2,
                    E_METHANOL 5.5, SAF 11.9 kWh/kg. Varies by fuel.
  · FUEL_DEFAULTS — the ELECTROLYSER's consumption per kg of H2 produced:
                    50.0 for ALL fuels, because it is a property of the
                    electrolyser, not of the downstream product.

They are not two sources for one number, so they are NOT merged. Anyone
"reconciling" them would corrupt either the energy content of every fuel or the
production formula fixed on 2026-08-08. A guardrail pins the distinction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fuel_catalog",
        sa.Column("fuel_id", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False, unique=True),
        sa.Column("offered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("legacy_aliases_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("applications_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trading_unit", sa.Text(), nullable=False),
        sa.Column("price_unit", sa.Text(), nullable=False),
        sa.Column("mass_unit", sa.Text(), nullable=False),
        sa.Column("energy_unit", sa.Text(), nullable=False),
        sa.Column("specific_energy_unit", sa.Text(), nullable=False,
                  server_default="kWh/kg",
                  comment="Energy density of the FUEL — not electrolyser consumption"),
        sa.Column("specific_energy_value", sa.Float()),
        sa.Column("capacity_unit", sa.Text(), nullable=False),
        sa.Column("emissions_unit", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text()),
    )

    op.create_table(
        "fuel_unit_conversions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fuel_id", sa.Text(), nullable=False),
        sa.Column("from_unit", sa.Text(), nullable=False),
        sa.Column("to_unit", sa.Text(), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.Column("offset", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.Text(), nullable=False, server_default="system"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["fuel_id"], ["fuel_catalog.fuel_id"],
                                ondelete="CASCADE",
                                name="fk_fuc_fuel"),
        sa.UniqueConstraint("fuel_id", "from_unit", "to_unit",
                            name="uq_fuc_fuel_from_to"),
    )
    op.create_index("idx_fuc_fuel", "fuel_unit_conversions", ["fuel_id"])

    conn = op.get_bind()
    for table in ("fuel_catalog", "fuel_unit_conversions"):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"""
            CREATE POLICY {table}_reference_data ON {table}
            FOR SELECT USING (true)
        """))
        # Writes are admin-only: reference data is curated, not tenant-authored.
        conn.execute(sa.text(f"""
            CREATE POLICY {table}_admin_writes ON {table}
            FOR ALL USING (
                current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN')
        """))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))
    conn.execute(sa.text(
        "GRANT USAGE, SELECT ON SEQUENCE fuel_unit_conversions_id_seq TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("fuel_catalog", "fuel_unit_conversions"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_reference_data ON {table}"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_admin_writes ON {table}"))
    op.drop_table("fuel_unit_conversions")
    op.drop_table("fuel_catalog")
