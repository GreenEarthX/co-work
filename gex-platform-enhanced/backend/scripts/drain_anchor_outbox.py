#!/usr/bin/env python
"""
Drain the ledger anchor outbox once, by hand (Phase 4 of "One contract record", Q11).

    set -a && source .env && set +a        # LEDGER_ANCHOR_DATABASE_URL (role gex_anchor) must be EXPORTED or in .env
    venv/bin/python scripts/drain_anchor_outbox.py --once                 # one pass with the configured backend
    venv/bin/python scripts/drain_anchor_outbox.py --status               # counts by status, nothing changed
    venv/bin/python scripts/drain_anchor_outbox.py --requeue-failed       # FAILED -> PENDING (attempts kept)
    venv/bin/python scripts/drain_anchor_outbox.py --requeue-not-anchored # NOT_ANCHORED -> PENDING, once anchoring is on
    venv/bin/python scripts/drain_anchor_outbox.py --assign-pseudo-ids    # contracts written without a salt

The backend worker does the same pass every 30 s when LEDGER_ANCHOR_BACKEND is not
"none". With it "none", --once uses NullAnchor and marks the due rows NOT_ANCHORED —
deliberately: a row is never silently left looking anchored.

Everything here runs as gex_anchor (SELECT on the outbox, UPDATE on its anchoring
columns, nothing else), except --assign-pseudo-ids, which sets tb_contract.pseudo_id
and so runs as the migrator (ALEMBIC_DATABASE_URL); the outbox rows follow by trigger.

Exit codes: 0 done; 2 the database could not be reached; 5 the backend is misconfigured.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    from app.core import ledger_anchor as la
    from app.core.config import settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    for flag in ("--once", "--status", "--requeue-failed", "--requeue-not-anchored", "--assign-pseudo-ids"):
        g.add_argument(flag, action="store_true")
    args = ap.parse_args(argv)

    if args.assign_pseudo_ids:
        import psycopg2

        if not settings.LEDGER_ANCHOR_SALT:
            print("LEDGER_ANCHOR_SALT is not set", file=sys.stderr)
            return 5
        dsn = os.environ.get("ALEMBIC_DATABASE_URL") or settings.ALEMBIC_DATABASE_URL
        try:
            conn = psycopg2.connect(dsn)
        except psycopg2.OperationalError as exc:
            print(f"database unreachable: {exc}", file=sys.stderr)
            return 2
        cur = conn.cursor()
        cur.execute("SELECT id, contract_ref FROM tb_contract WHERE pseudo_id IS NULL AND contract_ref IS NOT NULL")
        rows = cur.fetchall()
        for cid, ref in rows:
            cur.execute("UPDATE tb_contract SET pseudo_id = %s WHERE id = %s AND pseudo_id IS NULL",
                        (la.pseudo_id(ref), cid))
        conn.commit()
        conn.close()
        print(f"assigned {len(rows)} pseudonymous id(s)")
        return 0

    problems = la.config_problems(settings)
    if problems:
        print("backend misconfigured: " + "; ".join(problems), file=sys.stderr)
        return 5
    try:
        conn = la.connect_worker()
    except Exception as exc:  # noqa: BLE001
        print(f"database unreachable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        cur = conn.cursor()
        if args.status:
            cur.execute("SELECT status, count(*) AS n FROM ledger_anchor_outbox GROUP BY status ORDER BY status")
            print(json.dumps({r["status"]: r["n"] for r in cur.fetchall()}))
            return 0
        if args.requeue_failed or args.requeue_not_anchored:
            src = "FAILED" if args.requeue_failed else "NOT_ANCHORED"
            cur.execute("UPDATE ledger_anchor_outbox SET status = 'PENDING', next_attempt_at = now() "
                        "WHERE status = %s", (src,))
            print(f"requeued {cur.rowcount} {src} row(s)")
            conn.commit()
            return 0
    finally:
        conn.close()
    anchor = la.anchor_from_settings(settings)
    print(json.dumps({"backend": settings.LEDGER_ANCHOR_BACKEND, **la.drain_once(la.connect_worker, anchor)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
