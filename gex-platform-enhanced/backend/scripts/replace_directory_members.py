#!/usr/bin/env python
"""
Replace the directory's member list with the real GEX team.

WHY

The 19 members imported from Supabase on 2026-09-20 are seed data, confirmed by
Jim the same day. Two of them purported to be real people and got both the
surname and the address wrong ("Marwen Kadri <marwen@greenearthx.com>" for
Marwen Chaabouni; "Jean-Marie Dupont <jeanmarie@greenearthx.com>" for
Jean-Marie Lamay), and the `firstname.lastname@` convention is not GEX's. A
directory of invented colleagues is worse than an empty one: it offers
@mentions that reach nobody, and it made the anonymous Supabase exposure look
like a personal-data breach when it was largely fiction.

WHAT THIS TOUCHES

Members and their gate statuses only. Teams, roles and the permission gates
themselves are a structure rather than a roster, so they are left alone —
`--wipe-structure` removes them too, if that turns out to be seed as well.

Gate statuses are dropped with the members they belong to: a status row keyed
to a member id that no longer exists is a dangling reference, and keeping it
would let a future member id collide with someone else's clearances.

Nothing is destroyed irrecoverably: the seed rows remain in Supabase and in the
local export, so a bad run is re-runnable from those.

USAGE

    ./venv/bin/python scripts/replace_directory_members.py \\
        --member "Marwen Chaabouni <t-MarwenC@greenearthx.com>" \\
        --member "Mohamed Kedim <t-MohamedK@greenearthx.com>" \\
        --member "Jean-Marie Lamay <jean-marie@greenearthx.com>"

Team and role assignment is deliberately not guessed — pass
`--member "Name <email>|TEAM_ID|ROLE_ID"` when you know them, or set them later.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import directory_store  # noqa: E402
from app.core.config import settings  # noqa: E402

_MEMBER = re.compile(r"^\s*(?P<name>[^<]+?)\s*<(?P<email>[^>]+)>\s*$")


def _parse(spec: str) -> dict[str, str]:
    head, _, rest = spec.partition("|")
    m = _MEMBER.match(head)
    if not m:
        raise SystemExit(f"--member expects 'Full Name <email>', got {spec!r}")
    team, _, role = rest.partition("|")
    return {"full_name": m.group("name"), "email": m.group("email").strip(),
            "primary_team_id": team.strip(), "primary_role_id": role.strip()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--member", action="append", default=[], required=True,
                   metavar='"Full Name <email>[|TEAM|ROLE]"')
    p.add_argument("--wipe-structure", action="store_true",
                   help="also remove teams, roles and permission gates")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    members = [_parse(s) for s in args.member]
    directory_store.init_db()

    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        old = conn.execute("SELECT COUNT(*) FROM directory_members").fetchone()[0]
        old_status = conn.execute(
            "SELECT COUNT(*) FROM directory_gate_status").fetchone()[0]
        print(f"replacing {old} members ({old_status} gate statuses) "
              f"with {len(members)}:")
        for m in members:
            assigned = f"{m['primary_team_id'] or '—'}/{m['primary_role_id'] or '—'}"
            print(f"   {m['full_name']:<24} {m['email']:<34} team/role {assigned}")
        if args.wipe_structure:
            print("   …and removing teams, roles and permission gates")
        if args.dry_run:
            print("dry run — nothing written")
            return 0

        conn.execute("BEGIN")
        conn.execute("DELETE FROM directory_gate_status")
        conn.execute("DELETE FROM directory_members")
        if args.wipe_structure:
            conn.execute("DELETE FROM directory_roles")
            conn.execute("DELETE FROM directory_teams")
            conn.execute("DELETE FROM directory_gates")
        for m in members:
            conn.execute(
                "INSERT INTO directory_members (member_id, full_name, email, "
                "phone, organisation, status, primary_team_id, primary_role_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), m["full_name"], m["email"], "", "GreenEarthX",
                 "active", m["primary_team_id"], m["primary_role_id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    report = directory_store.reconcile_with_auth_users()
    print(f"\n{len(members)} members written")
    print(f"  with a platform account    : "
          f"{len(members) - len(report['members_without_account'])}")
    print(f"  without one                : {len(report['members_without_account'])}")
    if report["name_match_candidates"]:
        print("  same name, different address (reported, not linked):")
        for c in report["name_match_candidates"]:
            print(f"      {c['full_name']}: {c['directory_email']} ↔ {c['auth_email']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
