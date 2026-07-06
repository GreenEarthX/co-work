"""
entropy_doctrine.py
====================
GEX Platform — gex-enhanced-platform/backend/app/core/

Hidalgo Entropy-Reduction Doctrine + Sung Causal Compression
=============================================================

César Hidalgo's thesis: economic value emerges when a system accumulates
knowledge and reduces entropy (disorder, uncertainty, information asymmetry)
of a productive process.

Justin Sung's learning architecture: complex information must be compressed
into hierarchical, causally connected units — not flat lists.

Applied to the GEX Bridge:
  - Each workflow transition reduces a NAMED entropy dimension
  - Each package carries cost + evidence + capital eligibility + downstream
    effect in ONE object (causal adjacency)
  - The two-axis progression (workflow × capital) preserves information that
    a single merged axis would destroy

This module is the EXPLICIT, AUDITABLE record of the doctrine.
No hidden assumptions. Every entropy source, mechanism, and capital link
is a data structure that tests, audits, and governance reviews can inspect.

Integration:
  - development_packages.py imports ENTROPY_MAP for transition docs
  - pre_cod_metrics.py uses entropy_reduced_count() for scoring
  - abac.py references ActorClass hierarchy (PRODUCER→VALIDATOR→ABSORBER→RELEASER)
  - Evidence ledger references entropy dimensions for density scoring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
# ENTROPY SOURCES — 7 dimensions of pre-COD uncertainty (Hidalgo §2.1)
# ═══════════════════════════════════════════════════════════════════════════

class EntropySource(str, Enum):
    """
    Named entropy dimensions in greenfield project finance.
    Each maps to one or more GEX mechanisms that reduce it.
    Order is causal: earlier sources must be reduced before later ones
    become tractable (Sung: hierarchical, not flat).
    """
    PROJECT_DEFINITION   = "PROJECT_DEFINITION"    # What is being built?
    FINANCIAL_ESTIMATE   = "FINANCIAL_ESTIMATE"     # What does it cost?
    CREDIBILITY          = "CREDIBILITY"            # Can claims be verified?
    FUNDING_PATHWAY      = "FUNDING_PATHWAY"        # Who can rationally fund this?
    GOVERNANCE           = "GOVERNANCE"             # Is the decision-making process trustworthy?
    CAPITAL_COMMITMENT   = "CAPITAL_COMMITMENT"     # Is money actually committed?
    INFORMATION_SYMMETRY = "INFORMATION_SYMMETRY"   # Do all parties see the same truth?


@dataclass(frozen=True)
class EntropyMechanism:
    """
    One entropy-reduction event.
    Maps a named entropy source to the GEX mechanism that reduces it,
    the transition that triggers the reduction, and the capital link
    that becomes available when the entropy is sufficiently reduced.
    """
    source: EntropySource
    gex_mechanism: str              # Which GEX subsystem performs the reduction
    trigger_transition: str         # workflow_state transition that confirms it
    capital_unlocked: str           # What capital action becomes possible
    metric_affected: list[str]      # Pre-COD metrics impacted
    evidence_required: str          # What evidence type is consumed
    actor_class_required: str       # Which actor class must perform the action


# ═══════════════════════════════════════════════════════════════════════════
# THE ENTROPY MAP — 7 reduction events, one per entropy source
# ═══════════════════════════════════════════════════════════════════════════
# This IS the Hidalgo table. If a dimension is not here, GEX does not
# claim to reduce it. If a mechanism is not here, GEX does not use it.
# Auditors: verify that every transition in development_packages.py
# maps to exactly one row in this table.
# ═══════════════════════════════════════════════════════════════════════════

ENTROPY_MAP: list[EntropyMechanism] = [

    EntropyMechanism(
        source=EntropySource.PROJECT_DEFINITION,
        gex_mechanism="Package taxonomy (12 types) + PlantBuilder capacity model",
        trigger_transition="identified → scoped",
        capital_unlocked="DEVEX/GRANT eligibility confirmed",
        metric_affected=["ECR"],
        evidence_required="BOD, site assessment, capacity model",
        actor_class_required="EVIDENCE_PRODUCER",
    ),

    EntropyMechanism(
        source=EntropySource.FINANCIAL_ESTIMATE,
        gex_mechanism="AACE estimate class progression (5→3→1) + P10/P50/P90 range",
        trigger_transition="scoped → costed",
        capital_unlocked="Bridge/vendor finance becomes rational",
        metric_affected=["FMR", "DRE"],
        evidence_required="Cost estimate with AACE class, P10/P50/P90 range",
        actor_class_required="EVIDENCE_PRODUCER",
    ),

    EntropyMechanism(
        source=EntropySource.CREDIBILITY,
        gex_mechanism="Evidence ledger (SHA-256 hash chain) + verification state machine",
        trigger_transition="costed → evidenced",
        capital_unlocked="Evidence base sufficient for external review",
        metric_affected=["DRE", "FRI"],
        evidence_required="Independent engineer report, certification docs",
        actor_class_required="EVIDENCE_PRODUCER",
    ),

    EntropyMechanism(
        source=EntropySource.FUNDING_PATHWAY,
        gex_mechanism="Capital source eligibility (9 sources) + DFI criteria matching",
        trigger_transition="evidenced → eligible",
        capital_unlocked="Formal capital provider engagement (term sheets)",
        metric_affected=["ECR", "CLR"],
        evidence_required="Capital source validation by independent reviewer",
        actor_class_required="EVIDENCE_VALIDATOR",
    ),

    EntropyMechanism(
        source=EntropySource.GOVERNANCE,
        gex_mechanism="Four-eyes principle (R11) + actor doctrine + ABAC R0-R10",
        trigger_transition="eligible → approved",
        capital_unlocked="Governance sign-off enables commitment requests",
        metric_affected=["RAS", "TIE"],
        evidence_required="Board/IC approval, compliance sign-off",
        actor_class_required="EVIDENCE_VALIDATOR",
    ),

    EntropyMechanism(
        source=EntropySource.CAPITAL_COMMITMENT,
        gex_mechanism="Capital bridge (blended WACC, catalytic ratio) + drawdown schedule",
        trigger_transition="approved → committed",
        capital_unlocked="Binding financial commitment — CPs attach",
        metric_affected=["FMR", "RMR", "TIE"],
        evidence_required="Signed term sheet, facility agreement, commitment letter",
        actor_class_required="RISK_ABSORBER",
    ),

    EntropyMechanism(
        source=EntropySource.INFORMATION_SYMMETRY,
        gex_mechanism="Information lineage (8-source fan-out) + provenance hash chain",
        trigger_transition="closed → propagated",
        capital_unlocked="Downstream gates, metrics, and views reflect audited truth",
        metric_affected=["IRS", "SPPV"],
        evidence_required="Independent verification report, use-of-funds confirmation",
        actor_class_required="EVIDENCE_VALIDATOR",
    ),
]

# Keyed by transition string for O(1) lookup
ENTROPY_BY_TRANSITION: dict[str, EntropyMechanism] = {
    em.trigger_transition: em for em in ENTROPY_MAP
}


# ═══════════════════════════════════════════════════════════════════════════
# SUNG CAUSAL COMPRESSION — validation functions
# ═══════════════════════════════════════════════════════════════════════════
# Sung's principle: a "package" is a compressed knowledge object.
# It MUST carry cost, evidence, capital eligibility, and downstream effect
# in a single unit. If any of these is missing, the compression is broken
# and the object cannot function as a unit of capital logic.
# ═══════════════════════════════════════════════════════════════════════════

CAUSAL_REQUIRED_FIELDS = {
    "cost":       ("cost_amount",),                              # financial dimension
    "evidence":   ("risk_removed", "evidence_refs"),             # credibility dimension
    "capital":    ("capital_eligible", "capital_status"),         # funding dimension
    "downstream": ("downstream_effect",),                        # propagation dimension
}


@dataclass
class CausalValidationResult:
    """Result of checking whether a package maintains causal adjacency."""
    is_valid: bool
    missing_dimensions: list[str] = field(default_factory=list)
    score: float = 1.0    # 0.0–1.0 completeness ratio
    detail: str = ""


def validate_causal_adjacency(package_dict: dict) -> CausalValidationResult:
    """
    Sung causal compression check: does this package carry all four
    dimensions required for it to function as a single knowledge unit?

    A package with cost but no downstream_effect is an orphan.
    A package with evidence but no capital path is a dead end.

    Args:
        package_dict: dict representation of a package row

    Returns:
        CausalValidationResult with score and missing dimensions
    """
    missing = []
    for dimension, fields in CAUSAL_REQUIRED_FIELDS.items():
        for f in fields:
            val = package_dict.get(f)
            # Check for meaningful content
            if val is None:
                missing.append(f"{dimension}:{f}")
            elif isinstance(val, (list, str)):
                # JSON-stored lists come as strings from SQLite
                if isinstance(val, str):
                    try:
                        import json
                        parsed = json.loads(val)
                        if isinstance(parsed, list) and len(parsed) == 0:
                            missing.append(f"{dimension}:{f}")
                    except (ValueError, TypeError):
                        if val == "" or val == "[]":
                            missing.append(f"{dimension}:{f}")
                elif len(val) == 0:
                    missing.append(f"{dimension}:{f}")
            elif isinstance(val, (int, float)) and val == 0:
                missing.append(f"{dimension}:{f}")

    total_fields = sum(len(flds) for flds in CAUSAL_REQUIRED_FIELDS.values())
    filled = total_fields - len(missing)
    score = round(filled / total_fields, 2) if total_fields > 0 else 0.0

    return CausalValidationResult(
        is_valid=len(missing) == 0,
        missing_dimensions=missing,
        score=score,
        detail=(
            f"Package carries {filled}/{total_fields} causal dimensions. "
            + (f"Missing: {', '.join(missing)}." if missing else "Full causal adjacency.")
        ),
    )


def package_entropy_score(package_dict: dict) -> dict:
    """
    Compute the entropy-reduction contribution of a single package.

    Returns a dict with:
      - workflow_entropy_reduced: count of completed transitions (0–11)
      - capital_entropy_reduced: capital_status progression (0–5)
      - causal_completeness: Sung compression score (0.0–1.0)
      - entropy_dimensions_resolved: list of EntropySource names fully resolved
      - overall_score: weighted combination (0.0–1.0)

    Used by:
      - pre_cod_metrics.py: portfolio-level entropy score
      - evidence_ledger.py: density grid weighting
      - Executive dashboard: entropy reduction heatmap
    """
    # Workflow progression score
    workflow_order = [
        "identified", "scoped", "costed", "evidenced", "eligible",
        "approved", "committed", "drawable", "drawn", "verified",
        "closed", "propagated",
    ]
    current_state = package_dict.get("workflow_state", "identified")
    try:
        workflow_idx = workflow_order.index(current_state)
    except ValueError:
        workflow_idx = 0
    workflow_entropy = workflow_idx  # 0 for identified, 11 for propagated

    # Capital progression score
    capital_order = [
        "NOT_ELIGIBLE", "THEORETICALLY_ELIGIBLE", "INDICATED",
        "COMMITTED", "DRAWABLE", "DRAWN",
    ]
    current_capital = package_dict.get("capital_status", "NOT_ELIGIBLE")
    try:
        capital_idx = capital_order.index(current_capital)
    except ValueError:
        capital_idx = 0

    # Causal completeness
    causal = validate_causal_adjacency(package_dict)

    # Resolved entropy dimensions
    resolved = []
    for em in ENTROPY_MAP:
        parts = em.trigger_transition.split(" → ")
        if len(parts) == 2:
            target = parts[1].strip()
            target_idx = workflow_order.index(target) if target in workflow_order else 999
            if workflow_idx >= target_idx:
                resolved.append(em.source.value)

    # Weighted score: workflow 40%, capital 30%, causal 30%
    w_score = workflow_idx / max(len(workflow_order) - 1, 1)
    c_score = capital_idx / max(len(capital_order) - 1, 1)
    overall = round(0.4 * w_score + 0.3 * c_score + 0.3 * causal.score, 3)

    return {
        "workflow_entropy_reduced": workflow_entropy,
        "capital_entropy_reduced": capital_idx,
        "causal_completeness": causal.score,
        "causal_detail": causal.detail,
        "entropy_dimensions_resolved": resolved,
        "overall_score": overall,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ACTOR CAUSAL HIERARCHY (Sung: the 4 classes form a causal chain)
# ═══════════════════════════════════════════════════════════════════════════
# EVIDENCE_PRODUCER → EVIDENCE_VALIDATOR → RISK_ABSORBER → CAPITAL_RELEASER
#
# Each class can only act on output produced by the preceding class.
# A validator cannot validate their own evidence (four-eyes).
# A capital releaser cannot commit without risk absorption confirmation.
# This ordering IS the causal compression — it cannot be flattened.
# ═══════════════════════════════════════════════════════════════════════════

ACTOR_CAUSAL_ORDER = [
    "EVIDENCE_PRODUCER",
    "EVIDENCE_VALIDATOR",
    "RISK_ABSORBER",
    "CAPITAL_RELEASER",
]

# Transition windows: which workflow states each actor class can govern.
# NOTE: these are PRIMARY windows. FOUR_EYES_RULES in abac.py is the
# enforceable truth — it accepts EITHER class at some boundaries
# (e.g. committed accepts RISK_ABSORBER or CAPITAL_RELEASER).
# This map shows the DOMINANT class per window for documentation.
ACTOR_CLASS_WINDOWS: dict[str, list[str]] = {
    "EVIDENCE_PRODUCER":  ["identified", "scoped", "costed", "evidenced"],
    "EVIDENCE_VALIDATOR": ["eligible", "approved", "verified"],
    "RISK_ABSORBER":      ["committed"],              # also CAPITAL_RELEASER accepted
    "CAPITAL_RELEASER":   ["committed", "drawable", "drawn"],  # shared at committed boundary
}
