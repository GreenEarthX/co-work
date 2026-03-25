"""
GEX Deal-Killer Flag System — R1 (Architectural Reform v6.0)

Pre-seeds 8 fatal/critical deal-killers that override all composite scores.
Any FATAL killer ACTIVE on a project blocks: IC Pack export, committee-ready
signal, and capital unlock classification.

Plain-language descriptions are mandatory — every killer must be readable
by a non-specialist in one sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class KillerSeverity(str, Enum):
    FATAL    = "FATAL"     # blocks FID, IC pack, committee — non-waivable
    CRITICAL = "CRITICAL"  # blocks IC pack unless formally waived


class KillerStatus(str, Enum):
    ACTIVE   = "ACTIVE"    # outstanding — blocks progress
    RESOLVED = "RESOLVED"  # evidence submitted and confirmed
    WAIVED   = "WAIVED"    # formally waived with documented rationale


class CommitteeReadiness(str, Enum):
    READY       = "READY"
    NOT_READY   = "NOT_READY"
    CONDITIONAL = "CONDITIONAL"  # CRITICAL killers only, all FATAL resolved


@dataclass
class DealKiller:
    id:               str
    gate:             str                # which gate this killer belongs to
    condition:        str                # machine-readable condition name
    plain_language:   str                # one sentence, no jargon
    severity:         KillerSeverity
    current_status:   KillerStatus = KillerStatus.ACTIVE
    resolution_action: str = ""          # what to do to resolve
    resolution_page:  str = ""          # frontend route to navigate to
    affects_states:   list[str] = field(default_factory=list)
    waiver_requires:  str = ""          # who/what is needed to waive


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-SEEDED DEAL-KILLERS (8 canonical killers)
# ═══════════════════════════════════════════════════════════════════════════════

DEAL_KILLERS: list[DealKiller] = [
    DealKiller(
        id="DK_G4_NO_OFFTAKE",
        gate="G4",
        condition="offtake_binding_pct < 50",
        plain_language=(
            "No binding offtake contract covering at least 50% of production — "
            "without this, no lender will commit funds."
        ),
        severity=KillerSeverity.FATAL,
        resolution_action="Execute a binding offtake agreement with an investment-grade counterparty covering ≥50% of nameplate capacity.",
        resolution_page="/finance/offtake-quality",
        affects_states=["STRUCTURALLY_BANKABLE", "CREDIT_APPROVED", "FINANCEABLE"],
        waiver_requires="Senior lender written confirmation of alternative credit support accepted.",
    ),
    DealKiller(
        id="DK_G5_NO_EPC",
        gate="G5",
        condition="epc_contract_executed == False",
        plain_language=(
            "No EPC or EPCM contract has been executed — "
            "construction cannot proceed without a signed engineering, procurement, and construction agreement."
        ),
        severity=KillerSeverity.FATAL,
        resolution_action="Execute an EPC, EPCM, or hybrid EPC contract with an approved contractor. Lump-sum or risk-transfer equivalent required.",
        resolution_page="/finance/stage-gates",
        affects_states=["BUILDABLE", "STRUCTURALLY_BANKABLE"],
        waiver_requires="IE confirmation that EPCM + performance bond achieves equivalent risk transfer.",
    ),
    DealKiller(
        id="DK_G6_NO_IE",
        gate="G6",
        condition="ie_appointed == False",
        plain_language=(
            "No independent engineer has been appointed — "
            "lenders require an IE to certify CAPEX estimates and design adequacy before financial close."
        ),
        severity=KillerSeverity.FATAL,
        resolution_action="Appoint a named, lender-accepted independent engineer. Confirm firm name and scope (minimum FEED-stage review).",
        resolution_page="/finance/stage-gates",
        affects_states=["STRUCTURALLY_BANKABLE", "CREDIT_APPROVED"],
        waiver_requires="N/A — non-waivable. Lenders require IE in all project finance transactions.",
    ),
    DealKiller(
        id="DK_G8_NO_AUDIT_MODEL",
        gate="G8",
        condition="financial_model_status != 'AUDIT_GRADE'",
        plain_language=(
            "The financial model has not been verified to audit grade — "
            "credit committees require an independently reviewed, audited model before approving debt."
        ),
        severity=KillerSeverity.FATAL,
        resolution_action="Commission a financial model audit from a named firm (e.g. KPMG, Deloitte, PwC). Model must reach AUDITED verification state.",
        resolution_page="/finance/bankability",
        affects_states=["CREDIT_APPROVED", "FINANCEABLE"],
        waiver_requires="N/A — non-waivable for senior debt transactions.",
    ),
    DealKiller(
        id="DK_G7_NO_INSURANCE",
        gate="G7",
        condition="insurance_fully_placed == False",
        plain_language=(
            "The insurance programme has not been fully placed — "
            "construction and operational insurance must be bound before drawdown."
        ),
        severity=KillerSeverity.CRITICAL,
        resolution_action="Bind all required insurance lines: construction all-risk, third-party liability, political risk, and delay in start-up (DSU).",
        resolution_page="/finance/insurance",
        affects_states=["FINANCEABLE"],
        waiver_requires="Lender written waiver with timeline commitment for placement before first drawdown.",
    ),
    DealKiller(
        id="DK_G2_CERT_FAIL",
        gate="G2",
        condition="rfnbo_pathway_viable == False",
        plain_language=(
            "The RFNBO certification pathway has not been confirmed as viable — "
            "without certification, the fuel cannot claim the GHG reduction required by buyers and regulators."
        ),
        severity=KillerSeverity.FATAL,
        resolution_action="Complete a pre-certification assessment confirming hourly renewable matching, additionality, and GHG calculation pathway under RED III.",
        resolution_page="/finance/cert-readiness",
        affects_states=["COMMERCIALLY_PLAUSIBLE", "BUILDABLE"],
        waiver_requires="Offtaker written confirmation that uncertified product is commercially acceptable (rare).",
    ),
    DealKiller(
        id="DK_DSCR_BELOW_FLOOR",
        gate="G8",
        condition="dscr_p90 < 1.10",
        plain_language=(
            "The debt service coverage ratio at P90 stress falls below 1.10x — "
            "this is below the minimum floor accepted by most project finance lenders."
        ),
        severity=KillerSeverity.FATAL,
        resolution_action="Restructure debt tenor, reduce gearing, increase equity contribution, or improve offtake price to restore DSCR P90 ≥ 1.25x.",
        resolution_page="/finance/dscr-sensitivity",
        affects_states=["CREDIT_APPROVED", "FINANCEABLE"],
        waiver_requires="Lender credit committee approval with specific covenant override — requires additional security.",
    ),
    DealKiller(
        id="DK_G1_NO_GRID",
        gate="G1",
        condition="grid_connection_offer_firm == False",
        plain_language=(
            "No firm grid connection offer has been received from the network operator — "
            "without this, renewable electricity supply to the electrolyzer cannot be confirmed."
        ),
        severity=KillerSeverity.CRITICAL,
        resolution_action="Obtain a firm grid connection offer (or equivalent direct line agreement) from the relevant network operator.",
        resolution_page="/finance/stage-gates",
        affects_states=["TECHNICALLY_PLAUSIBLE", "COMMERCIALLY_PLAUSIBLE"],
        waiver_requires="PPA with direct-wire arrangement confirmed by IE as technically equivalent.",
    ),
]

# Index for O(1) lookup
DEAL_KILLERS_BY_ID: dict[str, DealKiller] = {dk.id: dk for dk in DEAL_KILLERS}


# ═══════════════════════════════════════════════════════════════════════════════
# DEAL-KILLER ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class DealKillerEngine:
    """
    Evaluates project data against pre-seeded deal-killers.
    Stateless — all state is in project_data dict.
    """

    def evaluate(self, project_data: dict) -> list[DealKiller]:
        """
        Check each deal-killer against current project state.
        Returns list of DealKiller objects with current_status set.

        project_data keys expected:
          offtake_binding_pct      float 0-100
          epc_contract_executed    bool
          ie_appointed             bool
          financial_model_status   str  (AUDIT_GRADE | IE_REVIEWED | SELF_ASSESSED)
          insurance_fully_placed   bool
          rfnbo_pathway_viable     bool
          dscr_p90                 float
          grid_connection_firm     bool
        """
        results: list[DealKiller] = []

        checks: list[tuple[str, bool]] = [
            ("DK_G4_NO_OFFTAKE",     project_data.get("offtake_binding_pct", 0) < 50),
            ("DK_G5_NO_EPC",         not project_data.get("epc_contract_executed", False)),
            ("DK_G6_NO_IE",          not project_data.get("ie_appointed", False)),
            ("DK_G8_NO_AUDIT_MODEL", project_data.get("financial_model_status", "") != "AUDIT_GRADE"),
            ("DK_G7_NO_INSURANCE",   not project_data.get("insurance_fully_placed", False)),
            ("DK_G2_CERT_FAIL",      not project_data.get("rfnbo_pathway_viable", False)),
            ("DK_DSCR_BELOW_FLOOR",  project_data.get("dscr_p90", 0) < 1.10),
            ("DK_G1_NO_GRID",        not project_data.get("grid_connection_firm", False)),
        ]

        for killer_id, is_active in checks:
            dk = DEAL_KILLERS_BY_ID[killer_id]
            import dataclasses
            updated = dataclasses.replace(
                dk,
                current_status=KillerStatus.ACTIVE if is_active else KillerStatus.RESOLVED,
            )
            results.append(updated)

        return results

    def has_fatal(self, project_data: dict) -> bool:
        """True if ANY FATAL killer is ACTIVE."""
        return any(
            dk.severity == KillerSeverity.FATAL and dk.current_status == KillerStatus.ACTIVE
            for dk in self.evaluate(project_data)
        )

    def get_active_killers(self, project_data: dict) -> list[DealKiller]:
        return [dk for dk in self.evaluate(project_data) if dk.current_status == KillerStatus.ACTIVE]

    def get_blockers(self, project_data: dict) -> list[str]:
        """Plain-language list of active deal-killers for banner display."""
        return [dk.plain_language for dk in self.get_active_killers(project_data)]

    def get_resolution_actions(self, project_data: dict) -> list[dict]:
        """What to do and where to go for each active killer."""
        return [
            {
                "id": dk.id,
                "severity": dk.severity.value,
                "plain_language": dk.plain_language,
                "action": dk.resolution_action,
                "page": dk.resolution_page,
            }
            for dk in self.get_active_killers(project_data)
        ]

    def committee_ready(self, project_data: dict) -> dict:
        """
        Returns committee readiness status with conditions.
        READY        — no active killers
        CONDITIONAL  — only CRITICAL killers active (no FATAL)
        NOT_READY    — any FATAL killer active
        """
        active = self.get_active_killers(project_data)
        fatal_active   = [dk for dk in active if dk.severity == KillerSeverity.FATAL]
        critical_active = [dk for dk in active if dk.severity == KillerSeverity.CRITICAL]

        if not active:
            return {
                "status": CommitteeReadiness.READY.value,
                "conditions": [],
                "blockers": [],
            }

        if fatal_active:
            return {
                "status": CommitteeReadiness.NOT_READY.value,
                "conditions": [],
                "blockers": [dk.plain_language for dk in fatal_active],
            }

        return {
            "status": CommitteeReadiness.CONDITIONAL.value,
            "conditions": [dk.plain_language for dk in critical_active],
            "blockers": [],
        }


# Module-level singleton
deal_killer_engine = DealKillerEngine()
