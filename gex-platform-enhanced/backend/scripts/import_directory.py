#!/usr/bin/env python
"""
Import the staff directory from a Supabase export into the backend store.

Increment 1 of `docs/supabase-cutover-endpoints.md`. The five tables behind the
Team screen live in Supabase, readable by anyone with the bundled anon key.
This moves the rows behind the backend; revoking the key is a later increment.

USAGE

    ./venv/bin/python scripts/import_directory.py directory_export.json
    ./venv/bin/python scripts/import_directory.py directory_export.json --dry-run

The export is one JSON object holding the five PostgREST result sets verbatim:

    {"teams": [...], "roles": [...], "team_users": [...],
     "permission_gates": [...], "user_gate_status": [...]}

The file contains personal data — 19 people's email and phone. Keep it out of
the repository and delete it once the import is verified.

After importing, this prints the reconciliation against `auth_users`: who is in
the directory with no account, and who has an account with no directory row.
That difference is the cost of folding the two identity stores into one, which
is the decision recorded as open in §2 of the same document.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import directory_store  # noqa: E402


def _str(row: dict, key: str, default: str = "") -> str:
    value = row.get(key)
    return default if value is None else str(value)


def _opt(row: dict, key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="JSON export of the five tables")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the counts and write nothing")
    args = parser.parse_args()

    payload = json.loads(args.export.read_text(encoding="utf-8"))
    teams = payload.get("teams", [])
    roles = payload.get("roles", [])
    members = payload.get("team_users", [])
    gates = payload.get("permission_gates", [])
    statuses = payload.get("user_gate_status", [])

    print(f"teams {len(teams)} · roles {len(roles)} · members {len(members)} · "
          f"gates {len(gates)} · gate statuses {len(statuses)}")
    if args.dry_run:
        print("dry run — nothing written")
        return 0

    directory_store.init_db()

    for row in teams:
        directory_store.upsert_team(
            team_id=_str(row, "id"), name=_str(row, "name"),
            description=_str(row, "description"),
            primary_modules=_str(row, "primary_modules"))

    for row in roles:
        directory_store.upsert_role(
            role_id=_str(row, "id"), role_code=_str(row, "role_code"),
            role_name=_str(row, "role_name"),
            permission_tier=_str(row, "permission_tier"),
            is_default_admin=bool(row.get("is_default_admin")),
            team_id=_str(row, "team_id"))

    for row in members:
        directory_store.upsert_member(
            member_id=_str(row, "id"), full_name=_str(row, "full_name"),
            email=_str(row, "email"), phone=_str(row, "phone"),
            organisation=_opt(row, "organisation"),
            status=_str(row, "status", "ACTIVE"),
            primary_team_id=_str(row, "primary_team_id"),
            primary_role_id=_str(row, "primary_role_id"),
            secondary_team_id=_opt(row, "secondary_team_id"),
            secondary_role_id=_opt(row, "secondary_role_id"))

    for row in gates:
        directory_store.upsert_gate(
            gate_id=_str(row, "id"), gate_name=_str(row, "gate_name"),
            trigger_description=_str(row, "trigger_description"))

    for row in statuses:
        directory_store.set_gate_status(
            member_id=_str(row, "user_id"), gate_id=_str(row, "gate_id"),
            status=_str(row, "status"))

    print(f"imported into {directory_store.settings.SQLITE_DB_PATH}")

    report = directory_store.reconcile_with_auth_users()
    no_account = report["members_without_account"]
    no_entry = report["accounts_without_directory_entry"]
    candidates = report["name_match_candidates"]
    print("\nreconciliation against auth_users:")
    print(f"  directory members with no account : {len(no_account)}")
    print(f"  accounts with no directory entry  : {len(no_entry)}")
    print(f"  same name, different address      : {len(candidates)} "
          f"(reported, NOT linked)")
    for c in candidates:
        print(f"      {c['full_name']}: {c['directory_email']} "
              f"↔ {c['auth_email']} ({c['auth_user_id']})")
    print("\nThat gap is what folding the two identity stores would cost "
          "(docs/supabase-cutover-endpoints.md §2). Name candidates need a "
          "human: two people can share a name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
