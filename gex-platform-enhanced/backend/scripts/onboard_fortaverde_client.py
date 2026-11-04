#!/usr/bin/env python3
"""
onboard_fortaverde_client.py — Möhring Energie (FortaVerde, Pecém) as a real client.
===================================================================================
Steps 3 and 4 of `docs/FORTAVERDE_CLIENT_ONBOARDING.md`, reading
`scripts/fortaverde_client_accounts.json`. It stops there: vetting (claim,
telephone verification, usage agreement) and activation are done by GEX staff
through `/api/v1/account/{user_id}/…`, never by this script.

--tenant    INSERT the tenant row … ON CONFLICT (company_id) DO NOTHING.
            Nothing in app/ creates tenants, and without the row a project
            cannot be created (projects.owner_tenant_id is a foreign key).
            Written with ALEMBIC_DATABASE_URL (gex_user), the only step that is.

--register  Each user through the real registration handler
            (`routes_account_vetting.register`), so the account is PENDING and
            `account.registered` is written. Telephone is mandatory there; a
            missing number stops the script — it is never invented.

PASSWORDS: by default one is generated per user, passed to the handler and
discarded. It is never printed, logged or stored, and the owner sets a password
with `scripts/set_password.py <email>`.

--temporary-password  JML's decision, 2026-11-03: register both users with one
            temporary password chosen by GEX, which the users change. It is
            read with getpass (typed once, twice for confirmation: not echoed, not
            in shell history, not stored), checked against the password policy
            for each user, and an `account.temporary_password_set` event records
            that GEX chose it. A temporary password is still useless until GEX
            staff vet and activate the account.

USAGE
    set -a; source .env; set +a      # both URLs must be EXPORTED, see .claude/CLAUDE.md
    ./venv/bin/python scripts/onboard_fortaverde_client.py --tenant --register            # dry run
    ./venv/bin/python scripts/onboard_fortaverde_client.py --tenant --register --execute

Idempotent: an existing tenant row is left alone, and an address already
registered is reported, not retried.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.project_registry import company_slug  # noqa: E402

ACCOUNTS = Path(__file__).with_name("fortaverde_client_accounts.json")


def load() -> dict:
    data = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    t = data["tenant"]
    if company_slug(t["company_name"]) != t["company_id"]:
        sys.exit(f"REFUSING — company_slug({t['company_name']!r}) = "
                 f"{company_slug(t['company_name'])!r}, not {t['company_id']!r}. "
                 "Project ownership depends on that match.")
    for u in data["users"]:
        if u["company_name"] != t["company_name"]:
            sys.exit(f"REFUSING — {u['email']} names company {u['company_name']!r}, "
                     f"the tenant is {t['company_name']!r}.")
    return data


# ── Step 3: tenant ──────────────────────────────────────────────────────────

def tenant(t: dict, execute: bool) -> None:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not dsn:
        sys.exit("export ALEMBIC_DATABASE_URL (the gex_user credential) — the tenant row needs it")
    conn = psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://"))
    try:
        cur = conn.cursor()
        cur.execute("SELECT company_name, company_type, jurisdiction FROM tenants "
                    "WHERE company_id = %s", (t["company_id"],))
        row = cur.fetchone()
        print(f"\n[tenant] {t['company_id']}  {t['company_name']}  "
              f"{t['company_type']}  {t['jurisdiction']}")
        if row:
            print(f"  already present: {row[0]} / {row[1]} / {row[2]} — left unchanged")
            return
        if not execute:
            print("  would INSERT (DRY RUN — nothing written)")
            return
        cur.execute("""
            INSERT INTO tenants (company_id, company_name, company_type, jurisdiction)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (company_id) DO NOTHING
        """, (t["company_id"], t["company_name"], t["company_type"], t["jurisdiction"]))
        created = cur.rowcount == 1
        conn.commit()
        print("  created" if created else "  already present (concurrent insert) — left unchanged")
    finally:
        conn.close()


# ── Step 4: registration ────────────────────────────────────────────────────

def _throwaway_password(email: str, user_name: str) -> str:
    """Random, policy-checked, and never leaves this process."""
    from app.core.password_policy import PasswordPolicyError, validate_password

    for _ in range(5):
        candidate = secrets.token_urlsafe(32)
        try:
            validate_password(candidate, email=email, user_name=user_name)
            return candidate
        except PasswordPolicyError:
            continue
    sys.exit("could not generate a password the policy accepts — nothing registered")


def _temporary_password(users: list[dict]) -> str:
    """Typed by the GEX admin, never echoed; refused unless the policy accepts it for every user."""
    from app.core.password_policy import PasswordPolicyError, validate_password

    first = getpass.getpass("temporary password: ")
    if first != getpass.getpass("again: "):
        sys.exit("the two entries differ — nothing registered")
    for u in users:
        try:
            validate_password(first, email=u["email"], user_name=u["user_name"])
        except PasswordPolicyError as exc:
            sys.exit(f"refused for {u['email']}: {exc} — nothing registered")
    return first


def register(users: list[dict], execute: bool, temporary: bool = False) -> int:
    from app.core.auth import auth_db_connection

    missing = [u["email"] for u in users if not (u.get("telephone") or "").strip()]
    print(f"\n[register] {len(users)} user(s)")
    if missing:
        for e in missing:
            print(f"  STOP — no telephone for {e}. Registration requires one "
                  "(RegistrationRequest, min 6 characters); it is never invented.")
        print("  Fill users[].telephone in fortaverde_client_accounts.json. Nothing registered.")
        return 3

    conn = auth_db_connection()
    try:
        existing = {u["email"]: conn.execute(
            "SELECT user_id, account_state FROM auth_users WHERE email = ?",
            (u["email"].strip().lower(),)).fetchone() for u in users}
    finally:
        conn.close()

    if not execute:
        for u in users:
            row = existing[u["email"]]
            state = (f"already registered ({row['user_id']}, {row['account_state']})"
                     if row else "would register PENDING")
            print(f"  {u['email']:<42} {u['user_name']:<16} {state}")
        print("  DRY RUN — nothing written.")
        return 0

    from app.api.v1.routes_account_vetting import RegistrationRequest
    from app.api.v1.routes_account_vetting import register as register_route
    from app.core.event_store import append_event

    shared = _temporary_password(users) if temporary else None
    for u in users:
        if existing[u["email"]]:
            row = existing[u["email"]]
            print(f"  {u['email']:<42} already registered ({row['user_id']}, "
                  f"{row['account_state']}) — not retried")
            continue
        body = RegistrationRequest(
            email=u["email"], user_name=u["user_name"],
            password=shared or _throwaway_password(u["email"], u["user_name"]),
            company_name=u["company_name"], company_type=u["company_type"],
            business_function=u["business_function"], jurisdiction=u["jurisdiction"],
            telephone=u["telephone"],
        )
        resp = asyncio.run(register_route(body))
        del body
        if not resp.user_id:
            # The handler answers a duplicate with the same shape, minus user_id.
            print(f"  {u['email']:<42} already registered — not retried")
            continue
        print(f"  {resp.email:<42} {resp.user_id}  {resp.account_state}")
        if shared:
            append_event(
                event_type="account.temporary_password_set", aggregate_type="account",
                aggregate_id=resp.user_id,
                data={"chosen_by": "GEX", "decided_by": "Jean-Marie Lamay (JML), 2026-11-03",
                      "to_be_changed_by_owner": True},
                user_id="SCRIPT_onboard_fortaverde_client", correlation_id=f"ACCT-{resp.user_id[:8]}")
    if shared:
        print("  Temporary password set (chosen by GEX, JML 2026-11-03); recorded as "
              "account.temporary_password_set. The owners change it.")
    else:
        print("  Passwords were generated and discarded. Owners set theirs with "
              "scripts/set_password.py <email>.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", action="store_true", help="step 3: the tenant row")
    ap.add_argument("--register", action="store_true", help="step 4: register the users")
    ap.add_argument("--temporary-password", action="store_true",
                    help="register with one temporary password, typed at the prompt (JML 2026-11-03)")
    ap.add_argument("--execute", action="store_true", help="write (default is a dry run)")
    args = ap.parse_args()
    if not (args.tenant or args.register):
        ap.error("name a step: --tenant and/or --register")

    data = load()
    rc = 0
    if args.tenant:
        tenant(data["tenant"], args.execute)
    if args.register:
        rc = register(data["users"], args.execute, args.temporary_password)
    print("\nStops here. Vetting and activation are GEX staff's "
          "(docs/FORTAVERDE_CLIENT_ONBOARDING.md §5–6).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
