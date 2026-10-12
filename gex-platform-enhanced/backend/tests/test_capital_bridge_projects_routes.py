"""
The CapitalBridge routes that read `projects` must use the canonical columns.

WHY THIS FILE EXISTS
--------------------
`GET /api/v1/capital-bridge/users/{user_id}/projects` returned **500 for every
caller** while the suite reported 844 passing. The route selected `p.id` and
`p.stage` from `projects`, and neither has ever been a column of that table:

    canonical PostgreSQL (migration 020/033)   project_id, status
    retired SQLite      (migration 033)        project_id, phase

The second was measured, not assumed, from
`data/db_backups/gex_platform.pre-projects-collision.20260807.db`. So this was
never "written against the old shape" — it was written against a shape that has
never existed anywhere, which is why no frontend code and no test ever consumed
it. The absence of coverage was the actual defect; the column names were only
its first symptom.

The same `WHERE id=?` mistake sat in `_project_exists`, which eight write
routes call as their FK gate, and in `get_full_project`. All are covered here.

WHAT THESE TESTS PIN
--------------------
1. The routes answer 200 against PostgreSQL and the SQL plans (a wrong column
   name is a plan-time error in PostgreSQL, so it fires with zero matching rows
   — but these tests still assert real rows, so a silently-empty result cannot
   pass for a working query).
2. The response keys are the canonical `project_id`/`status`, not aliases back
   to the retired `id`/`stage`. There is no caller to keep compatible (swept
   2026-09-30: zero hits in `frontend/src`, zero in `backend/tests`), and
   `get_full_project` in the same module already returns the canonical names.
3. Absence of a caller fails CLOSED — 200 and an empty list, never a 500 and
   never another tenant's rows.
4. Negative verification, per the repo rule that a new guardrail must be shown
   to fail: `test_the_retired_column_names_still_fail` re-runs the ORIGINAL
   query and asserts PostgreSQL rejects it. Without it, tests 1–3 would pass
   just as happily against a query that was never broken.

NOT `isolated_store`: that fixture pins every slice switch to sqlite, which is
the opposite of what is under test. These ask for PostgreSQL explicitly.
Every read is a SELECT against live development data and writes nothing.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import capital_bridge
from tests.pg_support import pg_admin, requires_pg

# The retired names. Held as data so the assertions and the negative
# verification below cannot drift apart.
RETIRED_COLUMNS = ("id", "stage")


@pytest.fixture(scope="module", autouse=True)
def _postgres_only() -> None:
    """Skip unless the capital slice is actually on PostgreSQL and reachable."""
    from app.core.db_backend import capital_is_postgres

    requires_pg()
    if not capital_is_postgres():
        pytest.skip("CAPITAL_DB_BACKEND is not postgres; this defect is PG-only")


def _client(company: str | None) -> TestClient:
    """A minimal app serving the router, with `company` bound as the caller.

    This mirrors `ABACMiddleware`'s mechanism rather than re-deriving it: the
    ContextVar is set in `dispatch` BEFORE `call_next`, and a child task copies
    the context at spawn time, so the value reaches the shim downstream.
    `tests/test_request_tenant.py` pins that propagation; relying on it here
    keeps this file about the SQL.

    Binding in the middleware — not in the test thread — is load-bearing:
    `TestClient` runs the request in a worker thread, so a ContextVar set
    around the `client.get(...)` call would not be visible to the route.
    """
    from app.core.request_tenant import reset_current_company, set_current_company

    api = FastAPI()

    @api.middleware("http")
    async def _bind_tenant(request, call_next):
        if company is None:
            return await call_next(request)
        token = set_current_company(company)
        try:
            return await call_next(request)
        finally:
            reset_current_company(token)

    api.include_router(capital_bridge.router)
    return TestClient(api)


def _a_user_with_projects() -> tuple[str, int]:
    """A real `(user_id, project_count)` discovered at runtime.

    Deliberately not hardcoded. This tree's `projects` table has been rebuilt
    twice and `auth_user_project_roles` is seeded data; a pinned user id would
    turn the next rebuild into a false failure in a test about column names.
    """
    conn, cur = pg_admin()
    try:
        cur.execute("""
            SELECT r.user_id, count(*) AS n
            FROM auth_user_project_roles r
            JOIN projects p ON p.project_id = r.project_id
            GROUP BY r.user_id
            ORDER BY n DESC, r.user_id
            LIMIT 1
        """)
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("no user is linked to any project in this database")
    return row["user_id"], int(row["n"])


# ── 1. the route answers, and answers with rows ─────────────────────────────

def test_list_projects_for_user_returns_200_with_rows():
    """The defect: this was a 500 for every caller, for every user_id."""
    user_id, expected = _a_user_with_projects()

    response = _client("PLATFORM_ADMIN").get(
        f"/api/v1/capital-bridge/users/{user_id}/projects"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # Asserting rows, not just 200: a query naming a column that does not exist
    # fails at plan time in PostgreSQL, so an empty result would mask nothing
    # here — but a future change that quietly filtered everything away would
    # still be a regression, and this is what catches it.
    assert len(body) == expected, f"{user_id} should see {expected} projects"


def test_the_response_uses_the_canonical_column_names():
    """`project_id`/`status`, never the retired `id`/`stage`.

    Pinned because the alternative fix — `SELECT p.project_id AS id` — would
    have kept a retired vocabulary alive in a JSON contract that no caller
    depends on. `stage` is not a word this platform's project vocabulary uses.
    """
    user_id, _ = _a_user_with_projects()

    row = _client("PLATFORM_ADMIN").get(
        f"/api/v1/capital-bridge/users/{user_id}/projects"
    ).json()[0]

    assert "project_id" in row
    assert "status" in row
    for retired in RETIRED_COLUMNS:
        assert retired not in row, f"retired column name {retired!r} is back"


def test_list_projects_for_company_returns_200():
    """Same retired `p.id`; same 500. Empty is a legitimate answer here.

    The route joins on `project_control.company_id`, and `project_control`
    holds 0 rows in this database, so the honest assertion is the status code
    and the shape — not a row count that would be asserting the seed.
    """
    response = _client("PLATFORM_ADMIN").get(
        "/api/v1/capital-bridge/companies/etfuels_sa/projects"
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_get_full_project_resolves_a_real_project():
    """`SELECT * FROM projects WHERE id=?` — the same defect, a 404's worth of
    difference: it could not even reach the "not found" branch."""
    conn, cur = pg_admin()
    try:
        cur.execute("SELECT project_id FROM projects WHERE is_active LIMIT 1")
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("no active project in this database")
    project_id = row["project_id"]

    response = _client("PLATFORM_ADMIN").get(
        f"/api/v1/capital-bridge/projects/{project_id}/full"
    )

    assert response.status_code == 200, response.text
    assert response.json()["project"]["project_id"] == project_id


def test_a_missing_project_is_404_not_500():
    """The 404 branch was unreachable while the WHERE clause named `id`."""
    response = _client("PLATFORM_ADMIN").get(
        "/api/v1/capital-bridge/projects/proj_does_not_exist/full"
    )

    assert response.status_code == 404, response.text


# ── 2. the absence of a caller, and another tenant's caller ─────────────────

def test_no_tenant_context_returns_200_and_no_rows():
    """Fails closed. The deny sentinel matches no policy, so the route answers
    an empty list — not a 500, and not somebody else's portfolio."""
    user_id, _ = _a_user_with_projects()

    response = _client(None).get(
        f"/api/v1/capital-bridge/users/{user_id}/projects"
    )

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_a_tenant_cannot_read_another_tenants_user():
    """The route takes `user_id` from the path and authorizes nothing, so RLS on
    `projects` IS the access control — the same shape as the project-activity
    hole fixed on 2026-09-24. `auth_user_project_roles` carries no RLS; the
    INNER JOIN to `projects` is what contains the read. Measured, because
    "the join protects it" is exactly the kind of claim that stops being true.
    """
    user_id, _ = _a_user_with_projects()

    conn, cur = pg_admin()
    try:
        cur.execute(
            "SELECT DISTINCT p.owner_tenant_id FROM projects p "
            "JOIN auth_user_project_roles r ON r.project_id = p.project_id "
            "WHERE r.user_id = %s",
            (user_id,),
        )
        owners = {r["owner_tenant_id"] for r in cur.fetchall()}
        cur.execute(
            "SELECT company_id FROM tenants WHERE company_id <> ALL(%s) LIMIT 1",
            (list(owners) or [""],),
        )
        other = cur.fetchone()
    finally:
        conn.close()
    if not other:
        pytest.skip("no second tenant to read across")

    response = _client(other["company_id"]).get(
        f"/api/v1/capital-bridge/users/{user_id}/projects"
    )

    assert response.status_code == 200, response.text
    assert response.json() == [], (
        f"{other['company_id']} read projects owned by {owners}"
    )


# ── 3. negative verification ───────────────────────────────────────────────

@pytest.mark.parametrize("retired", RETIRED_COLUMNS)
def test_the_retired_column_names_still_fail(retired):
    """Prove the tests above are not vacuous.

    Every assertion here would pass against a query that had never been broken.
    This one re-runs the shape the route actually had and requires PostgreSQL
    to reject it, so if `projects` ever grows an `id` or a `stage` column this
    file says so instead of going quietly green.
    """
    import psycopg2

    conn, cur = pg_admin()
    try:
        with pytest.raises(psycopg2.errors.UndefinedColumn):
            cur.execute(f"SELECT p.{retired} FROM projects p LIMIT 1")
    finally:
        conn.rollback()
        conn.close()
