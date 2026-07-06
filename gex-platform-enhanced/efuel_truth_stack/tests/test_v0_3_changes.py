"""Spec v0.3 changes (CanonicalProjectLedger_Migration_v0.3 §3.1–3.6) — each
change is guarded by a test so it cannot silently drift or regress."""
from datetime import date

import pytest

from efuel_truth_stack import (
    Ledger, new_entry, utc, fold_claims, ToStateViolation, ProjectionError,
)
from efuel_truth_stack.enums import EntryType
from efuel_truth_stack.models import EvidenceLink
from efuel_truth_stack.spec import ACTORS, NODES, SPEC, WRITE_AUTHORITY

D = date(2026, 7, 1)
T = utc(2026, 7, 1)


def _writer(entry_type: EntryType) -> str:
    """An actor authorised for this entry_type (or any actor if ungated)."""
    allowed = WRITE_AUTHORITY.get(entry_type.value)
    return sorted(allowed)[0] if allowed else "system"


def _entry(entry_type: EntryType, payload: dict, *, entry_id=None, minute=0):
    return new_entry(
        project_id="P1", entry_type=entry_type, produced_by=_writer(entry_type),
        valid_from=D, recorded_at=utc(2026, 7, 1, 0, minute),
        payload=payload, entry_id=entry_id,
    )


# ── 3.1 migration_agent actor + write authority ─────────────────────────────

def test_migration_agent_is_an_actor():
    assert "migration_agent" in ACTORS


def test_migration_agent_admitted_to_every_gated_entry_type():
    assert WRITE_AUTHORITY, "expected gated entry types"
    for et, allowed in WRITE_AUTHORITY.items():
        assert "migration_agent" in allowed, f"migration_agent missing for {et}"


# ── 3.2 biofuel nodes formalised into the JSON ───────────────────────────────

BIO = ["feedstock_sustainability", "annex_ix", "land_criteria", "ghg_saving"]


def test_biofuel_nodes_in_json_spec_not_just_code():
    json_ids = {n["id"] for n in SPEC["certification"]["nodes"]}
    for nid in BIO:
        assert nid in json_ids, f"{nid} must live in the JSON spec (v0.3), not code"


def test_biofuel_nodes_in_registry_with_claims():
    for nid in BIO:
        assert nid in NODES and NODES[nid]["required_claims"], nid


# ── 3.3 no new entry types ────────────────────────────────────────────────────

def test_entry_type_count_unchanged():
    assert len(EntryType) == 18


# ── 3.4 to_state bounded at append time ──────────────────────────────────────

@pytest.mark.parametrize("terminal", ["verified", "satisfied", "waived"])
def test_fact_and_derived_entries_cannot_smuggle_terminal_state(terminal):
    lg = Ledger()
    for et in (EntryType.MEASUREMENT, EntryType.PROJECTION_SNAPSHOT):
        with pytest.raises(ToStateViolation):
            lg.append(_entry(et, {"claim_id": "c", "to_state": terminal}))


def test_non_terminal_to_state_is_allowed_on_derived():
    lg = Ledger()
    lg.append(_entry(EntryType.PROJECTION_SNAPSHOT,
                     {"claim_id": "c", "to_state": "submitted"}))
    assert fold_claims(lg)["c"].state.value == "submitted"


def test_decision_entries_may_carry_terminal_to_state():
    lg = Ledger()
    lg.append(_entry(EntryType.MEASUREMENT, {"claim_id": "c"}, minute=0))
    lg.append(_entry(EntryType.APPROVAL_DECISION,
                     {"claim_id": "c", "outcome": "approve"}, minute=1))
    lg.append(_entry(EntryType.RELEASE_DECISION,
                     {"claim_id": "c", "to_state": "satisfied"}, minute=2))
    assert fold_claims(lg)["c"].state.value == "satisfied"


# ── 3.5 release_decision → SATISFIED (the legitimate path) ───────────────────

def test_release_decision_folds_to_satisfied_without_to_state():
    lg = Ledger()
    lg.append(_entry(EntryType.MEASUREMENT, {"claim_id": "c"}, minute=0))
    lg.append(_entry(EntryType.APPROVAL_DECISION,
                     {"claim_id": "c", "outcome": "approve"}, minute=1))
    lg.append(_entry(EntryType.RELEASE_DECISION, {"claim_id": "c"}, minute=2))
    assert fold_claims(lg)["c"].state.value == "satisfied"


# ── 3.6 evidence_links: many-to-many, hash-pinned, dedup, tamper-fails ───────

def _two_claims_one_certificate():
    lg = Ledger()
    lg.append(_entry(EntryType.PROJECTION_SNAPSHOT,
                     {"claim_id": "A", "to_state": "submitted"}, minute=0))
    lg.append(_entry(EntryType.PROJECTION_SNAPSHOT,
                     {"claim_id": "B", "to_state": "submitted"}, minute=1))
    cert = _entry(EntryType.CERTIFICATE, {"claim_id": "A"}, entry_id="le_cert", minute=2)
    lg.append(cert)
    return lg, cert


def test_one_entry_backs_many_claims_via_links():
    lg, cert = _two_claims_one_certificate()
    links = [EvidenceLink(ledger_entry_id=cert.id, evidence_hash=cert.hash,
                          claim_id="B", link_type="supports")]
    claims = fold_claims(lg, evidence_links=links)
    assert any(r.ledger_entry_id == cert.id for r in claims["A"].evidence_refs)  # via payload
    assert any(r.ledger_entry_id == cert.id for r in claims["B"].evidence_refs)  # via link
    assert claims["B"].state.value == "submitted"  # links attach evidence, never move state


def test_links_deduplicate_against_payload_derived_refs():
    lg, cert = _two_claims_one_certificate()
    links = [EvidenceLink(ledger_entry_id=cert.id, evidence_hash=cert.hash,
                          claim_id="A", link_type="supports")]
    claims = fold_claims(lg, evidence_links=links)
    assert sum(1 for r in claims["A"].evidence_refs
               if r.ledger_entry_id == cert.id) == 1


def test_tampered_link_hash_fails_the_fold():
    lg, cert = _two_claims_one_certificate()
    links = [EvidenceLink(ledger_entry_id=cert.id, evidence_hash="sha256:forged",
                          claim_id="B", link_type="supports")]
    with pytest.raises(ProjectionError):
        fold_claims(lg, evidence_links=links)


# ── meta ──────────────────────────────────────────────────────────────────────

def test_spec_version_is_0_3():
    assert SPEC["meta"]["version"] == "0.3.0"
    assert SPEC["meta"]["supersedes"] == "0.2.0"
    assert "payload_conventions" in SPEC and "evidence_links" in SPEC


# ── inferred fact-floor (exposed by the 3.4 lockdown) ────────────────────────

def test_later_evidence_on_verified_claim_does_not_demote_or_crash():
    """A validity-narrowing correction (fact, no to_state) on a VERIFIED claim
    must attach evidence and apply valid_to — never demote, never raise."""
    lg = Ledger()
    lg.append(_entry(EntryType.MEASUREMENT, {"claim_id": "c"}, entry_id="le_c_01", minute=0))
    lg.append(_entry(EntryType.APPROVAL_DECISION,
                     {"claim_id": "c", "outcome": "approve"}, entry_id="le_c_02", minute=1))
    lg.append(_entry(EntryType.MEASUREMENT, {"claim_id": "c"}, entry_id="le_c_03", minute=2))
    claim = fold_claims(lg)["c"]
    assert claim.state.value == "verified"          # floor, not demotion
    assert len(claim.evidence_refs) == 2            # both facts attached


def test_explicit_to_state_submitted_after_verified_still_raises():
    """The fact-floor leniency applies ONLY to inferred targets — an explicit
    to_state keeps strict transition semantics."""
    lg = Ledger()
    lg.append(_entry(EntryType.MEASUREMENT, {"claim_id": "c"}, entry_id="le_c_01", minute=0))
    lg.append(_entry(EntryType.APPROVAL_DECISION,
                     {"claim_id": "c", "outcome": "approve"}, entry_id="le_c_02", minute=1))
    lg.append(_entry(EntryType.MEASUREMENT,
                     {"claim_id": "c", "to_state": "submitted"}, entry_id="le_c_03", minute=2))
    with pytest.raises(ProjectionError):
        fold_claims(lg)


# ── v0.3.1 rule-challenge fixes ───────────────────────────────────────────────

@pytest.mark.parametrize("demoting", ["expired", "rejected", "failed", "superseded"])
def test_facts_cannot_demote_by_explicit_to_state(demoting):
    """Fact-driven demotion was a griefing vector — lapse is modelled by
    narrowing valid_to, never by state."""
    lg = Ledger()
    with pytest.raises(ToStateViolation):
        lg.append(_entry(EntryType.MEASUREMENT,
                         {"claim_id": "c", "to_state": demoting}))


def test_decision_entries_may_demote():
    """Authorised decisions/events may still demote (e.g. drawstop expiring a claim)."""
    lg = Ledger()
    lg.append(_entry(EntryType.MEASUREMENT, {"claim_id": "c"}, entry_id="le_c_01", minute=0))
    lg.append(_entry(EntryType.APPROVAL_DECISION,
                     {"claim_id": "c", "outcome": "approve"}, entry_id="le_c_02", minute=1))
    lg.append(_entry(EntryType.DRAWSTOP,
                     {"claim_id": "c", "to_state": "expired"}, entry_id="le_c_03", minute=2))
    assert fold_claims(lg)["c"].state.value == "expired"


def test_certifier_may_write_approval_decisions():
    """Authority-inversion fix: the certifier certifies (GHG), not the IE."""
    assert "certification_body_auditor" in WRITE_AUTHORITY["approval_decision"]


def test_rejection_is_write_gated():
    """rejection was ungated — any actor could reject any claim."""
    assert "rejection" in WRITE_AUTHORITY
    assert "system" not in WRITE_AUTHORITY["rejection"]
