"""
JML's reference decisions of 2026-10-19, applied through the registry's own lifecycle.

  1. EU Hydrogen Bank premium: base 0.40 (midpoint) -> 0.20 (lowest winning bid).
     Conservative lender case: winners that bid premiums too low have struggled to
     proceed, so a model must not count on more than the floor. A NEW row supersedes
     the seed row; the 0.40 row stays readable with as_of.
  2. Debt gearing 60/65/70%: approve the seed row as it stands, OIES ET21 cited.

Proposer is the review-session marker, approver is JML, so the two differ.
Idempotent: a decision already applied is skipped. Dry run unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/apply_reference_decisions_20261019.py [--execute]

A database rebuilt from Alembic needs this run after 061; a pg_dump restore
already carries its result.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402
from app.core.db_backend import fuelref_connection  # noqa: E402

PROPOSER = "REVIEW_SESSION_20261019"
APPROVER = "jean-marie_greenearthx_com"
DECIDED = "JML decision 2026-10-19 (review session)"


def main(execute: bool) -> int:
    if not reg.registry_available():
        print("FUELREF_DB_BACKEND is not postgres: nothing to do")
        return 1
    # Curating reference data is a PLATFORM_ADMIN write by policy (061).
    conn = fuelref_connection(company_id="PLATFORM_ADMIN")
    try:
        ehb = reg.in_force(conn, "ehb_premium", "H2", "EU", as_of="2026-10-20")
        if ehb and ehb["value_base"] == 0.20:
            print("1. ehb_premium base 0.20 already in force: skipped")
        else:
            new = reg.propose(conn, {
                "parameter_key": "ehb_premium", "pathway": "H2", "region": "EU",
                "value_low": 0.20, "value_base": 0.20, "value_high": 0.60,
                "unit": "EUR/kg", "currency": "EUR", "price_base_date": ehb["price_base_date"],
                "source_class": ehb["source_class"], "source_name": ehb["source_name"],
                "source_url": ehb["source_url"], "retrieved_at": ehb["retrieved_at"],
                "valid_from": "2026-10-20",
                "note": ("Fixed premium, round 2 general topic; winners bid 0.20-0.60, "
                         "0.60 being the highest accepted (clearing). Base = 0.20, the "
                         "lowest winning bid: conservative lender case, because premiums "
                         "bid too low have left winners unable to proceed. Supersedes "
                         f"the 0.40 midpoint. {DECIDED}."),
            }, actor=PROPOSER)
            out = reg.approve(conn, new["ref_id"], actor=APPROVER,
                              reason=f"ehb_premium base 0.40 -> 0.20. {DECIDED}")
            print(f"1. ehb_premium 0.20 approved as {new['ref_id']}, "
                  f"version {out['version']['version_number']}")

        gearing = conn.execute(
            "SELECT * FROM reference_parameter WHERE parameter_key = 'debt_gearing' "
            "AND pathway = 'ANY' AND region = 'ANY' AND proposed_by = 'MIGRATION_061'"
        ).fetchone()
        if gearing["state"] != "proposed":
            print(f"2. debt_gearing is already {gearing['state']}: skipped")
        else:
            out = reg.approve(conn, gearing["ref_id"], actor=APPROVER,
                              reason=f"debt_gearing 0.65 approved, OIES ET21 kept as "
                                     f"source (not yet located). {DECIDED}")
            print(f"2. debt_gearing approved, version {out['version']['version_number']}")

        if execute:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("dry run: rolled back (pass --execute to commit)")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv[1:]))
