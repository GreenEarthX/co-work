#!/usr/bin/env python3
"""One-time copy of the engine's SQLite run log into PostgreSQL (JML, 2026-11-04).

Reads engine_model_runs.db READ-ONLY (model_runs, param_change_events) and inserts
into engine_model_runs / engine_param_change_events (platform migration 082) as the
engine's own role, gex_engine, via GEX_ENGINE_DATABASE_URL.

Dry run by default; --execute writes. Idempotent: a run already present (same
run_id) is skipped; a parameter change already present (same molecule,
new_calibration_id and timestamp) is skipped. Afterwards it re-reads both stores
and refuses to call the copy complete unless every SQLite row is in PostgreSQL.

    ../micro_service/bin/python scripts/migrate_run_log_to_postgres.py [--execute] [--sqlite PATH]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

import psycopg2

RUN_COLS = ("run_id", "endpoint", "molecule", "model_version", "calibration_id", "calibration_status",
            "input_hash", "n_violations", "violations_json", "computed_at")
EVENT_COLS = ("molecule", "old_calibration_id", "new_calibration_id", "changed_fields_json",
              "n_observations", "source", "at")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--sqlite", default="engine_model_runs.db")
    args = ap.parse_args()
    dsn = os.getenv("GEX_ENGINE_DATABASE_URL")
    if not dsn:
        sys.exit("GEX_ENGINE_DATABASE_URL is not set (see gex_pf_engine/backend/.env)")

    src = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    runs = src.execute(f"SELECT {', '.join(RUN_COLS)} FROM model_runs").fetchall()
    events = src.execute(f"SELECT {', '.join(EVENT_COLS)} FROM param_change_events ORDER BY id").fetchall()
    src.close()

    dst = psycopg2.connect(dsn)
    try:
        with dst, dst.cursor() as cur:
            cur.execute("SELECT run_id FROM engine_model_runs")
            have_runs = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT molecule, new_calibration_id, at FROM engine_param_change_events")
            have_events = {tuple(r) for r in cur.fetchall()}
            new_runs = [r for r in runs if r[0] not in have_runs]
            new_events = [e for e in events if (e[0], e[2], e[6]) not in have_events]
            print(f"SQLite: {len(runs)} runs, {len(events)} parameter changes")
            print(f"to copy: {len(new_runs)} runs, {len(new_events)} parameter changes")
            if not args.execute:
                print("dry run: nothing written (pass --execute)")
                dst.rollback()
                return 0
            for r in new_runs:
                cur.execute(f"INSERT INTO engine_model_runs ({', '.join(RUN_COLS)}) "
                            f"VALUES ({', '.join(['%s'] * len(RUN_COLS))})", r)
            for e in new_events:
                cur.execute(f"INSERT INTO engine_param_change_events ({', '.join(EVENT_COLS)}) "
                            f"VALUES ({', '.join(['%s'] * len(EVENT_COLS))})", e)
        with dst.cursor() as cur:       # verify, after the commit
            cur.execute("SELECT run_id FROM engine_model_runs")
            in_pg = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT molecule, new_calibration_id, at FROM engine_param_change_events")
            ev_pg = {tuple(r) for r in cur.fetchall()}
        missing_runs = [r[0] for r in runs if r[0] not in in_pg]
        missing_events = [e for e in events if (e[0], e[2], e[6]) not in ev_pg]
        if missing_runs or missing_events:
            print(f"INCOMPLETE: {len(missing_runs)} runs and {len(missing_events)} changes not in PostgreSQL")
            return 1
        print(f"complete: all {len(runs)} runs and {len(events)} parameter changes are in PostgreSQL")
        return 0
    finally:
        dst.close()


if __name__ == "__main__":
    raise SystemExit(main())
