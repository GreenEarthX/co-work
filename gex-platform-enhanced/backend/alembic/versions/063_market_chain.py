"""Market chain — the tables and columns a tokenised trade needs end to end.

Revision ID: 063
Revises: 062

WHY (docs/COMMERCIAL_PLATFORM_GAP_REGISTER.md, P0, 2026-10-23)
--------------------------------------------------------------
The chain capacity -> token -> offer/RFQ -> match -> contract -> settlement was
modelled but could not run:

  * `rfqs` existed in neither store. Both RFQ endpoints wrote to it and the
    matching run read it, so every RFQ call and every matching run failed.
  * `contracts` had no DDL anywhere (036 recorded this and left it). Contract
    creation and `/contracts/summary` failed.
  * A buyer could not see a match against its own RFQ, a contract it is party
    to, the token it bought, or the settlement it pays: every policy followed the
    SELLER's project only.

JML's decisions of 2026-10-23: listings are visible to every vetted company but
anonymised (counterparty revealed only to the two parties once a match exists),
and a match needs BOTH parties to accept. Base tables therefore stay strictly
tenant-scoped; the anonymised listing is produced by the market engine
(app/core/market_engine.py), which also performs every cross-company step.

WHAT
----
  rfqs       new. Owned by `buyer_company_id`. FORCED RLS; reads AND writes
             limited to the owner (explicit WITH CHECK — not the 062 flaw).
  contracts  new. Seller side via the project (capacity chain) or the buyer
             company. Snapshot of the match it came from.
  matches    + the agreed terms snapshot (project, token, both companies,
             molecule, window, correlation_id) and two-sided acceptance
             (who and when, per side). Visible to both parties.
  tokens     + holder_company_id: the company holding title. Set to the buyer
             at settlement, so the holder can retire the claim it bought.
  settlement_events, carbon_attribution_events
             + correlation_id: one chain id from capacity to retirement.
  settlement_events, settlement_event_log
             readable by the buyer company too (counterparty_buyer_id).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "063"
down_revision: Union[str, None] = "062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
SELLER_OF = "app_company_can_see_capacity({col}, " + ME + ")"

MATCH_COLUMNS = [
    ("project_id", sa.Text()), ("token_id", sa.Text()),
    ("seller_company_id", sa.Text()), ("buyer_company_id", sa.Text()),
    ("molecule", sa.Text()), ("delivery_start", sa.Text()), ("delivery_end", sa.Text()),
    ("correlation_id", sa.Text()), ("created_by", sa.Text()),
    ("seller_accepted_by", sa.Text()), ("seller_accepted_at", sa.Text()),
    ("buyer_accepted_by", sa.Text()), ("buyer_accepted_at", sa.Text()),
]


def _force(conn, table):
    conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def _policy(conn, table, name, using, check=None):
    conn.execute(sa.text(f"DROP POLICY IF EXISTS {name} ON {table}"))
    conn.execute(sa.text(f"CREATE POLICY {name} ON {table} FOR ALL USING ({using}) "
                         f"WITH CHECK ({check or using})"))


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "rfqs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("buyer_company_id", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text()),
        sa.Column("molecule", sa.Text(), nullable=False),
        sa.Column("volume_mtpd", sa.Float(), nullable=False),
        sa.Column("max_price_eur_kg", sa.Float()),
        sa.Column("delivery_start", sa.Text(), nullable=False),
        sa.Column("delivery_end", sa.Text(), nullable=False),
        sa.Column("location", sa.Text()),
        sa.Column("buyer_name", sa.Text()),
        sa.Column("buyer_contact", sa.Text()),
        sa.Column("compliance_requirements", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("correlation_id", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text()),
        # The trader module's own state machine: draft -> open | cancelled;
        # open -> matched | expired | withdrawn.
        sa.CheckConstraint("status IN ('draft','open','matched','expired','withdrawn','cancelled')",
                           name="ck_rfqs_status"),
    )
    op.create_index("idx_rfqs_buyer", "rfqs", ["buyer_company_id"])
    op.create_index("idx_rfqs_open", "rfqs", ["status", "molecule"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("match_id", sa.Text()),
        sa.Column("offer_id", sa.Text()),
        sa.Column("rfq_id", sa.Text()),
        sa.Column("token_id", sa.Text()),
        sa.Column("seller_company_id", sa.Text()),
        sa.Column("buyer_company_id", sa.Text()),
        sa.Column("contract_id_external", sa.Text()),
        sa.Column("counterparty", sa.Text()),
        sa.Column("molecule", sa.Text()),
        sa.Column("volume_mtpd", sa.Float()),
        sa.Column("price_eur_kg", sa.Float()),
        sa.Column("pricing_basis", sa.Text()),
        sa.Column("delivery_terms", sa.Text()),
        sa.Column("payment_terms", sa.Text()),
        sa.Column("start_date", sa.Text()),
        sa.Column("end_date", sa.Text()),
        sa.Column("tenor_years", sa.Integer()),
        sa.Column("credit_rating", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("correlation_id", sa.Text()),
        sa.Column("created_by", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text()),
    )
    op.create_index("idx_contracts_project", "contracts", ["project_id"])
    op.create_index("idx_contracts_buyer", "contracts", ["buyer_company_id"])
    op.create_index("idx_contracts_match", "contracts", ["match_id"], unique=True)

    for name, coltype in MATCH_COLUMNS:
        op.add_column("matches", sa.Column(name, coltype))
    op.add_column("tokens", sa.Column("holder_company_id", sa.Text()))
    op.add_column("settlement_events", sa.Column("correlation_id", sa.Text()))
    op.add_column("carbon_attribution_events", sa.Column("correlation_id", sa.Text()))

    # ── policies ────────────────────────────────────────────────────────────
    _force(conn, "rfqs")
    _policy(conn, "rfqs", "rfqs_owner", f"{ADMIN} OR buyer_company_id = {ME}")

    _force(conn, "contracts")
    _policy(conn, "contracts", "contracts_parties",
            f"{ADMIN} OR {SELLER_OF.format(col='project_id')} OR buyer_company_id = {ME}")

    legacy_chain = (f"EXISTS (SELECT 1 FROM offers o JOIN tokens t ON t.id = o.token_id "
                    f"WHERE o.id = matches.offer_id AND {SELLER_OF.format(col='t.capacity_id')})")
    conn.execute(sa.text("DROP POLICY IF EXISTS matches_tenant_isolation ON matches"))
    _policy(conn, "matches", "matches_parties",
            f"{ADMIN} OR {SELLER_OF.format(col='project_id')} OR buyer_company_id = {ME} "
            f"OR {legacy_chain}")

    conn.execute(sa.text("DROP POLICY IF EXISTS tokens_tenant_isolation ON tokens"))
    _policy(conn, "tokens", "tokens_seller_or_holder",
            f"{ADMIN} OR {SELLER_OF.format(col='capacity_id')} OR holder_company_id = {ME}")

    conn.execute(sa.text("DROP POLICY IF EXISTS settlement_events_tenant_isolation ON settlement_events"))
    _policy(conn, "settlement_events", "settlement_events_parties",
            f"{ADMIN} OR app_company_owns_project(project_id, {ME}) "
            f"OR app_company_has_project_access(project_id, {ME}) "
            f"OR counterparty_buyer_id = {ME}")
    conn.execute(sa.text("DROP POLICY IF EXISTS settlement_event_log_tenant_isolation ON settlement_event_log"))
    _policy(conn, "settlement_event_log", "settlement_event_log_parties",
            f"{ADMIN} OR app_company_owns_project(project_id, {ME}) "
            f"OR app_company_has_project_access(project_id, {ME}) "
            f"OR EXISTS (SELECT 1 FROM settlement_events s WHERE s.settlement_id = "
            f"settlement_event_log.settlement_id AND s.counterparty_buyer_id = {ME})")

    # Assert rather than trust (059, 062).
    forced = conn.execute(sa.text(
        "SELECT relname FROM pg_class WHERE relname IN ('rfqs','contracts') "
        "AND relrowsecurity AND relforcerowsecurity")).fetchall()
    if len(forced) != 2:
        raise RuntimeError(f"rfqs/contracts are not under FORCED RLS: {forced}")


def downgrade() -> None:
    conn = op.get_bind()
    me, admin = ME, ADMIN
    _policy(conn, "settlement_event_log", "settlement_event_log_tenant_isolation",
            f"{admin} OR app_company_owns_project(project_id, {me}) "
            f"OR app_company_has_project_access(project_id, {me})")
    conn.execute(sa.text("DROP POLICY IF EXISTS settlement_event_log_parties ON settlement_event_log"))
    _policy(conn, "settlement_events", "settlement_events_tenant_isolation",
            f"{admin} OR app_company_owns_project(project_id, {me}) "
            f"OR app_company_has_project_access(project_id, {me})")
    conn.execute(sa.text("DROP POLICY IF EXISTS settlement_events_parties ON settlement_events"))
    conn.execute(sa.text("DROP POLICY IF EXISTS tokens_seller_or_holder ON tokens"))
    conn.execute(sa.text(f"CREATE POLICY tokens_tenant_isolation ON tokens FOR ALL USING "
                         f"({admin} OR {SELLER_OF.format(col='capacity_id')})"))
    conn.execute(sa.text("DROP POLICY IF EXISTS matches_parties ON matches"))
    conn.execute(sa.text(
        f"CREATE POLICY matches_tenant_isolation ON matches FOR ALL USING ({admin} OR "
        f"EXISTS (SELECT 1 FROM offers o JOIN tokens t ON t.id = o.token_id "
        f"WHERE o.id = matches.offer_id AND {SELLER_OF.format(col='t.capacity_id')}))"))
    op.drop_column("carbon_attribution_events", "correlation_id")
    op.drop_column("settlement_events", "correlation_id")
    op.drop_column("tokens", "holder_company_id")
    for name, _ in reversed(MATCH_COLUMNS):
        op.drop_column("matches", name)
    op.drop_table("contracts")
    op.drop_table("rfqs")
