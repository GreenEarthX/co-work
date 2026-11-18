"""The calculation chain: saved cost basis -> reviewed TEA -> financing case -> returns (18 Nov).

Revision ID: 124
Revises: 123
Create Date: 2026-11-18

JML, 2026-11-18: "complete and demonstrate one project from saved Cost Basis
through reviewed TEA, financing and published Returns". Before this, no link
existed: the Cost Basis screen could not save, a TEA run named no cost basis,
nothing recorded a financing case, and a returns version carried whatever the
caller typed as its TEA case and input versions.

  · cost_basis_version      a saved Cost Basis: the configuration AND the result
                            the server recomputed from it, hashed. INSERT-only.
  · financing_case_version  debt, rate, tenor, grant and their sources, on ONE
                            reviewed TEA base case, hashed. INSERT-only.
  · model_base_case         + cost_basis_version_id / cost_basis_sha256 (the saved
                            version a run was priced from), run_by (who ran it),
                            review_basis / reviewed_by_company / reviewed_at /
                            review_conditions (who reviewed it, on what standing).

Both new tables: FORCED RLS, read and insert by the owning company or GEX only;
gex_app holds SELECT and INSERT, and a trigger refuses UPDATE and DELETE for every
role. A shared reader never reads these tables: it reads the returns version,
which cites them by id and hash.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "124"
down_revision: Union[str, None] = "123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
OWNER = f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}))"
TABLES = ("cost_basis_version", "financing_case_version")
MBC_COLUMNS = (("cost_basis_version_id", "TEXT"), ("cost_basis_sha256", "TEXT"), ("run_by", "TEXT"),
               ("review_basis", "TEXT"), ("reviewed_by_company", "TEXT"), ("reviewed_at", "TEXT"),
               ("review_conditions", "JSONB"))


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _lock(table: str) -> None:
    _q(f"""
        CREATE FUNCTION {table}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '{table} is immutable: save a new version';
        END $$""")
    _q(f"""CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table}
           FOR EACH ROW EXECUTE FUNCTION {table}_immutable()""")
    _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY {table}_owner_read ON {table} FOR SELECT USING {OWNER}")
    _q(f"CREATE POLICY {table}_owner_insert ON {table} FOR INSERT WITH CHECK {OWNER}")
    # 031's default privileges hand every new table full DML: only a REVOKE restricts.
    _q(f"REVOKE ALL ON {table} FROM gex_app")
    _q(f"GRANT SELECT, INSERT ON {table} TO gex_app")
    granted = {r[0] for r in _q(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        f"WHERE grantee = 'gex_app' AND table_name = '{table}'")}
    if granted != {"SELECT", "INSERT"}:
        raise RuntimeError(f"gex_app must hold exactly SELECT, INSERT on {table}; holds {sorted(granted)}")


def upgrade() -> None:
    _q("""
        CREATE TABLE cost_basis_version (
            version_id        TEXT PRIMARY KEY,
            project_id        TEXT NOT NULL REFERENCES projects(project_id),
            owner_tenant_id   TEXT NOT NULL,
            version_number    INTEGER NOT NULL CHECK (version_number >= 1),
            molecule          TEXT NOT NULL,
            configuration     JSONB NOT NULL,
            result            JSONB NOT NULL,
            catalogue_sha256  TEXT NOT NULL,
            content_sha256    TEXT NOT NULL,
            supersedes_version_id TEXT REFERENCES cost_basis_version(version_id),
            saved_by          TEXT NOT NULL,
            saved_by_function TEXT,
            saved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (project_id, version_number)
        )""")
    _q("""
        CREATE TABLE financing_case_version (
            version_id        TEXT PRIMARY KEY,
            project_id        TEXT NOT NULL REFERENCES projects(project_id),
            owner_tenant_id   TEXT NOT NULL,
            version_number    INTEGER NOT NULL CHECK (version_number >= 1),
            tea_claim_id      TEXT NOT NULL,
            tea_cost_basis_hash TEXT NOT NULL,
            fci_eur           DOUBLE PRECISION NOT NULL CHECK (fci_eur > 0),
            debt_eur          DOUBLE PRECISION NOT NULL CHECK (debt_eur >= 0),
            interest_rate     DOUBLE PRECISION NOT NULL CHECK (interest_rate >= 0),
            debt_tenor_years  INTEGER NOT NULL CHECK (debt_tenor_years >= 0),
            grant_eur         DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (grant_eur >= 0),
            terms             JSONB NOT NULL,
            content_sha256    TEXT NOT NULL,
            supersedes_version_id TEXT REFERENCES financing_case_version(version_id),
            saved_by          TEXT NOT NULL,
            saved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (project_id, version_number),
            CHECK (debt_eur + grant_eur <= fci_eur)
        )""")
    for t in TABLES:
        _q(f"CREATE INDEX idx_{t}_project ON {t}(project_id)")
        _lock(t)
    for name, typ in MBC_COLUMNS:
        _q(f"ALTER TABLE model_base_case ADD COLUMN {name} {typ}")


def downgrade() -> None:
    for t in TABLES:
        n = _q(f"SELECT count(*) FROM {t}").scalar()
        if n:
            raise RuntimeError(f"{n} row(s) in {t}; refusing to drop them. Dump the table first.")
    linked = _q("SELECT count(*) FROM model_base_case WHERE cost_basis_version_id IS NOT NULL").scalar()
    if linked:
        raise RuntimeError(f"{linked} base case(s) cite a saved cost basis; refusing to drop the link.")
    for name, _ in MBC_COLUMNS:
        _q(f"ALTER TABLE model_base_case DROP COLUMN {name}")
    for t in reversed(TABLES):
        _q(f"DROP TABLE {t}")
        _q(f"DROP FUNCTION {t}_immutable()")
