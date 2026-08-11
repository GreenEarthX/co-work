"""Marketplace / trading tail — slice 6.

Revision ID: 036
Revises: 035

The plan calls this "bulk but low coupling; mechanical". The bulk and the
coupling are as advertised — 13 tables, 5 rows — but the RLS is NOT mechanical,
because none of these tables has a `project_id`.

TENANCY IS IMPLICIT IN AN OVERLOADED PRIMARY KEY
------------------------------------------------
`capacities.id` IS a project id. All five rows are real registry projects
(proj_bremen_h2, proj_lehavre_eng, proj_rotterdam_nh3,
proj_sansebastian_emethanol, proj_wales_saf) — but nothing in the schema says
so: no FK, no naming, no comment. The rest of the marketplace hangs off it:

    capacities.id (= project_id)
        <- tokens.capacity_id
             <- offers.token_id
                  <- matches.offer_id

So isolation is reachable, by resolving `capacities.id` as a project and
delegating to the 032 helpers. `app_company_can_see_capacity()` does exactly
that, and the three downstream policies chain through it. SECURITY DEFINER, so
the chain does not re-enter RLS and recurse (the defect 032 had to fix).

This is worth doing NOW, while the tables are empty: `tokens` is the object that
carries the green claim, so it is the last table where tenant isolation should
be an afterthought.

buyer_mandates is COMPANY-scoped, not project-scoped — `buyer_id` is the
company. Its policy compares directly.

THE tb_* TABLES GET AN ADMIN-ONLY POLICY, DELIBERATELY
------------------------------------------------------
The eight trading-book tables have no path to a project at all: `tb_asset.id`
is a UUID with no external reference, which is the same gap that makes
`/api/v1/trading-book/.../cashflows` reject GEX project slugs with a 422.

There is therefore no honest tenant policy to write. Rather than leave them
unprotected (which reads as an oversight) or invent a policy that pretends to
isolate, they are locked to PLATFORM_ADMIN. They are empty and unreachable
today, so nothing regresses; when the asset-to-project bridge lands, the policy
becomes a real one.

NOT IN THIS MIGRATION: `contracts`
----------------------------------
`contracts_sqlite.py` is routed and queries a `contracts` table that has NO DDL
anywhere in app/ and does not exist in SQLite. `/api/v1/contracts/summary`
returns 500 today. Creating it here would make PostgreSQL work while SQLite
still fails — breaking the backend-parity gate that every slice is verified
against. It is a defect to fix as its own change, with a schema derived
deliberately rather than guessed inside a migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"

TB_TABLES = (
    "tb_asset", "tb_counterparty", "tb_index_definition", "tb_index_history",
    "tb_contract", "tb_contract_fixed_price", "tb_contract_index_linked",
    "tb_project_finance_link",
)


def upgrade() -> None:
    op.create_table(
        "capacities",
        # NOTE: `id` doubles as the project id. Kept as-is for fidelity; the
        # comment is the documentation the schema never had.
        sa.Column("id", sa.Text(), primary_key=True,
                  comment="ALSO the project_id — see the RLS policy below"),
        sa.Column("project_name", sa.Text(), nullable=False),
        sa.Column("molecule", sa.Text(), nullable=False),
        sa.Column("capacity_mtpd", sa.Float(), nullable=False),
        sa.Column("location", sa.Text()),
        sa.Column("production_start", sa.Text()),
        sa.Column("production_end", sa.Text()),
        sa.Column("compliance_certifications", sa.Text()),
        sa.Column("capex_eur", sa.Float()),
        sa.Column("opex_eur_kg", sa.Float()),
        sa.Column("status", sa.Text()),
        sa.Column("created_at", sa.Text()),
        sa.Column("updated_at", sa.Text()),
    )

    op.create_table(
        "tokens",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("capacity_id", sa.Text()),
        sa.Column("tokenised_mtpd", sa.Float()),
        sa.Column("delivery_start", sa.Text()),
        sa.Column("delivery_end", sa.Text()),
        sa.Column("compliance_certifications", sa.Text()),
        sa.Column("correlation_id", sa.Text()),
        sa.Column("sovereign_provenance", sa.Text()),
        sa.Column("molecule", sa.Text()),
        sa.Column("energy_mj", sa.Float()),
        sa.Column("production_window_start", sa.Text()),
        sa.Column("production_window_end", sa.Text()),
        sa.Column("certification_pathway", sa.Text()),
        sa.Column("carbon_intensity_gco2e_mj", sa.Float()),
        sa.Column("mass_balance_lot_id", sa.Text()),
        sa.Column("lifecycle_state", sa.Text(), server_default="MINTED"),
        sa.Column("provenance_hash", sa.Text()),
        sa.Column("verification_state", sa.Text(), server_default="UNVERIFIED"),
        sa.Column("created_at", sa.Text()),
        # Retirement / annulment accountability (2026-08-07 ruling: a green
        # claim is made once). RETIRED exits only to ANNULLED, which is terminal
        # and non-claimable — the CHECK below pins the domain; the state machine
        # itself lives in tokens_sqlite.TOKEN_TRANSITIONS.
        sa.Column("retirement_event_id", sa.Text()),
        sa.Column("carbon_attribution_event_id", sa.Text()),
        sa.Column("retired_by", sa.Text()),
        sa.Column("retired_at", sa.Text()),
        sa.Column("retirement_evidence_ref", sa.Text()),
        sa.Column("annulment_event_id", sa.Text()),
        sa.Column("annulled_by", sa.Text()),
        sa.Column("annulled_at", sa.Text()),
        sa.Column("annulment_reason", sa.Text()),
        sa.Column("annulment_authority_ref", sa.Text()),
        sa.Column("supersedes_retirement_event_id", sa.Text()),
        sa.CheckConstraint(
            "lifecycle_state IN ('MINTED','RESERVED','MATCHED','SETTLED',"
            "'RETIRED','ANNULLED','VOIDED')", name="ck_tokens_lifecycle_state"),
    )
    op.create_index("idx_tokens_capacity", "tokens", ["capacity_id"])
    op.create_index("idx_tokens_state", "tokens", ["lifecycle_state"])

    op.create_table(
        "offers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("token_id", sa.Text()),
        sa.Column("molecule", sa.Text()),
        sa.Column("volume_mtpd", sa.Float()),
        sa.Column("price_eur_kg", sa.Float()),
        sa.Column("delivery_start", sa.Text()),
        sa.Column("delivery_end", sa.Text()),
        sa.Column("location", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("offer_type", sa.Text()),
        sa.Column("correlation_id", sa.Text()),
        sa.Column("delivery_type", sa.Text()),
        sa.Column("delivery_basis", sa.Text()),
        sa.Column("price_basis", sa.Text()),
        sa.Column("certification_pathway_required", sa.Text()),
        sa.Column("min_order_kg", sa.Float()),
        sa.Column("esg_tier", sa.Text()),
        sa.Column("listing_state", sa.Text()),
        sa.Column("created_at", sa.Text()),
    )
    op.create_index("idx_offers_token", "offers", ["token_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("offer_id", sa.Text()),
        sa.Column("rfq_id", sa.Text()),
        sa.Column("match_score", sa.Float()),
        sa.Column("volume_mtpd", sa.Float()),
        sa.Column("price_eur_kg", sa.Float()),
        sa.Column("status", sa.Text()),
        sa.Column("created_at", sa.Text()),
    )
    op.create_index("idx_matches_offer", "matches", ["offer_id"])

    op.create_table(
        "buyer_mandates",
        sa.Column("mandate_id", sa.Text(), primary_key=True),
        sa.Column("buyer_id", sa.Text(), nullable=False),
        sa.Column("esg_compliance_level", sa.Text(), nullable=False),
        sa.Column("certification_acceptable", sa.Text(), nullable=False),
        sa.Column("delivery_basis_acceptable", sa.Text(), nullable=False),
        sa.Column("price_band_min", sa.Float(), nullable=False),
        sa.Column("price_band_max", sa.Float(), nullable=False),
        sa.Column("volume_band_min_kg", sa.Float(), nullable=False),
        sa.Column("volume_band_max_kg", sa.Float(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_mandates_buyer", "buyer_mandates", ["buyer_id"])

    conn = op.get_bind()

    # ── Trading-book tables, from the SQLAlchemy models ─────────────────────
    # Hand-writing these 8 would risk drifting from app/trading_book/models.py,
    # which is their single definition. Build them from the models instead.
    from app.trading_book.models import Base as TBBase

    TBBase.metadata.create_all(conn, checkfirst=True)

    # ── The capacity -> project resolver ────────────────────────────────────
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION app_company_can_see_capacity(
            p_capacity_id text, p_company_id text
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            -- capacities.id IS the project id. SECURITY DEFINER so this lookup
            -- does not itself go through RLS and recurse.
            SELECT app_company_owns_project(p_capacity_id, p_company_id)
                OR app_company_has_project_access(p_capacity_id, p_company_id)
        $$;
    """))
    conn.execute(sa.text(
        "REVOKE ALL ON FUNCTION app_company_can_see_capacity(text, text) FROM PUBLIC"))
    conn.execute(sa.text(
        f"GRANT EXECUTE ON FUNCTION app_company_can_see_capacity(text, text) TO {APP_ROLE}"))

    admin = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
    me = "current_setting('app.current_company_id', true)"

    policies = {
        # capacities.id IS the project id.
        "capacities": f"{admin} OR app_company_can_see_capacity(id, {me})",
        # tokens hang off a capacity.
        "tokens": f"{admin} OR app_company_can_see_capacity(capacity_id, {me})",
        # offers hang off a token, which hangs off a capacity.
        "offers": f"""{admin} OR EXISTS (
            SELECT 1 FROM tokens t
            WHERE t.id = offers.token_id
              AND app_company_can_see_capacity(t.capacity_id, {me}))""",
        # matches hang off an offer -> token -> capacity.
        "matches": f"""{admin} OR EXISTS (
            SELECT 1 FROM offers o JOIN tokens t ON t.id = o.token_id
            WHERE o.id = matches.offer_id
              AND app_company_can_see_capacity(t.capacity_id, {me}))""",
        # buyer_mandates are COMPANY-scoped, not project-scoped.
        "buyer_mandates": f"{admin} OR buyer_id = {me}",
    }
    for table, using in policies.items():
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL USING ({using})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))

    # ── Trading book: admin-only until an asset can name its project ────────
    for table in TB_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY {table}_admin_only ON {table} FOR ALL USING ({admin})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("capacities", "tokens", "offers", "matches", "buyer_mandates"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    for table in TB_TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_admin_only ON {table}"))
    conn.execute(sa.text(
        "DROP FUNCTION IF EXISTS app_company_can_see_capacity(text, text)"))
    from app.trading_book.models import Base as TBBase
    TBBase.metadata.drop_all(conn, checkfirst=True)
    for table in ("buyer_mandates", "matches", "offers", "tokens", "capacities"):
        op.drop_table(table)
