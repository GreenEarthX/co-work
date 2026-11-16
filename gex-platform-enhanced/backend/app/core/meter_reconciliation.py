"""
Declared against metered — the custody ledger's reconciliation (migration 098, Step 3).
=====================================================================================
A lot's declared volume is compared with the PRODUCTION_VOLUME the facility's meters
reported for the lot's production window; at period close the period's declared
production and its declared electricity are compared with the meters over the period.
One of three answers, always with its reason — nothing passes silently:

  RECONCILED   the meters cover the whole window and |declared − metered| is within
               the agreed tolerance x metered
  VARIANCE     the meters cover the whole window and the difference is larger
  UNVERIFIED   there are no meter readings, they do not cover the whole window, or the
               lot's window overlaps another lot's so the meter cannot be attributed

Windows are whole days in UTC: a production window 2026-02-01 .. 2026-02-28 runs from
2026-02-01T00:00Z to 2026-03-01T00:00Z. Only meter intervals lying wholly inside the
window count; one that straddles a boundary is reported, not prorated (prorating would
assume a constant rate). Readings of several gateways of one facility are added.

The tolerance is `coc_meter_tolerance`, per facility and measure, versioned, sourced. It
ships EMPTY because the value is the certifier's or the independent engineer's to give.
With no agreed tolerance it is ZERO, so any difference is a VARIANCE, and the detail says
that no tolerance has been agreed.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

EPS = 1e-9
STATUSES = ("RECONCILED", "VARIANCE", "UNVERIFIED")


def _d(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def window_of(start: Any, end: Any) -> tuple[datetime, datetime]:
    """Whole UTC days, end inclusive."""
    s = datetime.combine(_d(start), time.min, tzinfo=timezone.utc)
    e = datetime.combine(_d(end) + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return s, e


def metered(conn, project_id: str, facility_id: str, data_type: str, molecule: Optional[str],
            start: datetime, end: datetime) -> dict:
    rows = [dict(r) for r in conn.execute(
        "SELECT gateway_id, interval_start, interval_end, quantity_normalised, normalised_unit "
        "FROM plant_data WHERE project_id = ? AND facility_id = ? AND data_type = ? "
        "AND COALESCE(molecule, '') = ? AND interval_start < ? AND interval_end > ? "
        "ORDER BY interval_start",
        (project_id, facility_id, data_type, molecule or "", end, start)).fetchall()]
    inside = [r for r in rows if r["interval_start"] >= start and r["interval_end"] <= end]
    covered, cursor = 0.0, None                      # union of the inside intervals
    for r in sorted(inside, key=lambda r: r["interval_start"]):
        s, e = r["interval_start"], r["interval_end"]
        if cursor is None or s > cursor:
            covered += (e - s).total_seconds()
            cursor = e
        elif e > cursor:
            covered += (e - cursor).total_seconds()
            cursor = e
    span = (end - start).total_seconds()
    return {"quantity": sum(float(r["quantity_normalised"]) for r in inside),
            "unit": "MWh" if data_type == "POWER_CONSUMPTION" else "kg",
            "readings": len(inside), "straddling_readings": len(rows) - len(inside),
            "coverage_fraction": covered / span if span > 0 else 0.0,
            "gateways": sorted({r["gateway_id"] for r in inside})}


def tolerance(conn, project_id: str, facility_id: str, measure: str, molecule: Optional[str],
              on: Any) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM coc_meter_tolerance WHERE project_id = ? AND facility_id = ? AND measure = ? "
        "AND COALESCE(molecule, '') = ? AND valid_from <= ? ORDER BY valid_from DESC LIMIT 1",
        (project_id, facility_id, measure, molecule or "", _d(on))).fetchone()
    return dict(row) if row else None


def judge(declared: float, meter: dict, tol_row: Optional[dict], window: tuple[datetime, datetime]) -> tuple[str, dict]:
    tol = float(tol_row["tolerance_fraction"]) if tol_row else 0.0
    detail = {"declared": declared, "metered": meter["quantity"], "unit": meter["unit"],
              "window_start": window[0].isoformat(), "window_end": window[1].isoformat(),
              "meter_readings": meter["readings"], "straddling_readings": meter["straddling_readings"],
              "coverage_fraction": round(meter["coverage_fraction"], 6), "gateways": meter["gateways"],
              "tolerance_fraction": tol,
              "tolerance_source": tol_row["source"] if tol_row else "none agreed: zero tolerance applied"}
    if meter["readings"] == 0:
        return "UNVERIFIED", {**detail, "reason": "no meter readings for this facility and window"}
    if meter["coverage_fraction"] < 1 - EPS:
        return "UNVERIFIED", {**detail, "reason": (
            f"the meters cover {meter['coverage_fraction']:.1%} of the window"
            + (f"; {meter['straddling_readings']} reading(s) straddle its edges and are not prorated"
               if meter["straddling_readings"] else ""))}
    diff = declared - meter["quantity"]
    detail["difference"] = diff
    detail["relative_difference"] = (abs(diff) / meter["quantity"]) if meter["quantity"] > 0 else None
    if abs(diff) <= tol * meter["quantity"] + EPS:
        return "RECONCILED", {**detail, "reason": "declared matches metered within the tolerance"}
    return "VARIANCE", {**detail, "reason": "declared differs from metered beyond the tolerance"}


def reconcile_lot(conn, project_id: str, facility_id: str, molecule: str, window_start: Any,
                  window_end: Any, declared_kg: float, exclude_lot_id: Optional[str] = None) -> tuple[str, dict]:
    """A lot's window against the meters. Lots with the SAME window are added together; a
    lot whose window only partly overlaps makes the attribution ambiguous: UNVERIFIED."""
    win = window_of(window_start, window_end)
    ws, we = _d(window_start), _d(window_end)
    declared, partial = float(declared_kg), []
    for r in conn.execute(
            "SELECT lot_id, total_volume_kg, characteristics FROM mass_balance_lots WHERE project_id = ? "
            "AND facility_id = ? AND molecule = ? AND characteristics IS NOT NULL",
            (project_id, facility_id, molecule)).fetchall():
        if r["lot_id"] == exclude_lot_id:
            continue
        c = r["characteristics"]
        os_, oe = _d(c["production_window_start"]), _d(c["production_window_end"])
        if (os_, oe) == (ws, we):
            declared += float(r["total_volume_kg"])
        elif os_ <= we and ws <= oe:
            partial.append(r["lot_id"])
    meter = metered(conn, project_id, facility_id, "PRODUCTION_VOLUME", molecule, *win)
    status, detail = judge(declared, meter, tolerance(conn, project_id, facility_id, "PRODUCTION",
                                                      molecule, we), win)
    if partial:
        return "UNVERIFIED", {**detail, "overlapping_lots": partial, "reason": (
            "this lot's production window partly overlaps another lot's, so metered output "
            "cannot be attributed between them")}
    return status, detail


def lot_reconciliation(conn, lot: dict) -> dict:
    """Live status of a stored lot (the lot response's `meter_reconciliation`)."""
    c = lot.get("characteristics")
    if not lot.get("facility_id") or not c:
        return {"status": "UNVERIFIED",
                "reason": "the lot names no facility and production window (it has no accounting period)"}
    status, detail = reconcile_lot(conn, lot["project_id"], lot["facility_id"], lot["molecule"],
                                   c["production_window_start"], c["production_window_end"],
                                   float(lot["total_volume_kg"]), exclude_lot_id=lot["lot_id"])
    return {"status": status, **detail}


def period_reconciliation(conn, p: dict, pos: dict) -> dict:
    """At close: the period's declared production and declared electricity vs the meters."""
    win = window_of(p["period_start"], p["period_end"])
    end = p["period_end"]
    prod = metered(conn, p["project_id"], p["facility_id"], "PRODUCTION_VOLUME", p["molecule"], *win)
    s1, d1 = judge(float(pos["declared_production_kg"]), prod,
                   tolerance(conn, p["project_id"], p["facility_id"], "PRODUCTION", p["molecule"], end), win)
    power = metered(conn, p["project_id"], p["facility_id"], "POWER_CONSUMPTION", None, *win)
    declared_mwh = float(pos["inputs"].get("ELECTRICITY", {}).get("quantity_all", 0.0))
    s2, d2 = judge(declared_mwh, power,
                   tolerance(conn, p["project_id"], p["facility_id"], "ELECTRICITY", None, end), win)
    return {"production": {"status": s1, **d1}, "electricity": {"status": s2, **d2}}
