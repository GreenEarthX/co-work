"""regimes.py — regulatory-regime fork keyed on a molecule's pathway_class.

A fuel's pathway_class (set in process_functions.py) determines a *different*
regulatory reality: which certification claims the certification gate requires,
which GHG methodology applies, and which subsidy/credit is claimable. e-fuels
(RFNBO) and biofuels (ADVANCED_BIOFUEL) are NOT the same regime — this module is
the single place that fork is expressed, so gate evaluation, the GHG engine, and
the capital/subsidy layer all read one source of truth.

Scope note: this declares the fork as data + helpers. The consuming engines still
have to READ it — (1) the truth-stack certification gate (G2/G6) must require
`required_cert_claims` and waive `waived_cert_claims`; (2) the GHG engine must
apply `ghg_method`; (3) the capital layer must select `us_credit`/`eu_incentive`.
Several biofuel claim_types below (feedstock_sustainability, annex_ix_class,
land_criteria, ghg_saving) are NOT yet in the truth-stack canonical NODES
registry — adding them there (a governed spec change) is what lets rollup_nodes
fold a biofuel pathway. Flagged, not silently assumed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Regime:
    pathway_class:         str
    label:                 str
    certification_scheme:  str
    required_cert_claims:  tuple[str, ...]   # claim_types the certification gate requires
    waived_cert_claims:    tuple[str, ...]   # claim_types N/A for this regime (auto-waived)
    ghg_method:            str
    ghg_rule:              str
    eu_incentive:          str
    us_credit:             str
    ghg_threshold:         str


# RFNBO claim_types that exist in the truth-stack NODES registry today.
_RFNBO_CERT = ("additionality_passed", "temporal_correlation", "geo_correlation",
               "hourly_matched_mwh", "rfnbo_issued", "g_co2e_per_mj")
# Biofuel claim_types — NOT yet in the truth-stack registry (spec change needed).
_BIOFUEL_CERT = ("feedstock_sustainability", "chain_of_custody", "annex_ix_class",
                 "land_criteria", "ghg_saving", "g_co2e_per_mj")


_RFNBO = Regime(
    pathway_class="RFNBO",
    label="Renewable fuel of non-biological origin (e-fuel)",
    certification_scheme="RFNBO — RED III Art. 27 + Delegated Regs (EU) 2023/1184 & 2023/1185",
    required_cert_claims=_RFNBO_CERT,
    waived_cert_claims=("feedstock_sustainability", "annex_ix_class", "land_criteria"),
    ghg_method="RED III Annex VI (RFNBO delegated methodology)",
    ghg_rule="Electricity from additional renewables; hourly temporal + geographic correlation; "
             "captured-CO2 source-eligibility rules apply.",
    eu_incentive="RED III RFNBO sub-targets (transport & industry); ReFuelEU e-SAF sub-mandate.",
    us_credit="45V clean-H2 PTC (3 pillars, 45VH2-GREET) on the hydrogen; downstream fuel via 45Z.",
    ghg_threshold="≥70% GHG saving vs fossil comparator (RFNBO).",
)

_ADVANCED_BIOFUEL = Regime(
    pathway_class="ADVANCED_BIOFUEL",
    label="Advanced biofuel (RED III Annex IX Part A/B feedstocks)",
    certification_scheme="Voluntary scheme (e.g. ISCC EU) — Proof of Sustainability, RED III Art. 29–31",
    required_cert_claims=_BIOFUEL_CERT,
    # RFNBO electricity rules do not apply to a biogenic feedstock pathway.
    waived_cert_claims=("additionality_passed", "temporal_correlation", "geo_correlation",
                        "hourly_matched_mwh", "rfnbo_issued"),
    ghg_method="RED III Annex V (biofuels) — biogenic CO2 = 0 at combustion",
    ghg_rule="Actual or default Annex V values; ILUC reporting; no high-carbon-stock / "
             "high-biodiversity land-use change; Annex IX Part B cap + double-counting.",
    eu_incentive="ReFuelEU Aviation SAF mandate; RED III Annex IX Part B cap.",
    us_credit="40B (2023–24) / 45Z Clean Fuel Production Credit (2025+), GREET / CORSIA-based.",
    ghg_threshold="≥65% GHG saving (transport, new installations).",
)

_BIOFUEL_CROP = Regime(
    pathway_class="BIOFUEL_CROP",
    label="Crop-based biofuel (food/feed feedstock)",
    certification_scheme="Voluntary scheme — Proof of Sustainability, RED III Art. 29–31 (+ food/feed cap)",
    required_cert_claims=("feedstock_sustainability", "chain_of_custody", "land_criteria",
                          "ghg_saving", "g_co2e_per_mj"),
    waived_cert_claims=("additionality_passed", "temporal_correlation", "geo_correlation",
                        "hourly_matched_mwh", "rfnbo_issued", "annex_ix_class"),
    ghg_method="RED III Annex V (biofuels) — biogenic CO2 = 0; ILUC factor applies",
    ghg_rule="Subject to the RED III food/feed crop cap (max share) and ILUC; NOT Annex IX.",
    eu_incentive="Counts toward RED III general target only, capped; excluded from advanced sub-target.",
    us_credit="45Z (GREET) — crop feedstocks scored with ILUC.",
    ghg_threshold="≥65% GHG saving (transport, new installations).",
)

_RCF = Regime(
    pathway_class="RCF",
    label="Recycled carbon fuel (fossil waste streams)",
    certification_scheme="RED III recycled-carbon-fuel category (separate delegated methodology)",
    required_cert_claims=("feedstock_sustainability", "chain_of_custody", "g_co2e_per_mj"),
    waived_cert_claims=("additionality_passed", "temporal_correlation", "geo_correlation",
                        "rfnbo_issued", "annex_ix_class", "land_criteria"),
    ghg_method="RED III RCF delegated methodology (Art. 29a)",
    ghg_rule="Fossil-waste-derived; GHG credited only vs the counterfactual waste fate.",
    eu_incentive="May count toward RED III targets subject to the RCF delegated act.",
    us_credit="Case-by-case (45Z if lifecycle GHG qualifies).",
    ghg_threshold="≥70% GHG saving (RCF, per delegated act).",
)

_LOW_CARBON = Regime(
    pathway_class="LOW_CARBON",
    label="Low-carbon fuel (e.g. blue H2 / CCS-abated)",
    certification_scheme="EU Hydrogen & Gas Decarbonisation Package — low-carbon fuels methodology",
    required_cert_claims=("g_co2e_per_mj", "chain_of_custody"),
    waived_cert_claims=("additionality_passed", "temporal_correlation", "geo_correlation",
                        "rfnbo_issued", "annex_ix_class", "land_criteria"),
    ghg_method="Low-carbon fuels delegated methodology (fossil + CCS)",
    ghg_rule="Not renewable; qualifies as low-carbon only, distinct from RFNBO targets.",
    eu_incentive="Low-carbon fuel targets (separate from renewable sub-targets).",
    us_credit="45Q (carbon sequestration) / 45V lower tiers if lifecycle GHG qualifies.",
    ghg_threshold="≥70% GHG saving (low-carbon threshold).",
)

REGIMES: dict[str, Regime] = {
    r.pathway_class: r for r in
    (_RFNBO, _ADVANCED_BIOFUEL, _BIOFUEL_CROP, _RCF, _LOW_CARBON)
}


# pathway_class → LCA GHG-method key (EU compliance default; GREET is US, set explicitly).
_METHOD_KEY = {"RFNBO": "annex_vi", "ADVANCED_BIOFUEL": "annex_v", "BIOFUEL_CROP": "annex_v",
               "RCF": "annex_vi", "LOW_CARBON": "annex_vi"}


def ghg_method_key(pathway_class: str) -> str:
    return _METHOD_KEY.get((pathway_class or "RFNBO").upper(), "annex_vi")


def get_regime(pathway_class: str) -> Regime:
    r = REGIMES.get((pathway_class or "RFNBO").upper())
    if r is None:
        raise ValueError(f"unknown pathway_class '{pathway_class}'. "
                         f"Known: {sorted(REGIMES)}")
    return r


def regime_for_fuel(fuel_id: str) -> Regime:
    """Resolve a molecule's regime via its process function's pathway_class."""
    import tea_engine.process_functions as pfx
    pf = pfx.get(fuel_id)
    pc = pf.pathway_class if pf else "RFNBO"
    return get_regime(pc)


def as_dict(r: Regime) -> dict:
    return {
        "pathway_class": r.pathway_class,
        "label": r.label,
        "certification_scheme": r.certification_scheme,
        "required_cert_claims": list(r.required_cert_claims),
        "waived_cert_claims": list(r.waived_cert_claims),
        "ghg_method": r.ghg_method,
        "ghg_rule": r.ghg_rule,
        "ghg_threshold": r.ghg_threshold,
        "eu_incentive": r.eu_incentive,
        "us_credit": r.us_credit,
    }


def certification_gate(fuel_id: str) -> dict:
    """The certification gate (G2/G6) fork for a fuel: what it requires vs waives."""
    r = regime_for_fuel(fuel_id)
    return {
        "fuel_id": (fuel_id or "").upper(),
        "pathway_class": r.pathway_class,
        "certification_scheme": r.certification_scheme,
        "required_cert_claims": list(r.required_cert_claims),
        "waived_cert_claims": list(r.waived_cert_claims),
    }


# Terminal-valid ClaimStates (mirrors efuel_truth_stack.enums.TERMINAL_VALID).
TERMINAL_VALID = frozenset({"verified", "satisfied", "waived"})


def evaluate_certification_gate(fuel_id: str, claim_states: dict[str, str]) -> dict:
    """ENFORCE the fork: is the certification gate (G2/G6) open for this fuel?

    Given the project's {claim_type: state}, the gate opens iff every claim in the
    regime's required_cert_claims is terminal-valid. Waived claims are ignored
    (an RFNBO project is not blocked on Annex IX; a biofuel is not blocked on
    hourly matching). This is the runtime fork — same product, different gate.
    """
    r = regime_for_fuel(fuel_id)
    missing = [c for c in r.required_cert_claims
               if claim_states.get(c) not in TERMINAL_VALID]
    return {
        "fuel_id": (fuel_id or "").upper(),
        "pathway_class": r.pathway_class,
        "certification_scheme": r.certification_scheme,
        "ghg_method": r.ghg_method,
        "us_credit": r.us_credit,
        "required_cert_claims": list(r.required_cert_claims),
        "waived_cert_claims": list(r.waived_cert_claims),
        "missing_claims": missing,
        "gate_open": not missing,
    }
