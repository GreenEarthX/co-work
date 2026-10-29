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


def _engine_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("openpytea")
    except Exception:  # pragma: no cover
        return None


def _version_tuple(v: str | None) -> tuple:
    """(3, 0, 0) from "3.0.0", and from "3.0.0rc1" / "3.0.0.post1" too — a pre-release
    of 3.0 still carries the `random_seed` parameter, so refusing it would be a false
    alarm. Unknown/unparseable sorts lowest, so a version we cannot read fails the
    minimum check rather than passing it."""
    import re
    parts = []
    for p in (v or "").split(".")[:3]:
        m = re.match(r"\d+", p)
        if not m:
            break
        parts.append(int(m.group()))
    return tuple(parts)


def cost_basis_hash(req: TEAComputeRequest) -> str:
    """The identity of a cost basis is the request AND the engine that priced it.

    The request alone is not enough. Measured 2026-09-23: OpenPyTEA 2.1.0 -> 3.0.0
    moved e-methanol CAPEX +2.0% (171,833,372 -> 175,255,929) on byte-identical
    inputs while this hash stayed at sha256:61a2cbc34aff5b64cb138456. A verified
    model_base_case would have changed meaning with nothing to show for it. The
    engine and its version are part of the basis, so an upgrade surfaces as a new
    hash instead of hiding inside the old one.
    """
    # The engine VERSION is not enough: two installs of the same version can carry
    # different cost data (a vendored tree, a patched wheel, a local build), and
    # cepci_extension mutates the CEPCI series in memory. So the fingerprint of the
    # data that actually priced the basis is hashed too — point 2 of the 2026-10-26
    # plan. On the stub path there is no cost data, so there is nothing to pin.
    from tea_engine.correlation_set import set_hash as _set_hash
    # The escalation basis is part of the cost basis: a different target year or a
    # different index provider prices the same equipment differently. Measured
    # 2026-10-26 before this line existed: a 2025 cost base moved capex +3.2% under an
    # unchanged hash.
    _esc = None
    if not _stub_allowed():
        from tea_engine import escalation as _e
        _esc = {"provider": _e.active_provider().name, "target_year": _e.target_year()}
    blob = json.dumps({"request": req.model_dump(),
                       "engine": engine_name(),
                       "engine_version": _engine_version(),
                       "correlation_set": (None if _stub_allowed() else _set_hash()),
                       "escalation": _esc},
                      sort_keys=True, default=str).encode()
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
    # A governed train (migration 075) replaces the code registry's equipment. It
    # arrives in the request because the engine is stateless, which also puts it inside
    # cost_basis_hash — so an approved change to a base_param or a scale_exp reprices
    # visibly rather than silently.
    governed = None
    if req.governed_train:
        governed = [
            pfx.EquipmentSpec(
                role=str(e["role"]), node=str(e.get("node") or "synthesis"),
                category=str(e["category"]), type=str(e["equipment_type"]),
                material=str(e["material"]), base_param=float(e["base_param"]),
                scale_exp=float(e.get("scale_exp") or pfx.DEFAULT_SCALE_EXP),
            )
            for e in req.governed_train
        ]
    built = pfx.build_process_function(req.fuel_id, nameplate_t_yr,
                                       equipment=governed,
                                       capacity_factor=a.capacity_factor)
    if built.get("meta") is not None:
        built["meta"]["train_basis"] = ("governed" if governed else "canonical_code")
        built["meta"]["governed_train_version"] = req.governed_train_version
    units = [ProcessUnitSpec(**u) for u in built["process_units"]]
    # fill prices from assumptions into the stoichiometric skeleton
    var_opex = {}
    for stream, cfg in built["variable_opex_inputs"].items():
        var_opex[stream] = {"consumption": cfg["consumption"],
                            "price": float(getattr(a, cfg["price_field"]))}
    return units, var_opex, built["meta"]


def _stub_numbers(req: TEAComputeRequest, units) -> tuple[float, float, float]:
    """Deterministic, sizing-driven illustrative economics.

    The nameplate is canonicalised FIRST. This used to divide by the raw
    `req.nameplate_capacity` with its unit discarded, so the same physical plant
    returned a different LCOP per spelling and in the wrong unit entirely — measured
    2026-10-26 for one 50 kt/yr plant: 't_per_year' gave 5,967.16 where the correct
    EUR/kg figure is 5.967 (ratio 1000), 'mtpd' was out by 365,000 (= 1000 kg/t x 365
    d/yr) and 'kt_per_year' by 1,000,000. Capex was unaffected because it is driven by
    the canonicalised equipment sizing, which is why the error showed up only in LCOP.

    The stub's LCOP is handed to `plausibility_flags` as a EUR/kg value and is labelled
    `engine="stub"`, so it must be on the same basis as the real path: EUR per kilogram
    of product, over the canonical annual output in kilograms.
    """
    total_sizing = sum(u.sizing for u in units) or 1.0
    nameplate_t_yr = _nameplate_t_per_year(req)          # raises on an unknown unit
    capex = total_sizing * 6200.0 * (1 + req.assumptions.contingency_pct / 100.0)
    # electricity term scales with annual tonnage, not with whatever magnitude the
    # caller happened to spell the nameplate in
    opex = capex * 0.11 + req.assumptions.electricity_eur_mwh * nameplate_t_yr * 1.2
    annual_output_kg = nameplate_t_yr * 1000.0 * req.assumptions.capacity_factor
    crf = (req.assumptions.discount_rate_pct / 100.0)  # simplified capital recovery
    lcop = ((capex * crf) + opex) / max(annual_output_kg, 1.0)
    return round(capex, 2), round(opex, 2), round(lcop, 4)


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

    # The cost base is passed EXPLICITLY. It used to be left to OpenPyTEA's own default
    # of 2024 while integrity.OPENPYTEA_TARGET_CEPCI_YEAR labelled the basis separately:
    # the two agreed by coincidence, so moving the GEX constant would have moved the
    # LABEL while the arithmetic stood still. escalation.target_year() is now the single
    # answer, and it refuses a year the escalation series does not cover rather than
    # letting OpenPyTEA raise from inside inflation_adjustment without naming the year.
    from tea_engine import escalation
    escalation.apply()                     # a provider may supply years CEPCI lacks
    _target_year = escalation.target_year()

    equipment = [
        Equipment(
            name=(u.id[:8] or f"EQ{i}").upper(),
            param=u.sizing,
            process_type=u.process_type,
            category=u.category,
            type=u.equipment_type,
            material=u.material,
            target_year=_target_year,
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
    fx_rate = integrity.usd_to_base_rate(base_ccy, req.fx_usd_to_eur,
                                         req.fx_benchmark_usd_to_eur)
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


def _escalation_target_year() -> int:
    """The cost base, from the same source the Equipment construction uses."""
    from tea_engine import escalation
    return escalation.target_year()


def _correlation_set_block() -> dict:
    """The fingerprint, trimmed for the artefact: the pin plus what identifies it."""
    from tea_engine.correlation_set import fingerprint
    f = fingerprint()
    return {k: f[k] for k in ("hash", "openpytea_version", "correlations",
                              "cepci_year_range", "gex_supplied_cepci_years")}


def run_tea(req: TEAComputeRequest) -> TEAResult:
    from tea_engine import integrity
    _ensure_runnable()
    cbh = cost_basis_hash(req)
    nameplate_t = _nameplate_t_per_year(req)   # G2: validates the unit up front (→ 422 on unknown)
    integrity.usd_to_base_rate((req.base_currency or "EUR").upper(), req.fx_usd_to_eur,
                               req.fx_benchmark_usd_to_eur)   # G5: fx band (→ 422)
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
    plausibility = integrity.plausibility_flags(
        capex, nameplate_t, lcop,
        governed_lcop_band=((req.lcop_band_low, req.lcop_band_high)
                            if req.lcop_band_low is not None
                            and req.lcop_band_high is not None else None),
        governed_lcop_band_unit=req.lcop_band_unit)
    plausibility = plausibility + integrity.scaling_flags(pf_meta)   # G4: extreme scale extrapolation
    input_provenance = integrity.classify_inputs(req.assumptions)
    # The input-side sibling of plausibility_flags. Kept off `plausibility` so it does
    # not reclassify every basis as IMPLAUSIBLE (see TEAResult.mass_balance).
    mass_balance = None
    if pf_meta and pf_meta.get("mass_balance"):
        mass_balance = {**pf_meta["mass_balance"],
                        "flags": integrity.mass_balance_flags(pf_meta),
                        "energy_reconciliation": pf_meta.get("energy_reconciliation"),
                        "energy_flags": integrity.energy_balance_flags(pf_meta)}
    status = integrity.result_status(input_provenance, plausibility)

    # G5: currency / base-date basis. OpenPyTEA's USD costs are converted to the base
    # currency with a fixed dated rate (or the caller/CFO override); the rate carries
    # its own provenance (external_benchmark, or sponsor_assumption when overridden).
    fx = None if is_stub else integrity.fx_meta(
        currency, req.fx_usd_to_eur, req.fx_benchmark_usd_to_eur, req.fx_benchmark_ref_id)
    cost_basis = integrity.cost_basis_block(
        currency, None if is_stub else _escalation_target_year(), is_stub, fx,
        engine=engine_name(), engine_version=_engine_version(),
        correlation_set=(None if is_stub else _correlation_set_block()))
    # G6: what the cost covers — canonical battery limits vs an unverified caller train.
    import tea_engine.process_functions as _pfx
    calc_boundary = integrity.calculation_boundary(
        pf_meta, len(units), req.fuel_id,
        _pfx.canonical_equipment_count(req.fuel_id), _pfx.canonical_nodes(req.fuel_id))

    return TEAResult(
        engine=engine_name(),
        engine_version=_engine_version(),
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
            "engine_version": _engine_version(),
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
            "mass_balance": mass_balance,
            "cost_basis": cost_basis,
            "calculation_boundary": calc_boundary,
        }),
        process_function=pf_meta,
        regime=regime,
        result_status=status,
        input_provenance=input_provenance,
        mass_balance=mass_balance,
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
# Hard ceiling on any sigma, governed or not. The registry can move the
# default and the refusal ceiling within this; it cannot escape it.
MC_MAX_REL_STD_CEILING = 1.0
# Monte Carlo needs OpenPyTEA >= 3.0 for two reasons, both load-bearing:
#   · `random_seed` — 3.0 builds its own Generator per call. 2.x sampled through numpy's
#     global RNG, which this service seeded under a lock; that no longer reproduces.
#   · per-sample project lifetime — 2.1.0's vectorised MC levelised EVERY sample over the
#     longest sampled horizon (10 y and 30 y returned the same LCOP), biasing the band
#     low, so GEX held lifetime fixed. Fixed upstream in 3.0 and re-enabled here
#     (measured 2026-09-23: short-vs-long-life LCOP gap 0.0013 -> 0.6077).
MIN_OPENPYTEA_MC = (3, 0)
# OpenPyTEA floors sampled lifetimes with `.astype(int)` and refuses anything below 3
# (plant.py, calculate_cash_flow). Any band GEX hands it must stay above that after the
# cast, or /monte-carlo rejects a request /compute just accepted.
MIN_PROJECT_LIFETIME_YEARS = 3.0
_TQDM_SILENCED = False


def _silence_progress_bars() -> None:
    """A service has nowhere to print a progress bar, and tqdm reads TQDM_DISABLE at
    import — so the module attribute is patched instead. Once and permanently: the
    old save/patch/restore ran per call, which raced when two runs overlapped."""
    global _TQDM_SILENCED
    if not _TQDM_SILENCED:
        import functools
        import openpytea.analysis as _opa
        _opa.tqdm = functools.partial(_opa.tqdm, disable=True)
        _TQDM_SILENCED = True


def _mc_default_sigma(req) -> float:
    """The governed default relative sigma, else the engine constant.

    Bounded here as a source invariant: a registry row is approved by two people, but
    neither of them should be able to make every published band meaningless. 0 would
    collapse the band to the point estimate and silently restate a Monte Carlo as a
    deterministic run, which is the false precision this endpoint exists to cure.
    """
    v = getattr(req, "mc_default_rel_std", None)
    if v is None:
        return MC_DEFAULT_REL_STD
    v = float(v)
    if not (0 < v <= MC_MAX_REL_STD_CEILING):
        raise ValueError(
            f"governed tea_mc_default_rel_std={v} is outside (0, {MC_MAX_REL_STD_CEILING}] "
            f"— a zero sigma would report a deterministic run as a distribution.")
    return v


def _mc_max_sigma(req) -> float:
    """The governed refusal ceiling for a caller-supplied sigma, else the engine constant."""
    v = getattr(req, "mc_max_rel_std", None)
    if v is None:
        return MC_MAX_REL_STD
    v = float(v)
    if not (0 < v <= MC_MAX_REL_STD_CEILING):
        raise ValueError(
            f"governed tea_mc_max_rel_std={v} is outside (0, {MC_MAX_REL_STD_CEILING}].")
    return v


def _is_constant(a) -> bool:
    """Was this input actually held, at the scale it is measured on?

    An exact `std == 0.0` test misclassifies a constant whose magnitude is large:
    a vectorised constant carries float noise proportional to its own size, so
    `E Methanol production` (mean 136,986 kg) came back with std 2.9e-11 and was
    reported as SAMPLED, while `held_fixed` in the same response said the
    stoichiometry was held. The response contradicted itself. Scale-relative, so
    the verdict does not depend on the unit the quantity happens to be in.
    """
    import numpy as _np
    a = _np.asarray(a, dtype=float)
    return float(a.std()) <= 1e-9 * max(abs(float(a.mean())), 1.0)


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


def run_monte_carlo(req: TEAMonteCarloRequest) -> TEAMonteCarloResult:
    _ensure_runnable()
    if not (_HAS_OPENPYTEA and not _stub_allowed()):
        raise NotImplementedError(
            "Monte Carlo needs the real OpenPyTEA engine — the deterministic stub has no "
            "distribution to sample.")
    if _version_tuple(_engine_version()) < MIN_OPENPYTEA_MC:
        # Fail loudly rather than silently returning an unreproducible, low-biased band.
        raise RuntimeError(
            f"Monte Carlo requires OpenPyTEA >= 3.0 (installed: {_engine_version()}). "
            "3.0 added the `random_seed` parameter this service seeds with, and fixed the "
            "per-sample project-lifetime bug that biased 2.x bands low.")
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
        _max = _mc_max_sigma(req)
        if not (0 <= float(rel) <= _max):
            raise ValueError(f"price_rel_std[{s!r}]={rel} must be within [0, {_max}]")
    mc_opex = {
        stream: {**cfg, **_band(float(cfg["price"]),
                                float(req.price_rel_std.get(stream, _mc_default_sigma(req))), lo=0.0)}
        for stream, cfg in var_opex.items()
    }
    pu = dict(req.project_uncertainties)          # explicit OpenPyTEA spec wins
    if "project_lifetime" not in pu:
        # Anchored on the SPONSOR'S stated life, not OpenPyTEA's own 10-30 y default,
        # which ignores the project entirely. Same treatment as plant_utilization.
        # The floor is 3, not 1: OpenPyTEA casts sampled lifetimes with `.astype(int)`
        # and hard-refuses anything below 3 (plant.py, calculate_cash_flow). A floor of
        # 1 let a stated 3-year life draw 2.4 -> int 2 -> ValueError, so /compute
        # accepted a request that /monte-carlo then rejected quoting an engine-internal
        # message that contradicted the caller's own input.
        pu["project_lifetime"] = _band(float(base_req.assumptions.project_life_years),
                                       _mc_default_sigma(req), lo=MIN_PROJECT_LIFETIME_YEARS)
    if "plant_utilization" not in pu:
        rel = (req.capacity_factor_rel_std if req.capacity_factor_rel_std is not None
               else _mc_default_sigma(req))
        pu["plant_utilization"] = _band(float(base_req.assumptions.capacity_factor), rel,
                                        lo=0.01, hi=1.0)
    plant, base_ccy = _build_plant(base_req, units, mc_opex,
                                   extra_config={"project_uncertainties": pu})

    # 3) Seeded run. OpenPyTEA >= 3.0 takes `random_seed` and builds its own
    #    Generator from it, so the result depends on nothing outside this call:
    #    no global-RNG seeding, no state save/restore, no lock. Verified 2026-09-23 —
    #    perturbing numpy's global RNG between runs leaves the output bit-identical,
    #    and the seed alone reproduces it regardless of batch_size.
    n = req.num_samples
    _silence_progress_bars()
    mc = monte_carlo(plant, num_samples=n, batch_size=min(1000, n), random_seed=req.seed)

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
              "Interest rate": "interest_rate",
              "Tax rate": "tax_rate"}
    gex_default = f"GEX default: {MC_DEFAULT_REL_STD:.0%} relative σ, truncated ±2σ"
    basis = []
    held_fixed = []
    # Quantity risk is entirely absent from the band: yield_frac is not an OpenPyTEA
    # input, so it appears in neither mc["inputs"] nor the loop below. Say so, rather
    # than let the band imply it covered conversion uncertainty.
    _yf = (pf_meta or {}).get("yield_frac")
    if _yf is not None:
        held_fixed.append(
            f"conversion yield (yield_frac = {_yf}, sigma = 0, NOT sampled) — the band "
            f"covers price, utilisation and lifetime risk only, not quantity risk")
    for name, arr in mc["inputs"].items():
        a = np.asarray(arr, dtype=float)
        if name == "Project lifetime":
            # Report the horizons ACTUALLY levelised over, not the floats that were
            # drawn. OpenPyTEA casts with `.astype(int)` (plant.py, calculate_cash_flow),
            # so the raw samples overstate the band: measured at a stated 25 y, the
            # pre-floor array says max 27.75 y and mean 22.02 while every sample really
            # ran on an integer 20..27, mean 21.55. Reporting what was drawn would claim
            # a horizon no sample used.
            a = np.floor(a)
        if _is_constant(a):                       # not varied — list it, don't dress it up
            held_fixed.append(f"{name.lower()} (σ = 0)")
            continue
        if name in stream_of:
            caller = stream_of[name] in req.price_rel_std
            src = "caller price_rel_std" if caller else gex_default
        elif name == "Plant utilization":
            caller = ("plant_utilization" in req.project_uncertainties
                      or req.capacity_factor_rel_std is not None)
            src = "caller override" if caller else gex_default
        elif name == "Project lifetime":
            caller = "project_lifetime" in req.project_uncertainties
            src = ("caller project_uncertainties" if caller
                   else gex_default + ", anchored on the stated project life")
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
