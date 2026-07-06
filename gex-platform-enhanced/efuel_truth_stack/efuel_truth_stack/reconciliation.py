"""
reconciliation.py — cross-layer reconciliation with op-aware operators.

The spec is emphatic: equality is the WRONG operator for cash. Each constraint
declares an `op`; we implement all seven (exact / tolerance_pct / settlement_lag
/ accrual_aware / fx_normalised / net_of_retention / net_of_vat). A constraint
with no inputs available for the period is SKIPPED (passed, status="skipped") —
absence of data is not a violation.

`run_reconciliations` is the engine (build step 5): it evaluates every constraint,
appends a derived `reconciliation_result` row for each, and on failure ALSO
raises the mapped event (an `audit_event` row carrying the event_type). The
constraint -> event mapping is an implementation decision (the spec says a fail
emits an event but does not table the mapping); it is collected in
CONSTRAINT_EVENT_MAP and easy to review/adjust.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .enums import EntryType, EventType, ReconciliationOp
from .ledger import Ledger, new_entry
from .models import DrawdownRequest, ReconciliationResult
from .spec import RECON_CONSTRAINTS, StackConfig, DEFAULT_CONFIG


# ── operators: each returns (passed, detail) ─────────────────────────────────
def _op_exact(c: dict, ctx: dict, cfg: StackConfig):
    l, r = ctx["left"], ctx["right"]
    ok = abs(l - r) <= cfg.exact_epsilon
    return ok, {"left": l, "right": r, "delta": l - r}


def _op_tolerance_pct(c: dict, ctx: dict, cfg: StackConfig):
    l, r = ctx["left"], ctx["right"]
    tol = cfg.recon_tolerances_pct.get(c["id"], c.get("tol", 0.0))
    denom = max(abs(l), abs(r), 1e-12)
    ok = abs(l - r) <= (tol / 100.0) * denom
    return ok, {"left": l, "right": r, "tol_pct": tol, "rel_diff_pct": 100.0 * abs(l - r) / denom}


def _op_net_of_retention(c: dict, ctx: dict, cfg: StackConfig):
    gross, ret, paid = ctx["gross"], ctx["retention_pct"], ctx["paid"]
    expected = gross * (1.0 - ret)
    ok = abs(expected - paid) <= max(cfg.exact_epsilon, 1e-6 * abs(gross))
    return ok, {"gross": gross, "retention_pct": ret, "expected_net": expected, "paid": paid}


def _op_settlement_lag(c: dict, ctx: dict, cfg: StackConfig):
    left, right = ctx["left"], ctx["right"]  # lists of {date, amount}
    window = cfg.settlement_lag_days.get(c["id"], c.get("window_days", 0))
    sum_l, sum_r = sum(m["amount"] for m in left), sum(m["amount"] for m in right)
    amounts_ok = abs(sum_l - sum_r) <= max(cfg.exact_epsilon, 1e-6 * abs(sum_l))
    gap_days = 0
    if left and right:
        gap_days = abs((max(m["date"] for m in right) - min(m["date"] for m in left)).days)
    within = gap_days <= window
    return (amounts_ok and within), {"sum_left": sum_l, "sum_right": sum_r,
                                     "gap_days": gap_days, "window_days": window}


def _op_accrual_aware(c: dict, ctx: dict, cfg: StackConfig):
    # accrual basis: amounts must match regardless of cash timing.
    l, r = ctx["left"], ctx["right"]
    ok = abs(l - r) <= max(cfg.exact_epsilon, 1e-6 * abs(l))
    return ok, {"accrued_left": l, "settled_right": r}


def _op_fx_normalised(c: dict, ctx: dict, cfg: StackConfig):
    fx, base = ctx["fx"], ctx.get("base", "EUR")

    def norm(items):
        return sum(it["amount"] * (1.0 if it["ccy"] == base else fx[it["ccy"]]) for it in items)

    l, r = norm(ctx["left"]), norm(ctx["right"])
    ok = abs(l - r) <= max(cfg.exact_epsilon, 1e-6 * abs(l))
    return ok, {"base": base, "left_base": l, "right_base": r}


def _op_net_of_vat(c: dict, ctx: dict, cfg: StackConfig):
    gross, amount, treatment = ctx["gross"], ctx["amount"], ctx.get("vat_treatment", "net")
    vat = ctx.get("vat_rate", 0.0)
    expected = gross if treatment == "gross" else gross / (1.0 + vat)
    ok = abs(expected - amount) <= max(cfg.exact_epsilon, 1e-6 * abs(gross))
    return ok, {"treatment": treatment, "expected": expected, "amount": amount}


def _op_threshold(c: dict, ctx: dict, cfg: StackConfig):
    # left <= right (e.g. ghg_lca.g_co2e_per_mj <= configured limit). The expr is
    # a bound, not an equality — modelled as its own op (review-resolved).
    value, limit = ctx["left"], ctx["right"]
    return value <= limit, {"value": value, "threshold": limit}


_OPS = {
    ReconciliationOp.EXACT: _op_exact,
    ReconciliationOp.TOLERANCE_PCT: _op_tolerance_pct,
    ReconciliationOp.NET_OF_RETENTION: _op_net_of_retention,
    ReconciliationOp.SETTLEMENT_LAG: _op_settlement_lag,
    ReconciliationOp.ACCRUAL_AWARE: _op_accrual_aware,
    ReconciliationOp.FX_NORMALISED: _op_fx_normalised,
    ReconciliationOp.NET_OF_VAT: _op_net_of_vat,
    ReconciliationOp.THRESHOLD: _op_threshold,
}

# constraint_id -> event raised on failure. Read from the spec (each constraint
# declares its `event`); was a code-side map before the review baked it in.
CONSTRAINT_EVENT_MAP: dict[str, EventType] = {
    c["id"]: EventType(c["event"]) for c in RECON_CONSTRAINTS if c.get("event")
}


def evaluate_constraint(constraint: dict, ctx_entry: Optional[dict],
                        cfg: StackConfig = DEFAULT_CONFIG,
                        period: Optional[str] = None) -> ReconciliationResult:
    op = ReconciliationOp(constraint["op"])
    cid = constraint["id"]
    if ctx_entry is None:
        return ReconciliationResult(constraint_id=cid, op=op, passed=True,
                                    reason="skipped — no inputs for period",
                                    detail={"status": "skipped"}, period=period)
    passed, detail = _OPS[op](constraint, ctx_entry, cfg)
    reason = "ok" if passed else f"{cid} failed under op {op.value}: {detail}"
    return ReconciliationResult(
        constraint_id=cid, op=op, passed=passed, reason=reason, detail=detail,
        event_raised=None if passed else CONSTRAINT_EVENT_MAP.get(cid), period=period,
    )


# ── context extraction from drawdown + ledger ────────────────────────────────
def build_context(drawdown: DrawdownRequest, ledger: Ledger,
                  cfg: StackConfig = DEFAULT_CONFIG) -> dict[str, dict]:
    """Populate per-constraint inputs from the drawdown + ledger where derivable."""
    ctx: dict[str, dict] = {}
    draw_total = sum(drawdown.amount_by_source.values())

    # cost_basis: drawn amount == cost lines net of retention.
    if drawdown.cost_lines:
        gross = sum(cl.total_amount for cl in drawdown.cost_lines)
        # retention-weighted expected net == paid (we pass gross+weighted retention).
        net_expected = sum(cl.total_amount * (1.0 - cl.retention_pct) for cl in drawdown.cost_lines)
        weighted_ret = 0.0 if gross == 0 else 1.0 - (net_expected / gross)
        ctx["cost_basis"] = {"gross": gross, "retention_pct": weighted_ret, "paid": draw_total}

    # cash_release: drawn amount vs cash_movement rows in the period.
    cash_rows = [e for e in ledger.by_entry_type(EntryType.CASH_MOVEMENT)
                 if e.payload.get("period") == drawdown.period]
    if cash_rows:
        ctx["cash_release"] = {
            "left": [{"date": drawdown_period_date(drawdown), "amount": draw_total}],
            "right": [{"date": e.valid_from, "amount": e.payload.get("amount", 0.0)} for e in cash_rows],
        }

    # ghg_pass: latest g_co2e_per_mj measurement vs configured threshold.
    ghg_rows = [e for e in ledger.live()
                if e.payload.get("claim_type") == "g_co2e_per_mj" and "value" in e.payload]
    if ghg_rows:
        latest = sorted(ghg_rows, key=lambda e: (e.recorded_at, e.id))[-1]
        ctx["ghg_pass"] = {"left": float(latest.payload["value"]), "right": cfg.ghg_threshold_g_per_mj}

    return ctx


def drawdown_period_date(drawdown: DrawdownRequest) -> date:
    """Period 'YYYY-MM' -> first of month (date anchor for the draw)."""
    y, m = drawdown.period.split("-")[:2]
    return date(int(y), int(m), 1)


def evaluate_all(drawdown: DrawdownRequest, ledger: Ledger,
                 cfg: StackConfig = DEFAULT_CONFIG,
                 ctx: Optional[dict[str, dict]] = None) -> list[ReconciliationResult]:
    ctx = ctx if ctx is not None else build_context(drawdown, ledger, cfg)
    return [evaluate_constraint(c, ctx.get(c["id"]), cfg, drawdown.period)
            for c in RECON_CONSTRAINTS]


def run_reconciliations(drawdown: DrawdownRequest, ledger: Ledger,
                        recorded_at: datetime, cfg: StackConfig = DEFAULT_CONFIG,
                        ctx: Optional[dict[str, dict]] = None) -> list[ReconciliationResult]:
    """
    Engine: evaluate, append a reconciliation_result row per constraint, and on
    failure ALSO raise the mapped event (audit_event row). Returns the results.
    """
    results = evaluate_all(drawdown, ledger, cfg, ctx)
    for res in results:
        ledger.append(new_entry(
            project_id=drawdown.project_id, entry_type=EntryType.RECONCILIATION_RESULT,
            produced_by="system", valid_from=drawdown_period_date(drawdown),
            recorded_at=recorded_at, payload=res.model_dump(mode="json"),
        ))
        if not res.passed and res.event_raised is not None:
            ledger.append(new_entry(
                project_id=drawdown.project_id, entry_type=EntryType.AUDIT_EVENT,
                produced_by="system", valid_from=drawdown_period_date(drawdown),
                recorded_at=recorded_at,
                payload={"event_type": res.event_raised.value, "open": True,
                         "source_constraint": res.constraint_id, "period": drawdown.period},
            ))
    return results
