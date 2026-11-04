"""
The PF engine keeps nothing in SQLite (JML, 2026-11-04).

1. The pricing run log and the parameter-change log are PostgreSQL tables owned
   by the platform's migration 082, written by the engine's own role gex_engine.
   Until then they were a local file, engine_model_runs.db, outside every backup.
2. The offered fuels come from the platform's API (public reference data). Until
   then this engine opened the platform's retired SQLite file gex_platform.db and
   fell back to gex_fuel_catalog.json.

No test here touches a real database or the live platform: the connection and the
HTTP call are replaced by fakes. The platform side — the tables, the role, its
privileges — is tested in gex-platform-enhanced/backend/tests/test_engine_run_log_pg.py.
"""
from __future__ import annotations

import ast
import pathlib

import httpx
import pytest
from fastapi import HTTPException

from pf_engine.api import routes_pricing
from pf_engine.core import model_governance as mg

PACKAGE = pathlib.Path(mg.__file__).resolve().parents[1]


# ── no SQLite anywhere ───────────────────────────────────────────────────────

def test_no_engine_module_imports_sqlite3():
    """By the AST, not the text: comments here are allowed to name it."""
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            if any(n == "sqlite3" or n.startswith("sqlite3.") for n in names):
                offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


# ── the run log ──────────────────────────────────────────────────────────────

class FakeConn:
    """Records what the engine executes; behaves like a psycopg2 connection."""

    def __init__(self, fail=False):
        self.fail, self.executed, self.closed, self.committed = fail, [], False, False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError("TEST: the database refused")
        self.executed.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.committed = True
        return False

    def close(self):
        self.closed = True


def _stamp():
    return mg.governance_stamp("TEST/endpoint", "E_METHANOL", {"alpha": 1.0}, 0, {"x": 1}, [])


def test_without_a_dsn_the_run_is_stamped_not_logged_and_no_file_appears(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                      # where the old SQLite file used to be created
    stamp = _stamp()
    assert stamp["run_logged"] is False
    assert list(tmp_path.iterdir()) == []


def test_a_run_is_inserted_into_the_postgres_table(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(mg, "_runs_conn", lambda: conn)
    stamp = _stamp()
    assert stamp["run_logged"] is True
    (sql, params), = conn.executed
    assert sql.startswith("INSERT INTO engine_model_runs") and "%s" in sql and "?" not in sql
    assert params[0] == stamp["run_id"] and params[1] == "TEST/endpoint"
    assert conn.committed and conn.closed


def test_a_refused_write_never_blocks_pricing(monkeypatch):
    monkeypatch.setattr(mg, "_runs_conn", lambda: FakeConn(fail=True))
    assert _stamp()["run_logged"] is False


def test_a_parameter_change_says_whether_it_was_logged(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(mg, "_runs_conn", lambda: conn)
    change = mg.log_param_change("E_METHANOL", {"alpha": 1.0}, {"alpha": 2.0}, 3, "TEST")
    assert change["change_logged"] is True
    assert conn.executed[0][0].startswith("INSERT INTO engine_param_change_events")
    monkeypatch.setattr(mg, "_runs_conn", lambda: FakeConn(fail=True))
    assert mg.log_param_change("E_METHANOL", None, {"alpha": 2.0}, 0, "TEST")["change_logged"] is False


def test_reading_the_log_without_a_dsn_says_so():
    with pytest.raises(mg.RunLogUnavailable):
        mg.recent_runs(5)


# ── the fuel catalogue ───────────────────────────────────────────────────────

PLATFORM_ANSWER = {"version": "TEST", "source": "postgres", "fuels": [
    {"label": "e-Methanol", "offered": True, "is_active": True},
    {"label": "SAF", "offered": True, "is_active": True},
    {"label": "e-NH3", "offered": False, "is_active": True},        # not offered
    {"label": "HVO", "offered": True, "is_active": False},          # retired
    {"label": "TEST Unpriceable Fuel", "offered": True, "is_active": True},  # no model for it
]}


class FakePlatform:
    def __init__(self):
        self.calls, self.down = [], False

    def get(self, url, timeout):
        self.calls.append(url)
        if self.down:
            raise httpx.ConnectError("TEST: platform down")
        return httpx.Response(200, json=PLATFORM_ANSWER, request=httpx.Request("GET", url))


@pytest.fixture
def platform(monkeypatch):
    fake = FakePlatform()
    monkeypatch.setattr(routes_pricing.httpx, "get", fake.get)
    monkeypatch.setitem(routes_pricing._fuel_cache, "labels", None)
    monkeypatch.setitem(routes_pricing._fuel_cache, "at", 0.0)
    return fake


@pytest.mark.real_fuel_lookup
def test_offered_fuels_come_from_the_platform_route(platform):
    assert routes_pricing._load_offered_molecules() == ["e-Methanol", "SAF"]
    assert platform.calls == [routes_pricing.PLATFORM_API_URL + "/api/v1/onboarding/reference-data/fuels"]


@pytest.mark.real_fuel_lookup
def test_the_answer_is_cached(platform):
    routes_pricing._load_offered_molecules()
    routes_pricing._load_offered_molecules()
    assert len(platform.calls) == 1


@pytest.mark.real_fuel_lookup
def test_no_platform_means_503_not_a_stale_copy(platform):
    platform.down = True
    with pytest.raises(HTTPException) as exc:
        routes_pricing._load_offered_molecules()
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "FUEL_CATALOGUE_UNAVAILABLE"
