"""
release.py — evaluate_release_predicate: the drawdown.release_predicate AND-tree.

Each of the nine checks returns a CheckResult (pass/fail + reason + the bound
approver from the spec), so a caller sees *why* a draw is not releasable — not
just a bool. `releasable` is the AND of all checks. Each check is both a logical
test AND tied to the party that must accept it (the spec's approver field).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .enums import BLOCKING_EVENTS, EntryType, EventType, FundingSourceType
from .ledger import Ledger
from .models import CheckResult, DrawdownRequest, FundingCommitment, ReleaseResult
from .projectors import fold_claims, node_is_green, rollup_nodes
from .reconciliation import evaluate_all, drawdown_period_date
from .spec import DEFAULT_CONFIG, RELEASE_CHECKS, StackConfig, cps_of_class


def open_blocking_events(ledger: Ledger, transaction_time: Optional[datetime] = None) -> list[dict]:
    """Live rows carrying an open, uncured, blocking event_type."""
    live = ledger.live(transaction_time)
    cured = {e.payload.get("cures") for e in live if e.payload.get("cures")}
    out = []
    for e in live:
        et = e.payload.get("event_type")
        if et in {b.value for b in BLOCKING_EVENTS} and e.payload.get("open", False) and e.id not in cured:
            out.append({"id": e.id, "event_type": et, "source": e.payload.get("source_constraint")})
    return out


def evaluate_release_predicate(
    drawdown: DrawdownRequest,
    ledger: Ledger,
    commitments: Optional[dict[FundingSourceType, FundingCommitment]] = None,
    config: StackConfig = DEFAULT_CONFIG,
    valid_time: Optional[date] = None,
    transaction_time: Optional[datetime] = None,
) -> ReleaseResult:
    commitments = commitments or {}
    vt = valid_time or drawdown_period_date(drawdown)
    claims = fold_claims(ledger, transaction_time, drawdown.project_id)
    nodes = rollup_nodes(claims, vt)

    def cp_ok(cp_class: str) -> tuple[bool, str]:
        missing = []
        for cp in cps_of_class(cp_class):
            node = nodes.get(cp["node"])
            if node is None or not node_is_green(node):
                missing.append(cp["id"])
        return (not missing), ("all satisfied" if not missing else f"unsatisfied: {missing}")

    # 1 + 2: CP projections
    def chk_initial():
        ok, why = cp_ok("initial")
        return ok, why

    def chk_ongoing():
        ok, why = cp_ok("ongoing")
        return ok, why

    # 3: approvals_fresh
    def chk_approvals_fresh():
        current = ledger.current_hashes(transaction_time, drawdown.project_id)
        stale = []
        for e in ledger.by_entry_type(EntryType.APPROVAL_DECISION, transaction_time, drawdown.project_id):
            for h in e.payload.get("approved_evidence_hashes", []):
                if h not in current:
                    stale.append({"approval": e.id, "stale_hash": h[:12]})
        return (not stale), ("all approvals current" if not stale else f"stale approvals: {stale}")

    # 4: evidence_backed
    def chk_evidence_backed():
        unbacked = []
        for cl in drawdown.cost_lines:
            backers = [
                e for e in ledger.by_entry_type(cl.required_evidence_type, transaction_time, drawdown.project_id)
                if e.payload.get("cost_line_id") == cl.cost_line_id
                and e.is_valid_at(vt) and e.verified_by is not None
            ]
            if not backers:
                unbacked.append(cl.cost_line_id)
        return (not unbacked), ("every cost line backed" if not unbacked else f"unbacked cost lines: {unbacked}")

    # 5: eligible_cost_balanced
    def chk_eligible_balanced():
        bad = []
        for cl in drawdown.cost_lines:
            if abs(cl.allocation_sum() - cl.total_amount) > max(config.exact_epsilon, 1e-6 * abs(cl.total_amount)):
                bad.append({"cost_line": cl.cost_line_id, "alloc": cl.allocation_sum(), "total": cl.total_amount})
        return (not bad), ("allocations balance" if not bad else f"unbalanced: {bad}")

    # 6: funding_ratio_respected
    def chk_funding_ratio():
        over = []
        for src, amt in drawdown.amount_by_source.items():
            com = commitments.get(src)
            if com is not None and amt > com.drawable_amount + config.exact_epsilon:
                over.append({"source": src.value, "draw": amt, "drawable": com.drawable_amount})
        ratio_bad = []
        if config.funding_ratios:
            total = sum(drawdown.amount_by_source.values()) or 1.0
            for src, amt in drawdown.amount_by_source.items():
                target = config.funding_ratios.get(src.value)
                if target is not None and abs((amt / total) - target) > 0.01:
                    ratio_bad.append({"source": src.value, "share": amt / total, "target": target})
        ok = not over and not ratio_bad
        return ok, ("within commitment + ratio" if ok else f"over_drawable={over} ratio={ratio_bad}")

    # 7: reconciles
    def chk_reconciles():
        results = evaluate_all(drawdown, ledger, config)
        fails = [r.constraint_id for r in results if not r.passed]
        return (not fails), ("all reconciliations pass/skip" if not fails else f"failed: {fails}")

    # 8: no_open_blocking_event
    def chk_no_blocking():
        evs = open_blocking_events(ledger, transaction_time)
        return (not evs), ("no open blocking event" if not evs else f"open: {[e['event_type'] for e in evs]}")

    # 9: account_release_authorised
    def chk_account_release():
        rows = [
            e for e in ledger.by_entry_type(EntryType.RELEASE_DECISION, transaction_time, drawdown.project_id)
            if e.payload.get("drawdown_id") == drawdown.id or e.payload.get("period") == drawdown.period
        ]
        return (bool(rows), "release decision present" if rows else "no account/security release decision")

    handlers = {
        "initial_cps_satisfied": chk_initial,
        "ongoing_cps_satisfied": chk_ongoing,
        "approvals_fresh": chk_approvals_fresh,
        "evidence_backed": chk_evidence_backed,
        "eligible_cost_balanced": chk_eligible_balanced,
        "funding_ratio_respected": chk_funding_ratio,
        "reconciles": chk_reconciles,
        "no_open_blocking_event": chk_no_blocking,
        "account_release_authorised": chk_account_release,
    }

    checks: list[CheckResult] = []
    for spec_check in RELEASE_CHECKS:
        name = spec_check["check"]
        passed, reason = handlers[name]()
        checks.append(CheckResult(check=name, passed=passed, reason=reason,
                                  approver=spec_check.get("approver", "")))

    return ReleaseResult(
        drawdown_id=drawdown.id,
        releasable=all(c.passed for c in checks),
        checks=checks,
    )
