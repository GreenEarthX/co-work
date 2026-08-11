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
    PlantSummaryExtract,
    SensitivityVar,
    TEAComputeRequest,
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
    unit = req.nameplate_unit.lower()
    if "kt_per_year" in unit:
        return req.nameplate_capacity * 1000.0
    return req.nameplate_capacity                  # assume t/yr


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


def _real_numbers(req: TEAComputeRequest, units, var_opex) -> tuple[float, float, float]:
    """Run the real OpenPyTEA plant TEA and extract (capex, opex/yr, lcop)."""
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

    a = req.assumptions
    plant = Plant({
        "name": req.pathway_id,
        "country": req.country,
        "process_type": req.plant_process_type,
        "equipment": equipment,
        "interest_rate": a.discount_rate_pct / 100.0,
        "plant_utilization": a.capacity_factor,
        "project_lifetime": a.project_life_years,
        "plant_products": {req.fuel_id.lower(): {"production": _nameplate_kg_per_day(req)}},
        "variable_opex_inputs": var_opex,
    })
    plant.calculate_all()
    d = plant.to_dict()

    capex = float(d["capital_costs"]["fixed_capital"])
    opex = float(d["variable_opex"]["total"]) + float(d["fixed_opex"]["total"])
    lcop = float(d["metrics"]["levelized_cost"])
    return round(capex, 2), round(opex, 2), round(lcop, 4)


def run_tea(req: TEAComputeRequest) -> TEAResult:
    _ensure_runnable()
    cbh = cost_basis_hash(req)
    units, var_opex, pf_meta = resolve_process_function(req)

    if _HAS_OPENPYTEA and not _stub_allowed():
        capex, opex, lcop = _real_numbers(req, units, var_opex)
    else:
        capex, opex, lcop = _stub_numbers(req, units)

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
        }),
        process_function=pf_meta,
        regime=regime,
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
