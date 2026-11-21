"""What a workbook import declared beside the record it saved (19 Nov).

Revision ID: 126
Revises: 125
Create Date: 2026-11-19

The CFO's workbook (core/cost_workbook.py) saves into GEX's own records: a cost
basis version, a financing case version, the offtake card. Some of what the CFO
states has no column in those records: each offtake term's source and date, the
capital stack being raised behind a financing case. Dropping it would lose what
the CFO told us; inventing columns on the contract record would blur what a
counterparty confirmed with what the producer declared. So it is kept apart:

  · workbook_import  one row per tab saved from a workbook: the file's sha256, the
                     record it saved (target_kind + target_ref + target_sha256), and
                     what was declared beside it (`declared`). INSERT-only for every
                     role (trigger); FORCED RLS, the owning company or GEX.
                     Declared means declared: nothing here is verified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "126"
down_revision: Union[str, None] = "125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
OWNER = f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}))"
T = "workbook_import"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q(f"""
        CREATE TABLE {T} (
            import_id        TEXT PRIMARY KEY,
            project_id       TEXT NOT NULL REFERENCES projects(project_id),
            owner_tenant_id  TEXT NOT NULL,
            tab              TEXT NOT NULL CHECK (tab IN ('cost_basis', 'financing', 'offtake')),
            template_version TEXT NOT NULL,
            file_sha256      TEXT NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
            target_kind      TEXT NOT NULL,
            target_ref       TEXT NOT NULL,
            target_sha256    TEXT,
            declared         JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            imported_by      TEXT NOT NULL,
            imported_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    _q(f"CREATE INDEX idx_{T}_project_tab ON {T}(project_id, tab, imported_at)")
    _q(f"""
        CREATE FUNCTION {T}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'a workbook import is a record and cannot be changed';
        END $$""")
    _q(f"CREATE TRIGGER {T}_immutable BEFORE UPDATE OR DELETE ON {T} FOR EACH ROW EXECUTE FUNCTION {T}_immutable()")
    _q(f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY")
    _q(f"ALTER TABLE {T} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY {T}_owner_read ON {T} FOR SELECT USING {OWNER}")
    _q(f"CREATE POLICY {T}_owner_insert ON {T} FOR INSERT WITH CHECK {OWNER}")
    _q(f"REVOKE ALL ON {T} FROM gex_app")
    _q(f"GRANT SELECT, INSERT ON {T} TO gex_app")
    granted = {r[0] for r in _q("SELECT privilege_type FROM information_schema.role_table_grants "
                                f"WHERE grantee = 'gex_app' AND table_name = '{T}'")}
    if granted != {"SELECT", "INSERT"}:
        raise RuntimeError(f"gex_app must hold exactly SELECT, INSERT on {T}; holds {sorted(granted)}")


def downgrade() -> None:
    n = _q(f"SELECT count(*) FROM {T}").scalar()
    if n:
        raise RuntimeError(f"{n} workbook import(s) exist; refusing to drop them. Dump the table first.")
    _q(f"DROP TABLE {T}")
    _q(f"DROP FUNCTION {T}_immutable()")
