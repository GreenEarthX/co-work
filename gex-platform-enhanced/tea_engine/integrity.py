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


def lcop_band(governed: Optional[tuple[float, float]] = None,
              governed_unit: Optional[str] = None) -> tuple[float, float]:
    """The plausible-LCOP band: the GOVERNED band when supplied, else the code default.

    The registry key `tea_lcop_plausible_band` sits in COST_PER_MASS, whose family also
    admits EUR/t. A per-tonne band read as per-kilogram is a silent 1000x error that
    would widen the band enough to pass almost anything — and this band gates
    `result_status = IMPLAUSIBLE`, which gates promotion to `verified`, which gates P1.
    So a band whose unit is not EUR/kg is REFUSED, not converted and not ignored:
    converting silently would hide a mis-entered row, and ignoring it would quietly fall
    back to the default while the registry said otherwise.
    """
    if governed is None:
        return PLAUSIBLE_LCOP_EUR_PER_KG
    # Fail CLOSED on a missing unit. A band with no unit was previously accepted as-is,
    # so a direct :8002 caller posting lcop_band_low/high without lcop_band_unit could
    # hand us a per-tonne band read as per-kilogram — ceiling 30 -> 30,000, which makes
    # the IMPLAUSIBLE gate pass almost anything. Not reachable through the bridge
    # (reference_parameter.unit is NOT NULL) but reachable directly, and this band gates
    # promotion to `verified`, which gates P1. An unlabelled band is refused.
    if governed_unit is None:
        raise ValueError(
            "a governed LCOP band must carry its unit: an unlabelled band could be "
            "EUR/t read as EUR/kg, a 1000x widening of the band that gates IMPLAUSIBLE.")
    if governed_unit != "EUR/kg":
        raise ValueError(
            f"tea_lcop_plausible_band is in {governed_unit!r}; this band is compared "
            f"against an LCOP in EUR/kg. A per-tonne band read as per-kilogram is a "
            f"1000x error — re-propose the row in EUR/kg.")
    lo, hi = float(governed[0]), float(governed[1])
    if not (lo > 0 and hi > lo):
        raise ValueError(f"tea_lcop_plausible_band is not a band: [{lo}, {hi}]")
    return lo, hi


def plausibility_flags(capex_eur: float, nameplate_t_per_year: float,
                       lcop_eur_per_kg: Optional[float],
                       governed_lcop_band: Optional[tuple[float, float]] = None,
                       governed_lcop_band_unit: Optional[str] = None) -> list[str]:
    """Flags for physically implausible outputs — the tell of a unit/scale error.

    NOTE the two bands are on DIFFERENT mass bases, deliberately: specific capex is
    EUR per tonne/year of nameplate, LCOP is EUR per kilogram of product. Each is
    compared against a value already in its own unit (`nameplate_t_per_year` is
    canonicalised to t/yr by `to_t_per_year`; `lcop_eur_per_kg` is the engine's EUR/kg
    levelised cost). They are a 1000x apart by nature, not by accident.
    """
    flags: list[str] = []
    if nameplate_t_per_year and nameplate_t_per_year > 0:
        spec = capex_eur / nameplate_t_per_year
        lo, hi = PLAUSIBLE_SPECIFIC_CAPEX_EUR_PER_TPA
        if spec < lo or spec > hi:
            flags.append(
                f"specific_capex {spec:,.0f} EUR/tpa is outside the plausible "
                f"{lo:,.0f}–{hi:,.0f} band — likely a unit or scale error")
    if lcop_eur_per_kg is not None:
        lo, hi = lcop_band(governed_lcop_band, governed_lcop_band_unit)
        if lcop_eur_per_kg < lo or lcop_eur_per_kg > hi:
            flags.append(
                f"lcop {lcop_eur_per_kg:g} EUR/kg is outside the plausible "
                f"{lo}–{hi} band — likely a unit or scale error")
    return flags


# ── Mass balance: the INPUT-side sibling of plausibility_flags ──────────────
# plausibility_flags catches an implausible OUTPUT (a capex or an LCOP out of band).
# This catches an implausible INPUT: a pathway that consumes less mass than it makes.
# Deliberately simple, so a reader can check it by hand — Process Mass Intensity, the
# standard green-chemistry measure, is just total mass in over total mass out.
#
# A mass-product pathway with PMI < 1 is making mass from nothing. Measured 2026-10-26:
# E_AMMONIA declares 0.198 t/t (its nitrogen, 0.8235 t/t from air, is never declared)
# and GREEN_H2 declares 0.000 (its feed water, ~9 t/t, is never declared). Both are
# FREE streams, so the costing is unaffected — but an undeclared stream is also an
# undeclared CO-PRODUCT risk (GREEN_H2's oxygen, ~8 t/t, is saleable), and a balance
# nobody can check is a balance nobody should trust.
PMI_FLOOR = 1.0


def mass_balance_flags(pf_meta: Optional[dict]) -> list[str]:
    """Flags for a declared mass balance that cannot be true.

    Reads the meta block the process function already publishes — no new data, no new
    concept. Returns human-readable strings exactly as `plausibility_flags` and
    `scaling_flags` do, so they append to the same list and gate the same
    `result_status`.
    """
    if not pf_meta:
        return []
    flags: list[str] = []
    mass_in = pf_meta.get("mass_in_t_per_t_primary")
    mass_out = pf_meta.get("mass_out_t_per_t_primary")
    if mass_in is None or not mass_out:
        return flags

    pmi = float(mass_in) / float(mass_out)
    if float(mass_in) == 0.0:
        flags.append(
            "mass balance: no mass input is declared at all, yet the pathway produces "
            f"{mass_out:g} t of product per t of primary — every feed stream is missing "
            "from the process function, so nothing about this balance can be checked")
    elif pmi < PMI_FLOOR:
        flags.append(
            f"mass balance: process mass intensity {pmi:.3f} is below {PMI_FLOOR:g} — "
            f"{mass_in:g} t declared in against {mass_out:g} t out per t of primary "
            "product. Mass cannot be created; a feed stream is undeclared (an inert or "
            "free stream still has mass, and an undeclared stream may also be an "
            "undeclared saleable co-product)")

    undeclared = pf_meta.get("undeclared_outputs_t_per_t_primary")
    if undeclared is not None and float(undeclared) > 0:
        flags.append(
            f"mass balance: {float(undeclared):.4f} t per t of primary product is "
            "unaccounted on the OUTPUT side — reaction water, purge and vent are not "
            "declared, so closure is asserted rather than computed")
    return flags


# ── Energy reconciliation: the CAPEX side against the OPEX side ────────────
# The two halves of a plant are built from independent numbers. CAPEX comes from the
# equipment train's rotating duty (base_param in MWe or kW); OPEX comes from a
# hand-entered mwh_per_t_product. Nothing tied them together, so each could be
# defensible while the pair was not.
#
# Measured 2026-10-26, per tonne of PRIMARY product at capacity factor 0.60:
#   E_METHANOL    train implies 2.737 MWh/t  declared 0.700   ratio 3.91x
#   E_SAF         train implies 3.180 MWh/t  declared 3.120   ratio 1.02x   consistent
#   BIO_SAF_HEFA  train implies 0.999 MWh/t  declared 0.525   ratio 1.90x
#
# Which side is wrong is NOT decidable from the ratio, and this check deliberately does
# not guess. For E_METHANOL a first-principles check says the DECLARED figure is right
# (CO2 compression alone needs 0.137-0.183 MWh/t for 1.53 t CO2/t at 0.09-0.12 MWh/t
# CO2, so 0.70 for the whole utility load is plausible) and the EQUIPMENT is oversized:
# the CO2 compressor declares 6.0 MWe against a duty of 0.78-1.05 MW, 5.7x too large.
# That overstates CAPEX. The equipment sizing is a governed row (migration 075), so the
# correction is a four-eye proposal, not a code edit.
#
# Installed capacity is an UPPER BOUND on consumption: rated duty is not drawn
# continuously, and a train may carry spares. So the band is wide and one-sided — it
# fires on a gross mismatch, not on a duty factor.
ENERGY_RECONCILE_MAX_RATIO = 2.0


def energy_balance_flags(pf_meta: Optional[dict]) -> list[str]:
    """Flag a plant whose equipment duty and declared energy cannot both be right.

    Same shape as `mass_balance_flags` and `plausibility_flags`: a pure predicate over
    the meta block, returning human-readable strings.
    """
    if not pf_meta:
        return []
    e = pf_meta.get("energy_reconciliation") or {}
    implied = e.get("implied_from_train_mwh_per_t")
    declared = e.get("declared_mwh_per_t")
    if not implied or not declared:
        return []
    ratio = float(implied) / float(declared)
    if ratio <= ENERGY_RECONCILE_MAX_RATIO:
        return []
    return [
        f"energy reconciliation: the equipment train implies {float(implied):.3f} MWh "
        f"per t of primary product ({e.get('installed_mw')} MW installed at capacity "
        f"factor {e.get('capacity_factor')}) against a declared {float(declared):.3f} "
        f"— a factor of {ratio:.2f}. The CAPEX and OPEX sides of this plant are built "
        f"on different energy bases and cannot both be right. Installed duty is an "
        f"upper bound, so a ratio near 1 is expected; check whether the equipment "
        f"sizing is oversized (overstating CAPEX) or the declared energy is too low "
        f"(understating OPEX)."
    ]


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


def fx_benchmark(base_currency: str, supplied: Optional[float] = None) -> float:
    """The benchmark USD -> base rate: the GOVERNED value when the caller supplies one,
    else this module's dated default.

    `tea_engine` is stateless and holds no database, so it cannot read the reference
    registry itself. The backend bridge resolves `tea_fx_usd_to_eur` and passes it in
    the request, which keeps the engine stateless AND puts the rate inside
    `cost_basis_hash` — the hash hashes the request, so a governed change to the rate
    now changes the hash. Before this it did not: the rate moved capex -4.8% under a
    byte-identical hash (measured 2026-09-24).
    """
    base = (base_currency or "EUR").upper()
    if supplied is not None:
        return float(supplied)
    return USD_TO_BASE.get(base, 1.0)


def usd_to_base_rate(base_currency: str, override: Optional[float] = None,
                     benchmark: Optional[float] = None) -> float:
    """USD -> base-currency multiplier applied to OpenPyTEA's USD costs. An explicit
    override wins but must sit within ±FX_CONSERVATIVE_BAND of the benchmark; else the
    benchmark (governed if supplied, else the dated default); else 1.0 (unknown ccy)."""
    base = (base_currency or "EUR").upper()
    benchmark = fx_benchmark(base, benchmark)
    if override is None:
        return benchmark
    ovr = float(override)
    if benchmark and abs(ovr - benchmark) > FX_CONSERVATIVE_BAND * benchmark:
        lo, hi = benchmark * (1 - FX_CONSERVATIVE_BAND), benchmark * (1 + FX_CONSERVATIVE_BAND)
        raise ValueError(
            f"FX override {ovr:g} for USD->{base} is outside the ±{FX_CONSERVATIVE_BAND:.0%} "
            f"conservative band around the benchmark {benchmark} ([{lo:.4f}, {hi:.4f}]).")
    return ovr


def fx_meta(base_currency: str, override: Optional[float] = None,
            benchmark: Optional[float] = None,
            benchmark_ref: Optional[str] = None) -> dict:
    """The FX assumption as a provenanced object for the cost basis. Default rate is an
    external benchmark; a caller/CFO override (within the band) is a sponsor assumption.

    `benchmark_ref` is the registry `ref_id` the bridge resolved, so the artefact names
    the governed row that priced it rather than just the number.
    """
    base = (base_currency or "EUR").upper()
    overridden = override is not None
    rate = usd_to_base_rate(base, override, benchmark)   # validates the ±band
    return {
        "pair": f"USD->{base}",
        "rate": rate,
        "provenance": (ProvenanceClass.SPONSOR_ASSUMPTION.value if overridden
                       else ProvenanceClass.EXTERNAL_BENCHMARK.value),
        "source": "caller/CFO override" if overridden else FX_SOURCE,
        "conservative_band": FX_CONSERVATIVE_BAND if overridden else None,
        "base_year": OPENPYTEA_TARGET_CEPCI_YEAR,
        # Which benchmark the band was computed against, and whether it was governed.
        "benchmark": fx_benchmark(base, benchmark),
        "benchmark_governed_by": benchmark_ref,
        "benchmark_provenance": ("reference_registry" if benchmark_ref
                                 else "engine_default"),
    }


def cost_basis_block(base_currency: str, cost_year: Optional[int], is_stub: bool,
                     fx: Optional[dict] = None, engine: Optional[str] = None,
                     engine_version: Optional[str] = None,
                     correlation_set: Optional[dict] = None) -> dict:
    if is_stub:
        return {"currency": (base_currency or "EUR").upper(), "cost_year": None,
                "cepci_basis": None, "fx_normalised": False, "fx": None,
                "engine": engine, "engine_version": engine_version,
                # Present and None, never absent: a consumer must not have to handle
                # two different shapes. The stub prices from sizing arithmetic, so
                # there is no published cost data to pin.
                "correlation_set": None,
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
    if engine_version:
        # The priced numbers move with the engine, so the engine is part of the basis
        # (see cost_basis_hash). An upgrade must be visible on the artefact itself.
        note += f" Priced by {engine or 'openpytea'} {engine_version}."
    return {
        "currency": base,
        "cost_year": cost_year,
        "cepci_basis": f"CEPCI {cost_year}" if cost_year else None,
        "fx_normalised": True,
        "fx": fx,
        "engine": engine,
        "engine_version": engine_version,
        # Which published cost data priced this basis (point 2). A pin, not a
        # parameter: these are literature constants and are not editable.
        "correlation_set": correlation_set,
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
