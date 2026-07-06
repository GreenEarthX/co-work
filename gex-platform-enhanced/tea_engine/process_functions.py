"""process_functions — the canonical PROCESS FUNCTION for each molecule.

This is the root of GEX's molecule spine: for each offered molecule it ascertains
*how the molecule is actually made* — the reaction, the feedstock stoichiometry,
and the equipment train — so the TEA describes that molecule's real plant, not a
generic one. Without this, CAPEX/OPEX/LCOP (and therefore the model_base_case
claim, and the release gate) describe a fiction.

Two honesty rails:
  · Every equipment entry uses an OpenPyTEA correlation that actually computes
    (valid category/type/material, CEPCI-covered cost year). Verified against the
    bundled cost_correlations.csv.
  · `ascertained` marks whether the process function has been IE-verified. A
    canonical template authored here is `ascertained=False` until an independent
    engineer signs it — exactly like model_base_case is `submitted` until approved.
    The sizing coefficients are a documented FIRST-PASS engineering basis, not gospel.

Feedstock consumption is per-DAY (OpenPyTEA: cost = consumption·price·365·utilization).
Stoichiometry is mass ratio per tonne of product, divided by a conversion yield.
"""
from __future__ import annotations

from dataclasses import dataclass, field

REFERENCE_NAMEPLATE_T_YR = 50_000.0      # coefficients are tuned at this scale
DEFAULT_SCALE_EXP = 0.65                  # six-tenths-rule-ish equipment scaling


@dataclass(frozen=True)
class EquipmentSpec:
    role:       str       # human role in the train
    node:       str       # canonical truth-stack node it rolls up to
    category:   str       # OpenPyTEA category (must exist in cost_correlations.csv)
    type:       str       # OpenPyTEA type
    material:   str       # OpenPyTEA material
    base_param: float     # sizing param at REFERENCE_NAMEPLATE_T_YR (unit per correlation)
    scale_exp:  float = DEFAULT_SCALE_EXP


@dataclass(frozen=True)
class FeedstockSpec:
    stream:          str            # variable_opex key: hydrogen | co2 | electricity | ...
    t_per_t_product: float | None   # mass ratio (None ⇒ energy stream, see mwh_per_t_product)
    price_field:     str            # FinancialAssumptions field holding the price
    mwh_per_t_product: float = 0.0  # for electricity / energy streams


@dataclass(frozen=True)
class CoProduct:
    """A saleable co-product produced alongside the primary product, per kg of it.
    Used for LCA co-product allocation (RED III Annex V energy basis) AND for
    crediting co-product revenue in the TEA (so TEA and LCA treat co-products
    consistently and the mass balance closes)."""
    name:               str
    mass_per_kg_primary: float      # kg co-product per kg primary product
    lhv_mj_per_kg:      float
    eur_per_t:          float = 0.0  # co-product sale price (TEA revenue credit)


@dataclass(frozen=True)
class ProcessFunction:
    fuel_id:     str
    label:       str
    reaction:    str
    yield_frac:  float                  # single-pass-equivalent conversion to product
    equipment:   list[EquipmentSpec]
    feedstocks:  list[FeedstockSpec]
    version:     str
    ascertained: bool = False           # IE-verified? template ⇒ False
    note:        str = ""
    co_products: tuple = ()             # tuple[CoProduct] — for LCA co-product allocation
    # Regulatory regime — determines which certification gates, GHG method and
    # subsidy apply. RFNBO (RED III e-fuels + 45V) is the only regime modelled
    # today; ADVANCED_BIOFUEL / BIOFUEL_CROP / RCF / LOW_CARBON require the
    # biogenic branch (different feedstock nodes, GHG method, ISCC certification,
    # 40B/45Z credits) — see docs. All current molecules are RFNBO e-fuels.
    pathway_class: str = "RFNBO"


# ───────────────────────────────────────────────────────────────────────────
# REGISTRY
# ───────────────────────────────────────────────────────────────────────────

_E_METHANOL = ProcessFunction(
    fuel_id="E_METHANOL",
    label="e-Methanol via CO₂ hydrogenation (purchased green H₂ + captured CO₂)",
    reaction="CO2 + 3 H2 -> CH3OH + H2O",
    yield_frac=0.90,
    equipment=[
        EquipmentSpec("CO2 feed compressor",   "synthesis", "Compressors & blowers",        "CO2 compressor",            "Carbon steel",        6.0),    # MWe
        EquipmentSpec("Makeup gas compressor", "synthesis", "Compressors, fans, & blowers",  "Compressor, centrifugal",   "Carbon steel",        6000.0), # kW
        EquipmentSpec("Recycle compressor",    "synthesis", "Compressors, fans, & blowers",  "Compressor, centrifugal",   "Carbon steel",        3500.0), # kW
        EquipmentSpec("Methanol synthesis reactor", "synthesis", "Reactors",                 "Tubular fixed bed",         "304 stainless steel", 110000.0), # shell mass kg
        EquipmentSpec("Feed/effluent exchanger", "synthesis", "Heat exchangers",             "Floating head shell & tube","Carbon steel",        1500.0), # area m^2
        EquipmentSpec("Product condenser",      "synthesis", "Heat exchangers",              "Air cooler",                "Carbon steel",        900.0),  # area m^2
        EquipmentSpec("HP flash separator",     "synthesis", "Pressure vessels",             "Vertical",                  "304 stainless steel", 60.0),   # volume m^3
        EquipmentSpec("Distillation column",    "product",   "Pressure vessels",             "Vertical",                  "Carbon steel",        250.0),  # volume m^3
        EquipmentSpec("Column reboiler",        "product",   "Heat exchangers",              "Thermosiphon reboiler",     "Carbon steel",        700.0),  # area m^2 (Kettle reboiler correlation is pathological — explodes on extrapolation)
        EquipmentSpec("Reflux/product pump",    "product",   "Pumps",                        "Centrifugal",               "Carbon steel",        120.0),  # shaft power kW
        EquipmentSpec("Product storage tank",   "storage",   "Tanks",                        "Cone-roof tank",            "Carbon steel",        6000.0), # capacity m^3
        EquipmentSpec("Cooling water system",   "synthesis", "Utilities",                    "Cooling tower & pumps",     "Carbon steel",        450.0),  # flow L/s
    ],
    feedstocks=[
        FeedstockSpec("hydrogen",    0.1875, "hydrogen_eur_t"),     # 6 g H2 / 32 g MeOH
        FeedstockSpec("co2",         1.375,  "co2_eur_t"),          # 44 g CO2 / 32 g MeOH
        FeedstockSpec("electricity", None,   "electricity_eur_mwh", mwh_per_t_product=0.70),
    ],
    version="0.1",
    ascertained=False,
    note="First-pass canonical e-methanol train. Sizing coefficients tuned at 50 kt/yr; "
         "IE to verify equipment list, sizing basis, and 0.90 yield before ascertained=True.",
)

_E_SAF = ProcessFunction(
    fuel_id="E_SAF",
    label="e-SAF via Fischer-Tropsch (green H₂ + captured CO₂ → RWGS → FT → upgrading)",
    reaction="CO2 + H2 -(RWGS)-> CO + H2O ; nCO + (2n+1)H2 -(FT)-> CnH(2n+2) + nH2O",
    yield_frac=0.75,   # FT + hydrocracking/fractionation losses; SAF is one cut of the syncrude
    equipment=[
        EquipmentSpec("CO2 feed compressor",     "synthesis", "Compressors & blowers",        "CO2 compressor",            "Carbon steel",        7.0),     # MWe
        EquipmentSpec("Makeup H2 compressor",    "synthesis", "Compressors, fans, & blowers",  "Compressor, centrifugal",   "Carbon steel",        7000.0),  # kW
        EquipmentSpec("RWGS reactor",            "synthesis", "Reactors",                      "Tubular fixed bed",         "304 stainless steel", 85000.0), # shell mass kg (catalytic RWGS; OpenPyTEA furnace correlations are unreliable at scale)
        EquipmentSpec("Fischer-Tropsch reactor", "synthesis", "Reactors",                      "Tubular fixed bed",         "304 stainless steel", 150000.0),# shell mass kg
        EquipmentSpec("Syncrude cooler",         "synthesis", "Heat exchangers",               "Floating head shell & tube","Carbon steel",        1800.0),  # area m^2
        EquipmentSpec("3-phase separator",       "synthesis", "Pressure vessels",              "Vertical",                  "304 stainless steel", 80.0),    # volume m^3
        EquipmentSpec("Hydrocracker/upgrading",  "product",   "Reactors",                      "Tubular fixed bed",         "304 stainless steel", 95000.0), # shell mass kg
        EquipmentSpec("Product fractionation",   "product",   "Pressure vessels",              "Vertical",                  "Carbon steel",        300.0),   # volume m^3
        EquipmentSpec("Fractionation reboiler",  "product",   "Heat exchangers",               "Thermosiphon reboiler",     "Carbon steel",        800.0),   # area m^2
        EquipmentSpec("Tail-gas recycle compressor","synthesis","Compressors, fans, & blowers","Compressor, centrifugal",   "Carbon steel",        4000.0),  # kW
        EquipmentSpec("Product pump",            "product",   "Pumps",                         "Centrifugal",               "Carbon steel",        150.0),   # shaft power kW
        EquipmentSpec("SAF storage tank",        "storage",   "Tanks",                         "Cone-roof tank",            "Carbon steel",        7000.0),  # capacity m^3
        EquipmentSpec("Cooling water system",    "synthesis", "Utilities",                     "Cooling tower & pumps",     "Carbon steel",        600.0),   # flow L/s
    ],
    feedstocks=[   # PER TONNE OF TOTAL FT PRODUCT (~CH2): CO2+3H2 -> -CH2- + 2H2O
        FeedstockSpec("hydrogen",    0.43, "hydrogen_eur_t"),    # 6 g H2 / 14 g CH2
        FeedstockSpec("co2",         3.14, "co2_eur_t"),         # 44 g CO2 / 14 g CH2
        FeedstockSpec("electricity", None, "electricity_eur_mwh", mwh_per_t_product=1.20),  # RWGS + compression, per t total
    ],
    version="0.2",
    ascertained=False,
    note="First-pass canonical e-SAF (RFNBO Fischer-Tropsch) train, matching the Breizh SAF "
         "workbook (PEM electrolyser upstream + FT). Sizing/stoichiometry are illustrative, "
         "tuned at 50 kt/yr; IE to verify FT/upgrading train, yield, and H2:CO2 ratios. NOTE: "
         "this is the E-FUEL SAF route — biogenic SAF (HEFA / bio-FT) is a different "
         "pathway_class (ADVANCED_BIOFUEL) with a different train and RED III regime.",
    co_products=(   # FT: jet is a modest cut of the syncrude — large diesel/naphtha/wax slate
        CoProduct("renewable_diesel", 0.90, 43.0, eur_per_t=750.0),
        CoProduct("naphtha",          0.50, 44.0, eur_per_t=650.0),
        CoProduct("wax",              0.20, 40.0, eur_per_t=700.0),
    ),
)

_BIO_SAF_HEFA = ProcessFunction(
    fuel_id="BIO_SAF_HEFA",
    label="bio-SAF via HEFA (hydroprocessed esters & fatty acids from waste lipids: UCO / tallow)",
    reaction="Triglyceride + H2 -(HDO)-> n-paraffins + H2O + CO2/CO ; n-paraffins -(hydroisom./crack)-> iso-paraffins (SAF cut)",
    yield_frac=0.70,   # SAF-max mode; balance is renewable diesel / naphtha / propane co-products
    equipment=[
        EquipmentSpec("Feed pretreatment vessel", "synthesis", "Pressure vessels",             "Vertical",                  "Carbon steel",        120.0),   # volume m^3 (degumming/bleaching)
        EquipmentSpec("Feed charge pump",         "synthesis", "Pumps",                         "Centrifugal",               "Carbon steel",        200.0),   # shaft power kW
        EquipmentSpec("H2 makeup compressor",     "synthesis", "Compressors, fans, & blowers",  "Compressor, centrifugal",   "Carbon steel",        3000.0),  # kW
        EquipmentSpec("Feed preheat train",       "synthesis", "Heat exchangers",               "Floating head shell & tube","Carbon steel",        2200.0),  # area m^2 (fired-heater duty proxied as HX; OpenPyTEA furnace correlations unreliable at scale — IE to add fired-heater vendor quote)
        EquipmentSpec("Hydrotreater (HDO) reactor","synthesis","Reactors",                      "Tubular fixed bed",         "304 stainless steel", 130000.0),# shell mass kg
        EquipmentSpec("Hydroisomerisation reactor","product",  "Reactors",                      "Tubular fixed bed",         "304 stainless steel", 90000.0), # shell mass kg
        EquipmentSpec("Feed/effluent exchanger",  "synthesis", "Heat exchangers",               "Floating head shell & tube","Carbon steel",        1600.0),  # area m^2
        EquipmentSpec("HP hot separator",         "synthesis", "Pressure vessels",              "Vertical",                  "304 stainless steel", 70.0),    # volume m^3
        EquipmentSpec("Product fractionation",    "product",   "Pressure vessels",              "Vertical",                  "Carbon steel",        280.0),   # volume m^3
        EquipmentSpec("Fractionation reboiler",   "product",   "Heat exchangers",               "Thermosiphon reboiler",     "Carbon steel",        750.0),   # area m^2
        EquipmentSpec("H2 recycle compressor",    "synthesis", "Compressors, fans, & blowers",  "Compressor, centrifugal",   "Carbon steel",        2500.0),  # kW
        EquipmentSpec("Product cooler",           "product",   "Heat exchangers",               "Air cooler",                "Carbon steel",        850.0),   # area m^2
        EquipmentSpec("SAF storage tank",         "storage",   "Tanks",                         "Cone-roof tank",            "Carbon steel",        7000.0),  # capacity m^3
        EquipmentSpec("Cooling water system",     "synthesis", "Utilities",                     "Cooling tower & pumps",     "Carbon steel",        500.0),   # flow L/s
    ],
    feedstocks=[   # PER TONNE OF TOTAL HEFA LIQUID PRODUCT (oil→paraffins, ~86% mass yield)
        FeedstockSpec("waste_lipid", 1.16, "feedstock_oil_eur_t"),   # UCO/tallow per t total product
        FeedstockSpec("hydrogen",    0.035, "hydrogen_eur_t"),       # HDO + isomerisation, per t total
        FeedstockSpec("electricity", None, "electricity_eur_mwh", mwh_per_t_product=0.30),
    ],
    version="0.2",
    ascertained=False,
    pathway_class="ADVANCED_BIOFUEL",
    note="First biogenic pathway. HEFA from waste lipids (UCO = RED III Annex IX Part B, cap + double-counting; "
         "tallow Cat 1/2 = Part B). DIFFERENT REGIME from e-SAF: certification is ISCC EU / Proof-of-Sustainability "
         "+ Annex IX + mass-balance (NOT RFNBO additionality/temporal/geo); GHG by RED III Annex V with biogenic "
         "CO2 = 0 at combustion; US credit is 40B/45Z (GREET), NOT 45V. Feedstock cost (not H2/power) dominates LCOP. "
         "Sizing/stoichiometry illustrative, tuned at 50 kt/yr SAF; IE to verify. Gate/GHG/subsidy branching by "
         "pathway_class is not yet enforced in the truth stack (that is the separate regime-branch work).",
    co_products=(   # HEFA SAF-max: renewable diesel dominant co-product, plus naphtha + LPG
        CoProduct("renewable_diesel", 0.55, 43.0, eur_per_t=750.0),
        CoProduct("naphtha",          0.15, 44.0, eur_per_t=650.0),
        CoProduct("lpg",              0.05, 46.0, eur_per_t=500.0),
    ),
)

# Scaffolds — reaction + canonical equipment skeleton present, but NOT yet a full
# costed train. build_process_function() raises for these until equipment is filled,
# so the TEA cannot silently emit a number for a molecule whose process function
# is not defined. This is the point: no fictional economics.
_E_METHANE = ProcessFunction(
    fuel_id="E_METHANE", label="e-Methane via CO₂ methanation (Sabatier)",
    reaction="CO2 + 4 H2 -> CH4 + 2 H2O", yield_frac=0.90,
    equipment=[], feedstocks=[
        FeedstockSpec("hydrogen", 0.50, "hydrogen_eur_t"),   # 8 g H2 / 16 g CH4
        FeedstockSpec("co2", 2.75, "co2_eur_t"),             # 44 g CO2 / 16 g CH4
        FeedstockSpec("electricity", None, "electricity_eur_mwh", mwh_per_t_product=0.55),
    ],
    version="0.0", ascertained=False,
    note="SCAFFOLD: methanation reactor + recycle train to be defined.")

_GREEN_H2 = ProcessFunction(
    fuel_id="GREEN_H2", label="Green hydrogen via PEM/alkaline electrolysis",
    reaction="2 H2O -> 2 H2 + O2", yield_frac=1.0,
    equipment=[], feedstocks=[
        FeedstockSpec("electricity", None, "electricity_eur_mwh", mwh_per_t_product=52.0),
    ],
    version="0.0", ascertained=False,
    note="SCAFFOLD: electrolyser stacks not in OpenPyTEA's generic correlations — "
         "needs a custom cost_func or vendor-quote equipment entry.")

_AMMONIA = ProcessFunction(
    fuel_id="E_AMMONIA", label="Green ammonia via Haber-Bosch (green H₂ + ASU N₂)",
    reaction="N2 + 3 H2 -> 2 NH3", yield_frac=0.90,
    equipment=[], feedstocks=[
        FeedstockSpec("hydrogen", 0.178, "hydrogen_eur_t"),  # 6 g H2 / 34 g (2 NH3 per 3 H2 → per NH3)
        FeedstockSpec("electricity", None, "electricity_eur_mwh", mwh_per_t_product=0.60),
    ],
    version="0.0", ascertained=False,
    note="SCAFFOLD: synthesis loop + ASU to be defined.")

REGISTRY: dict[str, ProcessFunction] = {
    pf.fuel_id: pf for pf in (_E_METHANOL, _E_SAF, _BIO_SAF_HEFA, _E_METHANE, _GREEN_H2, _AMMONIA)
}


def has_process_function(fuel_id: str) -> bool:
    pf = REGISTRY.get((fuel_id or "").upper())
    return bool(pf and pf.equipment)


def get(fuel_id: str) -> ProcessFunction | None:
    return REGISTRY.get((fuel_id or "").upper())


def total_product_per_primary(pf: ProcessFunction) -> float:
    """Total saleable product (primary + co-products) per t of primary product."""
    return 1.0 + sum(cp.mass_per_kg_primary for cp in pf.co_products)


def feedstock_per_t_primary(pf: ProcessFunction):
    """Yield (stream, qty_per_t_primary, is_energy, price_field).

    MASS-BALANCE BASIS: for multi-product pathways (SAF etc.) the FeedstockSpec
    ratios are stated PER TONNE OF TOTAL PRODUCT and scaled here to per-t-primary
    by the total/primary multiplier — so carbon and mass conserve (SAF no longer
    absorbs the whole plant's feed). Single-product molecules (methanol/methane)
    have no co-products, so feed carries recycle/purge inefficiency via yield_frac
    exactly as before — those pathways are unchanged.
    """
    M = total_product_per_primary(pf)
    has_co = bool(pf.co_products)
    for fs in pf.feedstocks:
        if fs.t_per_t_product is not None:
            scale = M if has_co else (1.0 / pf.yield_frac)
            yield (fs.stream, fs.t_per_t_product * scale, False, fs.price_field)
        else:
            scale = M if has_co else 1.0
            yield (fs.stream, fs.mwh_per_t_product * scale, True, fs.price_field)


def coproduct_revenue_per_t_primary(pf: ProcessFunction) -> float:
    """EUR of co-product revenue per t of primary product (TEA credit)."""
    return sum(cp.mass_per_kg_primary * cp.eur_per_t for cp in pf.co_products)


def build_process_function(fuel_id: str, nameplate_t_yr: float) -> dict:
    """Instantiate a molecule's process function at the requested scale.

    Returns {process_units, variable_opex_inputs, meta} where process_units is a
    list of plain dicts (matching ProcessUnitSpec fields) and variable_opex_inputs
    is the OpenPyTEA {stream:{consumption,price_field}} skeleton — prices are filled
    by the runner from the request's assumptions.
    """
    pf = get(fuel_id)
    if pf is None:
        raise ValueError(f"No process function registered for molecule '{fuel_id}'.")
    if not pf.equipment:
        raise ValueError(
            f"Process function for '{fuel_id}' is a SCAFFOLD (no costed equipment "
            f"train yet): {pf.note}. Supply explicit process_units, or define the "
            f"train before running TEA — GEX will not emit fictional economics.")

    ratio = max(nameplate_t_yr, 1.0) / REFERENCE_NAMEPLATE_T_YR
    units = [
        {
            "id": e.role.lower().replace(" ", "_").replace("/", "_")[:24],
            "category": e.category,
            "equipment_type": e.type,
            "material": e.material,
            "sizing": round(e.base_param * (ratio ** e.scale_exp), 4),
            "process_type": "Fluids",
        }
        for e in pf.equipment
    ]

    product_t_per_day = nameplate_t_yr / 365.0
    var_opex_skeleton = {}
    for stream, qty, _is_energy, price_field in feedstock_per_t_primary(pf):
        var_opex_skeleton[stream] = {
            "consumption": round(product_t_per_day * qty, 4),  # t/day (mass) or MWh/day (energy)
            "price_field": price_field,
        }

    meta = {
        "process_function_id": pf.fuel_id,
        "version": pf.version,
        "reaction": pf.reaction,
        "yield_frac": pf.yield_frac,
        "ascertained": pf.ascertained,
        "pathway_class": pf.pathway_class,
        "equipment_count": len(units),
        "total_product_per_primary": round(total_product_per_primary(pf), 4),
        "co_products": [{"name": cp.name, "mass_per_kg_primary": cp.mass_per_kg_primary,
                         "eur_per_t": cp.eur_per_t} for cp in pf.co_products],
        "coproduct_revenue_per_t_primary": round(coproduct_revenue_per_t_primary(pf), 2),
        "note": pf.note,
    }
    return {"process_units": units, "variable_opex_inputs": var_opex_skeleton, "meta": meta}
