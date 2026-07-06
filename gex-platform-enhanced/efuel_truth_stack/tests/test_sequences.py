"""
Orchestration tests over the core — the `sequences_required` lifecycles.

These do not add any runtime; they drive the ledger through an end-to-end flow
and assert the projections / release predicate / reconciliation engine behave as
a sequence. Started with the two that most exercise the release + event loop:
  - draw_cycle:     empty -> gated -> assembled -> releasable -> reconciled clean
  - exception_cure: clean -> reconciliation fails -> event raised -> release
                    blocked -> cure (fix + close event) -> release restored
"""

from datetime import date

from efuel_truth_stack.enums import EntryType, EventType
from efuel_truth_stack.ledger import Ledger, new_entry, utc
from efuel_truth_stack.models import DrawdownRequest
from efuel_truth_stack.projectors import fold_claims, node_is_green, rollup_nodes
from efuel_truth_stack.reconciliation import run_reconciliations
from efuel_truth_stack.release import evaluate_release_predicate, open_blocking_events


def _check(res, name):
    return next(c for c in res.checks if c.check == name)


def _latest_ghg(led):
    return [e for e in led.live() if e.payload.get("claim_type") == "g_co2e_per_mj"][0]


def _set_ghg(led, project, value, *, recorded, supersedes):
    led.append(new_entry(
        project_id=project, entry_type=EntryType.MEASUREMENT, produced_by="metering_mrv_actor",
        valid_from=date(2030, 1, 1), recorded_at=recorded, supersedes=supersedes,
        payload={"claim_type": "g_co2e_per_mj", "value": value, "period": "2030-03"},
    ))


def test_draw_cycle(clean):
    """A draw is gated until every prerequisite exists, then reconciles clean."""
    # 1) the same drawdown against an EMPTY ledger is not releasable — the
    #    predicate gates missing CPs / evidence / account release.
    r0 = evaluate_release_predicate(clean.drawdown, Ledger(), clean.commitments)
    assert not r0.releasable
    gated = {c.check for c in r0.failed}
    assert {"initial_cps_satisfied", "evidence_backed", "account_release_authorised"} <= gated

    # 2) the fully assembled ledger IS releasable
    assert evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments).releasable

    # 3) run the reconciliation engine: everything passes/skips, NO event raised,
    #    a reconciliation_result row written per constraint.
    results = run_reconciliations(clean.drawdown, clean.ledger, recorded_at=utc(2030, 3, 13))
    assert all(r.passed for r in results)
    assert not open_blocking_events(clean.ledger)
    recon_rows = [e for e in clean.ledger.entries if e.entry_type == EntryType.RECONCILIATION_RESULT]
    assert len(recon_rows) == len(results)

    # 4) still releasable after reconciliation (no blocking event introduced)
    assert evaluate_release_predicate(clean.drawdown, clean.ledger, clean.commitments).releasable


def test_exception_cure(clean):
    """A failed reconciliation blocks the draw; a cure restores it."""
    led, dd, coms = clean.ledger, clean.drawdown, clean.commitments
    assert evaluate_release_predicate(dd, led, coms).releasable

    # break GHG: supersede the passing measurement (25) with a failing one (35 > 28.2)
    _set_ghg(led, dd.project_id, 35.0, recorded=utc(2030, 3, 12), supersedes=_latest_ghg(led).id)

    # engine raises the mapped blocking event (certification_failure), open
    run_reconciliations(dd, led, recorded_at=utc(2030, 3, 13))
    evs = open_blocking_events(led)
    assert any(e["event_type"] == "certification_failure" for e in evs)
    event_id = next(e["id"] for e in evs if e["event_type"] == "certification_failure")

    # release is blocked: reconciles fails AND no_open_blocking_event fails
    blocked = evaluate_release_predicate(dd, led, coms)
    assert not blocked.releasable
    assert not _check(blocked, "no_open_blocking_event").passed
    assert not _check(blocked, "reconciles").passed

    # CURE: fix the underlying fact (GHG back to 25) and close the event
    _set_ghg(led, dd.project_id, 25.0, recorded=utc(2030, 3, 14), supersedes=_latest_ghg(led).id)
    led.append(new_entry(
        project_id=dd.project_id, entry_type=EntryType.AUDIT_EVENT, produced_by="system",
        valid_from=date(2030, 1, 1), recorded_at=utc(2030, 3, 14),
        payload={"event_type": "cure", "cures": event_id, "open": False},
    ))

    # release restored: the blocking event is cured and reconciliation passes again
    assert not open_blocking_events(led)
    restored = evaluate_release_predicate(dd, led, coms)
    assert restored.releasable, [(c.check, c.reason) for c in restored.failed]


def test_certification_issuance_and_retroactive_decertification(clean):
    """
    The capability that justified the build: a GoO/PoS issued and relied on, then
    an additionality breach found AFTER sale revokes it effective the breach date.
    `as_of` (via fold transaction_time) shows the OLD belief (certified) before the
    revocation was recorded, and the NEW belief (de-certified) after — driving the
    dual clawback (revenue + grant) and blocking further draws.
    """
    led, dd, coms = clean.ledger, clean.drawdown, clean.commitments
    vt = date(2030, 3, 15)        # a valid-time within the certified window
    T1 = utc(2030, 4, 1)          # belief while certified
    T2 = utc(2030, 10, 1)         # belief after the breach is found

    # baseline: goo_pos green and a draw releasable under the T1 belief
    nodes_t1 = rollup_nodes(fold_claims(led, T1, dd.project_id), valid_time=vt)
    assert node_is_green(nodes_t1["goo_pos"])
    assert evaluate_release_predicate(dd, led, coms, valid_time=vt, transaction_time=T1).releasable

    # RETROACTIVE DE-CERT: revoke the RFNBO certificate effective the breach date,
    # recorded only at T2 (found post-sale). A correction = a new superseding row.
    goo_row = next(e for e in led.live() if e.payload.get("claim_id") == "clm_goo_pos_rfnbo_issued")
    led.append(new_entry(
        project_id=dd.project_id, entry_type=EntryType.CERTIFICATE, produced_by="certification_body_auditor",
        valid_from=date(2030, 1, 1), valid_to=date(2030, 3, 1), recorded_at=T2, supersedes=goo_row.id,
        payload={"claim_id": "clm_goo_pos_rfnbo_issued", "claim_type": "rfnbo_issued",
                 "subject_node": "goo_pos", "value_type": "boolean", "value": True,
                 # v0.3: no to_state — a validity-narrowing correction carries no
                 # state intent; the inferred fact floor leaves VERIFIED intact
                 # and _latest_valid_to applies the narrowed valid_to.
                 "reason": "additionality temporal-correlation breach found post-sale"},
    ))

    # bitemporal: OLD belief still certified at vt; NEW belief de-certified at vt
    old = rollup_nodes(fold_claims(led, T1, dd.project_id), valid_time=vt)
    new = rollup_nodes(fold_claims(led, T2, dd.project_id), valid_time=vt)
    assert node_is_green(old["goo_pos"])          # before we knew: certified
    assert not node_is_green(new["goo_pos"])       # after de-cert: revoked at vt

    # raise the retroactive_decertification event + DUAL clawback (revenue + grant)
    decert = led.append(new_entry(
        project_id=dd.project_id, entry_type=EntryType.AUDIT_EVENT, produced_by="system",
        valid_from=date(2030, 1, 1), recorded_at=T2,
        payload={"event_type": "retroactive_decertification", "open": True,
                 "decertified_from": "2030-03-01"},
    ))
    for authority, stream in (("facility_agent", "revenue"), ("grant_authority", "grant")):
        led.append(new_entry(
            project_id=dd.project_id, entry_type=EntryType.CLAWBACK_NOTICE, produced_by=authority,
            valid_from=date(2030, 1, 1), recorded_at=T2,
            payload={"event_type": "clawback", "basis": "retroactive_decertification", "stream": stream},
        ))

    # consequence: a draw under the NEW belief is blocked — cert CP fails + open de-cert event
    blocked = evaluate_release_predicate(dd, led, coms, valid_time=vt, transaction_time=T2)
    assert not blocked.releasable
    assert not _check(blocked, "ongoing_cps_satisfied").passed     # cp_cert_valid (goo_pos)
    assert not _check(blocked, "no_open_blocking_event").passed    # retroactive_decertification open
    streams = {e.payload["stream"] for e in led.live() if e.entry_type == EntryType.CLAWBACK_NOTICE}
    assert streams == {"revenue", "grant"}                          # dual clawback recorded


def test_revenue_collection_waterfall():
    """Post-COD: revenue/opex/debt-service reconciliations; a coverage shortfall raises default."""
    op = DrawdownRequest(id="op1", project_id="P", period="2031-06", amount_by_source={})
    led = Ledger()
    ctx_ok = {
        "revenue_to_cash": {"left": 1_000_000.0, "right": 1_000_000.0},        # accrual_aware
        "power_cost_to_opex": {"left": 200_000.0, "right": 200_000.0},          # accrual_aware
        "debt_service_to_waterfall": {"left": 500_000.0, "right": 500_000.0},   # exact
    }
    results = run_reconciliations(op, led, recorded_at=utc(2031, 7, 1), ctx=ctx_ok)
    assert all(r.passed for r in results)
    assert not open_blocking_events(led)

    # shortfall: scheduled debt service > waterfall coverage -> default event
    led2 = Ledger()
    ctx_bad = dict(ctx_ok, debt_service_to_waterfall={"left": 500_000.0, "right": 450_000.0})
    res2 = run_reconciliations(op, led2, recorded_at=utc(2031, 7, 1), ctx=ctx_bad)
    dsw = next(r for r in res2 if r.constraint_id == "debt_service_to_waterfall")
    assert not dsw.passed and dsw.event_raised == EventType.DEFAULT
    assert any(e["event_type"] == "default" for e in open_blocking_events(led2))


def test_operations_reporting_cycle(clean):
    """Ongoing CPs are re-tested each period; a model drift breaches lock-up (drawstop)."""
    led, dd, coms = clean.ledger, clean.drawdown, clean.commitments
    # period P1: ongoing CPs all green
    assert evaluate_release_predicate(dd, led, coms).releasable

    # P2 re-test: an ongoing CP lapses (insurance expires) -> ongoing CPs fail.
    # v0.3.1: lapse = validity-narrowing correction (fact), not a state demotion.
    led.append(new_entry(project_id=dd.project_id, entry_type=EntryType.CONTRACT, produced_by="insurer",
                         valid_from=date(2030, 1, 1), valid_to=date(2030, 3, 1),
                         recorded_at=utc(2030, 4, 1),
                         payload={"claim_id": "clm_insurance_car_dsu_current",
                                  "reason": "CAR/DSU cover lapsed"}))
    res = evaluate_release_predicate(dd, led, coms)
    assert not res.releasable and not _check(res, "ongoing_cps_satisfied").passed

    # model_actuals: within the 1% tolerance passes; a >1% drift breaches lock-up (drawstop)
    rep = DrawdownRequest(id="rep", project_id="P", period="2031-06", amount_by_source={})
    ok = run_reconciliations(drawdown=rep, ledger=Ledger(), recorded_at=utc(2031, 7, 1),
                             ctx={"model_actuals": {"left": 1_000_000.0, "right": 1_005_000.0}})  # 0.5%
    assert next(r for r in ok if r.constraint_id == "model_actuals").passed
    led4 = Ledger()
    bad = run_reconciliations(rep, led4, recorded_at=utc(2031, 7, 1),
                              ctx={"model_actuals": {"left": 1_000_000.0, "right": 1_050_000.0}})  # 5%
    ma = next(r for r in bad if r.constraint_id == "model_actuals")
    assert not ma.passed and ma.event_raised == EventType.DRAWSTOP
    assert any(e["event_type"] == "drawstop" for e in open_blocking_events(led4))
