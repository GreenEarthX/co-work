#!/usr/bin/env python
"""
Set an account's password, typed by the person it belongs to.

    ./venv/bin/python scripts/set_password.py t-marwenc@greenearthx.com

The password is read with `getpass`, so it is not echoed to the screen, does
not land in shell history, and does not appear in any transcript. It is asked
for twice and compared. `app.core.password_policy` is enforced by
`update_password`, and a platform administrator faces the longer minimum
because that flag grants cross-tenant visibility.

Whoever owns the account should run this themselves. An operator who sets
somebody else's password knows it, and from then on the audit trail cannot
distinguish the two of them.
"""
from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import update_password  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.password_policy import (  # noqa: E402
    PasswordPolicyError,
    describe_policy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    args = parser.parse_args()
    email = args.email.strip().lower()

    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT user_name, is_platform_admin, account_state FROM auth_users "
            "WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()

    if row is None:
        print(f"No account for {email}.")
        return 2

    is_admin = bool(row["is_platform_admin"])
    policy = describe_policy(is_platform_admin=is_admin)
    print(f"Setting the password for {row['user_name']} <{email}>"
          f"{' — platform administrator' if is_admin else ''}")
    print(f"  at least {policy['min_length']} characters. {policy['note']}")

    first = getpass.getpass("new password: ")
    second = getpass.getpass("again: ")
    if first != second:
        print("They do not match. Nothing changed.")
        return 1

    try:
        update_password(email, first)
    except PasswordPolicyError as exc:
        print(f"Refused: {exc}")
        return 1

    print("Password set.")
    if row["account_state"] != "ACTIVE":
        print(f"Note: the account is {row['account_state']}, so login is still "
              "refused until it is activated — the password is not the gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
