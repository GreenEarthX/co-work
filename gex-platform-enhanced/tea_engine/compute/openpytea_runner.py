"""openpytea_runner — runs OpenPyTEA and shapes the result for GEX.

OpenPyTEA is an OPTIONAL dependency. Three execution modes:
  · OpenPyTEA installed                         → real run            (TODO: wire API)
  · TEA_STUB=1 (or OpenPyTEA absent + stub ok)  → deterministic stub  (demo/CI)
  · OpenPyTEA absent and stub not allowed        → RuntimeError → 503

The stub is deterministic (CAPEX scales with total equipment sizing) so the
contract is exercisable end-to-end without the heavy dependency. It is clearly
labelled engine="stub" so a stub result can never be mistaken for a real one.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading

from tea_engine.models import (
    EvidenceEntryProposal,
    LcopStats,
    PlantSummaryExtract,
    SensitivityVar,
    TEAComputeRequest,
    TEAMonteCarloRequest,
    TEAMonteCarloResult,
    TEAResult,
    TEASensitivityResult,
)

try:  # optional
    import openpytea  # type: ignore
    _HAS_OPENPYTEA = True
except Exception:  # pragma: no cover
    openpytea = None  # type: ignore
    _HAS_OPENPYTEA = False

if _HAS_OPENPYTEA:
    # Completes openpytea's CEPCI series where its own cost correlations
    # reference years its data file omits (see cepci_extension for the why).
    # Import for side effect, before any Equipment is constructed.
    from tea_engine import cepci_extension  # noqa: F401


def _stub_allowed() -> bool:
    return os.getenv("TEA_STUB", "0") == "1"


def engine_name() -> str:
    return "openpytea" if (_HAS_OPENPYTEA and not _stub_allowed()) else "stub"


def cost_basis_hash(req: TEAComputeRequest) -> str:
    blob = json.dumps(req.model_dump(), sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:24]


def _ensure_runnable() -> None:
    if not _HAS_OPENPYTEA and not _stub_allowed():
        raise RuntimeError(
            "OpenPyTEA is not installed and TEA_STUB is not enabled. "
            "Install openpytea in this service image, or set TEA_STUB=1 for "
            "deterministic stub output."
        )


def resolve_process_function(req: TEAComputeRequest):
    """Resolve the equipment train + variable_opex_inputs for this request.

    If the caller supplied process_units, use them (caller-owned basis). Otherwise
    derive the molecule's CANONICAL process function from fuel_id — this is the
    'ascertain the process function for each molecule' step. Raises if neither a
    train nor a defined process function exists (no fictional economics).

    Returns (units: list[ProcessUnitSpec], variable_opex_inputs: dict, meta|None).
    """
    from tea_engine.models import ProcessUnitSpec
    import tea_engine.process_functions as pfx

    a = req.assumptions
    if req.process_units:
        var_opex = req.variable_opex_inputs or {
            "electricity": {"consumption": 1.0, "price": a.electricity_eur_mwh}
        }
        return list(req.process_units), var_opex, None

    nameplate_t_yr = _nameplate_t_per_year(req)
    built = pfx.build_process_function(req.fuel_id, nameplate_t_yr)
    units = [ProcessUnitSpec(**u) for u in built["process_units"]]
    # fill prices from assumptions into the stoichiometric skeleton
    var_opex = {}
    for stream, cfg in built["variable_opex_inputs"].items():
        var_opex[stream] = {"consumption": cfg["consumption"],
                            "price": float(getattr(a, cfg["price_field"]))}
    return units, var_opex, built["meta"]


def _stub_numbers(req: TEAComputeRequest, units) -> tuple[float, float, float]:
    """Deterministic, sizing-driven illustrative economics."""
    total_sizing = sum(u.sizing for u in units) or 1.0
    capex = total_sizing * 6200.0 * (1 + req.assumptions.contingency_pct / 100.0)
    opex = capex * 0.11 + req.assumptions.electricity_eur_mwh * req.nameplate_capacity * 1.2
    annual_output = req.nameplate_capacity * req.assumptions.capacity_factor
    crf = (req.assumptions.discount_rate_pct / 100.0)  # simplified capital recovery
    lcop = ((capex * crf) + opex) / max(annual_output, 1.0)
    return round(capex, 2), round(opex, 2), round(lcop, 2)


def _nameplate_t_per_year(req: TEAComputeRequest) -> float:
    # G2: normalise through the canonical unit table; an unknown unit RAISES
    # (→ 422) rather than being silently read as t/yr (the 1000×/365× trap).
    from tea_engine import integrity
    return integrity.to_t_per_year(req.nameplate_capacity, req.nameplate_unit)


def _nameplate_kg_per_day(req: TEAComputeRequest) -> float:
    """OpenPyTEA plant_products production is kg/day. Convert from the request unit."""
    return _nameplate_t_per_year(req) * 1000.0 / 365.0


def _correlation_index() -> dict[tuple[str, str], None]:
    """(category, type) pairs OpenPyTEA can actually cost, from its own CSV."""
    import csv
    import glob
    import os

    import openpytea

    pkg = os.path.dirname(openpytea.__file__)
    matches = glob.glob(os.path.join(pkg, "**", "cost_correlations.csv"), recursive=True)
    if not matches:
        return {}
    with open(matches[0]) as fh:
        return {(r["category"], r["type"]): None for r in csv.DictReader(fh)}


def _validate_equipment(units) -> None:
    """Reject an uncostable equipment spec BEFORE OpenPyTEA raises KeyError.

    OpenPyTEA validates `material` itself and raises ValueError with the valid
    options (→ 422). It does NOT do the same for category/type: an unknown pair
    escapes as a bare KeyError telling the caller to 'add a row to the CSV' —
    engine-internal advice that reached the API as an opaque 500. Same class of
    bad input, so it gets the same clean answer.
    """
    index = _correlation_index()
    if not index:
        return  # cannot introspect — let OpenPyTEA speak for itself

    for u in units:
        if (u.category, u.equipment_type) in index:
            continue
        valid_types = sorted(t for c, t in index if c == u.category)
        if valid_types:
            raise ValueError(
                f"Unknown equipment_type {u.equipment_type!r} for category "
                f"{u.category!r} (unit {u.id!r}). Valid options are: {valid_types}"
            )
        raise ValueError(
            f"Unknown equipment category {u.category!r} (unit {u.id!r}). "
            f"Valid options are: {sorted({c for c, _ in index})}"
        )


def _build_plant(req: TEAComputeRequest, units, var_opex, extra_config: dict | None = None):
    """Assemble (not calculate) the OpenPyTEA Plant for a request. Shared by the point
    estimate and the Monte Carlo so both run on the identical plant — same equipment,
    currency, FX, utilisation. Returns (plant, base_currency)."""
    from openpytea.equipment import Equipment
    from openpytea.plant import Plant

    _validate_equipment(units)

    equipment = [
        Equipment(
            name=(u.id[:8] or f"EQ{i}").upper(),
            param=u.sizing,
            process_type=u.process_type,
            category=u.category,
            type=u.equipment_type,
            material=u.material,
        )
        for i, u in enumerate(units)
    ]

    from tea_engine import integrity
    a = req.assumptions
    base_ccy = (req.base_currency or "EUR").upper()
    # G5: OpenPyTEA correlations are USD — convert the CAPITAL side to the project's
    # base currency via exchange_rate (a fixed dated rate, or the caller/CFO override).
    # exchange_rate touches only purchased/direct cost; variable OPEX (GEX's already-
    # base-currency feedstock prices) is untouched, so nothing is double-converted.
    fx_rate = integrity.usd_to_base_rate(base_ccy, req.fx_usd_to_eur)
    config = {
        "name": req.pathway_id,
        "country": req.country,
        "process_type": req.plant_process_type,
        "equipment": equipment,
        "currency": base_ccy,
        "exchange_rate": fx_rate,
        "interest_rate": a.discount_rate_pct / 100.0,
        "plant_utilization": a.capacity_factor,
        "project_lifetime": a.project_life_years,
        "plant_products": {req.fuel_id.lower(): {"production": _nameplate_kg_per_day(req)}},
        "variable_opex_inputs": var_opex,
    }
    if extra_config:
        config.update(extra_config)
    return Plant(config), base_ccy


def _real_numbers(req: TEAComputeRequest, units, var_opex) -> tuple[float, float, float, str]:
    """Run the real OpenPyTEA plant TEA and extract (capex, opex/yr, lcop, currency)."""
    plant, base_ccy = _build_plant(req, units, var_opex)
    plant.calculate_all()
    d = plant.to_dict()

    capex = float(d["capital_costs"]["fixed_capital"])
    opex = float(d["variable_opex"]["total"]) + float(d["fixed_opex"]["total"])
    lcop = float(d["metrics"]["levelized_cost"])
    return round(capex, 2), round(opex, 2), round(lcop, 4), base_ccy


def run_tea(req: TEAComputeRequest) -> TEAResult:
    from tea_engine import integrity
    _ensure_runnable()
    cbh = cost_basis_hash(req)
    nameplate_t = _nameplate_t_per_year(req)   # G2: validates the unit up front (→ 422 on unknown)
    integrity.usd_to_base_rate((req.base_currency or "EUR").upper(), req.fx_usd_to_eur)  # G5: fx band (→ 422)
    units, var_opex, pf_meta = resolve_process_function(req)

    if _HAS_OPENPYTEA and not _stub_allowed():
        capex, opex, lcop, currency = _real_numbers(req, units, var_opex)
        is_stub = False
    else:
        capex, opex, lcop = _stub_numbers(req, units)
        currency, is_stub = (req.base_currency or "EUR").upper(), True

    # Co-product revenue credit — the plant sells diesel/naphtha/etc. alongside the
    # primary product. Credit it against OPEX so the TEA treats co-products the same
    # way the LCA allocates GHG to them (consistent, mass-balanced basis).
    coproduct_credit = 0.0
    if pf_meta and pf_meta.get("coproduct_revenue_per_t_primary"):
        annual_primary = _nameplate_t_per_year(req) * req.assumptions.capacity_factor
        coproduct_credit = pf_meta["coproduct_revenue_per_t_primary"] * annual_primary
        opex = round(opex - coproduct_credit, 2)
        # LCOP recomputed net of co-product revenue (per unit of primary product)
        lcop = round(lcop - coproduct_credit / max(annual_primary, 1.0) / 1000.0, 4)

    # Regulatory-regime fork (certification / GHG method / subsidy) by pathway_class.
    regime = None
    if pf_meta:
        import tea_engine.regimes as rg
        regime = rg.as_dict(rg.get_regime(pf_meta.get("pathway_class", "RFNBO")))

    # G2/G1: physically-implausible-output flags + input provenance → a result
    # status that tracks input QUALITY, not just that the arithmetic ran.
    plausibility = integrity.plausibility_flags(capex, nameplate_t, lcop)
    plausibility = plausibility + integrity.scaling_flags(pf_meta)   # G4: extreme scale extrapolation
    input_provenance = integrity.classify_inputs(req.assumptions)
    status = integrity.result_status(input_provenance, plausibility)

    # G5: currency / base-date basis. OpenPyTEA's USD costs are converted to the base
    # currency with a fixed dated rate (or the caller/CFO override); the rate carries
    # its own provenance (external_benchmark, or sponsor_assumption when overridden).
    fx = None if is_stub else integrity.fx_meta(currency, req.fx_usd_to_eur)
    cost_basis = integrity.cost_basis_block(
        currency, None if is_stub else integrity.OPENPYTEA_TARGET_CEPCI_YEAR, is_stub, fx)
    # G6: what the cost covers — canonical battery limits vs an unverified caller train.
    import tea_engine.process_functions as _pfx
    calc_boundary = integrity.calculation_boundary(
        pf_meta, len(units), req.fuel_id,
        _pfx.canonical_equipment_count(req.fuel_id), _pfx.canonical_nodes(req.fuel_id))

    return TEAResult(
        engine=engine_name(),
        cost_basis_hash=cbh,
        lcop=lcop,
        plant_summary=PlantSummaryExtract(
            capex_eur=capex,
            opex_eur_per_year=opex,
            nameplate_capacity=req.nameplate_capacity,
            nameplate_unit=req.nameplate_unit,
        ),
        run_evidence=EvidenceEntryProposal(payload={
            "cost_basis_hash": cbh,
            "engine": engine_name(),
            "project_id": req.project_id,
            "pathway_id": req.pathway_id,
            "capex_eur": capex,
            "opex_eur_per_year": opex,
            "lcop": lcop,
            "process_function": pf_meta,
            "regime": regime,
            "result_status": status,
            "input_provenance": input_provenance,
            "plausibility": plausibility,
            "cost_basis": cost_basis,
            "calculation_boundary": calc_boundary,
        }),
        process_function=pf_meta,
        regime=regime,
        result_status=status,
        input_provenance=input_provenance,
        plausibility=plausibility,
        cost_basis=cost_basis,
        calculation_boundary=calc_boundary,
    )


def run_sensitivity(req: TEAComputeRequest) -> TEASensitivityResult:
    _ensure_runnable()
    base = run_tea(req)
    base_lcop = base.lcop

    # One-way ±20% sweep. Each point re-runs run_tea, so this is real OpenPyTEA
    # economics when the engine is installed (no reliance on openpytea.analysis
    # plotting fns, which render matplotlib — unfit for a headless service).
    # We perturb levers that ACTUALLY bind the real Plant: plant_utilization
    # (capacity_factor) and each variable_opex_inputs stream price. Perturbing
    # assumptions.electricity_eur_mwh would be a no-op in real mode (the real
    # electricity cost lives in variable_opex_inputs). Monte-Carlo can be added
    # later via openpytea.analysis.monte_carlo.
    def _capacity(r, f):
        r.assumptions.capacity_factor = min(r.assumptions.capacity_factor * f, 1.0)

    def _stream_price(stream):
        def setter(r, f):
            r.variable_opex_inputs[stream]["price"] = req.variable_opex_inputs[stream]["price"] * f
        return setter

    def _assumption_price(field):
        def setter(r, f):
            setattr(r.assumptions, field, getattr(req.assumptions, field) * f)
        return setter

    levers: list[tuple[str, Any]] = [("capacity_factor", _capacity)]
    if req.process_units:
        # caller-supplied train → perturb the supplied stream prices
        for stream, cfg in (req.variable_opex_inputs or {}).items():
            if isinstance(cfg, dict) and "price" in cfg:
                levers.append((f"price:{stream}", _stream_price(stream)))
    else:
        # registry-derived train → feedstock prices live in the assumptions; perturb
        # only the fields the molecule's process function actually consumes.
        import tea_engine.process_functions as pfx
        pf = pfx.get(req.fuel_id)
        fields = {fs.price_field for fs in pf.feedstocks} if pf else set()
        for field in sorted(fields):
            levers.append((f"price:{field}", _assumption_price(field)))
    if len(levers) == 1:  # stub path / nothing else to perturb
        levers.append(("electricity_eur_mwh", _assumption_price("electricity_eur_mwh")))

    tornado = []
    for name, apply in levers:
        lo = req.model_copy(deep=True); hi = req.model_copy(deep=True)
        apply(lo, 0.8); apply(hi, 1.2)
        tornado.append(SensitivityVar(
            parameter=name,
            low_lcop=run_tea(lo).lcop,
            high_lcop=run_tea(hi).lcop,
        ))

    return TEASensitivityResult(
        engine=engine_name(),
        cost_basis_hash=base.cost_basis_hash,
        base_lcop=base_lcop,
        tornado=tornado,
        run_evidence=base.run_evidence,
    )


# ── Monte Carlo (OpenPyTEA analysis.monte_carlo, headless) ──────────────────────
# GEX default uncertainty for inputs OpenPyTEA holds fixed by default (every variable-
# OPEX price, capacity factor): 10% relative σ truncated at ±2σ — the same ±20% band the
# one-way tornado uses. Without it the dominant drivers (H2, power) are not sampled and
# the band comes out falsely narrow — the false precision this endpoint exists to cure.
MC_DEFAULT_REL_STD = 0.10
MC_MAX_REL_STD = 0.50
# UPSTREAM BUG — OpenPyTEA 2.1.0 (verified 2026-09-22): with project_lifetime sampled as
# an array, the vectorised Monte Carlo levelises EVERY sample over the longest horizon —
# samples at 10 y and at 30 y return the same LCOP — biasing the band ~6% LOW. Every
# other vectorised input (interest, utilisation, prices, capital factor) was checked
# per-sample against deterministic runs and is correct. GEX therefore holds lifetime
# fixed and refuses a request to sample it; test_openpytea_mc_lifetime_bug_canary fails
# the day upstream fixes it, which is the signal to re-enable.
MC_LIFETIME_HELD = ("project lifetime — held at the point-estimate value: OpenPyTEA 2.1.0's "
                    "vectorised Monte Carlo levelises every sample over the longest sampled "
                    "horizon (samples at 10 y and 30 y return the same LCOP), which would "
                    "bias the band low. Test lifetime with deterministic /tea/compute runs.")
# OpenPyTEA samples via scipy truncnorm with no random_state, i.e. numpy's GLOBAL RNG.
# Seed under a lock and restore the state afterwards, or concurrent requests interleave
# draws and neither result is reproducible.
_MC_LOCK = threading.Lock()


def _band(mean: float, rel: float, lo: float | None = None, hi: float | None = None) -> dict:
    """Truncated-normal spec: σ = rel·|mean|, bounds mean ± 2σ (clipped to [lo, hi])."""
    if rel <= 0:
        return {"std": 0.0}
    std = abs(mean) * rel
    low, high = mean - 2 * std, mean + 2 * std
    if lo is not None:
        low = max(lo, low)
    if hi is not None:
        high = min(hi, high)
    return {"std": std, "min": low, "max": high}


def _engine_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("openpytea")
    except Exception:  # pragma: no cover
        return None


def run_monte_carlo(req: TEAMonteCarloRequest) -> TEAMonteCarloResult:
    _ensure_runnable()
    if not (_HAS_OPENPYTEA and not _stub_allowed()):
        raise NotImplementedError(
            "Monte Carlo needs the real OpenPyTEA engine — the deterministic stub has no "
            "distribution to sample.")
    import numpy as np
    from openpytea.analysis import monte_carlo

    # 1) Point estimate on the plain compute inputs: identical cost_basis_hash to
    #    /tea/compute (so the two link), and every integrity check (unit, FX band,
    #    plausibility, provenance) runs exactly as it does there.
    base_req = TEAComputeRequest.model_validate(
        req.model_dump(include=set(TEAComputeRequest.model_fields), exclude_unset=True))
    base = run_tea(base_req)

    # 2) Uncertainty spec. An unknown stream or an out-of-range σ is refused, not
    #    silently ignored — a typo must not quietly narrow the band.
    units, var_opex, pf_meta = resolve_process_function(base_req)
    unknown = set(req.price_rel_std) - set(var_opex)
    if unknown:
        raise ValueError(f"price_rel_std names unknown stream(s) {sorted(unknown)}; "
                         f"streams in this run: {sorted(var_opex)}")
    for s, rel in req.price_rel_std.items():
        if not (0 <= float(rel) <= MC_MAX_REL_STD):
            raise ValueError(f"price_rel_std[{s!r}]={rel} must be within [0, {MC_MAX_REL_STD}]")
    mc_opex = {
        stream: {**cfg, **_band(float(cfg["price"]),
                                float(req.price_rel_std.get(stream, MC_DEFAULT_REL_STD)), lo=0.0)}
        for stream, cfg in var_opex.items()
    }
    pu = dict(req.project_uncertainties)          # explicit OpenPyTEA spec wins
    lt_spec = pu.get("project_lifetime")
    if lt_spec is not None and float((lt_spec or {}).get("std", 5) or 0) > 0:
        raise ValueError("project_lifetime cannot be sampled: " + MC_LIFETIME_HELD)
    pu["project_lifetime"] = {"std": 0}           # held fixed — upstream bug, see above
    if "plant_utilization" not in pu:
        rel = (req.capacity_factor_rel_std if req.capacity_factor_rel_std is not None
               else MC_DEFAULT_REL_STD)
        pu["plant_utilization"] = _band(float(base_req.assumptions.capacity_factor), rel,
                                        lo=0.01, hi=1.0)
    plant, base_ccy = _build_plant(base_req, units, mc_opex,
                                   extra_config={"project_uncertainties": pu})

    # 3) Seeded, serialised, RNG-state-preserving run. No progress bar in a service: tqdm
    #    reads TQDM_DISABLE at import, so the bar is switched off on the module instead.
    import functools
    import openpytea.analysis as _opa
    n = req.num_samples
    with _MC_LOCK:
        state = np.random.get_state()
        orig_tqdm = _opa.tqdm
        _opa.tqdm = functools.partial(orig_tqdm, disable=True)
        try:
            np.random.seed(req.seed)
            mc = monte_carlo(plant, num_samples=n, batch_size=min(1000, n))
        finally:
            _opa.tqdm = orig_tqdm
            np.random.set_state(state)

    # 4) Same co-product credit as the point estimate (a constant per-kg shift).
    shift = (pf_meta["coproduct_revenue_per_t_primary"] / 1000.0
             if pf_meta and pf_meta.get("coproduct_revenue_per_t_primary") else 0.0)
    lcop = np.asarray(mc["metrics"]["LCOP"], dtype=float) - shift
    valid = lcop[np.isfinite(lcop)]
    if valid.size == 0:
        raise ValueError("Monte Carlo produced no finite LCOP samples — check the inputs.")

    p5, p10, p50, p90, p95 = (float(x) for x in np.percentile(valid, [5, 10, 50, 90, 95]))
    stats = LcopStats(
        mean=round(float(valid.mean()), 4), std=round(float(valid.std()), 4),
        p5=round(p5, 4), p10=round(p10, 4), p50=round(p50, 4),
        p90=round(p90, 4), p95=round(p95, 4),
        min=round(float(valid.min()), 4), max=round(float(valid.max()), 4))
    counts, edges = np.histogram(valid, bins=20)

    # 5) Provenance of every varied input — what was actually sampled, and who said so.
    stream_of = {f"{k.replace('_', ' ').title()} price": k for k in var_opex}
    pu_key = {"Fixed capital factor": "fixed_capital_factor",
              "Fixed opex factor": "fixed_opex_factor",
              "Project lifetime": "project_lifetime",
              "Interest rate": "interest_rate",
              "Tax rate": "tax_rate"}
    gex_default = f"GEX default: {MC_DEFAULT_REL_STD:.0%} relative σ, truncated ±2σ"
    basis = []
    held_fixed = [MC_LIFETIME_HELD]
    for name, arr in mc["inputs"].items():
        a = np.asarray(arr, dtype=float)
        if float(a.std()) == 0.0:                 # not varied — list it, don't dress it up
            if name != "Project lifetime":
                held_fixed.append(f"{name.lower()} (σ = 0)")
            continue
        if name in stream_of:
            caller = stream_of[name] in req.price_rel_std
            src = "caller price_rel_std" if caller else gex_default
        elif name == "Plant utilization":
            caller = ("plant_utilization" in req.project_uncertainties
                      or req.capacity_factor_rel_std is not None)
            src = "caller override" if caller else gex_default
        elif name in pu_key:
            caller = pu_key[name] in req.project_uncertainties
            src = "caller project_uncertainties" if caller else "OpenPyTEA default"
        else:                                     # operator hourly rate — GEX doesn't set it
            caller, src = False, "OpenPyTEA default"
        basis.append({
            "input": name, "distribution": "truncated normal",
            "mean": round(float(a.mean()), 6), "std": round(float(a.std()), 6),
            "min": round(float(a.min()), 6), "max": round(float(a.max()), 6),
            "source_class": "sponsor_assumption" if caller else "model_default",
            "source": src,
        })

    mc_hash = "sha256:" + hashlib.sha256(json.dumps({
        "cost_basis_hash": base.cost_basis_hash, "num_samples": n, "seed": req.seed,
        "price_rel_std": req.price_rel_std,
        "capacity_factor_rel_std": req.capacity_factor_rel_std,
        "project_uncertainties": req.project_uncertainties,
    }, sort_keys=True, default=str).encode()).hexdigest()[:24]

    target = req.target_lcop
    return TEAMonteCarloResult(
        engine=engine_name(), engine_version=_engine_version(),
        cost_basis_hash=base.cost_basis_hash, mc_hash=mc_hash,
        seed=req.seed, num_samples=n, num_valid=int(valid.size),
        currency=base_ccy, base_lcop=base.lcop, lcop=stats,
        target_lcop=target,
        p_lcop_le_target=(round(float((valid <= target).mean()), 4)
                          if target is not None else None),
        histogram={"bin_edges": [round(float(e), 4) for e in edges],
                   "counts": [int(c) for c in counts]},
        uncertainty_basis=basis,
        held_fixed=held_fixed + [
            "equipment cost correlations (varied only through the global fixed-capital factor)",
            "process stoichiometry, conversion yield and feedstock consumption rates",
            "nameplate capacity and the process boundary",
            "co-product prices / credit",
            "FX rate and CEPCI escalation",
        ],
        base_result_status=base.result_status,
        plausibility=base.plausibility,
    )
