"""
Projects collision guardrails — one `projects` table, not two.
==============================================================
Ruling (user, 2026-08-07): the **PostgreSQL shape wins**.

Two tables were both called `projects`:

  SQLite   — /projects/new on-ramp. `owner_company_name` was a company NAME
             with no FK, so an owner could be a string matching no tenant.
             No RLS.
  Postgres — migration 020. `owner_tenant_id` FK -> tenants. RLS-protected.

The SQLite one is retired (renamed, not dropped — data recoverable in
`projects_retired_pg_collision_20260807` and in data/db_backups/).

These tests stop it coming back. The failure mode is quiet: SQLite DDL is
`CREATE TABLE IF NOT EXISTS`, so a single reintroduced call would silently
recreate the second table and split project truth again with no error.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"


def _py_sources():
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path, path.read_text()


# ── No second projects table ────────────────────────────────────────────────

def test_no_module_creates_a_sqlite_projects_table():
    """
    The collision came from `CREATE TABLE IF NOT EXISTS projects` in
    project_registry. IF NOT EXISTS never errors, so a reintroduction would be
    invisible until two stores disagreed about who owns a project.
    """
    offenders = [
        str(p.relative_to(BACKEND))
        for p, src in _py_sources()
        if re.search(r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?projects\b", src, re.I)
    ]
    assert not offenders, (
        f"{offenders} creates a SQLite `projects` table. The canonical table is "
        "PostgreSQL (migrations 020/033); use app/core/projects_store.py."
    )


def test_ensure_project_table_is_a_no_op():
    """
    Kept as a no-op rather than deleted, so any surviving caller fails to
    recreate the table instead of quietly succeeding.
    """
    from app.core import project_registry

    assert project_registry.ensure_project_table(None) is None


def test_project_registry_no_longer_queries_a_sqlite_projects_table():
    src = (APP / "core" / "project_registry.py").read_text()
    assert not re.search(r"(FROM|INTO|UPDATE)\s+projects\b", src, re.I), (
        "project_registry still issues SQL against a local `projects` table"
    )


def test_the_retired_sqlite_table_is_renamed_not_deleted():
    """The 2 on-ramp rows must remain recoverable."""
    from app.core.config import settings

    db = Path(settings.SQLITE_DB_PATH)
    if not db.exists():
        pytest.skip("SQLite database not present")
    conn = sqlite3.connect(str(db))
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'projects%'")}
    conn.close()
    assert "projects" not in names, (
        "a SQLite `projects` table exists again — the collision is back"
    )
    assert any(n.startswith("projects_retired") for n in names), (
        "the retired table is gone; the on-ramp rows should stay recoverable"
    )


# ── The canonical store is the only accessor ────────────────────────────────

def test_no_module_creates_sqlite_project_context_tables():
    """
    Same silent-failure shape as the projects table. Between migration 033 and
    this change, create_project wrote the Postgres project_context while
    PATCH /context wrote the SQLite one — two stores, diverging, no error.
    """
    offenders = [
        str(p.relative_to(BACKEND))
        for p, src in _py_sources()
        if re.search(
            r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?project_context(_events)?\b",
            src, re.I)
    ]
    assert not offenders, (
        f"{offenders} creates SQLite project_context tables. They are canonical "
        "in PostgreSQL (migration 033); use app/core/projects_store.py."
    )


def test_ensure_context_tables_is_a_no_op():
    from app.core import project_registry

    assert project_registry.ensure_context_tables(None) is None


def test_routes_projects_does_not_write_context_to_sqlite():
    src = (APP / "api" / "v1" / "routes_projects.py").read_text()
    assert not re.search(r"(INSERT\s+INTO|UPDATE)\s+project_context", src, re.I), (
        "routes_projects still writes project_context directly; it must go "
        "through projects_store.update_context so state and audit commit together"
    )


def test_context_update_writes_state_and_audit_in_one_transaction():
    """
    A context change recorded without its audit row — or an audit row without
    the change — is exactly what the append-only events table exists to
    prevent. They must share a transaction.
    """
    src = (APP / "core" / "projects_store.py").read_text()
    fn = src[src.index("def update_context("):src.index("def create_project(")]
    assert "with _engine().begin()" in fn
    assert "project_context_events" in fn and "INSERT INTO project_context" in fn


def test_the_canonical_store_sets_a_tenant_context_on_every_read():
    """
    projects/project_context are RLS-protected and migration 032 removed the
    empty-string bypass, so a read without `app.current_company_id` returns
    nothing. Every accessor must set it explicitly rather than rely on a
    default that no longer exists.
    """
    src = (APP / "core" / "projects_store.py").read_text()
    assert "SET LOCAL app.current_company_id" in src
    # and it must be whitelisted, not interpolated raw
    assert "_safe(" in src, "company_id must be whitelisted before interpolation"


def test_tenant_context_value_is_whitelisted():
    from app.core.projects_store import _safe

    assert _safe("PLATFORM_ADMIN") == "PLATFORM_ADMIN"
    assert _safe("hamburgone_com") == "hamburgone_com"
    for bad in ["'; DROP TABLE projects; --", "Robert'); --", "UPPER", "has space"]:
        with pytest.raises(ValueError):
            _safe(bad)


def test_create_project_writes_context_in_the_same_store():
    """
    project_context moved to Postgres with projects (033) specifically so
    create_project stays atomic. If a future edit writes context back to
    SQLite, a failed create leaves an orphan.
    """
    src = (APP / "core" / "projects_store.py").read_text()
    create = src[src.index("def create_project("):]
    assert "project_context" in create and "project_context_events" in create
    # Match actual SQLite USE, not the word — the docstring legitimately
    # explains what the old SQLite table used to store.
    assert not re.search(r"sqlite3\.|import\s+sqlite3|\.connect\(", create), (
        "create_project must not open a SQLite connection — it would split the "
        "transaction across two stores and a failed create could leave an orphan"
    )
    # All three writes must be inside one transaction block.
    assert "with _engine().begin()" in create, (
        "create_project must wrap its writes in a single transaction"
    )


# ── The silent-empty-list failure ───────────────────────────────────────────

def test_runtime_visible_projects_reads_the_canonical_store():
    """
    `_runtime_visible_projects` used to query the SQLite `projects` table and
    swallow sqlite3.Error into an empty list. Once that table was retired, every
    runtime project silently disappeared from the very list it was created for —
    no error, no log, just fewer rows. This asserts the source.
    """
    src = (APP / "api" / "v1" / "routes_projects.py").read_text()
    fn = src[src.index("def _runtime_visible_projects("):src.index('@router.get("/visible"')]
    # Strip the docstring: it legitimately DESCRIBES the old sqlite3 behaviour,
    # and matching prose rather than code is how this test first failed.
    body = re.sub(r'"""[\s\S]*?"""', "", fn, count=1)
    assert "projects_store" in body, "must read the canonical store"
    assert not re.search(r"sqlite3\.|import\s+sqlite3", body), "must not query SQLite"
    assert "except sqlite3.Error" not in body, (
        "must not swallow a store failure into an empty list — the store logs "
        "its own failures"
    )


def test_runtime_projects_do_not_get_fabricated_coordinates():
    """
    The old code sent lat=0.0, lng=0.0 for projects whose coordinates were never
    collected — which drops a map pin in the Gulf of Guinea. Null is the honest
    answer, so the model must permit it.
    """
    from app.api.v1.routes_projects import VisibleProject

    # Assert the VALUE is None, not merely that the field has a default —
    # `lat: float = 0.0` also "has a default" and is exactly the bug.
    vp = VisibleProject(
        id="p", name="n", molecule="m", location="l", country="DE",
        capacity_mtpd=1.0, capacity_mt_year=365, capex_eur=1.0,
        status="development", phase="development",
        owner_company="c", associated_companies=[], jurisdiction="DE",
    )
    assert vp.lat is None and vp.lng is None, (
        "a project with no recorded coordinates must report None, not 0.0 — "
        f"got lat={vp.lat} lng={vp.lng}, which is a map pin in the Gulf of Guinea"
    )
    # Check the WHOLE module, not one function: the create handler had the same
    # `lat=0.0, lng=0.0` and a single-function assertion missed it.
    src = (APP / "api" / "v1" / "routes_projects.py").read_text()
    offenders = re.findall(r"l(?:at|ng)\s*=\s*0\.0", src)
    assert not offenders, (
        f"{len(offenders)} site(s) still pass 0.0 coordinates; omit them instead"
    )


def test_runtime_project_owners_pass_the_authorization_check():
    """
    `_visible_ids_from_jwt` is used BOTH to build the list and (line ~883) to
    authorize per-project access. It walks the static registry, so without the
    runtime branch a project's own creator was denied access to it.
    """
    src = (APP / "api" / "v1" / "routes_projects.py").read_text()
    fn = src[src.index("def _visible_ids_from_jwt("):src.index("@router.get")]
    assert "project_ids_owned_by" in fn, (
        "_visible_ids_from_jwt must include runtime-owned projects, or their "
        "owners fail the per-project authorization check"
    )
