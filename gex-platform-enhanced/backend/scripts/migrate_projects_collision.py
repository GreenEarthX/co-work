#!/usr/bin/env python
"""
Move runtime projects from the SQLite `projects` table into the canonical
PostgreSQL one, and bring project_context / project_context_events with them.

    DATABASE_URL=postgresql://... python scripts/migrate_projects_collision.py [--execute]

Dry run by default.

The mapping (SQLite -> Postgres). Every source column is accounted for:

    project_id          -> project_id
    name                -> project_name
    owner_company_name  -> owner_tenant_id      via company_slug(); the tenant
                           MUST already exist (FK). Reported, never invented.
    molecule            -> molecule
    country             -> country              (new column, 033)
    location            -> location             (new column, 033)
    created_by          -> created_by           (new column, 033)
    capacity_mtpd       -> capacity_mtpd
    capex_eur           -> capex_eur
    phase               -> status
    created_at          -> created_at           TEXT ISO -> TIMESTAMPTZ
    power_model         -> project_context.power_model      (NOT projects)
    financing_model     -> project_context.financing_model  (NOT projects)

power_model / financing_model / phase were stored on BOTH the SQLite projects
row and project_context. That duplication does not travel: project_context is
their canonical home. `status` keeps the lifecycle value 020 already defined.

Idempotent (ON CONFLICT DO UPDATE). SQLite is never written.
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
from app.core.project_registry import company_slug  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    pg_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    print(f"SQLite : {settings.SQLITE_DB_PATH}")
    print(f"Postgres: {pg_url.split('@')[-1]}")
    print(f"Mode   : {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    lite = sqlite3.connect(settings.SQLITE_DB_PATH)
    lite.row_factory = sqlite3.Row
    engine = create_engine(pg_url)
    problems: list[str] = []

    rows = lite.execute("SELECT * FROM projects").fetchall()
    ctx = lite.execute("SELECT * FROM project_context").fetchall()
    events = lite.execute("SELECT * FROM project_context_events").fetchall()
    print(f"── source: {len(rows)} projects, {len(ctx)} context, {len(events)} events\n")

    with engine.begin() as pg:
        # PLATFORM_ADMIN so RLS does not hide pre-existing rows from the check.
        pg.execute(text("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'"))
        tenants = {r[0] for r in pg.execute(text("SELECT company_id FROM tenants"))}

        for r in rows:
            tenant = company_slug(r["owner_company_name"])
            collides = pg.execute(
                text("SELECT owner_tenant_id FROM projects WHERE project_id=:p"),
                {"p": r["project_id"]},
            ).fetchone()
            note = ""
            if tenant not in tenants:
                problems.append(
                    f"{r['project_id']}: tenant {tenant!r} "
                    f"(from owner_company_name {r['owner_company_name']!r}) does not "
                    "exist in `tenants` — FK would fail. Create the tenant first.")
                note = "  ← MISSING TENANT"
            if collides:
                note += f"  ← already in Postgres (owner={collides[0]})"
            print(f"   {r['project_id']:38} -> tenant {tenant}{note}")

        if not args.execute:
            print("\nDry run. Re-run with --execute to write.")
            lite.close()
            return 1 if problems else 0

        for r in rows:
            tenant = company_slug(r["owner_company_name"])
            if tenant not in tenants:
                continue
            pg.execute(text("""
                INSERT INTO projects (project_id, project_name, owner_tenant_id,
                    molecule, status, jurisdiction, capex_eur, capacity_mtpd,
                    location, country, created_by, is_active, created_at)
                VALUES (:pid, :name, :tenant, :mol, :status, :juris, :capex, :cap,
                        :loc, :country, :by, true, :created)
                ON CONFLICT (project_id) DO UPDATE SET
                    project_name = EXCLUDED.project_name,
                    owner_tenant_id = EXCLUDED.owner_tenant_id,
                    molecule = EXCLUDED.molecule,
                    status = EXCLUDED.status,
                    capex_eur = EXCLUDED.capex_eur,
                    capacity_mtpd = EXCLUDED.capacity_mtpd,
                    location = EXCLUDED.location,
                    country = EXCLUDED.country,
                    created_by = EXCLUDED.created_by
            """), {
                "pid": r["project_id"], "name": r["name"], "tenant": tenant,
                "mol": r["molecule"], "status": r["phase"] or "development",
                # jurisdiction is the regulatory regime, NOT the country. The old
                # code conflated them; keep 020's default rather than assert 'DE'
                # is a jurisdiction.
                "juris": "EU",
                "capex": r["capex_eur"], "cap": r["capacity_mtpd"],
                "loc": r["location"], "country": r["country"],
                "by": r["created_by"], "created": r["created_at"],
            })
        print(f"\n   projects copied : {len(rows)}")

        for r in ctx:
            pg.execute(text("""
                INSERT INTO project_context (project_id, power_model, phase,
                    financing_model, updated_by, updated_at)
                VALUES (:p, :pm, :ph, :fm, :by, :at)
                ON CONFLICT (project_id) DO UPDATE SET
                    power_model = EXCLUDED.power_model,
                    phase = EXCLUDED.phase,
                    financing_model = EXCLUDED.financing_model,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
            """), {"p": r["project_id"], "pm": r["power_model"], "ph": r["phase"],
                   "fm": r["financing_model"], "by": r["updated_by"], "at": r["updated_at"]})
        print(f"   context copied  : {len(ctx)}")

        for r in events:
            pg.execute(text("""
                INSERT INTO project_context_events (id, project_id, field,
                    old_value, new_value, actor, at)
                VALUES (:i, :p, :f, :o, :n, :a, :at)
                ON CONFLICT (id) DO NOTHING
            """), {"i": r["id"], "p": r["project_id"], "f": r["field"],
                   "o": r["old_value"], "n": r["new_value"], "a": r["actor"], "at": r["at"]})
        # Keep the identity sequence ahead of the copied ids.
        pg.execute(text(
            "SELECT setval('project_context_events_id_seq', "
            "GREATEST((SELECT COALESCE(MAX(id),0) FROM project_context_events), 1))"))
        print(f"   events copied   : {len(events)}")

    # ── Parity ──────────────────────────────────────────────────────────────
    print("\n══ PARITY ══")
    with engine.connect() as pg:
        pg.execute(text("SET app.current_company_id = 'PLATFORM_ADMIN'"))
        for r in rows:
            d = pg.execute(text(
                "SELECT project_name, owner_tenant_id, molecule, location, country, "
                "created_by, capacity_mtpd, capex_eur, status FROM projects WHERE project_id=:p"
            ), {"p": r["project_id"]}).mappings().first()
            if not d:
                problems.append(f"{r['project_id']}: not present in Postgres after copy")
                continue
            checks = {
                "project_name": (r["name"], d["project_name"]),
                "owner_tenant_id": (company_slug(r["owner_company_name"]), d["owner_tenant_id"]),
                "molecule": (r["molecule"], d["molecule"]),
                "location": (r["location"], d["location"]),
                "country": (r["country"], d["country"]),
                "created_by": (r["created_by"], d["created_by"]),
                "capacity_mtpd": (r["capacity_mtpd"], float(d["capacity_mtpd"] or 0)),
                "capex_eur": (r["capex_eur"], float(d["capex_eur"] or 0)),
                "status": (r["phase"], d["status"]),
            }
            bad = [k for k, (a, b) in checks.items() if str(a) != str(b)]
            print(f"  {r['project_id']:38} {'OK' if not bad else 'MISMATCH ' + str(bad)}")
            problems += [f"{r['project_id']}.{k} differs" for k in bad]

    lite.close()
    if problems:
        print("\n⚠  PROBLEMS")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("\nNo problems.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
