"""
The gate clock (rules 4.8.0, migration 080): a gate's FIRST satisfaction is recorded once and never
rewritten; a gate that is not satisfied, or only waived, is not recorded; a measurement can never fail an
evaluation. Isolated SQLite store.
"""
from __future__ import annotations

import asyncio

from app.api.v1 import routes_bankability_proxy as proxy
from app.core import gate_clock


def _gates(*pairs):
    return [{"gate_id": g, "gate_name": g, "determination": d} for g, d in pairs]


def _clock(pid):
    conn = proxy._get_db()
    proxy._ensure_tables(conn)
    try:
        return {r["gate_id"]: r for r in gate_clock.read(conn, pid)}
    finally:
        conn.close()


def _record(pid, gates, rules="4.8.0", state="BUILDABLE"):
    conn = proxy._get_db()
    proxy._ensure_tables(conn)
    try:
        n = gate_clock.record(conn, pid, gates, rules, state)
        conn.commit()
        return n
    finally:
        conn.close()


def test_only_a_satisfied_gate_is_recorded(isolated_store):
    n = _record("gc-1", _gates(("G0_SITE_RIGHTS", "SATISFIED"), ("G1_GRID_UTILITIES_REALITY", "INCOMPLETE"),
                               ("G6_IE_SIGNOFF", "WAIVED"), ("G4_OFFTAKE_BANKABLE", "BLOCKED")))
    assert n == 1 and set(_clock("gc-1")) == {"G0_SITE_RIGHTS"}


def test_the_first_date_is_kept_when_the_gate_is_satisfied_again(isolated_store):
    """Negative-verified 2026-10-31: replacing DO NOTHING with an update moves the date."""
    _record("gc-2", _gates(("G0_SITE_RIGHTS", "SATISFIED")), state="TECHNICALLY_PLAUSIBLE")
    first = _clock("gc-2")["G0_SITE_RIGHTS"]
    conn = proxy._get_db()
    conn.execute("UPDATE project_gate_clock SET first_satisfied_at = '2026-01-01 00:00:00' WHERE project_id = 'gc-2'")
    conn.commit()
    conn.close()
    again = _record("gc-2", _gates(("G0_SITE_RIGHTS", "SATISFIED")), rules="4.9.0", state="OPERATIONAL")
    kept = _clock("gc-2")["G0_SITE_RIGHTS"]
    assert again == 0
    assert kept["first_satisfied_at"].startswith("2026-01-01") and kept["rules_version"] == first["rules_version"]
    assert kept["state_at_time"] == "TECHNICALLY_PLAUSIBLE"


def test_a_gate_lost_and_regained_keeps_its_first_date(isolated_store):
    _record("gc-3", _gates(("G4_OFFTAKE_BANKABLE", "SATISFIED")))
    _record("gc-3", _gates(("G4_OFFTAKE_BANKABLE", "BLOCKED")))
    _record("gc-3", _gates(("G4_OFFTAKE_BANKABLE", "SATISFIED")))
    assert len(_clock("gc-3")) == 1


def test_a_failing_clock_never_fails_the_evaluation(isolated_store, monkeypatch):
    """reevaluate swallows a recorder failure and still returns the snapshot."""
    async def engine(path, method="GET", json_data=None):
        return {"current_state": "SPECULATIVE", "rules_version": "t",
                "gate_evaluations": _gates(("G0_SITE_RIGHTS", "SATISFIED"))}

    def boom(*a, **k):
        raise RuntimeError("clock down")

    monkeypatch.setattr(proxy, "_call_engine", engine)
    monkeypatch.setattr(gate_clock, "record", boom)
    result = asyncio.run(proxy.reevaluate("gc-4", reason="test", actor="t", evidence=[]))
    assert result["snapshot"]["current_state"] == "SPECULATIVE"


def test_reevaluation_starts_the_clock(isolated_store, monkeypatch):
    async def engine(path, method="GET", json_data=None):
        return {"current_state": "TECHNICALLY_PLAUSIBLE", "rules_version": "t", "gate_evaluations": _gates(("G0_SITE_RIGHTS", "SATISFIED"))}

    monkeypatch.setattr(proxy, "_call_engine", engine)
    asyncio.run(proxy.reevaluate("gc-5", reason="test", actor="t", evidence=[]))
    assert _clock("gc-5")["G0_SITE_RIGHTS"]["state_at_time"] == "TECHNICALLY_PLAUSIBLE"
