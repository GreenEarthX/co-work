#!/usr/bin/env python
"""Apply PostgreSQL schema and copy every migrated SQLite slice with parity checks."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATORS = (
    "migrate_auth_slice.py",
    "migrate_evidence_slice.py",
    "migrate_capital_bridge_slice.py",
    "migrate_marketplace_slice.py",
    "migrate_entitlements_slice.py",
    "migrate_fuel_reference_slice.py",
    "migrate_governance_slice.py",
    "migrate_tail_slices.py",
)
REQUIRED_TABLES = (
    "auth_users",
    "bankability_evidence",
    "project_control",
    "capacities",
    "finance_entitlements",
    "platform_events",
    "fuel_catalog",
    "approval_policies",
)
SWITCHES = (
    "AUTH_DB_BACKEND",
    "EVIDENCE_DB_BACKEND",
    "CAPITAL_DB_BACKEND",
    "MARKET_DB_BACKEND",
    "ENTITLEMENT_DB_BACKEND",
    "EVENTSTORE_DB_BACKEND",
    "FUELREF_DB_BACKEND",
    "GOVERNANCE_DB_BACKEND",
)


def require_url(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit(f"{name} must be an explicit PostgreSQL URL")
    return value


def check_connection(url: str, label: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise SystemExit(f"{label} PostgreSQL connection failed: {exc}") from exc
    finally:
        engine.dispose()


def run(command: list[str], env: dict[str, str]) -> None:
    print(f"\n==> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=BACKEND_ROOT, env=env, check=True)


def verify_runtime_schema(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(:tables)"
            ), {"tables": list(REQUIRED_TABLES)}).scalars()
            found = set(rows)
    finally:
        engine.dispose()
    missing = sorted(set(REQUIRED_TABLES) - found)
    if missing:
        raise SystemExit(f"Cutover verification failed; missing tables: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate all SQLite slices to PostgreSQL and prove row parity."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="apply migrations and copy data; without this flag only connectivity is checked",
    )
    args = parser.parse_args()

    owner_url = require_url("ALEMBIC_DATABASE_URL")
    runtime_url = require_url("DATABASE_URL")
    sqlite_path = Path(os.environ.get("SQLITE_DB_PATH", BACKEND_ROOT / "gex_platform.db"))
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite source does not exist: {sqlite_path}")

    check_connection(owner_url, "migration owner")
    check_connection(runtime_url, "runtime")
    print(f"Connections OK; SQLite source is {sqlite_path}")
    if not args.execute:
        print("Preflight only. Re-run with --execute during the write freeze.")
        return 0

    owner_env = os.environ.copy()
    owner_env["ALEMBIC_DATABASE_URL"] = owner_url
    owner_env["DATABASE_URL"] = owner_url
    owner_env["SQLITE_DB_PATH"] = str(sqlite_path)

    # auth_slice@head, never "heads": the legacy 001->011 branch re-creates
    # tables (matrix_rooms, approval_policies, ...) that 042/044 already own.
    run([sys.executable, "-m", "alembic", "upgrade", "auth_slice@head"], owner_env)
    for migrator in MIGRATORS:
        run([sys.executable, f"scripts/{migrator}", "--execute"], owner_env)

    verify_runtime_schema(runtime_url)
    print("\nCutover checks passed. Deploy with:")
    for switch in SWITCHES:
        print(f"{switch}=postgres")
    print("Keep the SQLite file read-only until the rollback window closes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
