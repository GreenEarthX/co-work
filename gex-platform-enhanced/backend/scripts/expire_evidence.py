#!/usr/bin/env python
"""
Re-evaluate every project whose stored evaluation has gone stale because evidence expired
(rules 4.5.0). Dry run by default.

    set -a && source .env && set +a        # DATABASE_URL and ALEMBIC_DATABASE_URL must be EXPORTED
    venv/bin/python scripts/expire_evidence.py              # list the projects that would be re-evaluated
    venv/bin/python scripts/expire_evidence.py --apply      # re-evaluate them (needs the PF engine on :8001)

Why a sweep as well as the read-time rule (`fresh_snapshot`): a read re-evaluates a stale project
only when someone looks. Expiry is the one change nobody makes, so the executives a project
designates would otherwise learn of a lapsed permit when they next open the page. Re-evaluating
here goes through the same `reevaluate`, so a state or gate that moves is recorded and the
designated executives are notified (migration 076).

Reads the stored evaluations' `next_expiry` (written by the engine); touches nothing else. The
re-evaluation itself runs as PLATFORM_ADMIN — a system action across tenants, logged by
`_tenant_context` — and its actor is `system:expiry_sweep`.

Scheduled by files/com.gex.expiry-sweep.plist (daily). That agent is NOT installed by this script;
the two commands are in its header comment.

Exit codes (what `launchctl list | grep gex` shows in its second column):
    0   nothing was stale, or every stale project was re-evaluated
    2   the database could not be read (Docker stopped or PAUSED? `docker start files-postgres-1`) —
        a connection that is never answered times out after 10 s (PGCONNECT_TIMEOUT, app/core/config.py)
    3   at least one project could not be re-evaluated (the PF engine on :8001 down?); the others were
    4   the whole run exceeded SWEEP_TIMEOUT_SECONDS (default 600): something answered and then stopped
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def stale_projects(today: str) -> list[tuple[str, str]]:
    """(project_id, next_expiry) for each stored evaluation whose next_expiry is before today."""
    from app.api.v1 import routes_bankability_proxy as proxy
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company("PLATFORM_ADMIN")
    try:
        conn = proxy._get_db()
        proxy._ensure_tables(conn)
        rows = conn.execute("SELECT project_id, snapshot_json FROM bankability_snapshots").fetchall()
        conn.close()
    finally:
        reset_current_company(token)
    out = []
    for r in rows:
        try:
            nxt = (json.loads(r["snapshot_json"]) or {}).get("next_expiry")
        except (TypeError, ValueError):
            continue
        if nxt and str(nxt)[:10] < today:
            out.append((r["project_id"], str(nxt)[:10]))
    return sorted(out)


async def sweep(projects: list[tuple[str, str]]) -> list[str]:
    """Re-evaluate each project; returns the ids that failed. One failure never stops the others."""
    failed: list[str] = []
    from app.api.v1 import routes_bankability_proxy as proxy
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company("PLATFORM_ADMIN")
    try:
        for pid, nxt in projects:
            try:
                result = await proxy.reevaluate(pid, reason="evidence expired", actor="system:expiry_sweep")
                snap = result.get("snapshot") or {}
                print(f"  re-evaluated {pid}: {snap.get('current_state')} "
                      f"(expired: {[e['key'] for e in snap.get('expired_evidence', [])] or 'none'})")
            except Exception as exc:  # noqa: BLE001 — one project's failure must not stop the sweep
                failed.append(pid)
                print(f"  FAILED {pid}: {getattr(exc, 'detail', exc)}")
    finally:
        reset_current_company(token)
    return failed


def _watchdog(seconds: int) -> None:
    """A mid-run stall (a socket that answered, then went silent) must end the job, not hold it for hours.
    A THREAD, not SIGALRM: a signal handler only runs when the main thread returns from the blocking
    libpq call it is stuck in, which is exactly the case this exists for."""
    import threading

    def expire():
        print(f"expiry sweep: still running after {seconds}s — giving up (exit 4)", flush=True)
        os._exit(4)

    timer = threading.Timer(seconds, expire)
    timer.daemon = True
    timer.start()


def main() -> None:
    _watchdog(int(os.environ.get("SWEEP_TIMEOUT_SECONDS", "600")))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="re-evaluate; default is a dry run")
    args = ap.parse_args()
    today = date.today().isoformat()
    try:
        projects = stale_projects(today)
    except Exception as exc:  # noqa: BLE001
        print(f"{today}: cannot read the evaluations: {exc}")
        sys.exit(2)
    print(f"{today}: {len(projects)} project(s) with expired evidence since their last evaluation")
    for pid, nxt in projects:
        print(f"  {pid}  (an item was valid until {nxt})")
    if not args.apply:
        print("dry run — nothing re-evaluated (--apply to run)")
        return
    failed = asyncio.run(sweep(projects))
    if failed:
        print(f"{len(failed)} of {len(projects)} could not be re-evaluated: {', '.join(failed)}")
        sys.exit(3)


if __name__ == "__main__":
    main()
