"""Client billing and the open-interest board — the last two SQLite-only stores.

Revision ID: 048
Revises: 047
Create Date: 2026-09-22

WHY THIS EXISTS
---------------
`client_billing.py` and `open_interest.py` follow `CAPITAL_DB_BACKEND` but
their tables were never added to a migration: they were created at runtime by
`CREATE TABLE IF NOT EXISTS` against SQLite. The moment that switch is
`postgres` the runtime tries the same DDL as `gex_app` and is refused —

    psycopg2.errors.InsufficientPrivilege: permission denied for schema public

— which is `gex_app` working as designed (031: no CREATE on schema public).
Both tables were empty at cutover, so this migration moves a schema, not data.

THE POLICIES
------------
`client_id` IS the tenant's `company_id`: `client_billing.seats_used()` counts
`auth_users WHERE company_id = client_id`, and `routes_client_billing`
authorises by comparing the caller's `company_id` to it. So client rows are
company-scoped, and this states that one layer below the route check.

`commercial_terms` is readable by everyone, like `approval_policies` and
`fuel_catalog`: a client cannot be asked to accept terms it is not allowed to
read, and the published fee schedule is the same document for all of them.
Writes are admin-only — publishing terms is a GEX act.

`open_interests` is company-scoped here, which is NOT the same as the board's
confidentiality rule. Who may see a published interest is decided by
`is_visible()` in Python, from the publisher's `visibility_json` intersected
with the viewer's own filter, and a platform admin deliberately does NOT bypass
the publisher. RLS cannot express that, so it is not asked to: this policy
protects the rows a company owns, and `_all_interests()` opens an explicit
PLATFORM_ADMIN connection for discovery, which `_tenant_context` logs. The
confidentiality decision stays in one place instead of being half-stated in SQL
and half in Python, which is how such rules drift apart.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"

TABLES = ("client_accounts", "commercial_terms", "terms_acceptances",
          "client_invoices", "throughput_charges", "open_interests")


def upgrade() -> None:
    op.create_table(
        "client_accounts",
        sa.Column("client_id", sa.Text(), primary_key=True),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="PROSPECT"),
        sa.Column("seat_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "commercial_terms",
        sa.Column("terms_id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text(), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        # The fee schedule is FROZEN into the version. Changing fees means
        # publishing a new terms version, never editing this JSON in place.
        sa.Column("fee_schedule_json", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "terms_acceptances",
        sa.Column("acceptance_id", sa.Text(), primary_key=True),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("terms_id", sa.Text(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Text(), nullable=False),
        sa.Column("accepted_sha256", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text()),
        sa.Column("accepted_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("client_id", "terms_id", name="uq_terms_acceptance"),
    )

    op.create_table(
        "client_invoices",
        sa.Column("invoice_id", sa.Text(), primary_key=True),
        sa.Column("invoice_number", sa.Text(), nullable=False, unique=True),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("terms_id", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="EUR"),
        # Minor units (cents). Never a float — money that rounds is money lost.
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("line_items_json", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="ISSUED"),
        sa.Column("issued_at", sa.Text(), nullable=False),
        sa.Column("due_at", sa.Text()),
        sa.Column("paid_at", sa.Text()),
        sa.Column("payment_ref", sa.Text()),
    )
    op.create_index("idx_client_invoices_client", "client_invoices", ["client_id"])

    op.create_table(
        "throughput_charges",
        sa.Column("charge_id", sa.Text(), primary_key=True),
        sa.Column("settlement_id", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("component_code", sa.Text(), nullable=False),
        sa.Column("volume_kg", sa.Float(), nullable=False),
        sa.Column("settled_value_minor", sa.Integer(), nullable=False),
        sa.Column("fee_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("settled_at", sa.Text(), nullable=False),
        sa.Column("due_at", sa.Text(), nullable=False),
        sa.Column("accrued_at", sa.Text(), nullable=False),
        # One charge per settlement per side — this is what makes accruing the
        # same settlement twice bill once.
        sa.UniqueConstraint("settlement_id", "side", name="uq_throughput_settlement_side"),
    )
    op.create_index("idx_throughput_company", "throughput_charges", ["company_id"])

    op.create_table(
        "open_interests",
        sa.Column("interest_id", sa.Text(), primary_key=True),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("molecule", sa.Text()),
        sa.Column("volume_tpa", sa.Float()),
        sa.Column("target_cod_year", sa.Integer()),
        sa.Column("term_years_min", sa.Integer()),
        sa.Column("jurisdiction", sa.Text()),
        sa.Column("counterparty_rating", sa.Text()),
        sa.Column("indicative_price_eur_t", sa.Float()),
        sa.Column("state", sa.Text(), nullable=False, server_default="DRAFT"),
        # The publisher's confidentiality rule. Never returned to a viewer.
        sa.Column("visibility_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_open_interests_company", "open_interests", ["company_id"])

    conn = op.get_bind()

    def rls(table: str, using: str, read_all: bool = False):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        if read_all:
            conn.execute(sa.text(
                f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (true)"))
            conn.execute(sa.text(
                f"CREATE POLICY {table}_admin_writes ON {table} FOR ALL USING ({ADMIN})"))
        else:
            conn.execute(sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL USING ({using})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))

    rls("commercial_terms", "true", read_all=True)
    rls("client_accounts", f"{ADMIN} OR client_id = {ME}")
    rls("terms_acceptances", f"{ADMIN} OR client_id = {ME}")
    rls("client_invoices", f"{ADMIN} OR client_id = {ME}")
    rls("throughput_charges", f"{ADMIN} OR company_id = {ME}")
    rls("open_interests", f"{ADMIN} OR company_id = {ME}")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP POLICY IF EXISTS commercial_terms_read ON commercial_terms"))
    conn.execute(sa.text(
        "DROP POLICY IF EXISTS commercial_terms_admin_writes ON commercial_terms"))
    for t in ("client_accounts", "terms_acceptances", "client_invoices",
              "throughput_charges", "open_interests"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {t}_tenant_isolation ON {t}"))
    for t in reversed(TABLES):
        op.drop_table(t)
