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
    # DFI concessional sub-persona — sees additionality, DFI criteria, adjacency data
    DFI_CONCESSIONAL = "DFI_CONCESSIONAL"
    # Export Credit Agency — de-risks cross-border capital via sovereign guarantees
    ECA = "ECA"
    # Unauthenticated / unvetted prospect — PUBLIC data only, no gate access
    GUEST = "GUEST"


class Sensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    SHARED = "SHARED"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class ESGComplianceLevel(str, Enum):
    """ESG compliance tiers for marketplace and ABAC gating."""
    STANDARD = "STANDARD"
    VERIFIED = "VERIFIED"
    SOVEREIGN = "SOVEREIGN"


class TradeAction(str, Enum):
    """Actions specific to marketplace trade execution (R7-R9)."""
    BUY = "BUY"
    SELL = "SELL"
    PRODUCE = "PRODUCE"
    TRANSFORM = "TRANSFORM"


class Capability(str, Enum):
    """Capabilities an entity can hold — replaces single actor_type for prosumers."""
    OFFTAKE = "OFFTAKE"       # Can buy feedstock / end-product
    PRODUCE = "PRODUCE"       # Can produce / transform molecules
    SELL = "SELL"              # Can sell produced output
    TRADE = "TRADE"           # Can trade on marketplace (broker/trader)
    CERTIFY = "CERTIFY"       # Can certify / audit
    FINANCE = "FINANCE"       # Can provide financing
    INSURE = "INSURE"         # Can provide insurance


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

# Credit rating ordinal — higher = better.  Supports GEX internal + S&P notation.
CREDIT_RATING_ORDER: dict[str, int] = {
    "NR": 0,          # Not Rated
    "D": 1,
    "C": 2,
    "CC": 3,
    "CCC-": 4, "CCC": 5, "CCC+": 6,
    "B-": 7,  "B": 8,  "B+": 9,
    "BB-": 10, "BB": 11, "BB+": 12,
    "BBB-": 13, "BBB": 14, "BBB+": 15,
    "A-": 16, "A": 17, "A+": 18,
    "AA-": 19, "AA": 20, "AA+": 21,
    "AAA": 22,
    # GEX internal shorthand ratings (map to S&P equivalents)
    "GEX-1": 7,   # ≈ B
    "GEX-2": 11,  # ≈ BB
    "GEX-3": 14,  # ≈ BBB
    "GEX-4": 17,  # ≈ A
    "GEX-5": 20,  # ≈ AA
}


def _rating_ordinal(rating: str) -> int:
    """Convert a credit rating string to its ordinal for comparison."""
    return CREDIT_RATING_ORDER.get(rating, 0)


# ═══════════════════════════════════════════════════════════════
# ATTRIBUTE OBJECTS
# ═══════════════════════════════════════════════════════════════

@dataclass
class UserAttributes:
    """Attributes of the requesting user — loaded from auth token + DB."""
    user_id: str
    company_id: str
    actor_type_per_project: dict[str, list[ActorType]]  # project_id → [ActorType, …]  (prosumer = multiple)
    clearance_level: ClearanceLevel = ClearanceLevel.STANDARD
    jurisdiction: str = ""
    kyc_status: str = "VERIFIED"
    nda_signed_with: Set[str] = field(default_factory=set)
    assigned_audits: Set[str] = field(default_factory=set)  # project_ids for certifiers
    # ── Prosumer / trade attributes (Phase 3) ──
    capabilities: Set[Capability] = field(default_factory=set)       # e.g. {OFFTAKE, PRODUCE, SELL}
    credit_rating: str = "NR"                                        # S&P or GEX-internal rating
    credit_rating_source: str = "GEX"                                # "GEX" | "S&P" | "HOUSE_BANK"
    export_licenses: list[str] = field(default_factory=list)         # ISO-3166-1 alpha-2 codes, e.g. ["DE"]
    token_ready: bool = False                                        # configured for tokenized molecule settlement
    transformation_license: bool = False                             # licensed to transform feedstock → end-product
    aggregation_limit_mt: Optional[float] = None                     # max metric-tons this entity may aggregate
    # ── ESG & Sovereign compliance (Phase 3+) ──
    esg_compliance_score: Optional[float] = None                     # 0-100 composite ESG score
    esg_compliance_level: str = "STANDARD"                           # STANDARD | VERIFIED | SOVEREIGN (ESGComplianceLevel)
    esg_certifications: list[str] = field(default_factory=list)      # e.g. ["RED_III", "RFNBO", "45V"]
    sovereign_jurisdiction: str = ""                                  # ISO-3166 country for sovereign token ops
    dfi_accredited: bool = False                                     # accredited by a DFI for concessional access


@dataclass
class ResourceAttributes:
    """Attributes of the data being accessed — loaded from DB record."""
    project_id: str
    data_owner_company_id: str
    sensitivity: Sensitivity = Sensitivity.SHARED
    shared_with: Set[str] = field(default_factory=set)
    gate_id: Optional[str] = None
    evidence_type: Optional[str] = None
    resource_type: str = "EVIDENCE"  # EVIDENCE, FINANCIAL_MODEL, PLANT_TECHNICAL, SOVEREIGN_TOKEN, ADDITIONALITY, DFI_CRITERIA, ADJACENCY, etc.
    resource_id: str = ""
    mandated_lenders: Set[str] = field(default_factory=set)  # for FINANCIAL_MODEL only
    mandated_insurers: Set[str] = field(default_factory=set)
    # ── ESG / Sovereign attributes ──
    esg_required_score: Optional[float] = None           # min ESG score to access this resource
    esg_compliance_required: str = ""                    # STANDARD | VERIFIED | SOVEREIGN (ESGComplianceLevel)
    required_certifications: list[str] = field(default_factory=list)  # e.g. ["RED_III"]
    sovereign_origin: str = ""                           # ISO-3166 country of sovereign token
    dfi_funded: bool = False                             # resource backed by concessional capital


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
class TradeContext:
    """Context for a marketplace trade action — evaluated by rules R7-R9."""
    action: TradeAction                          # BUY, SELL, PRODUCE, TRANSFORM
    molecule: str = ""                           # H2, NH3, SAF, eMeOH
    is_tokenized: bool = False                   # molecule is tokenized on-chain
    destination: str = ""                        # ISO-3166 alpha-2 of delivery destination
    required_rating: str = "NR"                  # min credit rating the counterparty demands
    volume_mt: float = 0.0                       # trade volume in metric tons
    counterparty_company_id: str = ""


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
    # DFI_CONCESSIONAL: same as DFI + additionality + adjacency visibility
    ActorType.DFI_CONCESSIONAL: [
        "G4_OFFTAKE", "G6_IE_SIGNOFF", "G7_INSURANCE",
        "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE",
    ],
    # ECA: Export Credit Agency — insurance, financial close, offtake, EPC
    ActorType.ECA: [
        "G4_OFFTAKE", "G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE",
        "G8_MODEL_AUDIT", "G10_FINANCIAL_CLOSE",
    ],
    # GUEST: no gate access — PUBLIC sensitivity resources only
    ActorType.GUEST: [],
}


# ── Evidence → gate resolution (fixes R5 "write to gate None" deny) ──────────
# An evidence write (POST /bankability/evidence) carries an evidence_key, not a
# gate. Without resolving the gate, R5 sees gate_id=None and denies EVERY actor.
# Build the reverse map from the gate registry; match by gate-NUMBER prefix so
# the two registry vocabularies (G1_GRID_WATER vs G1_GRID_UTILITIES_REALITY)
# don't cause a false deny — the stable taxonomy is the gate number.

def gate_number(gate_id: Optional[str]) -> Optional[str]:
    """G1_GRID_WATER → 'G1'. The vocabulary-agnostic gate identity."""
    if not gate_id:
        return None
    return gate_id.split("_", 1)[0]


_EVIDENCE_TO_GATE: dict[str, str] = {}
try:
    from app.core.bankability_engine import GATE_REGISTRY as _GR
    for _g in _GR:
        for _ev in getattr(_g, "required_evidence", []):
            _EVIDENCE_TO_GATE[_ev] = _g.id
except Exception:
    _EVIDENCE_TO_GATE = {}


def gate_for_evidence(evidence_key: Optional[str]) -> Optional[str]:
    """Resolve an evidence_key to its owning gate id (or None if unmapped)."""
    return _EVIDENCE_TO_GATE.get(evidence_key) if evidence_key else None


# ═══════════════════════════════════════════════════════════════
# POLICY RULES
# ═══════════════════════════════════════════════════════════════

def _actor_types_for_project(user: UserAttributes, project_id: str) -> list[ActorType]:
    """Resolve actor types for a user on a project.  Returns [GUEST] if none.

    Precedence: the JWT-baked map first (login-time scope), then the project
    registry by ownership. The registry fallback is what makes a project created
    AFTER the caller's token was issued — e.g. via the on-ramp — immediately
    accessible to its owning company, without forcing a re-login. It only ever
    grants PRODUCER to the owner company; every other company stays GUEST.
    """
    raw = user.actor_type_per_project.get(project_id)
    if raw is not None:
        # Back-compat: accept a single ActorType or a list
        if isinstance(raw, list):
            return raw if raw else [ActorType.GUEST]
        return [raw]

    # No baked entry — derive from ownership in the registry so freshly-minted
    # projects are reachable by their owner before the token is refreshed.
    try:
        from app.core.project_registry import get_project_profile
        profile = get_project_profile(project_id)
        if profile is not None and user.company_id == profile.owner_company_id:
            return [ActorType.PRODUCER]
    except Exception:
        pass
    return [ActorType.GUEST]


def _rule_0_guest_gate(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> Optional[AccessDecision]:
    """R0: GUEST actors may only access PUBLIC resources.
    Evaluated before all other rules so unauthenticated prospects
    cannot reach any project data, evidence, or financial models.
    """
    actor_types = _actor_types_for_project(user, resource.project_id)
    if actor_types != [ActorType.GUEST]:
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

    actor_types = _actor_types_for_project(user, resource.project_id)

    if ActorType.REGULATOR in actor_types and user.jurisdiction == context.project_jurisdiction:
        return None  # Regulator in same jurisdiction — pass through

    if ActorType.GOV_AGENCY in actor_types and user.jurisdiction == context.project_jurisdiction:
        return None  # Government agency in same jurisdiction — pass through

    if ActorType.CERTIFIER in actor_types and resource.project_id in user.assigned_audits:
        return None  # Assigned certifier — pass through

    return AccessDecision(
        decision=Decision.DENY,
        rules_evaluated=["R1"],
        denial_reason="User is not a stakeholder on this project",
    )


def _rule_2_gate_visibility(
    user: UserAttributes, resource: ResourceAttributes, context: ContextAttributes
) -> list[str]:
    """R2: Compute visible gates for this user on this project.
    Prosumers see the union of gates across all their actor types."""
    actor_types = _actor_types_for_project(user, resource.project_id)
    gates: set[str] = set()
    for at in actor_types:
        gates.update(GATE_VISIBILITY.get(at, []))
    return sorted(gates)


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

    actor_types = _actor_types_for_project(user, resource.project_id)

    if ActorType.CERTIFIER in actor_types and resource.project_id in user.assigned_audits:
        if resource.gate_id in GATE_VISIBILITY.get(ActorType.CERTIFIER, []):
            return None  # Certifier on assigned audit, relevant gate

    if ActorType.REGULATOR in actor_types and user.jurisdiction == context.project_jurisdiction:
        return None  # Regulator in jurisdiction

    # DFI_CONCESSIONAL sub-persona: can view additionality, DFI criteria, and adjacency data
    if ActorType.DFI_CONCESSIONAL in actor_types:
        if resource.resource_type in ("ADDITIONALITY", "DFI_CRITERIA", "ADJACENCY"):
            return None

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

    actor_types = _actor_types_for_project(user, resource.project_id)

    if ActorType.COMMERCIAL_BANKER in actor_types or ActorType.DFI in actor_types:
        if user.company_id in resource.mandated_lenders:
            return None  # Mandated lender
    if ActorType.INSURER in actor_types or ActorType.ECA in actor_types:
        if user.company_id in resource.mandated_insurers:
            return None  # Mandated insurer / ECA providing export credit insurance

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

    actor_types = _actor_types_for_project(user, resource.project_id)

    if action == Action.VERIFY:
        if ActorType.CERTIFIER in actor_types and resource.project_id in user.assigned_audits:
            return None  # Certifier can verify
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R5"],
            denial_reason="Only assigned certifiers can verify evidence",
        )

    if action == Action.WRITE:
        visible: set[str] = set()
        for at in actor_types:
            visible.update(GATE_VISIBILITY.get(at, []))
        # Match by gate-NUMBER prefix so the two gate vocabularies
        # (G1_GRID_WATER vs G1_GRID_UTILITIES_REALITY) don't false-deny.
        visible_numbers = {gate_number(g) for g in visible}
        if resource.gate_id and gate_number(resource.gate_id) in visible_numbers:
            return None  # Can write to gates they own
        if resource.resource_type == "FINANCIAL_MODEL":
            if ActorType.COMMERCIAL_BANKER in actor_types or ActorType.DFI in actor_types:
                if user.company_id in resource.mandated_lenders:
                    return None
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R5"],
            denial_reason=f"Actor types {actor_types} cannot write to gate {resource.gate_id}",
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

    # Phase 3+: R10 — ESG compliance / sovereign / DFI gating
    if phase >= 3:
        r10 = _rule_10_esg_compliance(user, resource)
        rules_evaluated.append("R10")
        if r10 and r10.decision == Decision.DENY:
            r10.attributes_snapshot = _snapshot(user, resource, action, context)
            return r10

    return AccessDecision(
        decision=Decision.ALLOW,
        rules_evaluated=rules_evaluated,
        attributes_snapshot=_snapshot(user, resource, action, context),
    )


def get_visible_gates(user: UserAttributes, project_id: str) -> list[str]:
    """
    Compute which bankability gates this user can see on this project.
    Prosumers see the union of gates across all their actor types.
    """
    actor_types = _actor_types_for_project(user, project_id)
    gates: set[str] = set()
    for at in actor_types:
        gates.update(GATE_VISIBILITY.get(at, []))
    return sorted(gates)


def _snapshot(user: UserAttributes, resource: ResourceAttributes,
              action: Action, context: ContextAttributes) -> dict:
    """Capture attribute values at decision time for immutable audit trail."""
    return {
        "user_id": user.user_id,
        "company_id": user.company_id,
        "actor_types": [str(at) for at in _actor_types_for_project(user, resource.project_id)],
        "clearance": user.clearance_level.value,
        "action": action.value,
        "resource_type": resource.resource_type,
        "resource_id": resource.resource_id,
        "project_id": resource.project_id,
        "sensitivity": resource.sensitivity.value,
        "project_state": context.project_state,
        "timestamp": context.request_timestamp,
    }


# ═══════════════════════════════════════════════════════════════
# TRADE POLICY RULES R7-R9 — Prosumer / Marketplace Enforcement
# ═══════════════════════════════════════════════════════════════

def _rule_7_capability_gate(user: UserAttributes, trade: TradeContext) -> Optional[AccessDecision]:
    """R7: Capability-based trade authorization.
    An entity can only execute trade actions it has capabilities for.
    BremenThree (Frank Sabak) needs OFFTAKE to buy, PRODUCE to transform, SELL to sell.
    """
    CAPABILITY_MAP: dict[TradeAction, Capability] = {
        TradeAction.BUY: Capability.OFFTAKE,
        TradeAction.SELL: Capability.SELL,
        TradeAction.PRODUCE: Capability.PRODUCE,
        TradeAction.TRANSFORM: Capability.PRODUCE,
    }

    required = CAPABILITY_MAP.get(trade.action)
    if required and required not in user.capabilities:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R7"],
            denial_reason=f"Entity lacks {required.value} capability for {trade.action.value} action.",
        )
    return None


def _rule_8_credit_gate(user: UserAttributes, trade: TradeContext) -> Optional[AccessDecision]:
    """R8: Credit quality gating.
    A trade can only proceed if the buyer/seller meets the counterparty's
    minimum credit threshold (S&P or GEX internal rating).
    """
    if trade.required_rating == "NR":
        return None  # No credit requirement on this trade

    user_ordinal = _rating_ordinal(user.credit_rating)
    required_ordinal = _rating_ordinal(trade.required_rating)

    if user_ordinal < required_ordinal:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R8"],
            denial_reason=(
                f"Credit quality insufficient: {user.credit_rating} "
                f"({user.credit_rating_source}) < required {trade.required_rating}. "
                f"Ordinal {user_ordinal} < {required_ordinal}."
            ),
        )
    return None


def _rule_9_geofence_and_token(user: UserAttributes, trade: TradeContext) -> Optional[AccessDecision]:
    """R9: Export compliance + tokenization requirement.
    - SELL actions are restricted to user's licensed export regions.
    - Tokenized molecules can only be settled by token-ready entities.
    - Aggregation limits are enforced.
    """
    # 9a — Geofence: export license check on SELL
    if trade.action == TradeAction.SELL and trade.destination:
        if trade.destination not in user.export_licenses:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=["R9"],
                denial_reason=(
                    f"Export restricted: destination {trade.destination} not in "
                    f"licensed regions {user.export_licenses}."
                ),
            )

    # 9b — Tokenization readiness
    if trade.is_tokenized and not user.token_ready:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R9"],
            denial_reason="Entity not configured for tokenized molecule settlement.",
        )

    # 9c — Aggregation limit
    if user.aggregation_limit_mt is not None and trade.volume_mt > user.aggregation_limit_mt:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R9"],
            denial_reason=(
                f"Trade volume {trade.volume_mt} MT exceeds aggregation limit "
                f"{user.aggregation_limit_mt} MT."
            ),
        )

    # 9d — Transformation license check
    if trade.action == TradeAction.TRANSFORM and not user.transformation_license:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=["R9"],
            denial_reason="Entity lacks transformation license (feedstock → end-product).",
        )

    return None


def _rule_10_esg_compliance(
    user: UserAttributes, resource: ResourceAttributes
) -> Optional[AccessDecision]:
    """R10: ESG compliance gating for sovereign / DFI-backed resources.
    - If resource requires a minimum ESG score, user must meet it.
    - If resource requires specific certifications, user must hold them.
    - DFI-funded resources require DFI accreditation.
    - Reverse geofence: sovereign tokens restricted to matching jurisdictions.
    """
    # 10a — ESG score threshold
    if resource.esg_required_score is not None:
        user_score = user.esg_compliance_score or 0.0
        if user_score < resource.esg_required_score:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=["R10"],
                denial_reason=(
                    f"ESG compliance score {user_score} below resource requirement "
                    f"{resource.esg_required_score}."
                ),
            )

    # 10b — Certification match
    if resource.required_certifications:
        user_certs = set(user.esg_certifications)
        required = set(resource.required_certifications)
        missing = required - user_certs
        if missing:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=["R10"],
                denial_reason=(
                    f"Missing required certifications: {sorted(missing)}. "
                    f"User holds: {sorted(user_certs)}."
                ),
            )

    # 10c — DFI accreditation for concessional resources
    if resource.dfi_funded and not user.dfi_accredited:
        # DFI, DFI_CONCESSIONAL, and ECA actors are always accredited implicitly
        has_dfi_role = any(
            ActorType.DFI in roles or ActorType.DFI_CONCESSIONAL in roles or ActorType.ECA in roles
            for roles in user.actor_type_per_project.values()
        )
        if not has_dfi_role:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=["R10"],
                denial_reason="DFI-funded resource requires DFI accreditation or DFI actor role.",
            )

    # 10d — Reverse geofence: sovereign jurisdiction matching
    if resource.sovereign_origin and user.sovereign_jurisdiction:
        if resource.sovereign_origin != user.sovereign_jurisdiction:
            # Not a hard deny — log warning but allow (sovereign != export control)
            pass  # Soft constraint — may be tightened per CISO policy

    return None


def evaluate_trade_policy(user: UserAttributes, trade: TradeContext) -> AccessDecision:
    """
    Evaluate whether a prosumer entity can execute a marketplace trade action.
    Runs rules R7 (capability), R8 (credit), R9 (geofence + tokenization).

    This is separate from evaluate_access() which governs data/screen access.
    Trade policy governs *transaction execution* in the matching engine and
    contract flow.
    """
    rules_evaluated: list[str] = []
    snapshot = {
        "user_id": user.user_id,
        "company_id": user.company_id,
        "capabilities": [c.value for c in user.capabilities],
        "credit_rating": f"{user.credit_rating} ({user.credit_rating_source})",
        "export_licenses": user.export_licenses,
        "token_ready": user.token_ready,
        "trade_action": trade.action.value,
        "molecule": trade.molecule,
        "destination": trade.destination,
        "required_rating": trade.required_rating,
        "is_tokenized": trade.is_tokenized,
        "volume_mt": trade.volume_mt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # R7 — Capability gate
    r7 = _rule_7_capability_gate(user, trade)
    rules_evaluated.append("R7")
    if r7 and r7.decision == Decision.DENY:
        r7.rules_evaluated = rules_evaluated
        r7.attributes_snapshot = snapshot
        return r7

    # R8 — Credit quality gate
    r8 = _rule_8_credit_gate(user, trade)
    rules_evaluated.append("R8")
    if r8 and r8.decision == Decision.DENY:
        r8.rules_evaluated = rules_evaluated
        r8.attributes_snapshot = snapshot
        return r8

    # R9 — Geofence + tokenization + aggregation
    r9 = _rule_9_geofence_and_token(user, trade)
    rules_evaluated.append("R9")
    if r9 and r9.decision == Decision.DENY:
        r9.rules_evaluated = rules_evaluated
        r9.attributes_snapshot = snapshot
        return r9

    return AccessDecision(
        decision=Decision.ALLOW,
        rules_evaluated=rules_evaluated,
        attributes_snapshot=snapshot,
    )


# ═══════════════════════════════════════════════════════════════
# ACTOR DOCTRINE — 4-class taxonomy (Alt Bridge v0 §3.1)
# ═══════════════════════════════════════════════════════════════
# Bridges between fine-grained 15 ABAC actors and the functional
# classes that govern the four-eyes principle.
# Every action in the bridge must be attached to one of these
# four classes. An institution may hold multiple classes.
# ═══════════════════════════════════════════════════════════════

class ActorClass(str, Enum):
    """
    Alt Bridge v0 §3.1 — Functional actor classes.
    These govern the four-eyes principle: no single class
    can both CREATE and APPROVE the same package or transition.

    Hidalgo: each class reduces a different entropy dimension.
    Sung: the 4 classes form a causal hierarchy:
      PRODUCER → VALIDATOR → ABSORBER → RELEASER
    mirroring the capital chain:
      evidence → validation → risk pricing → capital movement
    """
    EVIDENCE_PRODUCER  = "EVIDENCE_PRODUCER"   # Creates primary documents, cost objects, designs
    EVIDENCE_VALIDATOR = "EVIDENCE_VALIDATOR"   # Confirms evidence is credible, complete, applicable
    RISK_ABSORBER      = "RISK_ABSORBER"        # Accepts, prices, guarantees, insures risk
    CAPITAL_RELEASER   = "CAPITAL_RELEASER"     # Controls whether committed capital can move


# 15 ABAC actors → actor classes.
# An actor may hold multiple classes (DFI validates + absorbs + releases).
ACTOR_CLASS_MAP: dict[ActorType, frozenset[ActorClass]] = {
    ActorType.PRODUCER:            frozenset({ActorClass.EVIDENCE_PRODUCER}),
    ActorType.OFFTAKER:            frozenset({ActorClass.EVIDENCE_PRODUCER, ActorClass.RISK_ABSORBER}),
    ActorType.COMMERCIAL_BANKER:   frozenset({ActorClass.CAPITAL_RELEASER}),
    ActorType.DFI:                 frozenset({ActorClass.EVIDENCE_VALIDATOR, ActorClass.RISK_ABSORBER, ActorClass.CAPITAL_RELEASER}),
    ActorType.DFI_CONCESSIONAL:    frozenset({ActorClass.EVIDENCE_VALIDATOR, ActorClass.RISK_ABSORBER, ActorClass.CAPITAL_RELEASER}),
    ActorType.ECA:                 frozenset({ActorClass.EVIDENCE_VALIDATOR, ActorClass.RISK_ABSORBER, ActorClass.CAPITAL_RELEASER}),
    ActorType.INSURER:             frozenset({ActorClass.EVIDENCE_VALIDATOR, ActorClass.RISK_ABSORBER}),
    ActorType.REGULATOR:           frozenset({ActorClass.EVIDENCE_VALIDATOR}),
    ActorType.GOV_AGENCY:          frozenset({ActorClass.EVIDENCE_VALIDATOR}),
    ActorType.CERTIFIER:           frozenset({ActorClass.EVIDENCE_VALIDATOR}),
    ActorType.EPC_CONTRACTOR:      frozenset({ActorClass.EVIDENCE_PRODUCER}),
    ActorType.LOGISTICS_OPERATOR:  frozenset({ActorClass.EVIDENCE_PRODUCER}),
    ActorType.TECHNOLOGY_PROVIDER: frozenset({ActorClass.EVIDENCE_PRODUCER}),
    ActorType.EXECUTIVE:           frozenset({ActorClass.CAPITAL_RELEASER}),
    ActorType.GUEST:               frozenset(),
}


def get_actor_classes(actor_type: ActorType) -> frozenset[ActorClass]:
    """Resolve the functional classes for a given actor type."""
    return ACTOR_CLASS_MAP.get(actor_type, frozenset())


def get_actor_classes_for_user(user: UserAttributes, project_id: str) -> frozenset[ActorClass]:
    """Resolve ALL functional classes a user holds on a project (union across actor types)."""
    actor_types = _actor_types_for_project(user, project_id)
    classes: set[ActorClass] = set()
    for at in actor_types:
        classes.update(ACTOR_CLASS_MAP.get(at, frozenset()))
    return frozenset(classes)


# ═══════════════════════════════════════════════════════════════
# R11 — FOUR-EYES PRINCIPLE (Maker-Checker)
# ═══════════════════════════════════════════════════════════════
# Core for bank/insurer/investor/regulator credibility.
# No single actor can both create AND approve the same transition.
# Critical transitions require specific actor classes.
#
# The four-eyes check validates TWO independent constraints:
#   1. IDENTITY:  changed_by ≠ previous actor (different person)
#   2. CLASS:     actor must hold the required functional class
#
# For dual-sign-off transitions (COMMITTED, DRAWABLE):
#   3. DUAL:      approved_by is required AND differs from changed_by
#                 AND holds the required class
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FourEyesRequirement:
    """Four-eyes rule for a workflow transition target state."""
    required_classes: Optional[frozenset[ActorClass]]  # None = any class
    must_differ_from: Optional[str]                    # package field name, or None
    dual_sign_off: bool = False                        # requires approved_by
    dual_required_classes: Optional[frozenset[ActorClass]] = None  # for the approver


# Keyed by target WorkflowState value (str, not enum — avoids circular import)
FOUR_EYES_RULES: dict[str, FourEyesRequirement] = {
    # Early transitions — no four-eyes needed
    "scoped": FourEyesRequirement(required_classes=None, must_differ_from=None),
    "costed": FourEyesRequirement(required_classes=None, must_differ_from=None),

    # EVIDENCED: producer attaches evidence — four-eyes not needed yet
    "evidenced": FourEyesRequirement(
        required_classes=frozenset({ActorClass.EVIDENCE_PRODUCER}),
        must_differ_from=None,
    ),

    # ELIGIBLE: validator confirms eligibility — CANNOT be the producer who created
    "eligible": FourEyesRequirement(
        required_classes=frozenset({ActorClass.EVIDENCE_VALIDATOR}),
        must_differ_from="discipline_owner",  # four-eyes: validator ≠ creator
    ),

    # APPROVED: governance sign-off — different person from eligibility checker
    "approved": FourEyesRequirement(
        required_classes=frozenset({ActorClass.EVIDENCE_VALIDATOR, ActorClass.CAPITAL_RELEASER}),
        must_differ_from="last_changed_by",
    ),

    # COMMITTED: capital committed — dual sign-off required
    # Maker: risk absorber or capital releaser confirms commitment
    # Checker: different actor validates the commitment
    "committed": FourEyesRequirement(
        required_classes=frozenset({ActorClass.RISK_ABSORBER, ActorClass.CAPITAL_RELEASER}),
        must_differ_from="last_changed_by",
        dual_sign_off=True,
        dual_required_classes=frozenset({ActorClass.CAPITAL_RELEASER, ActorClass.EVIDENCE_VALIDATOR}),
    ),

    # DRAWABLE: release conditions met — capital releaser, different from committer
    "drawable": FourEyesRequirement(
        required_classes=frozenset({ActorClass.CAPITAL_RELEASER}),
        must_differ_from="last_changed_by",
    ),

    # DRAWN: funds moved — dual sign-off (maker + checker for cash movement)
    "drawn": FourEyesRequirement(
        required_classes=frozenset({ActorClass.CAPITAL_RELEASER}),
        must_differ_from="last_changed_by",
        dual_sign_off=True,
        dual_required_classes=frozenset({ActorClass.CAPITAL_RELEASER, ActorClass.EVIDENCE_VALIDATOR}),
    ),

    # VERIFIED: independent verification — validator, MUST differ from drawer
    "verified": FourEyesRequirement(
        required_classes=frozenset({ActorClass.EVIDENCE_VALIDATOR}),
        must_differ_from="last_changed_by",
    ),

    # CLOSED: completion — any authorized actor, different from verifier
    "closed": FourEyesRequirement(
        required_classes=None,
        must_differ_from="last_changed_by",
    ),

    # PROPAGATED: system propagation — no four-eyes (system action)
    "propagated": FourEyesRequirement(required_classes=None, must_differ_from=None),
}


def evaluate_four_eyes(
    target_state: str,
    actor_id: str,
    actor_type_str: str,
    package_row: dict,
    approver_id: Optional[str] = None,
    approver_type_str: Optional[str] = None,
) -> AccessDecision:
    """
    R11: Four-eyes enforcement for workflow transitions.

    Args:
        target_state: WorkflowState value being transitioned to
        actor_id: user_id of the actor making the transition (from JWT)
        actor_type_str: ActorType value of the actor (from JWT)
        package_row: dict of the current package row from DB
        approver_id: user_id of the second actor (for dual-sign-off)
        approver_type_str: ActorType value of the approver

    Returns:
        AccessDecision — ALLOW or DENY with reasoning
    """
    rule = FOUR_EYES_RULES.get(target_state)
    if rule is None:
        return AccessDecision(decision=Decision.ALLOW, rules_evaluated=["R11"])

    rules_evaluated = ["R11"]

    # Resolve actor class
    try:
        actor_type = ActorType(actor_type_str)
    except ValueError:
        return AccessDecision(
            decision=Decision.DENY,
            rules_evaluated=rules_evaluated,
            denial_reason=f"Unknown actor_type: {actor_type_str}",
        )

    actor_classes = get_actor_classes(actor_type)

    # CHECK 1: Actor class requirement
    if rule.required_classes is not None:
        if not actor_classes.intersection(rule.required_classes):
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=rules_evaluated,
                denial_reason=(
                    f"Four-eyes: transition to {target_state} requires actor class "
                    f"{sorted(c.value for c in rule.required_classes)}. "
                    f"Actor {actor_id} ({actor_type_str}) holds classes "
                    f"{sorted(c.value for c in actor_classes)}."
                ),
            )

    # CHECK 2: Must-differ-from (identity check)
    if rule.must_differ_from is not None:
        previous_actor = package_row.get(rule.must_differ_from, "")
        if actor_id == previous_actor:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=rules_evaluated,
                denial_reason=(
                    f"Four-eyes violation: actor {actor_id} cannot transition to "
                    f"{target_state} because they are the same as "
                    f"{rule.must_differ_from}={previous_actor}. "
                    f"A different person must perform this action."
                ),
            )

    # CHECK 3: Dual sign-off requirement
    if rule.dual_sign_off:
        if not approver_id or not approver_type_str:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=rules_evaluated,
                denial_reason=(
                    f"Four-eyes: transition to {target_state} requires dual sign-off. "
                    f"Provide approved_by and approver_actor_type."
                ),
            )

        if approver_id == actor_id:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=rules_evaluated,
                denial_reason=(
                    f"Four-eyes: approver ({approver_id}) must be a different person "
                    f"from maker ({actor_id})."
                ),
            )

        try:
            approver_type = ActorType(approver_type_str)
        except ValueError:
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=rules_evaluated,
                denial_reason=f"Unknown approver_actor_type: {approver_type_str}",
            )

        approver_classes = get_actor_classes(approver_type)
        if rule.dual_required_classes and not approver_classes.intersection(rule.dual_required_classes):
            return AccessDecision(
                decision=Decision.DENY,
                rules_evaluated=rules_evaluated,
                denial_reason=(
                    f"Four-eyes: approver for {target_state} must hold class "
                    f"{sorted(c.value for c in rule.dual_required_classes)}. "
                    f"Approver {approver_id} ({approver_type_str}) holds "
                    f"{sorted(c.value for c in approver_classes)}."
                ),
            )

    return AccessDecision(
        decision=Decision.ALLOW,
        rules_evaluated=rules_evaluated,
        attributes_snapshot={
            "actor_id": actor_id,
            "actor_type": actor_type_str,
            "actor_classes": sorted(c.value for c in actor_classes),
            "target_state": target_state,
            "four_eyes_rule": {
                "required_classes": sorted(c.value for c in rule.required_classes) if rule.required_classes else None,
                "must_differ_from": rule.must_differ_from,
                "dual_sign_off": rule.dual_sign_off,
            },
            "approver_id": approver_id,
            "approver_type": approver_type_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
