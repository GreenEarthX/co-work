"""
GEX Task Router — R6 (Architectural Reform v6.0)

Implements guided flows for 4 actor types. Each flow is a sequence
of 3-5 steps that drives the actor to a single decision output.

The landing page of each workspace renders the TaskRouter instead of
a generic dashboard. The full sidebar remains accessible but is secondary.

Actor types and their flows:
  COMMERCIAL_BANKER (RM)    — 5 steps → IC Pack generation
  OFFTAKER                  — 4 steps → RFQ submission
  CREDIT_COMMITTEE_CHAIR    — 3 steps → Committee recommendation
  PRODUCER                  — 4 steps → Structuring recommendation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActorType(str, Enum):
    COMMERCIAL_BANKER       = "COMMERCIAL_BANKER"
    OFFTAKER                = "OFFTAKER"
    CREDIT_COMMITTEE_CHAIR  = "CREDIT_COMMITTEE_CHAIR"
    PRODUCER                = "PRODUCER"


class StepStatus(str, Enum):
    DONE        = "DONE"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED     = "BLOCKED"
    NOT_STARTED = "NOT_STARTED"


@dataclass
class FlowStep:
    number:      int
    title:       str
    description: str    # one sentence: what this step answers
    page:        str    # frontend route
    status:      StepStatus = StepStatus.NOT_STARTED
    status_detail: str = ""   # e.g. "2 of 5 deal-killers resolved"
    blocked_by:  list[str] = field(default_factory=list)


@dataclass
class ActorFlow:
    actor_type:   ActorType
    project_id:   str
    objective:    str      # one sentence: what this actor is trying to decide
    overall_status: str    # READY | NOT_READY | CONDITIONAL
    steps:        list[FlowStep]
    fatal_killers_active: int = 0
    next_action:  str = ""
    next_action_page: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# FLOW DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

def build_banker_rm_flow(project_id: str, project_data: dict) -> ActorFlow:
    """5-step flow: Review → Gates → Evidence → Commitments → IC Pack."""
    deal_killers = project_data.get("active_fatal_killers", 0)
    g8_audit     = project_data.get("g8_is_audit_grade", False)
    snapshot_viewed = project_data.get("snapshot_viewed_within_7_days", False)
    evidence_confirmed_pct = project_data.get("evidence_confirmed_pct", 0)
    capital_committed = project_data.get("capital_stack_committed", False)

    ic_pack_blocked = deal_killers > 0 or not g8_audit
    ic_pack_blocked_by: list[str] = []
    if deal_killers > 0:
        ic_pack_blocked_by.append(f"{deal_killers} FATAL deal-killer(s) active")
    if not g8_audit:
        ic_pack_blocked_by.append("G8 financial model not at AUDIT_GRADE")

    steps = [
        FlowStep(
            number=1,
            title="Review Banker's Snapshot",
            description="Get a one-page summary of where this project stands and what is blocking it.",
            page="/finance/bankers-snapshot",
            status=StepStatus.DONE if snapshot_viewed else StepStatus.IN_PROGRESS,
            status_detail="Viewed" if snapshot_viewed else "Not yet viewed",
        ),
        FlowStep(
            number=2,
            title="Check Gates and Deal-Killers",
            description="Identify any FATAL issues that block committee submission.",
            page="/finance/bankability",
            status=(
                StepStatus.DONE if deal_killers == 0
                else StepStatus.IN_PROGRESS
            ),
            status_detail=(
                "No deal-killers" if deal_killers == 0
                else f"{deal_killers} FATAL deal-killer(s) active"
            ),
        ),
        FlowStep(
            number=3,
            title="Review Evidence Verification",
            description="Confirm what proportion of evidence is CONFIRMED or above.",
            page="/finance/stage-gates",
            status=(
                StepStatus.DONE if evidence_confirmed_pct >= 70
                else StepStatus.IN_PROGRESS
            ),
            status_detail=f"{evidence_confirmed_pct:.0f}% at CONFIRMED+",
        ),
        FlowStep(
            number=4,
            title="Confirm Commitment Firmness",
            description="Verify that capital stack entries are COMMITTED, not just MODELLED.",
            page="/finance/capital-stack",
            status=StepStatus.DONE if capital_committed else StepStatus.NOT_STARTED,
            status_detail="Committed" if capital_committed else "Items remain MODELLED",
        ),
        FlowStep(
            number=5,
            title="Generate IC Pack",
            description="Export the investment committee pack when all gates are clear.",
            page="/finance/ic-pack",
            status=StepStatus.BLOCKED if ic_pack_blocked else StepStatus.NOT_STARTED,
            blocked_by=ic_pack_blocked_by,
        ),
    ]

    overall = "NOT_READY" if deal_killers > 0 else ("READY" if not ic_pack_blocked else "CONDITIONAL")

    return ActorFlow(
        actor_type=ActorType.COMMERCIAL_BANKER,
        project_id=project_id,
        objective=f"Assess this project for credit committee submission",
        overall_status=overall,
        steps=steps,
        fatal_killers_active=deal_killers,
        next_action="Resolve FATAL deal-killers" if deal_killers > 0 else "Generate IC Pack",
        next_action_page="/finance/bankability" if deal_killers > 0 else "/finance/ic-pack",
    )


def build_offtaker_flow(project_id: str, project_data: dict) -> ActorFlow:
    """4-step flow: Mandate → Aggregate supply → Justify price → RFQ."""
    requirement_set  = project_data.get("requirement_defined", False)
    offers_available = project_data.get("qualified_offers_count", 0)
    pricing_ready    = project_data.get("pricing_reference_ready", False)

    steps = [
        FlowStep(
            number=1,
            title="Define Demand Mandate",
            description="Set molecule, monthly volume, delivery window, certifications, and target start date.",
            page="/onboarding",
            status=StepStatus.DONE if requirement_set else StepStatus.IN_PROGRESS,
            status_detail="Defined" if requirement_set else "Not yet defined",
        ),
        FlowStep(
            number=2,
            title="Aggregate Qualified Supply",
            description="Pool producer offers into a contractable supply stack using GreenMesh / FlowFusion logic.",
            page="/marketplace",
            status=StepStatus.IN_PROGRESS if requirement_set else StepStatus.NOT_STARTED,
            status_detail=(
                f"{offers_available} qualified producer offer(s) available"
                if offers_available else
                "No qualified producer offers yet"
            ),
        ),
        FlowStep(
            number=3,
            title="Establish Reference Price",
            description="Publish clean token spot reference plus Gabillon forward curve to justify internal and external pricing.",
            page="/pricing-curves",
            status=(
                StepStatus.BLOCKED if offers_available == 0 else
                StepStatus.DONE if pricing_ready else
                StepStatus.IN_PROGRESS
            ),
            status_detail=(
                "Spot reference + forward curve published"
                if pricing_ready else
                "Spot reference / forward curve still missing"
            ),
            blocked_by=[] if offers_available > 0 else ["No qualified supply pool yet — complete step 2 first"],
        ),
        FlowStep(
            number=4,
            title="Launch RFQ / Term Sheet",
            description="Approach counterparties with a priced, evidence-backed contract package for Q1 2027 delivery.",
            page="/rfqs",
            status=StepStatus.BLOCKED if not pricing_ready else StepStatus.NOT_STARTED,
            blocked_by=[] if pricing_ready else ["Reference price not yet defensible — complete step 3 first"],
        ),
    ]

    return ActorFlow(
        actor_type=ActorType.OFFTAKER,
        project_id=project_id,
        objective="Close a defensible offtake contract with trusted price reference and Q1 2027 delivery visibility",
        overall_status="IN_PROGRESS",
        steps=steps,
        next_action=(
            "Define demand mandate" if not requirement_set else
            "Aggregate qualified supply" if offers_available == 0 else
            "Establish reference price" if not pricing_ready else
            "Launch RFQ / term sheet"
        ),
        next_action_page=(
            "/onboarding" if not requirement_set else
            "/marketplace" if offers_available == 0 else
            "/pricing-curves" if not pricing_ready else
            "/rfqs"
        ),
    )


def build_credit_committee_flow(project_id: str, project_data: dict) -> ActorFlow:
    """3-step flow: Evidence Hierarchy → Deal-Killers → Recommendation."""
    deal_killers     = project_data.get("active_fatal_killers", 0)
    evidence_audited = project_data.get("evidence_audited_count", 0)
    evidence_total   = max(project_data.get("evidence_total_count", 1), 1)
    audited_pct      = round((evidence_audited / evidence_total) * 100)

    steps = [
        FlowStep(
            number=1,
            title="Evidence Hierarchy",
            description="Review per-gate breakdown of AUDITED / CONFIRMED / SUBMITTED / UNVERIFIED evidence.",
            page="/finance/evidence-hierarchy",
            status=StepStatus.IN_PROGRESS,
            status_detail=f"{audited_pct}% of evidence at AUDITED",
        ),
        FlowStep(
            number=2,
            title="Deal-Killer Status",
            description="Confirm whether any FATAL deal-killers are outstanding or formally waived.",
            page="/finance/bankability",
            status=StepStatus.DONE if deal_killers == 0 else StepStatus.IN_PROGRESS,
            status_detail=(
                "No FATAL killers" if deal_killers == 0
                else f"{deal_killers} FATAL killer(s) ACTIVE"
            ),
        ),
        FlowStep(
            number=3,
            title="Committee Recommendation",
            description="Based on evidence hierarchy and deal-killer status, form a committee recommendation.",
            page="/finance/bankers-snapshot",
            status=(
                StepStatus.BLOCKED if deal_killers > 0
                else StepStatus.NOT_STARTED
            ),
            blocked_by=(
                [f"{deal_killers} FATAL deal-killer(s) must be resolved or waived"]
                if deal_killers > 0 else []
            ),
        ),
    ]

    return ActorFlow(
        actor_type=ActorType.CREDIT_COMMITTEE_CHAIR,
        project_id=project_id,
        objective="Determine whether this project is ready for credit committee discussion",
        overall_status="NOT_READY" if deal_killers > 0 else "CONDITIONAL",
        steps=steps,
        fatal_killers_active=deal_killers,
        next_action="Review evidence hierarchy",
        next_action_page="/finance/evidence-hierarchy",
    )


def build_producer_flow(project_id: str, project_data: dict) -> ActorFlow:
    """4-step flow: Configure Plant → Upload Evidence → Check Bankability → Structuring."""
    plant_configured = project_data.get("plant_configured", False)
    next_gate_items  = project_data.get("next_gate_missing_items", 0)
    deal_killers     = project_data.get("active_fatal_killers", 0)

    steps = [
        FlowStep(
            number=1,
            title="Configure Plant",
            description="Enter technology type, TRL, engineering stage, and equipment in Plant Builder.",
            page="/finance/plant-builder",
            status=StepStatus.DONE if plant_configured else StepStatus.IN_PROGRESS,
            status_detail="Configured" if plant_configured else "Technology type and TRL required",
        ),
        FlowStep(
            number=2,
            title="Upload Evidence",
            description="Submit documents for the next gate. All evidence starts as UNVERIFIED.",
            page="/finance/stage-gates",
            status=StepStatus.IN_PROGRESS,
            status_detail=f"{next_gate_items} item(s) missing for next gate",
        ),
        FlowStep(
            number=3,
            title="Check Bankability and Deal-Killers",
            description="See what is blocking progress and what deal-killers are outstanding.",
            page="/finance/bankability",
            status=StepStatus.DONE if deal_killers == 0 else StepStatus.IN_PROGRESS,
            status_detail=(
                "No blocking deal-killers" if deal_killers == 0
                else f"{deal_killers} deal-killer(s) active"
            ),
        ),
        FlowStep(
            number=4,
            title="View Structuring Recommendation",
            description="See which de-risking instruments apply to your project stage and molecule.",
            page="/finance/instrument-catalog",
            status=StepStatus.NOT_STARTED,
        ),
    ]

    return ActorFlow(
        actor_type=ActorType.PRODUCER,
        project_id=project_id,
        objective="Advance this project to the next bankability gate",
        overall_status="IN_PROGRESS",
        steps=steps,
        fatal_killers_active=deal_killers,
        next_action="Upload missing evidence" if next_gate_items > 0 else "Check deal-killers",
        next_action_page="/finance/stage-gates" if next_gate_items > 0 else "/finance/bankability",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TASK ROUTER ENGINE (dispatcher)
# ═══════════════════════════════════════════════════════════════════════════════

class TaskRouterEngine:
    def get_flow(self, actor_type: ActorType, project_id: str, project_data: dict) -> ActorFlow:
        builders = {
            ActorType.COMMERCIAL_BANKER:      build_banker_rm_flow,
            ActorType.OFFTAKER:               build_offtaker_flow,
            ActorType.CREDIT_COMMITTEE_CHAIR: build_credit_committee_flow,
            ActorType.PRODUCER:               build_producer_flow,
        }
        builder = builders.get(actor_type)
        if builder is None:
            raise ValueError(f"Unknown actor type: {actor_type}")
        return builder(project_id, project_data)

    def complete_step(
        self,
        actor_type: ActorType,
        project_id: str,
        step_number: int,
        project_data: dict,
    ) -> FlowStep:
        flow = self.get_flow(actor_type, project_id, project_data)
        matching = [s for s in flow.steps if s.number == step_number]
        if not matching:
            raise ValueError(f"Step {step_number} not found in {actor_type} flow")
        step = matching[0]
        step.status = StepStatus.DONE
        return step


task_router_engine = TaskRouterEngine()
