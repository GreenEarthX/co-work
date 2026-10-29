"""Contract tokens: the counterparty confirms the terms the engine compares.

Revision ID: 078
Revises: 077

JML, 2026-10-28. The cross-contract checks (C1–C10) and the offtake / EPC
ladders read the commitment cards — terms the project OWNER typed, with no
document and no other party. Now each contract of a project has a TOKEN: an
append-only, hash-chained log of its versions and of the other party's
confirmations. "A change means a modification on the token": a card edit is a
new version on the token. Only terms in a version CONFIRMED by the counterparty
reach the engine. The producer's own plan — planned output, requirements,
schedule (kind `technical`) and model inputs (kind `model`) — is confirmed by an
appointed independent reviewer instead. The counterparty's confirmation also verifies the contract's own
instrument evidence — an independent verifier may exist, but is not required
for a contract.

  project_contract        one per (project, kind): its counterparty company
  project_contract_event  COUNTERPARTY_SET | VERSION | CONFIRMED | DISPUTED,
                          each carrying sha256(prev event hash + content)

RLS: the project's companies read and append; nobody rewrites an event.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "078"
down_revision: Union[str, None] = "077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
ON_PROJECT = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"
KINDS = ("offtake", "ppa", "supply", "epc", "licence", "technical", "model")


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    _q(f"""CREATE TABLE project_contract (
            id bigserial PRIMARY KEY,
            project_id text NOT NULL REFERENCES projects(project_id),
            kind text NOT NULL CHECK (kind IN ({kinds})),
            counterparty_company_id text REFERENCES tenants(company_id),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (project_id, kind))""")
    _q("""CREATE TABLE project_contract_event (
            id bigserial PRIMARY KEY,
            contract_id bigint NOT NULL REFERENCES project_contract(id),
            project_id text NOT NULL REFERENCES projects(project_id),
            seq integer NOT NULL,
            event_type text NOT NULL CHECK (event_type IN ('COUNTERPARTY_SET', 'VERSION', 'CONFIRMED', 'DISPUTED')),
            terms_json jsonb,
            terms_sha256 text,
            actor text NOT NULL,
            company_id text,
            note text,
            prev_hash text,
            event_hash text NOT NULL,
            at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (contract_id, seq))""")
    for t in ("project_contract", "project_contract_event"):
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING {ON_PROJECT}")
        _q(f"CREATE POLICY {t}_insert ON {t} FOR INSERT WITH CHECK {ON_PROJECT}")
        _q(f"CREATE POLICY {t}_delete ON {t} FOR DELETE USING {ADMIN}")
    _q(f"CREATE POLICY project_contract_update ON project_contract FOR UPDATE USING {ON_PROJECT} WITH CHECK {ON_PROJECT}")
    # The token is append-only: no event is ever rewritten or removed by the runtime.
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON project_contract_event FROM gex_app")


def downgrade() -> None:
    _q("DROP TABLE IF EXISTS project_contract_event")
    _q("DROP TABLE IF EXISTS project_contract")
