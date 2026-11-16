"""
Chain of custody — accounting periods, input consignments, declared conversion.
===============================================================================
The period arithmetic behind `api/v1/mass_balance.py` (migration 097). PostgreSQL only.

ONE IDENTITY, PER ACCOUNTING PERIOD
-----------------------------------
    opening + inputs x conversion - withdrawals = closing

  opening      0, unless the scheme rule for the period's scheme allows carry-forward,
               then the previous CLOSED period's closing. With no confirmed rule there
               is no carry-forward: the conservative reading, stated in the statement.
  inputs       input consignments recorded in the period, each with an evidence
               reference. Only CERTIFIED inputs earn credit.
  conversion   the DECLARED input per kg of output for the facility, pathway, molecule
               and input type, in force on the day the input was received. Where a
               product needs several inputs (electricity and CO2 for e-methanol) the
               credit is the smallest product equivalent across them.
  withdrawals  allocations of the period's lots to tokens.

A withdrawal beyond the balance is refused unless the scheme rule allows a negative
interim balance; a period never closes in deficit. A lot whose declared output exceeds
ALL inputs x conversion (beyond the factor's tolerance; none recorded = zero) is
recorded and FLAGGED, never silently accepted.

WHAT THIS IS NOT
----------------
The conversion factors are declared accounting ratios, supplied by the facility or its
engineer and versioned here. This module does not model the plant: no equipment sizing,
no process design, no losses. Engineering balance lives in the frontend equation engine.
Rules a certifier must confirm (period length, carry-forward, negative interim balance)
live in `coc_scheme_rule`, which ships EMPTY: no value is invented here.

HASH CHAIN
----------
A period's open record has `open_hash`. Each input carries `prev_hash` (the previous
input's hash, or the open hash) and `entry_hash`. Closing hashes the statement, which
names the head of the input chain and every allocation hash in the period.
`verify_period` recomputes all of it from the rows.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

INPUT_TYPES = ("ELECTRICITY", "CO2", "N2", "WATER", "H2")
EVIDENCE_KINDS = ("PPA", "GO", "POS", "SUPPLIER_INVOICE", "METER", "OTHER")
SUSTAINABILITY = ("CERTIFIED", "NON_CERTIFIED")
ADDITIONALITY_BASES = ("DIRECT_CONNECTION", "PPA", "GRID_RENEWABLE_SHARE", "GRID_LOW_EMISSION",
                       "IMBALANCE_REDUCTION", "NOT_CLAIMED")

# Quantity units: electricity in MWh, every material input in kg. No density or other
# physical constant is used, so a volume unit (m3) is refused rather than converted.
_QTY_UNITS = {
    "ELECTRICITY": {"MWh": 1.0, "kWh": 0.001, "GWh": 1000.0},
    "_MASS": {"kg": 1.0, "t": 1000.0},
}
# Declared conversion, stated per unit of output; normalised to (MWh | kg) per kg output.
_FACTOR_UNITS = {
    "ELECTRICITY": {"MWh/kg": 1.0, "kWh/kg": 0.001, "MWh/t": 0.001},
    "_MASS": {"kg/kg": 1.0, "t/t": 1.0, "kg/t": 0.001},
}
EPS = 1e-9


class CustodyError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _units(input_type: str, table: dict) -> dict:
    if input_type not in INPUT_TYPES:
        raise CustodyError(422, f"input_type must be one of {INPUT_TYPES}, got {input_type!r}")
    return table["ELECTRICITY"] if input_type == "ELECTRICITY" else table["_MASS"]


def base_unit(input_type: str) -> str:
    return "MWh" if input_type == "ELECTRICITY" else "kg"


def normalise_quantity(input_type: str, quantity: float, unit: str) -> float:
    units = _units(input_type, _QTY_UNITS)
    if unit not in units:
        raise CustodyError(422, f"{input_type} is recorded in {sorted(units)}, not {unit!r}")
    if not quantity > 0:
        raise CustodyError(422, "quantity must be positive")
    return quantity * units[unit]


def normalise_factor(input_type: str, value: float, unit: str) -> float:
    units = _units(input_type, _FACTOR_UNITS)
    if unit not in units:
        raise CustodyError(422, f"a {input_type} factor is stated in {sorted(units)}, not {unit!r}")
    if not value > 0:
        raise CustodyError(422, "a conversion factor must be positive")
    return value * units[unit]


# ── characteristics ─────────────────────────────────────────────────────────

class Characteristics(BaseModel):
    """The sustainability characteristics that stay assigned to a consignment (Art. 30(b)).
    Validated, closed (unknown keys refused) and DECLARED: Step 4 computes correlation."""

    model_config = ConfigDict(extra="forbid")

    ghg_intensity_gco2e_mj: float = Field(..., ge=0)
    pathway: str = Field(..., min_length=1)
    scheme: str = Field(..., min_length=1)
    certificate_id: Optional[str] = Field(None, min_length=1)
    country_of_origin: str = Field(..., pattern=r"^[A-Z]{2}$")
    production_window_start: date
    production_window_end: date
    rfnbo: bool
    additionality_basis: Literal[ADDITIONALITY_BASES]  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _consistent(self):
        if self.production_window_end < self.production_window_start:
            raise ValueError("production_window_end is before production_window_start")
        if self.rfnbo and not self.certificate_id:
            raise ValueError("an RFNBO consignment names its certificate_id")
        if self.rfnbo and self.additionality_basis == "NOT_CLAIMED":
            raise ValueError("an RFNBO consignment states its additionality basis")
        return self


def validate_characteristics(raw: Any, period: dict, production_date: str) -> dict:
    """The lot's characteristics, checked against itself and against its period."""
    if not isinstance(raw, dict):
        raise CustodyError(422, "a period lot carries a characteristics object")
    try:
        c = Characteristics.model_validate(raw)
    except ValidationError as exc:
        errs = "; ".join(f"{'.'.join(str(x) for x in e['loc']) or 'characteristics'}: {e['msg']}"
                         for e in exc.errors())
        raise CustodyError(422, f"invalid characteristics — {errs}") from exc
    if c.pathway != period["pathway"]:
        raise CustodyError(422, f"characteristics.pathway {c.pathway!r} is not the period's "
                                f"pathway {period['pathway']!r}")
    if c.scheme != period["scheme"]:
        raise CustodyError(422, f"characteristics.scheme {c.scheme!r} is not the period's "
                                f"scheme {period['scheme']!r}")
    start, end = _d(period["period_start"]), _d(period["period_end"])
    if c.production_window_start < start or c.production_window_end > end:
        raise CustodyError(422, "the production window lies outside the accounting period")
    pd = _d(production_date)
    if not c.production_window_start <= pd <= c.production_window_end:
        raise CustodyError(422, "production_date lies outside the lot's production window")
    return json.loads(c.model_dump_json())


# ── helpers ─────────────────────────────────────────────────────────────────

def _d(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise CustodyError(422, f"{v!r} is not an ISO date") from exc


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def chain_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _open_payload(p: dict) -> dict:
    return {k: _iso(p[k]) if k in ("period_start", "period_end") else p[k] for k in (
        "period_id", "project_id", "facility_id", "molecule", "pathway", "scheme",
        "period_start", "period_end", "opening_balance_kg", "opening_basis", "opened_by")}


def _input_payload(r: dict) -> dict:
    out = {k: r[k] for k in (
        "input_id", "period_id", "project_id", "input_type", "quantity", "unit",
        "quantity_normalised", "normalised_unit", "sustainability_status", "evidence_kind",
        "evidence_ref", "recorded_by", "seq", "prev_hash")}
    out["received_on"] = _iso(r["received_on"])
    out["characteristics"] = r["characteristics"] or {}
    if r.get("source_lot_id"):                       # since 101; absent from older payloads
        out["source_lot_id"] = r["source_lot_id"]
    if r.get("source_token_id"):                     # since 110 (G-23); absent from older payloads
        out["source_token_id"] = r["source_token_id"]
    return out


def cited_kg(conn, lot_id: str) -> float:
    """Hydrogen of a lot already taken as an input by downstream periods (101)."""
    v = conn.execute("SELECT COALESCE(SUM(quantity_normalised), 0) AS kg FROM coc_input "
                     "WHERE source_lot_id = ?", (lot_id,)).fetchone()
    return float(v["kg"] or 0)


def _source_lot(conn, data: dict, t: str, kg: float) -> Optional[str]:
    """Validate the upstream hydrogen lot an H2 input names (101). None when none is named:
    the input is then recorded, and its correlation stays UNVERIFIED downstream."""
    lot_id = (data.get("source_lot_id") or "").strip() or None
    if not lot_id:
        return None
    if t != "H2":
        raise CustodyError(422, "only a hydrogen (H2) input names a source lot")
    lot = conn.execute("SELECT * FROM mass_balance_lots WHERE lot_id = ? FOR UPDATE", (lot_id,)).fetchone()
    if not lot:
        raise CustodyError(422, f"source lot {lot_id} not found or not readable")
    if lot["molecule"] != "H2":
        raise CustodyError(422, f"source lot {lot_id} is {lot['molecule']}, not hydrogen")
    if not lot["period_id"]:
        raise CustodyError(422, f"source lot {lot_id} belongs to no accounting period: its hydrogen "
                                "cannot carry a correlation result")
    free = float(lot["total_volume_kg"]) - float(lot["allocated_volume_kg"]) - cited_kg(conn, lot_id)
    if kg > free + EPS:
        raise CustodyError(409, f"COC_SOURCE_LOT_EXHAUSTED: {kg} kg requested, {max(free, 0.0)} kg of "
                                f"lot {lot_id} is neither allocated nor already used as an input")
    return lot_id


def _source_token(conn, data: dict, t: str, kg: float, project_id: str) -> Optional[str]:
    """G-23 (110): an H2 input may name a hydrogen TOKEN its company holds by title transfer,
    instead of a lot. 110's trigger checks the same; these are the readable refusals."""
    from decimal import Decimal

    token_id = (data.get("source_token_id") or "").strip() or None
    if not token_id:
        return None
    if t != "H2":
        raise CustodyError(422, "only a hydrogen (H2) input names a source token")
    if (data.get("source_lot_id") or "").strip():
        raise CustodyError(422, "an input names a source lot or a source token, not both")
    owner = conn.execute("SELECT owner_tenant_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    tok = conn.execute("SELECT id, holder_company_id, lifecycle_state, molecule FROM tokens WHERE id = ?",
                       (token_id,)).fetchone()
    if tok is None or owner is None or tok["holder_company_id"] != owner["owner_tenant_id"]:
        raise CustodyError(422, f"COC_SOURCE_TOKEN_NOT_HELD: token {token_id} is not held by this project's company")
    if tok["lifecycle_state"] != "SETTLED" or tok["molecule"] != "H2":
        raise CustodyError(409, f"COC_SOURCE_TOKEN_STATE: token {token_id} is {tok['molecule']} "
                                f"{tok['lifecycle_state']}; an input names a delivered hydrogen token")
    whole = Decimal(str(conn.execute("SELECT app_token_kg(?) AS kg", (token_id,)).fetchone()["kg"]))
    used = Decimal(str(conn.execute("SELECT COALESCE(SUM(quantity_normalised), 0) AS kg FROM coc_input "
                                    "WHERE source_token_id = ?", (token_id,)).fetchone()["kg"]))
    if Decimal(str(kg)) > whole - used:
        raise CustodyError(409, f"COC_SOURCE_TOKEN_EXHAUSTED: {kg} kg requested, {whole - used} kg of token "
                                f"{token_id} is not yet used as an input")
    return token_id


def period_row(conn, period_id: str, lock: bool = False) -> dict:
    row = conn.execute("SELECT * FROM coc_period WHERE period_id = ?" + (" FOR UPDATE" if lock else ""),
                       (period_id,)).fetchone()
    if not row:
        raise CustodyError(404, f"Accounting period {period_id} not found")
    return dict(row)


def scheme_rule(conn, scheme: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM coc_scheme_rule WHERE scheme = ?", (scheme,)).fetchone()
    return dict(row) if row else None


def _rule_view(rule: Optional[dict]) -> Optional[dict]:
    if not rule:
        return None
    return {"scheme": rule["scheme"], "max_period_days": rule["max_period_days"],
            "carry_forward_allowed": rule["carry_forward_allowed"],
            "negative_interim_allowed": rule["negative_interim_allowed"],
            "source": rule["source"], "confirmed_by": rule["confirmed_by"],
            "confirmed_at": _iso(rule["confirmed_at"])}


def public_period(p: dict) -> dict:
    out = dict(p)
    for k in ("period_start", "period_end", "opened_at", "closed_at"):
        out[k] = _iso(out.get(k))
    return out


# ── opening a period ────────────────────────────────────────────────────────

def open_period(conn, data: dict, actor: str) -> dict:
    start, end = _d(data["period_start"]), _d(data["period_end"])
    if end < start:
        raise CustodyError(422, "period_end is before period_start")
    rule = scheme_rule(conn, data["scheme"])
    if rule and rule["max_period_days"] and (end - start).days + 1 > rule["max_period_days"]:
        raise CustodyError(422, f"{data['scheme']} allows periods of at most "
                                f"{rule['max_period_days']} days")
    opening, basis = 0.0, "FIRST_PERIOD"
    prev = conn.execute(
        "SELECT * FROM coc_period WHERE project_id = ? AND facility_id = ? AND molecule = ? "
        "AND pathway = ? AND period_end < ? ORDER BY period_end DESC LIMIT 1",
        (data["project_id"], data["facility_id"], data["molecule"], data["pathway"], start)).fetchone()
    if prev:
        if not rule or rule["carry_forward_allowed"] is None:
            basis = "NO_CARRY_FORWARD: no confirmed scheme rule"
        elif rule["carry_forward_allowed"] is False:
            basis = "NO_CARRY_FORWARD: not allowed by the scheme rule"
        elif prev["status"] != "CLOSED":
            raise CustodyError(409, f"the previous period {prev['period_id']} is still open; "
                                    "close it before carrying its balance forward")
        else:
            opening = float(prev["closing_balance_kg"])
            basis = f"CARRIED_FROM:{prev['period_id']}"
    p = {"period_id": str(uuid.uuid4()), "project_id": data["project_id"],
         "facility_id": data["facility_id"], "molecule": data["molecule"],
         "pathway": data["pathway"], "scheme": data["scheme"], "period_start": start,
         "period_end": end, "opening_balance_kg": opening, "opening_basis": basis,
         "opened_by": actor}
    p["open_hash"] = chain_hash(_open_payload(p))
    cols = list(p)
    conn.execute(f"INSERT INTO coc_period ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                 tuple(p[c] for c in cols))
    return period_row(conn, p["period_id"])


# ── inputs and factors ──────────────────────────────────────────────────────

def record_input(conn, period_id: str, data: dict, actor: str) -> dict:
    p = period_row(conn, period_id, lock=True)           # serialises the chain
    if p["status"] != "OPEN":
        raise CustodyError(409, f"COC_PERIOD_CLOSED: period {period_id} is closed")
    t = data["input_type"]
    if data.get("sustainability_status") not in SUSTAINABILITY:
        raise CustodyError(422, f"sustainability_status must be one of {SUSTAINABILITY}")
    if data.get("evidence_kind") not in EVIDENCE_KINDS:
        raise CustodyError(422, f"evidence_kind must be one of {EVIDENCE_KINDS}")
    if not (data.get("evidence_ref") or "").strip():
        raise CustodyError(422, "an input consignment names its evidence (PPA, GO, PoS ...)")
    chars = data.get("characteristics") or {}
    if not isinstance(chars, dict):
        raise CustodyError(422, "characteristics must be an object")
    kg = normalise_quantity(t, float(data["quantity"]), data["unit"])
    token_source = _source_token(conn, data, t, kg, p["project_id"])
    source = None if token_source else _source_lot(conn, data, t, kg)
    last = conn.execute("SELECT seq, entry_hash FROM coc_input WHERE period_id = ? "
                        "ORDER BY seq DESC LIMIT 1", (period_id,)).fetchone()
    r = {"input_id": str(uuid.uuid4()), "period_id": period_id, "project_id": p["project_id"],
         "input_type": t, "quantity": float(data["quantity"]), "unit": data["unit"],
         "quantity_normalised": kg,
         "normalised_unit": base_unit(t), "sustainability_status": data["sustainability_status"],
         "received_on": _d(data["received_on"]), "characteristics": chars,
         "evidence_kind": data["evidence_kind"], "evidence_ref": data["evidence_ref"].strip(),
         "recorded_by": actor, "seq": (last["seq"] + 1) if last else 1,
         "prev_hash": last["entry_hash"] if last else p["open_hash"], "source_lot_id": source,
         "source_token_id": token_source}
    r["entry_hash"] = chain_hash(_input_payload(r))
    cols = list(r)
    conn.execute(f"INSERT INTO coc_input ({', '.join(cols)}) VALUES ("
                 + ", ".join("CAST(? AS jsonb)" if c == "characteristics" else "?" for c in cols) + ")",
                 tuple(json.dumps(r[c]) if c == "characteristics" else r[c] for c in cols))
    return dict(conn.execute("SELECT * FROM coc_input WHERE input_id = ?", (r["input_id"],)).fetchone())


def record_factor(conn, data: dict, actor: str) -> dict:
    t = data["input_type"]
    stated, unit = float(data["value"]), data["unit"]
    if not (data.get("source") or "").strip():
        raise CustodyError(422, "a conversion factor names its source (engineer's report, design basis ...)")
    tol = data.get("tolerance_fraction")
    if tol is not None and tol < 0:
        raise CustodyError(422, "tolerance_fraction cannot be negative")
    r = {"factor_id": str(uuid.uuid4()), "project_id": data["project_id"],
         "facility_id": data["facility_id"], "pathway": data["pathway"], "molecule": data["molecule"],
         "input_type": t, "input_per_kg_output": normalise_factor(t, stated, unit),
         "input_unit": base_unit(t), "stated_value": stated, "stated_unit": unit,
         "tolerance_fraction": tol, "valid_from": _d(data["valid_from"]),
         "source": data["source"].strip(), "recorded_by": actor}
    cols = list(r)
    conn.execute(f"INSERT INTO coc_conversion_factor ({', '.join(cols)}) VALUES "
                 f"({', '.join('?' for _ in cols)})", tuple(r[c] for c in cols))
    return dict(conn.execute("SELECT * FROM coc_conversion_factor WHERE factor_id = ?",
                             (r["factor_id"],)).fetchone())


# ── the position of a period ────────────────────────────────────────────────

def position(conn, p: dict, extra_declared_kg: float = 0.0) -> dict:
    """The period's numbers now, from its rows. Same shape as the statement's body."""
    inputs = [dict(r) for r in conn.execute(
        "SELECT * FROM coc_input WHERE period_id = ? ORDER BY seq", (p["period_id"],)).fetchall()]
    factors = [dict(r) for r in conn.execute(
        "SELECT * FROM coc_conversion_factor WHERE project_id = ? AND facility_id = ? AND pathway = ? "
        "AND molecule = ? ORDER BY input_type, valid_from",
        (p["project_id"], p["facility_id"], p["pathway"], p["molecule"])).fetchall()]
    end = _d(p["period_end"])

    def in_force(t: str, on: date) -> Optional[dict]:
        best = None
        for f in factors:
            if f["input_type"] == t and _d(f["valid_from"]) <= on:
                best = f
        return best

    required = sorted({f["input_type"] for f in factors if _d(f["valid_from"]) <= end})
    by_type: dict[str, dict] = {}
    for r in inputs:
        t = r["input_type"]
        b = by_type.setdefault(t, {"unit": r["normalised_unit"], "quantity_all": 0.0,
                                   "quantity_certified": 0.0, "product_equivalent_all_kg": 0.0,
                                   "product_equivalent_certified_kg": 0.0,
                                   "quantity_without_factor": 0.0, "count": 0})
        b["count"] += 1
        q = float(r["quantity_normalised"])
        b["quantity_all"] += q
        cert = r["sustainability_status"] == "CERTIFIED"
        if cert:
            b["quantity_certified"] += q
        f = in_force(t, _d(r["received_on"]))
        if f is None:
            b["quantity_without_factor"] += q
            continue
        eq = q / float(f["input_per_kg_output"])
        b["product_equivalent_all_kg"] += eq
        if cert:
            b["product_equivalent_certified_kg"] += eq

    def eq_of(t: str, key: str) -> float:
        return by_type.get(t, {}).get(key, 0.0)

    if required:
        supported = min(eq_of(t, "product_equivalent_all_kg") for t in required)
        credit = min(eq_of(t, "product_equivalent_certified_kg") for t in required)
        latest = [in_force(t, end) for t in required]
        tolerance = min(float(f["tolerance_fraction"] or 0.0) for f in latest if f)
    else:
        supported, credit, tolerance = None, 0.0, None

    lots = [dict(r) for r in conn.execute(
        "SELECT lot_id, total_volume_kg FROM mass_balance_lots WHERE period_id = ? ORDER BY created_at, lot_id",
        (p["period_id"],)).fetchall()]
    declared = sum(float(r["total_volume_kg"]) for r in lots) + float(extra_declared_kg)
    allocs = [dict(r) for r in conn.execute(
        "SELECT allocation_hash, volume_kg FROM mass_balance_allocations WHERE period_id = ? "
        "ORDER BY created_at, allocation_id", (p["period_id"],)).fetchall()]
    withdrawals = sum(float(a["volume_kg"]) for a in allocs)
    opening = float(p["opening_balance_kg"])

    if not required:
        check = "NO_FACTOR"
    elif declared > supported * (1 + tolerance) + EPS:
        check = "EXCEEDS_INPUTS"
    else:
        check = "WITHIN_INPUTS"
    return {
        "opening_balance_kg": opening,
        "opening_basis": p["opening_basis"],
        "inputs": by_type,
        "input_count": len(inputs),
        "conversion": {"required_input_types": required, "credit_kg": credit,
                       "supported_output_kg": supported, "tolerance_fraction": tolerance,
                       "check": check},
        "declared_production_kg": declared,
        "lot_ids": [r["lot_id"] for r in lots],
        "withdrawals_kg": withdrawals,
        "allocation_hashes": [a["allocation_hash"] for a in allocs],
        "closing_balance_kg": opening + credit - withdrawals,
        "identity": "opening + inputs x conversion - withdrawals = closing",
        "input_chain_head": inputs[-1]["entry_hash"] if inputs else p["open_hash"],
    }


def conversion_check_for_new_lot(conn, p: dict, volume_kg: float) -> tuple[str, dict]:
    pos = position(conn, p, extra_declared_kg=volume_kg)
    c = pos["conversion"]
    return c["check"], {"declared_production_kg": pos["declared_production_kg"],
                        "supported_output_kg": c["supported_output_kg"],
                        "tolerance_fraction": c["tolerance_fraction"],
                        "required_input_types": c["required_input_types"],
                        "checked_at": _now()}


def check_withdrawal(conn, p: dict, volume_kg: float) -> dict:
    """Refuse a withdrawal the period's balance does not cover (unless the scheme allows it)."""
    if p["status"] != "OPEN":
        raise CustodyError(409, f"COC_PERIOD_CLOSED: period {p['period_id']} is closed")
    pos = position(conn, p)
    available = pos["closing_balance_kg"]
    rule = scheme_rule(conn, p["scheme"])
    if volume_kg > available + EPS and not (rule and rule["negative_interim_allowed"]):
        raise CustodyError(409, (
            f"COC_PERIOD_BALANCE: requested {volume_kg} kg but period {p['period_id']} holds "
            f"{available} kg (opening {pos['opening_balance_kg']} + certified inputs x conversion "
            f"{pos['conversion']['credit_kg']} - withdrawals {pos['withdrawals_kg']})"))
    return pos


# ── closing and verifying ───────────────────────────────────────────────────

def close_period(conn, period_id: str, actor: str) -> dict:
    p = period_row(conn, period_id, lock=True)
    if p["status"] != "OPEN":
        raise CustodyError(409, f"COC_PERIOD_CLOSED: period {period_id} is already closed")
    pos = position(conn, p)
    if pos["closing_balance_kg"] < -EPS:
        raise CustodyError(409, f"a period never closes in deficit ({pos['closing_balance_kg']} kg)")
    rule = scheme_rule(conn, p["scheme"])
    notes = []
    if not rule:
        notes.append(f"No confirmed rule for scheme {p['scheme']}: period length unchecked, no "
                     "carry-forward, no negative balance. Confirm with the certifying body.")
    elif not rule["max_period_days"]:
        notes.append("The scheme rule states no maximum period length: unchecked.")
    if pos["conversion"]["check"] != "WITHIN_INPUTS":
        notes.append(f"Declared production vs inputs x conversion: {pos['conversion']['check']}.")
    from app.core.meter_reconciliation import period_reconciliation

    meters = period_reconciliation(conn, p, pos)
    from app.core.rfnbo_correlation import evaluate_period

    correlation = evaluate_period(conn, p)
    if correlation["status"] != "PASS":
        notes.append(f"RFNBO correlation (computed): {correlation['status']}.")
    for measure, r in meters.items():
        if r["status"] != "RECONCILED":
            notes.append(f"Metered {measure}: {r['status']} — {r['reason']}.")
    closed_at = _now()
    statement = {
        "period": {k: _iso(p[k]) if k in ("period_start", "period_end") else p[k] for k in (
            "period_id", "project_id", "facility_id", "molecule", "pathway", "scheme",
            "period_start", "period_end", "open_hash")},
        **pos,
        "meter_reconciliation": meters,
        "rfnbo_correlation": correlation,
        "scheme_rule": _rule_view(rule),
        "notes": notes,
        "closed_by": actor,
        "closed_at": closed_at,
    }
    statement_hash = chain_hash(statement)
    conn.execute(
        "UPDATE coc_period SET status = 'CLOSED', closing_balance_kg = ?, statement = CAST(? AS jsonb), "
        "statement_hash = ?, closed_by = ?, closed_at = ? WHERE period_id = ?",
        (pos["closing_balance_kg"], json.dumps(statement, sort_keys=True, default=str),
         statement_hash, actor, closed_at, period_id))
    return period_row(conn, period_id)


def verify_period(conn, period_id: str) -> dict:
    """Recompute the open hash, the input chain and, when closed, the statement."""
    p = period_row(conn, period_id)
    checks: dict[str, bool] = {"open_hash": chain_hash(_open_payload(p)) == p["open_hash"]}
    prev, broken_at = p["open_hash"], None
    for r in conn.execute("SELECT * FROM coc_input WHERE period_id = ? ORDER BY seq", (period_id,)).fetchall():
        r = dict(r)
        if r["prev_hash"] != prev or chain_hash(_input_payload(r)) != r["entry_hash"]:
            broken_at = r["input_id"]
            break
        prev = r["entry_hash"]
    checks["input_chain"] = broken_at is None
    if p["status"] == "CLOSED":
        st = p["statement"]
        checks["statement_hash"] = chain_hash(st) == p["statement_hash"]
        checks["statement_names_the_chain_head"] = st.get("input_chain_head") == prev
        now = position(conn, p)
        checks["allocations_unchanged"] = now["allocation_hashes"] == st.get("allocation_hashes")
        checks["closing_reproduces"] = abs(now["closing_balance_kg"] - float(p["closing_balance_kg"])) <= EPS
    return {"period_id": period_id, "status": p["status"], "valid": all(checks.values()),
            "checks": checks, "broken_at": broken_at}
