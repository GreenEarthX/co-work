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

from tea_engine.correlation_set import current_category
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
        _esc = {"provider": _e.active_provider().name, "target_year": _e.request_target_year(req)}
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


def _current_units(units):
    return [u if current_category(u.category) == u.category
            else u.model_copy(update={"category": current_category(u.category)}) for u in units]


def category_renames(req: TEAComputeRequest) -> list[dict]:
    """The old OpenPyTEA category names this request used, each as a listed default."""
    named = [(u.id, u.category) for u in (req.process_units or [])]
    named += [(str(e.get("role")), str(e.get("category"))) for e in (req.governed_train or [])]
    return [{"name": f"category.{who}", "value": current_category(cat),
             "basis": f"RENAMED: OpenPyTEA 3.2 calls {cat!r} {current_category(cat)!r}; "
                      "same correlations, same coefficients"}
            for who, cat in named if current_category(cat) != cat]


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
        return _current_units(req.process_units), var_opex, None

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
                category=current_category(str(e["category"])), type=str(e["equipment_type"]),
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
    # Inside escalation.request_scope (run_tea / run_monte_carlo): the series already holds
    # this request's approved forward years, and the target is the request's cost base.
    _target_year = escalation.request_target_year(req)

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


def _config_record(req: TEAComputeRequest, units, var_opex) -> dict:
    """The canonical-mode config as plain data (what OpenPyTEA received, equipment as kwargs)."""
    a = req.assumptions
    return {"plant_name": req.pathway_id, "country": req.country, "process_type": req.plant_process_type,
            "currency": (req.base_currency or "EUR").upper(), "interest_rate": a.discount_rate_pct / 100.0,
            "plant_utilization": a.capacity_factor, "project_lifetime": a.project_life_years,
            "variable_opex_inputs": var_opex,
            "plant_products": {req.fuel_id.lower(): {"production": _nameplate_kg_per_day(req)}},
            "equipment": [{"name": (u.id[:8] or f"EQ{i}").upper(), "param": u.sizing,
                           "process_type": u.process_type, "category": u.category,
                           "type": u.equipment_type, "material": u.material}
                          for i, u in enumerate(units)]}


def _quote_plant(req: TEAComputeRequest):
    """Quote mode on the real OpenPyTEA: (the calculated plant, config record)."""
    from openpytea.plant import Plant
    from tea_engine import escalation
    from tea_engine.compute.quote_plant import quote_config
    config, equipment = quote_config(req, escalation.request_target_year(req))
    plant = Plant({**config, "equipment": equipment})
    plant.calculate_all()
    return plant, config


def _headline(plant) -> tuple[float, float, float]:
    d = plant.to_dict()
    capex = float(d["capital_costs"]["fixed_capital"])
    opex = float(d["variable_opex"]["total"]) + float(d["fixed_opex"]["total"])
    lcop = float(d["metrics"]["levelized_cost"])
    return round(capex, 2), round(opex, 2), round(lcop, 4)


def _quote_numbers(req: TEAComputeRequest) -> tuple[float, float, float, str, dict]:
    """Quote mode on the real OpenPyTEA: (capex, opex/yr, lcop, currency, config record)."""
    plant, config = _quote_plant(req)
    return (*_headline(plant), config["currency"], config)


def breakdown(plant, req: TEAComputeRequest) -> dict:
    """What a calculated OpenPyTEA plant priced, line by line (20 Nov 2026).

    Read from the plant OpenPyTEA calculated, never recomputed by a second formula, except
    the cost per kg: OpenPyTEA's LCOP is (discounted capital + discounted cash cost -
    discounted by-product revenue) / discounted production, each year t discounted by
    (1 + r)^t. Variable cost runs with production (ramp), fixed cost from the first
    production year at its full value, so the cash cost splits exactly; the parts are
    returned with `check` = LCOP minus their sum, which must be ~0.
    """
    import numpy as np
    d = plant.to_dict()
    cap = d["capital_costs"]
    r = float(plant.interest_rate)
    capital = np.asarray(plant.capital_cost_array, dtype=float)[0]
    prod = np.asarray(plant.prod_array, dtype=float)[0]
    cash = np.asarray(plant.cash_cost_array, dtype=float)[0]
    side = np.asarray(plant.side_revenue_array, dtype=float)[0]
    n = len(prod)
    disc = (1.0 + r) ** np.arange(1, n + 1)
    dp = float(np.sum(prod / disc))
    full = float(prod.max()) if n else 0.0
    var_streams = {k: float(v) for k, v in (d["variable_opex"].get("breakdown") or {}).items()}
    var_total = float(d["variable_opex"]["total"])
    fixed = {k: float(v) for k, v in d["fixed_opex"].items() if k != "total" and v is not None}
    fixed_total = float(d["fixed_opex"]["total"])
    ramp = prod / full if full else prod * 0
    disc_var = float(np.sum(var_total * ramp / disc))
    disc_cash = float(np.sum(cash / disc))
    disc_fixed = disc_cash - disc_var
    per_kg_capital = float(np.sum(capital / disc)) / dp if dp else None
    per_kg_var = disc_var / dp if dp else None
    per_kg_fixed = disc_fixed / dp if dp else None
    per_kg_side = float(np.sum(side / disc)) / dp if dp else None
    lcop = float(d["metrics"]["levelized_cost"])
    per_kg = None
    if dp:
        per_kg = {
            "capital": per_kg_capital,
            "variable": {k: (v / var_total * per_kg_var if var_total else 0.0) for k, v in var_streams.items()},
            "fixed": {k: (v / fixed_total * per_kg_fixed if fixed_total else 0.0) for k, v in fixed.items()},
            "by_product_credit": -per_kg_side,
            "levelized_cost": lcop,
            "check": lcop - (per_kg_capital + per_kg_var + per_kg_fixed - per_kg_side),
        }
    equipment = [{"name": e.name, "category": e.category, "cost_year": e.cost_year,
                  "target_year": e.target_year, "num_units": getattr(e, "num_units", 1),
                  "purchased_cost": float(e.purchased_cost), "direct_cost": float(e.direct_cost)}
                 for e in plant.equipment_list]
    years = [{"year": i, "discount_factor": float(1.0 / disc[i]), "production_kg": float(prod[i]),
              "capital": float(capital[i]), "fixed_opex": float(cash[i] - var_total * ramp[i]),
              "variable_opex": float(var_total * ramp[i]), "by_product_revenue": float(side[i]),
              "cost": float(capital[i] + cash[i] - side[i])} for i in range(n)]
    return {
        "currency": plant.currency,
        "unit": f"{plant.currency}/kg",
        "discount_rate": r,
        "plant_utilization": float(plant.plant_utilization),
        "project_lifetime": int(plant.project_lifetime),
        "exchange_rate": float(plant.exchange_rate),
        "location_factor": (float(plant.loc_factor) if getattr(plant, "loc_factor", None) is not None else None),
        "production_kg_per_year_full": full,
        "capital_costs": {k: (float(cap[k]) if cap.get(k) is not None else None)
                          for k in ("isbl", "osbl", "design_and_engineering", "contingency",
                                    "fixed_capital", "working_capital")},
        "equipment": equipment,
        "variable_opex": {"streams": var_streams, "total": var_total},
        "fixed_opex": {"components": fixed, "total": fixed_total},
        "per_kg": per_kg,
        "years": years,
        "note": ("Pre-tax, unfinanced: the discount rate is the only cost of money, there is no debt and "
                 "no tax. NPV, IRR and payback are not computed here: returns come from the financing case."),
    }


def _quote_stub(req: TEAComputeRequest) -> tuple[float, float, float, dict]:
    """Deterministic stand-in for quote mode (stub path only, labelled engine=stub)."""
    q = req.quote_plant
    capex = sum(e.installed_cost for e in q.equipment) * (1 + q.contingency)
    opex = (sum(v.consumption * v.price for v in q.variable_opex.values()) * 365
            + q.operators_hired * q.operator_hourly_rate * 1960 + sum(q.fixed_opex_components.values()))
    out_kg = _nameplate_t_per_year(req) * 1000.0 * req.assumptions.capacity_factor
    lcop = (capex * req.assumptions.discount_rate_pct / 100.0 + opex) / max(out_kg, 1.0)
    return round(capex, 2), round(opex, 2), round(lcop, 4), {"stub": True}


def _real_plant(req: TEAComputeRequest, units, var_opex):
    plant, base_ccy = _build_plant(req, units, var_opex)
    plant.calculate_all()
    return plant, base_ccy


def _real_numbers(req: TEAComputeRequest, units, var_opex) -> tuple[float, float, float, str]:
    """Run the real OpenPyTEA plant TEA and extract (capex, opex/yr, lcop, currency)."""
    plant, base_ccy = _real_plant(req, units, var_opex)
    return (*_headline(plant), base_ccy)


def _escalation_target_year(req: TEAComputeRequest) -> int:
    """The cost base, from the same source the Equipment construction uses."""
    from tea_engine import escalation
    return escalation.request_target_year(req)


def _forwards(req) -> dict:
    from tea_engine import escalation
    return escalation.forwards_used(req)


def _scope(req):
    """The run's CEPCI series (published + this request's approved forwards). None on the stub."""
    from contextlib import nullcontext
    if not (_HAS_OPENPYTEA and not _stub_allowed()):
        return nullcontext()
    from tea_engine import escalation
    return escalation.request_scope(req)


def _correlation_set_block() -> dict:
    """The fingerprint, trimmed for the artefact: the pin plus what identifies it."""
    from tea_engine.correlation_set import fingerprint
    f = fingerprint()
    return {k: f[k] for k in ("hash", "openpytea_version", "correlations",
                              "cepci_year_range", "gex_supplied_cepci_years")}


def run_tea(req: TEAComputeRequest) -> TEAResult:
    with _scope(req):
        return _run_tea(req)


def _run_tea(req: TEAComputeRequest) -> TEAResult:
    from tea_engine import integrity
    _ensure_runnable()
    cbh = cost_basis_hash(req)
    nameplate_t = _nameplate_t_per_year(req)   # G2: validates the unit up front (→ 422 on unknown)
    integrity.usd_to_base_rate((req.base_currency or "EUR").upper(), req.fx_usd_to_eur,
                               req.fx_benchmark_usd_to_eur)   # G5: fx band (→ 422)
    from tea_engine.compute.quote_plant import defaults_used as _defaults_used
    if req.quote_plant is None and "contingency_pct" in req.assumptions.model_fields_set:
        # JML, 19 Nov 2026: canonical mode does not apply a stated contingency (OpenPyTEA's
        # own factor prices its generic train), so it refuses one rather than ignore it.
        raise ValueError("Canonical mode does not apply a stated contingency: price the plant's own lines "
                         "in quote mode (quote_plant.contingency), or leave contingency_pct unstated so "
                         "OpenPyTEA's default applies and is listed.")
    plant = None
    if req.quote_plant is not None:
        units, var_opex, pf_meta = [], {}, None
        if _HAS_OPENPYTEA and not _stub_allowed():
            plant, config_record = _quote_plant(req)
            capex, opex, lcop = _headline(plant)
            currency, is_stub = config_record["currency"], False
        else:
            capex, opex, lcop, config_record = _quote_stub(req)
            currency, is_stub = (req.base_currency or "EUR").upper(), True
    else:
        units, var_opex, pf_meta = resolve_process_function(req)
        config_record = _config_record(req, units, var_opex)
        if _HAS_OPENPYTEA and not _stub_allowed():
            plant, currency = _real_plant(req, units, var_opex)
            capex, opex, lcop = _headline(plant)
            is_stub = False
        else:
            capex, opex, lcop = _stub_numbers(req, units)
            currency, is_stub = (req.base_currency or "EUR").upper(), True
    defaults = [] if is_stub else _defaults_used(config_record) + category_renames(req)
    feed_balance = []
    if req.quote_plant is not None:
        from tea_engine.compute.quote_plant import feedstock_balance, quote_year_defaults
        feed_balance = feedstock_balance(req)
        if not is_stub:
            defaults += quote_year_defaults(req, _escalation_target_year(req))
    if not is_stub:
        from tea_engine.compute.quote_plant import forward_defaults
        defaults += forward_defaults(req, _escalation_target_year(req))
    if req.quote_plant is not None and req.quote_plant.osbl_factor is not None and not is_stub:
        defaults.append({"name": "quote.osbl_factor", "value": req.quote_plant.osbl_factor,
                         "basis": f"STATED: {req.quote_plant.osbl_factor_basis}"})

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
    if req.quote_plant is None:
        # Canonical mode applies OpenPyTEA's own contingency factor (listed in defaults_used)
        # and refuses a stated one, so contingency_pct is not an input of the run.
        input_provenance.pop("contingency_pct", None)
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
        currency, None if is_stub else _escalation_target_year(req), is_stub, fx,
        engine=engine_name(), engine_version=_engine_version(),
        correlation_set=(None if is_stub else _correlation_set_block()),
        cepci_forward=(None if is_stub else _forwards(req)))
    # G6: what the cost covers — canonical battery limits vs an unverified caller train.
    import tea_engine.process_functions as _pfx
    calc_boundary = integrity.calculation_boundary(
        pf_meta, len(units), req.fuel_id,
        _pfx.canonical_equipment_count(req.fuel_id), _pfx.canonical_nodes(req.fuel_id))
    if req.quote_plant is not None:
        calc_boundary = {"basis": "QUOTE_LINES", "lines": len(req.quote_plant.equipment),
                         "note": "The caller's own lines, each an installed quote. No canonical "
                                 "equipment and no purchased feedstock beyond those stated."}

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
        openpytea_config=None if is_stub else config_record,
        defaults_used=defaults,
        feedstock_balance=feed_balance,
        # Not with a co-product credit: the plant's LCOP is then not the reported one.
        breakdown=(breakdown(plant, req) if plant is not None and not coproduct_credit else None),
    )


CONVENTION = "CONVENTION (GEX screening range, not a sourced range)"


def _lever(name, label, unit, base, lo, hi, basis, setter):
    return {"parameter": name, "label": label, "unit": unit, "base": base, "low": lo, "high": hi,
            "basis": basis, "set": setter}


def _levers(req: TEAComputeRequest) -> list[dict]:
    """The one-way levers of a run, each with the range it moves and why that range.

    A rate moves in points, not by a percentage of itself (8% +/- 20% would be 6.4-9.6%,
    which reads as noise). Prices and quotes move by a fraction. No range here is sourced:
    each says CONVENTION until a governed range exists. Fixed costs that OpenPyTEA sets as
    a percentage of capital move WITH the capital lever, never as a lever of their own:
    moving them separately would count the same uncertainty twice.
    """
    a = req.assumptions
    out = []
    dr = a.discount_rate_pct

    def _dr(r, v):
        r.assumptions.discount_rate_pct = v
    out.append(_lever("discount_rate", "Discount rate (no debt in this model)", "%", dr,
                      max(dr - 2.0, 0.0), dr + 2.0, f"{CONVENTION}: +/- 2 percentage points", _dr))
    cf = a.capacity_factor

    def _cf(r, v):
        r.assumptions.capacity_factor = v
    out.append(_lever("utilization", "Utilisation (share of the year at nameplate)", "fraction", cf,
                      round(max(cf - 0.10, 0.05), 4), round(min(cf + 0.10, 1.0), 4),
                      f"{CONVENTION}: +/- 10 points, capped at 1", _cf))
    q = req.quote_plant
    if q is not None:
        total = sum(e.installed_cost for e in q.equipment)

        def _capex(r, v):
            f = v / total
            for e, orig in zip(r.quote_plant.equipment, q.equipment):
                e.installed_cost = orig.installed_cost * f
        out.append(_lever("installed_cost", "Installed cost of the quoted lines (all together)",
                          req.base_currency or "EUR", total, total * 0.8, total * 1.2,
                          f"{CONVENTION}: +/- 20%; fixed costs set as % of capital move with it", _capex))
        for stream, s_in in q.variable_opex.items():
            def _price(r, v, stream=stream):
                r.quote_plant.variable_opex[stream].price = v
            out.append(_lever(f"price:{stream}", f"Price of {stream}",
                              f"{req.base_currency or 'EUR'} per {s_in.unit.split('/')[0]}", s_in.price,
                              s_in.price * 0.8, s_in.price * 1.2,
                              f"{CONVENTION}: +/- 20%; stated price source: {s_in.source}", _price))
        return out
    if req.process_units:
        for stream, cfg in (req.variable_opex_inputs or {}).items():
            if isinstance(cfg, dict) and "price" in cfg:
                def _sp(r, v, stream=stream):
                    r.variable_opex_inputs[stream]["price"] = v
                out.append(_lever(f"price:{stream}", f"Price of {stream}", None, cfg["price"],
                                  cfg["price"] * 0.8, cfg["price"] * 1.2, f"{CONVENTION}: +/- 20%", _sp))
    else:
        import tea_engine.process_functions as pfx
        pf = pfx.get(req.fuel_id)
        for field in sorted({fs.price_field for fs in pf.feedstocks} if pf else set()):
            v0 = getattr(a, field)

            def _ap(r, v, field=field):
                setattr(r.assumptions, field, v)
            out.append(_lever(f"price:{field}", field, None, v0, v0 * 0.8, v0 * 1.2, f"{CONVENTION}: +/- 20%", _ap))
    return out


def run_sensitivity(req: TEAComputeRequest) -> TEASensitivityResult:
    """One-way tornado: each lever moved alone to its low and high value, every point a real
    run of the same plant. Sorted by swing, widest first."""
    _ensure_runnable()
    with _scope(req):
        base = run_tea(req)
        tornado = []
        for lv in _levers(req):
            lo, hi = req.model_copy(deep=True), req.model_copy(deep=True)
            lv["set"](lo, lv["low"])
            lv["set"](hi, lv["high"])
            tornado.append(SensitivityVar(
                parameter=lv["parameter"], low_lcop=run_tea(lo).lcop, high_lcop=run_tea(hi).lcop,
                label=lv["label"], unit=lv["unit"], base_input=lv["base"], low_input=lv["low"],
                high_input=lv["high"], range_basis=lv["basis"]))
    tornado.sort(key=lambda t: -abs(t.high_lcop - t.low_lcop))
    return TEASensitivityResult(engine=engine_name(), cost_basis_hash=base.cost_basis_hash,
                                base_lcop=base.lcop, tornado=tornado, run_evidence=base.run_evidence)


INDEX_BAND_NOT_COVERED = [
    "Electricity and other prices: Gabillon does not apply to power, which cannot be stored; a band for it "
    "needs a third-party forward curve for the bidding zone.",
    "The accuracy of the quotes themselves (a quote is a price, not an index).",
    "Utilisation and the discount rate: see the sensitivity.",
]


def run_index_band(req: TEAComputeRequest) -> dict:
    """The cost-index band of a run (JML, 20 Nov 2026: Gabillon, not Monte Carlo).

    Every forward CEPCI year the run relies on is set to the 5% and then the 95% value of
    its approved Gabillon row, all together, and the same plant is priced again. The band
    is the escalation uncertainty only, and says so. With no forward year (cost base and
    every quote year published) there is no band, and the answer says why.
    """
    _ensure_runnable()
    from tea_engine import escalation
    with _scope(req):
        base = run_tea(req)
        used = escalation.forwards_used(req, escalation.published_series())
    years = {y: {"value": f.value, "low": f.low, "high": f.high, "ref_id": f.ref_id} for y, f in sorted(used.items())}
    out = {"method": ("Gabillon two-factor P-forward of the CEPCI (PF engine), 90% band: every forward year at "
                      "its 5% value, then at its 95% value, together"),
           "years": years, "base": {"lcop": base.lcop, "fixed_capital": base.plant_summary.capex_eur},
           "not_covered": INDEX_BAND_NOT_COVERED}
    if not used:
        return {**out, "applies": False,
                "reason": "The cost base and every quote year are published CEPCI years: no forward, so no band."}
    missing = [y for y, f in used.items() if f.low is None or f.high is None]
    if missing:
        return {**out, "applies": False,
                "reason": f"The approved forward row for {', '.join(map(str, missing))} carries no band."}
    scen = {}
    for side in ("low", "high"):
        r = req.model_copy(deep=True)
        for y in used:
            f = r.cepci_forward[y]
            f.value = getattr(f, side)
        res = run_tea(r)
        scen[side] = {"lcop": res.lcop, "fixed_capital": res.plant_summary.capex_eur,
                      "index": {y: getattr(used[y], side) for y in used}}
    return {**out, "applies": True, "index_low": scen["low"], "index_high": scen["high"],
            "lcop_range": [min(scen["low"]["lcop"], scen["high"]["lcop"]),
                           max(scen["low"]["lcop"], scen["high"]["lcop"])]}


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
    with _scope(req):
        return _run_monte_carlo(req)


def _run_monte_carlo(req: TEAMonteCarloRequest) -> TEAMonteCarloResult:
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
