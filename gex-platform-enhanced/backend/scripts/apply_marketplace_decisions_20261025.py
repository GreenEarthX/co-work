"""
JML's decisions of 2026-10-25 on the Marketplace records (handoff §8 item 48).

  1. Approve the five proposed spot prices (market_spot_price, market_spot_price_energy).
     "They will have to be modified anyway in the future" — a later value is a new
     registry row superseding this one; the approved row stays readable with as_of.
  2. Confirm every other Marketplace record moved on 2026-10-23 (sales details,
     production input lines, input classification): verification_state CONFIRMED,
     verified_by JML, verified_at now.

Proposer (MARKETPLACE_MOVE_20261023) and approver (JML) differ, as the registry
requires. Idempotent: an approved price or a confirmed record is skipped. Dry run
unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/apply_marketplace_decisions_20261025.py [--execute]

Needs migrations 066 and 067 and the 2026-10-23 load. A database rebuilt from
Alembic needs load_marketplace_unverified_20261023.py and then this; a pg_dump
restore already carries both.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402
from app.core.db_backend import market_connection, market_is_postgres, require_postgres  # noqa: E402

APPROVER = "jean-marie_greenearthx_com"
PROPOSER = "MARKETPLACE_MOVE_20261023"
DECIDED = "JML decision 2026-10-25: approve now; values will be revised later"
TABLES = ("project_sales_detail", "project_input_line", "input_classification")


def main(execute: bool) -> int:
    require_postgres(market_is_postgres(), "The Marketplace decisions", "MARKET_DB_BACKEND")
    conn = market_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held records
    try:
        pending = conn.execute(
            "SELECT ref_id, parameter_key, pathway FROM reference_parameter WHERE proposed_by = ? "
            "AND state = 'proposed' ORDER BY pathway", (PROPOSER,)).fetchall()
        for row in pending:
            reg.approve(conn, row["ref_id"], actor=APPROVER, reason=f"{row['parameter_key']} {row['pathway']}. {DECIDED}")
            print(f"1. approved {row['parameter_key']} {row['pathway']}")
        if not pending:
            print("1. no proposed spot price left: skipped")
        for table in TABLES:
            cur = conn.execute(
                f"UPDATE {table} SET verification_state = 'CONFIRMED', verified_by = ?, verified_at = now(), "
                f"updated_at = now() WHERE verification_state = 'UNVERIFIED'", (APPROVER,))
            print(f"2. {table}: {cur.rowcount} confirmed")
        if execute:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("dry run — nothing written; pass --execute")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
