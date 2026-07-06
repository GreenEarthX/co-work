"""
GEX De-Risking Instrument Registry
File: app/core/instrument_registry.py

The centre of gravity for the Deal Structuring Workbench.
Every other service reads from this registry.

Catalogs all available de-risking instruments worldwide,
filterable by jurisdiction, molecule, project stage, and type.
Checks stackability (conflict detection between instruments).
Pre-seeded with 35 instruments from OECD/World Bank 2024,
Oxford OIES ET52, Taghizadeh-Hesary 2022, Hydrogen Europe 2025.
"""

import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger("gex.instrument_registry")


class InstrumentType(str, Enum):
    CFD = "CFD"
    OFFTAKE_GUARANTEE = "OFFTAKE_GUARANTEE"
    FX_GUARANTEE = "FX_GUARANTEE"
    POLITICAL_RISK_INSURANCE = "PRI"
    CAR_INSURANCE = "CAR_INSURANCE"
    PARTIAL_CREDIT_GUARANTEE = "PARTIAL_CREDIT"
    TECH_GUARANTEE = "TECH_GUARANTEE"
    INTEREST_RATE_SWAP = "IRS"
    GCGC = "GCGC"
    EXPORT_CREDIT = "EXPORT_CREDIT"
    TAX_CREDIT = "TAX_CREDIT"
    CONCESSIONAL_LOAN = "CONCESSIONAL_LOAN"
    GRANT = "GRANT"
    GREEN_BOND = "GREEN_BOND"
    ESG_LINKED_BOND = "ESG_LINKED_BOND"           # Returns dependent on ESG KPIs
    SUSTAINABILITY_LINKED_LOAN = "SLL"             # Loan with ESG-linked margin ratchet
    GREEN_REVENUE_BOND = "GREEN_REVENUE_BOND"      # Revenue-backed, predetermined proceeds
    GREEN_PROJECT_BOND = "GREEN_PROJECT_BOND"      # Single-project, ring-fenced proceeds
    GREEN_SECURITIZED_BOND = "GREEN_SECURITIZED"   # Pool of sustainability projects
    PERFORMANCE_GUARANTEE = "PERFORMANCE_GUARANTEE"
    BLENDED_FINANCE = "BLENDED_FINANCE"


class ProviderType(str, Enum):
    MDB = "MDB"
    DFI = "DFI"
    ECA = "ECA"
    GOVERNMENT = "GOVERNMENT"
    COMMERCIAL = "COMMERCIAL"
    MULTILATERAL = "MULTILATERAL"
    NATIONAL = "NATIONAL"


class RiskCategory(str, Enum):
    CONSTRUCTION = "CONSTRUCTION"
    MARKET = "MARKET"
    TECHNOLOGY = "TECHNOLOGY"
    POLITICAL = "POLITICAL"
    REGULATORY = "REGULATORY"
    COUNTERPARTY = "COUNTERPARTY"
    FX = "FX"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    OFFTAKE = "OFFTAKE"
    INTEREST_RATE = "INTEREST_RATE"
    GRID = "GRID"
    CERTIFICATION = "CERTIFICATION"


class ProceedsType(str, Enum):
    """From ICMA Green Bond Principles — determines information architecture"""
    USE_OF_PROCEEDS = "USE_OF_PROCEEDS"       # Predetermined allocation to green projects
    GENERAL_PURPOSE = "GENERAL_PURPOSE"       # No predetermined use — ESG-linked via KPIs
    REVENUE_BACKED = "REVENUE_BACKED"         # Returns stem from project revenue
    SECURITIZED = "SECURITIZED"               # Backed by pool of green assets


class BondFramework(str, Enum):
    """Validated framework references instead of free text"""
    ICMA_GBP_2021 = "ICMA_GBP_2021"          # ICMA Green Bond Principles 2021
    EU_GBS = "EU_GBS"                          # EU Green Bond Standard
    CBI = "CBI"                                # Climate Bonds Initiative
    ICMA_SBP = "ICMA_SBP"                      # ICMA Social Bond Principles
    ICMA_SLB = "ICMA_SLB"                      # ICMA Sustainability-Linked Bond Principles
    ICMA_SBG = "ICMA_SBG"                      # ICMA Sustainability Bond Guidelines
    LMA_SLLP = "LMA_SLLP"                      # LMA Sustainability-Linked Loan Principles
    NONE = "NONE"


@dataclass
class ESGMetric:
    """KPI for ESG-linked instruments — returns depend on these"""
    kpi_name: str                              # e.g. "GHG Intensity Reduction"
    target_value: float                        # e.g. 50.0 (50% reduction)
    target_unit: str                           # e.g. "% reduction vs baseline"
    measurement_date: str                      # e.g. "2028-12-31"
    penalty_bps: int = 0                       # Rate step-up if KPI missed
    reward_bps: int = 0                        # Rate step-down if KPI exceeded
    verification_agent: str = ""               # e.g. "DNV", "S&P Global Ratings"


@dataclass
class Instrument:
    id: str
    name: str
    type: InstrumentType
    provider: str
    provider_type: ProviderType
    jurisdictions: list[str]
    eligible_molecules: list[str]
    eligible_stages: list[str]
    risks_addressed: list[RiskCategory]
    min_project_size_eur: int = 0
    max_coverage_pct: float = 1.0
    cost_bps: int = 0
    effective_rate_reduction_bps: int = 0
    typical_tenor_years: int = 0
    application_window: str = "Rolling"
    application_lead_time_weeks: int = 12
    application_url: str = ""
    requirements: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    regulatory_risk_score: int = 0  # 0-100, quantified political/regulatory risk impact
    cross_border_applicable: bool = False
    tax_stacking_risk: str = ""  # e.g., "45V/RFNBO conflict if both claimed"
    proceeds_type: ProceedsType = ProceedsType.GENERAL_PURPOSE
    bond_framework: BondFramework = BondFramework.NONE
    esg_metrics: list[ESGMetric] = field(default_factory=list)
    required_certifications: list[str] = field(default_factory=list)  # e.g. ["RFNBO", "RED_III"]
    required_audit_nodes: list[str] = field(default_factory=list)     # Typed verifiers: "DNV", "S&P", "IE"
    source: str = ""
    active: bool = True

    def addresses_risk(self, risk: RiskCategory) -> bool:
        return risk in self.risks_addressed

    def is_eligible(
        self,
        jurisdiction: str,
        molecule: str,
        stage: str,
        project_size_eur: int,
    ) -> bool:
        if not self.active:
            return False
        if jurisdiction not in self.jurisdictions and "GLOBAL" not in self.jurisdictions:
            return False
        if molecule not in self.eligible_molecules and "ALL" not in self.eligible_molecules:
            return False
        if stage not in self.eligible_stages and "ALL" not in self.eligible_stages:
            return False
        if project_size_eur < self.min_project_size_eur:
            return False
        return True


@dataclass
class StackabilityResult:
    stackable: bool
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    max_cumulative_coverage_pct: float = 0.0


class InstrumentRegistry:

    def __init__(self):
        self._instruments: dict[str, Instrument] = {}
        self._load_seed_data()

    def _load_seed_data(self):
        for inst in SEED_INSTRUMENTS:
            self._instruments[inst.id] = inst
        logger.info("Instrument registry loaded: %d instruments", len(self._instruments))

    def get(self, instrument_id: str) -> Optional[Instrument]:
        return self._instruments.get(instrument_id)

    def get_all(self, active_only: bool = True) -> list[Instrument]:
        if active_only:
            return [i for i in self._instruments.values() if i.active]
        return list(self._instruments.values())

    def search(
        self,
        jurisdiction: Optional[str] = None,
        molecule: Optional[str] = None,
        project_stage: Optional[str] = None,
        project_size_eur: int = 0,
        instrument_types: Optional[list[InstrumentType]] = None,
        risk_categories: Optional[list[RiskCategory]] = None,
    ) -> list[Instrument]:
        results = []
        for inst in self._instruments.values():
            if not inst.active:
                continue
            if jurisdiction and not inst.is_eligible(jurisdiction, molecule or "ALL", project_stage or "ALL", project_size_eur):
                continue
            if instrument_types and inst.type not in instrument_types:
                continue
            if risk_categories and not any(inst.addresses_risk(r) for r in risk_categories):
                continue
            results.append(inst)
        return sorted(results, key=lambda i: i.effective_rate_reduction_bps, reverse=True)

    def get_eligible_for_project(
        self,
        jurisdiction: str,
        molecule: str,
        stage: str,
        project_size_eur: int,
    ) -> list[Instrument]:
        return [
            inst for inst in self._instruments.values()
            if inst.active and inst.is_eligible(jurisdiction, molecule, stage, project_size_eur)
        ]

    def check_stackability(self, instrument_ids: list[str]) -> StackabilityResult:
        instruments = [self._instruments[iid] for iid in instrument_ids if iid in self._instruments]
        conflicts = []
        warnings = []
        total_coverage = 0.0

        for i, a in enumerate(instruments):
            for b in instruments[i + 1:]:
                if b.id in a.conflicts_with or a.id in b.conflicts_with:
                    conflicts.append((a.id, b.id, f"{a.name} conflicts with {b.name}"))
                if a.type == b.type and a.provider == b.provider:
                    warnings.append(f"Duplicate type from same provider: {a.name} and {b.name}")
            total_coverage += a.max_coverage_pct

        if total_coverage > 1.0:
            warnings.append(f"Total coverage {total_coverage:.0%} exceeds 100% — check for over-insurance")

        # Check tax stacking
        tax_instruments = [i for i in instruments if i.tax_stacking_risk]
        if len(tax_instruments) > 1:
            warnings.append(
                f"Tax stacking risk: {', '.join(i.name for i in tax_instruments)}. "
                f"Verify no double-claim (e.g., 45V vs RFNBO)."
            )

        return StackabilityResult(
            stackable=len(conflicts) == 0,
            conflicts=conflicts,
            warnings=warnings,
            max_cumulative_coverage_pct=min(total_coverage, 1.0),
        )

    def get_by_provider(self, provider: str) -> list[Instrument]:
        return [i for i in self._instruments.values() if i.active and provider.lower() in i.provider.lower()]

    def get_by_risk(self, risk: RiskCategory) -> list[Instrument]:
        return [i for i in self._instruments.values() if i.active and risk in i.risks_addressed]

    def add(self, instrument: Instrument) -> None:
        self._instruments[instrument.id] = instrument

    def deactivate(self, instrument_id: str) -> bool:
        inst = self._instruments.get(instrument_id)
        if inst:
            inst.active = False
            return True
        return False


# ════════════════════════════════════════════════════════════
# SEED DATA — 35 instruments from OECD/WB, OIES, research
# ════════════════════════════════════════════════════════════

_EU = ["EU", "FR", "DE", "NL", "ES", "IT", "BE", "AT", "PT", "IE", "GB"]
_GLOBAL = ["GLOBAL"]
_ALL_MOLECULES = [
    "E_METHANE",
    "E_METHANOL",
    "E_NH3",
    "HVO",
    "SAF",
    "E_GASOLINE",
    "E_LG",
    "E_NAPHTHA",
    "H2",
    "NH3",
    "E_NG",
]
_ALL_STAGES = ["SPECULATIVE", "TECHNICALLY_PLAUSIBLE", "COMMERCIALLY_PLAUSIBLE", "BUILDABLE",
               "STRUCTURALLY_BANKABLE", "CREDIT_APPROVED", "FINANCEABLE", "OPERATIONAL"]
_FID_STAGES = ["BUILDABLE", "STRUCTURALLY_BANKABLE", "CREDIT_APPROVED", "FINANCEABLE"]
_EARLY_STAGES = ["SPECULATIVE", "TECHNICALLY_PLAUSIBLE", "COMMERCIALLY_PLAUSIBLE"]
_POST_FID = ["FINANCEABLE", "OPERATIONAL"]

SEED_INSTRUMENTS = [
    # ── EU / European Instruments ──
    Instrument(
        id="EU_INNOVATION_FUND",
        name="EU Innovation Fund — Large Scale",
        type=InstrumentType.GRANT,
        provider="European Commission",
        provider_type=ProviderType.MULTILATERAL,
        jurisdictions=_EU,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_EARLY_STAGES + ["BUILDABLE"],
        risks_addressed=[RiskCategory.TECHNOLOGY, RiskCategory.MARKET],
        min_project_size_eur=7_500_000,
        max_coverage_pct=0.60,
        cost_bps=0,
        effective_rate_reduction_bps=0,
        application_window="Annual call — typically Q1",
        application_lead_time_weeks=24,
        requirements=["EU-based", "GHG reduction >50%", "Innovation component"],
        source="OECD/World Bank 2024",
    ),
    Instrument(
        id="EU_H2_BANK_AUCTION",
        name="EU Hydrogen Bank — Fixed Premium Auction",
        type=InstrumentType.CFD,
        provider="European Commission / Innovation Fund",
        provider_type=ProviderType.MULTILATERAL,
        jurisdictions=_EU,
        eligible_molecules=["H2"],
        eligible_stages=["COMMERCIALLY_PLAUSIBLE", "BUILDABLE", "STRUCTURALLY_BANKABLE"],
        risks_addressed=[RiskCategory.MARKET, RiskCategory.OFFTAKE],
        min_project_size_eur=10_000_000,
        max_coverage_pct=1.0,
        cost_bps=0,
        effective_rate_reduction_bps=80,
        typical_tenor_years=10,
        application_window="Auction rounds — 2024, 2025, 2026",
        application_lead_time_weeks=16,
        requirements=["RFNBO certified", "EU production", "Competitive bid"],
        source="OECD/World Bank 2024 — EU H2 Bank AaaS",
    ),
    Instrument(
        id="EIB_PROJECT_BOND",
        name="EIB Project Bond Credit Enhancement",
        type=InstrumentType.PARTIAL_CREDIT_GUARANTEE,
        provider="European Investment Bank",
        provider_type=ProviderType.MDB,
        jurisdictions=_EU + ["GB"],
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.CONSTRUCTION, RiskCategory.MARKET, RiskCategory.COUNTERPARTY],
        min_project_size_eur=50_000_000,
        max_coverage_pct=0.20,
        cost_bps=25,
        effective_rate_reduction_bps=60,
        typical_tenor_years=15,
        requirements=["Investment-grade sponsors or structure", "EIA approved"],
        source="OIES ET52 2026",
    ),
    Instrument(
        id="EIB_INVESTEU_GUARANTEE",
        name="EIB InvestEU Guarantee — Green Window",
        type=InstrumentType.PARTIAL_CREDIT_GUARANTEE,
        provider="European Investment Bank / InvestEU",
        provider_type=ProviderType.MDB,
        jurisdictions=_EU,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.CONSTRUCTION, RiskCategory.TECHNOLOGY],
        min_project_size_eur=25_000_000,
        max_coverage_pct=0.30,
        cost_bps=30,
        effective_rate_reduction_bps=75,
        typical_tenor_years=12,
        requirements=["EU taxonomy alignment", "Climate contribution >50%"],
        source="OECD/World Bank 2024",
    ),
    Instrument(
        id="KFW_H2_PROGRAMME",
        name="KfW Hydrogen Programme — Concessional Debt",
        type=InstrumentType.CONCESSIONAL_LOAN,
        provider="KfW Development Bank",
        provider_type=ProviderType.DFI,
        jurisdictions=["DE", "EU"],
        eligible_molecules=["H2", "NH3", "SAF"],
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.INTEREST_RATE, RiskCategory.MARKET],
        min_project_size_eur=20_000_000,
        max_coverage_pct=0.50,
        cost_bps=35,
        effective_rate_reduction_bps=90,
        typical_tenor_years=15,
        requirements=["German or EU project", "Green hydrogen certified"],
        source="OIES ET52 2026",
    ),
    Instrument(
        id="EULER_HERMES_ECA",
        name="Euler Hermes — Export Credit Guarantee",
        type=InstrumentType.EXPORT_CREDIT,
        provider="Euler Hermes (Allianz Trade)",
        provider_type=ProviderType.ECA,
        jurisdictions=["DE"] + _EU,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.POLITICAL, RiskCategory.COUNTERPARTY, RiskCategory.FX],
        min_project_size_eur=10_000_000,
        max_coverage_pct=0.95,
        cost_bps=45,
        effective_rate_reduction_bps=50,
        typical_tenor_years=12,
        cross_border_applicable=True,
        requirements=["German content >30%", "OECD Arrangement compliant"],
        source="OECD/World Bank 2024",
    ),
    Instrument(
        id="BPI_GREEN_GUARANTEE",
        name="Bpifrance — Green Credit Guarantee",
        type=InstrumentType.GCGC,
        provider="Bpifrance",
        provider_type=ProviderType.NATIONAL,
        jurisdictions=["FR"],
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.CONSTRUCTION, RiskCategory.TECHNOLOGY, RiskCategory.MARKET],
        min_project_size_eur=5_000_000,
        max_coverage_pct=0.80,
        cost_bps=50,
        effective_rate_reduction_bps=90,
        typical_tenor_years=15,
        requirements=["French project", "Green taxonomy alignment"],
        source="Taghizadeh-Hesary 2022 — GCGC mechanism",
    ),
    Instrument(
        id="ADEME_H2_GRANT",
        name="ADEME — Hydrogen Deployment Grant",
        type=InstrumentType.GRANT,
        provider="ADEME (France)",
        provider_type=ProviderType.NATIONAL,
        jurisdictions=["FR"],
        eligible_molecules=["H2", "SAF"],
        eligible_stages=_EARLY_STAGES + ["BUILDABLE"],
        risks_addressed=[RiskCategory.TECHNOLOGY, RiskCategory.MARKET],
        max_coverage_pct=0.40,
        cost_bps=0,
        effective_rate_reduction_bps=0,
        application_window="Periodic calls — France 2030",
        application_lead_time_weeks=16,
        requirements=["French territory", "Green hydrogen production"],
        source="OECD/World Bank 2024",
    ),
    Instrument(
        id="MIGA_PRI",
        name="MIGA — Political Risk Insurance",
        type=InstrumentType.POLITICAL_RISK_INSURANCE,
        provider="Multilateral Investment Guarantee Agency (World Bank)",
        provider_type=ProviderType.MDB,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.POLITICAL, RiskCategory.REGULATORY, RiskCategory.FX],
        min_project_size_eur=10_000_000,
        max_coverage_pct=0.90,
        cost_bps=45,
        effective_rate_reduction_bps=40,
        typical_tenor_years=20,
        regulatory_risk_score=85,
        cross_border_applicable=True,
        requirements=["Cross-border investment", "MIGA member country"],
        source="OECD/World Bank 2024",
    ),
    Instrument(
        id="EBRD_GREEN_FINANCE",
        name="EBRD — Green Finance Facility",
        type=InstrumentType.CONCESSIONAL_LOAN,
        provider="European Bank for Reconstruction and Development",
        provider_type=ProviderType.MDB,
        jurisdictions=["EU", "TR", "EG", "MA", "KZ", "UA", "GE"],
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.MARKET, RiskCategory.TECHNOLOGY, RiskCategory.POLITICAL],
        min_project_size_eur=5_000_000,
        max_coverage_pct=0.35,
        cost_bps=30,
        effective_rate_reduction_bps=70,
        typical_tenor_years=12,
        cross_border_applicable=True,
        requirements=["EBRD country of operations", "Green taxonomy"],
        source="OECD/World Bank 2024 case studies",
    ),
    # ── H2Global / Offtake Instruments ──
    Instrument(
        id="H2GLOBAL_AUCTION",
        name="H2Global — Offtake Guarantee via Double Auction",
        type=InstrumentType.OFFTAKE_GUARANTEE,
        provider="H2Global Foundation / BMWK",
        provider_type=ProviderType.GOVERNMENT,
        jurisdictions=_GLOBAL,
        eligible_molecules=["H2", "NH3", "SAF", "E_METHANOL"],
        eligible_stages=["COMMERCIALLY_PLAUSIBLE", "BUILDABLE", "STRUCTURALLY_BANKABLE"],
        risks_addressed=[RiskCategory.OFFTAKE, RiskCategory.MARKET],
        min_project_size_eur=20_000_000,
        max_coverage_pct=1.0,
        cost_bps=0,
        effective_rate_reduction_bps=100,
        typical_tenor_years=10,
        application_window="Auction windows — see h2global-foundation.com",
        application_lead_time_weeks=20,
        requirements=["Green H2 or derivative", "Export to EU"],
        source="OECD/World Bank 2024 — Egypt case study",
    ),
    # ── Technology Guarantees ──
    Instrument(
        id="OEM_PERFORMANCE_WRAP",
        name="OEM Electrolyser Performance Guarantee",
        type=InstrumentType.PERFORMANCE_GUARANTEE,
        provider="OEM (project-specific)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=["H2"],
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.TECHNOLOGY],
        max_coverage_pct=0.15,
        cost_bps=20,
        effective_rate_reduction_bps=30,
        requirements=["OEM parent guarantee", "Performance bond", "LD schedule"],
        source="Hydrogen Europe 2025 — Bankability paper",
    ),
    Instrument(
        id="INSURANCE_CAR_DSU",
        name="CAR + DSU Insurance Package",
        type=InstrumentType.CAR_INSURANCE,
        provider="Commercial insurers (Zurich, AXA XL, Swiss Re)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES,
        risks_addressed=[RiskCategory.CONSTRUCTION, RiskCategory.TECHNOLOGY],
        max_coverage_pct=1.0,
        cost_bps=35,
        effective_rate_reduction_bps=25,
        requirements=["EPC contract in place", "IE appointed", "HAZOP complete"],
        source="OIES ET52 2026",
    ),
    # ── Interest Rate / FX Instruments ──
    Instrument(
        id="IRS_COMMERCIAL",
        name="Interest Rate Swap — Fix Senior Debt Rate",
        type=InstrumentType.INTEREST_RATE_SWAP,
        provider="Commercial banks (project-specific)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.INTEREST_RATE],
        max_coverage_pct=1.0,
        cost_bps=15,
        effective_rate_reduction_bps=0,
        requirements=["Senior debt facility in place", "ISDA master agreement"],
        source="Taghizadeh-Hesary 2022 — interest rate dominant sensitivity",
    ),
    Instrument(
        id="FX_HEDGE_DFI",
        name="DFI Currency Hedging Facility",
        type=InstrumentType.FX_GUARANTEE,
        provider="TCX / IFC / AfDB",
        provider_type=ProviderType.MDB,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.FX, RiskCategory.POLITICAL],
        max_coverage_pct=1.0,
        cost_bps=60,
        effective_rate_reduction_bps=35,
        cross_border_applicable=True,
        requirements=["Cross-border revenue/cost mismatch", "DFI co-financing"],
        source="OECD/World Bank 2024",
    ),
    # ── US / Cross-Border Tax Credits ──
    Instrument(
        id="US_45V_PTC",
        name="US 45V — Clean Hydrogen Production Tax Credit",
        type=InstrumentType.TAX_CREDIT,
        provider="US Treasury / IRS",
        provider_type=ProviderType.GOVERNMENT,
        jurisdictions=["US"],
        eligible_molecules=["H2"],
        eligible_stages=_ALL_STAGES,
        risks_addressed=[RiskCategory.MARKET],
        max_coverage_pct=1.0,
        cost_bps=0,
        effective_rate_reduction_bps=120,
        typical_tenor_years=10,
        tax_stacking_risk="45V + RFNBO: risk of double-claim on energy attributes. If claiming 45V on RE used for H2, EU may deny RFNBO if same EACs are counted twice.",
        cross_border_applicable=True,
        requirements=["US production", "Lifecycle GHG <4 kgCO2e/kgH2", "Prevailing wage + apprenticeship"],
        source="OECD/World Bank 2024 — §7B US→EU export decision tree",
    ),
    Instrument(
        id="US_45Y_ITC",
        name="US 45Y — Clean Electricity ITC (for captive RE)",
        type=InstrumentType.TAX_CREDIT,
        provider="US Treasury / IRS",
        provider_type=ProviderType.GOVERNMENT,
        jurisdictions=["US"],
        eligible_molecules=["H2"],
        eligible_stages=_ALL_STAGES,
        risks_addressed=[RiskCategory.MARKET],
        max_coverage_pct=0.30,
        cost_bps=0,
        effective_rate_reduction_bps=80,
        tax_stacking_risk="45Y for captive RE: ensure no double-claim with RFNBO EACs if exporting to EU.",
        conflicts_with=["US_45V_PTC"],
        cross_border_applicable=True,
        requirements=["US-sited renewable electricity", "Used for hydrogen production"],
        source="GEX Bankability Playbook v1.0 — §7B",
    ),
    # ── Green Bonds ──
    Instrument(
        id="GREEN_BOND_ICMA",
        name="Green Bond — ICMA Green Bond Principles",
        type=InstrumentType.GREEN_BOND,
        provider="Capital markets (project-specific)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.INTEREST_RATE],
        max_coverage_pct=0.44,
        cost_bps=0,
        effective_rate_reduction_bps=25,
        requirements=["ICMA GBP framework", "Second-party opinion", "Annual impact reporting"],
        proceeds_type=ProceedsType.USE_OF_PROCEEDS,
        bond_framework=BondFramework.ICMA_GBP_2021,
        required_certifications=["RFNBO"],
        required_audit_nodes=["SPO_PROVIDER"],
        source="Taghizadeh-Hesary 2022 — optimal 56/44 bank/bond split",
    ),
    # ── ESG-Linked / Sustainability-Linked Instruments ── (from the chart)
    Instrument(
        id="ESG_LINKED_BOND_GENERIC",
        name="ESG-Linked Bond — Sustainability-Linked Principles",
        type=InstrumentType.ESG_LINKED_BOND,
        provider="Capital markets (project-specific)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.INTEREST_RATE, RiskCategory.ENVIRONMENTAL],
        max_coverage_pct=0.50,
        cost_bps=10,
        effective_rate_reduction_bps=15,
        requirements=["ICMA SLB Principles", "SPT framework", "Annual KPI reporting", "External verification"],
        proceeds_type=ProceedsType.GENERAL_PURPOSE,
        bond_framework=BondFramework.ICMA_SLB,
        esg_metrics=[
            ESGMetric(kpi_name="GHG Intensity Reduction", target_value=50.0, target_unit="% vs 2020 baseline",
                      measurement_date="2030-12-31", penalty_bps=25, reward_bps=0, verification_agent="DNV"),
        ],
        source="ICMA Sustainability-Linked Bond Principles 2023",
    ),
    Instrument(
        id="SLL_MARGIN_RATCHET",
        name="Sustainability-Linked Loan — Margin Ratchet",
        type=InstrumentType.SUSTAINABILITY_LINKED_LOAN,
        provider="Commercial banks (syndicated)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_FID_STAGES + _POST_FID,
        risks_addressed=[RiskCategory.INTEREST_RATE, RiskCategory.ENVIRONMENTAL],
        max_coverage_pct=0.60,
        cost_bps=5,
        effective_rate_reduction_bps=20,
        requirements=["LMA SLLP framework", "SPT with measurable KPIs", "Annual sustainability report"],
        proceeds_type=ProceedsType.GENERAL_PURPOSE,
        bond_framework=BondFramework.LMA_SLLP,
        esg_metrics=[
            ESGMetric(kpi_name="Renewable Energy Share", target_value=95.0, target_unit="%",
                      measurement_date="2029-06-30", penalty_bps=15, reward_bps=10, verification_agent="S&P Global"),
        ],
        source="LMA Sustainability-Linked Loan Principles 2023",
    ),
    # ── Green Bond sub-types (from ICMA GBP — 4 variants in the chart) ──
    Instrument(
        id="GREEN_REVENUE_BOND",
        name="Green Revenue Bond — Project Cash Flow Backed",
        type=InstrumentType.GREEN_REVENUE_BOND,
        provider="Capital markets (project-specific)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_POST_FID,
        risks_addressed=[RiskCategory.INTEREST_RATE, RiskCategory.OFFTAKE],
        min_project_size_eur=100_000_000,
        max_coverage_pct=0.40,
        cost_bps=5,
        effective_rate_reduction_bps=30,
        requirements=["ICMA GBP framework", "Revenue stream from green project", "Impact reporting", "Second-party opinion"],
        proceeds_type=ProceedsType.REVENUE_BACKED,
        bond_framework=BondFramework.ICMA_GBP_2021,
        required_certifications=["RFNBO"],
        required_audit_nodes=["SPO_PROVIDER", "IMPACT_AUDITOR"],
        source="ICMA Green Bond Principles 2021 — Type 2: Green Revenue Bond",
    ),
    Instrument(
        id="GREEN_PROJECT_BOND",
        name="Green Project Bond — Single Asset Ring-Fenced",
        type=InstrumentType.GREEN_PROJECT_BOND,
        provider="Capital markets (project-specific)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=["CREDIT_APPROVED", "FINANCEABLE"],
        risks_addressed=[RiskCategory.CONSTRUCTION, RiskCategory.INTEREST_RATE],
        min_project_size_eur=150_000_000,
        max_coverage_pct=0.35,
        cost_bps=10,
        effective_rate_reduction_bps=35,
        requirements=["ICMA GBP framework", "Ring-fenced SPV", "IE report", "Audit-grade financial model", "Second-party opinion"],
        proceeds_type=ProceedsType.USE_OF_PROCEEDS,
        bond_framework=BondFramework.ICMA_GBP_2021,
        required_certifications=["RFNBO", "RED_III"],
        required_audit_nodes=["IE", "SPO_PROVIDER", "MODEL_AUDITOR"],
        source="ICMA Green Bond Principles 2021 — Type 3: Green Project Bond",
    ),
    Instrument(
        id="GREEN_SECURITIZED_BOND",
        name="Green Securitized Bond — Asset Pool Backed",
        type=InstrumentType.GREEN_SECURITIZED_BOND,
        provider="Capital markets (portfolio)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_POST_FID,
        risks_addressed=[RiskCategory.INTEREST_RATE, RiskCategory.COUNTERPARTY],
        min_project_size_eur=250_000_000,
        max_coverage_pct=0.30,
        cost_bps=15,
        effective_rate_reduction_bps=20,
        requirements=["ICMA GBP framework", "Multiple green assets in pool", "Pool-level impact reporting", "Rating agency assessment"],
        proceeds_type=ProceedsType.SECURITIZED,
        bond_framework=BondFramework.ICMA_GBP_2021,
        required_audit_nodes=["RATING_AGENCY", "SPO_PROVIDER"],
        source="ICMA Green Bond Principles 2021 — Type 4: Green Securitized Bond",
    ),
    # ── Blended Finance ──
    Instrument(
        id="HY24_CLEAN_H2_FUND",
        name="Hy24 Clean Hydrogen Infrastructure Fund",
        type=InstrumentType.BLENDED_FINANCE,
        provider="Hy24 (Ardian + FiveT)",
        provider_type=ProviderType.COMMERCIAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=["BUILDABLE", "STRUCTURALLY_BANKABLE", "CREDIT_APPROVED"],
        risks_addressed=[RiskCategory.MARKET, RiskCategory.TECHNOLOGY],
        min_project_size_eur=50_000_000,
        max_coverage_pct=0.25,
        cost_bps=0,
        effective_rate_reduction_bps=40,
        requirements=["Equity co-investment", "Strategic alignment"],
        source="OECD/World Bank 2024 case studies — Hy24",
    ),
    Instrument(
        id="IRENA_ETAF",
        name="IRENA / ADFD — Energy Transition Accelerator Financing",
        type=InstrumentType.CONCESSIONAL_LOAN,
        provider="IRENA / Abu Dhabi Fund for Development",
        provider_type=ProviderType.MULTILATERAL,
        jurisdictions=_GLOBAL,
        eligible_molecules=_ALL_MOLECULES,
        eligible_stages=_EARLY_STAGES + ["BUILDABLE"],
        risks_addressed=[RiskCategory.TECHNOLOGY, RiskCategory.MARKET],
        min_project_size_eur=5_000_000,
        max_coverage_pct=0.50,
        cost_bps=10,
        effective_rate_reduction_bps=80,
        typical_tenor_years=15,
        requirements=["IRENA member country", "Renewable energy component"],
        source="OECD/World Bank 2024",
    ),
]

# ── Singleton ──

_registry: Optional[InstrumentRegistry] = None

def get_instrument_registry() -> InstrumentRegistry:
    global _registry
    if _registry is None:
        _registry = InstrumentRegistry()
    return _registry
