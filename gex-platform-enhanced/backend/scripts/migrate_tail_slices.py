#!/usr/bin/env python
"""
Evidence & bankability slice — copy SQLite -> PostgreSQL, then prove parity.

    DATABASE_URL=postgresql://... python scripts/migrate_capital_bridge_slice.py [--execute]

Dry run by default. Read-only on SQLite. Idempotent (upsert on the primary key).

WHAT TO WATCH FOR IN THE OUTPUT
-------------------------------
`bankability_evidence.project_id` has a column default of the literal string
'default', so rows written before a project was supplied are attributed to a
project that does not exist. Under the RLS added in 034 those rows match neither
`app_company_owns_project` nor `app_company_has_project_access`, so they become
visible ONLY to PLATFORM_ADMIN.

They are copied anyway — losing evidence is worse than losing visibility, and
inventing a project to attribute them to would be a fabrication. The script
reports the count so the consequence is a decision, not a surprise.
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

# table -> primary key column(s). Sequences are reset for the integer ones.
SLICE_TABLES: dict[str, tuple[str, ...]] = {
    "carbon_attribution_event_log": ('event_id',),
    "dfi_criteria_events": ('event_id',),
    "drawdown_schedule_events": ('event_id',),
    "mass_balance_allocations": ('allocation_id',),
    "settlement_event_log": ('event_id',),
    "sovereign_instrument_events": ('event_id',),
    "spend_wave_events": ('event_id',),
    "additionality_assessments": ('assessment_id',),
    "adjacency_cache": ('project_id',),
    "admin_log": ('id',),
    "adversarial_findings": ('id',),
    "adversarial_handoffs": ('id',),
    "adversarial_reviews": ('id',),
    "approval_decisions": ('id',),
    "availability_reports": ('id',),
    "carbon_attribution_events": ('attribution_id',),
    "commitment_records": ('commitment_id',),
    "corpus_status_transitions": ('transition_id',),
    "corpus_taxonomy_map": ('source', 'field', 'raw_label'),
    "corpus_versions": ('version_id',),
    "deliveries": ('id',),
    "dfi_criteria": ('criterion_id',),
    "dfi_impact_kpis": ('kpi_id',),
    "drawdown_schedules": ('drawdown_id',),
    "external_projects": ('row_id',),
    "gateway_registry": ('id',),
    "mass_balance_lots": ('lot_id',),
    "matrix_events": ('id',),
    "matrix_members": ('room_id', 'user_id'),
    "matrix_rooms": ('id',),
    "model_base_case": ('claim_id',),
    "offtake_contracts": ('id',),
    "pathway_claims": ('claim_id',),
    "plant_data": ('id',),
    "pre_cod_snapshots": ('snapshot_id',),
    "production_readings": ('id',),
    "quality_certificates": ('id',),
    "risk_flag_events": ('id',),
    "risk_flag_status": ('project_id', 'flag_id'),
    "settlement_events": ('settlement_id',),
    "sovereign_instruments": ('instrument_id',),
    "spend_waves": ('spend_wave_id',),
}
SEQUENCE_TABLES = ('admin_log', 'matrix_events', 'risk_flag_events')


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def pg_columns(pg, table: str) -> list[str]:
    return [r[0] for r in pg.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
    ), {"t": table}).fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    pg_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    print(f"SQLite  : {settings.SQLITE_DB_PATH}")
    print(f"Postgres: {pg_url.split('@')[-1]}")
    print(f"Mode    : {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    lite = sqlite3.connect(settings.SQLITE_DB_PATH)
    lite.row_factory = sqlite3.Row
    engine = create_engine(pg_url)
    problems: list[str] = []
    notes: list[str] = []

    with engine.begin() as pg:
        pg.execute(text("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'"))
        known = {r[0] for r in pg.execute(text("SELECT project_id FROM projects"))}

        for table, pk in SLICE_TABLES.items():
            src_cols = sqlite_columns(lite, table)
            dst_cols = pg_columns(pg, table)
            if not src_cols:
                problems.append(f"{table}: missing in SQLite")
                continue
            if not dst_cols:
                problems.append(f"{table}: missing in Postgres — run migration 034")
                continue
            only_src = [c for c in src_cols if c not in dst_cols]
            cols = [c for c in src_cols if c in dst_cols]
            rows = lite.execute(f"SELECT * FROM {table}").fetchall()

            unattributed = 0
            if "project_id" in cols:
                unattributed = sum(1 for r in rows if r["project_id"] not in known)

            print(f"── {table}")
            print(f"   rows        : {len(rows)}")
            print(f"   columns     : {len(cols)} copied"
                  + (f"  SQLITE-ONLY {only_src} (WOULD BE LOST)" if only_src else ""))
            if unattributed:
                print(f"   ⚠ {unattributed} row(s) reference a project not in Postgres "
                      f"→ PLATFORM_ADMIN-only under RLS")
                notes.append(f"{table}: {unattributed} unattributed row(s)")
            if only_src:
                problems.append(f"{table}: columns lost: {only_src}")

            if not args.execute:
                continue

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

        if args.execute:
            # Record EXACTLY which keys this copy wrote. Both stores stay live
            # during a strangler migration, so verification needs to know what
            # the copy covered — inferring it from max(timestamp) is unsafe when
            # timestamps have second precision and rows share a value.
            import datetime as _dt
            import json as _json

            for table, pk in SLICE_TABLES.items():
                keys = [str(r[pk[0]]) for r in lite.execute(f"SELECT * FROM {table}")]
                pg.execute(text("""
                    INSERT INTO migration_watermarks
                        (table_name, copied_at, row_count, copied_keys)
                    VALUES (:t, :ts, :n, :k)
                    ON CONFLICT (table_name) DO UPDATE SET
                        copied_at = EXCLUDED.copied_at,
                        row_count = EXCLUDED.row_count,
                        copied_keys = EXCLUDED.copied_keys
                """), {"t": table,
                       "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                       "n": len(keys), "k": _json.dumps(keys)})
            print(f"\n   watermarks recorded for {len(SLICE_TABLES)} table(s)")

            # Identity sequences must start past the copied ids, or the next
            # INSERT collides with a migrated row.
            for t in SEQUENCE_TABLES:
                pg.execute(text(
                    f"SELECT setval('{t}_id_seq', "
                    f"GREATEST((SELECT COALESCE(MAX(id), 0) FROM {t}), 1))"))
            print("\n   sequences reset past copied maxima")

    # ── Parity ──────────────────────────────────────────────────────────────
    if args.execute:
        print("\n══ PARITY ══")
        with engine.connect() as pg:
            pg.execute(text("SET app.current_company_id = 'PLATFORM_ADMIN'"))
            for table, pk in SLICE_TABLES.items():
                src_cols = sqlite_columns(lite, table)
                cols = [c for c in src_cols if c in pg_columns(pg, table)]
                if not cols:
                    continue
                src = lite.execute(f"SELECT * FROM {table}").fetchall()
                dst = pg.execute(text(f"SELECT * FROM {table}")).mappings().all()

                def key(row):
                    return tuple(str(row[c]) for c in pk)

                dmap = {key(d): d for d in dst}
                bad = 0
                for s in src:
                    d = dmap.get(key(s))
                    if d is None:
                        bad += 1
                        problems.append(f"{table}: row {key(s)} missing after copy")
                        continue
                    for c in cols:
                        if str(s[c]) != str(d[c]):
                            bad += 1
                            problems.append(
                                f"{table}.{c} differs for {key(s)}: "
                                f"sqlite={s[c]!r} pg={d[c]!r}")
                print(f"  {table:24} sqlite={len(src):4} pg={len(dst):4} "
                      f"{'OK' if bad == 0 else f'{bad} MISMATCH(ES)'}")

    lite.close()

    if notes:
        print("\nℹ  NOTES (not failures)")
        for n in notes:
            print(f"   - {n}")
    if problems:
        print("\n⚠  PROBLEMS")
        for p in problems[:25]:
            print(f"   - {p}")
        return 1
    print("\nNo problems." + ("" if args.execute else " Re-run with --execute to write."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
