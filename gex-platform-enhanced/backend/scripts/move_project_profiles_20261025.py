"""
Move the project data the code held into PostgreSQL (JML, 2026-10-25).

Source: scripts/data/project_records_20261025.json — customerProjects.ts's 12
projects and risk_flags.py's flags, extracted verbatim.

  1. projects — PostgreSQL is the reference: a column that holds a value keeps
     it; only NULL headline columns (location, capacity_mtpd, capex_eur,
     completion_date) are filled from the file.
  2. project_profile — the rest of each project (bankability snapshot, gates,
     offtakes, energy, certifications, incentives, timeline, narrative, ...).
  3. project_risk_flag — one row per flag.
  4. project_context — the seed power model / phase / financing model that
     project_registry.PROJECT_PHYSICAL held for 7 projects, where no row exists
     (a stored row always wins; updated_by names the move).
  5. project_profile_intelligence — the one record routes_projects held in
     _PROJECT_PROFILE_INTELLIGENCE (the table existed, empty).
Rows are UNVERIFIED (verification_state default) with `source` naming the file.

Idempotent: present rows and set columns are left alone. Dry run unless --execute.
Prints every place the file disagreed with PostgreSQL (PostgreSQL kept).

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/move_project_profiles_20261025.py [--execute]

Needs migration 068. A database rebuilt from Alembic needs this run (after the
project restore scripts and move_project_registry_20261025.py); a pg_dump
restore already carries it.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "project_records_20261025.json"
SOURCE = "frontend customerProjects.ts / backend risk_flags.py, moved to PostgreSQL 2026-10-25"
PHYSICAL = {   # project_registry.PROJECT_PHYSICAL as it stood on 2026-10-25, verbatim
    "proj_etf_pecos1": ("OFF_GRID_BTM", "development", "PROJECT_FINANCE"),
    "etfuels_us_tx_rattlesnake_gap": ("OFF_GRID_BTM", "development", "PROJECT_FINANCE"),
    "etfuels_fi_ranua_naataaapa": ("OFF_GRID_BTM", "development", "PROJECT_FINANCE"),
    "etfuels_uk_skyfuel_teesside": ("OFF_GRID_BTM", "development", "PROJECT_FINANCE"),
    "proj_bremen_h2": ("GRID_CONNECTED", "construction", "PROJECT_FINANCE"),
    "proj_hamburgone_emethanol": ("GRID_CONNECTED", "development", "PROJECT_FINANCE"),
    "proj_rheinwerk_prosumer": ("HYBRID", "development", "BALANCE_SHEET"),
}
HEADLINE = ("id", "name", "molecule", "location", "country", "capacity_mtpd", "capex_eur", "status",
            "owner_company", "associated_companies", "completion_date")
FILL = {"location": "location", "capacity_mtpd": "capacity_mtpd", "capex_eur": "capex_eur",
        "completion_date": "completion_date"}   # projects column -> file key


def _iso_date(v):
    return v if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None


def main(execute: bool) -> int:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not (dsn or "").startswith("postgres"):
        print("ALEMBIC_DATABASE_URL must be exported")
        return 1
    data = json.loads(DATA.read_text())
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        for p in data["projects"]:
            pid = p["id"]
            cur.execute("SELECT project_name, molecule, status, location, capacity_mtpd, capex_eur, "
                        "completion_date FROM projects WHERE project_id = %s", (pid,))
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"{pid} is in the file but not in projects — restore projects first")
            current = dict(zip(("name", "molecule", "status", "location", "capacity_mtpd", "capex_eur",
                                "completion_date"), row))
            for col, key in FILL.items():
                value = _iso_date(p.get(key)) if col == "completion_date" else p.get(key)
                if current[col] is None and value not in (None, "", 0):
                    cur.execute(f"UPDATE projects SET {col} = %s, updated_at = now() WHERE project_id = %s "
                                f"AND {col} IS NULL", (value, pid))
                    print(f"1. {pid}: {col} filled = {value}")
            for key, col in (("name", "name"), ("molecule", "molecule"), ("status", "status")):
                if current[col] is not None and str(current[col]) != str(p.get(key)):
                    print(f"   {pid}: {key} differs — PostgreSQL {current[col]!r} kept, file had {p.get(key)!r}")
            profile = {k: v for k, v in p.items() if k not in HEADLINE}
            cur.execute("INSERT INTO project_profile (project_id, profile, source) VALUES (%s, %s, %s) "
                        "ON CONFLICT (project_id) DO NOTHING", (pid, json.dumps(profile), SOURCE))
            print(f"2. {pid}: profile {'added' if cur.rowcount else 'present'}")
        for seq, f in enumerate(data["risk_flags"]):
            cur.execute("INSERT INTO project_risk_flag (id, project_id, claim, severity, confidence, category, "
                        "owner_function, classification, source_ids, status, seq, source) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                        (f["id"], f["project_id"], f["claim"], f["severity"], f["confidence"], f["category"],
                         f["owner_function"], f["classification"], f["source_ids"], f["status"], seq, SOURCE))
            print(f"3. {f['id']}: {'added' if cur.rowcount else 'present'}")
        for pid, (power, phase, financing) in PHYSICAL.items():
            cur.execute("INSERT INTO project_context (project_id, power_model, phase, financing_model, updated_by, "
                        "updated_at) VALUES (%s, %s, %s, %s, 'MOVED_FROM_CODE_20261025', now()) "
                        "ON CONFLICT (project_id) DO NOTHING", (pid, power, phase, financing))
            print(f"4. {pid}: context {'added' if cur.rowcount else 'present'}")
        for rec in data.get("profile_intelligence", []):
            cur.execute("INSERT INTO project_profile_intelligence (record_id, project_id, narrative, source_scope, "
                        "access_tier, backend_store, linked_records, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (record_id) DO NOTHING",
                        (rec["record_id"], rec["project_id"], rec["narrative"], rec["source_scope"], rec["access_tier"],
                         rec["backend_store"], json.dumps(rec["linked_records"]), rec["updated_at"]))
            print(f"5. {rec['record_id']}: {'added' if cur.rowcount else 'present'}")
        if execute:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("dry run — nothing written; pass --execute")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
