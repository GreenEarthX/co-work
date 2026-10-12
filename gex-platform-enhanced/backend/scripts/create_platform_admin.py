#!/usr/bin/env python
"""
Create a GEX platform-administrator account.

WHAT THIS GRANT ACTUALLY IS — read before running.

`is_platform_admin` is not "can see the internal directory". `request_tenant.py`
maps it to `PLATFORM_ADMIN`, which **disables tenant isolation for the whole
connection**: the holder reads every customer's data (measured: `projects`
returns 14 rows as PLATFORM_ADMIN against 3 as a tenant). It also makes the
holder GEX staff for account vetting — they can activate other people's
accounts — and lets them write reference data such as the fuel catalogue.

VETTING IS BYPASSED, AND THE ROW SAYS SO.

Normal accounts are created PENDING and activated only after phone
verification, a signed usage agreement, and separation of duties
(`app/core/account_lifecycle.py`). This script writes an ACTIVE account
directly, which is a deliberate one-off. It records
`activated_by='MANUAL_ADMIN_GRANT'` — **not** `SEED_GRANDFATHERED`, which is
reserved for the 17 rows that predate vetting and is how those are found. A
future audit can therefore tell a grandfathered row from a hand-granted one.

PASSWORDS ARE NOT HANDLED HERE.

The account is created with a random password that is generated, hashed and
discarded in the same breath — nobody, including this script's output, ever
sees it. The account exists and cannot be logged into until its owner sets a
password. They do that themselves:

    ./venv/bin/python -c "from app.core.auth import update_password; \\
        update_password('them@greenearthx.com', input('new password: '))"

USAGE

    ./venv/bin/python scripts/create_platform_admin.py \\
        --email marwen@greenearthx.com --name "Marwen Kadri"
"""
from __future__ import annotations

import argparse
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import auth_db_connection, pwd_context  # noqa: E402
from app.core.db_backend import auth_backend  # noqa: E402

GRANT_MARKER = "MANUAL_ADMIN_GRANT"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True, help="full name, e.g. \"Marwen Kadri\"")
    p.add_argument("--company-id", default="greenearthx")
    p.add_argument("--company-name", default="GreenEarthX")
    p.add_argument("--business-function", default="EXECUTIVE")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    email = args.email.strip().lower()
    user_id = email.replace("@", "_").replace(".", "_")
    now = datetime.now(timezone.utc).isoformat()

    # The store login reads (AUTH_DB_BACKEND). This used to open the SQLite
    # file directly, so after the PostgreSQL cutover it created an admin that
    # sign-in could never see.
    conn = auth_db_connection()
    try:
        existing = conn.execute(
            "SELECT user_id, is_platform_admin, account_state FROM auth_users WHERE email=?",
            (email,)).fetchone()
        if existing:
            print(f"REFUSING — an account already exists for {email}: "
                  f"user_id={existing['user_id']}, admin={existing['is_platform_admin']}, "
                  f"state={existing['account_state']}")
            print("Grant admin to an existing account deliberately, not by re-creating it.")
            return 2

        print(f"about to create ACTIVE platform admin:")
        print(f"  email    {email}")
        print(f"  user_id  {user_id}")
        print(f"  name     {args.name}")
        print(f"  company  {args.company_name} ({args.company_id})")
        print(f"  grants   cross-tenant visibility, account activation, reference-data writes")
        print(f"  store    {auth_backend()}")
        if args.dry_run:
            print("dry run — nothing written")
            return 0

        # Generated, hashed, discarded. The owner sets their own password.
        locked = pwd_context.hash(secrets.token_urlsafe(48))

        conn.execute(
            """
            INSERT INTO auth_users (
                user_id, email, password_hash, company_id, company_name,
                company_type, service_type, business_function, user_name,
                clearance_level, jurisdiction, kyc_status,
                is_platform_admin, is_active, account_state,
                activated_by, activated_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,1,'ACTIVE',?,?,?,?)
            """,
            (user_id, email, locked, args.company_id, args.company_name,
             "THIRD_PARTY", "PLATFORM", args.business_function, args.name,
             "CONFIDENTIAL", "EU", "VERIFIED", GRANT_MARKER, now, now, now))
        conn.commit()
    finally:
        conn.close()

    print(f"\ncreated {user_id} — ACTIVE, is_platform_admin=1, "
          f"activated_by={GRANT_MARKER}")
    print("The account CANNOT be logged into until its owner sets a password:")
    print(f"  ./venv/bin/python scripts/set_password.py {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
