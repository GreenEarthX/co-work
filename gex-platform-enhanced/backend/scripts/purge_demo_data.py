#!/usr/bin/env python
"""
Remove demo and test rows from PostgreSQL. Dry run by default.

    set -a && source .env && set +a
    venv/bin/python scripts/purge_demo_data.py            # dry run — counts only
    venv/bin/python scripts/purge_demo_data.py --execute  # delete

WHAT THIS REMOVES, AND HOW IT WAS IDENTIFIED
--------------------------------------------
Measured 2026-09-23 against the live database, not inferred:

  bankability_evidence   125 of 127 rows carry submitted_by='demo_seed' and
                         notes='Seeded demo'. They were written by
                         POST /bankability/evidence/seed, an HTTP endpoint that
                         took `project_id` as an unchecked query parameter — so
                         they sit on REAL projects, not only the placeholder
                         one. The endpoint and its two UI buttons were removed
                         in the same change; without that this script would be
                         undone by the next click.
  evidence_events         12 rows with actor='demo_seed'.
  bankability_snapshots    3 snapshots COMPUTED FROM the seeded evidence — a
                         completion percentage and a risk classification
                         derived entirely from invented rows.
  gateway_registry         1 row, cert_fingerprint
                         'sha256:demo_cert_fingerprint_change_in_production',
                         seeded at startup by ot_boundary.init_ot_db().
  entitlement_audit,     rows belonging to nine project ids that do not exist
  finance_entitlements,  and never did: proj_nope, proj_econ_test, proj_empty,
  evidence_ledger        proj_no_such_thing and the ADV-* adversarial-review
                         fixtures.

WHAT THIS DELIBERATELY DOES **NOT** TOUCH
-----------------------------------------
`auth_users` — 17 of 20 rows carry activated_by='SEED_GRANDFATHERED'. That is a
PROVENANCE MARKER on real people who predate the vetting flow, not a marker of
fake accounts. Deleting them would delete the platform's actual users. The
marker is how they are found; it is not a verdict on them.

The two genuine `bankability_evidence` rows (anna.keller@rheinwerk.de and
thierry.groell@etfuels.com) stay, and after this run they are the whole table.

REVERSIBILITY
-------------
Every row was exported first to
`db_backups/removed_demo_and_test_rows_2026-09-23.json` (532 rows). SQLite
still holds its own copies — it is the frozen pre-cutover store and is not
touched here.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text

TEST_PROJECTS = ["proj_nope", "proj_econ_test", "proj_empty", "proj_no_such_thing",
                 "ADV-BR-OK", "ADV-P1P5-FIXED", "ADV-P1-ONWIRE", "ADV-P1-TEST", "ADV-BR-IMP"]

TARGETS = [
    ("bankability_evidence",  "submitted_by = 'demo_seed'"),
    ("evidence_events",       "actor = 'demo_seed'"),
    ("bankability_snapshots", "snapshot_json LIKE '%demo_seed%'"),
    ("gateway_registry",      "cert_fingerprint LIKE '%demo_cert_fingerprint%'"),
    ("entitlement_audit",     "project_id = ANY(:projects)"),
    ("finance_entitlements",  "project_id = ANY(:projects)"),
    ("evidence_ledger",       "project_id = ANY(:projects)"),
]

BACKUP = "db_backups/removed_demo_and_test_rows_2026-09-23.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="delete; without it, only counts are printed")
    args = ap.parse_args()

    url = os.environ.get("ALEMBIC_DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("ALEMBIC_DATABASE_URL must be an explicit PostgreSQL URL")

    if args.execute and not os.path.exists(BACKUP):
        raise SystemExit(
            f"refusing to delete: {BACKUP} is missing. The export is the only way "
            "back — re-run the backup before deleting.")

    engine = create_engine(url)
    print(f"Postgres: {url.split('@')[-1]}")
    print(f"Mode    : {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    total = 0
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'"))
        for table, where in TARGETS:
            params = {"projects": TEST_PROJECTS} if ":projects" in where else {}
            n = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where}"),
                             params).scalar()
            total += n
            if args.execute and n:
                conn.execute(text(f"DELETE FROM {table} WHERE {where}"), params)
            print(f"  {table:24s} {n:5d} row(s){' — removed' if args.execute and n else ''}")

        print(f"\n{'removed' if args.execute else 'would remove'} {total} row(s)")

        # State the kept set explicitly, every run, so nobody has to trust the
        # docstring about the one thing that would be catastrophic to get wrong.
        kept = conn.execute(text(
            "SELECT COUNT(*) FROM auth_users WHERE activated_by='SEED_GRANDFATHERED'")).scalar()
        print(f"\nKEPT: {kept} auth_users rows marked SEED_GRANDFATHERED — real people "
              "who predate vetting, not demo accounts")
        real = conn.execute(text(
            "SELECT COUNT(*) FROM bankability_evidence WHERE submitted_by <> 'demo_seed'")).scalar()
        print(f"KEPT: {real} genuine bankability_evidence row(s)")

    if not args.execute:
        print("\nDry run. Re-run with --execute to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
