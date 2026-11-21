"""Sources and uses for ONE financing case (JML, 19 Nov 2026). Pure rules, no database.

What it decides, for the SELECTED case only (pipeline opportunities are shown, never counted):

Uses (total project cost), each from exactly one place:
  CONSTRUCTION      the named TEA run's fixed capital (calculated by the TEA engine). Stated only
                    when no TEA run is named, and then labelled an estimate.
  DEVELOPMENT, OWNERS_COSTS, RESERVES, OTHER   stated, each with its source.
  FINANCING_COSTS   D3: the engine calculation is the target, not built yet for a drawdown
                    schedule; until then each component (IDC, fees, hedging) is stated, with
                    its source AND the reason it is stated.
  WORKING_CAPITAL   D4: an explicit amount or a documented calculation, a zero only with its
                    reason. OpenPyTEA's own figure (0.15 x fixed capital in 3.0.0, kept in its
                    OPEX as interest and in its cash flow) is shown beside it, never added.
  A required use not stated is UNKNOWN: the total is then a floor, and it is said.

Sources, by the substance of the obligation (D2), not the document's title:
  NONE / INDICATIVE   pipeline-grade: shown, never deducted
  CONDITIONAL         obliged subject to stated conditions: shown separately, not deducted
  BINDING             obliged; `available_eur` is what may be drawn now; `received_eur` is cash in
  in_plan = No        a pipeline opportunity: outside the selected case altogether

  remaining need = total uses - received - binding available (a floor when uses are unknown)

Gearing: numerator the case's debt, denominator the case's total uses. Compared with a policy
value that names its owner and version (the registry row), REPORTED, never a GEX hurdle. A
lender's own limit is checked for that lender and attributed to it.
"""
from __future__ import annotations

from typing import Optional

USE_KINDS = ("DEVELOPMENT", "CONSTRUCTION", "OWNERS_COSTS", "FINANCING_COSTS", "RESERVES",
             "WORKING_CAPITAL", "OTHER")
REQUIRED_USES = ("DEVELOPMENT", "CONSTRUCTION", "FINANCING_COSTS", "RESERVES", "WORKING_CAPITAL")
FINANCING_COMPONENTS = ("IDC", "UPFRONT_FEES", "COMMITMENT_FEES", "HEDGING", "OTHER")
OBLIGATIONS = ("NONE", "INDICATIVE", "CONDITIONAL", "BINDING")
DEBT_TYPES = ("SENIOR_DEBT", "DFI_LOAN", "GREEN_BOND", "MEZZANINE")
EQUITY_TYPES = ("SPONSOR_EQUITY", "THIRD_PARTY_EQUITY")
OPENPYTEA_WC_FACTOR = 0.15          # openpytea 3.0.0, plant.py: working_capital = 0.15 x fixed_capital
STICKY = ("STACK_DEBT_UNRECONCILED", "GRANTS_UNRECONCILED")


def _num(v) -> float:
    return float(v or 0.0)


def reconcile(plan: dict, *, base_case: Optional[dict], terms: dict,
              gearing_policy: Optional[dict] = None) -> dict:
    """The selected case's sources and uses, its remaining need, and what stops promotion."""
    sources = plan.get("sources") or []
    uses_in = plan.get("uses") or []
    limitations: list[dict] = []
    notes: list[str] = []

    uses: list[dict] = []
    fci = _num(base_case.get("capex_eur")) if base_case and base_case.get("capex_eur") else None
    stated_construction = [u for u in uses_in if u["kind"] == "CONSTRUCTION"]
    if fci is not None:
        uses.append({"kind": "CONSTRUCTION", "amount_eur": fci, "origin": "CALCULATED",
                     "source": f"TEA run {base_case['claim_id']} fixed capital (OpenPyTEA: ISBL, OSBL, D&E, contingency)"})
        if stated_construction:
            limitations.append({"code": "CONSTRUCTION_TWICE", "detail": "Construction is the TEA run's fixed capital; "
                                "remove the stated construction use (it would count twice)."})
    for u in uses_in:
        if u["kind"] == "CONSTRUCTION" and fci is not None:
            continue
        origin = "ESTIMATE" if u["kind"] == "CONSTRUCTION" else (u.get("standing") or "STATED")
        uses.append({**u, "origin": origin})
    present = {u["kind"] for u in uses}
    unknown = [k for k in REQUIRED_USES if k not in present]
    if unknown:
        limitations.append({"code": "USES_INCOMPLETE", "detail": f"Not stated: {', '.join(unknown)}. The total "
                            "is a floor; a zero is stated with its reason."})
    for u in uses:
        if u["kind"] == "FINANCING_COSTS" and not (u.get("reason") or "").strip():
            limitations.append({"code": "FINANCING_COSTS_UNEXPLAINED",
                                "detail": f"Financing cost {u.get('component') or ''} is stated without the reason "
                                          "it replaces the engine calculation."})
        if u["kind"] == "WORKING_CAPITAL" and _num(u["amount_eur"]) == 0 and not (u.get("reason") or "").strip():
            limitations.append({"code": "WORKING_CAPITAL_ZERO_UNEXPLAINED",
                                "detail": "Working capital is zero without the reason."})
    total_uses = sum(_num(u["amount_eur"]) for u in uses)
    tea_wc = round(OPENPYTEA_WC_FACTOR * fci, 2) if fci is not None else None

    in_plan = [s for s in sources if s.get("in_plan", True)]
    pipeline = [s for s in sources if not s.get("in_plan", True)]
    received = sum(_num(s.get("received_eur")) for s in in_plan)
    binding = sum(_num(s.get("available_eur")) for s in in_plan if s.get("obligation") == "BINDING")
    conditional = [s for s in in_plan if s.get("obligation") == "CONDITIONAL"]
    uncommitted = [s for s in in_plan if s.get("obligation") in (None, "NONE", "INDICATIVE")]
    allocated = sum(_num(s["amount_eur"]) for s in in_plan)

    case_debt = _num((terms.get("debt_eur") or {}).get("value")) if "debt_eur" in terms else None
    case_grant = _num((terms.get("grant_eur") or {}).get("value"))
    plan_debt = sum(_num(s["amount_eur"]) for s in in_plan if s["type"] in DEBT_TYPES)
    plan_grant = sum(_num(s["amount_eur"]) for s in in_plan if s["type"] == "GRANT")
    if in_plan and case_debt is not None and abs(plan_debt - case_debt) > 0.5:
        limitations.append({"code": "STACK_DEBT_UNRECONCILED",
                            "detail": f"The plan's debt sources total EUR {plan_debt:,.0f}; the case's debt is "
                                      f"EUR {case_debt:,.0f}."})
    if in_plan and abs(plan_grant - case_grant) > 0.5:
        limitations.append({"code": "GRANTS_UNRECONCILED",
                            "detail": f"The plan's grants total EUR {plan_grant:,.0f}; the case's grants are "
                                      f"EUR {case_grant:,.0f}."})
    if uses and case_debt is not None and case_debt + case_grant > total_uses + 0.5:
        limitations.append({"code": "DEBT_EXCEEDS_USES",
                            "detail": f"Debt plus grants (EUR {case_debt + case_grant:,.0f}) exceed the case's defined "
                                      f"uses (EUR {total_uses:,.0f})."})
    if uses and in_plan and abs(allocated - total_uses) > 0.5:
        notes.append(f"The plan allocates EUR {allocated:,.0f} against EUR {total_uses:,.0f} of defined uses "
                     f"({'over' if allocated > total_uses else 'under'} by EUR {abs(allocated - total_uses):,.0f}).")

    gearing = []
    if case_debt is not None and total_uses > 0:
        ratio = case_debt / total_uses
        if gearing_policy:
            gearing.append({"by": gearing_policy["owner"], "reference": gearing_policy.get("reference"),
                            "threshold": gearing_policy["value"], "ratio": round(ratio, 4),
                            "result": "ABOVE" if ratio > gearing_policy["value"] else "WITHIN",
                            "basis": "debt / total defined uses of this case",
                            "standing": gearing_policy.get("standing", "REFERENCE: reported, not a GEX hurdle")})
        for s in in_plan:
            if s.get("lender_max_gearing") is not None:
                gearing.append({"by": s["name"], "reference": s.get("source"), "threshold": s["lender_max_gearing"],
                                "ratio": round(ratio, 4),
                                "result": "ABOVE" if ratio > float(s["lender_max_gearing"]) else "WITHIN",
                                "basis": "debt / total defined uses of this case",
                                "standing": "this lender's own limit, as declared"})
    return {
        "uses": uses, "unknown_uses": unknown, "total_uses_eur": round(total_uses, 2),
        "total_is_floor": bool(unknown), "openpytea_working_capital_eur": tea_wc,
        "sources_in_plan": len(in_plan), "allocated_eur": round(allocated, 2),
        "received_eur": round(received, 2), "binding_available_eur": round(binding, 2),
        "conditional": [{"name": s["name"], "amount_eur": s["amount_eur"], "conditions": s.get("conditions")}
                        for s in conditional],
        "uncommitted": [{"name": s["name"], "amount_eur": s["amount_eur"], "obligation": s.get("obligation")}
                        for s in uncommitted],
        "pipeline": [{"name": s["name"], "amount_eur": s["amount_eur"], "obligation": s.get("obligation")}
                     for s in pipeline],
        "pipeline_total_eur": round(sum(_num(s["amount_eur"]) for s in pipeline), 2),
        # With uses unknown, a need that nets to zero or less says nothing: unknown, not "at least 0".
        "remaining_need_eur": (None if not uses or (unknown and total_uses - received - binding <= 0)
                               else round(max(total_uses - received - binding, 0.0), 2)),
        "gearing": gearing, "notes": notes, "limitations": limitations,
    }
