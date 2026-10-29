"""
Remove the hand-typed ASSESSMENTS from project_profile (JML, 2026-10-28).

`project_profile.profile.bankability` (and its loose siblings) held gate
completion, capital status ("DRAWN"), next milestones and risk alerts typed by
hand for demonstrations — HamburgOne read G0 100 % / 52 % overall while the
engine, counting verified evidence only, said 0 %. Gate figures now come from
the engine alone (app/core/engine_view.py); the route already withholds these
keys. This removes them from the rows, after writing each removed block
VERBATIM to scripts/data/archive_profile_assessments_20261028.json.

Idempotent; dry run unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/remove_profile_assessments_20261028.py [--execute]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

KEYS = ("bankability", "risk_alerts", "unlocked_capital", "capital_status", "overall_completion",
        "gates", "next_milestone")
ARCHIVE = Path(__file__).resolve().parent / "data" / "archive_profile_assessments_20261028.json"


def main(execute: bool) -> int:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not (dsn or "").startswith("postgres"):
        print("ALEMBIC_DATABASE_URL must be exported")
        return 1
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT project_id, profile FROM project_profile ORDER BY project_id")
        removed = {}
        for pid, profile in cur.fetchall():
            hit = {k: profile[k] for k in KEYS if k in (profile or {})}
            if hit:
                removed[pid] = hit
        print(f"{len(removed)} profile(s) carry assessments: {', '.join(removed) or '-'}")
        if not removed:
            return 0
        if execute:
            prior = json.loads(ARCHIVE.read_text()) if ARCHIVE.exists() else {}
            prior.update(removed)
            ARCHIVE.write_text(json.dumps(prior, indent=1, sort_keys=True))
            for pid in removed:
                cur.execute("UPDATE project_profile SET profile = profile - %s::text[], updated_at = now() "
                            "WHERE project_id = %s", (list(KEYS), pid))
            conn.commit()
            print(f"archived to {ARCHIVE.name}; removed from {len(removed)} row(s)")
        else:
            print("dry run — nothing written; pass --execute")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
