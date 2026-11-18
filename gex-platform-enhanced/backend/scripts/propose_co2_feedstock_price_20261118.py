"""
Propose the purchased CO2 feedstock price to the reference registry (JML, 2026-11-18).
=====================================================================================
HamburgOne buys North Sea e-Methanol's CO2 shortfall (11,875 t/yr: capture 50 kt vs 61,875 t
needed). JML asked for a quick price review, the value to live in PostgreSQL. It is written
`proposed`: nothing reads it as in force until JML approves it (the registry's lifecycle).

Value (EUR/t, Germany, merchant liquid CO2):
  base 208  = IMARC "Liquid Carbon Dioxide" Germany, Q3 2026 (Sep): USD 225/t, x the approved
              registry rate tea_fx_usd_to_eur 0.924
  low  190  = IMARC Germany, lowest quarter Q1 2025-Q3 2026: USD 206/t (Sep 2025) x 0.924
  high 342  = Expert Market Research "Carbon Dioxide" Germany, Q1 2026: USD 370/t x 0.924
Neither source states grade or delivery terms (delivered vs ex-works), and they disagree
(Q1 2026: 208 vs 370). Not a supplier quote. Not checked for RFNBO eligibility of the CO2's
origin (fossil vs biogenic) — that decides whether the product can count as RFNBO.
For comparison, NOT this key: biogenic by-product CO2 capture cost, Northern Europe EUR 28/t,
and DAC EUR 123/t (Roland Berger for GasTerra, "Feasibility and potential of e-methane", appendix,
April 2025) — capture costs, before liquefaction and transport.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/propose_co2_feedstock_price_20261118.py [--approve] [--execute]

--approve applies JML's decision of 18 Nov 2026 ("approve the CO2 price at 208 EUR/t", given in the
Claude Code session) through the registry lifecycle: the approver is recorded as JML, never the proposer.
Idempotent. A database rebuilt from Alembic needs this run; a pg_dump restore carries the row.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402

PROPOSER = "CO2_PRICE_REVIEW_20261118"
APPROVER = "JML (instruction in session, 2026-11-18; applied by Claude)"
APPROVAL_REASON = "JML approved co2_feedstock_price DE at EUR 208/t for North Sea's purchased CO2 shortfall"
PROPOSAL = {
    "parameter_key": "co2_feedstock_price", "pathway": "ANY", "region": "DE",
    "value_low": 190.0, "value_base": 208.0, "value_high": 342.0, "unit": "EUR/t", "currency": "EUR",
    "price_base_date": "2026-09-30", "source_class": "public_source",
    "source_name": "IMARC Group, Liquid Carbon Dioxide pricing report, Germany Q3 2026 (USD 225/t; updated "
                   "2026-10-28); high end Expert Market Research, Carbon Dioxide price trends, Germany Q1 2026 "
                   "(USD 370/t; updated 2026-09-08); converted at the approved tea_fx_usd_to_eur 0.924",
    "source_url": "https://imarcgroup.com/liquid-carbon-dioxide-pricing-report",
    "retrieved_at": "2026-11-18", "valid_from": "2026-11-18",
    "note": ("Quick review for JML, 18 Nov 2026: market-research indices, not supplier quotes; grade and "
             "delivery terms not stated by either source; the two disagree. Origin (fossil or biogenic) not "
             "stated: it decides RFNBO eligibility of the methanol made from it. Replace with a supplier quote "
             "before FID. Biogenic by-product capture cost (N. Europe EUR 28/t, Roland Berger for GasTerra, "
             "Apr 2025) is a capture cost, not a delivered price."),
}


def main(execute: bool, approve: bool = False) -> int:
    from app.core.db_backend import fuelref_connection
    conn = fuelref_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held reference data
    try:
        reg.validate_proposal(PROPOSAL)
        existing = conn.execute("SELECT ref_id, state FROM reference_parameter WHERE parameter_key = ? AND "
                                "region = ? AND proposed_by = ?", ("co2_feedstock_price", "DE", PROPOSER)).fetchone()
        if not execute:
            print(("already proposed: " + existing["ref_id"] + f" ({existing['state']})") if existing
                  else "DRY RUN — valid; nothing written. Add --execute.")
            return 0
        if existing:
            ref_id, state = existing["ref_id"], existing["state"]
            print(f"already proposed: {ref_id} ({state})")
        else:
            row = reg.propose(conn, PROPOSAL, actor=PROPOSER)
            ref_id, state = row["ref_id"], row["state"]
            print(f"proposed {ref_id}: co2_feedstock_price DE {row['value_low']}/{row['value_base']}/"
                  f"{row['value_high']} {row['unit']}")
        if approve and state == "proposed":
            out = reg.approve(conn, ref_id, actor=APPROVER, reason=APPROVAL_REASON)
            print(f"approved by {out['parameter']['approved_by']}; registry version "
                  f"{out['version']['version_number']}")
        conn.commit()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv, approve="--approve" in sys.argv))
