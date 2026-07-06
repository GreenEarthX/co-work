"""tea_adapter — OpenPyTEA ⇄ GEX seam (REFERENCE STUB, Play #1).

This is the only glue between the OpenPyTEA techno-economic engine and the GEX
project-finance engine. It does two things:

  1. build_equipment()  — turn a GEX pathway's `engineering` layer into
     OpenPyTEA `Equipment` objects (so the cost run is reproducible from the
     canonical pathway object, not a spreadsheet).
  2. result_to_plant_summary()  — map OpenPyTEA's plant result back onto
     `gex_pf_engine.models.PlantSummary`, the exact bundle the PF engine already
     consumes, and stamp the cost-basis hash so it can become a truth-stack Claim.

Design notes
------------
* OpenPyTEA is an OPTIONAL dependency. Importing this module must never break the
  PF engine, so the OpenPyTEA import is guarded. In production this code runs in
  the separate `tea_engine` service (port 8002), not inside :8001 — see
  docs/integration/openpytea_pathwayspec_play.md.
* The returned `PlantSummary.verification_state` is UNVERIFIED: a raw engine run
  is an *asserted/submitted* claim, never self-verified. An independent engineer
  moves it to CONFIRMED/AUDITED via the 9-state ClaimState machine. That gate
  (G04) is what turns a number into decision-grade trust.

This file is a stub: function bodies sketch the mapping and raise/NotImplemented
where the real OpenPyTEA API calls go. It is safe to import as-is.
"""
from __future__ import annotations

from typing import Any, Optional

from gex_pf_engine.models.deal import PlantSummary, VerificationState

try:  # OpenPyTEA is optional; only the tea_engine service installs it.
    import openpytea  # type: ignore
    _HAS_OPENPYTEA = True
except Exception:  # pragma: no cover - absence is the normal case inside :8001
    openpytea = None  # type: ignore
    _HAS_OPENPYTEA = False


def openpytea_available() -> bool:
    """True iff the OpenPyTEA package is importable in this process."""
    return _HAS_OPENPYTEA


def build_equipment(engineering_layer: dict[str, Any]) -> list[Any]:
    """Map a GEX pathway `engineering` block → OpenPyTEA Equipment objects.

    Each `process_units[]` entry carries `category` (an OpenPyTEA cost-correlation
    key), `material`, and a `sizing` claim (the parameter cost is correlated
    against). Utilities feed the OPEX side.
    """
    if not _HAS_OPENPYTEA:
        raise RuntimeError(
            "OpenPyTEA not installed — build_equipment must run in the "
            "tea_engine service (port 8002), not in the PF engine."
        )
    equipment: list[Any] = []
    for unit in engineering_layer.get("process_units", []):
        # equipment.append(openpytea.Equipment(
        #     category=unit["category"],
        #     material=unit.get("material"),
        #     sizing=_resolve_claim_value(unit["sizing"]),
        # ))
        raise NotImplementedError("wire to openpytea.Equipment(...)")
    return equipment


def result_to_plant_summary(
    plant_id: str,
    openpytea_result: Any,
    cost_basis_hash: str,
    nameplate_capacity: Optional[float] = None,
    nameplate_unit: Optional[str] = None,
) -> PlantSummary:
    """Map an OpenPyTEA plant result → the PF engine's PlantSummary.

    OpenPyTEA's three-tier output (equipment → plant CAPEX → OPEX → LCOP) lines up
    field-for-field with what PlantSummary needs. We deliberately do NOT trust the
    run: verification_state stays UNVERIFIED until an independent engineer signs
    off (gate G04), per the GEX evidence model.
    """
    if not _HAS_OPENPYTEA:
        raise RuntimeError("OpenPyTEA not installed — run in tea_engine (:8002).")

    # capex_eur = float(openpytea_result.plant.capex_total())
    # opex_eur_per_year = float(openpytea_result.plant.opex_total())
    capex_eur = float(getattr(openpytea_result, "capex_total", 0.0))
    opex_eur_per_year = float(getattr(openpytea_result, "opex_total", 0.0))

    return PlantSummary(
        id=plant_id,
        capex_eur=capex_eur,
        opex_eur_per_year=opex_eur_per_year,
        nameplate_capacity=nameplate_capacity,
        nameplate_unit=nameplate_unit,
        verification_state=VerificationState.UNVERIFIED,  # never self-verify
        deal_killer_flag=False,
    )


def ledger_entry_for_run(project_id: str, cost_basis_hash: str) -> dict[str, Any]:
    """Shape a truth-stack CanonicalLedgerEntry for a TEA run.

    kind=derived / entry_type=projection_snapshot. The PF engine / backend writes
    this to the evidence ledger so the cost basis is auditable and the derived
    capex_eur Claim can reference it. Returned as a dict to avoid a hard import of
    efuel_truth_stack from inside the engine.
    """
    return {
        "project_id": project_id,
        "kind": "derived",
        "entry_type": "projection_snapshot",
        "produced_by": "tea_engine",
        "payload": {"cost_basis_hash": cost_basis_hash, "engine": "openpytea"},
    }
