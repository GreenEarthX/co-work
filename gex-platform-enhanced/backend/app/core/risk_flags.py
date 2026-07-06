"""
Structured project risk flags — server-authoritative registry + ABAC policy.

Replaces flat risk_alerts strings with auditable resources:
  id · claim · severity · confidence · category · owner_function
  · classification · source_ids · status

Design split (deliberate):
  - owner_function  = WHO WORKS the risk (task assignment)
  - classification  = WHO MAY SEE the risk (ABAC visibility)
These are never the same field: a related-party offtake risk is owned by
FINANCE but exists to warn the lenders (associated companies), so visibility
must come from classification × stakeholding, not from ownership.

Classification ladder:
  PUBLIC       → anyone who can see the project
  STAKEHOLDER  → owner company + associated companies
  CONFIDENTIAL → owner company only
  RESTRICTED   → owner company EXECUTIVE / FINANCE_TREASURY only
Platform admins see everything. Responses never include hidden-flag counts —
"3 flags (1 hidden)" would leak that a hidden risk exists.

The frontend keeps a static copy in customerProjects.ts as dev fallback only;
this registry is the enforced source (frontend is NEVER trusted for data
protection).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from app.core.project_registry import PROJECT_ACCESS_PROFILES, company_slug

CLASSIFICATIONS = ("PUBLIC", "STAKEHOLDER", "CONFIDENTIAL", "RESTRICTED")


@dataclass(frozen=True)
class RiskFlag:
    id: str
    project_id: str
    claim: str
    severity: str           # low | medium | high | critical
    confidence: str         # low | medium | high
    category: str           # capacity_claim | certification | offtake | financing
                            # | site_permits | insurance | supply_chain | policy
    owner_function: str     # EXECUTIVE | FINANCE_TREASURY | COMMERCIAL
                            # | ENGINEERING | OPERATIONS | COMPLIANCE_LEGAL
    classification: str     # PUBLIC | STAKEHOLDER | CONFIDENTIAL | RESTRICTED
    source_ids: tuple[str, ...]
    status: str = "OPEN"    # OPEN | ACKNOWLEDGED | WAIVED | RESOLVED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_ids"] = list(self.source_ids)
        return d


RISK_FLAGS: dict[str, list[RiskFlag]] = {
    "proj_etf_pecos1": [
        RiskFlag(
            id="rf_etf_pecos1_capacity_overstatement",
            project_id="proj_etf_pecos1",
            claim="Capacity discrepancy: GEX showed 165k t/yr, public sources confirm 120k t/yr (27% overstatement corrected)",
            severity="high", confidence="high",
            category="capacity_claim", owner_function="COMMERCIAL",
            classification="STAKEHOLDER",
            source_ids=("SRC_ETFUELS_OUR_SOLUTION_2026", "SRC_ARGUS_RFOCEAN_2026_02_24", "SRC_CARBONSTORAGE_RATTLESNAKE"),
            status="ACKNOWLEDGED",
        ),
        RiskFlag(
            id="rf_etf_pecos1_45v_temporal",
            project_id="proj_etf_pecos1",
            claim="45V temporal matching rule: IRS guidance still pending — annual vs hourly conflict with RFNBO",
            severity="high", confidence="medium",
            category="certification", owner_function="COMPLIANCE_LEGAL",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_RATTLESNAKE_FEED_2025_10_27",),
        ),
        RiskFlag(
            id="rf_etf_pecos1_related_party_offtake",
            project_id="proj_etf_pecos1",
            claim="ETFuels SA offtake (70k t/yr) is related-party — lenders may discount or exclude from bankability",
            severity="critical", confidence="high",
            category="offtake", owner_function="FINANCE_TREASURY",
            classification="STAKEHOLDER",
            source_ids=("SRC_GEX_INTERNAL_OFFTAKE_REVIEW",),
        ),
    ],
    "etfuels_us_tx_rattlesnake_gap": [
        RiskFlag(
            id="rf_etf_rsg_capacity_conflict",
            project_id="etfuels_us_tx_rattlesnake_gap",
            claim="Capacity conflict: 125 kt (company current) vs 120 kt (trade press / third-party DB)",
            severity="medium", confidence="high",
            category="capacity_claim", owner_function="FINANCE_TREASURY",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_OUR_SOLUTION_2026", "SRC_ARGUS_RFOCEAN_2026_02_24", "SRC_CARBONSTORAGE_RATTLESNAKE"),
        ),
        RiskFlag(
            id="rf_etf_rsg_electrolyser_mw_conflict",
            project_id="etfuels_us_tx_rattlesnake_gap",
            claim="Electrolyser MW conflict: 220 MW (Argus 2024) vs 500 MW (CarbonStorage DB)",
            severity="high", confidence="medium",
            category="site_permits", owner_function="ENGINEERING",
            classification="PUBLIC",
            source_ids=("SRC_ARGUS_2024_PIPELINE", "SRC_CARBONSTORAGE_RATTLESNAKE"),
        ),
        RiskFlag(
            id="rf_etf_rsg_45v_qualification",
            project_id="etfuels_us_tx_rattlesnake_gap",
            claim="45V qualification not automatic — IRS guidance pending",
            severity="high", confidence="medium",
            category="certification", owner_function="COMPLIANCE_LEGAL",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_RATTLESNAKE_FEED_2025_10_27", "SRC_ARGUS_RFOCEAN_2026_02_24"),
        ),
        RiskFlag(
            id="rf_etf_rsg_offtake_volume_private",
            project_id="etfuels_us_tx_rattlesnake_gap",
            claim="Offtake volume with RFOcean not publicly disclosed",
            severity="medium", confidence="high",
            category="offtake", owner_function="COMMERCIAL",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_RFOCEAN_2026_02_24", "SRC_ARGUS_RFOCEAN_2026_02_24"),
        ),
    ],
    "etfuels_fi_ranua_naataaapa": [
        RiskFlag(
            id="rf_etf_ranua_capacity_conflict",
            project_id="etfuels_fi_ranua_naataaapa",
            claim="Capacity conflict: 110 kt (tax credit release) vs 100 kt (legacy page)",
            severity="medium", confidence="high",
            category="capacity_claim", owner_function="FINANCE_TREASURY",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23", "SRC_ETFUELS_OLD_PROJECTS"),
        ),
        RiskFlag(
            id="rf_etf_ranua_tax_credit_not_cash",
            project_id="etfuels_fi_ranua_naataaapa",
            claim="Tax credit is NOT a cash grant — depends on tax eligibility and utilisation",
            severity="high", confidence="high",
            category="financing", owner_function="FINANCE_TREASURY",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23",),
        ),
        RiskFlag(
            id="rf_etf_ranua_offtake_private",
            project_id="etfuels_fi_ranua_naataaapa",
            claim="Offtake not publicly disclosed",
            severity="medium", confidence="high",
            category="offtake", owner_function="COMMERCIAL",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23",),
        ),
        RiskFlag(
            id="rf_etf_ranua_co2_counterparty",
            project_id="etfuels_fi_ranua_naataaapa",
            claim="CO₂ counterparty not public — certification risk",
            severity="medium", confidence="medium",
            category="certification", owner_function="COMPLIANCE_LEGAL",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23", "SRC_ETFUELS_OLD_PROJECTS"),
        ),
    ],
    "etfuels_uk_skyfuel_teesside": [
        RiskFlag(
            id="rf_etf_skyfuel_aff_dev_support",
            project_id="etfuels_uk_skyfuel_teesside",
            claim="AFF grant is development support only — not full project finance",
            severity="high", confidence="high",
            category="financing", owner_function="FINANCE_TREASURY",
            classification="PUBLIC",
            source_ids=("SRC_GOVUK_AFF_WINNERS_2025_07_22", "SRC_RICARDO_AFF"),
        ),
        RiskFlag(
            id="rf_etf_skyfuel_rcm_developing",
            project_id="etfuels_uk_skyfuel_teesside",
            claim="UK Revenue Certainty Mechanism details still developing (legislation May 2026)",
            severity="high", confidence="medium",
            category="policy", owner_function="COMPLIANCE_LEGAL",
            classification="PUBLIC",
            source_ids=("SRC_UK_SAF_TASK_FINISH_2026_04_27",),
        ),
        RiskFlag(
            id="rf_etf_skyfuel_feedstock_dependency",
            project_id="etfuels_uk_skyfuel_teesside",
            claim="Feedstock dependency on external e-methanol pipeline (TX/FI)",
            severity="medium", confidence="high",
            category="supply_chain", owner_function="OPERATIONS",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_OUR_SOLUTION_2026", "SRC_ETFUELS_OLD_PROJECTS"),
        ),
        RiskFlag(
            id="rf_etf_skyfuel_saf_cert_chain",
            project_id="etfuels_uk_skyfuel_teesside",
            claim="SAF testing/certification/distribution chain required",
            severity="medium", confidence="high",
            category="certification", owner_function="OPERATIONS",
            classification="PUBLIC",
            source_ids=("SRC_ETFUELS_SKYFUEL_GRANT_2025_07_23",),
        ),
    ],
}


def visible_risk_flags(project_id: str, payload: dict[str, Any]) -> list[RiskFlag] | None:
    """
    ABAC filter: returns the flags this caller may see, or None when the
    caller has no access to the project at all (404, not an empty list —
    an empty list would leak that the project exists).
    """
    profile = PROJECT_ACCESS_PROFILES.get(project_id)
    if profile is None:
        return None

    is_admin = bool(payload.get("is_platform_admin"))
    company_id = company_slug(payload.get("company_name", ""))
    is_owner = company_id == profile.owner_company_id
    is_stakeholder = company_id in profile.stakeholder_company_ids

    if not (is_admin or is_stakeholder):
        return None

    business_function = payload.get("business_function", "")

    def can_see(flag: RiskFlag) -> bool:
        if is_admin:
            return True
        if flag.classification == "PUBLIC":
            return True
        if flag.classification == "STAKEHOLDER":
            return is_stakeholder
        if flag.classification == "CONFIDENTIAL":
            return is_owner
        if flag.classification == "RESTRICTED":
            return is_owner and business_function in ("EXECUTIVE", "FINANCE_TREASURY")
        return False

    return [f for f in RISK_FLAGS.get(project_id, []) if can_see(f)]
