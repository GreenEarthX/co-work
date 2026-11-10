"""M6, drop 4 of 4: the market's own tables go — offers, rfqs, matches (Phase 3).

Revision ID: 091
Revises: 090

087 (M3) moved the market onto the order model: a listing is a firm sell
tb_order, an RFQ a tb_rfq, a proposal an invited tb_order (Phase 0 Q6, Q8). The
market engine has written and read only those since; the converter
(app/trading_book/migrate/market_to_orders.py) carries any legacy row across by
JML's Q8 mapping and stops on what it cannot map. JML decided 2026-11-10 to drop
the three tables after parity: on that day they hold 0 rows, and nothing outside
them refers to them (no foreign key, view or function; their policies are their
own).

Upgrade refuses while any row has no converted counterpart (the converter keeps
a legacy uuid id, or derives uuid5 from it — the same function is used here).
The downgrade rebuilds the three tables, EMPTY, as 087 left them (pg_dump -s at
090: columns, indexes, policies, FORCED RLS, grants); a converted row lives on
in the order model and is not copied back.

Two read-only endpoints still name `offers` in SQLite, not here:
api/v1/lineage.py and api/v1/marketplace_analytics.py (CLAUDE.md, unguarded reads).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "091"
down_revision: Union[str, None] = "090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# pg_dump -s -t offers / -t rfqs / -t matches (comments, SET lines and "public." removed).
OFFERS_DDL = """
CREATE TABLE offers (
    id text NOT NULL,
    token_id text,
    molecule text,
    volume_mtpd double precision,
    price_eur_kg double precision,
    delivery_start text,
    delivery_end text,
    location text,
    status text,
    offer_type text,
    correlation_id text,
    delivery_type text,
    delivery_basis text,
    price_basis text,
    certification_pathway_required text,
    min_order_kg double precision,
    esg_tier text,
    listing_state text,
    created_at text
);
ALTER TABLE ONLY offers FORCE ROW LEVEL SECURITY;
ALTER TABLE ONLY offers
    ADD CONSTRAINT offers_pkey PRIMARY KEY (id);
CREATE INDEX idx_offers_token ON offers USING btree (token_id);
ALTER TABLE offers ENABLE ROW LEVEL SECURITY;
CREATE POLICY offers_delete ON offers FOR DELETE USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (EXISTS ( SELECT 1
   FROM tokens t
  WHERE ((t.id = offers.token_id) AND app_company_owns_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true)))))));
CREATE POLICY offers_insert ON offers FOR INSERT WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (EXISTS ( SELECT 1
   FROM tokens t
  WHERE ((t.id = offers.token_id) AND app_company_owns_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true)))))));
CREATE POLICY offers_read ON offers FOR SELECT USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (EXISTS ( SELECT 1
   FROM tokens t
  WHERE ((t.id = offers.token_id) AND app_company_sees_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true)))))));
CREATE POLICY offers_update ON offers FOR UPDATE USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (EXISTS ( SELECT 1
   FROM tokens t
  WHERE ((t.id = offers.token_id) AND app_company_owns_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true))))))) WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (EXISTS ( SELECT 1
   FROM tokens t
  WHERE ((t.id = offers.token_id) AND app_company_owns_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true)))))));
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE offers TO gex_app;
GRANT ALL ON TABLE offers TO gex_admin;
"""
RFQS_DDL = """
CREATE TABLE rfqs (
    id text NOT NULL,
    buyer_company_id text NOT NULL,
    created_by text,
    molecule text NOT NULL,
    volume_mtpd double precision NOT NULL,
    max_price_eur_kg double precision,
    delivery_start text NOT NULL,
    delivery_end text NOT NULL,
    location text,
    buyer_name text,
    buyer_contact text,
    compliance_requirements text,
    status text DEFAULT 'open'::text NOT NULL,
    correlation_id text,
    created_at text NOT NULL,
    updated_at text,
    CONSTRAINT ck_rfqs_status CHECK ((status = ANY (ARRAY['draft'::text, 'open'::text, 'matched'::text, 'expired'::text, 'withdrawn'::text, 'cancelled'::text])))
);
ALTER TABLE ONLY rfqs FORCE ROW LEVEL SECURITY;
ALTER TABLE ONLY rfqs
    ADD CONSTRAINT rfqs_pkey PRIMARY KEY (id);
CREATE INDEX idx_rfqs_buyer ON rfqs USING btree (buyer_company_id);
CREATE INDEX idx_rfqs_open ON rfqs USING btree (status, molecule);
ALTER TABLE rfqs ENABLE ROW LEVEL SECURITY;
CREATE POLICY rfqs_owner ON rfqs USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)))) WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (buyer_company_id = current_setting('app.current_company_id'::text, true))));
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE rfqs TO gex_app;
"""
MATCHES_DDL = """
CREATE TABLE matches (
    id text NOT NULL,
    offer_id text,
    rfq_id text,
    match_score double precision,
    volume_mtpd double precision,
    price_eur_kg double precision,
    status text,
    created_at text,
    project_id text,
    token_id text,
    seller_company_id text,
    buyer_company_id text,
    molecule text,
    delivery_start text,
    delivery_end text,
    correlation_id text,
    created_by text,
    seller_accepted_by text,
    seller_accepted_at text,
    buyer_accepted_by text,
    buyer_accepted_at text,
    delivery_terms text,
    payment_terms text
);
ALTER TABLE ONLY matches FORCE ROW LEVEL SECURITY;
ALTER TABLE ONLY matches
    ADD CONSTRAINT matches_pkey PRIMARY KEY (id);
CREATE INDEX idx_matches_offer ON matches USING btree (offer_id);
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
CREATE POLICY matches_delete ON matches FOR DELETE USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)) OR (EXISTS ( SELECT 1
   FROM (offers o
     JOIN tokens t ON ((t.id = o.token_id)))
  WHERE ((o.id = matches.offer_id) AND app_company_sees_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true))))))));
CREATE POLICY matches_insert ON matches FOR INSERT WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)) OR (EXISTS ( SELECT 1
   FROM (offers o
     JOIN tokens t ON ((t.id = o.token_id)))
  WHERE ((o.id = matches.offer_id) AND app_company_sees_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true))))))));
CREATE POLICY matches_read ON matches FOR SELECT USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)) OR (EXISTS ( SELECT 1
   FROM (offers o
     JOIN tokens t ON ((t.id = o.token_id)))
  WHERE ((o.id = matches.offer_id) AND app_company_sees_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true))))))));
CREATE POLICY matches_update ON matches FOR UPDATE USING (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)) OR (EXISTS ( SELECT 1
   FROM (offers o
     JOIN tokens t ON ((t.id = o.token_id)))
  WHERE ((o.id = matches.offer_id) AND app_company_sees_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true)))))))) WITH CHECK (((current_setting('app.current_company_id'::text, true) = 'PLATFORM_ADMIN'::text) OR (app_company_owns_project(project_id, current_setting('app.current_company_id'::text, true)) OR app_company_has_project_access(project_id, current_setting('app.current_company_id'::text, true)) OR (buyer_company_id = current_setting('app.current_company_id'::text, true)) OR (EXISTS ( SELECT 1
   FROM (offers o
     JOIN tokens t ON ((t.id = o.token_id)))
  WHERE ((o.id = matches.offer_id) AND app_company_sees_capacity(t.capacity_id, current_setting('app.current_company_id'::text, true))))))));
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE matches TO gex_app;
GRANT ALL ON TABLE matches TO gex_admin;
"""
COUNTERPART = (("offers", "tb_order"), ("rfqs", "tb_rfq"), ("matches", "tb_order"))


def _uuid(v) -> str:
    """market_to_orders._uuid, repeated so the migration never imports application code that may move."""
    import uuid

    try:
        return str(uuid.UUID(str(v)))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"gex-market:{v}"))


def upgrade() -> None:
    conn = op.get_bind()
    missing = []
    for table, target in COUNTERPART:
        for (rid,) in conn.execute(sa.text(f"SELECT id FROM {table}")).fetchall():
            if conn.execute(sa.text(f"SELECT 1 FROM {target} WHERE id = CAST(:i AS uuid)"),
                            {"i": _uuid(rid)}).first() is None:
                missing.append(f"{table}:{rid}")
    assert not missing, ("not converted to the order model (run app.trading_book.migrate.market_to_orders "
                         f"--execute first): {missing[:10]}")
    for table in ("matches", "rfqs", "offers"):
        conn.execute(sa.text(f"DROP TABLE {table}"))
    assert conn.execute(sa.text("SELECT count(*) FROM pg_class WHERE relname IN ('offers', 'rfqs', 'matches') "
                                "AND relnamespace = 'public'::regnamespace")).scalar() == 0


def downgrade() -> None:
    conn = op.get_bind()
    for ddl in (OFFERS_DDL, RFQS_DDL, MATCHES_DDL):
        conn.exec_driver_sql(ddl)
