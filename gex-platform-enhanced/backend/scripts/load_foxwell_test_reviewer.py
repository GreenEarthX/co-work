"""
load_foxwell_test_reviewer.py — a TEST independent engineer for the calculation chain (JML, 18 Nov 2026).
=====================================================================================================
JML: "create an external client as an independent Engineer called Foxwell Survey UK,
user #1 senior engineer called Ewan Stewart". JML chose a TEST party (not a real client):

  tenant   foxwell_survey_uk         "TEST — Foxwell Survey UK", THIRD_PARTY, jurisdiction GB
  account  ewan_stewart_foxwellsurvey_com   ewan.stewart@foxwellsurvey.com, Senior Engineer,
           service_type ENGINEER, business_function ENGINEERING, ACTIVE

The account BYPASSES vetting, and its row says so: activated_by = 'TEST_FIXTURE_FOXWELL'
and the vetting_note. No telephone is invented (NULL). Its password is the project's demo
seed password (`app.core.auth.DEMO_PASSWORD`), never printed.

This script does NOT appoint the reviewer. Appointment is GEX staff's act through
POST /api/v1/projects/{id}/reviewers, on the written instruction of a named party
(reviewer_appointments.appoint); the owner may not instruct (OWNER_CANNOT_INSTRUCT).

Written as gex_user (ALEMBIC_DATABASE_URL): nothing in app/ creates tenants.

USAGE (both URLs exported, see .claude/CLAUDE.md)
    ./venv/bin/python scripts/load_foxwell_test_reviewer.py                 # dry run
    ./venv/bin/python scripts/load_foxwell_test_reviewer.py --execute
    ./venv/bin/python scripts/load_foxwell_test_reviewer.py --remove --execute

--remove deletes the account, its project roles, the company's project_access rows and the
tenant. Idempotent both ways.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MARKER = "TEST_FIXTURE_FOXWELL"
COMPANY = {"company_id": "foxwell_survey_uk", "company_name": "TEST — Foxwell Survey UK",
           "company_type": "THIRD_PARTY", "jurisdiction": "GB"}
USER = {"user_id": "ewan_stewart_foxwellsurvey_com", "email": "ewan.stewart@foxwellsurvey.com",
        "user_name": "Ewan Stewart", "service_type": "ENGINEER", "business_function": "ENGINEERING"}
NOTE = ("TEST fixture (JML 2026-11-18): a test independent engineer for the calculation-chain demonstration. "
        "Vetting BYPASSED: no telephone verification, no usage agreement. Not a real client or person.")


def _connect():
    import psycopg2
    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not dsn:
        sys.exit("Export ALEMBIC_DATABASE_URL first (gex_user).")
    return psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://"))


def load(cur) -> list[str]:
    from app.core.auth import DEMO_PASSWORD, pwd_context
    done = []
    cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) "
                "VALUES (%(company_id)s, %(company_name)s, %(company_type)s, %(jurisdiction)s) "
                "ON CONFLICT (company_id) DO NOTHING", COMPANY)
    done.append(f"tenant {COMPANY['company_id']}: {'created' if cur.rowcount else 'already there'}")
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
        "service_type, business_function, user_name, jurisdiction, kyc_status, is_active, account_state, "
        "registered_at, activated_at, activated_by, vetting_note) VALUES "
        "(%s,%s,%s,%s,%s,'THIRD_PARTY',%s,%s,%s,'GB','TEST',1,'ACTIVE',%s,%s,%s,%s) "
        "ON CONFLICT (user_id) DO NOTHING",
        (USER["user_id"], USER["email"], pwd_context.hash(DEMO_PASSWORD), COMPANY["company_id"],
         COMPANY["company_name"], USER["service_type"], USER["business_function"], USER["user_name"],
         now, now, MARKER, NOTE))
    done.append(f"account {USER['user_id']}: {'created ACTIVE (vetting bypassed)' if cur.rowcount else 'already there'}")
    return done


def remove(cur) -> list[str]:
    cur.execute("SELECT activated_by FROM auth_users WHERE user_id = %s", (USER["user_id"],))
    row = cur.fetchone()
    if row and row[0] != MARKER:
        sys.exit(f"{USER['user_id']} is not the fixture (activated_by={row[0]}); refusing to delete it.")
    cur.execute("DELETE FROM auth_user_project_roles WHERE user_id = %s", (USER["user_id"],))
    roles = cur.rowcount
    cur.execute("DELETE FROM project_access WHERE company_id = %s", (COMPANY["company_id"],))
    access = cur.rowcount
    cur.execute("DELETE FROM auth_users WHERE user_id = %s AND activated_by = %s", (USER["user_id"], MARKER))
    users = cur.rowcount
    cur.execute("DELETE FROM tenants WHERE company_id = %s", (COMPANY["company_id"],))
    return [f"removed: {users} account, {roles} project role(s), {access} project_access row(s), "
            f"{cur.rowcount} tenant"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SET app.current_company_id = 'PLATFORM_ADMIN'")
        lines = remove(cur) if args.remove else load(cur)
        if args.execute:
            conn.commit()
        else:
            conn.rollback()
            lines.append("DRY RUN — nothing written. Add --execute.")
        print("\n".join(lines))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
