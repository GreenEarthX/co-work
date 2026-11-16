"""
RFNBO correlation, COMPUTED from meters and contracts (migration 099, GreenMesh Step 4).
=====================================================================================
For one accounting period of a facility, three checks, each PASS, FAIL or UNVERIFIED with
its reason, and the rule versions (`rfnbo_rule`) they used:

  TEMPORAL     the electrolyser's POWER_CONSUMPTION matched against the PPA_GENERATION of
               its same-zone PPAs, per bucket: a calendar month while the rule in force on
               the reading's day says MONTHLY, a clock hour while it says HOURLY. PASS when
               generation covers consumption in every bucket. A reading that straddles a
               bucket edge cannot be assigned: UNVERIFIED (nothing is prorated).
  GEOGRAPHIC   the generator's bidding zone against the facility's. A PPA in another zone
               is reported and its generation not counted; the DA's alternatives
               (interconnected zones and prices) are NOT evaluated.
  ADDITIONALITY per same-zone PPA: generator in operation no earlier than the rule's months
               before the electrolyser, or the transitional exemption (electrolyser in
               operation before the rule's date, period ending by its end date).

UPSTREAM_HYDROGEN (since 101, GreenMesh Phase 2 Step 1) per CERTIFIED hydrogen input: the
               input names its source lot; the lot's period must be CLOSED and its statement
               re-verify, and that statement's own correlation is carried through (PASS or
               FAIL). No lot named, an open or unreadable upstream period, or an upstream
               UNVERIFIED: UNVERIFIED. Hydrogen is never assumed RFNBO.

Which checks apply: the three electricity checks when the period produces hydrogen or takes
CERTIFIED electricity; the upstream check when it takes CERTIFIED hydrogen. A check that does
not apply says NOT_APPLICABLE and counts for nothing. A period with no applicable check is
UNVERIFIED. Hydrogen periods therefore behave exactly as before 101.

Times are UTC; months and hours are UTC buckets. Overall: FAIL if any applicable check fails,
PASS if all applicable checks pass, otherwise UNVERIFIED. The result says `basis: COMPUTED`; the decision twin's
caller-supplied flags say `basis: DECLARED`, and a declared value is never shown as verified.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.core.meter_reconciliation import window_of

EPS = 1e-9


def _d(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def months_before(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 - months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def rules_on(conn, key: str, on: date) -> Optional[dict]:
    """The rule of `key` in force on `on` (latest valid_from among those whose window holds it)."""
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM rfnbo_rule WHERE rule_key = ? AND (valid_from IS NULL OR valid_from <= ?) "
        "AND (valid_to IS NULL OR valid_to >= ?) ORDER BY valid_from DESC NULLS LAST, recorded_at DESC",
        (key, on, on)).fetchall()]
    return rows[0] if rows else None


def granularity_on(conn, on: date) -> tuple[Optional[str], Optional[str]]:
    r = rules_on(conn, "TEMPORAL_CORRELATION", on)
    return (r["value"]["granularity"], r["rule_id"]) if r else (None, None)


def _bucket(start: datetime, granularity: str) -> tuple[str, datetime, datetime]:
    s = start.astimezone(timezone.utc)
    if granularity == "HOURLY":
        b0 = s.replace(minute=0, second=0, microsecond=0)
        return b0.strftime("%Y-%m-%dT%H"), b0, b0 + timedelta(hours=1)
    b0 = s.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    b1 = (b0 + timedelta(days=32)).replace(day=1)
    return b0.strftime("%Y-%m"), b0, b1


def _readings(conn, p: dict, data_type: str, start: datetime, end: datetime) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT interval_start, interval_end, quantity_normalised, ppa_id FROM plant_data "
        "WHERE project_id = ? AND facility_id = ? AND data_type = ? AND interval_start < ? AND interval_end > ? "
        "ORDER BY interval_start", (p["project_id"], p["facility_id"], data_type, end, start)).fetchall()]


def evaluate_period(conn, p: dict) -> dict:
    start, end = window_of(p["period_start"], p["period_end"])
    profile = conn.execute("SELECT * FROM coc_facility_profile WHERE project_id = ? AND facility_id = ?",
                           (p["project_id"], p["facility_id"])).fetchone()
    ppas = {r["ppa_id"]: dict(r) for r in conn.execute(
        "SELECT * FROM coc_ppa WHERE project_id = ? AND facility_id = ?",
        (p["project_id"], p["facility_id"])).fetchall()}
    rules_used: set[str] = set()

    # ── geographic ──
    geo_rule = rules_on(conn, "GEOGRAPHIC_CORRELATION", _d(p["period_end"]))
    if geo_rule:
        rules_used.add(geo_rule["rule_id"])
    zone = profile["bidding_zone"] if profile else None
    same = {k for k, a in ppas.items() if zone and a["generator_bidding_zone"] == zone}
    other = sorted(a["ppa_ref"] for k, a in ppas.items() if k not in same)
    if not profile:
        geo = {"status": "UNVERIFIED", "reason": "no facility profile: the electrolyser's bidding zone is not recorded"}
    elif not ppas:
        geo = {"status": "UNVERIFIED", "reason": "no PPA is registered for this facility"}
    elif not same:
        geo = {"status": "FAIL", "reason": f"no PPA is in the electrolyser's bidding zone {zone}"}
    else:
        geo = {"status": "PASS", "reason": f"{len(same)} PPA(s) in bidding zone {zone}"}
    geo.update({"facility_bidding_zone": zone, "ppas_in_zone": sorted(ppas[k]["ppa_ref"] for k in same),
                "ppas_not_counted_other_zone": other})

    # ── temporal ──
    cons = _readings(conn, p, "POWER_CONSUMPTION", start, end)
    gens = [g for g in _readings(conn, p, "PPA_GENERATION", start, end) if g["ppa_id"] in same]
    buckets: dict[str, dict] = {}
    straddling, no_rule = 0, 0
    for r in cons:
        if r["interval_start"] < start or r["interval_end"] > end:
            straddling += 1
            continue
        g, rid = granularity_on(conn, _d(r["interval_start"]))
        if g is None:
            no_rule += 1
            continue
        rules_used.add(rid)
        key, b0, b1 = _bucket(r["interval_start"], g)
        if r["interval_end"] > b1:
            straddling += 1
            continue
        b = buckets.setdefault(key, {"granularity": g, "start": b0, "end": b1, "consumption_mwh": 0.0,
                                     "generation_mwh": 0.0})
        b["consumption_mwh"] += float(r["quantity_normalised"])
    gen_unassigned = 0
    for gr in gens:
        hit = [b for b in buckets.values() if gr["interval_start"] >= b["start"] and gr["interval_end"] <= b["end"]]
        if hit:
            hit[0]["generation_mwh"] += float(gr["quantity_normalised"])
        elif any(gr["interval_start"] < b["end"] and b["start"] < gr["interval_end"] for b in buckets.values()):
            gen_unassigned += 1
    consumed = sum(b["consumption_mwh"] for b in buckets.values())
    matched = sum(min(b["consumption_mwh"], b["generation_mwh"]) for b in buckets.values())
    short = sorted(k for k, b in buckets.items() if b["generation_mwh"] + EPS < b["consumption_mwh"])
    temporal = {"consumption_mwh": consumed, "matched_mwh": matched,
                "matched_fraction": (matched / consumed) if consumed > 0 else None,
                "buckets": {k: {"granularity": b["granularity"], "consumption_mwh": b["consumption_mwh"],
                                "generation_mwh": b["generation_mwh"]} for k, b in sorted(buckets.items())},
                "buckets_short": short}
    if not cons:
        temporal.update(status="UNVERIFIED", reason="no POWER_CONSUMPTION readings for the period")
    elif no_rule:
        temporal.update(status="UNVERIFIED", reason=f"{no_rule} reading(s) fall on days no temporal rule covers")
    elif straddling or gen_unassigned:
        temporal.update(status="UNVERIFIED", reason=(
            f"{straddling} consumption and {gen_unassigned} generation reading(s) straddle a bucket or the "
            "period edge and cannot be assigned (nothing is prorated)"))
    elif short:
        temporal.update(status="FAIL", reason=f"generation does not cover consumption in {len(short)} bucket(s)")
    else:
        temporal.update(status="PASS", reason="generation covers consumption in every bucket")

    # ── additionality ──
    new_rule = rules_on(conn, "ADDITIONALITY_NEW_INSTALLATION", _d(p["period_end"]))
    tr_rule = rules_on(conn, "ADDITIONALITY_TRANSITION", _d(p["period_end"]))
    for r in (new_rule, tr_rule):
        if r:
            rules_used.add(r["rule_id"])
    elec = _d(profile["electrolyser_commissioning_date"]) if profile else None
    per_ppa, states = {}, []
    for k in sorted(same):
        a = ppas[k]
        gen_on = _d(a["generator_commissioning_date"])
        if elec is None or gen_on is None or not new_rule:
            st, why = "UNVERIFIED", "a commissioning date (electrolyser or generator) or the rule is missing"
        else:
            months = int(new_rule["value"]["max_months_before_electrolyser"])
            earliest = months_before(elec, months)
            if gen_on >= earliest:
                st, why = "PASS", f"generator in operation {gen_on}, not earlier than {months} months before {elec}"
            elif tr_rule and elec < _d(tr_rule["value"]["electrolyser_in_operation_before"]) \
                    and _d(p["period_end"]) <= _d(tr_rule["value"]["exempt_until"]):
                st, why = "PASS", "transitional exemption: electrolyser in operation before " \
                                  f"{tr_rule['value']['electrolyser_in_operation_before']}"
            else:
                st, why = "FAIL", f"generator in operation {gen_on}, earlier than {months} months before {elec}"
        per_ppa[a["ppa_ref"]] = {"status": st, "reason": why}
        states.append(st)
    if not same:
        add = {"status": "UNVERIFIED", "reason": "no same-zone PPA to assess"}
    elif "FAIL" in states:
        add = {"status": "FAIL", "reason": "a counted PPA fails additionality"}
    elif "UNVERIFIED" in states:
        add = {"status": "UNVERIFIED", "reason": "a counted PPA cannot be assessed"}
    else:
        add = {"status": "PASS", "reason": "every counted PPA is additional"}
    add["per_ppa"] = per_ppa

    # ── which checks apply (since 101) ──
    certified = {r["input_type"] for r in conn.execute(
        "SELECT DISTINCT input_type FROM coc_input WHERE period_id = ? AND sustainability_status = 'CERTIFIED'",
        (p["period_id"],)).fetchall()}
    electricity_applies = p["molecule"] == "H2" or "ELECTRICITY" in certified
    if not electricity_applies:
        for c in (geo, temporal, add):
            c.update(status="NOT_APPLICABLE",
                     reason="the period neither produces hydrogen nor takes certified electricity")
    upstream = upstream_hydrogen(conn, p)
    applicable = [c["status"] for c in (geo, temporal, add, upstream) if c["status"] != "NOT_APPLICABLE"]
    if not applicable:
        overall = "UNVERIFIED"
    else:
        overall = "FAIL" if "FAIL" in applicable else "PASS" if all(x == "PASS" for x in applicable) \
            else "UNVERIFIED"
    return {"basis": "COMPUTED", "status": overall, "period_id": p["period_id"],
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "temporal": temporal, "geographic": geo, "additionality": add,
            "upstream_hydrogen": upstream, "rules_used": sorted(rules_used)}


def _token_backed(conn, p: dict, r: dict) -> dict:
    """An input that names a hydrogen token its company holds: the permissioned upstream proof
    (core/upstream_proof.py), computed for the company that owns the consuming period."""
    from app.core import upstream_proof

    owner = conn.execute("SELECT owner_tenant_id FROM projects WHERE project_id = ?", (p["project_id"],)).fetchone()
    pr = upstream_proof.proof(r["source_token_id"], owner and owner["owner_tenant_id"])
    one = {"input_id": r["input_id"], "kg": float(r["quantity_normalised"]), "source_token_id": r["source_token_id"]}
    if pr is None:
        return {**one, "status": "UNVERIFIED", "reason": "the source token is not held by this period's company"}
    one.update(status=pr["status"], reason=pr["reason"], via="token proof",
               upstream_period_id=pr.get("period_id"), upstream_statement_hash=pr.get("statement_hash"))
    return one


def upstream_hydrogen(conn, p: dict) -> dict:
    """Carry the correlation of the hydrogen a period takes as a CERTIFIED input (101)."""
    from app.core.custody_ledger import verify_period

    rows = [dict(r) for r in conn.execute(
        "SELECT input_id, quantity_normalised, source_lot_id, source_token_id FROM coc_input WHERE period_id = ? "
        "AND input_type = 'H2' AND sustainability_status = 'CERTIFIED' ORDER BY seq", (p["period_id"],)).fetchall()]
    if not rows:
        return {"status": "NOT_APPLICABLE", "reason": "no certified hydrogen input", "inputs": []}
    per_input = []
    for r in rows:
        if r.get("source_token_id"):
            per_input.append(_token_backed(conn, p, r))      # G-23 (110): the holder's proof
            continue
        one = {"input_id": r["input_id"], "kg": float(r["quantity_normalised"]), "source_lot_id": r["source_lot_id"]}
        lot = conn.execute("SELECT period_id FROM mass_balance_lots WHERE lot_id = ?",
                           (r["source_lot_id"],)).fetchone() if r["source_lot_id"] else None
        up = conn.execute("SELECT * FROM coc_period WHERE period_id = ?",
                          (lot["period_id"],)).fetchone() if lot and lot["period_id"] else None
        if not r["source_lot_id"]:
            one.update(status="UNVERIFIED", reason="the input names no source hydrogen lot")
        elif not up:
            one.update(status="UNVERIFIED", reason="the source lot or its period is not readable")
        elif up["status"] != "CLOSED":
            one.update(status="UNVERIFIED", upstream_period_id=up["period_id"],
                       reason="the upstream hydrogen period is still open: its correlation is provisional")
        elif not verify_period(conn, up["period_id"])["valid"]:
            one.update(status="UNVERIFIED", upstream_period_id=up["period_id"],
                       reason="the upstream period's statement does not re-verify")
        else:
            c = (up["statement"] or {}).get("rfnbo_correlation") or {}
            st = c.get("status") if c.get("status") in ("PASS", "FAIL") else "UNVERIFIED"
            one.update(status=st, upstream_period_id=up["period_id"],
                       upstream_statement_hash=up["statement_hash"],
                       reason=f"upstream hydrogen period correlation: {c.get('status', 'not computed')}")
        per_input.append(one)
    states = [i["status"] for i in per_input]
    if "FAIL" in states:
        out = {"status": "FAIL", "reason": "certified hydrogen from a period that fails RFNBO correlation"}
    elif all(x == "PASS" for x in states):
        out = {"status": "PASS", "reason": f"all {len(states)} certified hydrogen input(s) come from periods that pass"}
    else:
        out = {"status": "UNVERIFIED", "reason": "a certified hydrogen input cannot be traced to a closed, "
                                                 "passing upstream period"}
    out["inputs"] = per_input
    return out
