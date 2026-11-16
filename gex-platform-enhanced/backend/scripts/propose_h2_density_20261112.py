"""
Propose the hydrogen density used to convert a meter's Nm3 to kg (gap G-22, GreenMesh Phase 2
Step 1; JML decision D8, 2026-11-12).

Writes ONE `reference_parameter` row, state `proposed`, key `h2_density_normal_0c_101325pa`.
A proposed row is in force for nothing: app/core/ot_boundary.py refuses Nm3 readings until a
second person confirms the value and APPROVES it through the registry lifecycle.

The value, 0.08988 kg/m3, is the commonly cited density of hydrogen gas at 0 °C and
101.325 kPa. It was written here from general knowledge and NOT read from the source on
2026-11-12: confirm it against the NIST Chemistry WebBook before approving. Also confirm that
the client's meters report Nm3 at DIN 1343 normal conditions (0 °C, 101.325 kPa); a meter
reporting ISO 13443 "standard" m3 (15 °C) needs a different key, not this value.

valid_from is 2020-01-01 because a physical property does not start on the day it is
recorded; readings from before the approval date can then be converted once it is approved.

Idempotent: skips when a row from this proposer exists. Dry run unless --execute.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402

PROPOSER = "G22_DENSITY_PROPOSAL_20261112"
PROPOSAL = {
    "parameter_key": "h2_density_normal_0c_101325pa", "pathway": "H2", "region": "ANY",
    "value_base": 0.08988, "unit": "kg/m3", "source_class": "public_source",
    "source_name": "NIST Chemistry WebBook, SRD 69, Thermophysical Properties of Fluid Systems: "
                   "hydrogen at 273.15 K and 0.101325 MPa",
    "source_url": "https://webbook.nist.gov/chemistry/fluid/",
    "retrieved_at": "2026-11-12", "valid_from": "2020-01-01",
    "note": ("PROPOSED, NOT CHECKED: value written from general knowledge, not read from the "
             "WebBook. Confirm the value there and confirm the meters report Nm3 at 0 °C and "
             "101.325 kPa (DIN 1343) before approving. Not valid for 15 °C 'standard' m3."),
}


def load(conn) -> bool:
    exists = conn.execute("SELECT 1 FROM reference_parameter WHERE parameter_key = ? AND proposed_by = ?",
                          (PROPOSAL["parameter_key"], PROPOSER)).fetchone()
    if exists:
        return False
    reg.propose(conn, PROPOSAL, actor=PROPOSER)
    return True


def main(execute: bool) -> int:
    from app.core.db_backend import fuelref_connection, require_postgres

    require_postgres(reg.registry_available(), "The reference registry", "FUELREF_DB_BACKEND")
    conn = fuelref_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held reference data
    try:
        inserted = load(conn)
        print(f"reference_parameter (proposed)  {'1 to insert' if inserted else 'already present'}")
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
