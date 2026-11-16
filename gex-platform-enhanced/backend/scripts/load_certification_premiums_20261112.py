"""
Propose the certification premiums to the reference registry, INDICATIVE (2026-11-12).

Source: scripts/data/certification_premiums_20261112.json — the 13 values that
`greenmesh_engine.CertificationPremium` held in code, copied verbatim before that module
was retired (GreenMesh Phase 1, Step 1, G-12). Its docstring cites "BNEF H2 Green Premium
Survey 2024, ICIS GoO market data 2025" without saying which figure came from which, and
neither has been checked. So every row is `proposed` (never in force until someone confirms
its source and approves it), source class `gex_assumption`, and its note starts INDICATIVE.

  reference_parameter    13 rows, proposed, keys certification_premium_<regime>

Nothing reads these keys yet. Idempotent: rows already present are skipped. Dry run unless
--execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/load_certification_premiums_20261112.py [--execute]

Needs migration 061. A database rebuilt from Alembic needs this run; a pg_dump restore
already carries its rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "certification_premiums_20261112.json"
PROPOSER = "CERT_PREMIUM_PORT_20261112"
SOURCE_NAME = ("Cited in greenmesh_engine.py v5.1 (retired 2026-11-12): BNEF H2 Green Premium "
               "Survey 2024; ICIS GoO market data 2025. Which figure comes from which is not "
               "recorded; not checked against either publication")
DATE = "2026-11-12"

KEY_OF = {"RFNBO": "certification_premium_rfnbo", "RED_III": "certification_premium_red_iii",
          "45V": "certification_premium_45v", "CertifHy": "certification_premium_certifhy",
          "CORSIA": "certification_premium_corsia"}
REGION_OF = {"RFNBO": "EU", "RED_III": "EU", "CertifHy": "EU", "45V": "US", "CORSIA": "ANY"}

NOTE = ("INDICATIVE, not verified: approve only once the source of this value is confirmed. "
        "Additional to the base commodity price. Region set from the regime's jurisdiction, "
        "not from the source.")
NOTE_45V = (" The source comment reads 'via PTC, effective premium'. EUR 300/t is EUR 0.30/kg, "
            "about a tenth of the 45V top tier recorded as subsidy_45v_max (USD 3.28/kg): "
            "check the basis before approving.")


def proposals(data: dict) -> list[dict]:
    out = []
    for p in data["premiums_eur_t"]:
        regime = p["regime"]
        out.append({
            "parameter_key": KEY_OF[regime], "pathway": p["molecule"], "region": REGION_OF[regime],
            "value_base": float(p["value"]), "unit": "EUR/t", "currency": "EUR",
            "price_base_date": DATE, "source_class": "gex_assumption", "source_name": SOURCE_NAME,
            "retrieved_at": DATE, "valid_from": DATE,
            "note": NOTE + (NOTE_45V if regime == "45V" else ""),
        })
    return out


def load(conn, data: dict) -> tuple[int, int]:
    """Propose what is missing. Returns (inserted, skipped)."""
    inserted = skipped = 0
    for p in proposals(data):
        exists = conn.execute(
            "SELECT 1 FROM reference_parameter WHERE parameter_key = ? AND pathway = ? "
            "AND region = ? AND proposed_by = ?",
            (p["parameter_key"], p["pathway"], p["region"], PROPOSER)).fetchone()
        if exists:
            skipped += 1
        else:
            reg.propose(conn, p, actor=PROPOSER)
            inserted += 1
    return inserted, skipped


def main(execute: bool) -> int:
    from app.core.db_backend import require_postgres

    require_postgres(reg.registry_available(), "The reference registry", "FUELREF_DB_BACKEND")
    from app.core.db_backend import fuelref_connection

    conn = fuelref_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held reference data
    try:
        ins, skip = load(conn, json.loads(DATA.read_text()))
        print(f"reference_parameter (proposed)  {ins:3} to insert, {skip:3} already present")
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
