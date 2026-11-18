"""Withdrawal from reliance of a published returns version; the TEA's exact inputs (18 Nov).

Revision ID: 125
Revises: 124
Create Date: 2026-11-18

JML, 18 Nov 2026, on returns version v1 of North Sea e-Methanol: "Revoke active
access and mark v1 withdrawn from reliance. Preserve its immutable contents and
audit history." A published version cannot change (123), so withdrawal is its own
record:

  · returns_case_withdrawal  one row per withdrawn version: why, by whom, when.
                             INSERT-only for every role (trigger); FORCED RLS, the
                             owning company or GEX. A withdrawn version is shown to
                             its owner with the withdrawal, and to nobody else.
  · model_base_case.tea_inputs  the request the TEA engine received, the exact
                             OpenPyTEA config, every OpenPyTEA default that still
                             applied, and the calculation boundary. v1's TEA used
                             defaults nobody could see; this keeps them on the record.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "125"
down_revision: Union[str, None] = "124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
OWNER = f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}))"
T = "returns_case_withdrawal"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q(f"""
        CREATE TABLE {T} (
            version_id      TEXT PRIMARY KEY REFERENCES returns_case_version(version_id),
            project_id      TEXT NOT NULL REFERENCES projects(project_id),
            owner_tenant_id TEXT NOT NULL,
            reason          TEXT NOT NULL CHECK (length(trim(reason)) > 0),
            withdrawn_by    TEXT NOT NULL,
            shares_revoked  JSONB NOT NULL DEFAULT '[]'::jsonb,
            withdrawn_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    _q(f"CREATE INDEX idx_{T}_project ON {T}(project_id)")
    _q(f"""
        CREATE FUNCTION {T}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'a withdrawal is permanent and cannot be changed';
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
    _q("ALTER TABLE model_base_case ADD COLUMN tea_inputs JSONB")


def downgrade() -> None:
    n = _q(f"SELECT count(*) FROM {T}").scalar()
    if n:
        raise RuntimeError(f"{n} withdrawal(s) exist; refusing to drop them. Dump the table first.")
    kept = _q("SELECT count(*) FROM model_base_case WHERE tea_inputs IS NOT NULL").scalar()
    if kept:
        raise RuntimeError(f"{kept} base case(s) carry their TEA inputs; refusing to drop them.")
    _q("ALTER TABLE model_base_case DROP COLUMN tea_inputs")
    _q(f"DROP TABLE {T}")
    _q(f"DROP FUNCTION {T}_immutable()")
