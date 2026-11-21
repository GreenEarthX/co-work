"""
Re-propose co2_feedstock_price DE (EUR 190/208/342 per t) for JML's own approval (19 Nov 2026).
================================================================================================
The row approved on 18 Nov (ref fd2aaca2-…) was proposed and approved in ONE script run, with
approved_by "JML (instruction in session, 2026-11-18; applied by Claude)". JML decided on 19 Nov:
re-propose the identical values; JML approves the new row on the reference registry screen with
his own account; its approval supersedes the 18 Nov row (the registry's lifecycle). The 18 Nov
row and its history stay as they are. This script proposes only; it can approve nothing.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/repropose_co2_for_jml_approval_20261119.py [--execute]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402
from scripts.propose_co2_feedstock_price_20261118 import PROPOSAL  # noqa: E402

PROPOSER = "CO2_PRICE_REPROPOSAL_20261119 (Claude, on JML's instruction of 19 Nov: approve on screen)"
NOTE_ADDED = (" Re-proposed 19 Nov 2026 with identical values so that JML approves it himself on the reference "
              "registry screen; the 18 Nov row was proposed and approved in one script run.")


def main(execute: bool) -> int:
    from app.core.db_backend import fuelref_connection
    conn = fuelref_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held reference data
    try:
        proposal = {**PROPOSAL, "note": PROPOSAL["note"] + NOTE_ADDED, "valid_from": "2026-11-19"}
        reg.validate_proposal(proposal)
        existing = conn.execute("SELECT ref_id, state FROM reference_parameter WHERE parameter_key = ? AND "
                                "region = ? AND proposed_by = ?", ("co2_feedstock_price", "DE", PROPOSER)).fetchone()
        if existing:
            print(f"already proposed: {existing['ref_id']} ({existing['state']})")
            return 0
        if not execute:
            print("DRY RUN — valid; nothing written. Add --execute.")
            return 0
        row = reg.propose(conn, proposal, actor=PROPOSER)
        conn.commit()
        print(f"proposed {row['ref_id']}: co2_feedstock_price DE {row['value_low']}/{row['value_base']}/"
              f"{row['value_high']} {row['unit']} — awaiting JML's approval on screen")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
