"""
Decision tests and their policy values (handoff v4, task 6; JML 2026-11-17).
===========================================================================
Gates certify facts. A metric threshold is a DECISION TEST, and every threshold
is attributed to its actual policy source.

Three rules, enforced here and nowhere else:

  1. The metric is always computed. A missing APPROVED policy value blocks only
     the pass/fail judgement: the test reads "no approved threshold — no
     pass/fail", and a proposed value is shown, labelled "GEX proposed".
  2. A missing required INPUT makes the test "not assessable — required inputs
     missing". Never a pass, never a confirmed breach.
  3. A GEX value never displays as an institution's policy. Status is derived:
        proposed                                    -> GEX proposed
        approved, party GEX                         -> GEX default (approved by JML)
        approved, party an institution, referenced  -> institution policy (established)
     An approved institution value WITHOUT a reference is not established; it is
     treated as having no approved threshold.

Values come from `reference_parameter` (061 + 121). On a backend without the
registry (SQLite tests), nothing is approved, so every test reads "no approved
threshold".
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("gex.decision_policy")

GEX_PROPOSED = "GEX proposed"
GEX_DEFAULT = "GEX default (approved by JML)"
INSTITUTION = "institution policy (established, with reference)"

PASS, FAIL = "PASS", "FAIL"
NO_THRESHOLD = "NO_APPROVED_THRESHOLD"
NOT_ASSESSABLE = "NOT_ASSESSABLE"
MESSAGES = {
    NO_THRESHOLD: "no approved threshold — no pass/fail",
    NOT_ASSESSABLE: "not assessable — required inputs missing",
}

# The one table of decision tests. A metric feeds the capital decision it affects,
# never a gate (task 3). `comparator` says which side passes.
DECISION_TESTS: dict[str, dict] = {
    "DSCR_P50": {"metric": "dscr_p50", "policy_key": "dscr_floor_p50", "comparator": ">=",
                 "capital_decisions": ["SENIOR_DEBT_COMMITMENT"],
                 "label": "Base-case DSCR against the senior lender's floor"},
    "DSCR_P90": {"metric": "dscr_p90", "policy_key": "dscr_floor_p90", "comparator": ">=",
                 "capital_decisions": ["SENIOR_DEBT_COMMITMENT"],
                 "label": "Downside DSCR against the senior lender's floor"},
    "DSCR_DEFAULT": {"metric": "dscr_p90", "policy_key": "dscr_default_floor", "comparator": ">=",
                     "capital_decisions": ["SENIOR_DEBT_COMMITMENT", "DEBT_DRAWDOWN"],
                     "label": "Downside DSCR against the debt-service failure floor"},
    "DSCR_COVENANT": {"metric": "dscr", "policy_key": "dscr_covenant_floor", "comparator": ">=",
                      "capital_decisions": ["DEBT_DRAWDOWN"],
                      "label": "DSCR against the facility's covenant floor (tested after financial close)"},
    "WACC": {"metric": "wacc", "policy_key": "wacc_target_max", "comparator": "<=",
             "capital_decisions": ["PROJECT_EQUITY", "STRATEGIC_EQUITY"],
             "label": "After-tax WACC against the equity investors' ceiling"},
    "OFFTAKE_COVERAGE": {"metric": "offtake_coverage_pct", "policy_key": "offtake_coverage_min",
                         "comparator": ">=", "capital_decisions": ["SENIOR_DEBT_COMMITMENT"],
                         "label": "Recorded offtake coverage against the lender's minimum"},
    # DFI additionality (task 6): ONE input each, never the decision. The party is the DFI.
    "DFI_IRR": {"metric": "irr_without_dfi", "policy_key": "dfi_irr_hurdle", "comparator": "<=",
                "capital_decisions": ["DFI_MEZZ_GUARANTEES"],
                "label": "Engine-computed project IRR without the DFI's terms, against the DFI's hurdle "
                         "(at or below supports additionality; one input only)"},
    "DFI_CATALYTIC": {"metric": "catalytic_ratio", "policy_key": "dfi_catalytic_ratio_min", "comparator": ">=",
                      "capital_decisions": ["DFI_MEZZ_GUARANTEES"],
                      "label": "Evidenced commercial money per unit of DFI money, against the DFI's minimum"},
    "REGULATORY_PREMIUM": {"metric": "regulatory_premium", "policy_key": "regulatory_premium_max",
                           "comparator": "<=", "capital_decisions": ["PROJECT_EQUITY", "STRATEGIC_EQUITY"],
                           "label": "Jurisdiction regulatory premium against the investment-grade ceiling"},
}


def _status(row: dict) -> Optional[str]:
    party = row.get("policy_party") or "GEX"
    if row.get("state") == "proposed":
        return GEX_PROPOSED
    if row.get("state") in ("approved", "superseded"):
        if party == "GEX":
            return GEX_DEFAULT
        if row.get("policy_reference"):
            return INSTITUTION
    return None


def _attribution(row: dict) -> dict:
    try:
        context = json.loads(row["policy_context"]) if row.get("policy_context") else None
    except (TypeError, ValueError):
        context = None
    return {
        "ref_id": row.get("ref_id"),
        "value": row.get("value_base"),
        "unit": row.get("unit"),
        "status": _status(row),
        "policy_party": row.get("policy_party") or "GEX",
        "context": context,
        "effective_date": row.get("valid_from"),
        "source": row.get("source_name"),
        "source_url": row.get("source_url"),
        "policy_reference": row.get("policy_reference"),
        "note": row.get("note"),
    }


def _rows(conn, key: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM reference_parameter WHERE parameter_key = ? "
        "AND state IN ('proposed', 'approved') ORDER BY valid_from DESC, proposed_at DESC",
        (key,)).fetchall()
    return [dict(r) for r in rows]


def resolve(key: str, *, party: Optional[str] = None, as_of: Optional[str] = None,
            conn=None) -> dict:
    """The policy value for `key` (optionally one party's).

    {"approved": attribution | None, "proposed": [attribution …]}. `approved` is set
    only for a GEX default or an ESTABLISHED institution policy in force on `as_of`.
    """
    from datetime import date
    as_of = as_of or date.today().isoformat()
    try:
        from app.core.reference_registry import registry_available
        if not registry_available():
            return {"approved": None, "proposed": [], "registry": "unavailable"}
        own = conn is None
        if own:
            from app.core.db_backend import fuelref_connection
            conn = fuelref_connection()
        try:
            rows = _rows(conn, key)
        finally:
            if own:
                conn.close()
    except Exception as exc:  # noqa: BLE001 — an unreadable policy is "no approved threshold"
        logger.warning("policy %s unreadable: %s", key, exc)
        return {"approved": None, "proposed": [], "registry": "unreadable"}
    if party is not None:
        rows = [r for r in rows if (r.get("policy_party") or "GEX") == party]
    approved = next((r for r in rows if r["state"] == "approved" and str(r["valid_from"]) <= as_of
                     and _status(r) in (GEX_DEFAULT, INSTITUTION)), None)
    return {"approved": _attribution(approved) if approved else None,
            "proposed": [_attribution(r) for r in rows if r["state"] == "proposed"]}


def evaluate(test_id: str, value: Any, *, policy: Optional[dict] = None,
             party: Optional[str] = None, conn=None) -> dict:
    """One decision test. `value` None means the required input is missing."""
    spec = DECISION_TESTS[test_id]
    policy = policy if policy is not None else resolve(spec["policy_key"], party=party, conn=conn)
    approved, proposed = policy.get("approved"), policy.get("proposed") or []
    result = {
        "test": test_id, "label": spec["label"], "metric": spec["metric"], "value": value,
        "comparator": spec["comparator"], "capital_decisions": spec["capital_decisions"],
        "policy": approved, "proposed_values": proposed,
    }
    if value is None:
        return {**result, "outcome": NOT_ASSESSABLE, "message": MESSAGES[NOT_ASSESSABLE]}
    if approved is None or approved.get("value") is None:
        return {**result, "outcome": NO_THRESHOLD, "message": MESSAGES[NO_THRESHOLD]}
    threshold = float(approved["value"])
    ok = value >= threshold if spec["comparator"] == ">=" else value <= threshold
    return {**result, "outcome": PASS if ok else FAIL,
            "message": (f"{'meets' if ok else 'does not meet'} {approved['policy_party']}'s "
                        f"{threshold:g} ({approved['status']}, effective {approved['effective_date']})")}
