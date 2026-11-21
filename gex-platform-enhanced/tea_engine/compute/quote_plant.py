"""Quote mode: OpenPyTEA on a plant's OWN lines (calculation chain, 18 Nov 2026).

The canonical train prices a molecule's generic equipment and BUYS what it does not
make (an e-methanol train buys hydrogen at a model default). A saved Cost Basis is a
different plant: it builds the electrolyser. Pricing one and financing the other is
the v1 defect. In quote mode the equipment is the caller's lines as installed quotes
(every OpenPyTEA install factor 0, material factor 1, so installed = the quote), each
utility carries an explicit unit, and location, contingency and labour are stated.

What is still left to OpenPyTEA is returned by `defaults_used`, with its value, so
the caller lists it as an assumption instead of inheriting it unseen.
"""
from __future__ import annotations

from tea_engine.models.tea import TEAComputeRequest

# OpenPyTEA 3.x defaults that apply when a key is absent (read from
# openpytea/plant.py; tests/test_quote_plant.py pins them against the installed source).
CAPITAL_FACTORS = {"Solids": {"OS": 0.4, "DE": 0.2, "X": 0.1},
                   "Fluids": {"OS": 0.3, "DE": 0.3, "X": 0.1},
                   "Mixed": {"OS": 0.4, "DE": 0.25, "X": 0.1}}
FIXED_OPEX_FACTORS = {
    "supervision": (0.25, "x operating labour"),
    "direct_salary_overhead": (0.5, "x (labour + supervision)"),
    "laboratory_charges": (0.10, "x operating labour"),
    "maintenance": (0.05, "x ISBL"),
    "taxes_insurance": (0.015, "x ISBL"),
    "rent_of_land": (0.015, "x (ISBL + OSBL)"),
    "environmental_charges": (0.01, "x (ISBL + OSBL)"),
    "operating_supplies": (0.009, "x ISBL"),
    "general_plant_overhead": (0.65, "x (labour + supervision + direct salary overhead)"),
    "working_capital": (0.15, "x fixed capital"),
    "working_capital_interest": (0.0, "x working capital (OpenPyTEA 3.1: none by default; 3.0 charged the discount rate)"),
    "patents_royalties": (0.02, "x cash cost of production"),
    "distribution_selling": (0.02, "x cash cost of production"),
    "rnd": (0.03, "x cash cost of production"),
}
COMPONENT_FOR = {"supervision": "supervision_costs", "direct_salary_overhead": "direct_salary_overhead",
                 "laboratory_charges": "laboratory_charges", "maintenance": "maintenance_costs",
                 "taxes_insurance": "taxes_insurance_costs", "rent_of_land": "rent_of_land_costs",
                 "environmental_charges": "environmental_charges", "operating_supplies": "operating_supplies",
                 "general_plant_overhead": "general_plant_overhead", "patents_royalties": "patents_royalties",
                 "working_capital_interest": "interest_working_capital",
                 "distribution_selling": "distribution_selling_costs", "rnd": "RnD_costs"}
TIMING_DEFAULTS = {"capex_ramp": [0.3, 0.6, 0.1], "production_ramp": [0, 0, 0.4, 0.8],
                   "tax_rate": 0, "depreciation": None}


def quote_config(req: TEAComputeRequest, target_year: int) -> tuple[dict, list]:
    """(the OpenPyTEA config as plain data, the Equipment objects to build it with)."""
    from openpytea.equipment import Equipment

    q = req.quote_plant
    a = req.assumptions
    if q.osbl_factor is not None and not (q.osbl_factor_basis or "").strip():
        raise ValueError("osbl_factor needs its basis (osbl_factor_basis).")
    unknown = sorted(set(q.fixed_opex_components) - set(_component_keys()))
    if unknown:
        raise ValueError(f"unknown fixed_opex_components: {unknown}")
    # Each quote escalates from its own price year to the cost base through the series in force
    # for this run (published CEPCI plus the approved forward years, escalation.request_scope).
    eq_data = [{"name": e.name, "param": 0.0, "process_type": req.plant_process_type,
                "category": "Vendor quote", "type": None, "material": None,
                "purchased_cost": e.installed_cost,
                "cost_year": e.cost_year or target_year, "cost_func": None,
                "target_year": target_year, "erection_factor": 0.0, "piping_factor": 0.0,
                "instrumentation_factor": 0.0, "electrical_factor": 0.0, "civil_factor": 0.0,
                "structural_factor": 0.0, "lagging_factor": 0.0, "material_factor": 1.0}
               for e in q.equipment]
    config = {
        "plant_name": req.pathway_id,
        "process_type": req.plant_process_type,
        "currency": (req.base_currency or "EUR").upper(),
        "exchange_rate": 1.0,                # quotes are already in the base currency
        "loc_factor": q.loc_factor,
        "interest_rate": a.discount_rate_pct / 100.0,
        "plant_utilization": a.capacity_factor,
        "project_lifetime": a.project_life_years,
        "fixed_capital_factors": {"contingency": q.contingency,
                                  **({"osbl": q.osbl_factor} if q.osbl_factor is not None else {})},
        "operators_hired": q.operators_hired,
        "operator_hourly_rate": q.operator_hourly_rate,
        "fixed_opex_components": dict(q.fixed_opex_components),
        "variable_opex_inputs": {k: {"consumption": v.consumption, "price": v.price}
                                 for k, v in q.variable_opex.items()},
        "plant_products": {req.fuel_id.lower(): {"production": _kg_per_day(req)}},
        "equipment": eq_data,
    }
    return config, [Equipment(**d) for d in eq_data]


def _kg_per_day(req: TEAComputeRequest) -> float:
    from tea_engine import integrity
    return integrity.to_t_per_year(req.nameplate_capacity, req.nameplate_unit) * 1000.0 / 365.0


def _component_keys() -> tuple:
    from tea_engine.models.tea import FIXED_OPEX_COMPONENT_KEYS
    return FIXED_OPEX_COMPONENT_KEYS


def defaults_used(config: dict) -> list[dict]:
    """Every OpenPyTEA default the run still relied on, with its value."""
    out = []
    pt = config.get("process_type") or "Fluids"
    caps = CAPITAL_FACTORS.get(pt, CAPITAL_FACTORS["Fluids"])
    given_caps = config.get("fixed_capital_factors") or {}
    for key, name in (("OS", "osbl"), ("DE", "de"), ("X", "contingency")):
        if name not in given_caps:
            out.append({"name": f"openpytea.{name}_factor", "value": caps[key],
                        "basis": f"OpenPyTEA default for {pt} plants"})
    comps = config.get("fixed_opex_components") or {}
    for key, (value, basis) in FIXED_OPEX_FACTORS.items():
        if key == "working_capital":
            if config.get("working_capital") is None:
                out.append({"name": "openpytea.working_capital", "value": value, "basis": basis})
            continue
        if COMPONENT_FOR[key] not in comps:
            out.append({"name": f"openpytea.{key}", "value": value, "basis": basis})
    for key, value in TIMING_DEFAULTS.items():
        if key not in config:
            out.append({"name": f"openpytea.{key}", "value": value,
                        "basis": "OpenPyTEA default (timing and tax: the PF engine's authority for returns)"})
    if config.get("loc_factor") is None:
        out.append({"name": "openpytea.location", "value": config.get("country", "United States"),
                    "basis": "location factor from the country table"})
    return out


def published_cepci() -> dict[int, float]:
    """The CEPCI years OpenPyTEA holds outside any run (published, plus GEX-supplied history)."""
    from tea_engine import escalation
    return escalation.published_series()


def forward_defaults(req: TEAComputeRequest, target_year: int) -> list[dict]:
    """Each forward year this run priced with, declared with its band and its approved row.
    Both modes: the cost base year itself, and (quote mode) any quote dated after the last
    published CEPCI. Call inside escalation.request_scope (it reads the published series)."""
    from tea_engine import escalation
    published = published_cepci()
    lines: dict = {}
    if req.quote_plant is not None:
        for e in req.quote_plant.equipment:
            if e.cost_year and e.cost_year not in published:
                lines.setdefault(e.cost_year, []).append(e.name)
    out = []
    for y, f in sorted(escalation.forwards_used(req, published).items()):
        role = []
        if y == target_year:
            role.append("the cost base year")
        if lines.get(y):
            role.append(f"the price year of {len(lines[y])} quote(s)")
        out.append({"name": f"cepci_forward.{y}", "value": f.value,
                    "basis": (f"FORWARD, not a published index (approved reference row {f.ref_id}): {f.basis}; "
                              f"90% band {f.low}-{f.high}; used as {' and '.join(role)}")})
    return out


def quote_year_defaults(req: TEAComputeRequest, target_year: int) -> list[dict]:
    """Quotes with no stated price year are taken at the cost base year (no escalation): said."""
    missing = [e.name for e in req.quote_plant.equipment if e.cost_year is None]
    return ([{"name": "quote.cost_year", "value": target_year,
              "basis": f"price year not stated for {len(missing)} line(s); taken as the cost base year, no escalation"}]
            if missing else [])


def feedstock_balance(req: TEAComputeRequest) -> list[dict]:
    """Each MASS feedstock of the molecule: required at the stated run time vs on-site supply
    vs a stated purchase. Stoichiometry from the molecule's process function."""
    import tea_engine.process_functions as pfx
    from tea_engine import integrity
    pf = pfx.REGISTRY.get(req.fuel_id)
    if pf is None:
        return [{"feedstock": None, "status": "UNKNOWN_MOLECULE",
                 "detail": f"No process function for {req.fuel_id}: the feedstock balance is not checked."}]
    q = req.quote_plant
    annual_t = integrity.to_t_per_year(req.nameplate_capacity, req.nameplate_unit) * req.assumptions.capacity_factor
    out = []
    for f in pf.feedstocks:
        if f.t_per_t_product is None:
            continue                                  # energy streams come from the plant's own lines
        required = f.t_per_t_product * annual_t
        on_site = q.on_site_supply.get(f.stream)
        bought = q.variable_opex.get(f.stream)
        supplied = on_site.t_per_year if on_site else 0.0
        row = {"feedstock": f.stream, "required_t_per_year": round(required, 1),
               "on_site_t_per_year": round(supplied, 1) if on_site else None,
               "on_site_basis": on_site.basis if on_site else None,
               "purchased": bought is not None}
        bought_t = None
        if bought is not None:
            per_t = {"kg/day": 0.001, "t/day": 1.0}.get(bought.unit)
            if per_t is None:                          # Nm3 or energy units: no agreed density here
                row["status"] = "UNVERIFIED_UNIT"
                row["detail"] = f"Bought in {bought.unit}: no approved conversion to tonnes, so cover is unchecked."
                out.append(row)
                continue
            bought_t = bought.consumption * per_t * 365.0 * req.assumptions.capacity_factor
            row["purchased_t_per_year"] = round(bought_t, 1)
        total = supplied + (bought_t or 0.0)
        if bought is not None and total + 1e-6 >= required:
            row["status"] = "COVERED_WITH_PURCHASE" if on_site else "PURCHASED"
            row["surplus_t_per_year"] = round(total - required, 1)
        elif bought is not None:
            row["status"] = "SHORTFALL"
            row["shortfall_t_per_year"] = round(required - total, 1)
            row["detail"] = "On-site supply and the stated purchase together fall short of the requirement."
        elif on_site is None:
            row["status"] = "NOT_COVERED"
            row["detail"] = "Neither made on site nor bought: the cost of this feedstock is missing."
        elif supplied + 1e-6 < required:
            row["status"] = "SHORTFALL"
            row["shortfall_t_per_year"] = round(required - supplied, 1)
            row["detail"] = ("On-site supply is below the requirement at this run time; the shortfall is "
                             "neither bought nor priced.")
        else:
            row["status"] = "COVERED"
            row["surplus_t_per_year"] = round(supplied - required, 1)
        out.append(row)
    return out
