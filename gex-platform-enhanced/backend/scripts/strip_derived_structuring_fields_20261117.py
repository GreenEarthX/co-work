"""Clean the stored structuring records after 2026-11-17.

Structuring takes gate decisions and state from the gate engine and identity
from the project registry (app/core/structuring_context.py). Those fields in a
stored `structuring_context` record are ignored; this removes them so nobody
reads them as live.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/strip_derived_structuring_fields_20261117.py               # report only
    ./venv/bin/python scripts/strip_derived_structuring_fields_20261117.py --execute

It deletes nothing and reads no reference case. A record that is not a project's
own is removed by provenance, with a quarantine copy (handoff v4 task 7: Bremen
H2, scripts/data/quarantine/), never by numerical similarity. The 2026-10-25 load
file no longer carries these fields, so a rebuild needs no re-run. Idempotent.
"""
from __future__ import annotations

import json
import os
import sys

DERIVED = ("gate_scores", "stage", "jurisdiction", "molecule", "project_size_eur")


def main(execute: bool) -> int:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not (dsn or "").startswith("postgres"):
        print("ALEMBIC_DATABASE_URL must be exported")
        return 1
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT project_id, payload FROM project_dataset WHERE kind = 'structuring_context' ORDER BY project_id")
        for project_id, payload in cur.fetchall():
            payload = payload if isinstance(payload, dict) else json.loads(payload)
            derived = [k for k in DERIVED if k in payload]
            print(f"{project_id}: derived fields {derived or 'none'}")
            if derived:
                kept = {k: v for k, v in payload.items() if k not in DERIVED}
                cur.execute("UPDATE project_dataset SET payload = %s, updated_at = now() "
                            "WHERE project_id = %s AND kind = 'structuring_context'",
                            (json.dumps(kept), project_id))
                print(f"   stripped {derived}")
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
