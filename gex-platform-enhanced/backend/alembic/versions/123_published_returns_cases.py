"""Published returns cases — versioned, hashed, immutable (handoff v4, task 10).

Revision ID: 123
Revises: 122
Create Date: 2026-11-17

JML, 2026-11-17: returns cases are published by the OWNER. A case version is
defined by project, scenario, valuation boundary (FULL_PROJECT | FROM_FID), TEA
case and input versions, model version, rules version, evidence snapshot and
publication date. It is versioned, hashed and immutable once published. Every
screen, report and export citing a version shows the same figures; none
recomputes for an audience. Permissions control disclosure only.

  · INSERT-only: a trigger refuses UPDATE and DELETE for every role, and gex_app
    holds SELECT and INSERT only. "Needs review" is DERIVED at read time from what
    changed since publication (evidence fingerprint, rules version, TEA claim);
    nothing is written onto a published version.
  · A new version names the one it supersedes; earlier versions stay readable.
  · RLS (FORCED): read and insert by the owning company or GEX. A reader holding
    the owner's RETURNS share reads through the route, in the owner's tenant
    (the same rule as pre-FID shared reads), and is shown results only.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "123"
down_revision: Union[str, None] = "122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
OWNER = f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}))"
TABLE = "returns_case_version"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q(f"""
        CREATE TABLE {TABLE} (
            version_id            TEXT PRIMARY KEY,
            case_id               TEXT NOT NULL,
            project_id            TEXT NOT NULL REFERENCES projects(project_id),
            owner_tenant_id       TEXT NOT NULL,
            case_name             TEXT NOT NULL,
            version_number        INTEGER NOT NULL CHECK (version_number >= 1),
            scenario              TEXT NOT NULL,
            valuation_boundary    TEXT NOT NULL CHECK (valuation_boundary IN ('FULL_PROJECT', 'FROM_FID')),
            tea_case              JSONB,
            input_versions        JSONB,
            model_version         TEXT NOT NULL,
            rules_version         TEXT,
            evidence_fingerprint  TEXT,
            evidence_evaluated_at TEXT,
            inputs                JSONB NOT NULL,
            results               JSONB NOT NULL,
            sensitivities         JSONB,
            provenance            JSONB NOT NULL,
            governance            JSONB,
            content_sha256        TEXT NOT NULL,
            supersedes_version_id TEXT REFERENCES {TABLE}(version_id),
            published_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            published_by          TEXT NOT NULL,
            UNIQUE (case_id, version_number)
        )""")
    _q(f"CREATE INDEX idx_{TABLE}_project ON {TABLE}(project_id)")
    _q(f"""
        CREATE FUNCTION {TABLE}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'a published returns case is immutable: publish a new version';
        END $$""")
    _q(f"""CREATE TRIGGER {TABLE}_immutable BEFORE UPDATE OR DELETE ON {TABLE}
           FOR EACH ROW EXECUTE FUNCTION {TABLE}_immutable()""")
    _q(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    _q(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY {TABLE}_owner_read ON {TABLE} FOR SELECT USING {OWNER}")
    _q(f"CREATE POLICY {TABLE}_owner_insert ON {TABLE} FOR INSERT WITH CHECK {OWNER}")
    # 031's default privileges hand every new table full DML: only a REVOKE restricts.
    _q(f"REVOKE ALL ON {TABLE} FROM gex_app")
    _q(f"GRANT SELECT, INSERT ON {TABLE} TO gex_app")
    granted = {r[0] for r in _q(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        f"WHERE grantee = 'gex_app' AND table_name = '{TABLE}'")}
    if granted != {"SELECT", "INSERT"}:
        raise RuntimeError(f"gex_app must hold exactly SELECT, INSERT on {TABLE}; holds {sorted(granted)}")


def downgrade() -> None:
    n = _q(f"SELECT count(*) FROM {TABLE}").scalar()
    if n:
        raise RuntimeError(f"{n} published returns case version(s) exist; refusing to drop them. "
                           "Dump the table first.")
    _q(f"DROP TABLE {TABLE}")
    _q(f"DROP FUNCTION {TABLE}_immutable()")
