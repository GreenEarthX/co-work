#!/usr/bin/env python
"""
Directory slice — copy the staff directory from SQLite to PostgreSQL (047).

    ALEMBIC_DATABASE_URL=postgresql://... python scripts/migrate_directory_slice.py [--execute]

Dry run by default. READ-ONLY on SQLite. Idempotent (upsert on the primary key).

WHY THIS RUNS AS THE OWNER, AND AS PLATFORM_ADMIN
-------------------------------------------------
047 puts the five tables under FORCE ROW LEVEL SECURITY, which binds the table
owner too. A copy with no tenant context would match no policy and write
nothing — silently, since an RLS-filtered write is not an error. So the copy
sets PLATFORM_ADMIN explicitly and says so, rather than discovering at parity
time that it moved zero rows.

THESE ROWS ARE PERSONAL DATA — 3 members with email and phone. The output
prints counts and ids, never a name, an email or a phone number.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402

SLICE_TABLES: dict[str, tuple[str, ...]] = {
    "directory_teams": ("team_id",),
    "directory_roles": ("role_id",),
    "directory_members": ("member_id",),
    "directory_gates": ("gate_id",),
    "directory_gate_status": ("member_id", "gate_id"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    pg_url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not pg_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("ALEMBIC_DATABASE_URL must be an explicit PostgreSQL URL")

    print(f"SQLite  : {settings.SQLITE_DB_PATH}")
    print(f"Postgres: {pg_url.split('@')[-1]}")
    print(f"Mode    : {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    lite = sqlite3.connect(f"file:{settings.SQLITE_DB_PATH}?mode=ro", uri=True)
    lite.row_factory = sqlite3.Row
    engine = create_engine(pg_url)
    problems: list[str] = []

    with engine.begin() as pg:
        pg.execute(text("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'"))
        for table, pk in SLICE_TABLES.items():
            rows = lite.execute(f"SELECT * FROM {table}").fetchall()
            src_cols = [c[1] for c in lite.execute(f"PRAGMA table_info({table})")]
            dst_cols = [r[0] for r in pg.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"), {"t": table})]
            lost = [c for c in src_cols if c not in dst_cols]
            if lost:
                problems.append(f"{table}: columns lost: {lost}")
            shared = [c for c in src_cols if c in dst_cols]
            print(f"── {table}: {len(rows)} row(s), {len(shared)} shared column(s)"
                  f"{'  ⚠ ' + str(lost) if lost else ''}")

            if not args.execute or not rows:
                continue
            cols = ", ".join(shared)
            binds = ", ".join(f":{c}" for c in shared)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in shared if c not in pk)
            action = f"DO UPDATE SET {updates}" if updates else "DO NOTHING"
            stmt = text(f"INSERT INTO {table} ({cols}) VALUES ({binds}) "
                        f"ON CONFLICT ({', '.join(pk)}) {action}")
            for r in rows:
                pg.execute(stmt, {c: r[c] for c in shared})

    print("\n══ PARITY ══")
    with engine.connect() as pg:
        pg.execute(text("SET app.current_company_id = 'PLATFORM_ADMIN'"))
        for table, pk in SLICE_TABLES.items():
            n_lite = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            n_pg = pg.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            ok = n_lite == n_pg
            print(f"  {table:24} sqlite={n_lite:4d} pg={n_pg:4d} {'OK' if ok else 'MISMATCH'}")
            if not ok and args.execute:
                problems.append(f"{table}: {n_lite} in SQLite, {n_pg} in PostgreSQL")
            if not ok:
                continue
            # Column-by-column, keyed on the primary key. A count that matches
            # is not evidence that the values did.
            src_cols = [c[1] for c in lite.execute(f"PRAGMA table_info({table})")]
            for r in lite.execute(f"SELECT * FROM {table}").fetchall():
                where = " AND ".join(f"{k} = :{k}" for k in pk)
                d = pg.execute(text(f"SELECT * FROM {table} WHERE {where}"),
                               {k: r[k] for k in pk}).mappings().first()
                if not d:
                    problems.append(f"{table}: {[r[k] for k in pk]} missing after copy")
                    continue
                bad = [c for c in src_cols
                       if c in d and str(r[c]) != str(d[c])]
                if bad:
                    problems.append(f"{table}: {[r[k] for k in pk]} differs in {bad}")

    lite.close()
    if problems:
        print("\n⚠  PROBLEMS")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("\nNo problems." if args.execute else "\nDry run. Re-run with --execute to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
