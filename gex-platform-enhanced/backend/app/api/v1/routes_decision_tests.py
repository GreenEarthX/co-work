"""
Decision tests and their attributed policy values (handoff v4, task 6).

GET /api/v1/decision-tests[?party=]  — every decision test with the policy value
in force (approved GEX default or established institution policy) or none, and
the proposed values beside it, each with party, status, context and effective
date. Screens judge a metric only against `approved`; with none they show
"no approved threshold — no pass/fail". Reference data: readable by every
signed-in caller. An unreadable registry answers 503, never an empty table.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core import decision_policy as dp

router = APIRouter(prefix="/api/v1/decision-tests", tags=["Decision tests"])


@router.get("")
def list_decision_tests(party: Optional[str] = None):
    tests = {}
    for test_id, spec in dp.DECISION_TESTS.items():
        policy = dp.resolve(spec["policy_key"], party=party)
        if policy.get("registry") in ("unavailable", "unreadable"):
            raise HTTPException(503, detail={"code": "POLICY_REGISTRY_UNAVAILABLE",
                                              "message": "The policy registry could not be read; no threshold is shown."})
        tests[test_id] = {**{k: spec[k] for k in ("label", "metric", "policy_key", "comparator", "capital_decisions")},
                          "approved": policy["approved"], "proposed": policy["proposed"]}
    return {"tests": tests, "statuses": [dp.GEX_PROPOSED, dp.GEX_DEFAULT, dp.INSTITUTION],
            "messages": dp.MESSAGES,
            "rule": "A metric is judged only against an approved value. A GEX default is never shown as a "
                    "lender's, insurer's or DFI's policy."}
