"""
The comprehension fixture loads, reloads and removes cleanly (Phase 2, 2026-11-06).

Phase 0 §7 item 7: its --remove deleted `projects` but not the project's contracts
(078), which reference it — so --remove, and --execute (which removes first), would
fail; and its load never wrote the cards' contract versions. Now it removes the
project's contract record (and any 078 rows) first, and writes the versions through
the card-save path. Run in the throwaway database (conftest.pg_store), never on the
development database.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import psycopg2.extras
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "load_comprehension_test_project.py"


@pytest.fixture(scope="module")
def loader(pg_store):
    from app.db import session

    saved = session._sync_engine            # projects_store's cached engine: never leak the throwaway one
    session._sync_engine = None
    spec = importlib.util.spec_from_file_location("comprehension_loader", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from pg_support import connect_dsn

    owner = os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + pg_store.rsplit("/", 1)[1]
    conn = connect_dsn(owner)
    conn.cursor_factory = psycopg2.extras.DictCursor          # the loader indexes rows by position
    conn.cursor().execute("INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, 'TEST HamburgOne', "
                          "'PRODUCER') ON CONFLICT DO NOTHING", (mod.OWNER_TENANT,))
    conn.commit()
    yield mod, conn
    conn.close()
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


def _counts(conn, pid):
    cur = conn.cursor()
    cur.execute("SELECT (SELECT count(*) FROM projects WHERE project_id = %s), "
                "(SELECT count(*) FROM tb_contract WHERE project_id = %s), "
                "(SELECT count(*) FROM tb_contract_event e JOIN tb_contract c ON c.id = e.contract_id "
                " WHERE c.project_id = %s AND e.event_type = 'VERSION' AND e.actor = 'TEST_FIXTURE_COMPREHENSION')",
                (pid, pid, pid))
    return tuple(cur.fetchone())


def test_load_writes_the_versions_reload_replaces_them_and_remove_clears_everything(loader):
    mod, conn = loader
    mod.load(conn, execute=True)
    assert _counts(conn, mod.PROJECT_ID) == (1, 4, 4)       # offtake, supply, epc, technical — as on 28 Oct
    mod.load(conn, execute=True)                              # removes first: no foreign-key failure
    assert _counts(conn, mod.PROJECT_ID) == (1, 4, 4)
    mod.remove(conn, execute=True)
    assert _counts(conn, mod.PROJECT_ID) == (0, 0, 0)
