#!/usr/bin/env python3
"""
restore_registry_projects.py — put back projects lost from PostgreSQL.
=====================================================================
WHY THIS EXISTS
---------------
On 2026-09-08 the PostgreSQL `gex_platform` schema was found empty — only
PostGIS's own tables. Migrations and the eight slice copiers rebuilt everything
except `projects`, because `migrate_projects_collision.py` reads
`SELECT * FROM projects` from SQLite and migration 033 retired that table. That
copier can no longer run, and nothing replaced it.

Migration 020 seeds 7 projects. `project_registry.py` knows 12. The 5 in the
gap were created at runtime and had no other home:

    etfuels_fi_ranua_naataaapa · etfuels_uk_skyfuel_teesside
    etfuels_us_tx_rattlesnake_gap · proj_etf_pecos1 · proj_rheinwerk_prosumer

WHERE THE DATA COMES FROM — AND WHAT IS NOT INVENTED
----------------------------------------------------
`project_registry.py` is an ACCESS profile (who may see a project), not a
project master: it carries id, name, owner company and jurisdiction, and none of
`molecule` or `status`, both of which are NOT NULL. Restoring from it alone
would mean inventing commercial attributes on a bankability platform.

The authoritative records are in `frontend/src/data/customerProjects.ts`, which
carries owner_company, molecule, location, country, capacity_mtpd, capex_eur,
status and completion_date. THIS SCRIPT READS THAT FILE. Nothing is guessed; a
field absent from the seed is written NULL, and the seven surviving rows already
carry NULLs in capex/capacity, so that is consistent rather than degraded.

TENANTS
-------
`ETFuels SA` and `RheinWerk Industries AG` are not in `tenants`, and
`owner_tenant_id` is NOT NULL. A project cannot be restored without its owner
existing, so this script creates those two tenants from the seed's
`owner_company` string. That is a second write and it is called out on every
run, because creating an organisation is not the same as restoring a project.

KNOWN DATA-QUALITY ISSUE, CARRIED NOT FIXED
-------------------------------------------
`proj_etf_pecos1` has `capex_eur: 562000000` alongside `capex_currency: "USD"`.
The column is named EUR and the seed says USD. This script writes the number as
it stands rather than applying an FX rate it cannot source. Flagged on every run.

USAGE
    python scripts/restore_registry_projects.py            # dry run (default)
    python scripts/restore_registry_projects.py --execute  # write

Idempotent: existing project_ids and company_ids are skipped, never updated.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SEED = BACKEND.parent / "frontend" / "src" / "data" / "customerProjects.ts"

TARGETS = [
    "etfuels_fi_ranua_naataaapa",
    "etfuels_uk_skyfuel_teesside",
    "etfuels_us_tx_rattlesnake_gap",
    "proj_etf_pecos1",
    "proj_rheinwerk_prosumer",
]

# Only fields that map to a `projects` column. Anything else in the seed record
# (gates, ppas, bankability…) belongs to other tables and is deliberately left.
WANTED = ["name", "molecule", "location", "country", "capacity_mtpd",
          "capex_eur", "status", "completion_date", "owner_company"]


def _slice_record(src: str, project_id: str) -> str | None:
    """The text of one seed record, from its `id:` line to the next `id:`."""
    m = re.search(rf'id:\s*"{re.escape(project_id)}"', src)
    if not m:
        return None
    nxt = re.search(r'\n\s{2,4}id:\s*"', src[m.end():])
    return src[m.start(): m.end() + (nxt.start() if nxt else 4000)]


def _field(block: str, key: str):
    """One scalar field. Numeric literals may carry _ separators (210_000_000)."""
    m = re.search(rf'\b{key}:\s*"([^"]*)"', block)
    if m:
        return m.group(1)
    m = re.search(rf'\b{key}:\s*([0-9_]+(?:\.[0-9]+)?)', block)
    if m:
        return float(m.group(1).replace("_", "")) if "." in m.group(1) else int(m.group(1).replace("_", ""))
    return None


def read_seed() -> list[dict]:
    if not SEED.exists():
        sys.exit(f"seed not found: {SEED}")
    src = SEED.read_text()
    out = []
    for pid in TARGETS:
        block = _slice_record(src, pid)
        if block is None:
            print(f"  ! {pid}: no record in the seed — skipped, not invented")
            continue
        rec = {"project_id": pid}
        for k in WANTED:
            rec[k] = _field(block, k)
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="write (default is dry run)")
    args = ap.parse_args()

    sys.path.insert(0, str(BACKEND))
    from app.core.project_registry import company_slug  # noqa: E402

    import psycopg2  # noqa: E402

    dsn = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn or not dsn.startswith("postgres"):
        sys.exit("set ALEMBIC_DATABASE_URL (migrator credential) to a PostgreSQL DSN")

    records = read_seed()
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET app.current_company_id='PLATFORM_ADMIN'")

    cur.execute("select project_id from projects")
    have_projects = {r[0] for r in cur.fetchall()}
    cur.execute("select company_id from tenants")
    have_tenants = {r[0] for r in cur.fetchall()}

    new_tenants, new_projects, skipped = [], [], []
    for r in records:
        if r["project_id"] in have_projects:
            skipped.append(r["project_id"])
            continue
        owner = r.get("owner_company")
        if not owner:
            print(f"  ! {r['project_id']}: seed has no owner_company — skipped")
            continue
        slug = company_slug(owner)
        if slug not in have_tenants and slug not in [t[0] for t in new_tenants]:
            new_tenants.append((slug, owner))
        new_projects.append((r, slug))

    print(f"\n  seed file      : {SEED}")
    print(f"  already present: {len(skipped)} {skipped}")
    print(f"  tenants to add : {[t[0] for t in new_tenants]}")
    print(f"  projects to add: {len(new_projects)}")
    # capex_eur: 0 in the seed is a placeholder for "not filled in", not a
    # price — etfuels_uk_skyfuel_teesside is 90 MTPD of SAF and
    # etfuels_us_tx_rattlesnake_gap is 342 MTPD of e-methanol. Writing a literal
    # zero into a bankability platform risks it being consumed as a real figure
    # by blended WACC or the catalytic ratio. NULL says "unknown"; 0 says "free".
    for r, _ in new_projects:
        if r.get("capex_eur") == 0:
            r["capex_eur"] = None
            r["_capex_was_zero"] = True

    for r, slug in new_projects:
        cap = r.get("capex_eur")
        flags = []
        if r.get("_capex_was_zero"):
            flags.append("seed capex was 0 → written NULL (unknown, not free)")
        if r["project_id"] == "proj_etf_pecos1":
            flags.append("capex column is EUR, seed says USD — carried as-is")
        note = ("  ⚠ " + "; ".join(flags)) if flags else ""
        print(f"    {r['project_id']:32s} {r.get('molecule') or '?':12s} "
              f"owner={slug:24s} capex={cap}{note}")

    if not args.execute:
        print("\n  DRY RUN — nothing written. Re-run with --execute.")
        return 0

    # company_type is NOT NULL and the seed does not carry one for the owner.
    # PRODUCER is DERIVED, not guessed: every tenant that owns a project in this
    # database is PRODUCER (7 of 7), and these two own projects. `jurisdiction`
    # is also NOT NULL but the column defaults to 'EU', so it is left to default
    # rather than asserting a country for a company that operates in several.
    for slug, name in new_tenants:
        cur.execute(
            "INSERT INTO tenants (company_id, company_name, company_type) "
            "VALUES (%s, %s, 'PRODUCER') ON CONFLICT (company_id) DO NOTHING",
            (slug, name))
    for r, slug in new_projects:
        cur.execute("""
            INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule,
                                  status, jurisdiction, capex_eur, capacity_mtpd,
                                  completion_date, location, country, is_active,
                                  created_by, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,now(),now())
            ON CONFLICT (project_id) DO NOTHING
        """, (
            r["project_id"], r["name"], slug, r.get("molecule") or "UNKNOWN",
            r.get("status") or "development", r.get("country") or "XX",
            r.get("capex_eur"), r.get("capacity_mtpd"), r.get("completion_date"),
            r.get("location"), r.get("country"),
            "restore_registry_projects.py",
        ))
    conn.commit()
    print(f"\n  WROTE {len(new_tenants)} tenant(s) and {len(new_projects)} project(s).")
    print("  Source: frontend/src/data/customerProjects.ts — no values invented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
