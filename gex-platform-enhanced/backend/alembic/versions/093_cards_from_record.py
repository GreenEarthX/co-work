"""The commitment cards become a view over the contract record (Phase 3 of "One contract record", Q9).

Revision ID: 093
Revises: 092

Phase 0 Q9 (JML 2026-11-06): the card becomes a view over the record — each
contract kind's latest version, confirmed or not — so the typed card and the record
cannot diverge; an edit proposes a new version; commitment_terms and
commitment_terms_events are retired, the record's chain replacing the event log,
and 058's UPDATE grant goes with the table. Since Phase 2 every card save already
wrote its versions in the same transaction (085), so the record holds every card.

Upgrade refuses unless, for every project with a card, the view rebuilt from the
record (core/contract_tokens.card_terms) equals commitment_terms exactly — then
drops commitment_terms. commitment_terms_events is dropped when empty (0 rows on
dev, 2026-11-10); a database that holds history keeps it, renamed
commitment_terms_events_retired and read-only, rather than losing it.

Downgrade rebuilds both tables as 092 left them (pg_dump -s: columns, sequence,
the 058 policy, FORCED RLS, grants) and refills commitment_terms from the view, so
the card store returns with the cards it had.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "093"
down_revision: Union[str, None] = "092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# pg_dump -s at 092 (comments, SET lines, OWNER lines and "public." removed).
COMMITMENT_TERMS_DDL = """
CREATE TABLE commitment_terms (
    id integer NOT NULL,
    project_id text NOT NULL,
    card_type text NOT NULL,
    terms_json text NOT NULL,
    updated_by text,
    updated_at text
);
ALTER TABLE ONLY commitment_terms FORCE ROW LEVEL SECURITY;
CREATE SEQUENCE commitment_terms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE commitment_terms_id_seq OWNED BY commitment_terms.id;
ALTER TABLE ONLY commitment_terms ALTER COLUMN id SET DEFAULT nextval('commitment_terms_id_seq'::regclass);
ALTER TABLE ONLY commitment_terms
    ADD CONSTRAINT commitment_terms_pkey PRIMARY KEY (id);
ALTER TABLE ONLY commitment_terms
    ADD CONSTRAINT uq_commitment_terms_project_card UNIQUE (project_id, card_type);
CREATE INDEX idx_commitment_terms_project ON commitment_terms USING btree (project_id);
ALTER TABLE commitment_terms ENABLE ROW LEVEL SECURITY;
CREATE POLICY commitment_terms_tenant_isolation ON commitment_terms USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
GRANT SELECT,INSERT,UPDATE ON TABLE commitment_terms TO gex_app;
GRANT ALL ON TABLE commitment_terms TO gex_admin;
GRANT SELECT,USAGE ON SEQUENCE commitment_terms_id_seq TO gex_app;
GRANT ALL ON SEQUENCE commitment_terms_id_seq TO gex_admin;
"""
COMMITMENT_TERMS_EVENTS_DDL = """
CREATE TABLE commitment_terms_events (
    id integer NOT NULL,
    project_id text NOT NULL,
    card_type text NOT NULL,
    old_json text,
    new_json text NOT NULL,
    actor text NOT NULL,
    at text NOT NULL
);
ALTER TABLE ONLY commitment_terms_events FORCE ROW LEVEL SECURITY;
CREATE SEQUENCE commitment_terms_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE commitment_terms_events_id_seq OWNED BY commitment_terms_events.id;
ALTER TABLE ONLY commitment_terms_events ALTER COLUMN id SET DEFAULT nextval('commitment_terms_events_id_seq'::regclass);
ALTER TABLE ONLY commitment_terms_events
    ADD CONSTRAINT commitment_terms_events_pkey PRIMARY KEY (id);
CREATE INDEX idx_commitment_terms_events_project ON commitment_terms_events USING btree (project_id);
ALTER TABLE commitment_terms_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY commitment_terms_events_tenant_isolation ON commitment_terms_events USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true))));
GRANT SELECT,INSERT ON TABLE commitment_terms_events TO gex_app;
GRANT ALL ON TABLE commitment_terms_events TO gex_admin;
GRANT SELECT,USAGE ON SEQUENCE commitment_terms_events_id_seq TO gex_app;
GRANT ALL ON SEQUENCE commitment_terms_events_id_seq TO gex_admin;
"""


def _conn():
    from app.trading_book.migrate.fold_contract_tokens import SAConnection

    return SAConnection(op.get_bind())


def _one(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar()


def upgrade() -> None:
    from app.core.contract_tokens import card_terms

    conn = op.get_bind()
    stored: dict = {}
    for project_id, card_type, terms_json in conn.execute(sa.text(
            "SELECT project_id, card_type, terms_json FROM commitment_terms")).fetchall():
        stored.setdefault(project_id, {})[card_type] = json.loads(terms_json or "{}")
    differ = []
    for project_id, cards in stored.items():
        view = card_terms(project_id, conn=_conn())
        want = {k: v for k, v in cards.items() if v}
        got = {k: v for k, v in view.items() if v}
        if got != want:
            differ.append(project_id)
    assert not differ, (f"the record does not hold these projects' cards as commitment_terms does: {differ}. "
                        "Re-save their cards (each save writes its versions) before retiring the table.")
    conn.execute(sa.text("DROP TABLE commitment_terms"))
    if _one("SELECT count(*) FROM commitment_terms_events") == 0:
        conn.execute(sa.text("DROP TABLE commitment_terms_events"))
    else:
        conn.execute(sa.text("ALTER TABLE commitment_terms_events RENAME TO commitment_terms_events_retired"))
        conn.execute(sa.text("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON commitment_terms_events_retired FROM gex_app"))


def downgrade() -> None:
    from app.core.contract_tokens import card_view

    conn = op.get_bind()
    conn.exec_driver_sql(COMMITMENT_TERMS_DDL)
    if _one("SELECT to_regclass('public.commitment_terms_events_retired')") is not None:
        conn.execute(sa.text("ALTER TABLE commitment_terms_events_retired RENAME TO commitment_terms_events"))
        conn.execute(sa.text("GRANT SELECT, INSERT ON commitment_terms_events TO gex_app"))
    else:
        conn.exec_driver_sql(COMMITMENT_TERMS_EVENTS_DDL)
    # 031's DEFAULT PRIVILEGES hand a new table full DML; 058 granted exactly these.
    conn.execute(sa.text("REVOKE ALL ON commitment_terms, commitment_terms_events FROM gex_app"))
    conn.execute(sa.text("GRANT SELECT, INSERT, UPDATE ON commitment_terms TO gex_app"))
    conn.execute(sa.text("GRANT SELECT, INSERT ON commitment_terms_events TO gex_app"))
    projects = [r[0] for r in conn.execute(sa.text(
        "SELECT DISTINCT project_id FROM tb_contract WHERE origin_ref LIKE :p AND project_id IS NOT NULL"),
        {"p": "project:%"}).fetchall()]
    for project_id in projects:
        for card_type, card in card_view(project_id, conn=_conn()).items():
            conn.execute(sa.text("INSERT INTO commitment_terms (project_id, card_type, terms_json, updated_by, "
                                 "updated_at) VALUES (:p, :c, :t, :b, :a)"),
                         {"p": project_id, "c": card_type, "t": json.dumps(card["terms"], sort_keys=True),
                          "b": card["updated_by"], "a": card["updated_at"]})
