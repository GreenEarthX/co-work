#!/usr/bin/env python
"""
Why does this login fail? Answers it with the backend's own functions.

    ./venv/bin/python scripts/check_login.py you@greenearthx.com

Reports which store login reads, whether the account is there, its state and
admin flag, and — after asking for the password with getpass (not echoed, not
stored, not printed) — whether that password matches. Writes nothing.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import _load_user_by_email, verify_password  # noqa: E402
from app.core.db_backend import auth_backend  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    email = sys.argv[1].strip().lower()
    print(f"  store login reads : {auth_backend()}")

    user = _load_user_by_email(email)
    if not user:
        print(f"  account           : NOT FOUND for {email}")
        print("  -> create it with scripts/create_platform_admin.py (store must say postgres),")
        print("     then set its password with scripts/set_password.py")
        return 1

    keys = user.keys()
    state = user["account_state"] if "account_state" in keys else "?"
    print(f"  account           : found ({user['user_id']})")
    print(f"  account_state     : {state}   is_active: {user['is_active']}   "
          f"platform admin: {bool(user['is_platform_admin'])}")

    pw = getpass.getpass("  password to test (not shown): ")
    if verify_password(pw, user["password_hash"]):
        print("  password          : MATCHES")
        if state != "ACTIVE" or not user["is_active"]:
            print("  -> login will be refused with 403 because the account is not ACTIVE")
        else:
            print("  -> credentials are fine; if the website still says 401, it is calling a")
            print("     different backend than this one (check the frontend proxy / port 8000)")
    else:
        print("  password          : DOES NOT MATCH")
        print("  -> set it again with scripts/set_password.py " + email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
