"""The hand-written enums/maps must match the JSON spec exactly (no drift)."""

from efuel_truth_stack import enums
from efuel_truth_stack.spec import SPEC


def test_enum_values_match_json():
    j = SPEC["enums"]
    assert {e.value for e in enums.LedgerKind} == set(j["ledger_kind"]["values"])
    assert {e.value for e in enums.ClaimState} == set(j["claim_state"]["values"])
    assert {e.value for e in enums.ValueType} == set(j["value_type"])
    assert {e.value for e in enums.Layer} == set(j["layer"])
    assert {e.value for e in enums.CPClass} == set(j["cp_class"])
    assert {e.value for e in enums.FundingSourceType} == set(j["funding_source_type"])
    assert {e.value for e in enums.AccountType} == set(j["account_type"])
    assert {e.value for e in enums.EventType} == set(j["event_type"])
    assert {e.value for e in enums.ApprovalOutcome} == set(j["approval_outcome"])
    assert {e.value for e in enums.ApprovalThreshold} == set(j["approval_threshold"])
    assert {e.value for e in enums.ReconciliationOp} == set(j["reconciliation_op"])


def test_entry_type_kind_mapping_matches_json():
    j = SPEC["enums"]["entry_type"]
    for kind_name in ("fact", "decision", "derived"):
        kind = enums.LedgerKind(kind_name)
        assert {e.value for e in enums.ENTRY_TYPES_BY_KIND[kind]} == set(j[kind_name])


def test_review_resolutions_baked_into_spec():
    """Decisions #2/#3/#4 resolved in the JSON (not just code)."""
    from efuel_truth_stack.enums import EventType
    from efuel_truth_stack.spec import NODES, RECON_BY_ID

    # #3: ghg_pass uses the dedicated threshold op (was exact with a <= expr)
    assert RECON_BY_ID["ghg_pass"]["op"] == "threshold"
    assert "threshold" in SPEC["enums"]["reconciliation_op"]

    # #4: every constraint declares a valid event it raises on failure
    for c in SPEC["reconciliation_constraints"]["constraints"]:
        assert EventType(c["event"])  # raises if not a valid event_type

    # #2: the four CP-referenced nodes are now defined in the JSON node sections
    for nid in ("financial_model", "no_default_cert", "kyc_aml", "state_aid_approval"):
        assert nid in NODES
    defined = set()
    for sec in ("financial_model", "public_controls"):
        for nd in SPEC.get(sec, {}).get("nodes", []):
            defined.add(nd["id"])
    assert {"financial_model", "no_default_cert", "kyc_aml", "state_aid_approval"} <= defined


def test_claim_state_transitions_match_json():
    j = SPEC["enums"]["claim_state"]
    assert {s.value for s in enums.TERMINAL_VALID} == set(j["terminal_valid"])
    assert {s.value for s in enums.TERMINAL_INVALID} == set(j["terminal_invalid"])
    for src, dsts in j["transitions"].items():
        coded = {d.value for d in enums.CLAIM_STATE_TRANSITIONS[enums.ClaimState(src)]}
        assert coded == set(dsts), f"transition mismatch for {src}"
