"""
Move the per-project datasets the backend held in code into PostgreSQL (JML, 2026-10-25).

Source: scripts/data/project_datasets_20261025.json — PROJECT_TRUTH (deal-killer
and task-router inputs), routes_structuring.DEMO_CONTEXTS, routes_finance_model.
_DRAWDOWN_BY_PROJECT, adjacency.MOCK_PROJECTS (the real project only) and
PROJECT_ID_ALIASES, extracted verbatim. 20 datasets, 2 aliases. Rows are
UNVERIFIED; `source` names the dictionary each came from. The defaults those
modules used for unknown projects were not moved.

Idempotent; dry run unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/move_project_datasets_20261025.py [--execute]

Refuses to load (2026-11-17, handoff v4 task 7): a file with no `approved_by`, a
dataset with no `from` (its source), and any dataset whose provenance is a
reference case — Breizh SAF is a reference case only, and contamination is
defined by provenance, not by numerical similarity. It never reads tests/fixtures.

Needs migration 069. A database rebuilt from Alembic needs this run (after the
project scripts); a pg_dump restore already carries it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "project_datasets_20261025.json"
# Provenance that may never reach a project. Matched on the declared source, not on values.
REFERENCE_PROVENANCE = ("reference_case", "reference case", "tests/fixtures", "breizh")


def refusals(data: dict) -> list[str]:
    """Why this load file may not be loaded; empty when it may."""
    out = []
    if not str(data.get("approved_by") or "").strip():
        out.append("the file names no approver (approved_by)")
    for d in data.get("datasets", []):
        where = f"{d.get('project_id')} {d.get('kind')}"
        source = str(d.get("from") or "").strip()
        if not source:
            out.append(f"{where}: no source (from)")
        marks = " ".join([source, str(d.get("provenance") or ""), str((d.get("payload") or {}).get("_provenance") or "")]).lower()
        if any(m in marks for m in REFERENCE_PROVENANCE):
            out.append(f"{where}: provenance is a reference case ({source}) — never loaded into a project")
    return out


def main(execute: bool) -> int:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not (dsn or "").startswith("postgres"):
        print("ALEMBIC_DATABASE_URL must be exported")
        return 1
    data = json.loads(DATA.read_text())
    refused = refusals(data)
    if refused:
        print("REFUSED — nothing loaded:\n  " + "\n  ".join(refused))
        return 2
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        for a in data["aliases"]:
            cur.execute("INSERT INTO project_id_alias (alias, project_id, note) VALUES (%s, %s, %s) "
                        "ON CONFLICT (alias) DO NOTHING",
                        (a["alias"], a["project_id"], "retired id, moved from PROJECT_ID_ALIASES 2026-10-25"))
            print(f"alias {a['alias']} -> {a['project_id']}: {'added' if cur.rowcount else 'present'}")
        for d in data["datasets"]:
            cur.execute("INSERT INTO project_dataset (project_id, kind, payload, source) VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (project_id, kind) DO NOTHING",
                        (d["project_id"], d["kind"], json.dumps(d["payload"]),
                         f"backend {d['from']}, moved to PostgreSQL 2026-10-25"))
            print(f"{d['project_id']} {d['kind']}: {'added' if cur.rowcount else 'present'}")
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
