"""The registry outbox — export only (GreenMesh Phase 2 Step 6; D5, D6).

Revision ID: 111
Revises: 110

Every outbound registry or scheme submission GEX builds is written here, with the payload
and its SHA-256, as `ledger_anchor_outbox` records anchors. D6: GEX does not submit for a
client. The only backend is `none` (REGISTRY_CONNECTOR_BACKEND, config.py): a file is
exported for the party or its certifier to submit, and nothing is sent. Production is not
a configuration value.

Append-only for every role (trigger): an export is never rewritten or removed. The parties
to the contract and GEX read it; only the operator connection writes, after the application
has authorised the exporting party (core/registry_connectors).

No public field-level specification of CertifHy, ISCC, the UDB or the AIB hub was found
(docs/GREENMESH_CONNECTORS_RESEARCH.md), so the only connector is `gex_export_v1`, GEX's own
documented format, not a registry's.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "111"
down_revision: Union[str, None] = "110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _q("""CREATE TABLE registry_outbox (
            id bigserial PRIMARY KEY,
            contract_id uuid NOT NULL REFERENCES tb_contract(id),
            connector text NOT NULL,
            backend text NOT NULL CHECK (backend = 'none'),
            status text NOT NULL CHECK (status = 'EXPORTED'),
            payload jsonb NOT NULL,
            payload_sha256 character(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
            pack_sha256 character(64) NOT NULL,
            exported_path text NOT NULL,
            created_by text NOT NULL,
            company_id text NOT NULL REFERENCES tenants(company_id),
            created_at timestamptz NOT NULL DEFAULT now())""")
    _q("CREATE INDEX ix_registry_outbox_contract ON registry_outbox (contract_id)")
    _q("ALTER TABLE registry_outbox ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE registry_outbox FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY registry_outbox_read ON registry_outbox FOR SELECT USING "
       f"({ADMIN} OR app_tb_contract_party(contract_id, {CURRENT}))")
    _q(f"CREATE POLICY registry_outbox_operator_insert ON registry_outbox FOR INSERT WITH CHECK {ADMIN}")
    _q("REVOKE ALL ON registry_outbox FROM gex_app")
    _q("GRANT SELECT, INSERT ON registry_outbox TO gex_app")
    _q("GRANT USAGE ON SEQUENCE registry_outbox_id_seq TO gex_app")
    _q("""CREATE FUNCTION registry_outbox_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'REGISTRY_OUTBOX_APPEND_ONLY: an export is never changed or removed'
          USING ERRCODE = 'check_violation'; END $$""")
    _q("CREATE TRIGGER registry_outbox_append_only BEFORE UPDATE OR DELETE ON registry_outbox "
       "FOR EACH ROW EXECUTE FUNCTION registry_outbox_append_only()")
    assert _q("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'registry_outbox'").scalar()
    held = set(_q("SELECT privilege_type FROM information_schema.role_table_grants "
                  "WHERE grantee = 'gex_app' AND table_name = 'registry_outbox'").scalars())
    assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on registry_outbox"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM registry_outbox").scalar()
    assert n == 0, f"{n} export(s) recorded; refusing to drop the outbox"
    _q("DROP TABLE registry_outbox")
    _q("DROP FUNCTION IF EXISTS registry_outbox_append_only()")
