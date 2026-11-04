#!/usr/bin/env python
"""
Two DEMO sign-ins for the FortaVerde Pecém TEST project, under the names of
FortaVerde's two contacts (JML, 2026-11-03).

WHAT THEY ARE
  "Sascha Möhring (demo)" and "Jan Block (demo)": ACTIVE EXECUTIVE accounts in
  the fixture tenant (test_fortaverde), so the Pecém TEST project can be shown
  and captured from the producer's own seat. The people's real accounts are a
  different thing (tenant mohring_energie, PENDING until GEX vets them) and this
  script never reads or touches them. Addresses are on the reserved .test domain
  and every name ends in "(demo)", so nobody mistakes one for the other.

WHAT IS BYPASSED, AND THE ROW SAYS SO
  * Vetting: no telephone verification, no usage agreement.
    activated_by = DEMO_FORTAVERDE_NAMED; the phone and agreement columns stay empty.
  * The 12 October rule "no real names in the fixture": JML decided on
    3 November to use the contacts' names for these two demo sign-ins.
  The vetting_note starts with the fixture marker, so the fixture's own
  --remove (and its --execute, which removes first) deletes these two as well.

WHAT IS NOT BYPASSED
  The password policy. One demo password for both, typed at a getpass prompt,
  checked by app.core.password_policy for each account (12+ characters, no part
  of the name or address, so demo1234 is refused), never printed, stored or logged.

USAGE (from backend/, with ALEMBIC_DATABASE_URL exported: this writes data)
    ./venv/bin/python scripts/create_fortaverde_demo_accounts.py                    # dry run
    ./venv/bin/python scripts/create_fortaverde_demo_accounts.py --execute          # asks for the password
    ./venv/bin/python scripts/create_fortaverde_demo_accounts.py --remove --execute
Re-running --execute replaces the two rows and asks for the password again.
After load_fortaverde_test_project.py --execute, run this again.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

ACTIVATED_BY = "DEMO_FORTAVERDE_NAMED"
DECIDED = "JML, 2026-11-03"

# (user_id, email, user_name, business_function, contact_id, title)
DEMO_ACCOUNTS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("usr_demo_fv_moehring", "sascha.moehring@fortaverde.test", "Sascha Möhring (demo)",
     "EXECUTIVE", "P1", "Managing Director and CTO"),
    ("usr_demo_fv_block", "jan.block@fortaverde.test", "Jan Block (demo)",
     "EXECUTIVE", "P2", "CEO"),
)


def vetting_note(marker: str, contact_id: str, title: str) -> str:
    return (f"{marker}: DEMO sign-in under the name of FortaVerde contact {contact_id} ({title}), "
            f"decided by {DECIDED}. VETTING BYPASSED: no telephone verification, no usage agreement. "
            "Not the person's own account; theirs is in tenant mohring_energie. Remove with "
            "scripts/create_fortaverde_demo_accounts.py --remove --execute, or the fixture's --remove.")


def conflicts(rows: list[tuple[str, str, str]], tenant_id: str, marker: str) -> list[str]:
    """Rows already holding one of our ids or addresses that this script did not write.

    rows: (user_id, company_id, vetting_note) for every auth_users row matching our
    user ids or emails. Ours = one of our ids, in the fixture tenant, marker-noted."""
    ours = {a[0] for a in DEMO_ACCOUNTS}
    out = []
    for user_id, company_id, note in rows:
        if user_id not in ours or company_id != tenant_id or not (note or "").startswith(marker):
            out.append(f"{user_id} (tenant {company_id})")
    return out


def _read_password(accounts) -> str:
    from app.core.password_policy import PasswordPolicyError, validate_password

    print("\n  One demo password for both accounts. Not echoed; at least 12 characters, and no part")
    print("  of the names or addresses (sascha, moehring, jan, block, demo, fortaverde, test).")
    first = getpass.getpass("  Demo password: ")
    if first != getpass.getpass("  Again: "):
        sys.exit("  The two entries differ. Nothing changed.")
    for _uid, email, name, *_ in accounts:
        try:
            validate_password(first, email=email, user_name=name, is_platform_admin=False)
        except PasswordPolicyError as exc:
            sys.exit(f"  Refused by the password policy for {email}: {exc}. Nothing changed.")
    return first


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--remove", action="store_true", help="delete the two demo accounts")
    args = ap.parse_args()

    # The platform's `app` FIRST. Loading the knowledge record runs its validator,
    # which puts gex_pf_engine/backend at the front of sys.path; an `import app`
    # after that finds the PF engine's alias guard and stops (2026-11-03).
    from app.core.auth import pwd_context
    from app.core import password_policy  # noqa: F401  (bound now; used in _read_password)

    import load_fortaverde_test_project as fx

    k = fx.Knowledge.load(fx.DEFAULT_KNOWLEDGE)
    ids = [a[0] for a in DEMO_ACCOUNTS]
    emails = [a[1] for a in DEMO_ACCOUNTS]
    print(f"\n  fixture: {k.project_id} in tenant {k.tenant_id} ({k.tenant_name})")

    conn = fx.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM projects WHERE project_id = %s AND owner_tenant_id = %s",
                    (k.project_id, k.tenant_id))
        if not cur.fetchone():
            sys.exit("  refusing: the FortaVerde TEST fixture is not loaded. Run "
                     "scripts/load_fortaverde_test_project.py --execute first. Nothing changed.")
        cur.execute("SELECT user_id, company_id, COALESCE(vetting_note, '') FROM auth_users "
                    "WHERE user_id = ANY(%s) OR lower(email) = ANY(%s)", (ids, emails))
        rows = [tuple(r) for r in cur.fetchall()]
        clash = conflicts(rows, k.tenant_id, k.marker)
        if clash:
            sys.exit(f"  refusing: these accounts hold our ids or addresses and were not written "
                     f"by this script: {', '.join(clash)}. Nothing changed.")

        if args.remove:
            print(f"  {'delete' if args.execute else 'would delete'} {len(rows)} demo account(s)")
            if args.execute:
                cur.execute("DELETE FROM auth_users WHERE user_id = ANY(%s) AND company_id = %s "
                            "AND vetting_note LIKE %s", (ids, k.tenant_id, k.marker + "%"))
                conn.commit()
                print(f"  DELETED {cur.rowcount}.")
            else:
                print("\n  DRY RUN — nothing deleted. Re-run with --execute.")
            return 0

        for user_id, email, name, function, cid, title in DEMO_ACCOUNTS:
            print(f"  {'write' if args.execute else 'would write'} {user_id} <{email}> {name}, "
                  f"{function}, ACTIVE (activated_by={ACTIVATED_BY}, vetting bypassed)")
        if rows:
            print(f"  ({len(rows)} existing demo row(s) replaced)")
        if not args.execute:
            print("\n  DRY RUN — nothing written. Re-run with --execute.")
            return 0

        password = _read_password(DEMO_ACCOUNTS)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur.execute("DELETE FROM auth_users WHERE user_id = ANY(%s) AND company_id = %s "
                    "AND vetting_note LIKE %s", (ids, k.tenant_id, k.marker + "%"))
        for user_id, email, name, function, cid, title in DEMO_ACCOUNTS:
            cur.execute("""
                INSERT INTO auth_users (
                    user_id, email, password_hash, company_id, company_name, company_type,
                    business_function, user_name, jurisdiction, clearance_level, kyc_status,
                    is_platform_admin, is_active, account_state, registered_at,
                    activated_by, activated_at, vetting_note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'STANDARD','UNVERIFIED',0,1,'ACTIVE',%s,%s,%s,%s)
            """, (user_id, email, pwd_context.hash(password), k.tenant_id, k.tenant_name,
                  k.tenant_type, function, name, k.tenant_jurisdiction, now, ACTIVATED_BY, now,
                  vetting_note(k.marker, cid, title)))
        conn.commit()
        del password
        print(f"\n  WROTE {len(DEMO_ACCOUNTS)} ACTIVE demo accounts: {', '.join(emails)}.")
        print("  On the login page they are under 'FortaVerde Pecém (TEST)'; type the demo password yourself.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
