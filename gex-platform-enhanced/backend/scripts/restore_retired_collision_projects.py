#!/usr/bin/env python3
"""
restore_retired_collision_projects.py — the last two projects lost on 2026-09-28.
=================================================================================
WHY THIS EXISTS
---------------
The 28 Sep 2026 16:14 dev-database reset (handoff §8 item 38) left PostgreSQL
empty. The rebuild restored 12 of the 14 projects: migration 020 seeds 7 and
`restore_registry_projects.py` returns 5 more from the frontend seed. Two were
in neither source:

    proj_north_sea_e_methanol_203b51     North Sea e-Methanol
    proj_wilhelmshaven_e_ammonia_f0dc91  Wilhelmshaven e-Ammonia

They are not hypothetical. After the 12 were restored, five tables still
referenced them — development_packages, development_package_events,
package_evidence, pre_cod_snapshots and bankability_snapshots — so leaving them
out leaves those rows pointing at projects that do not exist.

WHERE THE DATA COMES FROM — AND WHAT IS NOT INVENTED
----------------------------------------------------
`projects_retired_pg_collision_20260807` in `backend/gex_platform.db`. Migration
033 retired that table when the PostgreSQL shape won the `projects` collision,
so `migrate_projects_collision.py` can no longer read it. The ROWS were never
wrong — only the table's shape lost. Every value below is copied from them:

    project_name    <- name
    molecule        <- molecule
    jurisdiction    <- country              (also written to `country`)
    location        <- location
    capacity_mtpd   <- capacity_mtpd
    capex_eur       <- capex_eur
    created_by      <- created_by
    created_at      <- created_at

Three values are DERIVED, and each is stated rather than guessed:

  * `status` = the retired row's `phase`, which is 'development' for both. All
    12 already-restored projects also carry status='development', so this
    introduces no new value.
  * `owner_tenant_id` = 'hamburgone_com', normalised from `owner_company_name`
    'HamburgOne.com' — the same string->id normalisation
    `restore_registry_projects.py` performs. That tenant ALREADY EXISTS, so
    unlike the registry restore this script creates no organisation.
  * `updated_at` = `created_at`. No update was ever recorded for either row;
    writing "now" would assert an edit that did not happen.

`power_model` and `financing_model` have no column on the PostgreSQL `projects`
table. They are preserved under `metadata_json.restored_from` rather than
dropped, alongside the provenance of this restore.

USAGE
    python scripts/restore_retired_collision_projects.py            # dry run
    python scripts/restore_retired_collision_projects.py --execute  # write

Idempotent: ON CONFLICT (project_id) DO NOTHING — existing rows are never
updated. Requires ALEMBIC_DATABASE_URL (gex_user); `projects` is FORCE ROW LEVEL
SECURITY and this restore is a bootstrap, not a tenant action.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

RETIRED_TABLE = "projects_retired_pg_collision_20260807"
WANTED = ("proj_north_sea_e_methanol_203b51", "proj_wilhelmshaven_e_ammonia_f0dc91")
COMPANY_TO_TENANT = {"HamburgOne.com": "hamburgone_com"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    pg_url = os.environ.get("ALEMBIC_DATABASE_URL", "")
    if not pg_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("ALEMBIC_DATABASE_URL must be an explicit PostgreSQL URL")

    sqlite_path = Path(os.environ.get("SQLITE_DB_PATH", BACKEND_ROOT / "gex_platform.db"))
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite source does not exist: {sqlite_path}")

    lite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    lite.row_factory = sqlite3.Row
    marks = ",".join("?" * len(WANTED))
    rows = lite.execute(
        f"SELECT * FROM {RETIRED_TABLE} WHERE project_id IN ({marks})", WANTED
    ).fetchall()
    print(f"  source         : {sqlite_path}::{RETIRED_TABLE}")
    print(f"  rows found     : {len(rows)} of {len(WANTED)}")
    if len(rows) != len(WANTED):
        found = {r["project_id"] for r in rows}
        raise SystemExit(f"  missing from the retired table: {sorted(set(WANTED) - found)}")

    engine = create_engine(pg_url, pool_pre_ping=True)
    payloads = []
    with engine.begin() as pg:
        present = {
            r[0] for r in pg.execute(
                text("SELECT project_id FROM projects WHERE project_id = ANY(:ids)"),
                {"ids": list(WANTED)},
            )
        }
        tenants = {r[0] for r in pg.execute(text("SELECT company_id FROM tenants"))}

        for r in rows:
            tenant = COMPANY_TO_TENANT.get(r["owner_company_name"])
            if tenant is None:
                raise SystemExit(
                    f"  no tenant mapping for owner_company_name "
                    f"{r['owner_company_name']!r} — refusing to guess an owner"
                )
            if tenant not in tenants:
                raise SystemExit(
                    f"  tenant {tenant!r} does not exist. This script does not create "
                    f"organisations; run restore_registry_projects.py or add it deliberately."
                )
            flag = "  ALREADY PRESENT, will skip" if r["project_id"] in present else ""
            print(
                f"    {r['project_id']:36s} {r['molecule']:11s} owner={tenant:16s} "
                f"status={r['phase']}  capex={r['capex_eur']}{flag}"
            )
            payloads.append({
                "project_id": r["project_id"],
                "project_name": r["name"],
                "owner_tenant_id": tenant,
                "molecule": r["molecule"],
                "status": r["phase"],
                "jurisdiction": r["country"],
                "country": r["country"],
                "location": r["location"],
                "capacity_mtpd": r["capacity_mtpd"],
                "capex_eur": r["capex_eur"],
                "created_by": r["created_by"],
                "created_at": r["created_at"],
                "updated_at": r["created_at"],
                "metadata_json": json.dumps({
                    "restored_from": {
                        "table": RETIRED_TABLE,
                        "reason": "2026-09-28 dev database reset (handoff §8 item 38)",
                        "power_model": r["power_model"],
                        "financing_model": r["financing_model"],
                        "owner_company_name": r["owner_company_name"],
                    }
                }),
            })

        if not args.execute:
            print("\n  DRY RUN — nothing written. Re-run with --execute.")
            return 0

        written = 0
        for p in payloads:
            res = pg.execute(text("""
                INSERT INTO projects (
                    project_id, project_name, owner_tenant_id, molecule, status,
                    jurisdiction, country, location, capacity_mtpd, capex_eur,
                    created_by, created_at, updated_at, is_active, metadata_json
                ) VALUES (
                    :project_id, :project_name, :owner_tenant_id, :molecule, :status,
                    :jurisdiction, :country, :location, :capacity_mtpd, :capex_eur,
                    :created_by, :created_at, :updated_at, true, CAST(:metadata_json AS jsonb)
                )
                ON CONFLICT (project_id) DO NOTHING
            """), p)
            written += res.rowcount or 0

    print(f"\n  WROTE {written} project(s). Created 0 tenants.")
    print(f"  Source: {RETIRED_TABLE} — no values invented; three derived, each stated above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
