"""Canvas, plants and equipment equations — OWNER-scoped, no admin clause.

Revision ID: 050
Revises: 049
Create Date: 2026-09-22

WHAT IS DIFFERENT ABOUT THESE THREE TABLES
------------------------------------------
Every other policy in this schema answers "which COMPANY may see this row".
These three answer "whose own work is this". A canvas document is not a
company asset that colleagues may browse; it is what one person built, and
`canvas_blobs.owner_user_id` / `user_plants.owner_user_id` /
`equipment_equations.owner_user_id` already hold an `auth_users.user_id`.

So the policy compares the owner column to `app.current_user_id`, the GUC bound
on both database paths by `request_tenant` (added immediately before this
migration, precisely so this policy could exist rather than being approximated
by a company one).

THERE IS NO ADMIN CLAUSE. THAT IS THE POINT.
--------------------------------------------
Everywhere else in this schema a policy begins `ADMIN OR …`. Here it does not,
and it must not be "tidied up" to match the others:

  · Making these company-scoped would let colleagues read each other's canvases.
    PostgreSQL makes that easy to write, which is not a reason to grant it —
    it would quietly change GEX's authorization model.
  · Adding `ADMIN OR` would give every holder of `is_platform_admin` a standing
    read over all 500 canvas documents. Support and offboarding are real needs,
    but a permanent capability nobody can see being used is the wrong shape for
    them.

Support, deletion requests and offboarding go through `app/core/break_glass.py`
instead: one named user at a time, a mandatory reason, and a row in `admin_log`
written BEFORE the connection opens. The database default stays closed and the
exception becomes an event somebody can audit.

CONSEQUENCE FOR ANYTHING THAT MOVES THIS DATA
---------------------------------------------
FORCE ROW LEVEL SECURITY binds the table owner too, so `gex_user` cannot read
these rows either without setting `app.current_user_id`. The SQLite→PostgreSQL
copier therefore walks owner by owner, which is the same shape as break-glass
and is deliberate: there is no context in which "all owners at once" is a thing
this schema will hand out.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "050"
down_revision: Union[str, None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

# No ADMIN constant on purpose — see the module docstring. If a future policy
# in this file needs one, that is a decision to take in the open, not a line to
# copy from a neighbouring migration.
OWNER = "owner_user_id = current_setting('app.current_user_id', true)"

TABLES = ("canvas_blobs", "user_plants", "equipment_equations")


def upgrade() -> None:
    op.create_table(
        "canvas_blobs",
        sa.Column("owner_user_id", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), primary_key=True),
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        # The blob itself stays on disk; this is the pointer plus its digest.
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_canvas_owner", "canvas_blobs", ["owner_user_id"])

    op.create_table(
        "user_plants",
        sa.Column("owner_user_id", sa.Text(), primary_key=True),
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "equipment_equations",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("plant_slug", sa.Text(), nullable=False),
        sa.Column("equipment_node_id", sa.Text(), nullable=False),
        sa.Column("equipment_label", sa.Text(), nullable=False, server_default=""),
        sa.Column("equation_id", sa.Text(), nullable=False),
        sa.Column("equation_expression", sa.Text(), nullable=False),
        sa.Column("output_param", sa.Text(), nullable=False),
        sa.Column("variable_bindings", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("owner_user_id", "plant_slug", "equipment_node_id",
                            "equation_id", name="uq_equation_per_node"),
    )
    op.create_index("idx_equations_owner", "equipment_equations", ["owner_user_id"])

    conn = op.get_bind()
    for table in TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY {table}_owner_only ON {table} FOR ALL USING ({OWNER})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_owner_only ON {table}"))
    for table in reversed(TABLES):
        op.drop_table(table)
