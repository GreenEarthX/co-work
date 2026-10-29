"""tea_correlation_set — record which published cost data GEX has reviewed.

Revision ID: 074
Revises: 073
Create Date: 2026-10-26

072/073 moved GEX's own TEA assumptions into `reference_parameter` under four-eye.
OpenPyTEA's 417 published cost correlations (1,291 fitted coefficients, Turton /
Towler & Sinnott / Seider) and its CEPCI series are a different kind of thing: they are
literature constants and must NOT be editable, because editing them destroys the
traceability that makes a priced number defensible to a lender. They are PINNED instead.

`tea_engine/correlation_set.py` fingerprints the data actually in force — raw correlation
file bytes plus the EFFECTIVE CEPCI series, i.e. after `cepci_extension` injects the
years openpytea omits (1987 today) — and `cost_basis_hash` now includes that hash. The
engine version alone was not enough: two installs of the same version can carry
different data (a vendored tree, a patched wheel, a local build), and a `pip install`
can replace the files without anything in this repo changing.

This table is the review record, not the data. A row says "GEX has looked at this exact
set and accepted it for pricing". `state` is deliberately governed the same way the
registry governs a value, so accepting a NEW upstream data set is a decision someone
makes rather than something that happens silently on upgrade. A basis priced by a set
with no row here is still produced — refusing would take TEA offline on an upgrade —
but the bridge flags it as unreviewed.

Not RLS-scoped per tenant: a correlation set is platform reference data, the same call
made for fuel_catalog and approval_policies. It carries no project_id, so per the
tail-slice guardrails a tenant policy would only appear to isolate; it is admin-write,
readable by all, and failing closed here would blackhole every TEA run.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "074"
down_revision: Union[str, None] = "073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"


def upgrade() -> None:
    op.create_table(
        "tea_correlation_set",
        sa.Column("set_hash", sa.Text(), primary_key=True),
        sa.Column("openpytea_version", sa.Text()),
        sa.Column("correlations", sa.Integer()),
        sa.Column("cepci_year_min", sa.Integer()),
        sa.Column("cepci_year_max", sa.Integer()),
        sa.Column("gex_supplied_cepci_years", sa.Text()),
        sa.Column("components_json", sa.Text()),
        # review lifecycle — accepting a new upstream data set is a DECISION
        sa.Column("state", sa.Text(), nullable=False, server_default="unreviewed"),
        sa.Column("first_seen_at", sa.Text(), nullable=False),
        sa.Column("first_seen_project", sa.Text()),
        sa.Column("reviewed_by", sa.Text()),
        sa.Column("reviewed_at", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint("state IN ('unreviewed','accepted','rejected')",
                           name="ck_tea_correlation_set_state"),
    )
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE tea_correlation_set ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE tea_correlation_set FORCE ROW LEVEL SECURITY"))
    # Readable by all (reference data; failing closed would blackhole every TEA run),
    # written by GEX only. No project_id, so no honest tenant policy exists.
    conn.execute(sa.text(
        "CREATE POLICY tea_correlation_set_read ON tea_correlation_set "
        "FOR SELECT USING (true)"))
    for verb in ("INSERT", "UPDATE", "DELETE"):
        clause = "WITH CHECK" if verb == "INSERT" else "USING"
        conn.execute(sa.text(
            f"CREATE POLICY tea_correlation_set_{verb.lower()} ON tea_correlation_set "
            f"FOR {verb} {clause} ({ADMIN})"))
    conn.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE ON tea_correlation_set TO gex_app"))

    got = conn.execute(sa.text(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname = 'tea_correlation_set'")).fetchone()
    assert got and got[0] and got[1], "RLS must be enabled AND forced"


def downgrade() -> None:
    conn = op.get_bind()
    for name in ("read", "insert", "update", "delete"):
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS tea_correlation_set_{name} ON tea_correlation_set"))
    op.drop_table("tea_correlation_set")
