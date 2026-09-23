#!/usr/bin/env python
"""
Seeded accounts stop claiming VERIFIED KYC. Dry run by default.

    set -a && source .env && set +a
    venv/bin/python scripts/fix_seeded_kyc_status.py            # show the effect
    venv/bin/python scripts/fix_seeded_kyc_status.py --execute  # write

WHAT WAS WRONG
--------------
`auth_users.kyc_status` defaulted to 'VERIFIED' in the SQLite DDL and in the
seeder, so accounts created without an explicit value claimed a KYC check that
had never happened. Measured 2026-09-23: 19 of 20 rows said VERIFIED, about
evidence the database had never held — the KYC record itself lived in a browser
until migration 051 moved it.

PostgreSQL's column default was already 'UNVERIFIED' (migration 030); the code
paths are fixed in `app/core/auth.py`. This script corrects the rows that were
written before that.

WHY 'SEED' AND NOT 'UNVERIFIED'
-------------------------------
Both would be honest, and they say different things. UNVERIFIED is where a real
person sits between registering and being vetted — one row in this database is
genuinely there. SEED says nobody ever intended to vet this account, because it
is demo furniture from before the platform had a vetting flow. Collapsing the
two would lose the distinction exactly when someone asks "who is actually
waiting on us?".

It is worth saying plainly that 'SEED' is doing PROVENANCE duty inside a STATUS
column. The clean model is the one migration 051 uses for KYC profiles —
status and provenance as separate columns. Splitting `auth_users` that way is a
larger change; this records the truth in the column that exists today.

SCOPE, AND WHAT IS DELIBERATELY LEFT ALONE
------------------------------------------
Only rows with `activated_by = 'SEED_GRANDFATHERED'` — the marker the platform
already uses for accounts that predate vetting.

`MANUAL_ADMIN_GRANT` rows are NOT touched. An administrator took a deliberate
action on those, and rewriting what that action meant is a decision for a human,
not a cleanup script. They are listed on every run so the decision is not
forgotten.

THE CONSEQUENCE, STATED BEFORE IT HAPPENS
-----------------------------------------
One permission gates on this: `ecosystem.project_profile.project.edit` carries
`requires_kyc:VERIFIED`. Accounts moved to SEED lose it until they are actually
verified — which is now possible, through `POST /api/v1/kyc/verify/{user_id}`,
a GEX staff action that records who verified and when. The script prints how
many accounts are affected so that is a known outcome rather than a surprise
in someone's afternoon.
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, text

MARKER = "SEED_GRANDFATHERED"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    url = os.environ.get("ALEMBIC_DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("ALEMBIC_DATABASE_URL must be an explicit PostgreSQL URL")

    engine = create_engine(url)
    print(f"Postgres: {url.split('@')[-1]}")
    print(f"Mode    : {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    with engine.begin() as conn:
        conn.execute(text("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'"))

        rows = conn.execute(text(
            "SELECT user_id, email, is_platform_admin FROM auth_users "
            "WHERE kyc_status = 'VERIFIED' AND activated_by = :m ORDER BY user_id"
        ), {"m": MARKER}).fetchall()

        print(f"VERIFIED + {MARKER} — to become SEED: {len(rows)}")
        for user_id, email, admin in rows:
            print(f"   {user_id:34s} {email:34s} {'(platform admin)' if admin else ''}")

        others = conn.execute(text(
            "SELECT user_id, email, activated_by FROM auth_users "
            "WHERE kyc_status = 'VERIFIED' AND (activated_by IS NULL OR activated_by <> :m)"
        ), {"m": MARKER}).fetchall()
        if others:
            print(f"\nLEFT ALONE — VERIFIED but not seeded ({len(others)}). An admin acted "
                  "deliberately here; changing what that meant is a human decision:")
            for user_id, email, by in others:
                print(f"   {user_id:34s} {email:34s} activated_by={by}")

        affected = sum(1 for _, _, admin in rows if not admin)
        print(f"\nAccess effect: {affected} non-admin account(s) lose "
              "'ecosystem.project_profile.project.edit' (requires_kyc:VERIFIED).")
        print("Restore it per user with POST /api/v1/kyc/verify/{user_id} — GEX staff "
              "only, and it records who verified and when.")

        if args.execute:
            n = conn.execute(text(
                "UPDATE auth_users SET kyc_status = 'SEED', updated_at = now()::text "
                "WHERE kyc_status = 'VERIFIED' AND activated_by = :m"
            ), {"m": MARKER}).rowcount
            print(f"\nupdated {n} row(s) to kyc_status='SEED'")
        else:
            print("\nDry run. Re-run with --execute to write.")

        summary = conn.execute(text(
            "SELECT kyc_status, COUNT(*) FROM auth_users GROUP BY 1 ORDER BY 2 DESC")).fetchall()
        print(f"\nkyc_status now: {dict(summary)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
