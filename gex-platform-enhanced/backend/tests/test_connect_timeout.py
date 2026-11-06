"""
A PostgreSQL connection that is never answered must fail fast (2026-11-05). With Docker Desktop paused,
port 55432 still accepts the TCP connection and nothing replies: the 07:30 expiry sweep hung for 2h12m and
the suite froze at 10%. app/core/config.py now defaults PGCONNECT_TIMEOUT to 10 s, and the sweep has a
whole-run watchdog for a socket that answers and then stops. Driven against a local socket that accepts
and says nothing, so no database and no Docker are involved.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "expire_evidence.py"


@pytest.fixture()
def silent_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                held.append(srv.accept()[0])
            except OSError:
                pass

    t = threading.Thread(target=accept, daemon=True)
    t.start()
    yield srv.getsockname()[1]
    stop.set()
    t.join(2)
    for c in held:
        c.close()
    srv.close()


def _run_sweep(port: int, **env_extra) -> tuple[int, float, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PGCONNECT_TIMEOUT", "SWEEP_TIMEOUT_SECONDS", "DATABASE_URL", "ALEMBIC_DATABASE_URL")}
    env.update({"DATABASE_URL": f"postgresql://gex_app:x@127.0.0.1:{port}/gex_platform",
                "EVIDENCE_DB_BACKEND": "postgres", **env_extra})
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, str(SCRIPT)], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=90)
    return r.returncode, time.monotonic() - t0, r.stdout


def test_the_default_is_set_by_the_application_config():
    out = subprocess.run(
        [sys.executable, "-c", "import os; os.environ.pop('PGCONNECT_TIMEOUT', None); import app.core.config; "
         "print(os.environ['PGCONNECT_TIMEOUT'])"], cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert out.stdout.strip().splitlines()[-1] == "10"


def test_an_unanswered_database_makes_the_sweep_exit_2_not_hang(silent_server):
    """Negative-verified 2026-11-05: removing the setdefault in app/core/config.py makes this run into the
    sweep's own watchdog (exit 4) instead of exit 2."""
    code, seconds, out = _run_sweep(silent_server, SWEEP_TIMEOUT_SECONDS="45")
    assert code == 2 and "cannot read the evaluations" in out
    assert seconds < 40


def test_a_run_that_stalls_after_connecting_is_ended_by_the_watchdog(silent_server):
    code, seconds, out = _run_sweep(silent_server, PGCONNECT_TIMEOUT="120", SWEEP_TIMEOUT_SECONDS="3")
    assert code == 4 and "giving up" in out
    assert seconds < 30
