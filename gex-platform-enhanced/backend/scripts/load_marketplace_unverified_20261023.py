"""
Load the Marketplace records into PostgreSQL, every one UNVERIFIED (JML, 2026-10-23).

Source: scripts/data/marketplace_unverified_20261023.json — the four constants
MarketplacePage.tsx held in code, extracted verbatim. Nobody could say which were
real client information and which were invented, so each row is marked
verification_state = UNVERIFIED with `source` naming where it came from, and the
spot prices go to the reference registry as `proposed`, never in force until
someone confirms the source and approves them.

  project_sales_detail   8 projects
  project_input_line     33 lines across 11 projects
  input_classification   10 inputs
  reference_parameter    5 spot prices, proposed (market_spot_price[_energy])

Idempotent: rows already present are skipped. Dry run unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/load_marketplace_unverified_20261023.py [--execute]

Needs migration 066. A database rebuilt from Alembic needs this run; a pg_dump
restore already carries its rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402
from app.core.db_backend import market_connection, market_is_postgres, require_postgres  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "marketplace_unverified_20261023.json"
SOURCE = "MarketplacePage.tsx constant {name}, moved to PostgreSQL 2026-10-23 — provenance not recorded"
PROPOSER = "MARKETPLACE_MOVE_20261023"


def _num(v):
    return None if v is None else v


def load(conn, data: dict) -> dict:
    """Insert what is missing. Returns counts {table: (inserted, skipped)}."""
    counts: dict[str, list[int]] = {}

    def tally(table, inserted):
        counts.setdefault(table, [0, 0])[0 if inserted else 1] += 1

    projects = {r["project_id"] for r in conn.execute("SELECT project_id FROM projects").fetchall()}

    for pid, d in data["sales_detail"].items():
        if pid not in projects:
            raise SystemExit(f"sales_detail names a project not in PostgreSQL: {pid}")
        cur = conn.execute(
            "INSERT INTO project_sales_detail (project_id, region, e_source, green_energy_pct, certifier, "
            "breakeven_price, available, tokenised, in_market, source) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (project_id) DO NOTHING",
            (pid, d.get("region"), d.get("eSource"), _num(d.get("greenEnergyPct")), d.get("certifier"),
             _num(d.get("bePrice")), json.dumps(d.get("available")), json.dumps(d.get("tokenised")),
             json.dumps(d.get("inMarket") or []), SOURCE.format(name="PROJECT_SALES_DETAIL")))
        tally("project_sales_detail", cur.rowcount == 1)

    for pid, lines in data["input_lines"].items():
        if pid not in projects:
            raise SystemExit(f"input_lines names a project not in PostgreSQL: {pid}")
        for seq, s in enumerate(lines, 1):
            cur = conn.execute(
                "INSERT INTO project_input_line (project_id, seq, feedstock, supplier, ratio, ratio_unit, "
                "unit_price, price_unit, status, is_utility, capacity_factor, firming_cost, source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (project_id, seq) DO NOTHING",
                (pid, seq, s["feedstock"], s.get("supplier"), s["ratio"], s["ratioUnit"], s["unitPrice"],
                 s["priceUnit"], s["status"], bool(s.get("isUtility")), _num(s.get("capacityFactor")),
                 _num(s.get("firmingCost")), SOURCE.format(name="PROJECT_FEEDSTOCK")))
            tally("project_input_line", cur.rowcount == 1)

    for feedstock, e in data["input_classification"].items():
        cur = conn.execute(
            "INSERT INTO input_classification (feedstock, cert_relevance, capital_relevance, item_type, source) "
            "VALUES (?,?,?,?,?) ON CONFLICT (feedstock) DO NOTHING",
            (feedstock, e["certRelevance"], e["capitalRelevance"], e["itemType"],
             SOURCE.format(name="INPUT_ENRICHMENT")))
        tally("input_classification", cur.rowcount == 1)

    pathway_of = {r["market_molecule"]: r["registry_pathway"] for r in conn.execute(
        "SELECT market_molecule, registry_pathway FROM tb_commodity").fetchall()}
    for molecule, p in data["spot_prices"].items():
        pathway = pathway_of.get(molecule)
        if pathway is None:
            raise SystemExit(f"spot price for a molecule tb_commodity does not know: {molecule}")
        unit = p["unit"]
        key = "market_spot_price_energy" if unit.endswith("/MWh") else "market_spot_price"
        exists = conn.execute(
            "SELECT 1 FROM reference_parameter WHERE parameter_key = ? AND pathway = ? AND region = 'ANY' "
            "AND proposed_by = ?", (key, pathway, PROPOSER)).fetchone()
        if not exists:
            reg.propose(conn, {
                "parameter_key": key, "pathway": pathway, "region": "ANY", "value_base": p["spot"],
                "unit": unit, "currency": unit.split("/", 1)[0], "price_base_date": "2026-10-23",
                "source_class": "gex_assumption",
                "source_name": SOURCE.format(name="MOLECULE_SPOT"),
                "retrieved_at": "2026-10-23", "valid_from": "2026-10-23",
                "note": "UNVERIFIED: approve only once the source of this value is confirmed.",
            }, actor=PROPOSER)
        tally("reference_parameter (proposed)", not exists)
    return {k: tuple(v) for k, v in counts.items()}


def main(execute: bool) -> int:
    require_postgres(market_is_postgres(), "The Marketplace records", "MARKET_DB_BACKEND")
    conn = market_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held records
    try:
        counts = load(conn, json.loads(DATA.read_text()))
        for table, (ins, skip) in counts.items():
            print(f"{table:34} {ins:3} to insert, {skip:3} already present")
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
