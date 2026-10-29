"""Bankability reports: designated executives and in-app notifications.

Revision ID: 076
Revises: 075

JML, 2026-10-28: "each time a premise or a card changes it must trigger a
general process re-evaluation, the reports to designated executives either
pushed or pulled delivered". Every re-evaluation already goes to the event
ledger (bankability.reevaluated). This adds who RECEIVES a change:

  project_report_recipient   the executives designated for a project. None
                             designated → the owner company's EXECUTIVE accounts.
  bankability_notification   one row per recipient per change (state or gate
                             determination) — the push. The pull is the report
                             route, which reads the engine snapshot.

RLS. Recipients: the project's companies read; the owner company or GEX writes.
Notifications: a user reads and marks read only its own (owner axis,
app.current_user_id); any company on the project may write one, because the
party whose action caused the change may not be the owner.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "076"
down_revision: Union[str, None] = "075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
USER = "current_setting('app.current_user_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
ON_PROJECT = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"
OWNER = f"({ADMIN} OR app_company_owns_project(project_id, {ME}))"


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE project_report_recipient (
           project_id text NOT NULL REFERENCES projects(project_id),
           user_id text NOT NULL,
           designated_by text NOT NULL,
           designated_at timestamptz NOT NULL DEFAULT now(),
           PRIMARY KEY (project_id, user_id))""")
    _q("""CREATE TABLE bankability_notification (
           id bigserial PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           user_id text NOT NULL,
           created_at timestamptz NOT NULL DEFAULT now(),
           reason text NOT NULL,
           from_state text, to_state text,
           gate_changes jsonb NOT NULL DEFAULT '[]',
           read_at timestamptz)""")
    _q("CREATE INDEX ix_bankability_notification_user ON bankability_notification (user_id, read_at)")
    for t in ("project_report_recipient", "bankability_notification"):
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY prr_read ON project_report_recipient FOR SELECT USING {ON_PROJECT}")
    _q(f"CREATE POLICY prr_insert ON project_report_recipient FOR INSERT WITH CHECK {OWNER}")
    _q(f"CREATE POLICY prr_update ON project_report_recipient FOR UPDATE USING {OWNER} WITH CHECK {OWNER}")
    _q(f"CREATE POLICY prr_delete ON project_report_recipient FOR DELETE USING {OWNER}")
    _q(f"CREATE POLICY bn_read ON bankability_notification FOR SELECT USING ({ADMIN} OR user_id = {USER})")
    _q(f"CREATE POLICY bn_insert ON bankability_notification FOR INSERT WITH CHECK {ON_PROJECT}")
    _q(f"CREATE POLICY bn_update ON bankability_notification FOR UPDATE "
       f"USING (user_id = {USER}) WITH CHECK (user_id = {USER})")
    _q(f"CREATE POLICY bn_delete ON bankability_notification FOR DELETE USING {ADMIN}")


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS bankability_notification")
    _q("DROP TABLE IF EXISTS project_report_recipient")
