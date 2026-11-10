"""
M5 — capacities carry what the position view needs (spec §3.5, §8 M5; Phase 3, 2026-11-10).

For every capacity whose new columns are empty:

  commodity_id   tb_commodity by the molecule (its market code or its code)
  owner_id       the tb_counterparty of the project's owner company, registered from
                 its tenant row when it has none (record.counterparty_for's rule:
                 no two-letter jurisdiction, no counterparty — reported, not invented)
  period_start,  the production dates
  period_end
  quantity, unit capacity_mtpd × days in the period, in tonnes (the capacity is a
                 tonnes-per-day rate for every molecule, e-NG included)
  asset_id       only when the project has exactly one tb_asset; otherwise left NULL
                 and reported — never guessed

Returns what it could not determine, per capacity, so the migration can print it.
Idempotent: a capacity already filled is left alone.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.trading_book import record


def _day(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def fill(conn, capacity_ids=None) -> dict:
    """`conn` uses `?` placeholders. With capacity_ids, only those rows."""
    rows = record._rows(conn, "SELECT c.*, p.owner_tenant_id FROM capacities c JOIN projects p "
                              "ON p.project_id = c.project_id ORDER BY c.id")
    report = {}
    for c in rows:
        if capacity_ids is not None and c["id"] not in capacity_ids:
            continue
        if c.get("commodity_id") and c.get("owner_id") and c.get("quantity") is not None:
            continue
        missing = []
        code = record.commodity_for_molecule(conn, c["molecule"])
        commodity = record._row(conn, "SELECT id FROM tb_commodity WHERE code = ?", (code,)) if code else None
        if commodity is None:
            missing.append(f"commodity (molecule {c['molecule']!r})")
        try:
            owner = record.counterparty_for(conn, c["owner_tenant_id"])
        except record.RecordRefused:
            owner = None
            missing.append(f"owner (tenant {c['owner_tenant_id']!r} has no two-letter jurisdiction)")
        start, end = _day(c["production_start"]), _day(c["production_end"])
        quantity = None
        if start and end and end >= start and c["capacity_mtpd"] is not None:
            quantity = (Decimal(str(c["capacity_mtpd"])) * ((end - start).days + 1)).quantize(Decimal("0.000001"))
        else:
            missing.append("period (production dates)")
        assets = record._rows(conn, "SELECT id FROM tb_asset WHERE project_id = ?", (c["project_id"],))
        asset = str(assets[0]["id"]) if len(assets) == 1 else None
        if asset is None:
            missing.append(f"asset ({len(assets)} tb_asset rows for {c['project_id']})")
        conn.execute("UPDATE capacities SET commodity_id = ?, owner_id = ?, asset_id = ?, period_start = ?, "
                     "period_end = ?, quantity = ?, unit = CASE WHEN ? IS NULL THEN NULL ELSE 't'::tb_unit END "
                     "WHERE id = ?",
                     (str(commodity["id"]) if commodity else None, owner, asset, start, end, quantity, quantity,
                      c["id"]))
        if missing:
            report[c["id"]] = missing
    return report
