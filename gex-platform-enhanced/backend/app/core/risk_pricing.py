"""
GEX Risk Pricing Database
File: app/core/risk_pricing.py

Maps component_type × technology_maturity × jurisdiction to a
cost-of-capital spread (bps over risk-free rate).

Replaces illustrative CAPEX layer numbers with structured,
adjustable market-sourced data.

Sources: BCG Hydrogen Finance Survey 2023, BNEF H2 LCOH Tracker,
IEA Hydrogen Cost Assumptions, IRENA Green Hydrogen Cost Study.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("gex.risk_pricing")


class ComponentType:
    PEM_ELECTROLYSER = "PEM_ELECTROLYSER"
    ALKALINE_ELECTROLYSER = "ALKALINE_ELECTROLYSER"
    SOEC_ELECTROLYSER = "SOEC_ELECTROLYSER"
    FT_REACTOR = "FT_REACTOR"
    AMMONIA_SYNTHESIS = "AMMONIA_SYNTHESIS"
    METHANOL_SYNTHESIS = "METHANOL_SYNTHESIS"
    BALANCE_OF_PLANT = "BALANCE_OF_PLANT"
    POWER_ELECTRONICS = "POWER_ELECTRONICS"
    STORAGE_TANKS = "STORAGE_TANKS"
    PORT_INFRASTRUCTURE = "PORT_INFRASTRUCTURE"
    PIPELINE = "PIPELINE"
    GRID_CONNECTION = "GRID_CONNECTION"
    WATER_TREATMENT = "WATER_TREATMENT"
    SITE_ENTITLEMENTS = "SITE_ENTITLEMENTS"
    DCS_SCADA = "DCS_SCADA"


class TechnologyMaturity:
    PROVEN = "PROVEN"           # Multiple commercial-scale installations
    FIRST_OF_KIND = "FIRST_OF_KIND"  # First commercial-scale, pilot proven
    DEMONSTRATION = "DEMONSTRATION"   # Pilot only, no commercial reference


@dataclass
class RiskPriceEntry:
    component_type: str
    maturity: str
    jurisdiction: str
    base_spread_bps: int
    useful_life_years: int
    residual_value_pct: float
    adjustment_factors: dict = field(default_factory=dict)
    source: str = ""

    def adjusted_spread(self, adjustments: Optional[dict] = None) -> int:
        spread = self.base_spread_bps
        if adjustments:
            for factor, delta_bps in adjustments.items():
                if factor in self.adjustment_factors:
                    spread += delta_bps
        return max(spread, 0)


@dataclass
class LayerWACCResult:
    layers: list[dict]
    blended_wacc_pct: float
    traditional_flat_wacc_pct: float
    wacc_saving_bps: int
    total_etv_premium_pct: float


class RiskPricingDB:

    def __init__(self):
        self._entries: dict[str, RiskPriceEntry] = {}
        self._risk_free_rates: dict[str, float] = {
            "FR": 0.030, "DE": 0.028, "NL": 0.029, "ES": 0.035,
            "IT": 0.040, "GB": 0.038, "US": 0.042, "EG": 0.090,
            "BR": 0.080, "IN": 0.070, "OM": 0.045, "AU": 0.038,
        }
        self._load_seed_data()

    def _key(self, component: str, maturity: str, jurisdiction: str) -> str:
        return f"{component}|{maturity}|{jurisdiction}"

    def _load_seed_data(self):
        for entry in SEED_PRICING:
            key = self._key(entry.component_type, entry.maturity, entry.jurisdiction)
            self._entries[key] = entry
        logger.info("Risk pricing DB loaded: %d entries", len(self._entries))

    def get_risk_free_rate(self, jurisdiction: str) -> float:
        return self._risk_free_rates.get(jurisdiction, 0.040)

    def get_spread(
        self,
        component_type: str,
        maturity: str,
        jurisdiction: str,
        adjustments: Optional[dict] = None,
    ) -> Optional[int]:
        key = self._key(component_type, maturity, jurisdiction)
        entry = self._entries.get(key)
        if not entry:
            generic_key = self._key(component_type, maturity, "GENERIC")
            entry = self._entries.get(generic_key)
        if not entry:
            return None
        return entry.adjusted_spread(adjustments)

    def get_entry(self, component_type: str, maturity: str, jurisdiction: str) -> Optional[RiskPriceEntry]:
        key = self._key(component_type, maturity, jurisdiction)
        entry = self._entries.get(key)
        if not entry:
            return self._entries.get(self._key(component_type, maturity, "GENERIC"))
        return entry

    def compute_layer_wacc(
        self,
        jurisdiction: str,
        capex_layers: list[dict],
        traditional_flat_wacc: float = 0.090,
    ) -> LayerWACCResult:
        """
        Compute per-layer WACC from risk pricing data.

        capex_layers: list of dicts with keys:
            name, amount, component_type, maturity, debt_ratio, etv_premium_pct
        """
        risk_free = self.get_risk_free_rate(jurisdiction)
        total_capex = sum(l["amount"] for l in capex_layers)
        layer_results = []
        weighted_wacc_sum = 0.0
        total_etv = 0.0

        for layer in capex_layers:
            spread_bps = self.get_spread(
                layer["component_type"],
                layer["maturity"],
                jurisdiction,
            )
            if spread_bps is None:
                spread_bps = 350  # default fallback

            entry = self.get_entry(layer["component_type"], layer["maturity"], jurisdiction)
            useful_life = entry.useful_life_years if entry else 20
            residual_pct = entry.residual_value_pct if entry else 0.10

            cost_of_debt = risk_free + (spread_bps / 10000)
            cost_of_equity = cost_of_debt + 0.045  # equity premium ~450bps
            debt_ratio = layer.get("debt_ratio", 0.60)
            equity_ratio = 1 - debt_ratio
            layer_wacc = (debt_ratio * cost_of_debt) + (equity_ratio * cost_of_equity)

            weight = layer["amount"] / total_capex if total_capex > 0 else 0
            weighted_wacc_sum += weight * layer_wacc

            etv = layer.get("etv_premium_pct", 0.0)
            total_etv += weight * etv

            layer_results.append({
                "name": layer["name"],
                "amount": layer["amount"],
                "weight_pct": round(weight * 100, 1),
                "component_type": layer["component_type"],
                "maturity": layer["maturity"],
                "spread_bps": spread_bps,
                "cost_of_debt_pct": round(cost_of_debt * 100, 2),
                "debt_ratio_pct": round(debt_ratio * 100, 0),
                "layer_wacc_pct": round(layer_wacc * 100, 2),
                "useful_life_years": useful_life,
                "residual_value_pct": round(residual_pct * 100, 1),
                "etv_premium_pct": round(etv * 100, 1),
            })

        blended = round(weighted_wacc_sum * 100, 2)
        saving = round((traditional_flat_wacc - weighted_wacc_sum) * 10000)

        return LayerWACCResult(
            layers=layer_results,
            blended_wacc_pct=blended,
            traditional_flat_wacc_pct=round(traditional_flat_wacc * 100, 2),
            wacc_saving_bps=saving,
            total_etv_premium_pct=round(total_etv * 100, 1),
        )

    def get_regulatory_risk_premium(self, jurisdiction: str) -> int:
        """Returns regulatory/political risk premium in bps for a jurisdiction."""
        premiums = {
            "FR": 10, "DE": 5, "NL": 8, "ES": 15, "IT": 25,
            "GB": 12, "US": 8, "EG": 120, "BR": 80, "IN": 60,
            "OM": 45, "AU": 10, "MA": 90, "KZ": 100, "CL": 35,
        }
        return premiums.get(jurisdiction, 50)


# ════════════════════════════════════════════════════════════
# SEED DATA — per component × maturity × jurisdiction
# ════════════════════════════════════════════════════════════

def _make_entries(component, maturities, jurisdictions):
    """Generate entries for a component across maturity/jurisdiction combinations."""
    entries = []
    for maturity, (base, life, resid) in maturities.items():
        for juris in jurisdictions:
            entries.append(RiskPriceEntry(
                component_type=component,
                maturity=maturity,
                jurisdiction=juris,
                base_spread_bps=base,
                useful_life_years=life,
                residual_value_pct=resid,
                source="BCG/BNEF/IEA composite",
            ))
    return entries

_JURIS = ["FR", "DE", "NL", "ES", "GB", "US", "GENERIC"]

SEED_PRICING = [
    *_make_entries(ComponentType.PEM_ELECTROLYSER, {
        "PROVEN": (280, 20, 0.15), "FIRST_OF_KIND": (380, 18, 0.10), "DEMONSTRATION": (500, 15, 0.05),
    }, _JURIS),
    *_make_entries(ComponentType.ALKALINE_ELECTROLYSER, {
        "PROVEN": (220, 25, 0.20), "FIRST_OF_KIND": (300, 22, 0.15), "DEMONSTRATION": (420, 18, 0.08),
    }, _JURIS),
    *_make_entries(ComponentType.FT_REACTOR, {
        "PROVEN": (200, 30, 0.30), "FIRST_OF_KIND": (320, 25, 0.20), "DEMONSTRATION": (450, 20, 0.10),
    }, _JURIS),
    *_make_entries(ComponentType.AMMONIA_SYNTHESIS, {
        "PROVEN": (180, 30, 0.35), "FIRST_OF_KIND": (280, 25, 0.25),
    }, _JURIS),
    *_make_entries(ComponentType.STORAGE_TANKS, {
        "PROVEN": (120, 40, 0.70), "FIRST_OF_KIND": (160, 35, 0.60),
    }, _JURIS),
    *_make_entries(ComponentType.PORT_INFRASTRUCTURE, {
        "PROVEN": (100, 40, 0.75), "FIRST_OF_KIND": (140, 35, 0.65),
    }, _JURIS),
    *_make_entries(ComponentType.GRID_CONNECTION, {
        "PROVEN": (80, 30, 0.50),
    }, _JURIS),
    *_make_entries(ComponentType.SITE_ENTITLEMENTS, {
        "PROVEN": (50, 40, 0.60),
    }, _JURIS),
    *_make_entries(ComponentType.BALANCE_OF_PLANT, {
        "PROVEN": (200, 20, 0.15), "FIRST_OF_KIND": (300, 18, 0.10),
    }, _JURIS),
]


# ── Singleton ──

_db: Optional[RiskPricingDB] = None

def get_risk_pricing_db() -> RiskPricingDB:
    global _db
    if _db is None:
        _db = RiskPricingDB()
    return _db
