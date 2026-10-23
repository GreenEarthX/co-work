"""Marketplace records — the data MarketplacePage used to hold in code, now in PostgreSQL.

Revision ID: 066
Revises: 065

WHY (JML, 2026-10-23: "all variables and data points in PostgreSQL")
------------------------------------------------------------------
MarketplacePage.tsx carried four constants: spot prices per molecule, per-project
sales details (availability, tokenised volume, in-market lines with buyer names),
per-project production inputs (suppliers, ratios, prices) and a classification
of inputs. Nobody could say which entries were real client information and which
were invented. JML chose to move them as they are, every row marked UNVERIFIED,
rather than delete them.

WHAT
----
  project_sales_detail   one row per project (8 seeded); nested availability /
                         tokenised / in-market parts as jsonb.
  project_input_line     one row per production input (11 projects seeded).
  input_classification   reference: certification and capital relevance per input.
  tb_commodity.registry_pathway
                         the reference registry's pathway code for each commodity,
                         so spot prices resolve from data, not a mapping in code.
Spot prices go to reference_parameter as `proposed` (keys market_spot_price /
market_spot_price_energy) — by scripts/load_marketplace_unverified_20261023.py,
which also loads the rows above. This migration creates no data rows.

Every record carries verification_state (UNVERIFIED by default) and `source`.
Project records are read by the project's companies (app_company_can_see_capacity)
and written by GEX only for now; the classification is readable by all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "066"
down_revision: Union[str, None] = "065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
PROJECT_SEEN = f"{ADMIN} OR app_company_can_see_capacity(project_id, {ME})"
AUDIT = """verification_state tb_verification_state NOT NULL DEFAULT 'UNVERIFIED',
           source text NOT NULL,
           created_at timestamptz NOT NULL DEFAULT now(),
           created_by text NOT NULL DEFAULT current_user,
           updated_at timestamptz NOT NULL DEFAULT now()"""
TABLES = {"project_sales_detail": PROJECT_SEEN, "project_input_line": PROJECT_SEEN,
          "input_classification": "true"}
PATHWAYS = {"H2": "H2", "NH3": "NH3", "EMEOH": "E_METHANOL", "ENG": "E_NG", "SAF": "SAF"}


def _q(sql: str, params: dict | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    _q("ALTER TABLE tb_commodity ADD COLUMN registry_pathway text UNIQUE")
    for code, pathway in PATHWAYS.items():
        _q("UPDATE tb_commodity SET registry_pathway = :p WHERE code = :c", {"p": pathway, "c": code})

    _q(f"""CREATE TABLE project_sales_detail (
           project_id text PRIMARY KEY REFERENCES projects(project_id),
           region text, e_source text, green_energy_pct numeric(7,3), certifier text,
           breakeven_price numeric(20,4),
           available jsonb, tokenised jsonb, in_market jsonb NOT NULL DEFAULT '[]'::jsonb,
           {AUDIT})""")
    _q(f"""CREATE TABLE project_input_line (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           project_id text NOT NULL REFERENCES projects(project_id),
           seq int NOT NULL,
           feedstock text NOT NULL, supplier text,
           ratio numeric(20,6) NOT NULL, ratio_unit text NOT NULL,
           unit_price numeric(20,4) NOT NULL, price_unit text NOT NULL,
           status text NOT NULL CHECK (status IN ('contracted', 'planned', 'spot')),
           is_utility boolean NOT NULL DEFAULT false,
           capacity_factor numeric(7,4) CHECK (capacity_factor IS NULL OR (capacity_factor > 0 AND capacity_factor <= 1)),
           firming_cost numeric(20,4),
           {AUDIT},
           UNIQUE (project_id, seq))""")
    _q(f"""CREATE TABLE input_classification (
           feedstock text PRIMARY KEY,
           cert_relevance text[] NOT NULL,
           capital_relevance text NOT NULL CHECK (capital_relevance IN
             ('BANKABILITY_CRITICAL', 'COST_DRIVER', 'EVIDENCE_ITEM', 'COMMERCIAL_ONLY')),
           item_type text NOT NULL,
           {AUDIT})""")

    for table, read in TABLES.items():
        _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({read})")
        _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({ADMIN})")
        _q(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({ADMIN}) WITH CHECK ({ADMIN})")
        _q(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({ADMIN})")

    conn = op.get_bind()
    forced = conn.execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relrowsecurity AND relforcerowsecurity"),
        {"t": list(TABLES)}).scalar()
    assert forced == len(TABLES), f"only {forced} of {len(TABLES)} new tables under FORCED RLS"


def downgrade() -> None:
    for table in ("input_classification", "project_input_line", "project_sales_detail"):
        _q(f"DROP TABLE IF EXISTS {table}")
    _q("ALTER TABLE tb_commodity DROP COLUMN IF EXISTS registry_pathway")
