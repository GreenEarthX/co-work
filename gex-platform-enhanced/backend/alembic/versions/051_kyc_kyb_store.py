"""KYC / KYB — out of localStorage, into the database, with provenance.

Revision ID: 051
Revises: 050
Create Date: 2026-09-23

WHAT WAS WRONG
--------------
`frontend/src/features/kyc/kycState.ts` kept the whole KYC/KYB record in
`localStorage`: ~45 profile fields (name, phone, company email, job title,
project and plant detail) and the KYB record — legal name, registration
number, VAT id, registered address, BENEFICIAL OWNERS and the responsible
person. Regulated, personal, and living in one browser profile: lost on a new
device, invisible to the backend, and impossible for GEX to review, which is
the entire purpose of collecting it.

Meanwhile `auth_users.kyc_status` defaults to 'VERIFIED' and 19 of 20 rows say
VERIFIED — a verification claim about evidence the database had never seen.

PROVENANCE IS A COLUMN, NOT A CONVENTION
----------------------------------------
Every row here declares where its values came from:

    SEED             a plausible value made up to exercise the platform
    EXTERNAL_PRIOR   gathered from OSINT, an open-source publication, or the
                     geomap database — a real-world prior, not a client claim
    CLIENT_ASSERTED  the client typed it
    VERIFIED         GEX checked it against a document, and says who and when

This is deliberate and it is the difference between useful seed data and a
liability. Seeding the database with plausible values while the platform is
pre-production is legitimate — it is how a prospect sees their own shape of
problem. What is NOT legitimate is a seeded value that claims to be verified:
that is exactly how 125 fabricated `bankability_evidence` rows came to carry
status VERIFIED and feed a risk classification indistinguishable from a real
one. A CHECK constraint enforces the vocabulary, and `verified_by` /
`verified_at` are NULL unless provenance is VERIFIED.

The lifecycle runs one way in practice — SEED or EXTERNAL_PRIOR first, then
CLIENT_ASSERTED when the paying client edits it, then VERIFIED — but this
migration does not enforce a direction. A client correcting a verified field
back to asserted is a real event, and a schema that forbade it would make the
platform lie rather than make the client honest.

SCOPING, AND WHY IT DIFFERS FROM THE CANVAS
-------------------------------------------
Migration 050 gave canvas documents an owner-only policy with NO admin clause,
because a canvas is private work and nobody at GEX has business reading it.

KYC is the opposite case BY PURPOSE: it exists to be reviewed by GEX staff.
Vetting an account (`app/core/account_lifecycle.py` — telephone verification, a
signed usage agreement, separation of duties) is impossible if the vetting
party cannot read the submission. So these policies admit the subject and
PLATFORM_ADMIN, and that is a considered difference, not an inconsistency.

A colleague in the same company still cannot read your KYC profile: a personal
identity submission is not company property. The KYB record is the opposite
again — it describes the legal ENTITY, so it is company-scoped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "051"
down_revision: Union[str, None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"
OWNER = "user_id = current_setting('app.current_user_id', true)"

PROVENANCE = ("SEED", "EXTERNAL_PRIOR", "CLIENT_ASSERTED", "VERIFIED")
_PROV_CHECK = "provenance IN (" + ", ".join(f"'{p}'" for p in PROVENANCE) + ")"
# verified_by/at belong to VERIFIED and nothing else. Without this a SEED row
# could carry a verifier's name, which is the failure this whole column exists
# to prevent — a fabricated value wearing someone's signature.
_VERIFIED_CHECK = (
    "(provenance = 'VERIFIED') OR (verified_by IS NULL AND verified_at IS NULL)")


def upgrade() -> None:
    op.create_table(
        "kyc_profiles",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("company_id", sa.Text(), nullable=False),
        # production | infrastructure | offtaker — the role decides which of the
        # profile fields apply, so it is a column rather than buried in JSON.
        sa.Column("kyc_role", sa.Text()),
        # The ~45 role-dependent fields. JSON because the set genuinely differs
        # per role and is still moving; the fields that policy or SQL must reason
        # about are columns.
        sa.Column("profile_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="CLIENT_ASSERTED"),
        # Where an EXTERNAL_PRIOR came from: a URL, a publication, a geomap id.
        # Required in spirit for EXTERNAL_PRIOR; not enforced, because an honest
        # "unknown source" beats a fabricated citation.
        sa.Column("source_ref", sa.Text()),
        sa.Column("submitted_at", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("verified_at", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(_PROV_CHECK, name="ck_kyc_profiles_provenance"),
        sa.CheckConstraint(_VERIFIED_CHECK, name="ck_kyc_profiles_verified_fields"),
    )
    op.create_index("idx_kyc_profiles_company", "kyc_profiles", ["company_id"])

    op.create_table(
        "kyb_records",
        sa.Column("company_id", sa.Text(), primary_key=True),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("registration_number", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("vat_id", sa.Text()),
        sa.Column("registered_address", sa.Text(), nullable=False),
        # Free text today, as the browser stored it. A beneficial-ownership
        # GRAPH is the right model and is a separate piece of work; storing the
        # string as given is honest, inventing a structure for it is not.
        sa.Column("beneficial_owners", sa.Text()),
        sa.Column("responsible_name", sa.Text(), nullable=False),
        sa.Column("responsible_email", sa.Text(), nullable=False),
        sa.Column("responsible_job_title", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="none"),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="CLIENT_ASSERTED"),
        sa.Column("source_ref", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("verified_at", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(_PROV_CHECK, name="ck_kyb_records_provenance"),
        sa.CheckConstraint(_VERIFIED_CHECK, name="ck_kyb_records_verified_fields"),
        sa.CheckConstraint("status IN ('none', 'pending_colleague', 'completed')",
                           name="ck_kyb_records_status"),
    )

    op.create_table(
        "kyb_invitations",
        sa.Column("invitation_id", sa.Text(), primary_key=True),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("company_domain", sa.Text()),
        sa.Column("invited_by", sa.Text(), nullable=False),
        sa.Column("invited_by_name", sa.Text()),
        sa.Column("accepted_at", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("company_id", "email", name="uq_kyb_invitation"),
    )
    op.create_index("idx_kyb_invitations_company", "kyb_invitations", ["company_id"])

    conn = op.get_bind()

    def rls(table: str, using: str):
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY {table}_isolation ON {table} FOR ALL USING ({using})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))

    # The subject, or GEX staff doing the vetting. NOT the subject's colleagues.
    rls("kyc_profiles", f"{ADMIN} OR {OWNER}")
    # The legal entity's own record — company-scoped.
    rls("kyb_records", f"{ADMIN} OR company_id = {ME}")
    rls("kyb_invitations", f"{ADMIN} OR company_id = {ME}")


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("kyc_profiles", "kyb_records", "kyb_invitations"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_isolation ON {table}"))
    for table in ("kyb_invitations", "kyb_records", "kyc_profiles"):
        op.drop_table(table)
