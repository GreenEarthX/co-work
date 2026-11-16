"""
The quality specification sheet on the confirmed terms (D2; GreenMesh Phase 2 Step 3, sub-step 3).

The sheet is the typed part of `terms.quality_spec`:

    quality_spec = {"parameters": {"purity_pct": {"min": "99.97", "unit": "%"},
                                   "ghg_intensity_gco2e_mj": {"max": "28.2", "unit": "gCO2e/MJ"}},
                    ...free keys, untouched...}

Each parameter names its unit and at least one limit; limits are decimals, inclusive.
V16 (validation.py) refuses a malformed sheet. Free keys (the market's `certification_pathway`,
`carbon_intensity_gco2e_mj` as text) are never read as limits: a contract whose terms carry no
`parameters` has NO confirmed spec, and its deliveries cannot be accepted on a certificate
(D2) — only refused, or waived by both parties (D3).

`judge` compares an inspector's measured values with the sheet, PASS or FAIL per parameter;
a parameter the certificate does not measure is refused, never assumed.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def _dec(v: Any) -> Optional[Decimal]:
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def sheet_errors(quality_spec: dict) -> list[str]:
    params = (quality_spec or {}).get("parameters")
    if params is None:
        return []
    if not isinstance(params, dict) or not params:
        return ["parameters is a non-empty mapping of parameter -> limits"]
    out = []
    for name, p in params.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(p, dict):
            out.append(f"{name!r}: a named parameter with its limits")
            continue
        if not isinstance(p.get("unit"), str) or not p["unit"].strip():
            out.append(f"{name}: names its unit")
        lo, hi = p.get("min"), p.get("max")
        if lo is None and hi is None:
            out.append(f"{name}: has a min or a max")
        if (lo is not None and _dec(lo) is None) or (hi is not None and _dec(hi) is None):
            out.append(f"{name}: limits are decimals")
        elif lo is not None and hi is not None and _dec(lo) > _dec(hi):
            out.append(f"{name}: min above max")
        if set(p) - {"min", "max", "unit"}:
            out.append(f"{name}: only min, max and unit")
    return out


def sheet(quality_spec: dict) -> Optional[dict]:
    """The confirmed sheet, or None when the terms carry no typed parameters."""
    params = (quality_spec or {}).get("parameters")
    if not params or sheet_errors(quality_spec):
        return None
    return params


def judge(params: dict, measured: dict) -> list[dict]:
    """PASS/FAIL per parameter of the sheet. Raises ValueError naming what is missing or unreadable."""
    missing = [n for n in params if n not in (measured or {})]
    if missing:
        raise ValueError(f"the certificate does not measure {', '.join(sorted(missing))}")
    out = []
    for name in sorted(params):
        p, value = params[name], _dec(measured[name])
        if value is None:
            raise ValueError(f"{name}: {measured[name]!r} is not a measured value")
        lo, hi = _dec(p.get("min")), _dec(p.get("max"))
        ok = (lo is None or value >= lo) and (hi is None or value <= hi)
        out.append({"parameter": name, "measured": str(value), "min": p.get("min"), "max": p.get("max"),
                    "unit": p["unit"], "result": "PASS" if ok else "FAIL"})
    return out
