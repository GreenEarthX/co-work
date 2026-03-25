"""
GEX Plant Builder — Equipment-Level CAPEX/OPEX Configuration Engine
v5.1

Computes CAPEX, OPEX, levelised cost, competitive gap, government support
needed, and certification distance from a configured greenfield plant.
"""
import math
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger("gex.plant_builder")


# ════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════

class MoleculeType(str, Enum):
    H2         = "H2"
    NH3        = "NH3"
    SAF        = "SAF"
    E_METHANOL = "E_METHANOL"
    E_NG       = "E_NG"


class CertificationRegime(str, Enum):
    RFNBO    = "RFNBO"
    RED_III  = "RED_III"
    US_45V   = "45V"
    CORSIA   = "CORSIA"
    CERTIFHY = "CertifHy"


class EquipmentCategory(str, Enum):
    ELECTROLYSER   = "ELECTROLYSER"
    REACTOR        = "REACTOR"
    BOP            = "BOP"
    STORAGE        = "STORAGE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    UTILITIES      = "UTILITIES"
    CONTROLS       = "CONTROLS"
    SAFETY         = "SAFETY"


# ════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class EquipmentItem:
    id: str                           # "PEM_ELEC_120MW"
    name: str                         # "PEM Electrolyser Stack — 120MW"
    category: str                     # ELECTROLYSER | REACTOR | BOP | ...
    unit_price_eur: int               # 65_000_000
    installation_multiplier: float    # 1.35 (total installed = price × multiplier)
    annual_om_pct: float              # 0.025 (2.5% of installed cost per year)
    annual_power_mwh: int             # 876_000 (for power-consuming equipment)
    annual_water_m3: int              # 0
    useful_life_years: int            # 20
    residual_value_pct: float         # 0.15
    capex_layer: str                  # "L2" — maps to CAPEX Layer Decomposition
    molecule_output: str              # "H2" | "SAF" | "NH3" | "E_METHANOL" | "ALL"
    capacity_tonnes_year: int         # output capacity
    cert_enables: list = field(default_factory=list)       # ["RFNBO"]
    cert_blocks: list = field(default_factory=list)        # ["45V"]
    cert_requirements: list = field(default_factory=list)  # conditions for cert
    technology_maturity: str = "PROVEN"   # PROVEN | FIRST_OF_KIND | DEMONSTRATION
    oem: str = ""                          # "Siemens Energy"
    description: str = ""


@dataclass
class PlantConfiguration:
    project_id: str
    molecule: str                       # MoleculeType value
    location_jurisdiction: str          # "FR"
    equipment: list                     # list of {equipment_id, quantity}
    power_price_eur_mwh: float          # 45.0
    water_price_eur_m3: float           # 2.50
    labour_count: int                   # 45 FTEs
    labour_cost_eur_year: float         # 65_000 per FTE
    insurance_pct_capex: float          # 0.005
    contingency_pct: float              # 0.10
    target_market_price_eur_t: float    # 1_500 for SAF
    wacc_pct: float = 0.09              # 9% default WACC
    project_life_years: int = 20


@dataclass
class PlantBuildResult:
    # ── CAPEX ──
    total_equipment_eur: int
    total_installed_eur: int
    contingency_eur: int
    total_capex_eur: int
    capex_per_layer: dict           # {"L1": x, "L2": y, ...}
    capex_by_category: dict         # {"ELECTROLYSER": x, ...}

    # ── OPEX ──
    annual_om_eur: int
    annual_power_eur: int
    annual_water_eur: int
    annual_labour_eur: int
    annual_insurance_eur: int
    total_annual_opex_eur: int

    # ── Output ──
    annual_output_tonnes: int
    levelised_cost_eur_t: float
    market_price_eur_t: float
    competitive_gap_eur_t: float    # positive = subsidy needed
    subsidy_needed_eur_t: float     # max(0, gap)
    subsidy_needed_total_eur_yr: int

    # ── Certification ──
    cert_readiness: dict            # {"RFNBO": 85, "RED_III": 92, ...}
    cert_blockers: list
    cert_premium_eur_t: dict        # {"RFNBO": +180, ...}
    effective_price_with_certs: float

    # ── Detail ──
    equipment_lines: list           # per-item breakdown
    annualised_capex_eur: int


# ════════════════════════════════════════════════════════════════
# CERT READINESS LOGIC
# ════════════════════════════════════════════════════════════════

# Certification requirements: what scores each enabling/blocking item contributes
_CERT_WEIGHTS = {
    "RFNBO": {
        "renewable_power":      30,   # must be supplied from renewable source
        "additionality":        25,   # new capacity dedicated to electrolysis
        "temporal_correlation": 20,   # hourly matching in same bidding zone
        "ghg_threshold":        15,   # < 3.38 kgCO2eq/kgH2
        "mass_balance":         10,   # certified mass-balance chain
    },
    "RED_III": {
        "renewable_power":      35,
        "ghg_threshold":        30,
        "mass_balance":         20,
        "third_party_audit":    15,
    },
    "45V": {
        "us_jurisdiction":      40,   # must be US-based project
        "clean_electricity":    30,
        "lifecycle_ghg":        20,
        "incrementality":       10,
    },
    "CORSIA": {
        "feedstock_origin":     30,
        "ghg_threshold":        35,
        "book_transfer":        20,
        "third_party_audit":    15,
    },
    "CertifHy": {
        "renewable_power":      40,
        "ghg_threshold":        35,
        "documentation":        25,
    },
}

_CERT_PREMIUMS_EUR_T = {
    ("H2", "RFNBO"):         400,
    ("H2", "RED_III"):        250,
    ("H2", "45V"):            300,
    ("H2", "CertifHy"):       100,
    ("NH3", "RFNBO"):         120,
    ("NH3", "RED_III"):        80,
    ("SAF", "RFNBO"):         350,
    ("SAF", "RED_III"):       280,
    ("SAF", "CORSIA"):        150,
    ("E_METHANOL", "RFNBO"):  200,
    ("E_METHANOL", "RED_III"): 150,
}


def _compute_cert_readiness(
    molecule: str,
    jurisdiction: str,
    cert_enables: list,    # all enables from all equipment items
    cert_blocks: list,     # all blocks
) -> tuple[dict, list, dict]:
    """
    Returns (readiness_pct_dict, blockers_list, premiums_dict).
    Readiness is a score 0–100 for each regime.
    """
    readiness = {}
    blockers = []
    premiums = {}

    for regime, weights in _CERT_WEIGHTS.items():
        # Hard blocks
        blocked = [b for b in cert_blocks if b == regime]
        if blocked:
            readiness[regime] = 0
            blockers.append(f"{regime} blocked by equipment configuration")
            continue

        # Special jurisdiction rule for 45V
        if regime == "45V" and jurisdiction not in ("US",):
            readiness[regime] = 0
            blockers.append(f"45V blocked: jurisdiction {jurisdiction} is not US")
            continue

        # Score based on what cert_enables contains
        score = 0
        for criterion, weight in weights.items():
            if criterion in cert_enables:
                score += weight
        # Base score for having any enabling equipment
        if cert_enables:
            score = max(score, 20)
        readiness[regime] = min(score, 100)

    # Premiums for regimes with readiness ≥ 80
    for regime, score in readiness.items():
        if score >= 80:
            key = (molecule, regime)
            if key in _CERT_PREMIUMS_EUR_T:
                premiums[regime] = _CERT_PREMIUMS_EUR_T[key]

    return readiness, blockers, premiums


# ════════════════════════════════════════════════════════════════
# PLANT BUILDER ENGINE
# ════════════════════════════════════════════════════════════════

class PlantBuilder:

    def __init__(self, equipment_catalog: list):
        self._catalog = {e.id: e for e in equipment_catalog}

    def get_catalog(
        self,
        molecule: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list:
        items = list(self._catalog.values())
        if molecule:
            items = [i for i in items if i.molecule_output in (molecule, "ALL")]
        if category:
            items = [i for i in items if i.category == category]
        return items

    def get_item(self, item_id: str) -> Optional[EquipmentItem]:
        return self._catalog.get(item_id)

    def build(self, config: PlantConfiguration) -> PlantBuildResult:
        """Compute full CAPEX/OPEX/levelised cost/certification from configuration."""

        equipment_lines = []
        total_equipment_eur = 0
        total_installed_eur = 0
        total_annual_om = 0
        total_annual_power_mwh = 0
        total_annual_water_m3 = 0
        total_output_tonnes = 0
        capex_per_layer: dict = {}
        capex_by_category: dict = {}
        all_cert_enables: list = []
        all_cert_blocks: list = []

        for line in config.equipment:
            item_id = line.get("equipment_id") or line.get("id")
            qty = int(line.get("quantity", 1))
            item = self._catalog.get(item_id)
            if not item:
                logger.warning("Unknown equipment id: %s — skipping", item_id)
                continue

            eq_cost = item.unit_price_eur * qty
            installed_cost = int(eq_cost * item.installation_multiplier)
            annual_om = int(installed_cost * item.annual_om_pct)
            annual_power = item.annual_power_mwh * qty
            annual_water = item.annual_water_m3 * qty
            output = item.capacity_tonnes_year * qty

            total_equipment_eur += eq_cost
            total_installed_eur += installed_cost
            total_annual_om += annual_om
            total_annual_power_mwh += annual_power
            total_annual_water_m3 += annual_water
            total_output_tonnes += output

            # Layer aggregation
            layer = item.capex_layer or "L3"
            capex_per_layer[layer] = capex_per_layer.get(layer, 0) + installed_cost

            # Category aggregation
            cat = item.category
            capex_by_category[cat] = capex_by_category.get(cat, 0) + installed_cost

            # Cert aggregation
            all_cert_enables.extend(item.cert_enables)
            all_cert_blocks.extend(item.cert_blocks)

            equipment_lines.append({
                "equipment_id": item_id,
                "name": item.name,
                "category": item.category,
                "quantity": qty,
                "unit_price_eur": item.unit_price_eur,
                "equipment_cost_eur": eq_cost,
                "installed_cost_eur": installed_cost,
                "annual_om_eur": annual_om,
                "annual_power_mwh": annual_power,
                "annual_output_tonnes": output,
                "capex_layer": layer,
                "technology_maturity": item.technology_maturity,
                "oem": item.oem,
            })

        # ── CAPEX ──
        contingency_eur = int(total_installed_eur * config.contingency_pct)
        total_capex_eur = total_installed_eur + contingency_eur

        # ── OPEX ──
        annual_power_eur = int(total_annual_power_mwh * config.power_price_eur_mwh)
        annual_water_eur = int(total_annual_water_m3 * config.water_price_eur_m3)
        annual_labour_eur = int(config.labour_count * config.labour_cost_eur_year)
        annual_insurance_eur = int(total_capex_eur * config.insurance_pct_capex)
        total_annual_opex_eur = (
            total_annual_om
            + annual_power_eur
            + annual_water_eur
            + annual_labour_eur
            + annual_insurance_eur
        )

        # ── Levelised Cost ──
        # Annualised CAPEX = CAPEX × CRF
        # CRF = wacc * (1+wacc)^n / ((1+wacc)^n - 1)
        wacc = config.wacc_pct
        n = config.project_life_years
        if wacc > 0:
            crf = (wacc * (1 + wacc) ** n) / ((1 + wacc) ** n - 1)
        else:
            crf = 1 / n
        annualised_capex = int(total_capex_eur * crf)

        output = max(total_output_tonnes, 1)  # guard div/0
        levelised_cost = (annualised_capex + total_annual_opex_eur) / output

        # ── Gap / Subsidy ──
        market_price = config.target_market_price_eur_t
        gap = levelised_cost - market_price
        subsidy_per_t = max(0.0, gap)
        subsidy_total = int(subsidy_per_t * output)

        # ── Certification ──
        cert_readiness, cert_blockers, cert_premiums = _compute_cert_readiness(
            molecule=config.molecule,
            jurisdiction=config.location_jurisdiction,
            cert_enables=list(set(all_cert_enables)),
            cert_blocks=list(set(all_cert_blocks)),
        )

        best_premium = max(cert_premiums.values(), default=0.0)
        effective_price = levelised_cost - best_premium

        return PlantBuildResult(
            total_equipment_eur=total_equipment_eur,
            total_installed_eur=total_installed_eur,
            contingency_eur=contingency_eur,
            total_capex_eur=total_capex_eur,
            capex_per_layer=capex_per_layer,
            capex_by_category=capex_by_category,
            annual_om_eur=total_annual_om,
            annual_power_eur=annual_power_eur,
            annual_water_eur=annual_water_eur,
            annual_labour_eur=annual_labour_eur,
            annual_insurance_eur=annual_insurance_eur,
            total_annual_opex_eur=total_annual_opex_eur,
            annual_output_tonnes=total_output_tonnes,
            levelised_cost_eur_t=round(levelised_cost, 2),
            market_price_eur_t=market_price,
            competitive_gap_eur_t=round(gap, 2),
            subsidy_needed_eur_t=round(subsidy_per_t, 2),
            subsidy_needed_total_eur_yr=subsidy_total,
            cert_readiness=cert_readiness,
            cert_blockers=cert_blockers,
            cert_premium_eur_t=cert_premiums,
            effective_price_with_certs=round(effective_price, 2),
            equipment_lines=equipment_lines,
            annualised_capex_eur=annualised_capex,
        )


# ════════════════════════════════════════════════════════════════
# EQUIPMENT CATALOG — 50+ items
# ════════════════════════════════════════════════════════════════

EQUIPMENT_CATALOG: list[EquipmentItem] = [

    # ── PEM Electrolysers ──────────────────────────────────────
    EquipmentItem(
        id="PEM_ELEC_10MW", name="PEM Electrolyser Stack — 10 MW",
        category="ELECTROLYSER", unit_price_eur=6_500_000,
        installation_multiplier=1.35, annual_om_pct=0.025,
        annual_power_mwh=87_600, annual_water_m3=175_200,
        useful_life_years=20, residual_value_pct=0.15,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=438,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="Nel Hydrogen",
        description="10 MW PEM stack, 55 kWh/kg specific energy",
    ),
    EquipmentItem(
        id="PEM_ELEC_20MW", name="PEM Electrolyser Stack — 20 MW",
        category="ELECTROLYSER", unit_price_eur=12_000_000,
        installation_multiplier=1.35, annual_om_pct=0.025,
        annual_power_mwh=175_200, annual_water_m3=350_400,
        useful_life_years=20, residual_value_pct=0.15,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=876,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="ITM Power",
        description="20 MW PEM stack, containerised module",
    ),
    EquipmentItem(
        id="PEM_ELEC_50MW", name="PEM Electrolyser Stack — 50 MW",
        category="ELECTROLYSER", unit_price_eur=28_000_000,
        installation_multiplier=1.30, annual_om_pct=0.025,
        annual_power_mwh=438_000, annual_water_m3=876_000,
        useful_life_years=20, residual_value_pct=0.15,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=2_190,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="Siemens Energy",
        description="50 MW SILYZER 300 PEM module",
    ),
    EquipmentItem(
        id="PEM_ELEC_120MW", name="PEM Electrolyser Stack — 120 MW",
        category="ELECTROLYSER", unit_price_eur=65_000_000,
        installation_multiplier=1.35, annual_om_pct=0.025,
        annual_power_mwh=876_000, annual_water_m3=1_752_000,
        useful_life_years=20, residual_value_pct=0.15,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=5_256,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="Plug Power",
        description="120 MW PEM, gigawatt-class electrolyser plant block",
    ),

    # ── Alkaline Electrolysers ─────────────────────────────────
    EquipmentItem(
        id="ALK_ELEC_10MW", name="Alkaline Electrolyser — 10 MW",
        category="ELECTROLYSER", unit_price_eur=5_000_000,
        installation_multiplier=1.30, annual_om_pct=0.020,
        annual_power_mwh=88_000, annual_water_m3=200_000,
        useful_life_years=25, residual_value_pct=0.20,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=430,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="Nel Hydrogen",
        description="10 MW alkaline A-Series, proven at large scale",
    ),
    EquipmentItem(
        id="ALK_ELEC_20MW", name="Alkaline Electrolyser — 20 MW",
        category="ELECTROLYSER", unit_price_eur=9_500_000,
        installation_multiplier=1.30, annual_om_pct=0.020,
        annual_power_mwh=176_000, annual_water_m3=400_000,
        useful_life_years=25, residual_value_pct=0.20,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=860,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="ThyssenKrupp Uhde",
        description="20 MW ThyssenKrupp AWE module",
    ),
    EquipmentItem(
        id="ALK_ELEC_50MW", name="Alkaline Electrolyser — 50 MW",
        category="ELECTROLYSER", unit_price_eur=22_000_000,
        installation_multiplier=1.28, annual_om_pct=0.018,
        annual_power_mwh=440_000, annual_water_m3=1_000_000,
        useful_life_years=25, residual_value_pct=0.20,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=2_150,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="John Cockerill",
        description="50 MW alkaline, IHT 5040 Mono Bloc design",
    ),
    EquipmentItem(
        id="ALK_ELEC_100MW", name="Alkaline Electrolyser — 100 MW",
        category="ELECTROLYSER", unit_price_eur=42_000_000,
        installation_multiplier=1.28, annual_om_pct=0.018,
        annual_power_mwh=880_000, annual_water_m3=2_000_000,
        useful_life_years=25, residual_value_pct=0.20,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=4_300,
        cert_enables=["renewable_power", "additionality"],
        technology_maturity="PROVEN", oem="ThyssenKrupp Uhde",
        description="100 MW AWE platform, modular skids",
    ),
    EquipmentItem(
        id="SOEC_ELEC_5MW", name="SOEC Electrolyser — 5 MW",
        category="ELECTROLYSER", unit_price_eur=7_500_000,
        installation_multiplier=1.50, annual_om_pct=0.035,
        annual_power_mwh=38_500, annual_water_m3=77_000,
        useful_life_years=12, residual_value_pct=0.10,
        capex_layer="L2", molecule_output="H2",
        capacity_tonnes_year=290,
        cert_enables=["renewable_power", "additionality", "ghg_threshold"],
        technology_maturity="FIRST_OF_KIND", oem="Topsoe / Sunfire",
        description="SOEC high-efficiency electrolysis, ~37 kWh/kg with waste heat",
    ),

    # ── Fischer-Tropsch Reactors ───────────────────────────────
    EquipmentItem(
        id="FT_REACTOR_10KT", name="Fischer-Tropsch Reactor — 10 kt/yr SAF",
        category="REACTOR", unit_price_eur=18_000_000,
        installation_multiplier=1.45, annual_om_pct=0.030,
        annual_power_mwh=12_000, annual_water_m3=0,
        useful_life_years=25, residual_value_pct=0.25,
        capex_layer="L2", molecule_output="SAF",
        capacity_tonnes_year=10_000,
        cert_enables=["feedstock_origin", "ghg_threshold"],
        technology_maturity="FIRST_OF_KIND", oem="Velocys",
        description="Microchannel FT reactor, 10 kt/yr SAF, eFuels ready",
    ),
    EquipmentItem(
        id="FT_REACTOR_50KT", name="Fischer-Tropsch Reactor — 50 kt/yr SAF",
        category="REACTOR", unit_price_eur=75_000_000,
        installation_multiplier=1.40, annual_om_pct=0.028,
        annual_power_mwh=50_000, annual_water_m3=0,
        useful_life_years=25, residual_value_pct=0.25,
        capex_layer="L2", molecule_output="SAF",
        capacity_tonnes_year=50_000,
        cert_enables=["feedstock_origin", "ghg_threshold", "book_transfer"],
        technology_maturity="FIRST_OF_KIND", oem="Ineratec",
        description="Modular compact FT synthesis, 50 kt/yr SAF capacity",
    ),
    EquipmentItem(
        id="FT_UPGRADING", name="FT Product Upgrading Unit (Hydrotreater)",
        category="REACTOR", unit_price_eur=12_000_000,
        installation_multiplier=1.35, annual_om_pct=0.025,
        annual_power_mwh=8_000, annual_water_m3=0,
        useful_life_years=30, residual_value_pct=0.30,
        capex_layer="L2", molecule_output="SAF",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Axens",
        description="Hydrotreating and product upgrading for FT wax to SAF",
    ),

    # ── Ammonia Synthesis ─────────────────────────────────────
    EquipmentItem(
        id="NH3_SYNTH_50KT", name="Ammonia Synthesis Loop — 50 kt/yr",
        category="REACTOR", unit_price_eur=35_000_000,
        installation_multiplier=1.40, annual_om_pct=0.025,
        annual_power_mwh=15_000, annual_water_m3=0,
        useful_life_years=30, residual_value_pct=0.30,
        capex_layer="L2", molecule_output="NH3",
        capacity_tonnes_year=50_000,
        cert_enables=["renewable_power", "ghg_threshold"],
        technology_maturity="PROVEN", oem="Haldor Topsoe",
        description="Haber-Bosch loop, 50 kt/yr green ammonia, KAAP catalyst",
    ),
    EquipmentItem(
        id="NH3_SYNTH_200KT", name="Ammonia Synthesis Loop — 200 kt/yr",
        category="REACTOR", unit_price_eur=120_000_000,
        installation_multiplier=1.38, annual_om_pct=0.022,
        annual_power_mwh=50_000, annual_water_m3=0,
        useful_life_years=30, residual_value_pct=0.35,
        capex_layer="L2", molecule_output="NH3",
        capacity_tonnes_year=200_000,
        cert_enables=["renewable_power", "ghg_threshold"],
        technology_maturity="PROVEN", oem="ThyssenKrupp Uhde",
        description="Large-scale green ammonia synthesis, 200 kt/yr",
    ),
    EquipmentItem(
        id="ASU_50KT", name="Air Separation Unit — N₂ for 50 kt/yr NH3",
        category="UTILITIES", unit_price_eur=8_000_000,
        installation_multiplier=1.30, annual_om_pct=0.020,
        annual_power_mwh=40_000, annual_water_m3=0,
        useful_life_years=25, residual_value_pct=0.25,
        capex_layer="L3", molecule_output="NH3",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Air Liquide",
        description="Cryogenic ASU supplying nitrogen feed for ammonia synthesis",
    ),

    # ── Methanol Synthesis ────────────────────────────────────
    EquipmentItem(
        id="MEOH_SYNTH_50KT", name="eMethanol Synthesis Reactor — 50 kt/yr",
        category="REACTOR", unit_price_eur=28_000_000,
        installation_multiplier=1.38, annual_om_pct=0.025,
        annual_power_mwh=10_000, annual_water_m3=0,
        useful_life_years=25, residual_value_pct=0.25,
        capex_layer="L2", molecule_output="E_METHANOL",
        capacity_tonnes_year=50_000,
        cert_enables=["renewable_power", "ghg_threshold"],
        technology_maturity="PROVEN", oem="Johnson Matthey",
        description="Methanol synthesis via CO2 + H2, 50 kt/yr",
    ),
    EquipmentItem(
        id="MEOH_SYNTH_100KT", name="eMethanol Synthesis Reactor — 100 kt/yr",
        category="REACTOR", unit_price_eur=52_000_000,
        installation_multiplier=1.35, annual_om_pct=0.022,
        annual_power_mwh=18_000, annual_water_m3=0,
        useful_life_years=25, residual_value_pct=0.25,
        capex_layer="L2", molecule_output="E_METHANOL",
        capacity_tonnes_year=100_000,
        cert_enables=["renewable_power", "ghg_threshold"],
        technology_maturity="PROVEN", oem="Lurgi / Air Products",
        description="100 kt/yr eMethanol synthesis for marine fuel",
    ),

    # ── CO2 Capture / DAC ─────────────────────────────────────
    EquipmentItem(
        id="CO2_CAPTURE_50KT", name="CO2 Capture Unit — 50 kt/yr",
        category="UTILITIES", unit_price_eur=22_000_000,
        installation_multiplier=1.45, annual_om_pct=0.030,
        annual_power_mwh=20_000, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.15,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["feedstock_origin"],
        technology_maturity="PROVEN", oem="Aker Carbon Capture",
        description="Post-combustion CO2 capture for FT/MeOH feedstock",
    ),
    EquipmentItem(
        id="DAC_10KT", name="Direct Air Capture — 10 kt CO2/yr",
        category="UTILITIES", unit_price_eur=55_000_000,
        installation_multiplier=1.50, annual_om_pct=0.040,
        annual_power_mwh=35_000, annual_water_m3=0,
        useful_life_years=15, residual_value_pct=0.10,
        capex_layer="L2", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["feedstock_origin", "ghg_threshold"],
        technology_maturity="FIRST_OF_KIND", oem="Climeworks / Carbon Engineering",
        description="DAC unit — enables RFNBO-compliant CO2 feedstock",
    ),

    # ── Compressors ───────────────────────────────────────────
    EquipmentItem(
        id="H2_COMPRESSOR_100BAR", name="H₂ Compressor — 100 bar, 5 t/hr",
        category="BOP", unit_price_eur=2_500_000,
        installation_multiplier=1.25, annual_om_pct=0.030,
        annual_power_mwh=4_380, annual_water_m3=0,
        useful_life_years=15, residual_value_pct=0.20,
        capex_layer="L3", molecule_output="H2",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Burckhardt Compression",
        description="Reciprocating H2 compressor to 100 bar, 5 t/hr throughput",
    ),
    EquipmentItem(
        id="H2_COMPRESSOR_700BAR", name="H₂ Compressor — 700 bar (FCEV grade)",
        category="BOP", unit_price_eur=4_000_000,
        installation_multiplier=1.30, annual_om_pct=0.035,
        annual_power_mwh=6_000, annual_water_m3=0,
        useful_life_years=12, residual_value_pct=0.15,
        capex_layer="L3", molecule_output="H2",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="PDC Machines",
        description="700 bar ionic compressor for mobility refuelling",
    ),

    # ── Heat Exchangers ───────────────────────────────────────
    EquipmentItem(
        id="HEAT_EXCHANGER_MAIN", name="Main Process Heat Exchanger Network",
        category="BOP", unit_price_eur=3_500_000,
        installation_multiplier=1.30, annual_om_pct=0.015,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=30, residual_value_pct=0.40,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Alfa Laval",
        description="Shell-and-tube + plate heat exchangers for process heat integration",
    ),

    # ── Water Treatment ───────────────────────────────────────
    EquipmentItem(
        id="WATER_TREATMENT_500M3", name="Demineralised Water Plant — 500 m³/day",
        category="UTILITIES", unit_price_eur=4_500_000,
        installation_multiplier=1.25, annual_om_pct=0.020,
        annual_power_mwh=1_500, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.25,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["temporal_correlation"],
        technology_maturity="PROVEN", oem="Veolia",
        description="RO + EDI demineralisation, 500 m³/day to PEM feed spec",
    ),
    EquipmentItem(
        id="WATER_TREATMENT_2000M3", name="Demineralised Water Plant — 2,000 m³/day",
        category="UTILITIES", unit_price_eur=14_000_000,
        installation_multiplier=1.25, annual_om_pct=0.020,
        annual_power_mwh=5_000, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.25,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["temporal_correlation"],
        technology_maturity="PROVEN", oem="Veolia",
        description="Large-scale demineralisation plant for 100+ MW electrolyser",
    ),

    # ── Storage Tanks ─────────────────────────────────────────
    EquipmentItem(
        id="H2_STORAGE_CAVE", name="H₂ Underground Cavern Storage — 1,000 t",
        category="STORAGE", unit_price_eur=40_000_000,
        installation_multiplier=1.20, annual_om_pct=0.010,
        annual_power_mwh=500, annual_water_m3=0,
        useful_life_years=50, residual_value_pct=0.70,
        capex_layer="L1", molecule_output="H2",
        capacity_tonnes_year=0,
        cert_enables=["mass_balance"],
        technology_maturity="PROVEN", oem="Equinor / Storengy",
        description="Salt cavern H2 storage, seasonal buffer",
    ),
    EquipmentItem(
        id="H2_STORAGE_TANKS", name="Pressurised H₂ Storage Tanks — 50 t",
        category="STORAGE", unit_price_eur=6_000_000,
        installation_multiplier=1.20, annual_om_pct=0.010,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=30, residual_value_pct=0.50,
        capex_layer="L3", molecule_output="H2",
        capacity_tonnes_year=0,
        cert_enables=["mass_balance"],
        technology_maturity="PROVEN", oem="Hexagon / Faber",
        description="300 bar composite H2 storage vessels, 50 t buffer",
    ),
    EquipmentItem(
        id="NH3_STORAGE_10KT", name="Ammonia Storage Tank — 10,000 t",
        category="STORAGE", unit_price_eur=8_000_000,
        installation_multiplier=1.25, annual_om_pct=0.008,
        annual_power_mwh=500, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.60,
        capex_layer="L1", molecule_output="NH3",
        capacity_tonnes_year=0,
        cert_enables=["mass_balance"],
        technology_maturity="PROVEN", oem="Wheatley Group",
        description="Refrigerated ammonia tank at -33°C, 10,000 t",
    ),
    EquipmentItem(
        id="SAF_STORAGE_5KT", name="SAF Storage Tanks — 5,000 t",
        category="STORAGE", unit_price_eur=3_500_000,
        installation_multiplier=1.20, annual_om_pct=0.008,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.65,
        capex_layer="L1", molecule_output="SAF",
        capacity_tonnes_year=0,
        cert_enables=["book_transfer", "mass_balance"],
        technology_maturity="PROVEN", oem="Oiltanking",
        description="Floating-roof SAF storage, airport supply ready",
    ),
    EquipmentItem(
        id="MEOH_STORAGE_5KT", name="Methanol Storage Tank — 5,000 t",
        category="STORAGE", unit_price_eur=2_500_000,
        installation_multiplier=1.20, annual_om_pct=0.008,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.65,
        capex_layer="L1", molecule_output="E_METHANOL",
        capacity_tonnes_year=0,
        cert_enables=["mass_balance"],
        technology_maturity="PROVEN", oem="Tank Holdings",
        description="Floating-roof methanol storage, ATEX-rated",
    ),

    # ── Grid Connection & Power Electronics ───────────────────
    EquipmentItem(
        id="GRID_CONN_100MW", name="Grid Connection — 100 MW substation",
        category="INFRASTRUCTURE", unit_price_eur=12_000_000,
        installation_multiplier=1.20, annual_om_pct=0.015,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.70,
        capex_layer="L1", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["temporal_correlation"],
        technology_maturity="PROVEN", oem="Siemens / ABB",
        description="132/11kV substation, 100 MW grid connection",
    ),
    EquipmentItem(
        id="GRID_CONN_300MW", name="Grid Connection — 300 MW substation",
        category="INFRASTRUCTURE", unit_price_eur=30_000_000,
        installation_multiplier=1.20, annual_om_pct=0.015,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.70,
        capex_layer="L1", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["temporal_correlation"],
        technology_maturity="PROVEN", oem="Siemens / ABB",
        description="220/66kV substation, 300 MW grid connection",
    ),
    EquipmentItem(
        id="POWER_ELECTRONICS", name="Rectifiers & Power Converters",
        category="BOP", unit_price_eur=5_000_000,
        installation_multiplier=1.20, annual_om_pct=0.020,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=15, residual_value_pct=0.15,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="ABB",
        description="AC/DC rectifiers and thyristor bridges for electrolyser bus",
    ),
    EquipmentItem(
        id="BESS_20MWH", name="Battery Energy Storage — 20 MWh",
        category="UTILITIES", unit_price_eur=8_000_000,
        installation_multiplier=1.20, annual_om_pct=0.015,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=12, residual_value_pct=0.10,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["temporal_correlation", "additionality"],
        technology_maturity="PROVEN", oem="CATL / Fluence",
        description="BESS for renewable intermittency buffering, enables hourly matching",
    ),

    # ── Nitrogen Generation ───────────────────────────────────
    EquipmentItem(
        id="N2_PSA_1000NM3H", name="Nitrogen PSA — 1,000 Nm³/hr",
        category="UTILITIES", unit_price_eur=1_200_000,
        installation_multiplier=1.25, annual_om_pct=0.020,
        annual_power_mwh=1_800, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.20,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Air Products",
        description="PSA nitrogen generator for inerting and purging",
    ),

    # ── Site Infrastructure ───────────────────────────────────
    EquipmentItem(
        id="SITE_PREP", name="Site Preparation & Civil Works",
        category="INFRASTRUCTURE", unit_price_eur=15_000_000,
        installation_multiplier=1.00, annual_om_pct=0.005,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.80,
        capex_layer="L1", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="",
        description="Site clearing, grading, foundations, drainage, roads",
    ),
    EquipmentItem(
        id="BUILDINGS_CONTROL", name="Control Building & Operations Centre",
        category="INFRASTRUCTURE", unit_price_eur=4_500_000,
        installation_multiplier=1.10, annual_om_pct=0.010,
        annual_power_mwh=500, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.75,
        capex_layer="L1", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="",
        description="Blast-resistant control room, MCC room, offices",
    ),
    EquipmentItem(
        id="FIRE_PROTECTION", name="Fire Protection System",
        category="SAFETY", unit_price_eur=2_800_000,
        installation_multiplier=1.20, annual_om_pct=0.025,
        annual_power_mwh=100, annual_water_m3=0,
        useful_life_years=25, residual_value_pct=0.30,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Tyco",
        description="Deluge, foam, gaseous suppression — ATEX zone rated",
    ),
    EquipmentItem(
        id="FLARING_SYSTEM", name="Flare Stack & Blowdown Drum",
        category="SAFETY", unit_price_eur=1_500_000,
        installation_multiplier=1.25, annual_om_pct=0.020,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=30, residual_value_pct=0.30,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Zeeco",
        description="H2/ammonia emergency flare, ATEX-rated relief system",
    ),

    # ── DCS / SCADA / Controls ────────────────────────────────
    EquipmentItem(
        id="DCS_SCADA_MAIN", name="DCS/SCADA System",
        category="CONTROLS", unit_price_eur=3_500_000,
        installation_multiplier=1.15, annual_om_pct=0.040,
        annual_power_mwh=200, annual_water_m3=0,
        useful_life_years=15, residual_value_pct=0.10,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["mass_balance", "documentation"],
        technology_maturity="PROVEN", oem="Honeywell / Emerson",
        description="Distributed control system, SCADA, historian for RFNBO reporting",
    ),
    EquipmentItem(
        id="METERING_CERTIFIED", name="Fiscal Metering Package — Certified",
        category="CONTROLS", unit_price_eur=1_800_000,
        installation_multiplier=1.10, annual_om_pct=0.025,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=15, residual_value_pct=0.15,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["mass_balance", "documentation", "third_party_audit"],
        technology_maturity="PROVEN", oem="Emerson",
        description="Certified fiscal metering for GoO chain of custody",
    ),
    EquipmentItem(
        id="ENERGY_MANAGEMENT", name="Energy Management System",
        category="CONTROLS", unit_price_eur=900_000,
        installation_multiplier=1.10, annual_om_pct=0.030,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=10, residual_value_pct=0.05,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["temporal_correlation", "additionality"],
        technology_maturity="PROVEN", oem="ABB",
        description="EMS for hourly renewable matching (RFNBO temporal correlation)",
    ),

    # ── H2 Pipeline / Offtake ─────────────────────────────────
    EquipmentItem(
        id="H2_PIPELINE_1KM", name="H₂ Pipeline — 1 km, DN200",
        category="INFRASTRUCTURE", unit_price_eur=2_000_000,
        installation_multiplier=1.10, annual_om_pct=0.010,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.60,
        capex_layer="L1", molecule_output="H2",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="",
        description="DN200 H2 pipeline including cathodic protection, per km",
    ),
    EquipmentItem(
        id="H2_LOADING_TRAILER", name="H₂ Tube Trailer Loading Bay",
        category="INFRASTRUCTURE", unit_price_eur=1_200_000,
        installation_multiplier=1.20, annual_om_pct=0.015,
        annual_power_mwh=200, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.25,
        capex_layer="L3", molecule_output="H2",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Luxfer",
        description="Tube trailer loading & unloading bay, 350/700 bar",
    ),
    EquipmentItem(
        id="NH3_LOADING_JETTY", name="Ammonia Export Jetty",
        category="INFRASTRUCTURE", unit_price_eur=25_000_000,
        installation_multiplier=1.15, annual_om_pct=0.012,
        annual_power_mwh=500, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.65,
        capex_layer="L1", molecule_output="NH3",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="",
        description="Ammonia export jetty, 200,000 DWT vessel compatibility",
    ),
    EquipmentItem(
        id="SAF_PIPELINE_AIRPORT", name="SAF Pipeline to Airport Hydrant",
        category="INFRASTRUCTURE", unit_price_eur=8_000_000,
        installation_multiplier=1.15, annual_om_pct=0.010,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=40, residual_value_pct=0.70,
        capex_layer="L1", molecule_output="SAF",
        capacity_tonnes_year=0,
        cert_enables=["book_transfer"],
        technology_maturity="PROVEN", oem="",
        description="Dedicated SAF supply pipeline to airport fuel farm",
    ),

    # ── Utilities ─────────────────────────────────────────────
    EquipmentItem(
        id="COOLING_TOWER", name="Cooling Tower — 50 MW thermal duty",
        category="UTILITIES", unit_price_eur=3_200_000,
        installation_multiplier=1.25, annual_om_pct=0.020,
        annual_power_mwh=2_000, annual_water_m3=500_000,
        useful_life_years=25, residual_value_pct=0.30,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="SPX Cooling",
        description="Induced-draft cooling tower, 50 MW heat rejection capacity",
    ),
    EquipmentItem(
        id="BACKUP_GENERATOR", name="Emergency Diesel Generator — 2 MW",
        category="UTILITIES", unit_price_eur=600_000,
        installation_multiplier=1.20, annual_om_pct=0.030,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.20,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Caterpillar",
        description="Emergency UPS diesel genset for safe shutdown power",
    ),
    EquipmentItem(
        id="INSTRUMENT_AIR", name="Instrument Air Package",
        category="UTILITIES", unit_price_eur=800_000,
        installation_multiplier=1.20, annual_om_pct=0.020,
        annual_power_mwh=350, annual_water_m3=0,
        useful_life_years=20, residual_value_pct=0.20,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=[], technology_maturity="PROVEN", oem="Atlas Copco",
        description="Instrument air compressors + dryers + receiver",
    ),

    # ── Third-Party Audit & Certification Support ─────────────
    EquipmentItem(
        id="CERT_AUDIT_SYSTEM", name="Certification Data Management System",
        category="CONTROLS", unit_price_eur=500_000,
        installation_multiplier=1.05, annual_om_pct=0.100,
        annual_power_mwh=0, annual_water_m3=0,
        useful_life_years=10, residual_value_pct=0.05,
        capex_layer="L3", molecule_output="ALL",
        capacity_tonnes_year=0,
        cert_enables=["third_party_audit", "documentation", "mass_balance"],
        technology_maturity="PROVEN", oem="",
        description="Software platform for RFNBO/RED III compliance reporting and GoO issuance",
    ),
]


# ════════════════════════════════════════════════════════════════
# SINGLETON
# ════════════════════════════════════════════════════════════════

_builder: Optional[PlantBuilder] = None


def get_plant_builder() -> PlantBuilder:
    global _builder
    if _builder is None:
        _builder = PlantBuilder(EQUIPMENT_CATALOG)
        logger.info("Plant Builder catalog loaded: %d items", len(EQUIPMENT_CATALOG))
    return _builder
