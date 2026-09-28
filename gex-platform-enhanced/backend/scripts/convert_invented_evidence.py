#!/usr/bin/env python
"""
Convert invented evidence rows into open requests assigned to real accounts.
Dry run by default. PostgreSQL only.

    set -a && source .env && set +a        # ALEMBIC_DATABASE_URL must be EXPORTED
    venv/bin/python scripts/convert_invented_evidence.py \\
        --submitted-by demo_seed --row-id 346 --row-id 347          # dry run: the plan
    venv/bin/python scripts/convert_invented_evidence.py ... --apply # one transaction

The decision rules live in app/core/evidence_conversion.py; read its docstring.
In short: every selected row is archived verbatim to bankability_evidence_archive,
then reset to an open request for a named person, replaced by an open request for
its successor key, or removed when its project has no owner.

Runs with the MIGRATION credential (ALEMBIC_DATABASE_URL, gex_user). This is a
data migration: it must see every tenant's rows at once, which the runtime role
gex_app — correctly — never can. It needs migration 055.

Selection is explicit. 2026-09-26: all 127 rows were invented — 125 carry
submitted_by='demo_seed'; rows 346 and 347 were entered by hand with invented
content under real people's names (confirmed by the platform owner). The
real accounts are untouched: nothing here writes auth_users.

--mirror-sqlite then copies the result into the legacy SQLite store
(settings.SQLITE_DB_PATH) after a VACUUM INTO backup: bankability_evidence and
bankability_snapshots are replaced by PostgreSQL's, and the conversion's audit
events are appended. PostgreSQL is the system of record since 2026-09-22, but
the SQLite file is still the fallback EVIDENCE_DB_BACKEND=sqlite reads — left
alone, flipping that switch would resurrect every invented row, 25 of them
VERIFIED. (tests/test_evidence_slice.py compares the two stores and caught it.)

--assign-open assigns every OPEN request that has no assignee, using the same
rule (resolve_assignee), and leaves assigned ones alone. Run it after GEX staff
activate a new account — e.g. the ETFuels Executive and Engineering accounts
that its 30 unassignable requests are waiting for. Dry run unless --apply.

--reevaluate then re-scores each affected project through the running engine
(:8001) and replaces its bankability_snapshot, which was computed from invented
evidence. Without it the next evaluation replaces them anyway.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
import psycopg2.extras

from app.core.bankability_engine import GATE_REGISTRY, RETIRED_EVIDENCE, resolve_assignee
from app.core.evidence_conversion import REMOVED, REPLACED, REQUEST, plan_conversion

ARCHIVE_REASON = "invented evidence — not produced or verified by anyone"


def _now() -> str:
    # Same shape as the rows already stored ('YYYY-MM-DD HH:MM:SS', UTC).
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _connect():
    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not dsn or not dsn.startswith("postgresql"):
        sys.exit("export ALEMBIC_DATABASE_URL (migration credential) — see .claude/CLAUDE.md")
    return psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://"))


def _load(cur, submitted_by: list[str], row_ids: list[int]):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name='bankability_evidence' AND column_name='assignee_user_id'")
    if not cur.fetchone():
        sys.exit("migration 055 is not applied: alembic upgrade auth_slice@head")
    cur.execute("SELECT * FROM bankability_evidence ORDER BY id")
    all_rows = [dict(r) for r in cur.fetchall()]
    selected = [r for r in all_rows if r["submitted_by"] in submitted_by or r["id"] in row_ids]
    missing = set(row_ids) - {r["id"] for r in all_rows}
    if missing:
        sys.exit(f"row ids not found: {sorted(missing)}")
    cur.execute("SELECT project_id, owner_tenant_id FROM projects")
    owner = {r["project_id"]: r["owner_tenant_id"] for r in cur.fetchall()}
    cur.execute("SELECT user_id, company_id, business_function FROM auth_users "
                "WHERE account_state = 'ACTIVE' AND COALESCE(is_platform_admin, 0) = 0")
    accounts: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        accounts.setdefault(r["company_id"], []).append(dict(r))
    return selected, all_rows, owner, accounts


def _print_plan(plan, owner) -> None:
    print(f"\n{len(plan.dispositions)} rows selected: {plan.count(REQUEST)} become open requests, "
          f"{plan.count(REPLACED)} retired keys replaced, {plan.count(REMOVED)} removed; "
          f"{len(plan.new_requests)} new requests for replacement keys.\n")
    by_project: dict[str, list] = {}
    for d in plan.dispositions:
        by_project.setdefault(d.row["project_id"], []).append(d)
    for pid, ds in by_project.items():
        print(f"  {pid}  (owner: {owner.get(pid) or 'none'})")
        for kind in (REQUEST, REPLACED, REMOVED):
            n = sum(1 for d in ds if d.kind == kind)
            if n:
                print(f"      {kind:<9}{n}")
        reqs = [d for d in ds if d.kind == REQUEST] + [n for n in plan.new_requests if n.project_id == pid]
        people: dict[str, int] = {}
        for x in reqs:
            people[x.assignee or "UNASSIGNED"] = people.get(x.assignee or "UNASSIGNED", 0) + 1
        for who, n in sorted(people.items()):
            print(f"        -> {who:<34}{n}")
    gaps = sorted({x.assign_reason for x in
                   [d for d in plan.dispositions if d.kind == REQUEST] + plan.new_requests
                   if x.assignee is None})
    if gaps:
        print("\n  Unassigned, and why:")
        for g in gaps:
            print(f"    - {g}")


def _event(cur, pid, key, old_status, new_status, actor, at, old_maturity, old_assignee, new_assignee):
    cur.execute(
        "INSERT INTO evidence_events (project_id, evidence_key, old_status, new_status, actor, at, "
        "old_maturity, new_maturity, old_assignee, new_assignee) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)",
        (pid, key, old_status, new_status, actor, at, old_maturity, old_assignee, new_assignee))


def _request_note(archive_id: int, assign_reason: str, at: str) -> str:
    return (f"Open request, created {at[:10]}. Replaces an invented demonstration row "
            f"(archived as #{archive_id}); nothing it claimed carries over. {assign_reason}.")


def _apply(cur, plan, actor: str) -> set[str]:
    at = _now()
    touched: set[str] = set()
    archive_id_of: dict[int, int] = {}
    for d in plan.dispositions:
        r = d.row
        touched.add(r["project_id"])
        cur.execute(
            "INSERT INTO bankability_evidence_archive (original_id, project_id, evidence_key, status, "
            "submitted_by, verified_by, submitted_at, verified_at, document_hash, notes, updated_at, "
            "maturity, archived_at, archived_by, archive_reason, disposition, replaced_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (r["id"], r["project_id"], r["evidence_key"], r["status"], r["submitted_by"],
             r["verified_by"], r["submitted_at"], r["verified_at"], r["document_hash"], r["notes"],
             r["updated_at"], r["maturity"], at, actor, ARCHIVE_REASON, d.kind, d.replaced_by))
        archive_id = cur.fetchone()["id"]
        archive_id_of[r["id"]] = archive_id
        if d.kind == REQUEST:
            cur.execute(
                "UPDATE bankability_evidence SET status='NOT_STARTED', submitted_by=NULL, "
                "verified_by=NULL, submitted_at=NULL, verified_at=NULL, document_hash=NULL, "
                "maturity=NULL, notes=%s, assignee_user_id=%s, assigned_by=%s, assigned_at=%s, "
                "due_date=NULL, updated_at=%s WHERE id=%s",
                (_request_note(archive_id, d.assign_reason, at), d.assignee, actor, at, at, r["id"]))
            _event(cur, r["project_id"], r["evidence_key"], r["status"], "NOT_STARTED", actor, at,
                   r["maturity"], r.get("assignee_user_id"), d.assignee)
        else:
            cur.execute("DELETE FROM bankability_evidence WHERE id=%s", (r["id"],))
            _event(cur, r["project_id"], r["evidence_key"], r["status"], "ARCHIVED", actor, at,
                   r["maturity"], r.get("assignee_user_id"), None)
    for n in plan.new_requests:
        cur.execute(
            "INSERT INTO bankability_evidence (project_id, evidence_key, status, notes, "
            "assignee_user_id, assigned_by, assigned_at, updated_at) "
            "VALUES (%s, %s, 'NOT_STARTED', %s, %s, %s, %s, %s)",
            (n.project_id, n.evidence_key,
             _request_note(archive_id_of[n.source_row_id], n.assign_reason, at),
             n.assignee, actor, at, at))
        _event(cur, n.project_id, n.evidence_key, None, "NOT_STARTED", actor, at, None, None, n.assignee)
    return touched


def _reevaluate(cur, projects: set[str]) -> None:
    """Re-score through the running engine; replace snapshots built on invented rows."""
    import httpx
    from app.services.engine_auth import engine_auth_headers
    from app.core.project_registry import get_effective_context

    engine = os.getenv("GEX_ENGINE_URL", "http://localhost:8001")
    for pid in sorted(projects):
        cur.execute("SELECT * FROM bankability_evidence WHERE project_id=%s", (pid,))
        evidence = [{"key": r["evidence_key"], "status": r["status"], "maturity": r["maturity"],
                     "submitted_by": r["submitted_by"], "verified_by": r["verified_by"],
                     "submitted_at": r["submitted_at"], "verified_at": r["verified_at"],
                     "document_hash": r["document_hash"], "notes": r["notes"]} for r in cur.fetchall()]
        cur.execute("SELECT current_state FROM bankability_snapshots WHERE project_id=%s", (pid,))
        prev = cur.fetchone()
        ctx = None
        try:
            ctx = get_effective_context(pid)
        except Exception:
            pass
        body = {"project_id": pid, "evidence": evidence,
                "previous_state": prev["current_state"] if prev else None,
                "power_model": getattr(ctx, "power_model", None),
                "project_phase": getattr(ctx, "phase", None),
                "financing_model": getattr(ctx, "financing_model", None)}
        resp = httpx.post(f"{engine}/api/v1/bankability/evaluate", json=body,
                          headers=engine_auth_headers(), timeout=15)
        resp.raise_for_status()
        snap = resp.json()
        cur.execute("DELETE FROM bankability_snapshots WHERE project_id=%s", (pid,))
        cur.execute("INSERT INTO bankability_snapshots (project_id, current_state, snapshot_json, "
                    "evaluated_at) VALUES (%s, %s, %s, %s)",
                    (pid, snap.get("current_state", "SPECULATIVE"), json.dumps(snap), _now()))
        print(f"  re-evaluated {pid}: {prev['current_state'] if prev else 'no snapshot'} -> "
              f"{snap.get('current_state')} ({snap.get('overall_completion_pct', 0):.1f}% complete)")


def _mirror_sqlite(cur, actor: str) -> None:
    """Make the legacy SQLite fallback hold what PostgreSQL holds, after a backup."""
    import sqlite3
    from app.api.v1.routes_bankability_proxy import _ensure_tables
    from app.core.config import settings

    path = Path(settings.SQLITE_DB_PATH)
    if not path.exists():
        print(f"  no SQLite store at {path}; nothing to mirror")
        return
    backup = path.parent.parent.parent / "db_backups" / f"{path.stem}_before_evidence_mirror_{_now()[:10]}.db"
    backup.parent.mkdir(exist_ok=True)
    lite = sqlite3.connect(path)
    lite.row_factory = sqlite3.Row
    if not backup.exists():
        lite.execute("VACUUM INTO ?", (str(backup),))   # WAL-safe, unlike copying the file
    os.environ["EVIDENCE_DB_BACKEND"] = "sqlite"          # _ensure_tables adds 054/055 columns
    settings.EVIDENCE_DB_BACKEND = "sqlite"
    _ensure_tables(lite)

    cur.execute("SELECT * FROM bankability_evidence ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM bankability_snapshots")
    snaps = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM evidence_events WHERE actor = %s ORDER BY id", (actor,))
    events = [dict(r) for r in cur.fetchall()]
    try:
        lite.execute("BEGIN")
        lite.execute("DELETE FROM bankability_evidence")
        cols = ["id", "project_id", "evidence_key", "status", "submitted_by", "verified_by",
                "submitted_at", "verified_at", "document_hash", "notes", "updated_at", "maturity",
                "assignee_user_id", "assigned_by", "assigned_at", "due_date"]
        lite.executemany(f"INSERT INTO bankability_evidence ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         [tuple(r.get(c) for c in cols) for r in rows])
        lite.execute("DELETE FROM bankability_snapshots")
        lite.executemany("INSERT INTO bankability_snapshots (project_id, current_state, snapshot_json, evaluated_at) "
                         "VALUES (?, ?, ?, ?)",
                         [(s["project_id"], s["current_state"], s["snapshot_json"], s["evaluated_at"]) for s in snaps])
        already = lite.execute("SELECT count(*) FROM evidence_events WHERE actor = ?", (actor,)).fetchone()[0]
        if not already:
            ecols = ["project_id", "evidence_key", "old_status", "new_status", "actor", "at",
                     "document_sha256", "old_maturity", "new_maturity", "old_assignee", "new_assignee"]
            lite.executemany(f"INSERT INTO evidence_events ({','.join(ecols)}) VALUES ({','.join('?' * len(ecols))})",
                             [tuple(e.get(c) for c in ecols) for e in events])
        lite.commit()
    except Exception:
        lite.rollback()
        raise
    finally:
        lite.close()
    print(f"  mirrored to {path.name}: {len(rows)} evidence rows, {len(snaps)} snapshots, "
          f"{0 if already else len(events)} audit events (backup: {backup})")


def _assign_open(cur, actor: str, apply: bool) -> None:
    """Give unassigned open requests to accounts that can now take them.

    A request on an item the project does not need (power model, or lender
    protection under balance-sheet funding) is left alone: the 2026-09-26
    conversion raised six of those, and assigning one asks a real person for
    evidence nobody will ever use."""
    from app.core.bankability_engine import inapplicability
    from app.core.project_registry import get_effective_context

    cur.execute("SELECT e.id, e.project_id, e.evidence_key, p.owner_tenant_id FROM bankability_evidence e "
                "JOIN projects p ON p.project_id = e.project_id "
                "WHERE e.assignee_user_id IS NULL AND e.status <> 'VERIFIED' ORDER BY e.id")
    rows = cur.fetchall()
    cur.execute("SELECT user_id, company_id, business_function FROM auth_users "
                "WHERE account_state = 'ACTIVE' AND COALESCE(is_platform_admin, 0) = 0")
    accounts: dict[str, list[dict]] = {}
    for a in cur.fetchall():
        accounts.setdefault(a["company_id"], []).append(dict(a))
    at, done, still, premise = _now(), {}, {}, {}
    for r in rows:
        pid = r["project_id"]
        if pid not in premise:
            ctx = get_effective_context(pid)
            premise[pid] = (getattr(ctx, "power_model", None), getattr(ctx, "financing_model", None))
        reason = inapplicability(r["evidence_key"], *premise[pid])
        if reason:
            key = f"item does not apply to the project ({reason})"
            still[key] = still.get(key, 0) + 1
            continue
        who, why = resolve_assignee(r["evidence_key"], accounts.get(r["owner_tenant_id"], []))
        if who is None:
            still[why] = still.get(why, 0) + 1
            continue
        done[who] = done.get(who, 0) + 1
        if apply:
            cur.execute("UPDATE bankability_evidence SET assignee_user_id=%s, assigned_by=%s, assigned_at=%s, "
                        "updated_at=%s WHERE id=%s AND assignee_user_id IS NULL", (who, actor, at, at, r["id"]))
            cur.execute("SELECT status FROM bankability_evidence WHERE id=%s", (r["id"],))
            status = cur.fetchone()["status"]
            _event(cur, r["project_id"], r["evidence_key"], status, status, actor, at, None, None, who)
    print(f"{len(rows)} unassigned open requests: {sum(done.values())} {'assigned' if apply else 'assignable'}")
    for who, n in sorted(done.items()):
        print(f"    -> {who:<34}{n}")
    for why, n in sorted(still.items()):
        print(f"    still unassigned ({n}): {why}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--submitted-by", action="append", default=[], help="select rows by submitter")
    ap.add_argument("--row-id", action="append", type=int, default=[], help="select a row by id")
    ap.add_argument("--actor", default="ops:convert_invented_evidence", help="recorded as archived_by / assigned_by / event actor")
    ap.add_argument("--apply", action="store_true", help="write (one transaction); default is a dry run")
    ap.add_argument("--reevaluate", action="store_true", help="after --apply, re-score affected projects")
    ap.add_argument("--assign-open", action="store_true",
                    help="assign unassigned open requests to accounts that can now take them")
    ap.add_argument("--mirror-sqlite", action="store_true",
                    help="copy PostgreSQL's evidence into the legacy SQLite fallback (no conversion needed)")
    args = ap.parse_args()
    conn = _connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.assign_open:
        _assign_open(cur, args.actor, args.apply)
        conn.commit() if args.apply else conn.rollback()
        if args.apply and args.mirror_sqlite:
            _mirror_sqlite(cur, args.actor)
        conn.close()
        return
    if args.mirror_sqlite and not args.submitted_by and not args.row_id:
        _mirror_sqlite(cur, args.actor)
        conn.close()
        return
    if not args.submitted_by and not args.row_id:
        sys.exit("select rows with --submitted-by and/or --row-id")
    selected, all_rows, owner, accounts = _load(cur, args.submitted_by, args.row_id)
    live = {k for g in GATE_REGISTRY for k in g.required_evidence}
    plan = plan_conversion(selected, all_rows, owner, accounts, live, RETIRED_EVIDENCE, resolve_assignee)
    _print_plan(plan, owner)

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
        conn.rollback()
        return
    try:
        touched = _apply(cur, plan, args.actor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print(f"\nApplied: {len(plan.dispositions)} rows archived, "
          f"{plan.count(REQUEST) + len(plan.new_requests)} open requests in place.")
    if args.reevaluate:
        try:
            _reevaluate(cur, touched)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"  re-evaluation skipped ({exc}); the next evaluation will replace the snapshots")
    if args.mirror_sqlite:
        _mirror_sqlite(cur, args.actor)
    conn.close()


if __name__ == "__main__":
    main()
