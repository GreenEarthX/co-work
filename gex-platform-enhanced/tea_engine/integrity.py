"""integrity.py — input-integrity layer for the GEX TEA engine.

The engine computes from assumptions, but a screening number must carry the
QUALITY of its inputs, or a precise-looking LCOP gets trusted beyond its evidence.
Two gaps this closes (from the TEA-Challenger review):

  · G2 — units: nameplate units are normalised through ONE table and an unknown
    unit is REJECTED, never silently assumed t/yr (the 1000×/365× trap). Physically
    implausible outputs are flagged so a unit/scale error cannot pass as a normal case.
  · G1 — provenance: every material financial input is classified — a value the
    caller SET is a project assumption, a value left at its DEFAULT is a model
    default. The result carries a status that tracks that quality (SCREENING vs
    PROVISIONAL), so 'substitute a default for a project value' stops being invisible.

None of this changes the arithmetic or the truth-stack claim_state (that stays
'submitted' — verification is the IE/CFO axis, elsewhere).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


# ── G2: nameplate unit normalisation ───────────────────────────────────────
# Canonical production units → tonnes/year. MTPD is metric tonnes/day (the
# platform-wide convention). Anything not here is refused, not guessed.
NAMEPLATE_TO_T_PER_YEAR: dict[str, float] = {
    "t_per_year": 1.0, "tpa": 1.0, "tonnes_per_year": 1.0, "t/yr": 1.0,
    "kt_per_year": 1_000.0, "ktpa": 1_000.0, "kt/yr": 1_000.0,
    "kg_per_year": 0.001, "kg/yr": 0.001,
    "t_per_day": 365.0, "tpd": 365.0, "mtpd": 365.0, "t/day": 365.0,
    "kg_per_day": 0.365, "kg/day": 0.365,
}


def nameplate_factor(unit: str) -> float:
    key = (unit or "").strip().lower()
    if key not in NAMEPLATE_TO_T_PER_YEAR:
        raise ValueError(
            f"Unknown nameplate_unit {unit!r}. Supported: "
            f"{sorted(set(NAMEPLATE_TO_T_PER_YEAR))}. GEX refuses to guess a unit — "
            f"an unrecognised unit silently read as t/yr is the 1000×/365× TEA trap."
        )
    return NAMEPLATE_TO_T_PER_YEAR[key]


def to_t_per_year(capacity: float, unit: str) -> float:
    return capacity * nameplate_factor(unit)


# ── G2: plausibility of the computed result ────────────────────────────────
# Broad SCREENING sanity bands for e-fuels / H2. A unit or scale error produces a
# result wildly outside these; a legitimate project sits well inside. The bands are
# heuristic and deliberately wide — they flag, they do not price.
PLAUSIBLE_SPECIFIC_CAPEX_EUR_PER_TPA = (500.0, 50_000.0)
PLAUSIBLE_LCOP_EUR_PER_KG = (0.10, 30.0)


def plausibility_flags(capex_eur: float, nameplate_t_per_year: float,
                       lcop_eur_per_kg: Optional[float]) -> list[str]:
    """Flags for physically implausible outputs — the tell of a unit/scale error."""
    flags: list[str] = []
    if nameplate_t_per_year and nameplate_t_per_year > 0:
        spec = capex_eur / nameplate_t_per_year
        lo, hi = PLAUSIBLE_SPECIFIC_CAPEX_EUR_PER_TPA
        if spec < lo or spec > hi:
            flags.append(
                f"specific_capex {spec:,.0f} EUR/tpa is outside the plausible "
                f"{lo:,.0f}–{hi:,.0f} band — likely a unit or scale error")
    if lcop_eur_per_kg is not None:
        lo, hi = PLAUSIBLE_LCOP_EUR_PER_KG
        if lcop_eur_per_kg < lo or lcop_eur_per_kg > hi:
            flags.append(
                f"lcop {lcop_eur_per_kg:g} EUR/kg is outside the plausible "
                f"{lo}–{hi} band — likely a unit or scale error")
    return flags


# ── G1: input-provenance classification ────────────────────────────────────
class ProvenanceClass(str, Enum):
    MEASURED_ACTUAL = "measured_actual"
    VENDOR_GUARANTEED = "vendor_guaranteed"
    ENGINEER_VALIDATED = "engineer_validated"
    PROJECT_DOCUMENT = "project_document"
    EXTERNAL_BENCHMARK = "external_benchmark"
    SPONSOR_ASSUMPTION = "sponsor_assumption"
    MODEL_DEFAULT = "model_default"
    INFERRED = "inferred"
    MISSING = "missing"


# Classes that count as project-grounded (better than a bare default/inference).
_GROUNDED = {
    ProvenanceClass.MEASURED_ACTUAL, ProvenanceClass.VENDOR_GUARANTEED,
    ProvenanceClass.ENGINEER_VALIDATED, ProvenanceClass.PROJECT_DOCUMENT,
    ProvenanceClass.EXTERNAL_BENCHMARK, ProvenanceClass.SPONSOR_ASSUMPTION,
}

# Material financial inputs whose provenance we classify → their unit.
MATERIAL_INPUTS: dict[str, str] = {
    "discount_rate_pct": "%",
    "electricity_eur_mwh": "EUR/MWh",
    "capacity_factor": "fraction",
    "project_life_years": "years",
    "contingency_pct": "%",
    "co2_eur_t": "EUR/t",
    "hydrogen_eur_t": "EUR/t",
    "feedstock_oil_eur_t": "EUR/t",
}


def classify_inputs(assumptions) -> dict[str, dict]:
    """Per material input → {value, unit, source_class}.

    A value the caller SET is a SPONSOR_ASSUMPTION unless they classify it higher
    (via assumptions.provenance); a value left at its DEFAULT is a MODEL_DEFAULT.
    That is exactly the distinction TEA attack #18 relies on GEX not making.
    """
    declared = dict(getattr(assumptions, "provenance", None) or {})
    set_fields = getattr(assumptions, "model_fields_set", set())
    out: dict[str, dict] = {}
    for field, unit in MATERIAL_INPUTS.items():
        tag = declared.get(field)
        if tag:
            try:
                cls = ProvenanceClass(tag)
            except ValueError:
                cls = ProvenanceClass.SPONSOR_ASSUMPTION
        elif field in set_fields:
            cls = ProvenanceClass.SPONSOR_ASSUMPTION
        else:
            cls = ProvenanceClass.MODEL_DEFAULT
        out[field] = {"value": getattr(assumptions, field), "unit": unit,
                      "source_class": cls.value}
    return out


def result_status(input_provenance: dict[str, dict], plausibility: list[str]) -> str:
    """Evidence quality of the RESULT (not whether the arithmetic ran).

    IMPLAUSIBLE  → outputs out of band (unit/scale error).
    SCREENING    → at least one material input is a model default / inferred / missing.
    PROVISIONAL  → every material input is project-grounded.
    Never ENGINEER-REVIEWED / VENDOR-BACKED here — that is the IE/CFO approval axis.
    """
    if plausibility:
        return "IMPLAUSIBLE"
    classes = {ProvenanceClass(v["source_class"]) for v in input_provenance.values()}
    return "SCREENING" if (classes - _GROUNDED) else "PROVISIONAL"


# ── G5: cost basis (currency / base date / escalation) ─────────────────────
# OpenPyTEA's cost correlations are USD and it escalates to CEPCI target year 2024;
# GEX does not configure a Plant currency, so the number is USD-2024. The platform
# field is named *_eur and NO FX has been applied — surfaced here, not silently.
OPENPYTEA_TARGET_CEPCI_YEAR = 2024

# USD -> base-currency multipliers for OpenPyTEA's USD cost correlations. FIXED, DATED
# 2024 averages (ECB reference), matching the CEPCI-2024 cost base — NEVER a spot rate,
# which would break cost_basis_hash reproducibility and mismatch the cost-base year.
# A caller/CFO may override per request; the rate then becomes a sponsor assumption.
USD_TO_BASE = {"EUR": 0.924, "USD": 1.0}
FX_SOURCE = "ECB reference rate, 2024 average (fixed; matches CEPCI-2024 cost base)"
# A CFO/authorised override may move the benchmark by at most this much — a bounded,
# conservative adjustment, not an arbitrary rate. Enforced HERE as a source invariant
# (so even a direct engine caller can't set a wild rate); the CFO AUTHORITY gate lives
# in the backend bridge.
FX_CONSERVATIVE_BAND = 0.05


def usd_to_base_rate(base_currency: str, override: Optional[float] = None) -> float:
    """USD -> base-currency multiplier applied to OpenPyTEA's USD costs. An explicit
    override wins but must sit within ±FX_CONSERVATIVE_BAND of the benchmark; else the
    dated default; else 1.0 (unknown ccy)."""
    base = (base_currency or "EUR").upper()
    benchmark = USD_TO_BASE.get(base, 1.0)
    if override is None:
        return benchmark
    ovr = float(override)
    if benchmark and abs(ovr - benchmark) > FX_CONSERVATIVE_BAND * benchmark:
        lo, hi = benchmark * (1 - FX_CONSERVATIVE_BAND), benchmark * (1 + FX_CONSERVATIVE_BAND)
        raise ValueError(
            f"FX override {ovr:g} for USD->{base} is outside the ±{FX_CONSERVATIVE_BAND:.0%} "
            f"conservative band around the benchmark {benchmark} ([{lo:.4f}, {hi:.4f}]).")
    return ovr


def fx_meta(base_currency: str, override: Optional[float] = None) -> dict:
    """The FX assumption as a provenanced object for the cost basis. Default rate is an
    external benchmark; a caller/CFO override (within the band) is a sponsor assumption."""
    base = (base_currency or "EUR").upper()
    overridden = override is not None
    rate = usd_to_base_rate(base, override)   # validates the ±band
    return {
        "pair": f"USD->{base}",
        "rate": rate,
        "provenance": (ProvenanceClass.SPONSOR_ASSUMPTION.value if overridden
                       else ProvenanceClass.EXTERNAL_BENCHMARK.value),
        "source": "caller/CFO override" if overridden else FX_SOURCE,
        "conservative_band": FX_CONSERVATIVE_BAND if overridden else None,
        "base_year": OPENPYTEA_TARGET_CEPCI_YEAR,
    }


def cost_basis_block(base_currency: str, cost_year: Optional[int], is_stub: bool,
                     fx: Optional[dict] = None) -> dict:
    if is_stub:
        return {"currency": (base_currency or "EUR").upper(), "cost_year": None,
                "cepci_basis": None, "fx_normalised": False, "fx": None,
                "note": "Illustrative stub — not a real cost basis; no CEPCI/currency basis."}
    base = (base_currency or "EUR").upper()
    fx = fx or fx_meta(base)
    if base == "USD":
        note = (f"OpenPyTEA native USD, escalated to CEPCI {cost_year}. "
                f"No conversion (base currency USD).")
    else:
        note = (f"OpenPyTEA USD correlations converted to {base} at {fx['rate']} "
                f"({fx['source']}), escalated to CEPCI {cost_year}. Feedstock/variable "
                f"OPEX is already {base} (priced by GEX) — not double-converted.")
    return {
        "currency": base,
        "cost_year": cost_year,
        "cepci_basis": f"CEPCI {cost_year}" if cost_year else None,
        "fx_normalised": True,
        "fx": fx,
        "note": note,
    }


# ── G6: calculation boundary (battery limits) ──────────────────────────────
def calculation_boundary(pf_meta: Optional[dict], n_supplied: int,
                         fuel_id: str, canonical_count: Optional[int],
                         canonical_nodes: Optional[list] = None) -> dict:
    """Declare what the cost covers. For the canonical train, the battery-limit
    nodes. For a caller-supplied train, flag that GEX has NOT verified completeness
    — a dropped block (compression/purification/…) understates CAPEX (attack I)."""
    if pf_meta:
        return {
            "basis": "canonical",
            "nodes": pf_meta.get("nodes"),
            "equipment_count": pf_meta.get("equipment_count"),
            "complete": True,
            "note": ("Battery limit = the molecule's canonical process train. Excludes "
                     "grid connection, external H2/CO2 supply (priced as feedstocks), "
                     "land, and owner's cost."),
        }
    out = {
        "basis": "caller_supplied",
        "nodes": None,
        "equipment_count": n_supplied,
        "canonical_equipment_count": canonical_count,
        "canonical_nodes": canonical_nodes,
        "complete": None,   # unknown — GEX did not derive this train
        "note": ("Caller-supplied train — GEX did NOT verify battery-limit "
                 "completeness. A dropped process block understates CAPEX/LCOP."),
    }
    if canonical_count and n_supplied < canonical_count:
        out["complete"] = False
        out["note"] += (f" Supplied {n_supplied} of the ~{canonical_count} units in the "
                        f"canonical {fuel_id} train — likely missing process blocks.")
    return out


# ── G4: extreme scale extrapolation → an implausibility flag ───────────────
def scaling_flags(pf_meta: Optional[dict]) -> list[str]:
    """A nameplate far from the correlation's tuned reference scale makes the sizing
    an extrapolation. A MODERATE extrapolation is surfaced in meta.scaling; an
    EXTREME one (a likely nameplate unit/scale error) is flagged here so it downgrades
    the result status."""
    if not pf_meta:
        return []
    ratio = (pf_meta.get("scaling") or {}).get("ratio")
    if ratio is not None and (ratio > 50.0 or ratio < 0.02):
        ref = (pf_meta.get("scaling") or {}).get("reference_nameplate_t_per_year")
        return [f"nameplate is {ratio:g}× the tuned reference ({ref} t/yr) — the "
                f"cost correlations are extrapolated far beyond their basis "
                f"(likely a nameplate unit/scale error)"]
    return []
