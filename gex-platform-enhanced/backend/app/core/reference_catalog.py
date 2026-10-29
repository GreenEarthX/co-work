"""
The closed catalog of reference parameters — what may be stored, not what it is.
================================================================================
This module holds no reference NUMBERS. It says which parameter keys exist, which
unit family each belongs to, and which units that family accepts. The numbers live
in `reference_parameter` (migration 061).

Why closed: two quantities that share a name must not share a key. 041 records the
case that matters most — fuel LHV and electrolyser consumption are both "kWh/kg"
and both have been called "specific energy". Here they are distinct by KEY and by
FAMILY: `electrolyser_system_sec` is SPECIFIC_POWER (energy per kg PRODUCED), and
anything describing a fuel's energy content would be ENERGY_PER_MASS. A unit string
alone cannot tell them apart, so the family is fixed per key and a proposal cannot
choose it.

UNIT_FAMILIES mirrors `frontend/src/engine/registry/unitFamilies.ts`. Every family
and unit named here must exist there; a test reads that file and enforces it.
"""
from __future__ import annotations

from typing import NamedTuple

# Subset of the frontend's unit families that the registry uses.
UNIT_FAMILIES: dict[str, tuple[str, ...]] = {
    "COST_PER_POWER":    ("EUR/kW", "USD/kW"),
    "COST_PER_MASS":     ("EUR/kg", "EUR/t", "USD/t", "USD/kg"),
    "COST_PER_ENERGY":   ("EUR/MWh", "EUR/kWh", "USD/MWh"),
    "SPECIFIC_POWER":    ("kWh/kg",),
    "ENERGY_PER_MASS":   ("kWh/kg", "MJ/kg"),
    "LIFETIME":          ("year", "h", "month"),
    "AVAILABILITY":      ("fraction",),
    "FRACTION_OF_TOTAL": ("fraction",),
    "RATE_PER_YEAR":     ("fraction/yr",),
    # Not monetary: an FX rate is a ratio of two currencies, so a row in it carries
    # no `currency` / `price_base_date` (see MONETARY_FAMILIES below). The frontend
    # allows USD/EUR, EUR/USD and GBP/EUR; only the pair GEX prices in is used here.
    "EXCHANGE_RATE":     ("EUR/USD",),
    # A relative standard deviation is a ratio of a quantity to itself, so it carries no
    # unit. Deliberately NOT FRACTION_OF_TOTAL: these are not a share of any total.
    "DIMENSIONLESS":     ("-",),
}

# Families whose values are money: a row in one must carry currency + price date.
MONETARY_FAMILIES = frozenset({"COST_PER_POWER", "COST_PER_MASS", "COST_PER_ENERGY"})

PATHWAYS = ("H2", "H2_PEM", "H2_ALK", "NH3", "E_METHANOL", "E_NG", "SAF", "ANY")
SOURCE_CLASSES = ("public_source", "gex_cohort", "gex_assumption")

# Pathway fallback: a technology falls back to its product, then to ANY.
_PATHWAY_PARENT = {"H2_PEM": "H2", "H2_ALK": "H2"}

EU27 = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"})


class ParameterDef(NamedTuple):
    family: str
    description: str


PARAMETERS: dict[str, ParameterDef] = {
    "electrolyser_installed_capex": ParameterDef(
        "COST_PER_POWER", "Installed electrolyser system capex per kW of electrical input"),
    "electrolyser_system_sec": ParameterDef(
        "SPECIFIC_POWER", "Electrolyser SYSTEM electricity per kg H2 PRODUCED (stack + "
        "balance of plant). Not the fuel's LHV — see fuel_catalog.specific_energy_value"),
    "stack_life_hours": ParameterDef(
        "LIFETIME", "Stack replacement interval, operating hours"),
    "stack_replacement_pct_capex": ParameterDef(
        "FRACTION_OF_TOTAL", "Cost of one stack replacement as a fraction of installed capex"),
    "output_degradation_pct_per_year": ParameterDef(
        "RATE_PER_YEAR", "Output loss per year at constant power, reset at stack replacement"),
    "h2_price_rfnbo": ParameterDef("COST_PER_MASS", "RFNBO (renewable) hydrogen price"),
    "h2_price_grey": ParameterDef("COST_PER_MASS", "Conventional (SMR) hydrogen price"),
    "ppa_price_solar": ParameterDef("COST_PER_ENERGY", "Solar PPA price"),
    "ehb_premium": ParameterDef(
        "COST_PER_MASS", "European Hydrogen Bank fixed premium per kg"),
    "subsidy_45v_max": ParameterDef(
        "COST_PER_MASS", "45V clean hydrogen production credit, top tier"),
    "debt_gearing": ParameterDef(
        "FRACTION_OF_TOTAL", "Senior debt as a fraction of total capex"),
    # Capital-bridge fuel defaults. No seed rows: until an analyst proposes one,
    # these resolve to the code fallback, marked model_default.
    "offtake_price_base": ParameterDef(
        "COST_PER_MASS", "Commercial offtake base price of the final product"),
    "green_premium": ParameterDef(
        "COST_PER_MASS", "Green premium over the grey equivalent of the final product"),
    "plant_availability": ParameterDef("AVAILABILITY", "Plant availability factor"),
    "capex_contingency": ParameterDef(
        "FRACTION_OF_TOTAL", "Capex contingency as a fraction of capex"),
    "dsra_months": ParameterDef("LIFETIME", "Debt service reserve, months of debt service"),
    # Market spot reference per molecule (Marketplace). Seeded 2026-10-23 as
    # `proposed` from the values the screen used to hard-code — provenance
    # unknown, so not in force until approved. Two keys because one key has one
    # unit family: mass-priced molecules, and e-NG priced per MWh.
    "market_spot_price": ParameterDef("COST_PER_MASS", "Market spot reference price of the molecule"),
    "market_spot_price_energy": ParameterDef(
        "COST_PER_ENERGY", "Market spot reference price of an energy-priced molecule (e-NG)"),
    # TEA engine cost basis. OpenPyTEA's correlations are USD; this is the multiplier
    # that puts a capex into the project's base currency, and it sets the midpoint of
    # the +/-5% band a CFO override must sit inside. It was a hardcoded constant in
    # tea_engine/integrity.py (USD_TO_BASE) until 2026-10-26, so changing the rate
    # moved every priced capex with nothing proposing or approving it.
    "tea_fx_usd_to_eur": ParameterDef(
        "EXCHANGE_RATE", "USD->EUR multiplier applied to OpenPyTEA's USD cost "
        "correlations, and the benchmark a CFO FX override is bounded against"),
    # A BAND, not a point: consumers read value_low / value_high. An LCOP outside it is
    # flagged implausible and the result is downgraded to IMPLAUSIBLE, which blocks
    # promotion to a verified model_base_case — so widening it loosens a release gate,
    # which is exactly why it should take two people.
    "tea_lcop_plausible_band": ParameterDef(
        "COST_PER_MASS", "Plausible levelised cost of product. An LCOP outside "
        "[value_low, value_high] is flagged as a likely unit or scale error"),
    # Monte Carlo sampling policy. The default sigma sets the width of every band GEX
    # reports; the max is the refusal ceiling for a caller-supplied sigma.
    "tea_mc_default_rel_std": ParameterDef(
        "DIMENSIONLESS", "Default relative standard deviation applied to variable-OPEX "
        "prices, capacity factor and project lifetime in a TEA Monte Carlo run"),
    "tea_mc_max_rel_std": ParameterDef(
        "DIMENSIONLESS", "Largest relative standard deviation a caller may request "
        "before the Monte Carlo run is refused"),
}


def family_of(parameter_key: str) -> str | None:
    pdef = PARAMETERS.get(parameter_key)
    return pdef.family if pdef else None


def pathway_chain(pathway: str) -> list[str]:
    """`H2_PEM` -> [H2_PEM, H2, ANY]; `NH3` -> [NH3, ANY]; `ANY` -> [ANY]."""
    chain = [pathway]
    while chain[-1] in _PATHWAY_PARENT:
        chain.append(_PATHWAY_PARENT[chain[-1]])
    if chain[-1] != "ANY":
        chain.append("ANY")
    return chain


def region_chain(region: str) -> list[str]:
    """`DE` -> [DE, EU, ROW, ANY]; `CN` -> [CN, ANY]; `EU` -> [EU, ROW, ANY].

    ROW is "outside China" as the IEA uses it, so CN never falls back to ROW.
    """
    if region == "ANY":
        return ["ANY"]
    chain = [region]
    if region in EU27:
        chain.append("EU")
    if region != "CN":
        chain.append("ROW")
    chain.append("ANY")
    return list(dict.fromkeys(chain))
