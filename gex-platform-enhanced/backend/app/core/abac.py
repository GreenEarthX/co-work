"""
GEX ABAC Policy Engine — Attribute-Based Access Control
=========================================================
Evaluates every API request against user, resource, and context attributes.
Replaces role-based access. Workspaces are presentation. ABAC is security.

Location: gex-enhanced-platform/backend/app/core/abac.py

Phase 1: Rules R1-R3 (stakeholder gate, gate visibility, evidence sensitivity)
Phase 2: Rules R4-R6 (financial model protection, write permissions, export control)
Phase 3: Context attributes (project state, jurisdiction, time-based windows)
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Set
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class ActorType(str, Enum):
    PRODUCER = "PRODUCER"
    OFFTAKER = "OFFTAKER"
    COMMERCIAL_BANKER = "COMMERCIAL_BANKER"
    DFI = "DFI"
    INSURER = "INSURER"
    REGULATOR = "REGULATOR"
    GOV_AGENCY = "GOV_AGENCY"
    CERTIFIER = "CERTIFIER"
    EPC_CONTRACTOR = "EPC_CONTRACTOR"
    LOGISTICS_OPERATOR = "LOGISTICS_OPERATOR"
    TECHNOLOGY_PROVIDER = "TECHNOLOGY_PROVIDER"
    EXECUTIVE = "EXECUTIVE"
    # Unauthenticated / unvetted prospect — PUBLIC data only, no gate access
    GUEST = "GUEST"


class Sensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    SHARED = "SHARED"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class Action(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    VERIFY = "VERIFY"
    EXPORT = "EXPORT"
    SHARE = "SHARE"
    DELETE = "DELETE"


class ClearanceLevel(str, Enum):
    STANDARD = "STANDARD"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


# Clearance hierarchy for comparison
_CLEARANCE_ORDER = {
    ClearanceLevel.STANDARD: 0,
    ClearanceLevel.CONFIDENTIAL: 1,
    ClearanceLevel.RESTRICTED: 2,
}

_SENSITIVITY_ORDER = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.SHARED: 1,
    Sensitivity.CONFIDENTIAL: 2,
    Sensitivity.RESTRICTED: 3,
}


# ═══════════════════════════════════════════════════════════════
# ATTRIBUTE OBJECTS
# ═══════════════════════════════════════════════════════════════

@dataclass
class UserAttributes:
    """Attributes of the requesting user — loaded from auth token + DB."""
    user_id: str
    company_id: str
    actor_type_per_project: dict[str, ActorType]  # project_id → ActorType
    clearance_level: ClearanceLevel = ClearanceLevel.STANDARD
    jurisdiction: str = ""
    kyc_status: str = "VERIFIED"
    nda_signed_with: Set[str] = field(default_factory=set)
    assigned_audits: Set[str] = field(default_factory=set)  # project_ids for certifiers


@dataclass
class ResourceAttributes:
    """Attributes of the data being accessed — loaded from DB record."""
    project_id: str
    data_owner_company_id: str
    sensitivity: Sensitivity = Sensitivity.SHARED
    shared_with: Set[str] = field(default_factory=set)
    gate_id: Optional[str] = None
    evidence_type: Optional[str] = None
    resource_type: str = "EVIDENCE"  # EVIDENCE, FINANCIAL_MODEL, PLANT_TECHNICAL, etc.
    resource_id: str = ""
    mandated_lenders: Set[str] = field(default_factory=set)  # for FINANCIAL_MODEL only
    mandated_insurers: Set[str] = field(default_factory=set)


@dataclass
class ContextAttributes:
    """Attributes of the request context — computed at request time."""
    project_stakeholders: Set[str]  # company_ids that are stakeholders on this project
    project_jurisdiction: str = ""
    project_state: str = "SPECULATIVE"
    competing_bidders: Set[str] = field(default_factory=set)
    request_timestamp: str = ""

    def __post_init__(self):
        if not self.request_timestamp:
            self.request_timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class AccessDecision:
    """Result of policy evaluation — logged immutably."""
    decision: Decision
    rules_evaluated: list[str]
    denial_reason: Optional[str] = None
    attributes_snapshot: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════
# GATE VISIBILITY MATRIX
# ═══════════════════════════════════════════════════════════════

GATE_VISIBILITY: dict[ActorType, list[str]] = {
    ActorType.PRODUCER: [
        "G0_SITE_RIGHTS", "G1_GRID_WATER", "G3_FEEDSTOCK_LOGISTICS",
        "G5_EPC", "G9_PERMITS", "G11_COD",
    ],
    ActorType.OFFTAKER: ["G4_OFFTAKE"],
    ActorType.COMMERCIAL_BANKER: [
        "G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE",
        "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE",
    ],
    ActorType.DFI: [
        "G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE",
        "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE",
    ],
    ActorType.INSURER: ["G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE"],
    ActorType.REGULATOR: ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
    ActorType.GOV_AGENCY: [
        "G0_SITE_RIGHTS", "G1_GRID_WATER", "G2_CERTIFICATION",
        "G3_FEEDSTOCK_LOGISTICS", "G4_OFFTAKE", "G5_EPC", "G6_IE_SIGNOFF",
        "G7_INSURANCE", "G8_MODEL_AUDIT", "G9_PERMITS",
        "G10_FINANCIAL_CLOSE", "G11_COD",
    ],
    ActorType.CERTIFIER: ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
    ActorType.EPC_CONTRACTOR: ["G5_EPC", "G11_COD"],
    ActorType.LOGISTICS_OPERATOR: ["G3_FEEDSTOCK_LOGISTICS"],
    ActorType.TECHNOLOGY_PROVIDER: ["G5_EPC", "G11_COD"],
    ActorType.EXECUTIVE: [
        "G0_SITE_RIGHTS", "G1_GRID_WATER", "G2_CERTIFICATION",
        "G3_FEEDSTOCK_LOGISTICS", "G4_OFFTAKE", "G5_EPC", "G6_IE_SIGNOFF",
        "G7_INSURANCE", "G8_MODEL_AUDIT", "G9_PERMITS",
        "G10_FINANCIAL_CLOSE", "G11_COD",
    ],
    # GUEST: no gate access — PUBLIC sensitivity resources only
    ActorType.GUEST: [],
}


# ═══════════════════════════════════════════════════════════════
# POLICY RULES
# ═══════════════════════════════════════════════════════════════

def _rule_0_guest_gate(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> Optional[AccessDecision]:
    """R0: GUEST actors may only access PUBLIC resources.
    Evaluated before all other rules so unauthenticated prospects
    cannot reach any project data, evidence, or financial models.
    """
    actor_type = user.actor_type_per_project.get(resource.project_id, ActorType.GUEST)
    if actor_type != ActorType.GUEST:
        return None  # Not a guest — pass to later rules

    if resource.sensitivity == Sensitivity.PUBLIC:
        return None  # Guests can read public resources

    return AccessDecision(
        decision=Decision.DENY,
        rules_evaluated=["R0"],
        denial_reason="Guest users may only access PUBLIC resources. "
                      "Complete KYC verification to access project data.",
    )


# GUEST_POLICY — CISO-configurable set of PUBLIC resources a guest may see.
# Keys are feature slugs; True = visible to guests. CISO writes this at runtime.
DEFAULT_GUEST_POLICY: dict[str, bool] = {
    "onboarding_wizard": True,       # Always open — lead capture
    "market_demand_overview": True,  # Aggregated, no project names
    "gate_definitions": True,        # Public knowledge
    "pricing_curves": False,         # Indicative only — CISO opt-in
    "project_data": False,
    "evidence": False,
    "bankability_scores": False,
    "contracts": False,
    "data_room": False,
    "capital_stack": False,
}


def _rule_1_stakeholder_gate(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> Optional[AccessDecision]:
    """R1: User must be a stakeholder on this project (or regulator in jurisdiction)."""
    if resource.sensitivity == Sensitivity.PUBLIC:
        return None  # Public data — pass through

    if user.company_id in context.project_stakeholders:
        return None  # Stakeholder — pass through

    actor_type = user.actor_type_per_project.get(resource.project_id)
    if actor_type == ActorType.REGULATOR and user.jurisdiction == context.project_jurisdiction:
        return None  # Regulator in same jurisdiction — pass through

    if actor_type == ActorType.GOV_AGENCY and user.jurisdiction == context.project_jurisdiction:
        return None  # Government agency in same jurisdiction — pass through

    if actor_type == ActorType.CERTIFIER and resource.project_id in user.assigned_audits:
        return None  # Assigned certifier — pass through

    return AccessDecision(
        decision=Decision.DENY,
        rules_evaluated=["R1"],
        denial_reason="User is not a stakeholder on this project",
    )


def _rule_2_gate_visibility(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> list[str]:
    """R2: Compute visible gates for this user on this project. Returns gate list (not a deny)."""
    actor_type = user.actor_type_per_project.get(resource.project_id)
    if not actor_type:
        return []
    return GATE_VISIBILITY.get(actor_type, [])


def _rule_3_evidence_sensitivity(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> Optional[AccessDecision]:
    """R3: Document-level access based on sensitivity + sharing grants."""
    if resource.sensitivity == Sensitivity.PUBLIC:
        return None

    if resource.data_owner_company_id == user.company_id:
        return None  # Owner always sees their own data

    if user.company_id in resource.shared_with:
        return None  # Explicitly shared

    actor_type = user.actor_type_per_project.get(resource.project_id)

    if actor_type == ActorType.CERTIFIER and resource.project_id in user.assigned_audits:
        if resource.gate_id in GATE_VISIBILITY.get(ActorType.CERTIFIER, []):
            return None  # Certifier on assigned audit, relevant gate

    if actor_type == ActorType.REGULATOR and user.jurisdiction == context.project_jurisdiction:
        return None  # Regulator in jurisdiction

    return AccessDecision(
        decision=Decision.DENY,
        rules_evaluated=["R3"],
        denial_reason=f"Evidence sensitivity={resource.sensitivity.value}, "
                      f"user company not in shared_with and not data owner",
    )


def _rule_4_financial_model_protection(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> Optional[AccessDecision]:
    """R4: Competitive intelligence protection for financial models. Phase 2."""
    if resource.resource_type != "FINANCIAL_MODEL":
        return None  # Only applies to financial models

    if resource.data_owner_company_id == user.company_id:
        return None  # Owner sees own model

    actor_type = user.actor_type_per_project.get(resource.project_id)

    if actor_type in (ActorType.COMMERCIAL_BANKER, ActorType.DFI):
        if user.company_id in resource.mandated_lenders:
            return None  # Mandated lender
    elif actor_type == ActorType.INSURER:
        if user.company_id in resource.mandated_insurers:
            return None  # Mandated insurer

    # Check competing bidder
    if user.company_id in context.competing_bidders:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R4"],
            denial_reason="Competing bidder — financial model access denied",
        )

    return AccessDecision(
        decision=Decision.DENY,
        rules_evaluated=["R4"],
        denial_reason="Not a mandated lender/insurer or data owner",
    )


def _rule_5_write_permissions(
    user: UserAttributes, resource: ResourceAttributes, action: Action, context: ContextAttributes
) -> Optional[AccessDecision]:
    """R5: Write/verify permissions based on gate ownership. Phase 2."""
    if action not in (Action.WRITE, Action.VERIFY, Action.DELETE):
        return None  # Only applies to write actions

    actor_type = user.actor_type_per_project.get(resource.project_id)

    if action == Action.VERIFY:
        if actor_type == ActorType.CERTIFIER and resource.project_id in user.assigned_audits:
            return None  # Certifier can verify
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R5"],
            denial_reason="Only assigned certifiers can verify evidence",
        )

    if action == Action.WRITE:
        visible = GATE_VISIBILITY.get(actor_type, [])
        if resource.gate_id and resource.gate_id in visible:
            return None  # Can write to gates they own
        if resource.resource_type == "FINANCIAL_MODEL":
            if actor_type in (ActorType.COMMERCIAL_BANKER, ActorType.DFI):
                if user.company_id in resource.mandated_lenders:
                    return None
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R5"],
            denial_reason=f"Actor type {actor_type} cannot write to gate {resource.gate_id}",
        )

    return None


def _rule_6_export_share(
    user: UserAttributes, resource: ResourceAttributes, action: Action, context: ContextAttributes,
    target_company_id: Optional[str] = None,
) -> Optional[AccessDecision]:
    """R6: Export and share control based on clearance + NDA. Phase 2."""
    if action not in (Action.EXPORT, Action.SHARE):
        return None

    if action == Action.EXPORT:
        user_level = _CLEARANCE_ORDER.get(user.clearance_level, 0)
        resource_level = _SENSITIVITY_ORDER.get(resource.sensitivity, 0)
        if user_level < resource_level and resource.data_owner_company_id != user.company_id:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=["R6"],
                denial_reason=f"Clearance {user.clearance_level.value} insufficient "
                              f"for sensitivity {resource.sensitivity.value}",
            )

    if action == Action.SHARE and target_company_id:
        if target_company_id not in user.nda_signed_with:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=["R6"],
                denial_reason=f"No NDA signed with target company {target_company_id}",
            )

    return None


# ═══════════════════════════════════════════════════════════════
# PUBLIC API — evaluate access
# ═══════════════════════════════════════════════════════════════

def evaluate_access(
    user: UserAttributes,
    resource: ResourceAttributes,
    action: Action,
    context: ContextAttributes,
    target_company_id: Optional[str] = None,
    phase: int = 1,
) -> AccessDecision:
    """
    Evaluate an access request against ABAC policy rules.

    Args:
        user: Attributes of the requesting user
        resource: Attributes of the data being accessed
        action: What the user is trying to do
        context: Request context (project stakeholders, jurisdiction, state)
        target_company_id: For SHARE action — who is the recipient
        phase: Implementation phase (1=R1-R3, 2=R1-R6, 3=R1-R6+context)

    Returns:
        AccessDecision with ALLOW or DENY + reasoning
    """
    rules_evaluated = []

    # R0 — Guest gate (always first, regardless of phase)
    r0 = _rule_0_guest_gate(user, resource, context)
    rules_evaluated.append("R0")
    if r0 and r0.decision == Decision.DENY:
        r0.attributes_snapshot = _snapshot(user, resource, action, context)
        return r0

    # Phase 1: R1 — Stakeholder gate
    r1 = _rule_1_stakeholder_gate(user, resource, context)
    rules_evaluated.append("R1")
    if r1 and r1.decision == Decision.DENY:
        r1.attributes_snapshot = _snapshot(user, resource, action, context)
        return r1

    # Phase 1: R3 — Evidence sensitivity (READ actions)
    if action == Action.READ:
        r3 = _rule_3_evidence_sensitivity(user, resource, context)
        rules_evaluated.append("R3")
        if r3 and r3.decision == Decision.DENY:
            r3.attributes_snapshot = _snapshot(user, resource, action, context)
            return r3

    # Phase 2+: R4 — Financial model protection
    if phase >= 2 and action == Action.READ:
        r4 = _rule_4_financial_model_protection(user, resource, context)
        rules_evaluated.append("R4")
        if r4 and r4.decision == Decision.DENY:
            r4.attributes_snapshot = _snapshot(user, resource, action, context)
            return r4

    # Phase 2+: R5 — Write permissions
    if phase >= 2 and action in (Action.WRITE, Action.VERIFY, Action.DELETE):
        r5 = _rule_5_write_permissions(user, resource, action, context)
        rules_evaluated.append("R5")
        if r5 and r5.decision == Decision.DENY:
            r5.attributes_snapshot = _snapshot(user, resource, action, context)
            return r5

    # Phase 2+: R6 — Export & share control
    if phase >= 2 and action in (Action.EXPORT, Action.SHARE):
        r6 = _rule_6_export_share(user, resource, action, context, target_company_id)
        rules_evaluated.append("R6")
        if r6 and r6.decision == Decision.DENY:
            r6.attributes_snapshot = _snapshot(user, resource, action, context)
            return r6

    return AccessDecision(
        decision=Decision.ALLOW,
        rules_evaluated=rules_evaluated,
        attributes_snapshot=_snapshot(user, resource, action, context),
    )


def get_visible_gates(user: UserAttributes, project_id: str) -> list[str]:
    """
    Compute which bankability gates this user can see on this project.
    Used by the Platform when calling the PF Engine — replaces hardcoded PERSONA_GATES.
    """
    actor_type = user.actor_type_per_project.get(project_id)
    if not actor_type:
        return []
    return GATE_VISIBILITY.get(actor_type, [])


def _snapshot(user: UserAttributes, resource: ResourceAttributes,
              action: Action, context: ContextAttributes) -> dict:
    """Capture attribute values at decision time for immutable audit trail."""
    return {
        "user_id": user.user_id,
        "company_id": user.company_id,
        "actor_type": str(user.actor_type_per_project.get(resource.project_id, "NONE")),
        "clearance": user.clearance_level.value,
        "action": action.value,
        "resource_type": resource.resource_type,
        "resource_id": resource.resource_id,
        "project_id": resource.project_id,
        "sensitivity": resource.sensitivity.value,
        "project_state": context.project_state,
        "timestamp": context.request_timestamp,
    }
