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

from dataclasses import dataclass, replace, field

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
    note="First-pass canonical e-SAF (RFNBO Fischer-Tropsch) train "
         "(PEM electrolyser upstream + FT). Sizing/stoichiometry are illustrative, "
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
        # Stoichiometric. Was 0.035 = 88.4% of the reaction requirement, i.e. an
        # impossible 113.2% implied yield. Balanced 2026-10-26:
        #   C57H104O6 + 15 H2 -> 3 C18H38 + C3H8 + 6 H2O  closes at 915.69 both
        # sides, so H2 = 30.24/763.5 = 0.0396 per t of alkane product. Declaring
        # stoichiometry matches every other pathway — conversion loss lives in
        # yield_frac, never in the declared ratio.
        FeedstockSpec("hydrogen",    0.0396, "hydrogen_eur_t"),       # HDO + isomerisation, per t total
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


def canonical_equipment_count(fuel_id: str) -> int | None:
    """G6: how many equipment items the molecule's canonical train has (None if
    the molecule is a scaffold / unregistered) — used to flag a caller-supplied
    train that dropped process blocks."""
    pf = get(fuel_id)
    return len(pf.equipment) if (pf and pf.equipment) else None


def canonical_nodes(fuel_id: str) -> list[str]:
    """G6: the canonical battery-limit nodes for a molecule (empty if none)."""
    pf = get(fuel_id)
    return sorted({e.node for e in pf.equipment}) if (pf and pf.equipment) else []


def total_product_per_primary(pf: ProcessFunction) -> float:
    """Total saleable product (primary + co-products) per t of primary product."""
    return 1.0 + sum(cp.mass_per_kg_primary for cp in pf.co_products)


def feedstock_per_t_primary(pf: ProcessFunction):
    """Yield (stream, qty_per_t_primary, is_energy, price_field).

    ONE RULE, two orthogonal factors:

        qty per t of PRIMARY product  =  declared  x  M  /  yield_frac

      · declared    is per tonne of TOTAL product, and is raw STOICHIOMETRY.
                    Verified 2026-10-26 against first principles: every declared
                    ratio sits within 0.7% of theoretical (E_METHANOL H2 0.1875 vs
                    0.18875; E_SAF CO2 3.14 vs 3.13745; E_AMMONIA H2 0.178 vs
                    0.17756). So the declared numbers carry NO loss allowance.
      · M           total product per primary. Handles the fact that SAF is one cut
                    of a syncrude slate: 1 t of SAF arrives with 1.6 t of other cuts,
                    so the feed for 1 t of SAF is the feed for 2.6 t of product.
      · yield_frac  the conversion loss — unreacted feed purged or vented.

    They are INDEPENDENT. M is a question about what you call the product; yield_frac
    is a question about how much feed fails to become any product. Applying both is
    not double-counting, precisely because the declared ratios are stoichiometric.

    This replaced `scale = M if has_co else (1.0 / yield_frac)`, which applied one OR
    the other. On a co-product pathway that discarded yield_frac entirely: E_SAF
    published `yield_frac: 0.75` in its result meta while its price contained no
    conversion loss at all. The engine asserted a conversion it had not applied.
    Energy streams take M only — a MWh is not consumed by unreacted feed.
    """
    M = total_product_per_primary(pf)
    yield_frac = float(pf.yield_frac or 1.0)
    for fs in pf.feedstocks:
        if fs.t_per_t_product is not None:
            yield (fs.stream, fs.t_per_t_product * M / yield_frac, False, fs.price_field)
        else:
            yield (fs.stream, fs.mwh_per_t_product * M, True, fs.price_field)


def coproduct_revenue_per_t_primary(pf: ProcessFunction) -> float:
    """EUR of co-product revenue per t of primary product (TEA credit)."""
    return sum(cp.mass_per_kg_primary * cp.eur_per_t for cp in pf.co_products)


# Which base_param units carry rotating/electrical duty, and their factor to MW.
_DUTY_UNIT_TO_MW = {"mwe": 1.0, "mw": 1.0, "kw": 0.001}


def _installed_duty_mw(pf) -> float:
    """Total rotating/electrical duty the train itself carries, in MW.

    Read from the equipment's own base_param, whose unit comes from the OpenPyTEA
    correlation (e.g. "electric power, MWe", "driver power, kW", "shaft power, kW").
    An upper bound on consumption: rated duty is not drawn continuously.
    """
    try:
        import os

        import openpytea
        import pandas as pd
        cc = pd.read_csv(os.path.join(os.path.dirname(openpytea.__file__),
                                     "data", "cost_correlations.csv"))
    except Exception:                                     # pragma: no cover
        return 0.0
    total = 0.0
    for e in pf.equipment:
        m = cc[(cc["category"] == e.category) & (cc["type"] == e.type)]
        if not len(m):
            continue
        unit = str(m.iloc[0]["units"]).lower()
        for token, factor in _DUTY_UNIT_TO_MW.items():
            # match the unit WORD, so "kw" does not match inside another token
            if token in unit.replace(",", " ").split():
                total += float(e.base_param) * factor
                break
    return total


def _mass_in_per_t_primary(pf) -> float:
    """Total declared MASS entering, per tonne of primary product. Energy streams are
    not mass and are excluded."""
    return sum(q for _s, q, is_energy, _pf in feedstock_per_t_primary(pf) if not is_energy)


def _energy_reconciliation(pf, nameplate_t_yr: float, capacity_factor: float) -> dict:
    """Both energy bases side by side, per tonne of PRIMARY product."""
    mw = _installed_duty_mw(pf)
    M = total_product_per_primary(pf)
    declared = sum(f.mwh_per_t_product for f in pf.feedstocks if f.mwh_per_t_product) * M
    cf = float(capacity_factor or 0.0)
    annual_primary = max(nameplate_t_yr * cf, 1.0)
    implied = (mw * 8760.0 * cf / annual_primary) if mw and cf else 0.0
    return {
        "installed_mw": round(mw, 3),
        "capacity_factor": round(cf, 4),
        "implied_from_train_mwh_per_t": round(implied, 4),
        "declared_mwh_per_t": round(declared, 4),
        "ratio": (round(implied / declared, 3) if declared else None),
        "note": ("Installed duty is an UPPER BOUND on consumption (rated power is not "
                 "drawn continuously, and a train may carry spares), so a ratio near 1 "
                 "is expected. A large ratio means the two sides disagree; it does not "
                 "say which is wrong."),
    }


def build_process_function(fuel_id: str, nameplate_t_yr: float,
                           equipment: "list | None" = None,
                           capacity_factor: float = 0.0) -> dict:
    """Instantiate a molecule's process function at the requested scale.

    Returns {process_units, variable_opex_inputs, meta} where process_units is a
    list of plain dicts (matching ProcessUnitSpec fields) and variable_opex_inputs
    is the OpenPyTEA {stream:{consumption,price_field}} skeleton — prices are filled
    by the runner from the request's assumptions.
    """
    pf = get(fuel_id)
    if pf is None:
        raise ValueError(f"No process function registered for molecule '{fuel_id}'.")
    # A supplied train REPLACES the code registry's equipment — the governed set from
    # tea_equipment_spec (migration 075). Everything else (the ratio, the stoichiometry,
    # the meta) is unchanged, so the only thing that varies is the sizing basis.
    if equipment:
        pf = replace(pf, equipment=tuple(equipment))
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
        "nodes": sorted({e.node for e in pf.equipment}),          # G6: canonical battery-limit nodes
        "scaling": {                                              # G4: how the sizing was scaled
            "reference_nameplate_t_per_year": REFERENCE_NAMEPLATE_T_YR,
            "requested_nameplate_t_per_year": round(nameplate_t_yr, 1),
            "ratio": round(ratio, 4),
            "method": "six-tenths rule, per-equipment: param = base_param × ratio**scale_exp",
            "default_scale_exponent": DEFAULT_SCALE_EXP,
            "component_scale_exponents": sorted({e.scale_exp for e in pf.equipment}),
            "extrapolated": bool(ratio < 0.2 or ratio > 10.0),    # beyond the tuned band
        },
        "total_product_per_primary": round(total_product_per_primary(pf), 4),
        "co_products": [{"name": cp.name, "mass_per_kg_primary": cp.mass_per_kg_primary,
                         "eur_per_t": cp.eur_per_t} for cp in pf.co_products],
        "coproduct_revenue_per_t_primary": round(coproduct_revenue_per_t_primary(pf), 2),
        # The mass balance, stated so it can be CHECKED rather than asserted.
        # integrity.mass_balance_flags() reads these three numbers; a reader can check
        # them with a calculator. `undeclared_outputs` is what the declared inputs
        # exceed the declared products by — reaction water, purge and vent, none of
        # which is declared today. It is reported, not hidden, and not treated as zero.
        "mass_balance": {
            "basis": "per tonne of PRIMARY product",
            "rule": "declared x total_product_per_primary / yield_frac",
            "inputs_t": round(_mass_in_per_t_primary(pf), 6),
            "products_t": round(total_product_per_primary(pf), 6),
            "undeclared_outputs_t": round(
                max(_mass_in_per_t_primary(pf) - total_product_per_primary(pf), 0.0), 6),
            "process_mass_intensity": (
                round(_mass_in_per_t_primary(pf) / total_product_per_primary(pf), 4)
                if total_product_per_primary(pf) else None),
            "note": ("Inputs are stoichiometry / yield_frac. Outputs count the primary "
                     "product and declared co-products only; reaction water, purge and "
                     "vent are NOT declared, so closure is not yet computable."),
        },
        # The CAPEX side's energy against the OPEX side's. integrity.energy_balance_flags
        # reads this; it deliberately does not pick a winner (see that function).
        "energy_reconciliation": _energy_reconciliation(
            pf, nameplate_t_yr, capacity_factor),
        "mass_in_t_per_t_primary": round(_mass_in_per_t_primary(pf), 6),
        "mass_out_t_per_t_primary": round(total_product_per_primary(pf), 6),
        "undeclared_outputs_t_per_t_primary": round(
            max(_mass_in_per_t_primary(pf) - total_product_per_primary(pf), 0.0), 6),
        "note": pf.note,
    }
    return {"process_units": units, "variable_opex_inputs": var_opex_skeleton, "meta": meta}
