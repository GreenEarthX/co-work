"""The TEA run report (20 Nov 2026): a fixed reference, the inputs check, results recorded with the run.

No database: core/tea_report is pure apart from its two readers, which these tests replace.
"""
from __future__ import annotations

import asyncio
import copy

import pytest
from fastapi import HTTPException

from app.core import tea_report as tr

BASE = {
    "claim_id": "CLM-MBC-61f3a1083e", "project_id": "p", "cost_basis_version_id": "cb2",
    "cost_basis_sha256": "abc", "engine": "openpytea", "engine_version": "3.1.0",
    "cost_basis_hash": "sha256:x", "capex_eur": 182_840_000.0, "opex_eur_per_year": 21_000_000.0,
    "lcop": 2.365, "result_status": "SCREENING", "nameplate_capacity": 50_000, "nameplate_unit": "t_per_year",
    "created_at": "2026-11-20T14:00:00+00:00", "run_by": "u1", "state": "submitted",
    "tea_inputs": {"request": {"cepci_forward": {"2026": {"ref_id": "fwd2026", "value": 834.6}},
                               "fx_benchmark_ref_id": "fx1"},
                   "analysis": {"lcop": 2.365}},
}
CBS = [{"version_id": "cb1", "version_number": 1}, {"version_id": "cb2", "version_number": 2}]


def test_the_reference_is_fixed_by_the_stored_figures_not_by_the_review():
    ref = tr.report_ref(BASE)
    assert ref["ref"].startswith("GEX-TEA-61f3a1083e-") and len(ref["sha256"]) == 64
    reviewed = {**BASE, "state": "verified", "approved_by": "ie", "reconciliation": [1, 2]}
    assert tr.report_ref(reviewed) == ref                       # a review changes reliance, not figures
    moved = copy.deepcopy(BASE)
    moved["tea_inputs"]["analysis"]["lcop"] = 2.366
    assert tr.report_ref(moved)["ref"] != ref["ref"]            # a different figure never shares a reference
    assert tr.report_ref({**BASE, "capex_eur": 182_840_001.0})["ref"] != ref["ref"]


def test_inputs_unchanged_only_when_every_check_is_the_same():
    s = tr.inputs_status(BASE, CBS, {"fwd2026": "approved", "fx1": "approved"}, "3.1.0")
    assert s["unchanged"] is True and {c["result"] for c in s["checks"]} == {"SAME"}
    assert [c["check"] for c in s["checks"]] == ["cost basis", "CEPCI forward 2026", "FX benchmark", "engine"]


@pytest.mark.parametrize("cbs, states, engine, check", [
    (CBS + [{"version_id": "cb3", "version_number": 3}], {"fwd2026": "approved", "fx1": "approved"}, "3.1.0", "cost basis"),
    (CBS, {"fwd2026": "superseded", "fx1": "approved"}, "3.1.0", "CEPCI forward 2026"),
    (CBS, {"fwd2026": "approved", "fx1": "approved"}, "3.2.3", "engine"),
])
def test_each_change_is_named(cbs, states, engine, check):
    s = tr.inputs_status(BASE, cbs, states, engine)
    assert s["unchanged"] is False
    assert [c["check"] for c in s["checks"] if c["result"] == "CHANGED"] == [check]


def test_what_was_not_checked_is_never_reported_as_unchanged():
    s = tr.inputs_status(BASE, CBS, {"fwd2026": "approved"}, None)
    assert s["unchanged"] is None
    assert {c["check"] for c in s["checks"] if c["result"] == "NOT_CHECKED"} == {"FX benchmark", "engine"}


def test_the_results_are_recorded_with_the_run_and_a_failed_part_says_why(monkeypatch):
    from app.api.v1 import routes_tea as rt
    seen = []

    async def fake(path, payload, auth):
        seen.append(path)
        if path == "/index-band":
            raise HTTPException(422, "No published CEPCI for 2027")
        return {"tornado": [{"parameter": "discount_rate"}], "run_evidence": {"x": 1}}

    monkeypatch.setattr(rt, "_call_tea", fake)
    out = asyncio.run(rt._analysis({"p": 1}, None, {"breakdown": {"per_kg": {}}, "cost_basis": {"cost_year": 2026},
                                                    "engine_version": "3.1.0", "lcop": 2.0}))
    assert seen == ["/sensitivity", "/index-band"]
    assert out["breakdown"] == {"per_kg": {}} and out["cost_basis"]["cost_year"] == 2026
    assert out["sensitivity"]["tornado"] and "run_evidence" not in out["sensitivity"]
    assert "2027" in out["index_band"]["error"]


def test_the_chain_route_reads_the_chain_and_carries_the_report():
    """A helper placed under the route decorator once bound GET /calculation-chain/{p} to it (422)."""
    from app.api.v1 import routes_calculation_chain as rc
    route = next(r for r in rc.chain_router.routes if r.path.endswith("/{project_id}") and "GET" in r.methods)
    assert route.endpoint is rc.read_chain
    import inspect
    assert "_report_status(bases, cbs)" in inspect.getsource(rc.read_chain)
