"""
GEX Canonical Vocabulary — the single semantic registry (ADR 2026-07-29).
=========================================================================
Fixes ontology sprawl: the platform had four evidence-state vocabularies, two
readiness ladders, and internal enum names leaking into the user interface.

Doctrine — one store, one canonical model, familiar words at the edge:

  * **Canonical** values are the internal truth. They stay precise, they are what
    gets persisted, and they never change to suit a screen.
  * **Display** values are what a human reads. They follow Blueprint Law 3 —
    *familiar language, novel intelligence* — using the words developers and
    financiers already use.
  * **Bucket** values are the coarse grouping for executive summaries.
  * **Crosswalks** map every legacy/parallel vocabulary onto the canonical one,
    so a second vocabulary can never again mean "a second truth".

Entropy rule: this module is the ONLY place a user-facing label for a domain
state may be defined. No hardcoded label maps in route modules or in the
front-end — consume `GET /api/v1/vocabulary` instead. CI enforces both halves
(tests/test_vocabulary_guardrails.py): every canonical value must carry a label
and a description, and every foreign vocabulary value must resolve to a
canonical value or be explicitly declared as "no claim".

Adding a state: add it to the canonical registry here (with label + description)
in the same commit that adds it to its enum. The build fails otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Term:
    """One canonical value and how it is presented to a human."""

    canonical: str          # persisted value — the internal truth
    label: str              # what a user reads (Law 3: familiar language)
    description: str        # one plain sentence, no jargon
    bucket: str             # coarse grouping for executive/summary views
    weight: Optional[float] = None   # where the concept carries a score


@dataclass(frozen=True)
class Concept:
    """A domain concept: its canonical vocabulary plus every alias mapped onto it."""

    name: str
    canonical_source: str   # which module owns the canonical enum
    summary: str
    terms: tuple[Term, ...]
    # foreign vocabulary → {foreign value: canonical value or None}
    # None means "this value asserts no claim" (e.g. evidence that does not exist yet)
    crosswalks: dict[str, dict[str, Optional[str]]] = field(default_factory=dict)

    def term(self, canonical: str) -> Optional[Term]:
        return next((t for t in self.terms if t.canonical == canonical), None)

    @property
    def canonical_values(self) -> tuple[str, ...]:
        return tuple(t.canonical for t in self.terms)


# ── Evidence state ────────────────────────────────────────────────────────────
# Canonical: the truth-stack ClaimState. It alone has formally defined
# transitions, terminal-valid/terminal-invalid sets, and a bitemporal ledger.
# The three parallel vocabularies below are demoted to projections of it.

EVIDENCE_STATE = Concept(
    name="evidence_state",
    canonical_source="efuel_truth_stack.enums.ClaimState",
    summary="Lifecycle of an evidence item, from a bare claim to an accepted, "
            "verified artifact — or to expiry, rejection, or supersession.",
    terms=(
        Term("asserted",   "Claimed",              "Someone states this is true; nothing has been submitted yet.", "Open",     0.25),
        Term("submitted",  "Submitted for review", "The artifact has been provided and is awaiting review.",       "In review", 0.50),
        Term("verified",   "Verified",             "A named third party has checked the artifact and confirmed it.", "Verified", 0.85),
        Term("satisfied",  "Accepted",             "The requirement this evidence answers is fully met.",          "Verified",  1.00),
        Term("waived",     "Waived",               "The requirement was formally excused by an authorised approver.", "Verified", 1.00),
        Term("expired",    "Expired",              "The artifact was valid but has passed its validity date.",     "Invalid",   0.00),
        Term("rejected",   "Rejected",             "A reviewer examined the artifact and did not accept it.",      "Invalid",   0.00),
        Term("failed",     "Failed",               "The claim could not be established.",                          "Invalid",   0.00),
        Term("superseded", "Superseded",           "A newer artifact has replaced this one.",                      "Invalid",   0.00),
    ),
    crosswalks={
        # app/core/verification.py — the gate-scoring weights vocabulary
        "verification.VerificationState": {
            "UNVERIFIED": "asserted",
            "SUBMITTED":  "submitted",
            "CONFIRMED":  "verified",
            "AUDITED":    "satisfied",
        },
        # app/api/v1/evidence_ledger.py — the hash-chained custody store
        "evidence_ledger.VerificationState": {
            "UNVERIFIED": "asserted",
            "SUBMITTED":  "submitted",
            "CONFIRMED":  "verified",
            "AUDITED":    "satisfied",
        },
        # app/core/bankability_engine.py — gate evaluation
        "bankability.EvidenceStatus": {
            "NOT_STARTED":  None,          # no claim exists yet — absence, not a state
            "IN_PROGRESS":  "asserted",
            "SUBMITTED":    "submitted",
            "UNDER_REVIEW": "submitted",
            "VERIFIED":     "verified",
            "REJECTED":     "rejected",
            "EXPIRED":      "expired",
        },
    },
)


# ── Evidence assurance (SECOND AXIS — deliberately not merged) ────────────────
# Assurance answers "how well-checked is this artifact" and carries the
# gate-scoring weight. EVIDENCE_STATE above answers "what is the status of the
# assertion it supports". They are orthogonal: an artifact can be AUDITED and
# SUPERSEDED simultaneously — both true, on different axes. Collapsing them into
# one enum would destroy a real dimension, so the platform keeps two and says so.

EVIDENCE_ASSURANCE = Concept(
    name="evidence_assurance",
    canonical_source="app.core.verification.VerificationState",
    summary="How thoroughly an evidence artifact has been checked, and by whom. "
            "Drives the weight the artifact carries toward a bankability gate.",
    terms=(
        Term("UNVERIFIED", "Not yet checked",     "The document is present but nobody has reviewed it.",          "Unchecked", 0.25),
        Term("SUBMITTED",  "Submitted for review", "Formally submitted; a review is expected.",                   "In review", 0.50),
        Term("CONFIRMED",  "Third-party confirmed", "A named third party has confirmed it.",                      "Checked",   0.85),
        Term("AUDITED",    "Audit-grade",          "Signed, referenced and audit-grade.",                          "Checked",   1.00),
    ),
    crosswalks={
        # The ledger no longer defines its own copy — it imports this enum.
        # Retained so the historical alias still resolves.
        "evidence_ledger.VerificationState": {
            "UNVERIFIED": "UNVERIFIED",
            "SUBMITTED":  "SUBMITTED",
            "CONFIRMED":  "CONFIRMED",
            "AUDITED":    "AUDITED",
        },
    },
)

# The two axes are related but not interchangeable. This is the declared
# relationship: reaching an assurance level implies at least this claim state.
ASSURANCE_IMPLIES_CLAIM: dict[str, str] = {
    "UNVERIFIED": "asserted",
    "SUBMITTED":  "submitted",
    "CONFIRMED":  "verified",
    "AUDITED":    "satisfied",
}


# ── Capital package workflow ──────────────────────────────────────────────────
# Canonical: the 12-state, forward-only, server-enforced machine in
# development_packages.py. Buckets give the 8 coarse states practitioners use.

PACKAGE_WORKFLOW = Concept(
    name="package_workflow",
    canonical_source="app.api.v1.development_packages.WorkflowState",
    summary="How a capital package progresses from an idea to money drawn and "
            "its use verified. Each step removes a specific kind of uncertainty.",
    terms=(
        Term("identified",  "Proposed",            "The package has been named but not yet scoped.",                     "Proposed"),
        Term("scoped",      "Scoped",              "What the package covers is defined.",                                "Defined"),
        Term("costed",      "Costed",              "A cost estimate is attached.",                                       "Defined"),
        Term("evidenced",   "Evidenced",           "Supporting documentation is attached and linked.",                   "Reviewed"),
        Term("eligible",    "Funding-eligible",    "A funding pathway for this package has been established.",           "Reviewed"),
        Term("approved",    "Approved",            "Governance has approved the package.",                               "Approved"),
        Term("committed",   "Committed",           "Capital has been committed to the package.",                         "Funded"),
        Term("drawable",    "Ready to draw",       "Release conditions are met; funds can be drawn.",                    "Funded"),
        Term("drawn",       "Drawn",               "Funds have moved.",                                                  "Executing"),
        Term("verified",    "Use of funds verified", "Spending has been independently evidenced.",                       "Executing"),
        Term("closed",      "Closed",              "The package is complete.",                                           "Closed"),
        Term("propagated",  "Closed & propagated", "Downstream effects on other packages and gates have been applied.",  "Closed"),
    ),
    crosswalks={
        # "Capital Project Details" build spec vocabulary → canonical
        "spec.PackageStatus": {
            "Proposed":  "identified",
            "Defined":   "scoped",
            "Reviewed":  "evidenced",
            "Approved":  "approved",
            "Funded":    "committed",
            "Executing": "drawn",
            "Closed":    "closed",
            "Archived":  None,          # archival is a separate flag, not a workflow state
        },
    },
)


# ── Capital readiness ─────────────────────────────────────────────────────────
# Canonical: BankabilityState (9). Buckets are the Blueprint's 6 investor-facing
# stages. The bucket is what a developer or investor should see.

READINESS = Concept(
    name="readiness",
    canonical_source="app.core.bankability_engine.BankabilityState",
    summary="How close a project is to attracting institutional capital. "
            "Computed from validated evidence — never entered by hand.",
    terms=(
        Term("SPECULATIVE",           "Speculative",            "The project is an idea; little is established.",                  "Concept"),
        Term("TECHNICALLY_PLAUSIBLE", "Technically plausible",  "The technical concept holds up to scrutiny.",                     "Early Development"),
        Term("COMMERCIALLY_PLAUSIBLE","Commercially plausible", "There is a credible commercial case.",                            "Development"),
        Term("BUILDABLE",             "Buildable",              "Site, inputs and permits make the project physically deliverable.", "Development"),
        Term("STRUCTURALLY_BANKABLE", "Structurally bankable",  "The contract and risk structure meets lender expectations.",      "Pre-Finance"),
        Term("CREDIT_APPROVED",       "Credit approved",        "A lender's credit process has approved the project.",             "Finance Ready"),
        Term("FINANCEABLE",           "Financeable",            "The project can reach financial close.",                          "Finance Ready"),
        Term("OPERATIONAL",           "Operational",            "The plant is built and running.",                                 "Investment Secured"),
        Term("REFINANCING_ELIGIBLE",  "Refinancing eligible",   "Operating history supports refinancing on better terms.",         "Investment Secured"),
    ),
    crosswalks={
        # Blueprint stage → the FIRST canonical state of that stage (entry point)
        "blueprint.CapitalReadinessStage": {
            "Concept":            "SPECULATIVE",
            "Early Development":  "TECHNICALLY_PLAUSIBLE",
            "Development":        "COMMERCIALLY_PLAUSIBLE",
            "Pre-Finance":        "STRUCTURALLY_BANKABLE",
            "Finance Ready":      "CREDIT_APPROVED",
            "Investment Secured": "OPERATIONAL",
        },
    },
)


# ── Financing risk categories ─────────────────────────────────────────────────

RISK_CATEGORY = Concept(
    name="risk_category",
    canonical_source="app.api.v1.development_packages.RiskCategory",
    summary="The kinds of financing uncertainty a capital package can reduce.",
    terms=(
        Term("TECHNICAL",     "Technology",              "Will the process work at this scale?",                          "Delivery"),
        Term("PERMITTING",    "Permits & approvals",     "Can the project obtain and keep its permissions?",              "Delivery"),
        Term("COST",          "Cost",                    "Is the cost estimate reliable?",                                "Delivery"),
        Term("SCHEDULE",      "Schedule",                "Will the project be delivered on time?",                        "Delivery"),
        Term("EXECUTION",     "Execution",               "Can the team and contractors deliver?",                         "Delivery"),
        Term("REVENUE",       "Offtake & revenue",       "Will someone buy the product, at a price that works?",          "Commercial"),
        Term("CERTIFICATION", "Certification",           "Will the product qualify under the relevant green standard?",   "Commercial"),
        Term("LOGISTICS",     "Logistics & route to market", "Can the product physically reach its buyer?",               "Commercial"),
        Term("FINANCIAL",     "Financing",               "Can the capital structure be assembled and serviced?",          "Financial"),
        Term("INSURABILITY",  "Insurability",            "Can the risks be insured on acceptable terms?",                 "Financial"),
        Term("LEGAL",         "Legal",                   "Are the contracts and rights enforceable?",                     "Financial"),
        Term("SOVEREIGN",     "Country & sovereign",     "Is the host-country environment stable enough for lenders?",    "Financial"),
    ),
)


# ── Project phase ─────────────────────────────────────────────────────────────

PROJECT_PHASE = Concept(
    name="project_phase",
    canonical_source="app.api.v1.routes_projects (projects.phase)",
    summary="Where the physical project is in its life.",
    terms=(
        Term("development",   "Development",   "Before the final investment decision.",       "Pre-FID"),
        Term("construction",  "Construction",  "Building the plant.",                         "Post-FID"),
        Term("commissioning", "Commissioning", "Testing and starting up the plant.",          "Post-FID"),
        Term("operating",     "Operating",     "The plant is producing.",                     "Post-FID"),
    ),
)


# ── Commitment instrument ─────────────────────────────────────────────────────
# Six commitment-shaped objects accumulated in this codebase, one per conversation
# with a differently-imagined user. They are not six versions of one thing: they
# fall into TWO FAMILIES that act on entirely different parts of a financial model.
#
#   DEMAND          acts on the revenue line and its variance.
#                   Has volume, price formula, product spec, delivery conditions.
#   CAPITAL SUPPORT acts on the discount rate, debt sizing and funding stack.
#                   Has coverage %, cost in bps, tenor. Has NO volume and NO delivery.
#
# Merging them produces a table half-null for every row. The bucket is the family;
# COMMITMENT_OBJECT_ROLES below says which module owns which.

COMMITMENT_INSTRUMENT = Concept(
    name="commitment_instrument",
    canonical_source="app.core.vocabulary (family split); see COMMITMENT_OBJECT_ROLES",
    summary="What kind of promise underpins a project — either a promise to buy the "
            "product, or a promise that changes the cost or availability of capital. "
            "The two are not interchangeable and never share a schema.",
    terms=(
        # ── Demand family — creates or underwrites revenue ────────────────────
        Term("bilateral_offtake", "Bilateral offtake", "A buyer contracts directly for the product.", "Demand"),
        Term("advance_market_commitment", "Advance market commitment", "Buyers promise to purchase once the product exists.", "Demand"),
        Term("auction", "Auction", "Support is allocated by competitive bidding, H2Global-style.", "Demand"),
        Term("tender", "Tender", "A buyer solicits offers against a published specification.", "Demand"),
        Term("cfd", "Contract for difference", "The gap between a strike price and the market price is paid or reclaimed.", "Demand"),
        Term("buyer_club", "Buyer club", "Several buyers aggregate demand into one commitment.", "Demand"),
        Term("ppa", "Power purchase agreement", "A contract for electricity, usually on the input side.", "Demand"),
        Term("certification_linked_purchase", "Certification-linked purchase", "The promise to buy depends on the product earning a certificate.", "Demand"),
        # ── Capital support family — changes the cost or availability of capital ──
        Term("grant", "Grant", "Money that does not have to be repaid.", "Capital support"),
        Term("guarantee", "Guarantee", "A third party covers a defined loss if something goes wrong.", "Capital support"),
        Term("insurance", "Insurance", "A premium is paid to transfer a specific risk.", "Capital support"),
        Term("export_credit", "Export credit", "An export agency supports financing tied to its country's suppliers.", "Capital support"),
        Term("tax_credit", "Tax credit", "A reduction in tax owed, tied to production or investment.", "Capital support"),
        Term("concessional_loan", "Concessional loan", "Debt priced below market, usually from a development institution.", "Capital support"),
        Term("debt_instrument", "Debt instrument", "Borrowing raised on capital markets, including green and ESG-linked bonds.", "Capital support"),
        Term("hedge", "Hedge", "A financial contract that fixes an otherwise floating cost.", "Capital support"),
        Term("blended_finance", "Blended finance", "Concessional money is layered under commercial money to draw it in.", "Capital support"),
    ),
    crosswalks={
        # The 22 members of the built instrument registry. Note what this mapping
        # exposes: exactly ONE lands in the Demand family. The capital-support side
        # was built in depth; the demand side — the tenet — has almost no object.
        "app.core.instrument_registry.InstrumentType": {
            "CFD": "cfd",
            "OFFTAKE_GUARANTEE": "guarantee",      # a guarantee ABOUT an offtake, not an offtake
            "FX_GUARANTEE": "guarantee",
            "PRI": "insurance",
            "CAR_INSURANCE": "insurance",
            "PARTIAL_CREDIT": "guarantee",
            "TECH_GUARANTEE": "guarantee",
            "PERFORMANCE_GUARANTEE": "guarantee",
            "IRS": "hedge",
            "GCGC": "guarantee",
            "EXPORT_CREDIT": "export_credit",
            "TAX_CREDIT": "tax_credit",
            "CONCESSIONAL_LOAN": "concessional_loan",
            "GRANT": "grant",
            "GREEN_BOND": "debt_instrument",
            "ESG_LINKED_BOND": "debt_instrument",
            "SLL": "debt_instrument",
            "GREEN_REVENUE_BOND": "debt_instrument",
            "GREEN_PROJECT_BOND": "debt_instrument",
            "GREEN_SECURITIZED": "debt_instrument",
            "BLENDED_FINANCE": "blended_finance",
        },
    },
)

# Which module owns which concern. This is the answer to "there are six of these,
# which one do I use?" — the question that produced the six in the first place.
COMMITMENT_OBJECT_ROLES: dict[str, dict[str, str]] = {
    "app.core.contractual_rating_engine.OfftakeContract": {
        "family": "DEMAND",
        "role": "CANONICAL. The long-term offtake agreement — the tenet of the platform. "
                "Carries counterparty, volume, price floor, tenor, and feeds the only "
                "engine that computes whether an offtake makes a project financeable.",
        "not_for": "Capital-support instruments. It has no coverage percentage or bps cost.",
    },
    "app.core.instrument_registry.Instrument": {
        "family": "CAPITAL_SUPPORT",
        "role": "CANONICAL for guarantees, grants, ECAs, DFIs, insurance and bonds. "
                "Owns eligibility, conflicts_with and stacking/cumulation rules.",
        "not_for": "Offtake. It has no volume, no price formula and no delivery conditions.",
    },
    "app.core.css": {
        "family": "NEITHER",
        "role": "Commitment SIGNATURE service — eIDAS non-repudiation over a governance "
                "decision. 'Commitment' here means a signed record, not a market promise.",
        "not_for": "Anything to do with offtake, demand or instruments. The name collision "
                   "is the single most likely source of a wrong import in this codebase.",
    },
    "app.api.v1.contracts_sqlite": {
        "family": "NEITHER",
        "role": "Marketplace artifact produced when a match is accepted. Narrow by design.",
        "not_for": "An offtake register. It is a record that two parties agreed, not the "
                   "agreement's commercial terms.",
    },
    "app.api.v1.sovereign_instruments": {
        "family": "CAPITAL_SUPPORT",
        "role": "Sovereign-issued support instruments and their event history.",
        "not_for": "Demand-side commitments.",
    },
    "project_context.offtake_*": {
        "family": "DEMAND",
        "role": "PROJECTION ONLY. Summary fields for display and filtering.",
        "not_for": "The system of record. The canonical offtake is OfftakeContract; these "
                   "fields must be derived from it, never edited as the source.",
    },
    "app.core.open_interest": {
        "family": "DEMAND",
        "role": "PRE-CONTRACTUAL signal on the discovery board — 'I expect 50kt/yr from "
                "2030 and want a 12-year offtake'. Carries the publisher's confidentiality "
                "policy over who may see it.",
        "not_for": "An agreement. An interest is an intent to transact and binds nobody. "
                   "When terms are agreed, promote it to an OfftakeContract; do not let "
                   "the board become a shadow contract register.",
    },
}

DEMAND_FAMILY = "Demand"
CAPITAL_SUPPORT_FAMILY = "Capital support"


def commitment_family(canonical: str) -> Optional[str]:
    """Which family an instrument belongs to, or None if it is not an instrument."""
    term = COMMITMENT_INSTRUMENT.term(canonical)
    return term.bucket if term else None


# ── Registry ──────────────────────────────────────────────────────────────────

CONCEPTS: dict[str, Concept] = {
    c.name: c
    for c in (EVIDENCE_STATE, EVIDENCE_ASSURANCE, PACKAGE_WORKFLOW,
              READINESS, RISK_CATEGORY, PROJECT_PHASE, COMMITMENT_INSTRUMENT)
}

# Concepts that are two axes of one subject, declared so nobody "helpfully"
# merges them later. Key = subject, value = the concepts that describe it.
ORTHOGONAL_AXES: dict[str, tuple[str, ...]] = {
    "evidence": ("evidence_state", "evidence_assurance"),
}


# ── Lookup API ────────────────────────────────────────────────────────────────

def display_label(concept: str, canonical: str) -> str:
    """User-facing label for a canonical value. Falls back to the raw value."""
    c = CONCEPTS.get(concept)
    t = c.term(canonical) if c else None
    return t.label if t else canonical


def describe(concept: str, canonical: str) -> str:
    c = CONCEPTS.get(concept)
    t = c.term(canonical) if c else None
    return t.description if t else ""


def bucket(concept: str, canonical: str) -> str:
    """Coarse grouping — what an executive summary should show."""
    c = CONCEPTS.get(concept)
    t = c.term(canonical) if c else None
    return t.bucket if t else canonical


def to_canonical(concept: str, vocabulary: str, value: str) -> Optional[str]:
    """
    Translate a foreign/legacy vocabulary value into the canonical one.
    Returns None when the source value asserts no claim (declared in the
    crosswalk), and raises KeyError for an unknown value — silence would let a
    fifth vocabulary creep back in.
    """
    c = CONCEPTS[concept]
    cross = c.crosswalks.get(vocabulary)
    if cross is None:
        raise KeyError(f"{concept}: no crosswalk registered for {vocabulary!r}")
    if value not in cross:
        raise KeyError(
            f"{concept}/{vocabulary}: {value!r} is not mapped. Add it to "
            "app/core/vocabulary.py rather than inventing a local translation."
        )
    return cross[value]


def derive_bankability_status(
    claim_state: Optional[str],
    assurance: Optional[str] = None,
    lapsed: bool = False,
) -> str:
    """
    Bankability's EvidenceStatus as a DERIVED view of the two canonical axes
    (ADR 2026-07-29), rather than a fourth independently-maintained vocabulary.

    Gate evaluation keeps its own vocabulary at the surface — it is the language
    gate reviewers use — but that vocabulary is now computed, not stored, so it
    can never disagree with the ledger.
    """
    if claim_state is None:
        return "NOT_STARTED"
    if lapsed:
        return "EXPIRED"
    return {
        "asserted":   "IN_PROGRESS" if assurance in (None, "UNVERIFIED") else "SUBMITTED",
        "submitted":  "UNDER_REVIEW" if assurance == "SUBMITTED" else "SUBMITTED",
        "verified":   "VERIFIED",
        "satisfied":  "VERIFIED",
        "waived":     "VERIFIED",
        "rejected":   "REJECTED",
        "failed":     "REJECTED",
        "expired":    "EXPIRED",
        "superseded": "EXPIRED",
    }.get(claim_state, "NOT_STARTED")


def export() -> dict:
    """
    Whole registry as plain JSON — the payload behind GET /api/v1/vocabulary.
    The front-end renders from this; it must not carry its own label maps.
    """
    return {
        "version": "2026-07-29",
        "doctrine": (
            "Canonical values are the internal truth and are what gets stored. "
            "Labels are what users read. Buckets group states for summary views. "
            "Defined once, in app/core/vocabulary.py."
        ),
        "orthogonal_axes": {k: list(v) for k, v in ORTHOGONAL_AXES.items()},
        "assurance_implies_claim": ASSURANCE_IMPLIES_CLAIM,
        "concepts": {
            name: {
                "name": c.name,
                "canonical_source": c.canonical_source,
                "summary": c.summary,
                "terms": [
                    {
                        "canonical": t.canonical,
                        "label": t.label,
                        "description": t.description,
                        "bucket": t.bucket,
                        **({"weight": t.weight} if t.weight is not None else {}),
                    }
                    for t in c.terms
                ],
                "buckets": list(dict.fromkeys(t.bucket for t in c.terms)),
                "crosswalks": c.crosswalks,
            }
            for name, c in CONCEPTS.items()
        },
    }
