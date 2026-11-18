"""
Structuring context — what the structuring engine is told about a project.
=========================================================================
JML, 2026-11-17: "take structuring's gate scores from the engine — for every
project". Until now the whole context was one stored record per project
(project_dataset, kind structuring_context), typed by hand and UNVERIFIED,
gate scores and state included. A project could therefore show one gate
picture on Stage Gates (the engine's, from verified evidence) and another on
Gap Analysis, Instruments, Package, Risk Allocation and Structuring Timeline.
One such record (proj_bremen_h2) was a copy of the Breizh SAF reference case.

Each field now has exactly one source, stated in the answer under "sources":

  ENGINE      gate_scores   per gate G0..G11: the engine's completion_pct,
                            which counts verified evidence only
              stage         the engine's current_state
  REGISTRY    jurisdiction  projects.country (ISO 3166-1 alpha-2)
              molecule      projects.molecule, in the instrument registry's terms
              project_size_eur  projects.capex_eur
  RECORDED    dscr_p50, dscr_p90, wacc, offtake_coverage_pct
              — the stored record, with its verification state. (Grid,
              certification, EPC and insurance status, and LLCR, stopped being
              typed on 2026-11-17: requirement-level engine evidence, and the
              PF engine, replace them.) Gate scores,
              stage and identity in that record are IGNORED, so a stale or
              copied value can no longer reach a result.

Nothing has a default. A project the engine has not evaluated, or without a
recorded input, gets no structuring answer and is told which source is missing.
The builder is a pure function; the loader beside it does the reads.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# 2026-11-17 (handoff v4, task 2): grid, certification, EPC and insurance status
# are no longer typed. They are the engine's requirement-level evidence for G1,
# G2, G5 and G7 (offtake: G4). LLCR is engine-computed only (task 5), never a
# typed figure. Those fields, if still in a stored record, are IGNORED and listed.
RECORDED_FIELDS = ("dscr_p50", "dscr_p90", "wacc", "offtake_coverage_pct")
RETIRED_TYPED_FIELDS = ("cert_readiness", "epc_status", "insurance_status", "grid_status", "llcr")
DERIVED_FIELDS = ("gate_scores", "stage", "jurisdiction", "molecule", "project_size_eur")
GATE_KEYS = tuple(f"G{i}" for i in range(12))

# Project molecules as the registry writes them → the instrument registry's terms.
_MOLECULES = {
    "H2": "H2", "GREEN_H2": "H2", "HYDROGEN": "H2", "E_H2": "H2",
    "NH3": "NH3", "E_NH3": "NH3", "AMMONIA": "NH3", "GREEN_NH3": "NH3",
    "SAF": "SAF", "E_SAF": "SAF", "ESAF": "SAF",
    "E_METHANOL": "E_METHANOL", "EMETHANOL": "E_METHANOL", "METHANOL": "E_METHANOL", "E_MEOH": "E_METHANOL",
    "E_NG": "E_NG", "E_METHANE": "E_NG", "SNG": "E_NG", "E_GAS": "E_NG",
}


# Two-letter codes the registry uses that are not a country.
_NOT_COUNTRIES = {"EU", "XX", "ZZ"}


class ContextUnavailable(Exception):
    """A source the structuring context needs is missing. `code` and `message`
    are what the caller is told; `status` is the HTTP status."""

    def __init__(self, status: int, code: str, message: str, missing: Optional[list] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.missing = status, code, message, missing or []


def normalise_molecule(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")
    return _MOLECULES.get(key, key)


def engine_gate_scores(snapshot: dict) -> dict[str, float]:
    """G0..G11 → the engine's completion_pct. A gate the engine did not report is absent."""
    scores: dict[str, float] = {}
    for gate in snapshot.get("gate_evaluations") or []:
        match = re.match(r"^(G(?:1[01]|[0-9]))_", str(gate.get("gate_id", "")))
        if match:
            scores[match.group(1)] = float(gate.get("completion_pct") or 0.0)
    return scores


def build_context(project_id: str, *, identity: Optional[dict], snapshot: Optional[dict],
                  evaluated_at: Optional[str], record: Optional[dict],
                  readiness: Optional[dict] = None) -> dict:
    """The context, from the three sources. Raises ContextUnavailable."""
    if not identity:
        raise ContextUnavailable(404, "PROJECT_NOT_FOUND", f"Unknown project '{project_id}'.")
    if not snapshot:
        raise ContextUnavailable(409, "NOT_EVALUATED_BY_GATE_ENGINE",
                                 "The gate engine has not evaluated this project, so structuring has no gate "
                                 "scores or state to work from. Evaluate the project's gates first.")
    scores = engine_gate_scores(snapshot)
    stage = snapshot.get("current_state")
    if not scores or not stage:
        raise ContextUnavailable(409, "NOT_EVALUATED_BY_GATE_ENGINE",
                                 "The gate engine's snapshot for this project holds no gate scores or state.")
    if record is None:
        raise ContextUnavailable(404, "STRUCTURING_INPUTS_NOT_RECORDED",
                                 "No structuring inputs are recorded for this project, so no gaps or options "
                                 "are computed.", list(RECORDED_FIELDS))
    payload = record.get("payload") or {}
    # A missing input is not a refusal: the decision tests that need it read
    # "not assessable — required inputs missing"; everything else is computed.
    missing = [f for f in RECORDED_FIELDS if payload.get(f) is None]

    country = str(identity.get("country") or "").strip().upper()
    capex = identity.get("capex_eur")
    context: dict[str, Any] = {
        "gate_scores": scores,
        "stage": stage,
        "jurisdiction": country if len(country) == 2 and country not in _NOT_COUNTRIES else None,
        "molecule": normalise_molecule(identity.get("molecule")),
        "project_size_eur": int(capex) if capex else 0,
        **{f: payload.get(f) for f in RECORDED_FIELDS},
        "llcr": None,   # engine-computed only; no typed or proxy substitute (task 5)
    }
    context["sources"] = {
        "engine": {"fields": ["gate_scores", "stage"], "rules_version": snapshot.get("rules_version"),
                   "evaluated_at": evaluated_at or snapshot.get("evaluated_at"),
                   "note": "Gate scores are the engine's completion, counting verified evidence only."},
        "registry": {"fields": ["jurisdiction", "molecule", "project_size_eur"],
                     "missing": [k for k, v in (("jurisdiction", context["jurisdiction"]),
                                                ("molecule", context["molecule"]),
                                                ("project_size_eur", context["project_size_eur"])) if not v]},
        "recorded": {"fields": list(RECORDED_FIELDS), "verification_state": record.get("verification_state"),
                     "missing": missing,
                     "ignored": sorted(k for k in DERIVED_FIELDS + RETIRED_TYPED_FIELDS if k in payload)},
        "llcr": "Unavailable here: LLCR is computed by the PF engine on a returns case, never typed.",
    }
    context["readiness"] = readiness
    context["_snapshot"] = snapshot      # private: the engine's requirement-level evidence
    return context


def public(context: dict) -> dict:
    """What a response may show: the context without the private snapshot."""
    return {k: v for k, v in context.items() if not k.startswith("_")}


async def load_context(project_id: str) -> dict:
    """Read the three sources and build the context. Raises ContextUnavailable.

    The engine snapshot is the one readiness authority's (app/core/readiness.py),
    refreshed if its inputs moved, and carries its stamp."""
    from app.core import readiness
    from app.core.projects_store import PLATFORM_ADMIN, StoreUnavailable, _rows_strict, dataset_strict, resolve_alias

    pid = resolve_alias(project_id) or project_id
    try:
        rows = _rows_strict("SELECT project_id, country, molecule, capex_eur FROM projects "
                            "WHERE project_id = :pid AND is_active", {"pid": pid})
        record = dataset_strict(pid, "structuring_context", PLATFORM_ADMIN)
    except StoreUnavailable as exc:
        raise ContextUnavailable(503, "STRUCTURING_SOURCES_UNAVAILABLE",
                                 "The project record could not be read; nothing is computed.") from exc
    snapshot, evaluated_at, stamp = await readiness.current(pid)
    return build_context(pid, identity=rows[0] if rows else None, snapshot=snapshot,
                         evaluated_at=evaluated_at, record=record, readiness=stamp)
