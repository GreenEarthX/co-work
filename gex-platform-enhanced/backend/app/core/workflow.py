"""
GEX Bankability Workflow — State Machine (v2.1 — R3/R10 reform)

Governs the lifecycle of all bankability objects:
  DRAFT → COMPUTED → REVIEWED → APPROVED → EXPORTED → SHARED_EXTERNAL

All transitions are validated here. ABAC permissions are checked before
advancing state. Every transition is logged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from enum import Enum


class WorkflowState(str, Enum):
    DRAFT = "DRAFT"
    COMPUTED = "COMPUTED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"
    SHARED_EXTERNAL = "SHARED_EXTERNAL"


# Valid forward transitions
ALLOWED_TRANSITIONS: dict[WorkflowState, list[WorkflowState]] = {
    WorkflowState.DRAFT: [WorkflowState.COMPUTED],
    WorkflowState.COMPUTED: [WorkflowState.REVIEWED, WorkflowState.DRAFT],  # DRAFT = rejection path
    WorkflowState.REVIEWED: [WorkflowState.APPROVED, WorkflowState.DRAFT],
    WorkflowState.APPROVED: [WorkflowState.EXPORTED],
    WorkflowState.EXPORTED: [WorkflowState.SHARED_EXTERNAL],
    WorkflowState.SHARED_EXTERNAL: [],
}

# Minimum role required to perform each transition
TRANSITION_ROLES: dict[tuple[WorkflowState, WorkflowState], str] = {
    (WorkflowState.DRAFT, WorkflowState.COMPUTED): "system",
    (WorkflowState.COMPUTED, WorkflowState.REVIEWED): "analyst",
    (WorkflowState.COMPUTED, WorkflowState.DRAFT): "analyst",      # rejection
    (WorkflowState.REVIEWED, WorkflowState.APPROVED): "cfo",
    (WorkflowState.REVIEWED, WorkflowState.DRAFT): "analyst",      # rejection
    (WorkflowState.APPROVED, WorkflowState.EXPORTED): "analyst",
    (WorkflowState.EXPORTED, WorkflowState.SHARED_EXTERNAL): "analyst",
}

# Objects that are workflow-governed (cannot be exported without APPROVED state)
GOVERNED_OBJECTS = {
    "BankabilitySnapshot",
    "SensitivityRun",
    "OfftakeAssessment",
    "CertificationReadiness",
    "CapitalStackScenario",
    "ICPack",
    "EvidencePack",
}


class WorkflowResult:
    def __init__(
        self,
        success: bool,
        new_state: Optional[WorkflowState] = None,
        error: Optional[str] = None,
        previous_state: Optional[WorkflowState] = None,
    ):
        self.success = success
        self.new_state = new_state
        self.error = error
        self.previous_state = previous_state
        self.transitioned_at = datetime.now(timezone.utc).isoformat()


def advance_state(
    current_state: WorkflowState,
    target_state: WorkflowState,
    actor_role: str,
    object_type: str,
    rejection_reason: Optional[str] = None,
    # R3: Named reviewer fields — required for REVIEWED / EXPORTED
    reviewer_user_id: Optional[str] = None,
    reviewer_name: Optional[str] = None,
    reviewer_title: Optional[str] = None,
    review_scope: Optional[str] = None,
) -> WorkflowResult:
    """
    Validate and execute a workflow state transition.

    Returns WorkflowResult with success=True and new_state on success,
    or success=False and error message on failure.
    """
    allowed = ALLOWED_TRANSITIONS.get(current_state, [])
    if target_state not in allowed:
        return WorkflowResult(
            success=False,
            error=f"Invalid transition: {current_state} → {target_state}. "
                  f"Allowed transitions: {[s.value for s in allowed]}",
            previous_state=current_state,
        )

    required_role = TRANSITION_ROLES.get((current_state, target_state), "analyst")
    role_hierarchy = ["viewer", "analyst", "cfo", "system"]
    actor_level = role_hierarchy.index(actor_role) if actor_role in role_hierarchy else -1
    required_level = role_hierarchy.index(required_role) if required_role in role_hierarchy else 99

    if actor_level < required_level:
        return WorkflowResult(
            success=False,
            error=f"Insufficient role. Required: {required_role}, actual: {actor_role}.",
            previous_state=current_state,
        )

    if target_state == WorkflowState.DRAFT and not rejection_reason:
        return WorkflowResult(
            success=False,
            error="Rejection to DRAFT requires a rejection_reason.",
            previous_state=current_state,
        )

    # R3: Named reviewer required for REVIEWED and EXPORTED transitions
    if target_state in (WorkflowState.REVIEWED, WorkflowState.EXPORTED):
        if not reviewer_user_id:
            return WorkflowResult(
                success=False,
                error=(
                    f"Transition to {target_state.value} requires a named reviewer. "
                    "Provide reviewer_user_id, reviewer_name, reviewer_title, and review_scope."
                ),
                previous_state=current_state,
            )
        if not reviewer_name or not reviewer_title:
            return WorkflowResult(
                success=False,
                error=(
                    "reviewer_name and reviewer_title are required. "
                    "The reviewer must be identified by name and title for accountability."
                ),
                previous_state=current_state,
            )

    return WorkflowResult(
        success=True,
        new_state=target_state,
        previous_state=current_state,
    )


def can_export(state: WorkflowState, object_type: str) -> tuple[bool, Optional[str]]:
    """
    Check whether an object can be exported/shared externally.
    Returns (allowed, error_message).
    """
    if object_type not in GOVERNED_OBJECTS:
        return True, None  # Non-governed objects can always be exported

    if state not in (WorkflowState.APPROVED, WorkflowState.EXPORTED, WorkflowState.SHARED_EXTERNAL):
        return False, (
            f"Object is in state {state.value}. Export requires APPROVED state. "
            f"Current workflow position: {state.value}."
        )

    return True, None


def can_export_ic_pack(
    workflow_state: WorkflowState,
    reviewer_user_id: Optional[str],
    has_fatal_deal_killers: bool,
    g8_is_audit_grade: bool,
    unverified_section_count: int,
) -> tuple[bool, list[str], list[str]]:
    """
    R10: IC Pack-specific export gate with structured blockers.
    Returns (allowed, blockers, resolutions).

    Checks (all must pass):
    1. Workflow state = APPROVED
    2. Named reviewer exists
    3. No FATAL deal-killers ACTIVE
    4. G8 financial model is AUDIT_GRADE
    5. All 9 IC sections have evidence at CONFIRMED or above
    """
    blockers: list[str] = []
    resolutions: list[str] = []

    if workflow_state != WorkflowState.APPROVED:
        blockers.append(f"Workflow state is {workflow_state.value}. IC Pack requires APPROVED state.")
        resolutions.append("Advance workflow to APPROVED via the Deal Room approval queue.")

    if not reviewer_user_id:
        blockers.append("No named reviewer assigned. A named reviewer with title is required.")
        resolutions.append("Mark as Reviewed with a named reviewer before requesting approval.")

    if has_fatal_deal_killers:
        blockers.append("One or more FATAL deal-killers are ACTIVE. IC Pack cannot be exported with unresolved deal-killers.")
        resolutions.append("Resolve all FATAL deal-killers. See Deal-Killer banner for required actions.")

    if not g8_is_audit_grade:
        blockers.append("G8 financial model status is not AUDIT_GRADE. An audited financial model is required.")
        resolutions.append("Commission financial model audit from a named firm and confirm AUDITED verification state.")

    if unverified_section_count > 0:
        blockers.append(
            f"{unverified_section_count} IC Pack section(s) contain UNVERIFIED documents. "
            "All sections require evidence at CONFIRMED or above."
        )
        resolutions.append("Submit outstanding documents for third-party verification before export.")

    return (len(blockers) == 0, blockers, resolutions)


def is_stale(computed_at: Optional[datetime], threshold_days: int = 7) -> bool:
    """Return True if computed_at is older than threshold_days."""
    if computed_at is None:
        return False
    age = datetime.now(timezone.utc) - computed_at.replace(tzinfo=timezone.utc)
    return age.days > threshold_days
