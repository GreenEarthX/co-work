"""
KYC/KYB: provenance is a fact about a row, not a label anyone may claim.
========================================================================
Seeding a pre-production platform with plausible values is legitimate — it is
how a prospect sees their own shape of problem, and the values will later come
from OSINT, open-source publications and the geomap before the paying client
edits them. What is NOT legitimate is a seeded value that claims to be
verified: 125 fabricated `bankability_evidence` rows carried status VERIFIED
and fed a risk classification indistinguishable from a real one.

So migration 051 makes provenance a column with a CHECK constraint, and these
tests hold the rules that make the column mean something.
"""
from __future__ import annotations

import pytest

from app.core import kyc_store
from app.core.db_backend import governance_is_postgres
from app.core.request_tenant import (
    reset_current_company, reset_current_user,
    set_current_company, set_current_user,
)
from tests.pg_support import pg_connect, requires_pg

SUBJECT = "kyctest_subject_user"
COLLEAGUE = "kyctest_colleague_user"
COMPANY = "kyctest_company"
STAFF = "admin_greenearthx_com"


@pytest.fixture(autouse=True)
def _pg_only():
    requires_pg()
    if not governance_is_postgres():
        pytest.skip("GOVERNANCE_DB_BACKEND is sqlite — kyc_store requires PostgreSQL")


@pytest.fixture
def as_subject():
    """Bind the subject's identity, and remove their rows afterwards.

    These tests write the development database — `isolated_store` cannot help,
    because the store only exists on PostgreSQL. So they clean up exactly the
    ids they invented, which no real account can collide with.
    """
    ut, ct = set_current_user(SUBJECT), set_current_company(COMPANY)
    try:
        yield
    finally:
        reset_current_user(ut)
        reset_current_company(ct)
        conn = pg_connect()
        try:
            cur = conn.cursor()
            cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
            cur.execute("DELETE FROM kyc_profiles WHERE user_id = ANY(%s)",
                        ([SUBJECT, COLLEAGUE],))
            cur.execute("DELETE FROM kyb_records WHERE company_id = %s", (COMPANY,))
            cur.execute("DELETE FROM kyb_invitations WHERE company_id = %s", (COMPANY,))
            conn.commit()
        finally:
            conn.close()


# ── Provenance ──────────────────────────────────────────────────────────────

def test_a_new_submission_is_client_asserted_not_verified(as_subject):
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada"})
    row = kyc_store.get_profile(SUBJECT)
    assert row["provenance"] == "CLIENT_ASSERTED"
    assert row["verified_by"] is None and row["verified_at"] is None


@pytest.mark.parametrize("provenance", ["SEED", "EXTERNAL_PRIOR"])
def test_seeded_and_osint_values_are_allowed_and_say_so(as_subject, provenance):
    """The point of the column. A pre-production platform may hold plausible
    values, and a prospect's record may be pre-filled from a publication —
    provided the row admits which it is."""
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"companyName": "Acme"},
                             provenance=provenance, source_ref="companies-house/12345")
    row = kyc_store.get_profile(SUBJECT)
    assert row["provenance"] == provenance
    assert row["source_ref"] == "companies-house/12345"
    assert row["verified_by"] is None


def test_a_writer_cannot_declare_its_own_row_verified(as_subject):
    with pytest.raises(kyc_store.KycError) as exc:
        kyc_store.upsert_profile(SUBJECT, COMPANY, profile={}, provenance="VERIFIED")
    assert "verify()" in str(exc.value)


def test_a_subject_cannot_verify_themselves(as_subject):
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada"})
    with pytest.raises(kyc_store.KycError):
        kyc_store.verify(SUBJECT, verified_by=SUBJECT)


def test_verification_records_who_and_when(as_subject):
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada"})
    row = kyc_store.verify(SUBJECT, verified_by=STAFF)
    assert row["provenance"] == "VERIFIED"
    assert row["verified_by"] == STAFF and row["verified_at"]


def test_editing_a_verified_record_drops_the_verification(as_subject):
    """A record that changed after it was checked has not been checked."""
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada"})
    kyc_store.verify(SUBJECT, verified_by=STAFF)
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada", "jobTitle": "CTO"})
    row = kyc_store.get_profile(SUBJECT)
    assert row["provenance"] == "CLIENT_ASSERTED"
    assert row["verified_by"] is None and row["verified_at"] is None


def test_the_database_itself_refuses_a_seeded_row_wearing_a_verifier(as_subject):
    """Belt and braces: 051's CHECK constraint, not just the Python guard.

    A future writer that bypasses `kyc_store` must still be unable to file a
    SEED row with somebody's name in `verified_by`.
    """
    conn = pg_connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        with pytest.raises(Exception) as exc:
            cur.execute(
                "INSERT INTO kyc_profiles (user_id, company_id, profile_json, "
                "provenance, verified_by, verified_at, created_at, updated_at) "
                "VALUES (%s,%s,'{}','SEED',%s,'now','now','now')",
                (SUBJECT, COMPANY, STAFF))
        assert "ck_kyc_profiles_verified_fields" in str(exc.value)
    finally:
        conn.rollback()
        conn.close()


# ── Who can see it ──────────────────────────────────────────────────────────

def test_a_colleague_cannot_read_another_users_kyc(as_subject):
    """A personal identity submission is not company property — unlike the KYB
    record, which describes the legal entity and IS company-scoped."""
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada"})

    ut = set_current_user(COLLEAGUE)
    try:
        assert kyc_store.get_profile(SUBJECT) is None
    finally:
        reset_current_user(ut)


def test_gex_staff_can_read_it_because_vetting_is_what_kyc_is_for(as_subject):
    """The deliberate opposite of the canvas (migration 050), which has no
    admin clause at all. KYC exists to be reviewed."""
    kyc_store.upsert_profile(SUBJECT, COMPANY, profile={"firstName": "Ada"})

    ct = set_current_company("PLATFORM_ADMIN")
    try:
        assert kyc_store.get_profile(SUBJECT) is not None
    finally:
        reset_current_company(ct)


def test_the_kyb_record_is_company_scoped(as_subject):
    kyc_store.upsert_kyb(
        COMPANY, legal_name="Acme SA", registration_number="X-1",
        country="FR", registered_address="1 rue", responsible_name="Ada",
        responsible_email="ada@acme.example")

    ut = set_current_user(COLLEAGUE)   # same company, different person
    try:
        assert kyc_store.get_kyb(COMPANY)["legal_name"] == "Acme SA"
    finally:
        reset_current_user(ut)

    ct = set_current_company("some_other_company")
    try:
        assert kyc_store.get_kyb(COMPANY) is None
    finally:
        reset_current_company(ct)
