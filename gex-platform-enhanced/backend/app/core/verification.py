"""
GEX Verification State Engine — R0 (Architectural Reform v6.0)

Implements the four-level evidence verification taxonomy that underpins
all bankability scoring, IC pack export gating, and trust display.

Levels (ascending trust):
  UNVERIFIED  — uploaded or entered, no external check
  SUBMITTED   — formally submitted for review by document owner
  CONFIRMED   — named third-party has checked and confirmed
  AUDITED     — audit-grade, third-party signed with reference number

Every bankability gate score is weighted by the verification state
of its constituent evidence items (see compute_weighted_gate_score).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION STATE TAXONOMY
# ═══════════════════════════════════════════════════════════════════════════════

class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"   # weight 0.25 — document present, unchecked
    SUBMITTED  = "SUBMITTED"    # weight 0.50 — formally submitted for review
    CONFIRMED  = "CONFIRMED"    # weight 0.85 — named third-party confirmed
    AUDITED    = "AUDITED"      # weight 1.00 — audit-grade, signed + ref


VERIFICATION_WEIGHTS: dict[VerificationState, float] = {
    VerificationState.UNVERIFIED: 0.25,
    VerificationState.SUBMITTED:  0.50,
    VerificationState.CONFIRMED:  0.85,
    VerificationState.AUDITED:    1.00,
}

VERIFICATION_COLORS: dict[VerificationState, str] = {
    VerificationState.UNVERIFIED: "gray",
    VerificationState.SUBMITTED:  "amber",
    VerificationState.CONFIRMED:  "blue",
    VerificationState.AUDITED:    "green",
}

VERIFICATION_LABELS: dict[VerificationState, str] = {
    VerificationState.UNVERIFIED: "Unverified",
    VerificationState.SUBMITTED:  "Submitted",
    VerificationState.CONFIRMED:  "Confirmed",
    VerificationState.AUDITED:    "Audited",
}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANION ENUMS — supply firmness, commitment level, cert status, score basis
# ═══════════════════════════════════════════════════════════════════════════════

class OfferFirmness(str, Enum):
    INDICATIVE      = "INDICATIVE"       # no binding commitment
    HEADS_OF_TERMS  = "HEADS_OF_TERMS"   # HoT / MoU signed
    BINDING         = "BINDING"          # legally binding contract


class CommitmentLevel(str, Enum):
    MODELLED     = "MODELLED"     # financial model only, no external support
    INDICATIVE   = "INDICATIVE"   # informal indication from lender/sponsor
    TERM_SHEET   = "TERM_SHEET"   # signed term sheet
    COMMITTED    = "COMMITTED"    # commitment letter or credit approval
    DRAWN        = "DRAWN"        # funds drawn


class CertStatus(str, Enum):
    ASPIRATIONAL = "ASPIRATIONAL"  # no pathway confirmed
    APPLIED      = "APPLIED"       # application submitted to registry/authority
    ASSESSED     = "ASSESSED"      # pre-certification assessment completed
    ISSUED       = "ISSUED"        # certificate issued by competent authority


class ScoreBasis(str, Enum):
    SELF_ASSESSED  = "SELF_ASSESSED"   # project team assessment
    PEER_REVIEWED  = "PEER_REVIEWED"   # internal peer review
    IE_CONFIRMED   = "IE_CONFIRMED"    # independent engineer confirmed
    AUDITED        = "AUDITED"         # third-party audit-grade


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION RECORD — immutable audit entry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VerificationRecord:
    """Immutable. Append-only. Written to verification_log table."""
    resource_type:       str
    resource_id:         str
    previous_state:      Optional[VerificationState]
    new_state:           VerificationState
    actor_user_id:       str
    verifier_firm:       Optional[str]       # required for CONFIRMED / AUDITED
    verifier_reference:  Optional[str]       # required for AUDITED
    verifier_scope:      Optional[str]       # e.g. "FEED review", "Full audit"
    verifier_exceptions: Optional[str]       # any exceptions noted
    transitioned_at:     str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VALID STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# (from, to) → allowed
VALID_TRANSITIONS: set[tuple[Optional[VerificationState], VerificationState]] = {
    (None,                         VerificationState.UNVERIFIED),  # initial upload
    (VerificationState.UNVERIFIED, VerificationState.SUBMITTED),   # owner submits
    (VerificationState.SUBMITTED,  VerificationState.CONFIRMED),   # verifier confirms
    (VerificationState.SUBMITTED,  VerificationState.UNVERIFIED),  # rejected back
    (VerificationState.CONFIRMED,  VerificationState.AUDITED),     # audit upgrade
    (VerificationState.CONFIRMED,  VerificationState.UNVERIFIED),  # CISO force-reset
    (VerificationState.AUDITED,    VerificationState.UNVERIFIED),  # CISO force-reset only
}

# Transitions that require verifier_firm
REQUIRES_VERIFIER_FIRM: set[VerificationState] = {
    VerificationState.CONFIRMED,
    VerificationState.AUDITED,
}

# Transitions that require verifier_reference
REQUIRES_VERIFIER_REFERENCE: set[VerificationState] = {
    VerificationState.AUDITED,
}


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class VerificationError(Exception):
    pass


class VerificationEngine:
    """
    Stateless engine. Validates transitions, creates records, computes weights.
    Persistence is handled by the caller (route handler → DB).
    """

    # ── Transition validation ─────────────────────────────────────────────────

    def can_transition(
        self,
        current: Optional[VerificationState],
        target: VerificationState,
    ) -> tuple[bool, Optional[str]]:
        """Returns (allowed, error_message)."""
        if (current, target) not in VALID_TRANSITIONS:
            allowed = [t for (f, t) in VALID_TRANSITIONS if f == current]
            return False, (
                f"Invalid transition: {current} → {target}. "
                f"Allowed from {current}: {[s.value for s in allowed]}"
            )
        return True, None

    def transition(
        self,
        resource_type:      str,
        resource_id:        str,
        current_state:      Optional[VerificationState],
        target_state:       VerificationState,
        actor_user_id:      str,
        verifier_firm:      Optional[str] = None,
        verifier_reference: Optional[str] = None,
        verifier_scope:     Optional[str] = None,
        verifier_exceptions:Optional[str] = None,
    ) -> VerificationRecord:
        """
        Validate and create an immutable VerificationRecord.
        Raises VerificationError on any validation failure.
        Caller must persist the record to verification_log.
        """
        allowed, err = self.can_transition(current_state, target_state)
        if not allowed:
            raise VerificationError(err)

        if target_state in REQUIRES_VERIFIER_FIRM and not verifier_firm:
            raise VerificationError(
                f"verifier_firm is required for transition to {target_state.value}. "
                "Provide the name of the confirming organisation."
            )

        if target_state in REQUIRES_VERIFIER_REFERENCE and not verifier_reference:
            raise VerificationError(
                f"verifier_reference is required for AUDITED state. "
                "Provide the audit report reference number."
            )

        return VerificationRecord(
            resource_type=resource_type,
            resource_id=resource_id,
            previous_state=current_state,
            new_state=target_state,
            actor_user_id=actor_user_id,
            verifier_firm=verifier_firm,
            verifier_reference=verifier_reference,
            verifier_scope=verifier_scope,
            verifier_exceptions=verifier_exceptions,
        )

    # ── Score computation ─────────────────────────────────────────────────────

    def compute_weighted_gate_score(
        self,
        raw_score: float,
        evidence_states: list[VerificationState],
    ) -> float:
        """
        Effective gate score = raw_score × mean(verification_weights).

        Example:
          raw=80, states=[UNVERIFIED, UNVERIFIED, UNVERIFIED]
          → 80 × 0.25 = 20.0

          raw=80, states=[AUDITED, AUDITED, AUDITED]
          → 80 × 1.00 = 80.0

          raw=80, states=[CONFIRMED, SUBMITTED, UNVERIFIED]
          → 80 × mean(0.85, 0.50, 0.25) = 80 × 0.533 = 42.7
        """
        if not evidence_states:
            return raw_score * VERIFICATION_WEIGHTS[VerificationState.UNVERIFIED]
        weights = [VERIFICATION_WEIGHTS[s] for s in evidence_states]
        avg_weight = sum(weights) / len(weights)
        return round(raw_score * avg_weight, 2)

    def verification_summary(
        self,
        evidence_states: list[VerificationState],
    ) -> dict[str, int]:
        """Returns count per state for display in Evidence Hierarchy table."""
        summary: dict[str, int] = {s.value: 0 for s in VerificationState}
        for s in evidence_states:
            summary[s.value] += 1
        return summary

    def data_source_label(self, is_live: bool, is_demo: bool) -> str:
        """
        Returns the provenance label for the OT data provenance banner.
        Every screen consuming production data must display this.
        """
        if is_demo:
            return "DEMO — not live plant data"
        if is_live:
            return "LIVE OT"
        return "MANUAL ENTRY"


# Module-level singleton — import this in route handlers
verification_engine = VerificationEngine()
