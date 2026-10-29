"""
What a caller is shown about a project's gates — from the ENGINE only.

JML, 2026-10-28: "every gate figure must come from the engine". Until then
~22 screens read `project_profile.bankability`, a block typed by hand when the
platform was demonstrated: HamburgOne showed G0 Site Rights 100 % complete and
52 % overall while the engine, which counts only verified evidence, said 0 %;
capital lines read "DRAWN". This module turns the engine's stored snapshot into
the shape those screens read, and nothing else feeds it.

Two rules live here:

  persona_for     — which gates a caller may see, derived from the TOKEN and the
                    project's owner (the persona used to be a query parameter
                    the caller chose: ?persona=EXECUTIVE showed all twelve).
  bankability_view — the persona-scoped view, with its SCOPE stated: the
                    overall figure covers every applicable gate while a persona
                    sees some of them (finding 6 of the 26 Sep review).
"""
from __future__ import annotations

from typing import Optional

# The engine's persona → gates map is served by the engine itself (PERSONA_GATES
# in pf_engine). Kept here as the CALLER rule only; which gates each persona sees
# is read from the snapshot's own evaluation and the engine's map.
PERSONAS = ("EXECUTIVE", "PRODUCER", "FINANCE", "REGULATOR", "OFFTAKER")
_FINANCE_SERVICES = {"BANK", "DFI", "INSURER", "INVESTOR"}
_REGULATOR_SERVICES = {"CERTIFIER", "AUDITOR", "REGULATOR", "LEGAL"}


def persona_for(payload: dict, owner_company_id: Optional[str]) -> str:
    """The engine persona this caller sees a project through.

    EXECUTIVE (all gates) is the project owner's executives and GEX staff only.
    An executive of a bank, an offtaker or a contractor sees its own role's
    gates — not the producer's whole file.
    """
    if payload.get("is_platform_admin") or payload.get("service_type") == "PLATFORM":
        return "EXECUTIVE"
    company = payload.get("company_id")
    function = payload.get("business_function")
    if owner_company_id and company == owner_company_id:
        return "EXECUTIVE" if function == "EXECUTIVE" else "PRODUCER"
    if payload.get("company_type") == "OFFTAKER":
        return "OFFTAKER"
    service = payload.get("service_type")
    if service in _FINANCE_SERVICES or function == "FINANCE_TREASURY":
        return "FINANCE"
    if service in _REGULATOR_SERVICES or function == "COMPLIANCE_LEGAL":
        return "REGULATOR"
    return "PRODUCER"


def narrower_or_equal(requested: str, allowed: str, persona_gates: dict) -> bool:
    """A caller may ask for a persona whose gates are a subset of its own."""
    want, have = set(persona_gates.get(requested, [])), set(persona_gates.get(allowed, []))
    return bool(want) and want <= have


def _next_milestone(snapshot: dict) -> str:
    """The first thing blocking the next state, in the engine's words."""
    nxt = snapshot.get("next_state_label") or snapshot.get("next_state")
    for gid in snapshot.get("gates_blocking_next_state") or []:
        gate = next((g for g in snapshot.get("gate_evaluations", []) if g["gate_id"] == gid), None)
        if gate:
            why = (gate.get("blocked_reasons") or [])[:1] or [f"{len(gate.get('blocking_items') or [])} item(s) to verify"]
            return f"{gate['gate_name']}: {why[0]}" + (f" — then {nxt}" if nxt else "")
    return f"Next: {nxt}" if nxt else ""


def bankability_view(snapshot: Optional[dict], persona: str, persona_gates: dict,
                     evaluated_at: Optional[str] = None) -> dict:
    """The engine snapshot as the screens' `bankability` block, scoped to `persona`.

    No snapshot → `evaluated: False` and no figures: "not yet evaluated" is
    shown, never a guess.
    """
    if not snapshot:
        return {"evaluated": False, "source": "engine", "overall_completion": None, "gates": [],
                "capital_status": [], "unlocked_capital": [], "next_milestone": "", "risk_alerts": [],
                "state": None, "state_label": None, "rules_version": None, "evaluated_at": None,
                "scope": {"persona": persona, "visible_gates": 0, "total_gates": 0}}
    visible = set(persona_gates.get(persona, []))
    all_gates = snapshot.get("gate_evaluations", [])
    gates = [{
        "id": g["gate_id"], "name": g["gate_name"],
        "completion_pct": g.get("completion_pct", 0.0),
        "total_evidence": g.get("total_evidence", 0), "verified_count": g.get("verified_count", 0),
        "is_complete": bool(g.get("is_complete")),
        "determination": g.get("determination"),
        "blocking_items": list(g.get("blocking_items") or []),
        "blocked_reasons": list(g.get("blocked_reasons") or []),
        "description": "; ".join((g.get("blocked_reasons") or [])[:2]),
    } for g in all_gates if g["gate_id"] in visible]
    capital = [{
        "name": c.get("label") or c["capital_type"], "type": c["capital_type"],
        "is_unlocked": bool(c.get("decision_eligible") or c.get("is_unlocked")),
        "gating_gates": [g for g in c.get("gating_gates", []) if g in visible],
        "progress_pct": c.get("best_progress_pct", 0.0),
        # GEX establishes eligibility; it never records money as committed or drawn.
        "commitment_status": "DECISION_ELIGIBLE" if c.get("decision_eligible") else "NOT_YET_ELIGIBLE",
    } for c in snapshot.get("capital_unlocks", []) if c.get("financing_applicable", True)]
    return {
        "evaluated": True, "source": "engine",
        "overall_completion": snapshot.get("overall_completion_pct", 0.0),
        "gates": gates,
        "capital_status": capital,
        "unlocked_capital": [c["name"] for c in capital if c["is_unlocked"]],
        "next_milestone": _next_milestone(snapshot),
        "risk_alerts": [],
        "state": snapshot.get("current_state"),
        "state_label": snapshot.get("state_label"),
        "next_state": snapshot.get("next_state"),
        "rules_version": snapshot.get("rules_version"),
        "evaluated_at": evaluated_at or snapshot.get("evaluated_at"),
        "scope": {
            "persona": persona,
            "visible_gates": len(gates),
            "total_gates": len(all_gates),
            "note": (None if len(gates) == len(all_gates) else
                     f"The overall figure and the state cover all {len(all_gates)} gates; "
                     f"you see the {len(gates)} that concern your role."),
        },
    }


_SEVERITY_ORDER = {"deal_killer": 0, "warning": 1, "advisory": 2}


def open_items(snapshot: Optional[dict], persona: str, persona_gates: dict,
               evidence_rows: list[dict], today: Optional[str] = None) -> dict:
    """Everything still open on a project, side by side — the executive overview.

    A project is not worked gate by gate: evidence, contracts and checks move in
    parallel. So every open item of every visible gate is listed at once, each
    with what it is, who acts, by when, and what it holds back:

      evidence       an item not yet verified (or below its required maturity)
      commitment     the offtake or EPC commitment below the level the gate needs
      contradiction  a cross-contract check or commitment requirement that FAILED
      missing_data   a cross-contract check that cannot run (gate UNRESOLVED)
      trigger        a post-FID event undermining the gate
    """
    if not snapshot:
        return {"evaluated": False, "items": [], "summary": {}}
    visible = set(persona_gates.get(persona, []))
    by_key = {r["key"]: r for r in evidence_rows}
    items: list[dict] = []
    for order, g in enumerate(snapshot.get("gate_evaluations", [])):
        if g["gate_id"] not in visible or g.get("determination") in ("SATISFIED", "WAIVED"):
            continue
        holds = g.get("unlocks_state")
        base = {"gate_id": g["gate_id"], "gate_name": g["gate_name"], "gate_order": order,
                "determination": g.get("determination"), "holds_back": holds}
        for d in g.get("evidence_detail", []):
            if not d.get("applicable") or d["key"] not in (g.get("blocking_items") or []):
                continue
            row = by_key.get(d["key"], {})
            due = row.get("due_date")
            items.append({**base, "kind": "evidence", "key": d["key"], "what": d.get("label") or d["key"],
                          "severity": d.get("severity"), "status": d.get("status"),
                          "maturity": {"required": d.get("required_maturity"),
                                       "declared": d.get("declared_maturity"),
                                       "status": d.get("maturity_status")},
                          "owner_function": d.get("owner_function"),
                          "assignee": row.get("assignee_user_id"), "due_date": due,
                          "overdue": bool(due and today and str(due) < today),
                          "action": d.get("blocked_action")})
        for reason in g.get("blocked_reasons") or []:
            if reason[:1] == "C" and " failed" in reason[:12]:
                kind, action = "contradiction", "Resolve the conflict between the contracts named"
            elif reason[:1] == "T" and reason[1:2].isdigit():
                kind, action = "trigger", "Address the event that undermines the gate"
            else:   # "OFFTAKE O2 below the O4 this gate needs" — a commitment not yet reached
                kind, action = "commitment", "Advance the commitment to the level this gate needs"
            items.append({**base, "kind": kind, "what": reason, "severity": "deal_killer",
                          "owner_function": "PROJECT", "action": action})
        for reason in g.get("unresolved_reasons") or []:
            items.append({**base, "kind": "missing_data", "what": reason, "severity": "warning",
                          "owner_function": "PROJECT",
                          "action": "Record the missing contract terms so the check can run"})
    items.sort(key=lambda i: (_SEVERITY_ORDER.get(i.get("severity"), 3), i["gate_order"]))
    summary = {
        "open": len(items),
        "by_kind": {k: sum(1 for i in items if i["kind"] == k)
                    for k in ("evidence", "commitment", "contradiction", "missing_data", "trigger")},
        "deal_killers": sum(1 for i in items if i.get("severity") == "deal_killer"),
        "unassigned": sum(1 for i in items if i["kind"] == "evidence" and not i.get("assignee")),
        "overdue": sum(1 for i in items if i.get("overdue")),
        "without_due_date": sum(1 for i in items if i["kind"] == "evidence" and not i.get("due_date")),
    }
    return {"evaluated": True, "items": items, "summary": summary,
            "state": snapshot.get("current_state"), "next_state": snapshot.get("next_state")}
