"""M6, drop 3 of 4: the 078 contract tokens go (Phase 3 of "One contract record").

Revision ID: 090
Revises: 089

085 (Phase 2) folded every project_contract into ONE tb_contract (origin_ref
'project:<project_id>:<kind>') and copied every project_contract_event VERBATIM
into tb_contract_event under hash scheme '078', keyed by its 078 contract id;
since then the 078 tables were read-only history (085 revoked every write) and
the gate engine reads v_engine_contract_terms. On 2026-11-10: 4 contracts and 4
events, all folded.

Upgrade refuses unless every 078 contract has its record and every 078 event its
verbatim copy (same seq, same event_hash), then drops both tables.

Downgrade REBUILDS them from the record, not empty: their DDL as 085 left them
(pg_dump -s at 089: columns, checks, sequences, FKs, policies, FORCED RLS, the
SELECT-only grants), then one project_contract per folded record and one
project_contract_event per scheme-'078' event, with the version's card terms as
terms_json and the 078 sha as terms_sha256. Events appended after the fold
(scheme '2') were never 078's and are not written back.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "090"
down_revision: Union[str, None] = "089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# pg_dump -s -t project_contract -t project_contract_event at 089 (comments, SET lines and "public." removed).
DDL_078 = """
CREATE TABLE project_contract (
    id bigint NOT NULL,
    project_id text NOT NULL,
    kind text NOT NULL,
    counterparty_company_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT project_contract_kind_check CHECK ((kind = ANY (ARRAY['offtake'::text, 'ppa'::text, 'supply'::text, 'epc'::text, 'licence'::text, 'technical'::text, 'model'::text])))
);
ALTER TABLE ONLY project_contract FORCE ROW LEVEL SECURITY;
CREATE SEQUENCE project_contract_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE project_contract_id_seq OWNED BY project_contract.id;
ALTER TABLE ONLY project_contract ALTER COLUMN id SET DEFAULT nextval('project_contract_id_seq'::regclass);
ALTER TABLE ONLY project_contract
    ADD CONSTRAINT project_contract_pkey PRIMARY KEY (id);
ALTER TABLE ONLY project_contract
    ADD CONSTRAINT project_contract_project_id_kind_key UNIQUE (project_id, kind);
ALTER TABLE ONLY project_contract
    ADD CONSTRAINT project_contract_counterparty_company_id_fkey FOREIGN KEY (counterparty_company_id) REFERENCES tenants(company_id);
ALTER TABLE ONLY project_contract
    ADD CONSTRAINT project_contract_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(project_id);
ALTER TABLE project_contract ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_contract_delete ON project_contract FOR DELETE USING ((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text));
CREATE POLICY project_contract_insert ON project_contract FOR INSERT WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
CREATE POLICY project_contract_read ON project_contract FOR SELECT USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
CREATE POLICY project_contract_update ON project_contract FOR UPDATE USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true)))) WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
GRANT SELECT ON TABLE project_contract TO gex_app;
GRANT SELECT,USAGE ON SEQUENCE project_contract_id_seq TO gex_app;

CREATE TABLE project_contract_event (
    id bigint NOT NULL,
    contract_id bigint NOT NULL,
    project_id text NOT NULL,
    seq integer NOT NULL,
    event_type text NOT NULL,
    terms_json jsonb,
    terms_sha256 text,
    actor text NOT NULL,
    company_id text,
    note text,
    prev_hash text,
    event_hash text NOT NULL,
    at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT project_contract_event_event_type_check CHECK ((event_type = ANY (ARRAY['COUNTERPARTY_SET'::text, 'VERSION'::text, 'CONFIRMED'::text, 'DISPUTED'::text])))
);
ALTER TABLE ONLY project_contract_event FORCE ROW LEVEL SECURITY;
CREATE SEQUENCE project_contract_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE project_contract_event_id_seq OWNED BY project_contract_event.id;
ALTER TABLE ONLY project_contract_event ALTER COLUMN id SET DEFAULT nextval('project_contract_event_id_seq'::regclass);
ALTER TABLE ONLY project_contract_event
    ADD CONSTRAINT project_contract_event_contract_id_seq_key UNIQUE (contract_id, seq);
ALTER TABLE ONLY project_contract_event
    ADD CONSTRAINT project_contract_event_pkey PRIMARY KEY (id);
ALTER TABLE ONLY project_contract_event
    ADD CONSTRAINT project_contract_event_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES project_contract(id);
ALTER TABLE ONLY project_contract_event
    ADD CONSTRAINT project_contract_event_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(project_id);
ALTER TABLE project_contract_event ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_contract_event_delete ON project_contract_event FOR DELETE USING ((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text));
CREATE POLICY project_contract_event_insert ON project_contract_event FOR INSERT WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
CREATE POLICY project_contract_event_read ON project_contract_event FOR SELECT USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
GRANT SELECT ON TABLE project_contract_event TO gex_app;
GRANT SELECT,USAGE ON SEQUENCE project_contract_event_id_seq TO gex_app;
"""


def _one(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar()


def upgrade() -> None:
    unfolded = _one("SELECT count(*) FROM project_contract pc WHERE NOT EXISTS (SELECT 1 FROM tb_contract c "
                    "WHERE c.origin_ref = 'project:' || pc.project_id || ':' || pc.kind)")
    assert unfolded == 0, f"{unfolded} 078 contract(s) have no record; run the fold (085) first"
    uncopied = _one("SELECT count(*) FROM project_contract_event e WHERE NOT EXISTS (SELECT 1 FROM tb_contract_event r "
                    "WHERE r.hash_scheme = '078' AND r.legacy_contract_id = e.contract_id "
                    "AND r.seq = e.seq AND r.event_hash = e.event_hash)")
    assert uncopied == 0, f"{uncopied} 078 event(s) have no verbatim copy in tb_contract_event"
    op.get_bind().execute(sa.text("DROP TABLE project_contract_event"))
    op.get_bind().execute(sa.text("DROP TABLE project_contract"))
    assert _one("SELECT count(*) FROM pg_class WHERE relname IN ('project_contract', 'project_contract_event')") == 0


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(DDL_078)
    # 031's DEFAULT PRIVILEGES hand a new table full DML; 085 left these read-only history.
    conn.execute(sa.text("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON project_contract, project_contract_event "
                         "FROM gex_app"))
    conn.execute(sa.text(
        "INSERT INTO project_contract (id, project_id, kind, counterparty_company_id, created_at) "
        "SELECT DISTINCT e.legacy_contract_id, c.project_id, c.kind, c.confirming_company_id, c.created_at "
        "FROM tb_contract_event e JOIN tb_contract c ON c.id = e.contract_id WHERE e.hash_scheme = '078'"))
    conn.execute(sa.text(
        "INSERT INTO project_contract_event (contract_id, project_id, seq, event_type, terms_json, terms_sha256, "
        "actor, company_id, note, prev_hash, event_hash, at) "
        "SELECT e.legacy_contract_id, c.project_id, e.seq, e.event_type, "
        "CASE WHEN e.event_type = 'VERSION' THEN t.card_projection END, e.terms_hash, e.actor, e.company_id, e.note, "
        "e.prev_hash, e.event_hash, e.at FROM tb_contract_event e JOIN tb_contract c ON c.id = e.contract_id "
        "LEFT JOIN tb_contract_version v ON v.id = e.version_id LEFT JOIN tb_terms t ON t.id = v.terms_id "
        "WHERE e.hash_scheme = '078' ORDER BY e.legacy_contract_id, e.seq"))
    for table in ("project_contract", "project_contract_event"):
        conn.execute(sa.text(f"SELECT setval('{table}_id_seq', GREATEST((SELECT max(id) FROM {table}), 1))"))
    held = conn.execute(sa.text("SELECT count(*) FROM information_schema.role_table_grants WHERE grantee = 'gex_app' "
                                "AND table_name IN ('project_contract', 'project_contract_event') "
                                "AND privilege_type <> 'SELECT'")).scalar()
    assert held == 0, "gex_app may write the rebuilt 078 history"
