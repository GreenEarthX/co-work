"""Phase-aware compute orchestrator.

Single entry point that:
  1. Reads DealInputs (Sprint 3 will pull from the GEX platform API;
     Sprint 2 accepts inputs in the request).
  2. Runs pre-COD compute → construction-phase state at COD.
  3. Runs operations compute → post-COD cashflow + ratios.
  4. Evaluates COD test as projection.
  5. Assembles ComputeOutput, including Taghizadeh-Hesary commentary
     and engine-precondition checks.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from gex_pf_engine.compute.cod_test import evaluate_cod_test
from gex_pf_engine.compute.operations import run_operations, PreCODState as _ImportedPreCOD
from gex_pf_engine.compute.pre_cod import run_pre_cod
from gex_pf_engine.compute.ratios import (
    compute_irr, compute_npv, compute_equity_irr, compute_rating_band,
    taghizadeh_hesary_split,
)
from gex_pf_engine.models import (
    DealInputs, ComputeOutput, PeriodRow, ComputeWarning,
    TrancheType, TaghizadehHesaryAssessment,
)

ENGINE_VERSION = "gex_pf_engine@sprint2"


def compute_deal(inputs: DealInputs) -> ComputeOutput:
    """End-to-end compute. Phase-aware."""

    warnings: list[ComputeWarning] = []
    errors: list[ComputeWarning] = []

    # ------------------------------------------------------------------
    # Engine precondition: plant must have a clean equation engine run.
    # The migration enforces this for CONFIRMED state, but the compute
    # engine ALSO refuses to produce authoritative numbers on a plant
    # that's not engineering-clean. Returns degraded output instead.
    # ------------------------------------------------------------------
    if inputs.plant.latest_engine_run_status not in ("clean", None):
        errors.append(ComputeWarning(
            code="engine_run_not_clean",
            message=(
                f"Plant {inputs.plant.id} latest equation engine run status is "
                f"'{inputs.plant.latest_engine_run_status}'. The deal structuring "
                f"engine refuses to produce authoritative numbers until the "
                f"equipment/equation engine resolves cleanly."
            ),
            severity="error",
        ))
        return ComputeOutput(
            deal_structure_id=inputs.deal.id,
            inputs_hash=_compute_inputs_hash(inputs),
            engine_version=ENGINE_VERSION,
            cashflow_schedule=[],
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Pre-COD
    # ------------------------------------------------------------------
    pre_cod = run_pre_cod(inputs)
    warnings.extend(pre_cod.warnings)

    pre_cod_rows = _pre_cod_summary_to_period_rows(inputs, pre_cod)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    ops = run_operations(inputs, pre_cod)
    warnings.extend(ops.warnings)

    full_schedule: list[PeriodRow] = pre_cod_rows + ops.period_rows

    # ------------------------------------------------------------------
    # COD test (projection)
    # ------------------------------------------------------------------
    cod_summary, cod_warnings = evaluate_cod_test(inputs, ops)
    warnings.extend(cod_warnings)

    # ------------------------------------------------------------------
    # Summary metrics
    # ------------------------------------------------------------------
    operating_cfads = [r.cfads_eur for r in ops.period_rows if r.cfads_eur is not None]
    operating_distributions = [r.distributions_eur for r in ops.period_rows]

    project_irr = compute_irr(operating_cfads, inputs.plant.capex_eur) if operating_cfads else None
    npv = compute_npv(
        operating_cfads,
        inputs.deal.discount_rate_pct / 100.0,
        inputs.plant.capex_eur,
    ) if operating_cfads else None

    equity_committed = inputs.total_equity_commitment_eur()
    equity_irr = (
        compute_equity_irr(operating_distributions, equity_committed)
        if equity_committed > 0 and operating_distributions else None
    )

    rating_band = compute_rating_band(ops.min_dscr, ops.llcr)

    binding_constraint = _identify_binding_constraint(inputs, pre_cod, ops, cod_summary)

    # Taghizadeh-Hesary commentary
    bank_debt = sum(
        t.commitment_eur for t in inputs.debt_tranches()
        if (t.lender_class or "").lower() == "commercial_bank"
    )
    bond_debt = sum(
        t.commitment_eur for t in inputs.debt_tranches()
        if t.tranche_type == TrancheType.SENIOR_BOND
        or (t.lender_class or "").lower() == "bond_market"
    )
    th_dict = taghizadeh_hesary_split(bank_debt, bond_debt)
    th = TaghizadehHesaryAssessment(**th_dict)

    return ComputeOutput(
        deal_structure_id=inputs.deal.id,
        inputs_hash=_compute_inputs_hash(inputs),
        engine_version=ENGINE_VERSION,
        cashflow_schedule=full_schedule,
        precod_summary=pre_cod.summary,
        cod_test_summary=cod_summary,
        project_irr=project_irr,
        equity_irr=equity_irr,
        npv_eur=npv,
        min_dscr_operations=ops.min_dscr,
        avg_dscr_operations=ops.avg_dscr,
        llcr=ops.llcr,
        rating_band=rating_band,
        binding_constraint=binding_constraint,
        covenant_breach_periods=ops.breach_periods,
        warnings=warnings,
        errors=errors,
        taghizadeh_hesary_assessment=th,
    )


def _pre_cod_summary_to_period_rows(inputs, pre_cod) -> list[PeriodRow]:
    """Project the pre-COD ratio points into PeriodRow shape so the UI gets
    a continuous schedule. Cashflow fields are zero — those don't exist
    pre-COD by definition; ratios are surfaced via precod_summary."""
    rows: list[PeriodRow] = []
    for pt in pre_cod.summary.period_rows:
        rows.append(PeriodRow(
            period_index=pt.period_index,
            period_start_date=pt.period_start_date,
            phase="construction",
            # No DSCR/CFADS pre-COD; intentionally left None.
            dscr=None,
            cfads_eur=None,
            idc_capitalised_eur=0.0,  # aggregated separately in precod_summary
        ))
    return rows


def _identify_binding_constraint(inputs, pre_cod, ops, cod_summary) -> str | None:
    if not cod_summary.projected_passed and cod_summary.blocking_conditions:
        return f"cod_test:{cod_summary.blocking_conditions[0]}"
    if ops.breach_periods:
        return "dscr_floor_breach"
    if pre_cod.summary.worst_breach:
        return f"precod:{pre_cod.summary.worst_breach}"
    if ops.min_dscr is not None and ops.min_dscr < 1.20:
        return "dscr_lockup_proximity"
    return None


def _compute_inputs_hash(inputs: DealInputs) -> str:
    """Stable hash over the canonical JSON representation of inputs.
    Used to detect stale outputs in the UI."""
    payload = inputs.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
