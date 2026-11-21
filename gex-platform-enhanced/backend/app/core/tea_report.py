"""The TEA run report: a fixed reference, and whether the run's inputs still hold (20 Nov 2026).

A report is the stored run, never a recomputation. Its reference is derived from what was
stored when the run was made (figures, the exact request OpenPyTEA received, the defaults it
applied, the recorded results), so the same reference always reprints the same numbers and a
different number cannot carry the same reference. The review state is NOT part of it: a
review changes who relies on the run, not what it computed.

"Inputs unchanged" compares the run with today, three ways, each stated:
  · the cost basis: is the version it priced still the project's latest?
  · the reference rows it cited (CEPCI forward, FX benchmark, LCOP band): still approved?
  · the engine: is the running OpenPyTEA the version that priced it?
A part that could not be checked says so; it is never reported as unchanged.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

_RUN_FIELDS = ("claim_id", "project_id", "cost_basis_version_id", "cost_basis_sha256", "engine",
               "engine_version", "cost_basis_hash", "capex_eur", "opex_eur_per_year", "lcop",
               "result_status", "nameplate_capacity", "nameplate_unit", "created_at", "run_by")


def frozen_content(base: dict) -> dict:
    return {"run": {k: base.get(k) for k in _RUN_FIELDS}, "tea_inputs": base.get("tea_inputs")}


def report_ref(base: dict) -> dict:
    sha = hashlib.sha256(json.dumps(frozen_content(base), sort_keys=True, default=str).encode()).hexdigest()
    short = str(base["claim_id"]).removeprefix("CLM-MBC-")
    return {"ref": f"GEX-TEA-{short}-{sha[:8]}", "sha256": sha,
            "basis": "The run as stored when it was made; never recomputed. The same reference reprints "
                     "the same figures."}


def cited_refs(base: dict) -> dict[str, str]:
    """{ref_id: what it was used for} for every reference row the run's request cited."""
    req = (base.get("tea_inputs") or {}).get("request") or {}
    out: dict[str, str] = {}
    for year, f in (req.get("cepci_forward") or {}).items():
        if isinstance(f, dict) and f.get("ref_id"):
            out[f["ref_id"]] = f"CEPCI forward {year}"
    if req.get("fx_benchmark_ref_id"):
        out[req["fx_benchmark_ref_id"]] = "FX benchmark"
    if req.get("lcop_band_ref_id"):
        out[req["lcop_band_ref_id"]] = "LCOP plausibility band"
    return out


def inputs_status(base: dict, cost_bases: list[dict], ref_states: dict[str, str],
                  engine_now: Optional[str]) -> dict:
    checks = []
    mine = next((c for c in cost_bases if c["version_id"] == base.get("cost_basis_version_id")), None)
    latest = max(cost_bases, key=lambda c: c["version_number"]) if cost_bases else None
    if mine is None or latest is None:
        checks.append({"check": "cost basis", "result": "NOT_CHECKED", "detail": "The cost basis version is not readable."})
    elif latest["version_id"] == mine["version_id"]:
        checks.append({"check": "cost basis", "result": "SAME", "detail": f"v{mine['version_number']} is still the latest."})
    else:
        checks.append({"check": "cost basis", "result": "CHANGED",
                       "detail": f"v{latest['version_number']} was saved after this run (it priced v{mine['version_number']})."})
    for ref_id, used_for in sorted(cited_refs(base).items(), key=lambda kv: kv[1]):
        state = ref_states.get(ref_id)
        if state is None:
            checks.append({"check": used_for, "result": "NOT_CHECKED", "detail": f"Row {ref_id[:8]} is not readable."})
        elif state == "approved":
            checks.append({"check": used_for, "result": "SAME", "detail": f"Row {ref_id[:8]} is still approved."})
        else:
            checks.append({"check": used_for, "result": "CHANGED", "detail": f"Row {ref_id[:8]} is now {state}."})
    if not engine_now:
        checks.append({"check": "engine", "result": "NOT_CHECKED", "detail": "The TEA engine did not answer."})
    elif engine_now == base.get("engine_version"):
        checks.append({"check": "engine", "result": "SAME", "detail": f"OpenPyTEA {engine_now}."})
    else:
        checks.append({"check": "engine", "result": "CHANGED",
                       "detail": f"Priced on OpenPyTEA {base.get('engine_version')}; the engine now runs {engine_now}."})
    results = {c["result"] for c in checks}
    unchanged = False if "CHANGED" in results else (None if "NOT_CHECKED" in results else True)
    return {"unchanged": unchanged, "checks": checks}


def ref_states(ref_ids: set[str]) -> dict[str, str]:
    if not ref_ids:
        return {}
    from app.core.db_backend import fuelref_connection
    conn = fuelref_connection()
    try:
        marks = ",".join("?" for _ in ref_ids)
        rows = conn.execute(f"SELECT ref_id, state FROM reference_parameter WHERE ref_id IN ({marks})",
                            tuple(ref_ids)).fetchall()
        return {r["ref_id"]: r["state"] for r in rows}
    finally:
        conn.close()


_ENGINE_CACHE: dict = {"at": 0.0, "version": None}


def engine_version_now(url: str, ttl: float = 60.0) -> Optional[str]:
    """The OpenPyTEA version the running TEA engine reports; None if it does not answer."""
    if time.monotonic() - _ENGINE_CACHE["at"] < ttl:
        return _ENGINE_CACHE["version"]
    version = None
    try:
        import httpx
        r = httpx.get(f"{url}/healthz", timeout=2.0)
        if r.status_code == 200:
            version = r.json().get("openpytea_version") or None
    except Exception:
        version = None
    _ENGINE_CACHE.update(at=time.monotonic(), version=version)
    return version
