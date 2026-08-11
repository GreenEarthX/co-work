"""Hash-chained domain ledgers — slice 6b-5.

Revision ID: 043
Revises: 042

Seven append-only ledgers carrying prev_hash/event_hash, all EMPTY today.

Empty is the cheap moment to move a chain — the same argument that made the
token-retirement fix and the event-store lock cheap. Each is verified in
PostgreSQL by writing a chain, validating it, then tampering and confirming
detection, rather than assuming the digest reproduces across stores.

`project_events` is ALSO chained but is referenced nowhere in app/ — excluded
as a 6b-7 decision rather than migrated into apparent life.

GENERATED FROM THE LIVE SQLITE SCHEMAS, then reviewed. Hand-writing 7 tables
invites transcription errors; the generator reads PRAGMA table_info and the
stored DDL, so column names, NOT NULLs, composite primary keys, AUTOINCREMENT
and UNIQUE(...) constraints come from the source rather than from memory.

Type fidelity as in every prior slice: timestamps stay TEXT, booleans stay
INTEGER. Storage moves; the type system does not, so a failure cannot be both.

EXCLUDED — the 12 tables with no reference anywhere in app/ (no DDL, no query):
covenant_compliance, drawdown_tranches, equity_contributions, financial_metrics,
pre_cod_metric_snapshots, project_events, project_stakeholders, project_states,
reserve_accounts, service_calls, state_transitions, workflow_checkpoints.
Migrating a dead table makes it look alive. They are slice 6b-7's decision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"

PROJECT_SCOPED = ['carbon_attribution_event_log', 'dfi_criteria_events', 'drawdown_schedule_events', 'settlement_event_log', 'sovereign_instrument_events', 'spend_wave_events']
ALL_TABLES = ['carbon_attribution_event_log', 'dfi_criteria_events', 'drawdown_schedule_events', 'mass_balance_allocations', 'settlement_event_log', 'sovereign_instrument_events', 'spend_wave_events']
SEQUENCES = []


def upgrade() -> None:
    op.create_table(
        "carbon_attribution_event_log",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("attribution_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "dfi_criteria_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("criterion_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "drawdown_schedule_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("drawdown_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "mass_balance_allocations",
        sa.Column("allocation_id", sa.Text(), primary_key=True),
        sa.Column("lot_id", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("volume_kg", sa.Float(), nullable=False),
        sa.Column("allocated_by", sa.Text(), nullable=False),
        sa.Column("allocation_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "settlement_event_log",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("settlement_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "sovereign_instrument_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "spend_wave_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("spend_wave_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    conn = op.get_bind()
    for table in ALL_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        if table in PROJECT_SCOPED:
            using = (f"{ADMIN} OR app_company_owns_project(project_id, {ME}) "
                     f"OR app_company_has_project_access(project_id, {ME})")
        else:
            # No project_id: no honest tenant policy exists, so admin-only
            # rather than open. Same reasoning as the tb_* tables in 036 —
            # a policy that only appears to isolate is worse than none.
            using = ADMIN
        conn.execute(sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ({using})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))
    for t in SEQUENCES:
        conn.execute(sa.text(
            f"GRANT USAGE, SELECT ON SEQUENCE {t}_id_seq TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ALL_TABLES:
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    for table in reversed(ALL_TABLES):
        op.drop_table(table)
