#!/usr/bin/env python
"""
Auth slice — copy identity tables from SQLite to PostgreSQL, then prove parity.

    DATABASE_URL=postgresql://... python scripts/migrate_auth_slice.py [--execute]

Default is a DRY RUN: it reads both stores, reports what would move, and
verifies nothing. Pass --execute to write.

Design notes
------------
· IDEMPOTENT. Rows are upserted on the primary key, so re-running after a
  partial failure converges instead of duplicating. Safe to run twice.
· READ-ONLY on SQLite. The source is never modified — SQLite remains the live
  system of record until the application is flipped, so a botched copy costs
  nothing but a re-run.
· PARITY IS VERIFIED, NOT ASSUMED. After copying, every row is compared
  column-by-column and any mismatch is reported. A copy that "looks fine"
  because it didn't crash is not evidence.
· Column intersection only. If SQLite has a column Postgres lacks (or vice
  versa) the script says so loudly rather than silently dropping data.
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

# Order matters only for readability — there are no FKs between these tables.
SLICE_TABLES = {
    "auth_users": "user_id",
    "auth_user_project_roles": None,        # composite PK
    "auth_login_history": "id",
    "refresh_tokens": "token_id",
}
COMPOSITE_PK = {"auth_user_project_roles": ("user_id", "project_id", "actor_type")}


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def pg_columns(pg, table: str) -> list[str]:
    rows = pg.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
    ), {"t": table}).fetchall()
    return [r[0] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    pg_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    print(f"SQLite source : {settings.SQLITE_DB_PATH}")
    print(f"Postgres target: {pg_url.split('@')[-1]}")
    print(f"Mode           : {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    lite = sqlite3.connect(settings.SQLITE_DB_PATH)
    lite.row_factory = sqlite3.Row
    engine = create_engine(pg_url)

    problems: list[str] = []
    with engine.begin() as pg:
        for table in SLICE_TABLES:
            src_cols = sqlite_columns(lite, table)
            dst_cols = pg_columns(pg, table)
            if not src_cols:
                problems.append(f"{table}: missing in SQLite")
                continue
            if not dst_cols:
                problems.append(f"{table}: missing in Postgres — run the migration first")
                continue

            only_src = [c for c in src_cols if c not in dst_cols]
            only_dst = [c for c in dst_cols if c not in src_cols]
            cols = [c for c in src_cols if c in dst_cols]
            rows = lite.execute(f"SELECT * FROM {table}").fetchall()

            print(f"── {table}")
            print(f"   sqlite rows : {len(rows)}")
            print(f"   columns     : {len(cols)} copied"
                  + (f", SQLITE-ONLY {only_src} (WOULD BE LOST)" if only_src else "")
                  + (f", pg-only {only_dst} (left at default)" if only_dst else ""))
            if only_src:
                problems.append(f"{table}: columns present in SQLite but not Postgres: {only_src}")

            if not args.execute:
                continue

            pk = COMPOSITE_PK.get(table) or (SLICE_TABLES[table],)
            collist = ", ".join(f'"{c}"' for c in cols)
            params = ", ".join(f":{c}" for c in cols)
            updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in pk)
            conflict = ", ".join(f'"{c}"' for c in pk)
            stmt = text(
                f'INSERT INTO {table} ({collist}) VALUES ({params}) '
                f'ON CONFLICT ({conflict}) DO UPDATE SET {updates}'
                if updates else
                f'INSERT INTO {table} ({collist}) VALUES ({params}) ON CONFLICT DO NOTHING'
            )
            for r in rows:
                pg.execute(stmt, {c: r[c] for c in cols})
            print(f"   copied      : {len(rows)}")

    # ── Parity ──────────────────────────────────────────────────────────────
    if args.execute:
        print("\n══ PARITY ══")
        with engine.connect() as pg:
            for table in SLICE_TABLES:
                src_cols = sqlite_columns(lite, table)
                cols = [c for c in src_cols if c in pg_columns(pg, table)]
                if not cols:
                    continue
                src = lite.execute(f"SELECT * FROM {table}").fetchall()
                dst = pg.execute(text(f"SELECT * FROM {table}")).mappings().all()
                pk = COMPOSITE_PK.get(table) or (SLICE_TABLES[table],)

                def key(row):
                    return tuple(str(row[c]) for c in pk)

                dmap = {key(d): d for d in dst}
                mismatches = 0
                for s in src:
                    d = dmap.get(key(s))
                    if d is None:
                        mismatches += 1
                        problems.append(f"{table}: row {key(s)} missing in Postgres")
                        continue
                    for c in cols:
                        sv, dv = s[c], d[c]
                        # SQLite has no bool; Postgres INTEGER round-trips as int.
                        if sv is None and dv is None:
                            continue
                        if str(sv) != str(dv):
                            mismatches += 1
                            problems.append(
                                f"{table}.{c} differs for {key(s)}: sqlite={sv!r} pg={dv!r}")
                status = "OK" if mismatches == 0 else f"{mismatches} MISMATCH(ES)"
                print(f"  {table:26} sqlite={len(src):4}  pg={len(dst):4}  {status}")

    lite.close()

    if problems:
        print("\n⚠  PROBLEMS")
        for p in problems[:25]:
            print(f"   - {p}")
        if len(problems) > 25:
            print(f"   … and {len(problems)-25} more")
        return 1
    print("\nNo problems." + ("" if args.execute else " Re-run with --execute to write."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
