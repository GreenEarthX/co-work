#!/usr/bin/env python
"""
Import the canvas portfolio from a Supabase export into the backend store.

Increment 2 of `docs/supabase-cutover-endpoints.md`.

WHY THIS ASKS YOU WHO OWNS WHAT

The Supabase `plants` table keys ownership on strings the browser supplied:
measured 2026-09-20, the 53 rows carry seven of them —

    admin-001 (21)   user-003 (11)   etfuels-thierry (6)
    b05dcc50-56da-442c-b845-658720ff3c9f (5)   demo-user (5)
    user-001 (3)     user-002 (2)

None is an `auth_users.user_id`. They came from a stubbed `AuthContext` that
returns a hard-coded `demo-user`, and from seed data before it. There is no
derivable mapping, and guessing one would hand a plant to the wrong account —
which is precisely the class of mistake this cutover exists to prevent.

So the mapping is an input, not an inference:

    ./venv/bin/python scripts/import_plants.py plants_export.json \\
        --map admin-001=admin_greenearthx_com \\
        --map etfuels-thierry=thierry_groell_etfuels_com \\
        --drop demo-user

`--map OLD=NEW` assigns every plant of OLD to account NEW, which must exist in
`auth_users`. `--drop OLD` discards those rows (demo and seed data). Any owner
id that is neither mapped nor dropped stops the import before it writes
anything — an unclaimed plant is a question, not a default.
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import plants_store  # noqa: E402
from app.core.config import settings  # noqa: E402


def _known_accounts() -> set[str]:
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    try:
        return {r[0] for r in conn.execute("SELECT user_id FROM auth_users")}
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="JSON array of plant rows")
    parser.add_argument("--map", action="append", default=[], metavar="OLD=NEW",
                        help="assign OLD owner's plants to account NEW")
    parser.add_argument("--drop", action="append", default=[], metavar="OLD",
                        help="discard this owner's plants (demo/seed data)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = json.loads(args.export.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("plants", [])

    mapping: dict[str, str] = {}
    for pair in args.map:
        old, _, new = pair.partition("=")
        if not old or not new:
            parser.error(f"--map expects OLD=NEW, got {pair!r}")
        mapping[old] = new
    dropped = set(args.drop)

    by_owner = collections.Counter(r.get("user_id") for r in rows)
    print(f"{len(rows)} plants, {len(by_owner)} owner ids in the export")

    unresolved = [o for o in by_owner if o not in mapping and o not in dropped]
    if unresolved:
        print("\nREFUSING TO IMPORT — these owner ids are neither mapped nor dropped:")
        for owner in sorted(unresolved, key=lambda o: -by_owner[o]):
            slugs = [r["slug"] for r in rows if r.get("user_id") == owner][:4]
            print(f"  {owner!r:<40} {by_owner[owner]:>3} plants  e.g. {', '.join(slugs)}")
        print("\nPass --map OLD=NEW for each, or --drop OLD to discard them.")
        return 2

    accounts = _known_accounts()
    unknown = {new for new in mapping.values() if accounts and new not in accounts}
    if unknown:
        print(f"\nREFUSING TO IMPORT — no such account(s): {sorted(unknown)}")
        print(f"Known accounts: {len(accounts)}")
        return 2

    plan: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        owner = r.get("user_id")
        if owner in dropped:
            continue
        plan[mapping[owner]].append(
            {"slug": r["slug"], "data": r.get("data") or {}})

    print("\nplan:")
    for old, new in sorted(mapping.items()):
        print(f"  {old:<40} → {new:<32} {by_owner.get(old, 0):>3} plants")
    for old in sorted(dropped):
        print(f"  {old:<40} → (dropped)                       {by_owner.get(old, 0):>3} plants")
    total = sum(len(v) for v in plan.values())
    print(f"  {total} plants into {len(plan)} accounts")

    if args.dry_run:
        print("\ndry run — nothing written")
        return 0

    plants_store.init_db()
    for owner, items in plan.items():
        existing = plants_store.count_for_owner(owner)
        if existing:
            print(f"  ! {owner} already holds {existing} plants — merging by slug")
        for item in items:
            plants_store.upsert_plant(owner, item["slug"], item["data"])
        print(f"  {owner}: {plants_store.count_for_owner(owner)} plants")

    print(f"\nimported into {settings.SQLITE_DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
