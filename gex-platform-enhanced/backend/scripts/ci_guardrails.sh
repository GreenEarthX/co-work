#!/usr/bin/env bash
# Architecture guardrails (ADR 2026-07-06) — run in CI on every change.
# Enforces: single absolute DB path, no second database, authentication by
# default, explicit public-route registry, no demo mode in production, and
# the raw-SQLite ratchet for the Postgres migration.
#
# Usage: ./scripts/ci_guardrails.sh   (from backend/, any venv with dev deps)
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3

exec "$PYTHON" -m pytest tests/test_architecture_guardrails.py -q "$@"
