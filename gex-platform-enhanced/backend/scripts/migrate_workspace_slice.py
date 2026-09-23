#!/usr/bin/env python
"""
Workspace slice — canvas, plants and equations from SQLite to PostgreSQL (050).

    ALEMBIC_DATABASE_URL=postgresql://... python scripts/migrate_workspace_slice.py [--execute]

Dry run by default. READ-ONLY on SQLite. Idempotent (upsert on the primary key).

WHY THIS WALKS OWNER BY OWNER
-----------------------------
050's policies compare `owner_user_id` to `app.current_user_id` and have NO
admin clause, and the tables are FORCE ROW LEVEL SECURITY, so even the table
owner (`gex_user`) cannot write a row it is not currently acting as. There is
deliberately no "all owners" context to escalate to.

So the copy sets `app.current_user_id` to one owner, copies that owner's rows,
and moves on. That is slower and it is the point: if a future change made a
bulk path possible, it would have had to weaken the policy first.

EVERY OWNER MUST BE A REAL ACCOUNT. `owner_user_id` holds an
`auth_users.user_id`; measured 2026-09-22 all four distinct owners are real
accounts. An owner with no account stops the run before anything is written —
copying a row nobody can ever read again is not a migration, it is a leak with
extra steps.
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
    "canvas_blobs": ("owner_user_id", "kind", "slug", "version_id"),
    "user_plants": ("owner_user_id", "slug"),
    "equipment_equations": ("row_id",),
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

    owners = sorted({r[0] for table in SLICE_TABLES
                     for r in lite.execute(f"SELECT DISTINCT owner_user_id FROM {table}")})
    accounts = {r[0] for r in lite.execute("SELECT user_id FROM auth_users")}
    orphans = [o for o in owners if o not in accounts]
    print(f"── {len(owners)} owner(s): {', '.join(owners)}")
    if orphans:
        raise SystemExit(
            f"\n⚠  {len(orphans)} owner(s) have no auth_users account: {orphans}\n"
            "   Under 050 nobody could ever read those rows again. Resolve the\n"
            "   ownership first — do not copy them to a user id that does not exist.")

    for table, pk in SLICE_TABLES.items():
        n = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        src_cols = [c[1] for c in lite.execute(f"PRAGMA table_info({table})")]
        print(f"── {table}: {n} row(s), {len(src_cols)} column(s)")

    if args.execute:
        with engine.begin() as pg:
            dst = {t: [r[0] for r in pg.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"), {"t": t})]
                for t in SLICE_TABLES}
            for owner in owners:
                # One owner at a time — this IS the policy, not a workaround.
                pg.execute(text("SET LOCAL app.current_user_id = :u"), {"u": owner})
                for table, pk in SLICE_TABLES.items():
                    src_cols = [c[1] for c in lite.execute(f"PRAGMA table_info({table})")]
                    lost = [c for c in src_cols if c not in dst[table]]
                    if lost:
                        problems.append(f"{table}: columns lost: {lost}")
                    shared = [c for c in src_cols if c in dst[table]]
                    rows = lite.execute(
                        f"SELECT * FROM {table} WHERE owner_user_id = ?", (owner,)).fetchall()
                    if not rows:
                        continue
                    cols = ", ".join(shared)
                    binds = ", ".join(f":{c}" for c in shared)
                    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in shared if c not in pk)
                    action = f"DO UPDATE SET {updates}" if updates else "DO NOTHING"
                    stmt = text(f"INSERT INTO {table} ({cols}) VALUES ({binds}) "
                                f"ON CONFLICT ({', '.join(pk)}) {action}")
                    for r in rows:
                        pg.execute(stmt, {c: r[c] for c in shared})
                    print(f"   {owner:32s} {table:22s} {len(rows):4d} row(s)")

    # ── Parity, as the RUNTIME role ─────────────────────────────────────────
    # NOT as the migration owner. `ALEMBIC_DATABASE_URL` is `gex_user`, which is
    # SUPERUSER, and PostgreSQL does not apply row-level security to a
    # superuser at all — not even FORCE ROW LEVEL SECURITY. Verifying there
    # reported every owner seeing all 500 rows and a no-owner connection seeing
    # them too, which looks exactly like a broken policy and was in fact a
    # broken measurement. Anything that checks what RLS does must connect as
    # the role the application actually uses.
    runtime_url = os.environ.get("DATABASE_URL", "")
    if not runtime_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("DATABASE_URL (the gex_app runtime role) is required to verify RLS")
    runtime = create_engine(runtime_url)

    print("\n══ PARITY ══ (as the runtime role — RLS applies)")
    with runtime.connect() as pg:
        for table in SLICE_TABLES:
            n_lite = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            # Counted per owner and summed: there is no context that sees all
            # of them at once, which is exactly what 050 promises.
            n_pg = 0
            for owner in owners:
                pg.execute(text("SET app.current_user_id = :u"), {"u": owner})
                n_pg += pg.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            ok = n_lite == n_pg
            print(f"  {table:22} sqlite={n_lite:4d} pg={n_pg:4d} {'OK' if ok else 'MISMATCH'}")
            if not ok and args.execute:
                problems.append(f"{table}: {n_lite} in SQLite, {n_pg} in PostgreSQL")

        # The policy itself, asserted on real data rather than assumed: a
        # connection with no owner bound must see nothing at all.
        pg.execute(text("SET app.current_user_id = '__no:user:context__'"))
        for table in SLICE_TABLES:
            leaked = pg.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            if leaked:
                problems.append(
                    f"{table}: {leaked} row(s) visible with NO owner bound — "
                    "the owner policy is not doing anything")

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
