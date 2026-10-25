"""
Move the per-project data the FRONTEND held in code into PostgreSQL (JML, 2026-10-25).

Source: scripts/data/frontend_datasets_20261025.json, extracted verbatim from the
screens by scripts/extract_frontend_datasets_20261025.cjs (14 kinds). Rows are
UNVERIFIED; `source` names the screen and constant each came from.

Keys are resolved through project_id_alias. When a dictionary held BOTH a retired
id and the current one (e.g. proj_le_havre_eng and proj_lehavre_eng), the entry
under the current id is kept and the other reported. Keys with no project
(e.g. proj_helios_solar) and every "default" entry are not moved.

Idempotent; dry run unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/move_frontend_datasets_20261025.py [--execute]

Needs migration 071. A database rebuilt from Alembic needs this run (after
move_project_datasets_20261025.py); a pg_dump restore already carries it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "frontend_datasets_20261025.json"


def plan(entries: list[dict], projects: set[str], aliases: dict[str, str]):
    """(rows, notes): rows = (project_id, kind, payload, source)."""
    rows, notes = [], []
    for e in entries:
        chosen: dict[str, tuple[str, object]] = {}
        for key, payload in e["data"].items():
            if key == "default":
                notes.append(f"{e['kind']}: 'default' not moved (it answered for every project)")
                continue
            pid = key if key in projects else aliases.get(key)
            if pid is None:
                notes.append(f"{e['kind']}: {key} is no project — not moved")
                continue
            if pid in chosen:
                keep_key = key if key == pid else chosen[pid][0]
                drop_key = chosen[pid][0] if keep_key == key else key
                notes.append(f"{e['kind']}: {drop_key} and {keep_key} both map to {pid} — kept {keep_key}")
                if keep_key == chosen[pid][0]:
                    continue
            chosen[pid] = (key, payload)
        for pid, (key, payload) in chosen.items():
            rows.append((pid, e["kind"], payload, f"frontend {e['from']} [{key}], moved to PostgreSQL 2026-10-25"))
    return rows, notes


def main(execute: bool) -> int:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not (dsn or "").startswith("postgres"):
        print("ALEMBIC_DATABASE_URL must be exported")
        return 1
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT project_id FROM projects")
        projects = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT alias, project_id FROM project_id_alias")
        aliases = dict(cur.fetchall())
        rows, notes = plan(json.loads(DATA.read_text()), projects, aliases)
        for n in notes:
            print("note:", n)
        for pid, kind, payload, source in rows:
            cur.execute("INSERT INTO project_dataset (project_id, kind, payload, source) VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (project_id, kind) DO NOTHING", (pid, kind, json.dumps(payload), source))
            print(f"{pid} {kind}: {'added' if cur.rowcount else 'present'}")
        print(f"{len(rows)} datasets")
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
