"""PostgreSQL only at runtime (JML, 2026-11-11).

The backend refuses to start while any *_DB_BACKEND switch reads sqlite, every switch
defaults to postgres, the refusal runs in main.py before any module sets up a table, and
the two init functions that used to open the SQLite file on a PostgreSQL backend (one of
them crashed a Docker worker: four workers racing for the file) no longer do.
Pure: no database is needed.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from app.core import db_backend
from app.core.config import Settings, settings

BACKEND = Path(__file__).resolve().parents[1]
SWITCHES = sorted(n for n in Settings.model_fields if n.endswith("_DB_BACKEND"))


def test_there_are_ten_switches_and_every_default_is_postgres():
    assert len(SWITCHES) == 10, SWITCHES
    assert {n: Settings.model_fields[n].default for n in SWITCHES} == {n: "postgres" for n in SWITCHES}
    assert Settings.model_fields["ALLOW_SQLITE_BACKEND"].default is False


def _pin(monkeypatch, value: str, allow: bool) -> None:
    for n in SWITCHES:
        monkeypatch.setattr(settings, n, "postgres")
    monkeypatch.setattr(settings, "ALLOW_SQLITE_BACKEND", allow)
    if value != "postgres":
        monkeypatch.setattr(settings, "CAPITAL_DB_BACKEND", value)


def test_all_postgres_starts(monkeypatch):
    _pin(monkeypatch, "postgres", allow=False)
    db_backend.assert_postgres_runtime()


@pytest.mark.parametrize("value", ["sqlite", "", "Sqlite "])
def test_one_switch_off_postgres_refuses_and_names_it(monkeypatch, value):
    _pin(monkeypatch, value, allow=False)
    with pytest.raises(RuntimeError) as exc:
        db_backend.assert_postgres_runtime()
    assert "POSTGRES_REQUIRED" in str(exc.value) and "CAPITAL_DB_BACKEND" in str(exc.value)


def test_only_the_explicit_opt_out_lets_sqlite_through(monkeypatch):
    _pin(monkeypatch, "sqlite", allow=True)
    db_backend.assert_postgres_runtime()


def test_main_refuses_before_any_module_sets_up_a_table():
    """The call is a top-level statement of main.py, above the first app.api import."""
    body = ast.parse((BACKEND / "app" / "main.py").read_text()).body
    calls = [i for i, n in enumerate(body) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "id", None) == "assert_postgres_runtime"]
    assert calls, "main.py does not call assert_postgres_runtime() at top level"
    first_app_import = min(i for i, n in enumerate(body) if isinstance(n, (ast.Import, ast.ImportFrom))
                           and (getattr(n, "module", "") or "").startswith("app.api"))
    assert calls[0] < first_app_import


@pytest.mark.parametrize("module, slice_switch", [
    ("app.api.v1.development_packages", "CAPITAL_DB_BACKEND"),
    ("app.api.v1.adjacency", "DOMAIN_DB_BACKEND"),
])
def test_init_db_opens_no_sqlite_file_on_postgres(monkeypatch, module, slice_switch):
    import importlib

    mod = importlib.import_module(module)
    monkeypatch.setattr(settings, slice_switch, "postgres")
    monkeypatch.setenv(slice_switch, "postgres")      # the slice helpers read os.environ first
    opened = []
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(
        AssertionError(f"{module}.init_db opened SQLite {a}")))
    mod.init_db()
    assert opened == []
