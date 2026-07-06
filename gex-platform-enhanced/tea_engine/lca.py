"""lca.py — GEX LCA engine (co-located with the TEA engine, port 8002).

Closes the last report-grade→decision-grade gap: GHG stops being a typed-in
scalar and becomes a COMPUTED, provenance-bearing, regime-correct claim.

Structured LCA object (blueprint: insightquantix/pathway-spec — functional unit,
allocation, life-cycle inventory, emission factors, impact result) computed by the
method the molecule's regulatory regime demands:

  · annex_vi  — RED III RFNBO delegated methodology (e-fuels). Electricity must be
                additional renewable (~0 gCO2e); captured CO2 credited per the
                delegated act; comparator 94 gCO2e/MJ; ≥70% saving.
  · annex_v   — RED III biofuels. Biogenic CO2 = 0 at combustion; waste feedstock
                (UCO/tallow) carries only collection/transport burden (waste
                allocation, zero cultivation); ILUC applies to crops; ≥65% saving.
  · greet     — US 45V / 45Z lifecycle (GREET). US grid + boundary; scaled credit.

The two claims produced (g_co2e_per_mj, ghg_saving) are exactly what the
certification gate checks (regimes.evaluate_certification_gate). So: regime →
LCA method → GHG claims → gate. First-pass emission factors (ascertained=False);
an ISO 14067 verifier / ecoinvent-GREET dataset replaces them before verified.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# RED III (Annex V/VI) transport fossil comparator, gCO2e/MJ.
FOSSIL_COMPARATOR_GCO2E_MJ = 94.0

# Lower heating value, MJ/kg (energy basis for the functional unit "1 MJ fuel").
LHV_MJ_PER_KG = {
    "E_METHANOL": 19.9, "E_METHANE": 50.0, "E_SAF": 44.0,
    "BIO_SAF_HEFA": 44.0, "GREEN_H2": 120.0, "E_AMMONIA": 18.6,
}

# ── Emission-factor library — PROVENANCED, but reference-grade, NOT verifier-signed.
# Each factor carries {ef, unit, biogenic, source, year}. These are best-available
# PUBLIC reference values (typical literature / regulatory defaults); they are NOT
# an ISO 14067 verifier dataset or a licensed ecoinvent/GREET pull. A pathway stays
# ascertained=False until a named verifier signs the EF set (set EF_VERIFIED_BY).
# Do NOT flip ascertained on the strength of these defaults.
EF_VERIFIED_BY: str | None = None      # set to the verifier id once an EF set is signed

EF_LIBRARY = {
    "hydrogen":    {"ef": 1.0,  "unit": "kgCO2e/kg", "biogenic": False,
                    "source": "green-H2 electrolysis upstream, additional-renewable power (reference)", "year": 2024},
    "co2":         {"ef": 0.0,  "unit": "kgCO2e/kg", "biogenic": False,
                    "source": "captured CO2 credited under RFNBO delegated act (reference)", "year": 2023},
    "waste_lipid": {"ef": 0.10, "unit": "kgCO2e/kg", "biogenic": True,
                    "source": "UCO collection/transport only; waste allocation, RED III Annex V (reference)", "year": 2023},
}
# Electricity EF is METHOD/REGION dependent — this is the load-bearing choice.
ELECTRICITY_EF = {
    "eu_renewable": {"ef": 0.0,   "unit": "gCO2e/kWh",
                     "source": "RFNBO additional renewables, hourly+geo matched ≈ 0 (RED III delegated reg)", "year": 2023},
    "us_grid":      {"ef": 380.0, "unit": "gCO2e/kWh",
                     "source": "US national grid average (GREET/eGRID reference) — pre 3-pillar matching", "year": 2024},
}
_METHOD_ELEC = {"annex_vi": "eu_renewable", "annex_v": "eu_renewable", "greet": "us_grid"}

# GHG-saving thresholds per regime GHG method.
_THRESHOLD = {"annex_vi": 0.70, "annex_v": 0.65, "greet": 0.50}

# US 45V clean-hydrogen PTC tiers — lifecycle kgCO2e/kg H2 → $/kg (IRA §45V, public law).
_45V_TIERS = [
    (0.45, 3.00, "Tier 1 (≤0.45 kgCO2e/kg): full $3.00/kg (PWA)"),
    (1.50, 1.00, "Tier 2 (0.45–1.5): $1.00/kg"),
    (2.50, 0.75, "Tier 3 (1.5–2.5): $0.75/kg"),
    (4.00, 0.60, "Tier 4 (2.5–4.0): $0.60/kg"),
]  # >4.0 kgCO2e/kg → $0


def resolve_ef(stream: str, method: str) -> dict:
    if stream == "electricity":
        return ELECTRICITY_EF[_METHOD_ELEC.get(method, "eu_renewable")]
    return EF_LIBRARY.get(stream, {"ef": 0.0, "unit": "kgCO2e/kg", "biogenic": False,
                                   "source": "unknown stream — EF defaulted to 0", "year": 0})


def credit_signal(fuel_id: str, g_co2e_per_mj: float, method: str) -> dict:
    """Map GHG to the applicable US credit tier (GREET method only). H2 → 45V
    tiers (kgCO2e/kg); fuels → 45Z eligibility (per-MJ). Reference/eligibility
    only — the dollar figure is a signal for the capital layer, not tax advice."""
    if method != "greet":
        return {"applies": False, "note": "EU regime — see us_credit in the regime block"}
    if fuel_id.upper() == "GREEN_H2":
        # convert gCO2e/MJ → kgCO2e/kg H2 via LHV 120 MJ/kg
        kg_per_kg = g_co2e_per_mj * 120.0 / 1000.0
        for ceiling, usd, label in _45V_TIERS:
            if kg_per_kg <= ceiling:
                return {"applies": True, "credit": "45V", "lifecycle_kgco2e_per_kg_h2": round(kg_per_kg, 3),
                        "usd_per_kg": usd, "tier": label}
        return {"applies": True, "credit": "45V", "lifecycle_kgco2e_per_kg_h2": round(kg_per_kg, 3),
                "usd_per_kg": 0.0, "tier": ">4.0 kgCO2e/kg → no 45V credit"}
    # fuels → 45Z: eligible if GHG ≤ 50 kgCO2e/mmBTU (~47.4 gCO2e/MJ); SAF up to $1.75/gal
    eligible = g_co2e_per_mj <= 47.4
    return {"applies": True, "credit": "45Z", "eligible": eligible,
            "note": "SAF up to $1.75/gal, road fuels $1.00/gal; scales with GHG reduction (IRA §45Z, 2025+)"}


class LCIItem(BaseModel):
    stream:            str
    qty_per_kg_product: float             # kg/kg (mass) or kWh/kg (electricity)
    emission_factor:   float              # kgCO2e/kg, or gCO2e/kWh for electricity
    unit:              str
    biogenic:          bool = False


class LCAInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_id:      str
    pathway_id:      str
    fuel_id:         str
    ghg_method:      Optional[str] = None  # annex_vi | annex_v | greet; None ⇒ auto from regime
    allocation:      str = "energy"       # energy | mass | economic (co-products)
    lhv_mj_per_kg:   Optional[float] = None
    inventory:       list[LCIItem] = Field(default_factory=list)  # empty ⇒ derive from process function


class LCAResult(BaseModel):
    fuel_id:            str
    ghg_method:         str
    functional_unit:    str = "1 MJ fuel (LHV)"
    allocation:         str
    allocation_factor:  float = 1.0          # share of plant emissions borne by the primary product
    co_products:        list = []            # slate used for allocation
    g_co2e_per_mj_unallocated: float = 0.0   # before co-product allocation (all burden on SAF)
    g_co2e_per_mj:      float                # after allocation — the reportable figure
    fossil_comparator:  float
    ghg_saving_frac:    float
    threshold:          float
    meets_threshold:    bool
    breakdown:          dict
    lci_hash:           str
    claims:             dict                 # g_co2e_per_mj + ghg_saving (evidence proposals)
    data_sources:       list = []            # emission-factor provenance (reference-grade)
    ef_verified_by:     Optional[str] = None # verifier id once the EF set is signed
    credit_signal:      dict = {}            # US 45V tier / 45Z eligibility (GREET only)
    note:               str = ""
    ascertained:        bool = False


def _lci_from_process_function(fuel_id: str, method: str) -> tuple[list[LCIItem], float, list]:
    """Build the life-cycle inventory (per kg product) from the molecule's process
    function feedstocks + provenanced emission factors (method-dependent for
    electricity). Returns (items, lhv, data_sources)."""
    import tea_engine.process_functions as pfx
    pf = pfx.get(fuel_id)
    if pf is None or not pf.equipment:
        raise ValueError(f"no defined process function for '{fuel_id}' to derive an LCI from")
    items: list[LCIItem] = []
    sources: list[dict] = []
    # Same per-t-primary scaling the TEA uses (mass-balanced): the LCI attributes
    # the full plant feed to the primary product, then allocation φ spreads it
    # across co-products. LCI and TEA therefore share one consistent basis.
    for stream, qty, _is_energy, _pf in pfx.feedstock_per_t_primary(pf):
        ef = resolve_ef(stream, method)
        items.append(LCIItem(stream=stream, qty_per_kg_product=round(qty, 5),
                             emission_factor=ef["ef"], unit=ef["unit"], biogenic=ef.get("biogenic", False)))
        sources.append({"stream": stream, "ef": ef["ef"], "unit": ef["unit"],
                        "source": ef.get("source", ""), "year": ef.get("year")})
    lhv = LHV_MJ_PER_KG.get(fuel_id.upper(), 44.0)
    return items, lhv, sources


def _aggregate(inv: list[LCIItem], lhv: float, method: str) -> tuple[float, dict]:
    """gCO2e per kg product → gCO2e/MJ, with per-method rules."""
    g_per_kg = 0.0
    breakdown: dict[str, float] = {}
    for it in inv:
        if it.unit == "gCO2e/kWh":
            g = it.qty_per_kg_product * it.emission_factor            # kWh/kg × gCO2e/kWh
        else:
            g = it.qty_per_kg_product * it.emission_factor * 1000.0   # kg/kg × kgCO2e/kg × 1000
        # Biogenic carbon is zero at combustion (Annex V); we already count only
        # production burden, so biogenic streams contribute their (waste-allocated)
        # upstream EF only — no combustion term is ever added here.
        breakdown[it.stream] = round(g / lhv, 3)
        g_per_kg += g
    return round(g_per_kg / lhv, 3), breakdown


def _allocation_factor(fuel_id: str, method_basis: str) -> tuple[float, list]:
    """Share of plant emissions borne by the PRIMARY product, from its co-product
    slate. Energy basis (RED III Annex V default): φ = E_primary / Σ E_all. Mass
    basis: 1 / (1 + Σ mass_i). Under energy allocation every energy co-product
    carries the same intensity — SAF stops absorbing the whole plant's burden."""
    import tea_engine.process_functions as pfx
    pf = pfx.get(fuel_id)
    cps = list(getattr(pf, "co_products", ()) or ()) if pf else []
    slate = [{"name": cp.name, "mass_per_kg_primary": cp.mass_per_kg_primary,
              "lhv_mj_per_kg": cp.lhv_mj_per_kg} for cp in cps]
    if not cps or method_basis == "none":
        return 1.0, slate
    lhv_primary = LHV_MJ_PER_KG.get(fuel_id.upper(), 44.0)
    if method_basis == "mass":
        factor = 1.0 / (1.0 + sum(cp.mass_per_kg_primary for cp in cps))
    else:  # energy (default)
        e_primary = lhv_primary
        e_total = e_primary + sum(cp.mass_per_kg_primary * cp.lhv_mj_per_kg for cp in cps)
        factor = e_primary / e_total
    return round(factor, 4), slate


def compute_lca(inp: LCAInput) -> LCAResult:
    method = (inp.ghg_method or "annex_vi").lower()
    inv = inp.inventory
    lhv = inp.lhv_mj_per_kg
    sources: list = []
    if not inv:
        inv, derived_lhv, sources = _lci_from_process_function(inp.fuel_id, method)
        lhv = lhv or derived_lhv
    lhv = lhv or LHV_MJ_PER_KG.get(inp.fuel_id.upper(), 44.0)

    gco2e_mj_unalloc, breakdown_unalloc = _aggregate(inv, lhv, method)

    # Co-product allocation: SAF is one cut alongside diesel/naphtha/etc.
    alloc_basis = (inp.allocation or "energy").lower()
    factor, slate = _allocation_factor(inp.fuel_id, alloc_basis)
    gco2e_mj = round(gco2e_mj_unalloc * factor, 3)
    breakdown = {k: round(v * factor, 3) for k, v in breakdown_unalloc.items()}
    saving = round((FOSSIL_COMPARATOR_GCO2E_MJ - gco2e_mj) / FOSSIL_COMPARATOR_GCO2E_MJ, 4)
    threshold = _THRESHOLD.get(method, 0.70)

    lci_blob = json.dumps([i.model_dump() for i in inv] + [method, lhv], sort_keys=True).encode()
    lci_hash = "sha256:" + hashlib.sha256(lci_blob).hexdigest()[:24]

    biogenic = any(i.biogenic for i in inv)
    note = {
        "annex_vi": "RED III RFNBO (Annex VI): electricity must be additional renewable; captured CO2 credited per delegated act.",
        "annex_v":  "RED III biofuels (Annex V): biogenic CO2 = 0 at combustion; waste feedstock = collection burden only (waste allocation); ILUC applies to crops.",
        "greet":    "US GREET (45V/45Z): US grid + boundary; verify against 45VH2-GREET / CORSIA.",
    }.get(method, "unknown method")

    return LCAResult(
        fuel_id=inp.fuel_id.upper(), ghg_method=method, allocation=alloc_basis,
        allocation_factor=factor, co_products=slate,
        g_co2e_per_mj_unallocated=gco2e_mj_unalloc,
        g_co2e_per_mj=gco2e_mj, fossil_comparator=FOSSIL_COMPARATOR_GCO2E_MJ,
        ghg_saving_frac=saving, threshold=threshold, meets_threshold=saving >= threshold,
        breakdown=breakdown, lci_hash=lci_hash,
        data_sources=sources, ef_verified_by=EF_VERIFIED_BY,
        credit_signal=credit_signal(inp.fuel_id, gco2e_mj, method),
        ascertained=bool(EF_VERIFIED_BY),   # only true once a verifier signs the EF set
        claims={
            # evidence proposals — exactly the claim_types the certification gate checks
            "g_co2e_per_mj": {"value": gco2e_mj, "unit": "gCO2e/MJ", "state": "submitted",
                              "method": method, "lci_hash": lci_hash},
            "ghg_saving":    {"value": saving, "unit": "fraction_vs_fossil", "state": "submitted",
                              "threshold": threshold, "meets": saving >= threshold},
        },
        note=("Biogenic pathway. " + note) if biogenic else note,
    )
