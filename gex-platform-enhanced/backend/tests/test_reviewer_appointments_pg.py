"""
Reviewer appointments on PostgreSQL: the project_access row that RLS needs before
a reviewer's write is accepted, written in the SAME transaction as the role and
the assignment.

Every test runs inside one transaction that is ROLLED BACK, so the development
database is left exactly as found. The test account and the appointment never
commit. Uses the TEST fixture project proj_TEST_gates_reference (owner
hamburgone_com) and the registered tenant `nordlb`, which holds no access to it.
"""
from __future__ import annotations

import contextlib

import pytest

from pg_support import pg_dsn, requires_pg

PID = "proj_TEST_gates_reference"
OWNER = "hamburgone_com"
SHA = "b" * 64


@contextlib.contextmanager
def _tx(company: str):
    """A runtime (gex_app) connection bound to `company`, always rolled back."""
    requires_pg()
    from app.core.db_backend import PostgresConnection

    conn = PostgresConnection(pg_dsn(), company_id=company)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _seed(conn, user_id: str, company: str) -> None:
    if conn.execute("SELECT 1 FROM projects WHERE project_id = ?", (PID,)).fetchone() is None:
        pytest.skip(f"{PID} not loaded (scripts/load_comprehension_test_project.py)")
    conn.execute("INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                 "business_function, user_name, account_state) VALUES (?,?,?,?,?,?,?,?,?)",
                 (user_id, f"{user_id}@test.invalid", "TEST-not-a-hash", company, "TEST", "THIRD_PARTY",
                  "EXECUTIVE", f"TEST {user_id}", "ACTIVE"))


def _has_access(conn, company: str) -> bool:
    return bool(conn.execute("SELECT app_company_has_project_access(?, ?) AS ok", (PID, company)).fetchone()["ok"])


def test_an_appointment_writes_the_access_row_rls_needs_in_one_transaction():
    from app.core import reviewer_appointments as ra

    with _tx("PLATFORM_ADMIN") as conn:          # a GEX admin's request binds this
        _seed(conn, "u_TEST_pg_adviser", "nordlb")
        assert not _has_access(conn, "nordlb")
        ra.appoint(conn, project_id=PID, owner_company_id=OWNER, appointee_user_id="u_TEST_pg_adviser",
                   role="LENDERS_ADVISER", appointer={"user_id": "u_TEST_pg_staff"},
                   instructed_by="TEST lender", instruction_sha256=SHA, write_project_access=True)
        assert _has_access(conn, "nordlb")
        row = conn.execute("SELECT access_role, granted_by FROM project_access WHERE project_id = ? "
                           "AND company_id = ? AND actor_type = ?", (PID, "nordlb", "LENDERS_ADVISER")).fetchone()
        assert (row["access_role"], row["granted_by"]) == ("REVIEWER", "u_TEST_pg_staff")

        ra.revoke(conn, project_id=PID, appointee_user_id="u_TEST_pg_adviser", role="LENDERS_ADVISER",
                  write_project_access=True)
        assert not _has_access(conn, "nordlb")   # the REVIEWER row goes with the last appointee


def test_an_unregistered_company_is_refused_not_created():
    from app.core import reviewer_appointments as ra

    with _tx("PLATFORM_ADMIN") as conn:
        _seed(conn, "u_TEST_pg_unregistered", "test_no_such_tenant")
        with pytest.raises(ra.AppointmentRefused) as exc:
            ra.appoint(conn, project_id=PID, owner_company_id=OWNER, appointee_user_id="u_TEST_pg_unregistered",
                       role="INDEPENDENT_ENGINEER", appointer={"user_id": "u_TEST_pg_staff"},
                       instructed_by="TEST lender", instruction_sha256=SHA, write_project_access=True)
        assert exc.value.code == "REVIEWER_COMPANY_NOT_REGISTERED"
        assert conn.execute("SELECT 1 FROM tenants WHERE company_id = 'test_no_such_tenant'").fetchone() is None
