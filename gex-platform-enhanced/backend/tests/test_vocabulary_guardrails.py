"""
Vocabulary guardrails (ADR 2026-07-29) — CI enforcement of the semantic doctrine:

    One canonical model per concept. Familiar words at the edge.
    Every parallel vocabulary mapped, never re-invented.

A failure here is a doctrine regression, not a broken test. The fix is to
register the new state or alias in app/core/vocabulary.py — not to relax the
assertion.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.vocabulary import CONCEPTS, EVIDENCE_STATE, export, to_canonical

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"


# ── Registry integrity ────────────────────────────────────────────────────────

def test_every_canonical_value_has_label_and_description():
    """No user ever sees a raw enum name."""
    problems = []
    for name, concept in CONCEPTS.items():
        for t in concept.terms:
            if not t.label.strip():
                problems.append(f"{name}.{t.canonical}: empty label")
            if len(t.description.strip()) < 15:
                problems.append(f"{name}.{t.canonical}: description too thin")
            if not t.bucket.strip():
                problems.append(f"{name}.{t.canonical}: empty bucket")
    assert not problems, "Vocabulary entries missing presentation:\n" + "\n".join(problems)


def test_canonical_values_are_unique_within_a_concept():
    for name, concept in CONCEPTS.items():
        values = list(concept.canonical_values)
        assert len(values) == len(set(values)), f"{name}: duplicate canonical values"


def test_labels_are_human_readable():
    """Labels must not be SCREAMING_SNAKE internals leaking to the surface."""
    offenders = [
        f"{name}.{t.canonical} → {t.label!r}"
        for name, concept in CONCEPTS.items()
        for t in concept.terms
        if re.fullmatch(r"[A-Z0-9_]+", t.label)
    ]
    assert not offenders, (
        "Internal enum names used as user-facing labels (Blueprint Law 3 — "
        "familiar language):\n" + "\n".join(offenders)
    )


def test_every_crosswalk_resolves_to_a_canonical_value():
    """An alias may map to a canonical value or explicitly to None — never to a typo."""
    problems = []
    for name, concept in CONCEPTS.items():
        valid = set(concept.canonical_values)
        for vocab, mapping in concept.crosswalks.items():
            for foreign, canonical in mapping.items():
                if canonical is not None and canonical not in valid:
                    problems.append(f"{name}/{vocab}: {foreign!r} → {canonical!r} is not canonical")
    assert not problems, "Broken crosswalks:\n" + "\n".join(problems)


def test_translate_rejects_unmapped_values_loudly():
    """Silence is how a fifth vocabulary creeps back in."""
    with pytest.raises(KeyError):
        to_canonical("evidence_state", "verification.VerificationState", "NOT_A_STATE")
    with pytest.raises(KeyError):
        to_canonical("evidence_state", "some.UnregisteredVocabulary", "SUBMITTED")


# ── Coverage of the vocabularies that actually exist in the codebase ──────────

def _enum_values(path: Path, class_name: str) -> set[str]:
    """Extract the string values of a str-Enum class from source."""
    src = path.read_text()
    m = re.search(rf"class {class_name}\(.*?\):(.*?)(?=\nclass |\Z)", src, re.S)
    if not m:
        return set()
    return set(re.findall(r'^\s+[A-Z_]+\s*=\s*"([^"]+)"', m.group(1), re.M))


@pytest.mark.parametrize(
    "module,class_name,vocabulary",
    [
        ("core/verification.py", "VerificationState", "verification.VerificationState"),
        ("core/bankability_engine.py", "EvidenceStatus", "bankability.EvidenceStatus"),
    ],
)
def test_live_evidence_vocabularies_are_fully_mapped(module, class_name, vocabulary):
    """
    Every value of every parallel evidence vocabulary in the codebase must be
    mapped onto the canonical ClaimState. If someone adds a state to one of
    these enums without registering it, this fails.
    """
    values = _enum_values(APP / module, class_name)
    assert values, f"could not read {class_name} from {module}"
    mapped = set(EVIDENCE_STATE.crosswalks[vocabulary])
    missing = values - mapped
    assert not missing, (
        f"{vocabulary} has unmapped values {sorted(missing)} — register them in "
        "app/core/vocabulary.py (EVIDENCE_STATE.crosswalks)."
    )


def test_canonical_evidence_states_match_the_truth_stack():
    """The canonical list must not drift from the truth-stack ClaimState enum."""
    ts = BACKEND.parent / "efuel_truth_stack" / "efuel_truth_stack" / "enums.py"
    if not ts.exists():
        pytest.skip("truth stack not present in this checkout")
    values = _enum_values(ts, "ClaimState")
    assert values, "could not read ClaimState"
    assert set(EVIDENCE_STATE.canonical_values) == values, (
        "Canonical evidence vocabulary has drifted from the truth-stack ClaimState."
    )


def test_package_workflow_matches_the_enforced_state_machine():
    values = _enum_values(APP / "api/v1/development_packages.py", "WorkflowState")
    assert values, "could not read WorkflowState"
    assert set(CONCEPTS["package_workflow"].canonical_values) == values, (
        "package_workflow vocabulary has drifted from the server-enforced machine."
    )


def test_readiness_matches_bankability_states():
    values = _enum_values(APP / "core/bankability_engine.py", "BankabilityState")
    assert values, "could not read BankabilityState"
    assert set(CONCEPTS["readiness"].canonical_values) == values


def test_risk_categories_match_the_package_enum():
    values = _enum_values(APP / "api/v1/development_packages.py", "RiskCategory")
    assert values, "could not read RiskCategory"
    assert set(CONCEPTS["risk_category"].canonical_values) == values


# ── The registry is the ONLY home for labels ──────────────────────────────────

def test_no_competing_label_maps_in_route_modules():
    """
    Route modules must not define their own display-label dictionaries for
    domain states — they must consume the vocabulary registry.
    """
    pattern = re.compile(
        r"(DISPLAY_LABELS|STATE_LABELS|LABEL_MAP|_LABELS)\s*[:=]", re.I
    )
    offenders = []
    for f in (APP / "api").rglob("*.py"):
        if f.name == "routes_vocabulary.py":
            continue
        for m in pattern.finditer(f.read_text()):
            line = f.read_text()[: m.start()].count("\n") + 1
            offenders.append(f"{f.relative_to(BACKEND)}:{line}")
    assert not offenders, (
        "Local label maps found — labels belong in app/core/vocabulary.py:\n"
        + "\n".join(offenders)
    )


# ── Evidence consolidation invariants (ADR 2026-07-29) ────────────────────────

def test_evidence_ledger_does_not_redefine_the_assurance_enum():
    """
    The ledger used to declare its own identical copy of VerificationState.
    It must import the canonical one — one definition, one meaning.
    """
    src = (APP / "api/v1/evidence_ledger.py").read_text()
    assert "from app.core.verification import VerificationState" in src, (
        "evidence_ledger must import VerificationState, not define it"
    )
    assert not re.search(r"^class VerificationState\(", src, re.M), (
        "evidence_ledger re-declares VerificationState — the duplicate is back"
    )


def test_ledger_claim_states_match_the_canonical_vocabulary():
    values = _enum_values(APP / "api/v1/evidence_ledger.py", "ClaimState")
    assert values, "could not read ClaimState from evidence_ledger"
    assert values == set(EVIDENCE_STATE.canonical_values), (
        "the ledger's claim lifecycle has drifted from the canonical vocabulary"
    )


def test_orthogonal_axes_are_declared_and_real():
    """
    Assurance and lifecycle are two axes of one subject. The declaration exists
    so a future refactor cannot quietly merge them and lose a dimension.
    """
    from app.core.vocabulary import ORTHOGONAL_AXES, ASSURANCE_IMPLIES_CLAIM

    axes = ORTHOGONAL_AXES["evidence"]
    assert set(axes) == {"evidence_state", "evidence_assurance"}
    for concept in axes:
        assert concept in CONCEPTS, f"{concept} declared as an axis but not registered"

    # The two axes must not be the same value set — that would mean they are
    # in fact one concept and the split is fictional.
    a = set(CONCEPTS["evidence_state"].canonical_values)
    b = set(CONCEPTS["evidence_assurance"].canonical_values)
    assert a != b, "the two evidence axes have identical value sets — not orthogonal"

    # Every assurance level must state which claim state it implies.
    assert set(ASSURANCE_IMPLIES_CLAIM) == b
    assert set(ASSURANCE_IMPLIES_CLAIM.values()) <= a


def test_bankability_status_is_derivable_from_the_canonical_axes():
    """
    The fourth vocabulary is now computed, not stored, so it cannot disagree
    with the ledger. Every canonical claim state must produce a valid
    EvidenceStatus, and absence must produce NOT_STARTED.
    """
    from app.core.vocabulary import derive_bankability_status

    valid = _enum_values(APP / "core/bankability_engine.py", "EvidenceStatus")
    assert valid, "could not read EvidenceStatus"

    assert derive_bankability_status(None) == "NOT_STARTED"
    for claim in EVIDENCE_STATE.canonical_values:
        for assurance in (None, "UNVERIFIED", "SUBMITTED", "CONFIRMED", "AUDITED"):
            got = derive_bankability_status(claim, assurance)
            assert got in valid, f"{claim}/{assurance} → {got!r} is not an EvidenceStatus"

    # Expiry always wins, whatever the claim said.
    assert derive_bankability_status("verified", "AUDITED", lapsed=True) == "EXPIRED"


def test_ledger_hash_covers_state_and_actors():
    """
    F3: chain of custody without the custodian is not chain of custody.
    The digest must cover assurance, claim state, and both actors — not just
    the document reference.
    """
    from app.api.v1.evidence_ledger import _compute_hash

    base = dict(evidence_id="e1", entity_id="p1", category="TECHNICAL",
                document_ref="doc-1", prev_hash=None, timestamp="2026-07-29T00:00:00Z",
                verification_state="CONFIRMED", claim_state="verified",
                submitted_by="alice", verified_by="bob")
    original = _compute_hash(**base)

    for field, tampered in [
        ("verification_state", "AUDITED"),
        ("claim_state", "satisfied"),
        ("submitted_by", "mallory"),
        ("verified_by", "mallory"),
    ]:
        altered = _compute_hash(**{**base, field: tampered})
        assert altered != original, (
            f"tampering with {field} does not change the hash — it is outside "
            "the tamper-evident envelope"
        )


def test_export_is_json_serialisable_and_complete():
    import json

    payload = export()
    json.dumps(payload)  # must not raise
    assert set(payload["concepts"]) == set(CONCEPTS)
    for name, c in payload["concepts"].items():
        assert c["terms"], f"{name}: no terms exported"
        assert c["buckets"], f"{name}: no buckets exported"
