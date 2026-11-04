"""
files/start_stack.sh — the idempotent "make sure PostgreSQL is up" script (Docker Desktop restarts leave
the container stopped). Driven with a fake `docker` so no container is touched. The property that matters
most is the negative one: a MISSING container is never recreated and never started — it exits 12 and says so.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "start_stack.sh"

FAKE_DOCKER = """#!/bin/bash
# fake docker: state comes from env; every call is logged
echo "$*" >> "$FAKE_CALLS"
case "$1" in
  info) [ "$FAKE_DAEMON" = "up" ] ;;
  inspect)
    name="${@: -1}"
    if [ "$name" = "$FAKE_PG" ]; then
        [ -f "$FAKE_STARTED" ] && { echo true; exit 0; }
        case "$FAKE_PG_STATE" in true) echo true;; false) echo false;; *) exit 1;; esac
    elif [ "$name" = "$FAKE_FWD" ]; then
        [ -f "$FAKE_FWD_STARTED" ] && { echo true; exit 0; }
        case "$FAKE_FWD_STATE" in true) echo true;; false) echo false;; *) exit 1;; esac
    else exit 1; fi ;;
  start) [ "$2" = "$FAKE_PG" ] && touch "$FAKE_STARTED"; [ "$2" = "$FAKE_FWD" ] && touch "$FAKE_FWD_STARTED"; exit 0 ;;
  exec) [ "$FAKE_QUERY" = "ok" ] ;;
  *) exit 0 ;;
esac
"""


def run(tmp_path, **env):
    docker = tmp_path / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    calls = tmp_path / "calls"
    calls.write_text("")
    e = {"PATH": "/usr/bin:/bin", "GEX_DOCKER": str(docker), "GEX_NO_OPEN": "1",
         "GEX_STACK_LOG": str(tmp_path / "stack.log"), "GEX_DAEMON_WAIT": "3", "GEX_QUERY_WAIT": "2",
         "FAKE_CALLS": str(calls), "FAKE_STARTED": str(tmp_path / "pg_started"),
         "FAKE_FWD_STARTED": str(tmp_path / "fwd_started"), "FAKE_PG": "pg", "FAKE_FWD": "fwd",
         "GEX_PG_CONTAINER": "pg", "GEX_PG_FORWARDER": "fwd",
         "FAKE_DAEMON": "up", "FAKE_PG_STATE": "true", "FAKE_FWD_STATE": "true", "FAKE_QUERY": "ok", **env}
    r = subprocess.run(["/bin/bash", str(SCRIPT)], env=e, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, [c for c in calls.read_text().splitlines() if c.startswith("start")]


def test_everything_up_changes_nothing(tmp_path):
    code, out, starts = run(tmp_path)
    assert code == 0 and starts == [] and out == ""


def test_a_stopped_container_is_started_and_must_then_answer(tmp_path):
    code, out, starts = run(tmp_path, FAKE_PG_STATE="false")
    assert code == 0 and starts == ["start pg"] and "stopped — starting it" in out


def test_a_missing_container_is_never_started_or_recreated(tmp_path):
    """Negative-verified 2026-10-31: making the `*)` branch start it fails this. If the container is gone
    the database volume may be gone too, and `docker start` cannot fix that."""
    code, out, starts = run(tmp_path, FAKE_PG_STATE="missing")
    assert code == 12 and starts == [] and "DOES NOT EXIST" in out and "Nothing was created" in out


def test_a_running_container_that_refuses_queries_exits_14(tmp_path):
    code, out, starts = run(tmp_path, FAKE_QUERY="no")
    assert code == 14 and "does not answer queries" in out


def test_a_stopped_forwarder_is_started(tmp_path):
    code, out, starts = run(tmp_path, FAKE_FWD_STATE="false")
    assert code == 0 and starts == ["start fwd"]


def test_docker_that_never_comes_up_exits_11_and_a_missing_cli_exits_10(tmp_path):
    assert run(tmp_path, FAKE_DAEMON="down")[0] == 11
    assert run(tmp_path, GEX_DOCKER="/nonexistent")[0] == 10
