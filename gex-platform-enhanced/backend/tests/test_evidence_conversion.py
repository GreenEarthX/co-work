"""
Invented evidence becomes open requests for real people — the planning rules.

Pure: no database. The executor (scripts/convert_invented_evidence.py) only
carries out what plan_conversion() decides, so the decisions are tested here.
"""

from app.core.bankability_engine import (
    EVIDENCE_OWNER_FUNCTION, GATE_REGISTRY, RETIRED_EVIDENCE, resolve_assignee,
)
from app.core.evidence_conversion import REMOVED, REPLACED, REQUEST, plan_conversion

LIVE = {k for g in GATE_REGISTRY for k in g.required_evidence}
KEY_BY_OWNER = {}
for _k, _o in EVIDENCE_OWNER_FUNCTION.items():
    KEY_BY_OWNER.setdefault(_o, _k)

ACME = [
    {"user_id": "u_exec", "business_function": "EXECUTIVE"},
    {"user_id": "u_eng", "business_function": "ENGINEERING"},
    {"user_id": "u_com", "business_function": "COMMERCIAL"},
]


def _row(i, key, project="proj_a", status="VERIFIED"):
    return {"id": i, "project_id": project, "evidence_key": key, "status": status,
            "submitted_by": "demo_seed", "maturity": None}


def _plan(selected, all_rows=None, owners=None, accounts=None):
    return plan_conversion(selected, all_rows if all_rows is not None else selected,
                           owners or {"proj_a": "acme"}, accounts or {"acme": ACME},
                           LIVE, RETIRED_EVIDENCE, resolve_assignee)


# ── resolve_assignee ────────────────────────────────────────────────────────

def test_an_item_goes_to_the_account_holding_its_function():
    assert resolve_assignee(KEY_BY_OWNER["ENGINEERING"], ACME)[0] == "u_eng"
    assert resolve_assignee(KEY_BY_OWNER["SALES"], ACME)[0] == "u_com"


def test_legal_and_project_items_route_to_the_executive():
    """Accounts carry no LEGAL or PROJECT function; the executive is accountable."""
    assert resolve_assignee(KEY_BY_OWNER["LEGAL"], ACME)[0] == "u_exec"
    assert resolve_assignee(KEY_BY_OWNER["PROJECT"], ACME)[0] == "u_exec"


def test_a_missing_function_falls_back_to_the_executive_not_to_anyone():
    who, why = resolve_assignee(KEY_BY_OWNER["FINANCE"], ACME)
    assert who == "u_exec" and "no FINANCE_TREASURY account" in why


def test_no_executive_and_no_function_is_an_honest_gap():
    who, why = resolve_assignee(KEY_BY_OWNER["LEGAL"], [{"user_id": "u_com", "business_function": "COMMERCIAL"}])
    assert who is None and "no EXECUTIVE" in why


def test_the_independent_engineer_is_never_an_account_of_the_producer():
    who, why = resolve_assignee(KEY_BY_OWNER["INDEPENDENT_ENGINEER"], ACME)
    assert who is None and "external" in why


def test_assignment_is_deterministic():
    two = ACME + [{"user_id": "u_aaa", "business_function": "ENGINEERING"}]
    assert resolve_assignee(KEY_BY_OWNER["ENGINEERING"], two)[0] == "u_aaa"
    assert resolve_assignee(KEY_BY_OWNER["ENGINEERING"], list(reversed(two)))[0] == "u_aaa"


# ── plan_conversion ─────────────────────────────────────────────────────────

def test_a_live_invented_row_becomes_an_assigned_request():
    plan = _plan([_row(1, KEY_BY_OWNER["ENGINEERING"])])
    (d,) = plan.dispositions
    assert d.kind == REQUEST and d.assignee == "u_eng"
    assert not plan.new_requests


def test_a_retired_row_is_replaced_by_a_request_for_its_successor_never_relabelled():
    old = next(iter(RETIRED_EVIDENCE))
    new = RETIRED_EVIDENCE[old]["replaced_by"]
    plan = _plan([_row(1, old)])
    (d,) = plan.dispositions
    assert d.kind == REPLACED and d.replaced_by == new
    (n,) = plan.new_requests
    assert (n.project_id, n.evidence_key, n.source_row_id) == ("proj_a", new, 1)


def test_no_duplicate_request_when_the_successor_already_has_a_row():
    old = next(iter(RETIRED_EVIDENCE))
    new = RETIRED_EVIDENCE[old]["replaced_by"]
    existing = {"id": 9, "project_id": "proj_a", "evidence_key": new, "status": "SUBMITTED"}
    plan = _plan([_row(1, old)], all_rows=[_row(1, old), existing])
    assert plan.dispositions[0].kind == REPLACED and not plan.new_requests


def test_two_retired_keys_with_one_successor_create_one_request():
    by_new = {}
    for old, info in RETIRED_EVIDENCE.items():
        by_new.setdefault(info["replaced_by"], []).append(old)
    olds = next(v for v in by_new.values() if len(v) > 1)[:2]
    plan = _plan([_row(1, olds[0]), _row(2, olds[1])])
    assert plan.count(REPLACED) == 2 and len(plan.new_requests) == 1


def test_a_project_without_an_owner_has_no_one_to_ask():
    plan = _plan([_row(1, KEY_BY_OWNER["ENGINEERING"], project="default")],
                 owners={"default": None})
    assert plan.dispositions[0].kind == REMOVED and not plan.new_requests


def test_an_unknown_key_is_removed():
    plan = _plan([_row(1, "no_such_evidence_key")])
    assert plan.dispositions[0].kind == REMOVED


def test_only_selected_rows_are_touched():
    genuine = {"id": 5, "project_id": "proj_a", "evidence_key": KEY_BY_OWNER["SALES"], "status": "SUBMITTED"}
    seeded = _row(1, KEY_BY_OWNER["ENGINEERING"])
    plan = _plan([seeded], all_rows=[seeded, genuine])
    assert [d.row["id"] for d in plan.dispositions] == [1]


def test_an_owner_company_with_no_active_accounts_leaves_requests_unassigned():
    plan = _plan([_row(1, KEY_BY_OWNER["ENGINEERING"])], accounts={"acme": []})
    assert plan.dispositions[0].kind == REQUEST and plan.dispositions[0].assignee is None
