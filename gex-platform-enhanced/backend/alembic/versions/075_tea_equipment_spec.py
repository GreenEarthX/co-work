"""tea_equipment_spec — GEX's own equipment-train assumptions, under four-eye.

Revision ID: 075
Revises: 074
Create Date: 2026-10-26

The last hole in "all TEA variables in PostgreSQL, editable, four-eye" (JML, point 1).
Three kinds of number were conflated in that request and each needs a different home:

  · GEX POLICY constants (FX rate, plausibility band, MC sigma) -> reference_parameter,
    migrations 072/073. Proposable, approvable, one unit family per key.
  · PUBLISHED literature constants (417 correlations, CEPCI) -> PINNED, not editable,
    migration 074. Editing them would destroy the traceability to Turton/Towler that
    makes a priced number defensible to a lender.
  · GEX's EQUIPMENT TRAIN -> this table. 39 specs across E_METHANOL (12), E_SAF (13)
    and BIO_SAF_HEFA (14): what size each unit is at the 50,000 t/yr reference, and the
    exponent used to scale it. They move every capex directly and were changeable with
    nobody's approval and no record.

Why NOT reference_parameter: that table fixes ONE unit family per parameter_key, and
`base_param` carries eight different units across these 39 rows — measured: area m^2
(9), volume m^3 (7), driver power kW (6), shell mass kg (6), shaft power kW (3),
capacity m^3 (3), flow L/s (3), electric power MWe (2). The unit belongs to the
OpenPyTEA correlation, not to the key, so it has to live per row.

Four-eye is enforced in the DATABASE here, not only in application code:
`ck_tea_equipment_spec_four_eyes` makes an approved row with
`approved_by = proposed_by` impossible. reference_parameter checks that in
`reference_registry.approve` alone, which is bypassable by any other writer.

Seeded from `tea_engine/process_functions.py` as `approved` — these are the values in
force and have priced every basis to date. `proposed_by`/`approved_by` are the two
distinct markers SEED_PROCESS_FUNCTIONS / SEED_APPROVED_IN_FORCE, which satisfies the
constraint and records honestly that no human reviewed them: the marker is how you find
the rows that predate the lifecycle, exactly as SEED_GRANDFATHERED does in auth_users.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "075"
down_revision: Union[str, None] = "074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
_PROPOSER = "SEED_PROCESS_FUNCTIONS"
_APPROVER = "SEED_APPROVED_IN_FORCE"


def upgrade() -> None:
    op.create_table(
        "tea_equipment_spec",
        sa.Column("spec_id", sa.Text(), primary_key=True),
        sa.Column("fuel_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("node", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("equipment_type", sa.Text(), nullable=False),
        sa.Column("material", sa.Text(), nullable=False),
        sa.Column("base_param", sa.Float(), nullable=False),
        # per ROW, not per key: the unit belongs to the OpenPyTEA correlation
        sa.Column("base_param_unit", sa.Text()),
        sa.Column("scale_exp", sa.Float(), nullable=False),
        sa.Column("reference_nameplate_t_per_year", sa.Float(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("proposed_by", sa.Text(), nullable=False),
        sa.Column("proposed_at", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text()),
        sa.Column("approved_at", sa.Text()),
        sa.Column("supersedes_spec_id", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint("state IN ('proposed','approved','superseded','rejected')",
                           name="ck_tea_equipment_spec_state"),
        # Four-eye, in the database: an approved row cannot name its own proposer.
        sa.CheckConstraint("approved_by IS NULL OR approved_by <> proposed_by",
                           name="ck_tea_equipment_spec_four_eyes"),
        sa.CheckConstraint("scale_exp > 0 AND scale_exp <= 1",
                           name="ck_tea_equipment_spec_exp"),
        sa.CheckConstraint("base_param > 0", name="ck_tea_equipment_spec_param"),
    )
    op.create_index("idx_tes_fuel_state", "tea_equipment_spec", ["fuel_id", "state"])
    # one approved spec per (fuel, role): two in force at once would silently double a unit
    op.execute("CREATE UNIQUE INDEX uq_tes_fuel_role_approved ON tea_equipment_spec "
               "(fuel_id, role) WHERE state = 'approved'")

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE tea_equipment_spec ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE tea_equipment_spec FORCE ROW LEVEL SECURITY"))
    # Reference data: readable by all (failing closed would blackhole every TEA run),
    # written by GEX only. No project_id, so no honest tenant policy exists.
    conn.execute(sa.text("CREATE POLICY tea_equipment_spec_read ON tea_equipment_spec "
                         "FOR SELECT USING (true)"))
    for verb in ("INSERT", "UPDATE", "DELETE"):
        clause = "WITH CHECK" if verb == "INSERT" else "USING"
        conn.execute(sa.text(
            f"CREATE POLICY tea_equipment_spec_{verb.lower()} ON tea_equipment_spec "
            f"FOR {verb} {clause} ({ADMIN})"))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE ON tea_equipment_spec TO gex_app"))

    _seed(conn)

    n = conn.execute(sa.text("SELECT count(*) FROM tea_equipment_spec "
                             "WHERE state='approved'")).scalar()
    assert n == 39, f"expected 39 approved specs seeded from the registry, got {n}"


def _seed(conn) -> None:
    """Seed from the code registry so the table starts as the truth in force."""
    import os
    import sys
    from datetime import datetime, timezone

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    import pandas as pd
    import openpytea
    import tea_engine.process_functions as pfx

    cc = pd.read_csv(os.path.join(os.path.dirname(openpytea.__file__),
                                  "data", "cost_correlations.csv"))
    now = datetime.now(timezone.utc).isoformat()

    for fuel_id, pf in sorted(pfx.REGISTRY.items()):
        for spec in (pf.equipment or []):
            m = cc[(cc["category"] == spec.category) & (cc["type"] == spec.type)]
            unit = str(m.iloc[0]["units"]) if len(m) else None
            conn.execute(
                sa.text("""
                    INSERT INTO tea_equipment_spec
                        (spec_id, fuel_id, role, node, category, equipment_type,
                         material, base_param, base_param_unit, scale_exp,
                         reference_nameplate_t_per_year, state,
                         proposed_by, proposed_at, approved_by, approved_at, note)
                    VALUES (:sid, :fuel, :role, :node, :cat, :typ, :mat, :bp, :bpu,
                            :exp, :ref, 'approved', :pby, :at, :aby, :at, :note)
                """),
                {"sid": str(uuid.uuid4()), "fuel": fuel_id, "role": spec.role,
                 "node": spec.node, "cat": spec.category, "typ": spec.type,
                 "mat": spec.material, "bp": float(spec.base_param), "bpu": unit,
                 "exp": float(spec.scale_exp),
                 "ref": float(pfx.REFERENCE_NAMEPLATE_T_YR),
                 "pby": _PROPOSER, "at": now, "aby": _APPROVER,
                 "note": ("In force since before this table existed: the value in "
                          "tea_engine/process_functions.py. No human reviewed it — the "
                          "SEED_* markers are how you find the rows that predate the "
                          "lifecycle. Any change from here needs two different people.")},
            )


def downgrade() -> None:
    conn = op.get_bind()
    for name in ("read", "insert", "update", "delete"):
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS tea_equipment_spec_{name} ON tea_equipment_spec"))
    op.execute("DROP INDEX IF EXISTS uq_tes_fuel_role_approved")
    op.drop_index("idx_tes_fuel_state", table_name="tea_equipment_spec")
    op.drop_table("tea_equipment_spec")
