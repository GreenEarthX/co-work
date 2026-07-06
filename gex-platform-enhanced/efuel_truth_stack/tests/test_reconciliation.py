"""Reconciliation: op semantics + the engine raising mapped events on failure."""

from datetime import date

from efuel_truth_stack.enums import EntryType, EventType
from efuel_truth_stack.ledger import new_entry, utc
from efuel_truth_stack.reconciliation import (
    evaluate_constraint, run_reconciliations,
)
from efuel_truth_stack.spec import RECON_BY_ID


def test_settlement_lag_within_window_passes_outside_fails():
    c = RECON_BY_ID["cash_release"]  # op=settlement_lag, window_days=5
    draw = [{"date": date(2030, 3, 1), "amount": 900_000.0}]
    within = {"left": draw, "right": [{"date": date(2030, 3, 4), "amount": 900_000.0}]}   # +3d
    outside = {"left": draw, "right": [{"date": date(2030, 3, 12), "amount": 900_000.0}]}  # +11d
    assert evaluate_constraint(c, within).passed
    assert not evaluate_constraint(c, outside).passed


def test_net_of_retention_passes_with_epc_retention():
    c = RECON_BY_ID["cost_basis"]  # op=net_of_retention
    ok = {"gross": 1_000_000.0, "retention_pct": 0.10, "paid": 900_000.0}   # 10% held back
    bad = {"gross": 1_000_000.0, "retention_pct": 0.10, "paid": 1_000_000.0}  # paid gross -> wrong
    assert evaluate_constraint(c, ok).passed
    assert not evaluate_constraint(c, bad).passed


def test_engine_writes_results_and_raises_event_on_failure(clean):
    """A failing GHG reconciliation appends a reconciliation_result row AND an event."""
    led, dd = clean.ledger, clean.drawdown
    # supersede the (passing) GHG measurement with one above the 28.2 g/MJ limit
    ghg = [e for e in led.live() if e.payload.get("claim_type") == "g_co2e_per_mj"][0]
    led.append(new_entry(
        project_id=dd.project_id, entry_type=EntryType.MEASUREMENT, produced_by="metering_mrv_actor",
        valid_from=date(2030, 1, 1), recorded_at=utc(2030, 3, 12), supersedes=ghg.id,
        payload={"claim_type": "g_co2e_per_mj", "value": 35.0, "period": dd.period},
    ))
    n_before = len(led.entries)
    results = run_reconciliations(dd, led, recorded_at=utc(2030, 3, 13))

    ghg_res = next(r for r in results if r.constraint_id == "ghg_pass")
    assert not ghg_res.passed and ghg_res.event_raised == EventType.CERTIFICATION_FAILURE
    # a reconciliation_result row exists for every constraint, plus the raised event row
    recon_rows = [e for e in led.entries if e.entry_type == EntryType.RECONCILIATION_RESULT]
    event_rows = [e for e in led.entries if e.payload.get("event_type") == "certification_failure"]
    assert len(recon_rows) == len(results)
    assert event_rows and len(led.entries) > n_before
