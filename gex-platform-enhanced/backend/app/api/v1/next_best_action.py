"""
GEX Platform — Next-Best-Action Engine
=======================================
The operative nudge: not "this is locked" but "verifying THIS claim unlocks
THAT capital, THIS much sooner." Closes the loop the entropy doctrine declares:
each recommended action names the entropy dimension it collapses and the capital
it un-blocks.

Composes ONLY data that already exists:
  · pathway_claims + model_base_case  (routes_tea.py tables — claim states)
  · drawdown_schedules                (drawdown_schedule.py — capital at stake)
  · the regime fork                   (tea_engine :8002 /tea/regime/{fuel},
                                       static fallback if the engine is down)

Value scoring is an explicitly-labeled HEURISTIC (delay cost = amount ×
discount_rate/12 per month), not a valuation. Every action carries its basis.

Mount in main.py:
    from app.api.v1.next_best_action import router as nba_router
    app.include_router(nba_router, prefix="/api/v1/nba", tags=["Next Best Action"])
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends

from app.core.config import settings

router = APIRouter()
DB_PATH = settings.SQLITE_DB_PATH
TEA_ENGINE_URL = os.getenv("TEA_ENGINE_URL", "http://localhost:8002")

TERMINAL_VALID = {"verified", "satisfied", "waived"}
DEFAULT_DISCOUNT_RATE = 0.08

# Static fallback mirror of tea_engine/regimes.py (used only if :8002 is down —
# marked in the response so the caller knows which source answered).
_FALLBACK_CERT_CLAIMS = {
    "RFNBO": ["additionality_passed", "temporal_correlation", "geo_correlation",
              "hourly_matched_mwh", "rfnbo_issued", "g_co2e_per_mj"],
    "ADVANCED_BIOFUEL": ["feedstock_sustainability", "chain_of_custody", "annex_ix_class",
                         "land_criteria", "ghg_saving", "g_co2e_per_mj"],
}
_FALLBACK_FUEL_CLASS = {"E_METHANOL": "RFNBO", "E_METHANE": "RFNBO", "E_SAF": "RFNBO",
                        "GREEN_H2": "RFNBO", "E_AMMONIA": "RFNBO",
                        "BIO_SAF_HEFA": "ADVANCED_BIOFUEL"}


def get_db():
    # check_same_thread=False: the async endpoint uses this connection on the
    # event loop while the dependency ran in a threadpool thread. Safe — one
    # connection per request, never shared.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _rows(db, sql: str, args: tuple = ()) -> list:
    """Defensive query — a missing table (module not init'd) is an empty list."""
    try:
        return db.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []


async def _required_cert_claims(fuel_id: str) -> tuple[list[str], str]:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{TEA_ENGINE_URL}/tea/regime/{fuel_id}")
        if r.status_code == 200:
            g = r.json()["certification_gate"]
            return g["required_cert_claims"], "tea_engine"
    except Exception:  # noqa: BLE001
        pass
    pc = _FALLBACK_FUEL_CLASS.get((fuel_id or "").upper(), "RFNBO")
    return _FALLBACK_CERT_CLAIMS[pc], "static_fallback"


@router.get("/project/{project_id}/next-best-actions")
async def next_best_actions(
    project_id: str,
    fuel_id: str = "E_METHANOL",
    pathway_id: Optional[str] = None,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Ranked actions: for each open claim/approval, what it unlocks and what the
    delay is costing per month. The nudge — guidance with named consequences,
    never a lock."""
    # ── 1. Current claim states (live rows only) ────────────────────────────
    claim_states: dict[str, str] = {}
    q = ("SELECT claim_type, state FROM pathway_claims WHERE project_id=? "
         "AND valid_to IS NULL AND state NOT IN ('superseded','rejected','expired','failed')")
    args: list = [project_id]
    if pathway_id:
        q += " AND pathway_id=?"; args.append(pathway_id)
    for r in _rows(db, q, tuple(args)):
        claim_states[r["claim_type"]] = r["state"]

    base_case = None
    for r in _rows(db, "SELECT claim_id, state, capex_eur FROM model_base_case "
                       "WHERE project_id=? AND valid_to IS NULL AND state NOT IN "
                       "('superseded','rejected','expired','failed') "
                       "ORDER BY created_at DESC LIMIT 1", (project_id,)):
        base_case = dict(r)

    # ── 2. Capital at stake (pending drawdowns) ─────────────────────────────
    pending = _rows(db, "SELECT drawdown_id, amount, quarter, milestone_trigger, "
                        "ie_signoff_ref, drawdown_status FROM drawdown_schedules "
                        "WHERE project_id=? AND drawdown_status NOT IN ('RELEASED','CANCELLED')",
                    (project_id,))
    capital_at_stake = sum(r["amount"] or 0.0 for r in pending)
    monthly_delay_cost = capital_at_stake * discount_rate / 12.0

    required_cert, regime_source = await _required_cert_claims(fuel_id)

    actions: list[dict] = []

    # ── 3. Cost basis → release gate (blocks ALL release-gated capital) ─────
    if base_case is None:
        actions.append({
            "action": "Run the TEA to establish a cost basis (model_base_case)",
            "owner_role": "SPONSOR / FINANCE",
            "unlocks": "the entire release path — no drawdown or release-gated PF "
                       "compute can run without a cost basis",
            "entropy_dimension": "cost-definition uncertainty",
            "capital_at_stake_eur": capital_at_stake,
            "delay_cost_eur_per_month": round(monthly_delay_cost, 0),
            "how": f"POST /api/v1/tea/compute/{project_id}",
        })
    elif base_case["state"] not in TERMINAL_VALID:
        actions.append({
            "action": "Obtain IE/CFO approval of the cost basis "
                      f"({base_case['claim_id']}, currently '{base_case['state']}')",
            "owner_role": "INDEPENDENT_ENGINEER / CFO",
            "unlocks": "release-gated PF compute (waterfall, covenants, DSCR, "
                       "structured drawdown) and the pending drawdown queue",
            "entropy_dimension": "cost-verification uncertainty",
            "capital_at_stake_eur": capital_at_stake,
            "delay_cost_eur_per_month": round(monthly_delay_cost, 0),
            "how": f"POST /api/v1/tea/base-case/{base_case['claim_id']}/approve",
        })

    # ── 4. Certification gate — regime-specific missing claims ──────────────
    missing_cert = [c for c in required_cert if claim_states.get(c) not in TERMINAL_VALID]
    for c in missing_cert:
        state = claim_states.get(c)
        actions.append({
            "action": (f"Verify claim '{c}' (currently '{state}')" if state
                       else f"Produce evidence for claim '{c}' (absent)"),
            "owner_role": "CERTIFIER / PRODUCER",
            "unlocks": f"certification gate for {fuel_id} — 1 of {len(missing_cert)} "
                       "claims still blocking; gate gates the green premium and "
                       "offtake claim validity",
            "entropy_dimension": "certification uncertainty",
            "capital_at_stake_eur": None,
            "delay_cost_eur_per_month": None,
            "how": (f"POST /api/v1/tea/claim/<id>/approve" if state == "submitted"
                    else f"POST /api/v1/tea/lca/{project_id} (GHG claims) or upload evidence"),
        })

    # ── 5. Drawdown-specific blockers ────────────────────────────────────────
    for r in pending:
        if not r["ie_signoff_ref"]:
            actions.append({
                "action": f"Obtain IE sign-off for drawdown {r['drawdown_id']} "
                          f"({r['quarter']}, milestone: {r['milestone_trigger']})",
                "owner_role": "INDEPENDENT_ENGINEER",
                "unlocks": f"€{(r['amount'] or 0):,.0f} drawdown release",
                "entropy_dimension": "execution-verification uncertainty",
                "capital_at_stake_eur": r["amount"],
                "delay_cost_eur_per_month": round((r["amount"] or 0) * discount_rate / 12.0, 0),
                "how": "file IE certificate against the milestone evidence",
            })

    # ── 6. Rank: capital at stake desc, then cert claims, then rest ─────────
    actions.sort(key=lambda a: (-(a["capital_at_stake_eur"] or 0),
                                a["entropy_dimension"] != "certification uncertainty"))

    # ── 7. Cohort context (EXTERNAL_PRIOR) — nudge-side benchmark ONLY.
    #      By ruled policy this never enters the action ranking above, and it
    #      never reaches gate evaluation or bankability scoring.
    cohort_context = None
    try:
        from app.core import external_corpus as xc
        xc.init_db()
        d = xc.density({"fuel_id": fuel_id})
        if d.get("density") is not None:
            cohort_context = {"density": d, "base_rates": xc.base_rates(fuel_id),
                              "provenance": "EXTERNAL_PRIOR — benchmark context; "
                                            "does not affect ranking or scores"}
    except Exception:  # noqa: BLE001 — context is optional, never breaks the nudge
        pass

    return {
        "project_id": project_id,
        "fuel_id": fuel_id,
        "regime_source": regime_source,
        "capital_at_stake_eur": capital_at_stake,
        "assumed_discount_rate": discount_rate,
        "value_basis": "HEURISTIC — delay cost = capital at stake × discount_rate/12 "
                       "per month. A ranking signal, not a valuation.",
        "actions": actions,
        "action_count": len(actions),
        "cohort_context": cohort_context,
    }
