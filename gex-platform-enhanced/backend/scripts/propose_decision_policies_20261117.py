"""
Propose the decision-test thresholds found in code (handoff v4, task 6; JML 2026-11-17).

Every floor, hurdle and premium the platform used as a constant becomes ONE
`reference_parameter` row, state `proposed`, with the party it belongs to, its
context (instrument, stage, scenario), its effective date and its source. The
source of every row is a GEX code constant: no external document was found for
any of them, so none is an institution's ESTABLISHED policy. A DFI's hurdle is
recorded with that DFI as party and no reference, which keeps it "GEX proposed".

NOTHING IS APPROVED HERE. JML approves GEX defaults; an institution's policy is
established only by its own reference. Until then every decision test reads
"no approved threshold — no pass/fail", with these values shown as GEX proposed.

Idempotent: a (key, party) already proposed by this script is skipped. Dry run
unless --execute. After an Alembic rebuild run it again (a dump restore carries it).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402

PROPOSER = "POLICY_PROPOSAL_20261117"
TODAY = "2026-11-17"


def row(key, value, unit, party, context, where, note=""):
    return {
        "parameter_key": key, "value_base": value, "unit": unit, "source_class": "gex_assumption",
        "source_name": f"GEX code constant ({where}); no external source found",
        "retrieved_at": TODAY, "valid_from": TODAY, "policy_party": party, "policy_context": context,
        "note": ("PROPOSED from a code constant, unsourced. " + note).strip(),
    }


SENIOR = {"instrument": "senior debt", "stage": "credit decision"}
EQUITY = {"instrument": "project equity", "stage": "investment decision"}

PROPOSALS = [
    row("dscr_floor_p50", 1.30, "-", "GEX", {**SENIOR, "scenario": "P50"},
        "structuring_engine.py analyze_gaps; DSCRHeatmap.tsx 'Target DSCR 1.30x'; BankersSnapshot.tsx"),
    row("dscr_floor_p90", 1.20, "-", "GEX", {**SENIOR, "scenario": "P90"},
        "structuring_engine.py; DSCRHeatmap.tsx 'Covenant floor 1.20x'; CovenantsPage.tsx 1.3/1.2"),
    row("dscr_covenant_floor", 1.25, "-", "GEX", {**SENIOR, "stage": "operations (lock-up)", "scenario": "P50"},
        "FinanceDashboardPage.tsx:297 'covenant >= 1.25x'; Breizh workbook covenant floor 1.25",
        "Note: four different DSCR floors appear in code (1.30/1.20, 1.25, 1.3/1.2, 1.10)."),
    row("dscr_default_floor", 1.10, "-", "GEX", {**SENIOR, "stage": "credit decision", "scenario": "P90"},
        "deal_killers.py DK_DSCR_BELOW_FLOOR 'dscr_p90 < 1.10'"),
    row("llcr_floor", 1.20, "-", "GEX", {**SENIOR, "scenario": "base"},
        "BankersSnapshot.tsx LLCR bands 1.4 / 1.2"),
    row("wacc_target_max", 0.08, "fraction", "GEX", {**EQUITY, "scenario": "base"},
        "structuring_engine.py 'WACC above 8.0% target'"),
    row("offtake_coverage_min", 0.70, "fraction", "GEX", {**SENIOR, "scenario": "base"},
        "structuring_engine.py 'below 70% minimum'",
        "Distinct from the gate engine's 60% heads-of-terms bar at COMMERCIALLY_PLAUSIBLE (rules 4.1.0), which is a gate rule, not this decision test."),
    row("regulatory_premium_max", 0.003, "fraction", "GEX", {**EQUITY, "scenario": "base"},
        "structuring_engine.py '<30bps for investment-grade jurisdictions'"),
    row("project_risk_premium", 0.01, "fraction", "GEX", {**EQUITY, "scenario": "base"},
        "frontend returnsModel.ts default input"),
    row("technology_risk_premium", 0.03, "fraction", "GEX", {**EQUITY, "scenario": "base"},
        "frontend returnsModel.ts default input"),
    row("sponsor_equity_hurdle", 0.12, "fraction", "GEX", {**EQUITY, "scenario": "base"},
        "additionality.py commercial_hurdle_rate default 0.12"),
]
DFI = {"EIB": (0.092, 2.5), "KFW": (0.090, 2.0), "IFC": (0.085, 3.0),
       "BPIFRANCE": (0.090, 2.0), "DFC": (0.100, 2.5), "AFDB": (0.080, 2.0)}
for party, (hurdle, catalytic) in DFI.items():
    ctx = {"instrument": "DFI concessional finance", "stage": "additionality assessment"}
    PROPOSALS.append(row("dfi_irr_hurdle", hurdle, "fraction", party, ctx,
                         "additionality.py DFI_HURDLE_RATES",
                         f"Attributed to {party} as party but NOT {party}'s established policy: no reference found."))
    PROPOSALS.append(row("dfi_catalytic_ratio_min", catalytic, "-", party, ctx,
                         "additionality.py DFI_CATALYTIC_MINIMUMS",
                         f"Attributed to {party} as party but NOT {party}'s established policy: no reference found."))


def load(conn) -> int:
    inserted = 0
    for p in PROPOSALS:
        exists = conn.execute(
            "SELECT 1 FROM reference_parameter WHERE parameter_key = ? AND COALESCE(policy_party,'') = ? "
            "AND proposed_by = ?", (p["parameter_key"], p["policy_party"], PROPOSER)).fetchone()
        if exists:
            continue
        reg.propose(conn, p, actor=PROPOSER)
        inserted += 1
    return inserted


def main(execute: bool) -> int:
    from app.core.db_backend import fuelref_connection, require_postgres
    require_postgres(reg.registry_available(), "The reference registry", "FUELREF_DB_BACKEND")
    conn = fuelref_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held reference data
    try:
        inserted = load(conn)
        if execute:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    print(f"{'proposed' if execute else 'would propose'} {inserted} of {len(PROPOSALS)} rows "
          f"(proposer {PROPOSER}); none approved.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
