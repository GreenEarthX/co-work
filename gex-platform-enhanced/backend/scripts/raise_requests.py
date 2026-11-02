#!/usr/bin/env python
"""
Raise open evidence requests for items a project needs and has no row for. Dry run by default.

    set -a && source .env && set +a        # ALEMBIC_DATABASE_URL must be EXPORTED
    venv/bin/python scripts/raise_requests.py --project proj_rheinwerk_prosumer \\
        --key ie_report_issued --key energy_balance_verified                      # dry run: the plan
    venv/bin/python scripts/raise_requests.py ... --apply                         # one transaction

Why it exists: rules 4.3.0 made seven items apply to balance-sheet projects that they used to skip,
and nothing raises a request for an item that becomes applicable. The 85 open requests came from the
2026-09-26 conversion; this is the same row shape (NOT_STARTED, assigned by `resolve_assignee`, one
`evidence_events` row) for items added later.

Refuses, per key: an item that is not live, one that does not apply to the project's declared
premises (power or financing model), and one that already has a row. A request with no one to assign
is still raised, unassigned, and says so — an honest gap, never a guess.

Runs with the MIGRATION credential (gex_user): it must write across tenants, which the runtime role
never can. Take a backup first (files/backup_postgres.sh); this script does not.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
import psycopg2.extras

from app.core.bankability_engine import EVIDENCE_OWNER_FUNCTION, inapplicability, resolve_assignee
from app.core.project_registry import get_effective_context


def _connect():
    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not dsn or not dsn.startswith("postgresql"):
        sys.exit("export ALEMBIC_DATABASE_URL (migration credential) — see .claude/CLAUDE.md")
    return psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://"),
                            cursor_factory=psycopg2.extras.RealDictCursor)


def plan(cur, project_id: str, keys: list[str]) -> tuple[list[dict], list[tuple[str, str]]]:
    cur.execute("SELECT owner_tenant_id FROM projects WHERE project_id=%s", (project_id,))
    owner = cur.fetchone()
    if not owner:
        sys.exit(f"no such project: {project_id}")
    cur.execute("SELECT user_id, business_function FROM auth_users WHERE account_state='ACTIVE' "
                "AND company_id=%s AND COALESCE(is_platform_admin, 0)=0", (owner["owner_tenant_id"],))
    accounts = [dict(a) for a in cur.fetchall()]
    ctx = get_effective_context(project_id)
    power, financing = getattr(ctx, "power_model", None), getattr(ctx, "financing_model", None)
    cur.execute("SELECT evidence_key FROM bankability_evidence WHERE project_id=%s", (project_id,))
    have = {r["evidence_key"] for r in cur.fetchall()}
    raise_, refused = [], []
    for key in keys:
        if key not in EVIDENCE_OWNER_FUNCTION:
            refused.append((key, "not a live evidence item"))
        elif key in have:
            refused.append((key, "the project already has a row for it"))
        elif (why := inapplicability(key, power, financing)):
            refused.append((key, f"does not apply to the project ({why})"))
        else:
            who, reason = resolve_assignee(key, accounts)
            raise_.append({"key": key, "assignee": who, "reason": reason})
    return raise_, refused


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--key", action="append", required=True, help="evidence key (repeatable)")
    ap.add_argument("--actor", default="ops:raise_requests")
    ap.add_argument("--apply", action="store_true", help="write (one transaction); default is a dry run")
    args = ap.parse_args()
    conn = _connect()
    cur = conn.cursor()
    raise_, refused = plan(cur, args.project, args.key)
    print(f"{args.project}: {len(raise_)} request(s) to raise, {len(refused)} refused")
    for r in raise_:
        print(f"  + {r['key']:<34} -> {r['assignee'] or '(unassigned)':<34} {r['reason']}")
    for key, why in refused:
        print(f"  - {key:<34} {why}")
    if not args.apply:
        print("dry run — nothing written (--apply to write)")
        return
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for r in raise_:
        note = f"Open request, raised {at[:10]} for an item that became applicable under the current rules. {r['reason']}."
        cur.execute("INSERT INTO bankability_evidence (project_id, evidence_key, status, notes, assignee_user_id, "
                    "assigned_by, assigned_at, updated_at) VALUES (%s,%s,'NOT_STARTED',%s,%s,%s,%s,%s)",
                    (args.project, r["key"], note, r["assignee"], args.actor if r["assignee"] else None,
                     at if r["assignee"] else None, at))
        cur.execute("INSERT INTO evidence_events (project_id, evidence_key, old_status, new_status, actor, at, "
                    "old_maturity, new_maturity, old_assignee, new_assignee) VALUES (%s,%s,NULL,'NOT_STARTED',%s,%s,"
                    "NULL,NULL,NULL,%s)", (args.project, r["key"], args.actor, at, r["assignee"]))
    conn.commit()
    print(f"wrote {len(raise_)} request(s)")


if __name__ == "__main__":
    main()
