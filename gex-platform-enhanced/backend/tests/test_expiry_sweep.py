"""
The expiry sweep (scripts/expire_evidence.py, rules 4.5.0): which projects it re-evaluates, and that
one project's failure neither stops the others nor hides itself. Isolated SQLite store; no engine.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.api.v1 import routes_bankability_proxy as proxy

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture(scope="module")
def sweep_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "expire_evidence.py"
    spec = importlib.util.spec_from_file_location("expire_evidence", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["expire_evidence"] = mod
    spec.loader.exec_module(mod)
    return mod


def _store(pid: str, next_expiry):
    proxy._store_snapshot(pid, "BUILDABLE", json.dumps({"next_expiry": next_expiry, "rules_version": "t"}))


def test_only_projects_whose_next_expiry_has_passed_are_swept(isolated_store, sweep_module):
    """Negative-verified 2026-10-31: comparing with <= instead of < sweeps the last valid day too."""
    _store("sw-stale", YESTERDAY)
    _store("sw-last-day", TODAY)
    _store("sw-later", TOMORROW)
    _store("sw-none", None)
    assert sweep_module.stale_projects(TODAY) == [("sw-stale", YESTERDAY)]


def test_one_failure_does_not_stop_the_others_and_is_reported(isolated_store, sweep_module, monkeypatch, capsys):
    calls: list[str] = []

    async def reeval(pid, **kw):
        calls.append(pid)
        if pid == "sw-b":
            raise RuntimeError("engine unavailable")
        return {"snapshot": {"current_state": "SPECULATIVE", "expired_evidence": []}}

    monkeypatch.setattr(proxy, "reevaluate", reeval)
    failed = asyncio.run(sweep_module.sweep([("sw-a", YESTERDAY), ("sw-b", YESTERDAY), ("sw-c", YESTERDAY)]))
    assert calls == ["sw-a", "sw-b", "sw-c"] and failed == ["sw-b"]
    assert "FAILED sw-b" in capsys.readouterr().out


def test_the_sweep_acts_as_the_system_and_says_why(isolated_store, sweep_module, monkeypatch):
    seen: dict = {}

    async def reeval(pid, **kw):
        seen.update(kw)
        return {"snapshot": {}}

    monkeypatch.setattr(proxy, "reevaluate", reeval)
    asyncio.run(sweep_module.sweep([("sw-x", YESTERDAY)]))
    assert seen == {"reason": "evidence expired", "actor": "system:expiry_sweep"}


def test_the_exit_code_says_what_went_wrong(sweep_module, monkeypatch):
    """launchd shows only the exit status; 0 means fine, 2 an unreadable database, 3 a failed re-evaluation."""
    monkeypatch.setattr(sys, "argv", ["expire_evidence.py", "--apply"])
    monkeypatch.setattr(sweep_module, "stale_projects", lambda today: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(SystemExit) as db_down:
        sweep_module.main()
    assert db_down.value.code == 2

    async def failing(projects):
        return ["sw-b"]

    monkeypatch.setattr(sweep_module, "stale_projects", lambda today: [("sw-b", YESTERDAY)])
    monkeypatch.setattr(sweep_module, "sweep", failing)
    with pytest.raises(SystemExit) as engine_down:
        sweep_module.main()
    assert engine_down.value.code == 3

    async def fine(projects):
        return []

    monkeypatch.setattr(sweep_module, "sweep", fine)
    sweep_module.main()          # returns normally: exit status 0
