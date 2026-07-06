"""Tenant/project isolation — PostgreSQL Row-Level Security

Revision ID: 020
Revises: 011
Create Date: 2026-04-23

Tables added:
  tenants          — one row per company (producer, offtaker, third-party)
  projects         — every real project; owner_tenant_id FK; RLS-protected
  project_access   — junction: which tenant can see which project, and as
                     what actor type; RLS-protected
  project_users    — maps auth_users.user_id (SQLite PK slug) into PostgreSQL
                     for cross-DB FK annotation (no FK constraint, by design)

Row-Level Security (RLS):
  Both `projects` and `project_access` have RLS enabled.
  The policy reads app.current_company_id (set per-transaction by the
  FastAPI session dependency) and returns only rows the tenant may see.

  Reading policy for projects:
    owner_tenant_id  = current_setting('app.current_company_id')
    OR EXISTS row in project_access WHERE company_id = current_setting(...)

  Reading policy for project_access:
    company_id = current_setting('app.current_company_id')

  Platform admins bypass RLS via a BYPASSRLS role grant done separately.

Seeded from project_registry.py — kept in sync via the seed script.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "020"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Actor type values (mirrors abac.ActorType) ────────────────────────────────
ACTOR_TYPES = [
    "PRODUCER", "OFFTAKER", "COMMERCIAL_BANKER", "DFI", "INSURER",
    "REGULATOR", "GOV_AGENCY", "CERTIFIER", "EPC_CONTRACTOR",
    "LOGISTICS_OPERATOR", "TECHNOLOGY_PROVIDER", "EXECUTIVE", "GUEST",
]

# ── Company types (mirrors UserRole.company_type) ─────────────────────────────
COMPANY_TYPES = ["PRODUCER", "OFFTAKER", "THIRD_PARTY"]

# ── Access roles on a project ─────────────────────────────────────────────────
ACCESS_ROLES = ["OWNER", "STAKEHOLDER", "MANDATED_LENDER", "MANDATED_INSURER", "AUDITOR"]


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. ENUM types ──────────────────────────────────────────────────────────
    actor_type_enum = postgresql.ENUM(*ACTOR_TYPES, name="actor_type_enum", create_type=False)
    actor_type_enum.create(conn, checkfirst=True)

    company_type_enum = postgresql.ENUM(*COMPANY_TYPES, name="company_type_enum", create_type=False)
    company_type_enum.create(conn, checkfirst=True)

    access_role_enum = postgresql.ENUM(*ACCESS_ROLES, name="project_access_role_enum", create_type=False)
    access_role_enum.create(conn, checkfirst=True)

    # ── 2. tenants ─────────────────────────────────────────────────────────────
    # company_id is the same slug used in auth_users.company_id (SQLite) — the
    # canonical cross-store identifier derived by company_slug().
    op.create_table(
        "tenants",
        sa.Column("company_id",   sa.Text, primary_key=True,
                  comment="Slug from company_slug() — matches auth_users.company_id"),
        sa.Column("company_name", sa.Text, nullable=False),
        sa.Column("company_type", sa.Text, nullable=False),   # PRODUCER | OFFTAKER | THIRD_PARTY
        sa.Column("jurisdiction", sa.Text, nullable=False, server_default="EU"),
        sa.Column("is_active",    sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at",   sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_tenants_company_name", "tenants", ["company_name"])

    # ── 3. projects ────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("project_id",      sa.Text, primary_key=True,
                  comment="e.g. proj_hamburgone_emethanol"),
        sa.Column("project_name",    sa.Text, nullable=False),
        sa.Column("owner_tenant_id", sa.Text,
                  sa.ForeignKey("tenants.company_id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("molecule",        sa.Text, nullable=False),
        sa.Column("status",          sa.Text, nullable=False, server_default="development"),
        sa.Column("jurisdiction",    sa.Text, nullable=False, server_default="EU"),
        sa.Column("capex_eur",       sa.Numeric(18, 2)),
        sa.Column("capacity_mtpd",   sa.Numeric(10, 4)),
        sa.Column("completion_date", sa.Date),
        sa.Column("metadata_json",   postgresql.JSONB, server_default="'{}'"),
        sa.Column("is_active",       sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at",      sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_projects_owner",      "projects", ["owner_tenant_id"])
    op.create_index("idx_projects_molecule",   "projects", ["molecule"])
    op.create_index("idx_projects_status",     "projects", ["status"])

    # ── 4. project_access — junction ──────────────────────────────────────────
    # One row per (project, tenant, actor_type) triple.
    # A prosumer company (e.g. BremenThree) gets two rows on the same project:
    #   OFFTAKER  +  PRODUCER
    op.create_table(
        "project_access",
        sa.Column("id",          sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id",  sa.Text,
                  sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("company_id",  sa.Text,
                  sa.ForeignKey("tenants.company_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("actor_type",  sa.Text, nullable=False,
                  comment="ABAC ActorType — PRODUCER, OFFTAKER, COMMERCIAL_BANKER, etc."),
        sa.Column("access_role", sa.Text, nullable=False, server_default="STAKEHOLDER",
                  comment="OWNER | STAKEHOLDER | MANDATED_LENDER | MANDATED_INSURER | AUDITOR"),
        sa.Column("granted_by",  sa.Text,
                  comment="company_id of the granting tenant (usually project owner)"),
        sa.Column("granted_at",  sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_project_access_project",  "project_access", ["project_id"])
    op.create_index("idx_project_access_company",  "project_access", ["company_id"])
    op.create_index(
        "idx_project_access_unique",
        "project_access", ["project_id", "company_id", "actor_type"],
        unique=True,
    )

    # ── 5. Enable Row-Level Security ──────────────────────────────────────────
    # RLS on projects: a tenant sees a project if they own it OR have an access row.
    conn.execute(sa.text("ALTER TABLE projects       ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE project_access ENABLE ROW LEVEL SECURITY"))

    # Force RLS even for table owner (safety belt — owner can bypass via BYPASSRLS role)
    conn.execute(sa.text("ALTER TABLE projects       FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE project_access FORCE ROW LEVEL SECURITY"))

    # ── projects SELECT policy ─────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE POLICY projects_tenant_isolation
        ON projects
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) IN ('', 'PLATFORM_ADMIN')
            OR owner_tenant_id = current_setting('app.current_company_id', true)
            OR EXISTS (
                SELECT 1 FROM project_access pa
                WHERE pa.project_id = projects.project_id
                  AND pa.company_id = current_setting('app.current_company_id', true)
            )
        )
    """))

    # ── project_access SELECT policy ──────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE POLICY project_access_tenant_isolation
        ON project_access
        FOR ALL
        USING (
            current_setting('app.current_company_id', true) IN ('', 'PLATFORM_ADMIN')
            OR company_id = current_setting('app.current_company_id', true)
            OR EXISTS (
                SELECT 1 FROM projects p
                WHERE p.project_id = project_access.project_id
                  AND p.owner_tenant_id = current_setting('app.current_company_id', true)
            )
        )
    """))

    # ── 6. Seed tenants + projects from project_registry ─────────────────────
    # This keeps migration self-contained; the seed script can re-run upserts.
    _seed_initial_data(conn)


def _seed_initial_data(conn) -> None:
    """Seed tenants and project_access from the static project_registry snapshot."""
    from sqlalchemy import text

    # Tenant seed — mirrors DEMO_USER_SEEDS company names
    tenants = [
        ("greenearthx",            "GreenEarthX",           "THIRD_PARTY", "EU"),
        ("hamburgone_com",         "HamburgOne.com",         "PRODUCER",    "DE"),
        ("madrid2_com",            "Madrid2.com",            "PRODUCER",    "ES"),
        ("brementhree_ag",         "BremenThree AG",         "OFFTAKER",    "DE"),
        ("rotterdamofftake4_ag",   "RotterdamOfftake4 AG",   "OFFTAKER",    "NL"),
        ("nordlb",                 "NordLB",                 "THIRD_PARTY", "DE"),
        ("abn_amro",               "ABN-AMRO",               "THIRD_PARTY", "NL"),
        ("siemens_energy",         "Siemens Energy",         "THIRD_PARTY", "DE"),
        ("allianz",                "Allianz",                "THIRD_PARTY", "DE"),
        ("zurich_versicherung_ag", "Zurich Versicherung AG", "THIRD_PARTY", "CH"),
        # Implicit project-owner companies not in demo user seeds
        ("heliosnord_gmbh",        "HeliosNord GmbH",        "PRODUCER",    "DE"),
        ("rotterdamgreenfuels_bv", "RotterdamGreenFuels BV", "PRODUCER",    "NL"),
        ("helios_energia_sl",      "Helios Energia SL",      "PRODUCER",    "ES"),
        ("celtic_green_fuels_ltd", "Celtic Green Fuels Ltd", "PRODUCER",    "GB"),
        ("normandie_hydrogene_sa", "Normandie Hydrogene SA", "PRODUCER",    "FR"),
    ]
    for company_id, company_name, company_type, jurisdiction in tenants:
        conn.execute(text("""
            INSERT INTO tenants (company_id, company_name, company_type, jurisdiction)
            VALUES (:cid, :cname, :ctype, :jur)
            ON CONFLICT (company_id) DO UPDATE
              SET company_name = EXCLUDED.company_name,
                  company_type = EXCLUDED.company_type,
                  jurisdiction = EXCLUDED.jurisdiction,
                  updated_at   = now()
        """), {"cid": company_id, "cname": company_name, "ctype": company_type, "jur": jurisdiction})

    # Project seed (mirrors PROJECT_ACCESS_PROFILES)
    projects = [
        ("proj_bremen_h2",              "Bremen Green Hydrogen Plant",     "heliosnord_gmbh",          "H2",        "DE"),
        ("proj_rotterdam_nh3",          "Rotterdam Green Ammonia Terminal", "rotterdamgreenfuels_bv",   "NH3",       "NL"),
        ("proj_sansebastian_emethanol", "Project Helios e-Methanol",       "helios_energia_sl",        "e-Methanol","ES"),
        ("proj_wales_saf",              "Celtic Green SAF Complex",         "celtic_green_fuels_ltd",   "SAF",       "GB"),
        ("proj_lehavre_eng",            "Le Havre e-Gas Hub",               "normandie_hydrogene_sa",   "e-NG",      "FR"),
        ("proj_hamburgone_emethanol",   "HamburgOne e-Methanol Plant",      "hamburgone_com",           "e-Methanol","DE"),
        ("proj_madrid2_sansebastian",   "Madrid2 San-Sebastian e-Methanol", "madrid2_com",              "e-Methanol","ES"),
    ]
    for project_id, project_name, owner_id, molecule, jurisdiction in projects:
        conn.execute(text("""
            INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, jurisdiction)
            VALUES (:pid, :pname, :oid, :mol, :jur)
            ON CONFLICT (project_id) DO UPDATE
              SET project_name    = EXCLUDED.project_name,
                  owner_tenant_id = EXCLUDED.owner_tenant_id,
                  molecule        = EXCLUDED.molecule,
                  jurisdiction    = EXCLUDED.jurisdiction,
                  updated_at      = now()
        """), {"pid": project_id, "pname": project_name, "oid": owner_id, "mol": molecule, "jur": jurisdiction})

    # project_access seed — mirrors ProjectAccessProfile.associated_company_names
    # Format: (project_id, company_id, actor_type, access_role, granted_by)
    access_rows = [
        # proj_bremen_h2 — owner: HeliosNord GmbH
        ("proj_bremen_h2", "heliosnord_gmbh",        "PRODUCER",    "OWNER",            "heliosnord_gmbh"),
        ("proj_bremen_h2", "allianz",                "INSURER",     "MANDATED_INSURER", "heliosnord_gmbh"),
        ("proj_bremen_h2", "siemens_energy",         "EPC_CONTRACTOR","STAKEHOLDER",    "heliosnord_gmbh"),

        # proj_rotterdam_nh3 — owner: RotterdamGreenFuels BV
        ("proj_rotterdam_nh3", "rotterdamgreenfuels_bv",   "PRODUCER",   "OWNER",            "rotterdamgreenfuels_bv"),
        ("proj_rotterdam_nh3", "allianz",                  "INSURER",    "MANDATED_INSURER", "rotterdamgreenfuels_bv"),
        ("proj_rotterdam_nh3", "zurich_versicherung_ag",   "INSURER",    "MANDATED_INSURER", "rotterdamgreenfuels_bv"),

        # proj_sansebastian_emethanol — owner: Helios Energia SL
        ("proj_sansebastian_emethanol", "helios_energia_sl", "PRODUCER",   "OWNER",            "helios_energia_sl"),
        ("proj_sansebastian_emethanol", "allianz",           "INSURER",    "MANDATED_INSURER", "helios_energia_sl"),

        # proj_wales_saf — owner: Celtic Green Fuels Ltd
        ("proj_wales_saf", "celtic_green_fuels_ltd",  "PRODUCER",   "OWNER",            "celtic_green_fuels_ltd"),
        ("proj_wales_saf", "zurich_versicherung_ag",  "INSURER",    "MANDATED_INSURER", "celtic_green_fuels_ltd"),

        # proj_lehavre_eng — owner: Normandie Hydrogene SA
        ("proj_lehavre_eng", "normandie_hydrogene_sa",  "PRODUCER",   "OWNER",            "normandie_hydrogene_sa"),
        ("proj_lehavre_eng", "allianz",                 "INSURER",    "MANDATED_INSURER", "normandie_hydrogene_sa"),
        ("proj_lehavre_eng", "zurich_versicherung_ag",  "INSURER",    "MANDATED_INSURER", "normandie_hydrogene_sa"),

        # proj_hamburgone_emethanol — owner: HamburgOne.com
        ("proj_hamburgone_emethanol", "hamburgone_com",         "PRODUCER",          "OWNER",            "hamburgone_com"),
        ("proj_hamburgone_emethanol", "nordlb",                 "COMMERCIAL_BANKER", "MANDATED_LENDER",  "hamburgone_com"),
        ("proj_hamburgone_emethanol", "brementhree_ag",         "OFFTAKER",          "STAKEHOLDER",      "hamburgone_com"),
        ("proj_hamburgone_emethanol", "allianz",                "INSURER",           "MANDATED_INSURER", "hamburgone_com"),
        ("proj_hamburgone_emethanol", "siemens_energy",         "EPC_CONTRACTOR",    "STAKEHOLDER",      "hamburgone_com"),

        # proj_madrid2_sansebastian — owner: Madrid2.com
        ("proj_madrid2_sansebastian", "madrid2_com",            "PRODUCER",          "OWNER",            "madrid2_com"),
        ("proj_madrid2_sansebastian", "abn_amro",               "COMMERCIAL_BANKER", "MANDATED_LENDER",  "madrid2_com"),
        ("proj_madrid2_sansebastian", "rotterdamofftake4_ag",   "OFFTAKER",          "STAKEHOLDER",      "madrid2_com"),
        ("proj_madrid2_sansebastian", "zurich_versicherung_ag", "INSURER",           "MANDATED_INSURER", "madrid2_com"),
    ]
    for project_id, company_id, actor_type, access_role, granted_by in access_rows:
        conn.execute(text("""
            INSERT INTO project_access
                (project_id, company_id, actor_type, access_role, granted_by)
            VALUES (:pid, :cid, :at, :ar, :gb)
            ON CONFLICT (project_id, company_id, actor_type) DO UPDATE
              SET access_role = EXCLUDED.access_role,
                  granted_by  = EXCLUDED.granted_by
        """), {"pid": project_id, "cid": company_id, "at": actor_type, "ar": access_role, "gb": granted_by})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP POLICY IF EXISTS project_access_tenant_isolation ON project_access"))
    conn.execute(sa.text("DROP POLICY IF EXISTS projects_tenant_isolation ON projects"))

    op.drop_table("project_access")
    op.drop_table("projects")
    op.drop_table("tenants")

    for enum_name in ("project_access_role_enum", "company_type_enum", "actor_type_enum"):
        conn.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
