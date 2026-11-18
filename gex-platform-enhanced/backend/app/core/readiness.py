"""
One readiness authority (handoff v4, task 1; JML 2026-11-17).
==============================================================
The state shown anywhere is the gate engine's `current_state` from ONE stored
snapshot, and every response that carries it also carries what that snapshot was
computed from:

    project_id, scenario, evaluated_at, rules_version, evidence_fingerprint

STATUS
  CURRENT        the snapshot's inputs and rules are the project's inputs and rules
                 now. Only a CURRENT result supports a pass/fail judgement.
  STALE          evidence (or premise, or contract terms) changed after
                 evaluated_at, or the rules version changed. Shown as stale; no
                 pass/fail judgement may rest on it.
  NOT_EVALUATED  no snapshot: "not evaluated", never a figure.

The fingerprint is a SHA-256 over exactly what the engine is given besides the
date: each evidence item's key, status, maturity, validity and document, and the
engine context (power, phase and financing model, commitment cards). Assignees,
due dates and notes do not move a gate and are left out.

Gate state does not depend on a financial scenario: it is a statement about
verified evidence. `scenario` is therefore always "AS_EVIDENCED", stated so that
a reader never confuses it with a base or downside financial case.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

SCENARIO = "AS_EVIDENCED"
SCENARIO_NOTE = ("Gate state is a statement about verified evidence; it has no financial "
                 "scenario. Financial cases (base, downside, FROM_FID) are separate.")
FINGERPRINT_KEY = "gex_inputs_fingerprint"

_EVIDENCE_FIELDS = ("key", "status", "maturity", "valid_until", "verified_at", "document_hash")


def inputs_fingerprint(evidence: list[dict], context: dict) -> str:
    items = sorted(({f: (None if e.get(f) is None else str(e.get(f))) for f in _EVIDENCE_FIELDS}
                    for e in evidence or []), key=lambda e: e["key"] or "")
    payload = {"evidence": items, "context": context or {}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def stamp(project_id: str, snapshot: Optional[dict], evaluated_at: Optional[str], *,
          current_fingerprint: Optional[str], current_rules_version: Optional[str]) -> dict:
    """The identity and freshness of a readiness result. Pure."""
    if not snapshot:
        return {"project_id": project_id, "scenario": SCENARIO, "scenario_note": SCENARIO_NOTE,
                "status": "NOT_EVALUATED", "evaluated_at": None, "rules_version": None,
                "evidence_fingerprint": None, "stale_reasons": [], "supports_judgement": False,
                "state": None,
                "message": "Not evaluated: the gate engine has no result for this project."}
    stored = snapshot.get(FINGERPRINT_KEY)
    reasons = []
    if stored is None or (current_fingerprint is not None and stored != current_fingerprint):
        reasons.append("EVIDENCE_CHANGED" if stored is not None else "INPUTS_UNKNOWN")
    if current_rules_version is not None and snapshot.get("rules_version") != current_rules_version:
        reasons.append("RULES_CHANGED")
    status = "STALE" if reasons else "CURRENT"
    return {
        "project_id": project_id, "scenario": SCENARIO, "scenario_note": SCENARIO_NOTE,
        "status": status,
        "evaluated_at": evaluated_at or snapshot.get("evaluated_at"),
        "rules_version": snapshot.get("rules_version"),
        "current_rules_version": current_rules_version,
        "evidence_fingerprint": stored,
        "stale_reasons": reasons,
        "supports_judgement": status == "CURRENT",
        "state": snapshot.get("current_state"),
        "message": (None if status == "CURRENT" else
                    "Stale: " + ", ".join(r.replace("_", " ").lower() for r in reasons)
                    + " since this result was computed. It supports no pass/fail judgement."),
    }


def current_fingerprint(project_id: str) -> str:
    from app.api.v1.routes_bankability_proxy import _engine_context, _load_evidence
    return inputs_fingerprint(_load_evidence(project_id), _engine_context(project_id))


async def current(project_id: str) -> tuple[Optional[dict], Optional[str], dict]:
    """The project's readiness: (snapshot, evaluated_at, stamp).

    Re-evaluates first when the stored snapshot is missing, under other rules,
    past an evidence expiry, or computed from other inputs. If the engine cannot
    answer, the stored snapshot is returned STALE (or NOT_EVALUATED) — never as
    current.
    """
    from app.api.v1.routes_bankability_proxy import engine_rules, fresh_snapshot
    snapshot, evaluated_at = await fresh_snapshot(project_id)
    try:
        rules_version = (await engine_rules()).get("rules_version")
    except Exception:  # noqa: BLE001 — the engine is down: freshness cannot be confirmed
        rules_version = "UNAVAILABLE"
    fp = current_fingerprint(project_id)
    return snapshot, evaluated_at, stamp(project_id, snapshot, evaluated_at,
                                         current_fingerprint=fp, current_rules_version=rules_version)


def stored(project_id: str, rules_version: Optional[str] = None) -> tuple[Optional[dict], Optional[str], dict]:
    """The stored snapshot with its stamp, without re-evaluating (sync readers)."""
    from app.api.v1.routes_bankability_proxy import stored_snapshot
    snapshot, evaluated_at = stored_snapshot(project_id)
    return snapshot, evaluated_at, stamp(project_id, snapshot, evaluated_at,
                                         current_fingerprint=current_fingerprint(project_id),
                                         current_rules_version=rules_version)
