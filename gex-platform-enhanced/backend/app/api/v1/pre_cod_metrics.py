"""
pre_cod_metrics.py
==================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Pre-COD Financial Intelligence Engine.

Doctrine (GEX Bridge Document v3.1):
  Green fuel projects until COD have a burn-rate-and-progression problem,
  not a coverage-ratio problem. Standard project finance answers this with
  LLCR and Sources & Uses — both forward-looking, both pre-COD-appropriate,
  neither sufficient alone. GEX is unusually well-positioned to surface a
  small, named set of pre-COD KPIs computed continuously from live platform
  data. Four GEX-native metrics. Two standard PF metrics. DSCR demoted to
  a forward-projection footnote until T-2 quarters from COD.

─── THE METRICS ──────────────────────────────────────────────────────────────

GEX-NATIVE (require the package state machine — unique to this platform):

  CEC — Capital Eligibility Coverage
        Share of total CAPEX where the Development Package is EVIDENCED or
        beyond on the 10-state workflow. Rises monotonically as the project
        matures. Bank-grade pre-FID readiness measure. Superior to a raw
        evidence-count ratio because it uses the enforced state machine:
        a package cannot reach EVIDENCED without passing the transition
        guards in development_packages.py. Ungameable.

  FRI — FID Readiness Index
        Share of FID-critical CAPEX (FID + Construction phase packages) at
        AACE Class 3 estimate maturity or tighter. Senior lenders enforce
        Class 3 as the hard FID floor. Already computed in
        development_packages.py → fid_readiness_pct. Surfaced here as a
        primary metric, not buried in a summary object.

  RMR — Runway-to-Milestone Ratio
        Months of committed cash on hand ÷ Months to the next gated
        milestone (G6 IE sign-off, G9 permits, G10 financial close).
        >1.0 = you reach the milestone with cash to spare.
        <1.0 = funding-constrained against the critical path.
        Cleaner than raw burn rate because it indexes to actual delivery.
        Requires: committed cash position + milestone target dates.

  CBM — Cohort Burn Multiple
        Project burn rate ÷ Cohort median burn rate (same bankability state,
        same scale band). Adjacency Doctrine native. <1.0 = leaner than
        peers; >1.0 = burning hot. Requires the adjacency cohort endpoint
        (Vademecum §3.5). Returns PENDING when cohort data is unavailable.

STANDARD PF (not GEX-native but expected in the lender pack):

  LLCR — Loan Life Coverage Ratio
        PV of CFADS over loan life ÷ Outstanding debt. Forward-looking.
        Computed from gex_pf_engine/cfads.py. Requires post-FID financial
        model inputs (debt schedule, forecast CFADS).

  SUC  — Sources & Uses Coverage
        Total committed capital sources ÷ Total identified uses (CAPEX +
        cost to complete + contingency + DSRA). >1.0 = fully funded.
        The pre-COD equivalent of the balance sheet solvency test.

DSCR TREATMENT:
  - Present in the model for the credit memo only
  - Never leads the investor update before COD
  - Surfaced here as dscr_forward_projection only — a point-in-time
    projection of DSCR at COD, not a current-period measurement
  - Promoted to primary metric only inside T-2 quarters from COD

─── INTEGRATION ──────────────────────────────────────────────────────────────
  Consumes:  development_packages.py → /project/{id}/summary
  Consumes:  gex_pf_engine → /api/v1/model/cfads/calculate (for LLCR)
  Consumes:  gex_pf_engine → /api/v1/bankability/evaluate (milestone dates)
  Consumes:  adjacency engine (Vademecum §3.5) → cohort stats (when live)
  Surfaces:  Finance workspace → FinanceBankabilityView (pre-G10 panel)
  Surfaces:  Producer workspace → ProducerBankabilityView
  Surfaces:  Executive workspace → StrategicOverview
  Feeds:     Trust Score v1 composite (Vademecum task 2.3)
  Feeds:     CFO monthly investor update (one-pager generator)

─── ABAC ─────────────────────────────────────────────────────────────────────
  PRODUCER:       CEC, FRI, RMR — own project only
  FINANCE/BANKER: all six metrics + DSCR forward projection
  DFI:            all six + additionality cross-reference
  EXECUTIVE:      all six + portfolio rollup (CBM across pipeline)
  REGULATOR:      CEC + FRI only (evidence completeness view)

Route prefix: /api/v1/pre-cod-metrics
"""

import hashlib
import sqlite3
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

# Ticket 7b — single source of truth. Pre-COD metrics CONSUME development
# packages (CEC/FRI), so they must read the SAME store development_packages.py
# writes to. Previously hard-coded to a second database file, which made the
# metrics 404 ("no packages") for projects whose packages live in the platform DB.
from app.core.config import settings
DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/pre-cod-metrics", tags=["pre-cod-metrics"])


# ════════════════════════════════════════════════════════════════════════════
# STATUS HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _status(value: float, warn: float, target: float,
            invert: bool = False) -> str:
    """
    HEALTHY / CAUTION / CONCERN / BLOCKED.
    invert=True: lower value is better (CBM, burn rate metrics).
    """
    if invert:
        if value <= warn:   return "HEALTHY"
        if value <= target: return "CAUTION"
        return "CONCERN"
    if value >= target: return "HEALTHY"
    if value >= warn:   return "CAUTION"
    if value > 0:       return "CONCERN"
    return "BLOCKED"


# ════════════════════════════════════════════════════════════════════════════
# GOVERNANCE — provenance before completeness (no naked finance numbers)
# ════════════════════════════════════════════════════════════════════════════
# Every pre-COD ratio carries this stamp. A forward-looking finance number
# without scenario + basis + reliance is the Finance equivalent of the
# fabricated "P&L MTD" tile removed from Commercial. Bump on any change to the
# rule set (RULES) or the computation (MODEL).
PRE_COD_RULES_VERSION = "PF_RULES_2026_06"   # the rule set (thresholds, gate logic)
PRE_COD_MODEL_VERSION = "precod-1.0"          # the computation engine version
# Anti-theatre: every stamp field is REAL or honestly PENDING/NOT_SET — never a
# fake default. data_basis says how trustworthy the INPUTS are, not the maths.
DATA_BASIS_VALUES = ("SEED", "ILLUSTRATIVE", "DEAL_TERMS", "THIRD_PARTY", "VERIFIED", "MARKET")


class PreCODGovernance(BaseModel):
    """Panel-level assumption stamp for the whole pre-COD report."""
    scenario_id:          str   = Field("UNSPECIFIED", description="Named scenario, e.g. BASE_CASE_v0")
    assumption_set_id:    str   = Field(..., description="sha of the input bundle — same scenario, different inputs ⇒ different id")
    rules_version:        str   = PRE_COD_RULES_VERSION
    model_version:        str   = PRE_COD_MODEL_VERSION
    data_basis:           str   = Field("SEED", description=f"one of {DATA_BASIS_VALUES} — input trustworthiness, not maths")
    reliance:             str   = "ANALYTICAL_PREVIEW_NOT_CREDIT_APPROVED"
    input_completeness_pct: float = Field(..., description="share of metrics with real inputs (rest PENDING)")
    verified_by:          str   = "NOT_INDEPENDENTLY_VERIFIED"
    computed_at:          str


# ════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ════════════════════════════════════════════════════════════════════════════

class MetricResult(BaseModel):
    """Single metric with value, interpretation, and steering action."""
    value:          float
    formatted:      str   = Field(..., description="Display string e.g. '74%', '1.3x', '42/100'")
    status:         str   = Field(..., description="HEALTHY | CAUTION | CONCERN | BLOCKED | PENDING")
    threshold_warn: float
    threshold_target: float
    next_action:    str
    gate_relevance: str   = Field(..., description="Which GEX gate this metric primarily steers")
    data_freshness: str   = Field("live", description="live | stale | estimated | pending")
    # Per-metric provenance — DERIVED from status, never hand-typed (anti-drift).
    known_limitation: Optional[str] = Field(None, description="Why this number is not yet fully reliable; derived from status")


class LLCRInput(BaseModel):
    pv_cfads_over_loan_life: float = Field(..., description="PV of CFADS over loan tenor (EUR M)")
    outstanding_debt_eur:    float = Field(..., description="Total outstanding debt at time of calc (EUR M)")


class SUCInput(BaseModel):
    total_committed_sources_eur: float = Field(..., description="All committed capital (EUR M)")
    capex_remaining_eur:         float = Field(..., description="Remaining CAPEX to spend (EUR M)")
    cost_to_complete_eur:        float = Field(..., description="Est. cost to complete (EUR M)")
    contingency_eur:             float = Field(..., description="Uncommitted contingency reserve (EUR M)")
    dsra_required_eur:           float = Field(..., description="DSRA funding required at COD (EUR M)")


class RMRInput(BaseModel):
    cash_on_hand_eur:          float = Field(..., description="Committed undrawn capital available now (EUR M)")
    monthly_burn_eur:          float = Field(..., description="Average monthly spend last 3 months (EUR M)")
    months_to_next_milestone:  float = Field(..., gt=0, description="Calendar months to next gate milestone")
    next_milestone_gate:       str   = Field(..., description="e.g. G10, G6, G9")


class CohortInput(BaseModel):
    project_monthly_burn_eur:   float = Field(..., description="This project's monthly burn (EUR M)")
    cohort_median_burn_eur:     Optional[float] = Field(None, description="Cohort median monthly burn (EUR M). None = not yet available.")
    cohort_size:                int   = Field(0, description="Number of projects in cohort")
    bankability_state:          str   = Field(..., description="Current GEX bankability state for cohort matching")
    scale_band:                 str   = Field(..., description="e.g. '100-200MW' — scale band for cohort matching")


class PreCODRequest(BaseModel):
    """Full request body for the pre-COD metrics computation."""
    project_id:     str
    rmr:            Optional[RMRInput]   = None
    cohort:         Optional[CohortInput] = None
    llcr:           Optional[LLCRInput]  = None
    suc:            Optional[SUCInput]   = None
    dscr_at_cod_projection: Optional[float] = Field(
        None,
        description="Forward-projected DSCR at COD from PF engine. "
                    "Displayed as footnote only until T-2 quarters from COD."
    )
    months_to_cod:  Optional[float] = Field(None, description="Months remaining to COD")
    scenario_id:    str = Field("UNSPECIFIED", description="Named scenario for the assumption stamp, e.g. BASE_CASE_v0")
    data_basis:     str = Field("SEED", description=f"Input trustworthiness — one of {DATA_BASIS_VALUES}")
    save_snapshot:  bool = False


class PreCODReport(BaseModel):
    """
    The pre-COD financial intelligence report.
    DSCR is a footnote — not the headline — until T-2 quarters from COD.
    """
    project_id:         str
    computed_at:        str
    bankability_state:  str
    months_to_cod:      Optional[float]

    # GOVERNANCE — panel-level assumption stamp (provenance before completeness)
    governance:         PreCODGovernance

    # GEX-NATIVE
    cec: MetricResult
    fri: MetricResult
    rmr: MetricResult
    cbm: MetricResult

    # STANDARD PF
    llcr: MetricResult
    suc:  MetricResult

    # DSCR FOOTNOTE
    dscr_applicable:        bool  = False
    dscr_forward_projection: Optional[float] = None
    dscr_note:              str   = (
        "DSCR is not a current-period metric before COD. "
        "The figure above is a forward projection at COD from the PF engine. "
        "It becomes the primary covenant metric only post-COD (post-G11). "
        "See gex_pf_engine POST_COD for the live model."
    )
    dscr_promoted:          bool  = Field(
        False,
        description="True only if months_to_cod <= 6 — promotes DSCR to primary view."
    )

    # COMPOSITE
    overall_score:          float
    fid_readiness_signal:   str
    capital_gap_eur:        float
    blocked_packages:       int
    one_liner:              str


# ════════════════════════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════════════════════════

def get_db():
    # check_same_thread=False: FastAPI runs sync endpoints across threadpool
    # workers (per-request connection, not shared concurrently).
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Snapshot table for trend tracking. Call from main.py startup."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pre_cod_snapshots (
            snapshot_id     TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            computed_at     TEXT NOT NULL,
            cec_value       REAL,
            fri_value       REAL,
            rmr_value       REAL,
            cbm_value       REAL,
            llcr_value      REAL,
            suc_value       REAL,
            overall_score   REAL,
            fid_signal      TEXT,
            capital_gap_eur REAL,
            report_json     TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pcs_project ON pre_cod_snapshots(project_id)"
    )
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════════════════════
# METRIC COMPUTATIONS
# ════════════════════════════════════════════════════════════════════════════

def _compute_cec(packages: list) -> MetricResult:
    ELIGIBLE_STATES = {
        "evidenced", "eligible", "approved",
        "committed", "drawable", "drawn", "closed"
    }
    total_cost = sum(p["cost_amount"] for p in packages) or 1.0
    eligible_cost = sum(
        p["cost_amount"] for p in packages
        if p["workflow_state"] in ELIGIBLE_STATES
    )
    value = eligible_cost / total_cost
    evidenced_count = sum(1 for p in packages if p["workflow_state"] in ELIGIBLE_STATES)

    return MetricResult(
        value=value,
        formatted=f"{value*100:.1f}% ({evidenced_count}/{len(packages)} packages)",
        status=_status(value, 0.50, 0.85),
        threshold_warn=0.50,
        threshold_target=0.85,
        next_action=(
            "Advance packages from IDENTIFIED/SCOPED/COSTED to EVIDENCED. "
            "Prioritise FID-critical packages (G5/G8/G10 gates, Construction phase). "
            "Each transition requires at least one SHA-256 evidence ref."
            if value < 0.85 else
            "CEC target met. Maintain state as new packages are created."
        ),
        gate_relevance="G8 — Audit-Grade Financial Model | G10 — Financial Close",
        data_freshness="live",
    )


def _compute_fri(packages: list) -> MetricResult:
    FID_PHASES     = {"FID", "CONSTRUCTION"}
    CLASS3_PLUS    = {"CLASS_3", "CLASS_2", "CLASS_1"}

    fid_packages = [p for p in packages if p["phase_required"] in FID_PHASES]
    if not fid_packages:
        return MetricResult(
            value=0.0, formatted="0% (no FID packages yet)",
            status="BLOCKED",
            threshold_warn=0.50, threshold_target=1.00,
            next_action="Create FID and Construction phase packages in PLANT_BUILDER.",
            gate_relevance="G5 — EPC & Construction | G10 — Financial Close",
            data_freshness="live",
        )

    total_fid_cost = sum(p["cost_amount"] for p in fid_packages) or 1.0
    class3_cost    = sum(
        p["cost_amount"] for p in fid_packages
        if p["estimate_class"] in CLASS3_PLUS
    )
    value = class3_cost / total_fid_cost

    return MetricResult(
        value=value,
        formatted=f"{value*100:.1f}% of FID-critical CAPEX at Class 3+",
        status=_status(value, 0.50, 1.00),
        threshold_warn=0.50,
        threshold_target=1.00,
        next_action=(
            f"{(1-value)*100:.0f}% of FID-critical CAPEX is still at Class 4/5. "
            "Commission FEED engineering to achieve Class 3 before FID sanction. "
            "Lenders will not approve credit committee paper below Class 3."
            if value < 1.00 else
            "All FID-critical CAPEX at Class 3 or tighter. "
            "Cost basis is credible for lender underwriting."
        ),
        gate_relevance="G5 — EPC & Construction | G8 — Financial Model",
        data_freshness="live",
    )


def _compute_rmr(rmr_input: Optional[RMRInput]) -> MetricResult:
    if not rmr_input:
        return MetricResult(
            value=0.0,
            formatted="PENDING — supply cash_on_hand, monthly_burn, months_to_milestone",
            status="PENDING",
            threshold_warn=0.75,
            threshold_target=1.00,
            next_action=(
                "Supply RMR inputs: POST /api/v1/pre-cod-metrics/{project_id} "
                "with rmr.cash_on_hand_eur, rmr.monthly_burn_eur, "
                "rmr.months_to_next_milestone, rmr.next_milestone_gate. "
                "Cash position from CAPITAL_STACK committed drawdowns. "
                "Burn rate from SPEND_WAVE 3-month rolling average."
            ),
            gate_relevance="G6 — IE Sign-off | G9 — Permits | G10 — Financial Close",
            data_freshness="pending",
        )

    if rmr_input.monthly_burn_eur <= 0:
        return MetricResult(
            value=0.0, formatted="0.0x (zero burn — check spend wave data)",
            status="CONCERN",
            threshold_warn=0.75, threshold_target=1.00,
            next_action="Monthly burn is zero or negative. Verify SPEND_WAVE data.",
            gate_relevance="G10 — Financial Close",
            data_freshness="stale",
        )

    runway_months = rmr_input.cash_on_hand_eur / rmr_input.monthly_burn_eur
    value = runway_months / rmr_input.months_to_next_milestone

    if value < 0.5:
        action = (
            f"CRITICAL: Only {runway_months:.1f} months of runway to reach "
            f"{rmr_input.next_milestone_gate} ({rmr_input.months_to_next_milestone:.0f} months away). "
            "Immediate action: commit additional capital or accelerate milestone."
        )
    elif value < 1.0:
        action = (
            f"Runway ({runway_months:.1f} months) is shorter than milestone distance "
            f"({rmr_input.months_to_next_milestone:.0f} months to {rmr_input.next_milestone_gate}). "
            "Bridge financing or accelerated capital commitment required."
        )
    else:
        action = (
            f"Runway of {runway_months:.1f} months covers {rmr_input.next_milestone_gate} "
            f"({rmr_input.months_to_next_milestone:.0f} months) with {runway_months - rmr_input.months_to_next_milestone:.1f} months buffer. "
            "Monitor monthly burn against progression."
        )

    return MetricResult(
        value=round(value, 2),
        formatted=f"{value:.2f}x ({runway_months:.1f} months runway -> {rmr_input.next_milestone_gate})",
        status=_status(value, 0.75, 1.00),
        threshold_warn=0.75,
        threshold_target=1.00,
        next_action=action,
        gate_relevance=f"{rmr_input.next_milestone_gate} (next milestone)",
        data_freshness="live",
    )


def _compute_cbm(cohort_input: Optional[CohortInput]) -> MetricResult:
    if not cohort_input or cohort_input.cohort_median_burn_eur is None:
        return MetricResult(
            value=0.0,
            formatted="PENDING — adjacency engine not yet live",
            status="PENDING",
            threshold_warn=1.20,
            threshold_target=0.80,
            next_action=(
                "CBM requires the adjacency engine (Vademecum S3.5 — Tier 2 roadmap). "
                "When live, supply cohort_median_burn_eur from the adjacency nearest-neighbour "
                f"endpoint filtered by bankability_state='{cohort_input.bankability_state if cohort_input else 'unknown'}' "
                f"and scale_band='{cohort_input.scale_band if cohort_input else 'unknown'}'. "
                "Until then, this tile shows PENDING and does not affect the overall score."
            ),
            gate_relevance="All gates — efficiency benchmark across project lifecycle",
            data_freshness="pending",
        )

    if cohort_input.cohort_median_burn_eur <= 0:
        return MetricResult(
            value=0.0, formatted="0.0x (invalid cohort median)",
            status="PENDING",
            threshold_warn=1.20, threshold_target=0.80,
            next_action="Cohort median is zero. Verify adjacency engine cohort data.",
            gate_relevance="All gates",
            data_freshness="stale",
        )

    value = cohort_input.project_monthly_burn_eur / cohort_input.cohort_median_burn_eur

    if value <= 0.80:
        action = (
            f"Burning {value:.2f}x cohort median — operationally lean. "
            f"Cohort: {cohort_input.cohort_size} projects at "
            f"{cohort_input.bankability_state} / {cohort_input.scale_band}."
        )
    elif value <= 1.20:
        action = (
            f"Within-band burn rate ({value:.2f}x cohort median). "
            "Normal variance. Continue monitoring monthly."
        )
    else:
        action = (
            f"Burning {value:.2f}x cohort median — above peer group. "
            "Review spend categories: where is excess burn concentrated? "
            "Owner team costs, advisory fees, or certification scope?"
        )

    return MetricResult(
        value=round(value, 2),
        formatted=f"{value:.2f}x cohort median (n={cohort_input.cohort_size})",
        status=_status(value, 1.20, 0.80, invert=True),
        threshold_warn=1.20,
        threshold_target=0.80,
        next_action=action,
        gate_relevance="All gates — cross-project efficiency benchmark",
        data_freshness="live" if cohort_input.cohort_size > 0 else "estimated",
    )


def _compute_llcr(llcr_input: Optional[LLCRInput]) -> MetricResult:
    if not llcr_input:
        return MetricResult(
            value=0.0,
            formatted="PENDING — supply pv_cfads and outstanding_debt",
            status="PENDING",
            threshold_warn=1.10,
            threshold_target=1.40,
            next_action=(
                "LLCR requires PF engine output. "
                "POST /api/v1/finance-model/model/lifetime to get projected CFADS, "
                "then supply pv_cfads_over_loan_life and outstanding_debt_eur here."
            ),
            gate_relevance="G8 — Audit-Grade Financial Model | G10 — Financial Close",
            data_freshness="pending",
        )

    if llcr_input.outstanding_debt_eur <= 0:
        return MetricResult(
            value=0.0, formatted="N/A (no debt yet)",
            status="PENDING",
            threshold_warn=1.10, threshold_target=1.40,
            next_action="No outstanding debt. LLCR applies once debt is committed.",
            gate_relevance="G10 — Financial Close",
            data_freshness="pending",
        )

    value = llcr_input.pv_cfads_over_loan_life / llcr_input.outstanding_debt_eur

    return MetricResult(
        value=round(value, 3),
        formatted=f"{value:.2f}x LLCR",
        status=_status(value, 1.10, 1.40),
        threshold_warn=1.10,
        threshold_target=1.40,
        next_action=(
            "LLCR below 1.10 — loan life coverage is insufficient. "
            "Extend tenor, reduce debt quantum, or improve CFADS forecast."
            if value < 1.10 else
            f"LLCR at {value:.2f}x — {'above' if value >= 1.40 else 'within acceptable range of'} target 1.40x."
        ),
        gate_relevance="G8 — Audit-Grade Financial Model",
        data_freshness="estimated",
    )


def _compute_suc(suc_input: Optional[SUCInput]) -> MetricResult:
    if not suc_input:
        return MetricResult(
            value=0.0,
            formatted="PENDING — supply committed_sources and total_uses breakdown",
            status="PENDING",
            threshold_warn=0.90,
            threshold_target=1.00,
            next_action=(
                "Supply SUC inputs: total_committed_sources_eur, "
                "capex_remaining_eur, cost_to_complete_eur, "
                "contingency_eur, dsra_required_eur."
            ),
            gate_relevance="G10 — Financial Close",
            data_freshness="pending",
        )

    total_uses = (
        suc_input.capex_remaining_eur +
        suc_input.cost_to_complete_eur +
        suc_input.contingency_eur +
        suc_input.dsra_required_eur
    )
    if total_uses <= 0:
        return MetricResult(
            value=1.0, formatted="1.00x (no remaining uses)",
            status="HEALTHY",
            threshold_warn=0.90, threshold_target=1.00,
            next_action="All uses settled.",
            gate_relevance="G10 — Financial Close",
            data_freshness="live",
        )

    value = suc_input.total_committed_sources_eur / total_uses
    gap = max(0.0, total_uses - suc_input.total_committed_sources_eur)

    return MetricResult(
        value=round(value, 3),
        formatted=f"{value:.2f}x S&U coverage" + (f" (gap: EUR {gap/1e6:.1f}M)" if gap > 0 else ""),
        status=_status(value, 0.90, 1.00),
        threshold_warn=0.90,
        threshold_target=1.00,
        next_action=(
            f"Funding gap of EUR {gap/1e6:.1f}M. "
            "Identify unfunded use categories: CAPEX remaining, cost to complete, contingency, or DSRA. "
            "Commit additional capital or reduce contingency if sufficiently evidenced."
            if gap > 0 else
            f"All uses covered at {value:.2f}x. S&U balance confirmed."
        ),
        gate_relevance="G10 — Financial Close",
        data_freshness="live",
    )


# ════════════════════════════════════════════════════════════════════════════
# COMPOSITE SCORING
# ════════════════════════════════════════════════════════════════════════════

def _overall(cec: float, fri: float, rmr: float, cbm: float,
             llcr: float, suc: float) -> float:
    """
    Weighted composite (0-100). PENDING metrics excluded from denominator.
    Weights: SUC 30%, CEC 25%, FRI 20%, RMR 15%, LLCR 7%, CBM 3%.
    """
    weights = {"suc": 0.30, "cec": 0.25, "fri": 0.20,
               "rmr": 0.15, "llcr": 0.07, "cbm": 0.03}
    total_w = 0.0
    score   = 0.0

    contributions = {
        "cec":  (min(cec, 1.0), weights["cec"]),
        "fri":  (min(fri, 1.0), weights["fri"]),
        "rmr":  (min(rmr / 2.0, 1.0) if rmr > 0 else 0.0, weights["rmr"]),
        "cbm":  (max(0.0, 1.0 - (cbm - 0.8)) if cbm > 0 else None, weights["cbm"]),
        "llcr": (min((llcr - 1.0) / 0.4, 1.0) if llcr > 1.0 else 0.0, weights["llcr"]),
        "suc":  (min(suc, 1.0) if suc > 0 else 0.0, weights["suc"]),
    }
    for k, (v, w) in contributions.items():
        if v is None:
            continue
        score   += v * w
        total_w += w

    if total_w == 0:
        return 0.0
    return round((score / total_w) * 100, 1)


def _signal(cec: float, fri: float, rmr: float, suc: float) -> str:
    hard_blockers = sum([cec < 0.50, fri < 0.50, suc < 0.90])
    soft_concerns = sum([cec < 0.85, fri < 1.00, (0 < rmr < 1.00), suc < 1.00])
    if hard_blockers >= 2:   return "NOT_READY"
    if hard_blockers == 1:   return "PROGRESSING"
    if soft_concerns >= 3:   return "APPROACHING"
    return "READY"


def _one_liner(signal: str, cec: float, fri: float,
               rmr_val: float, suc_val: float, gap: float) -> str:
    if signal == "NOT_READY":
        return (
            f"Project has hard blockers: CEC {cec*100:.0f}%, FRI {fri*100:.0f}% — "
            "evidence and cost-basis maturity are insufficient for FID."
        )
    if signal == "PROGRESSING":
        return (
            f"Progressing — CEC {cec*100:.0f}%, FRI {fri*100:.0f}%, "
            f"S&U {'covered' if suc_val >= 1.0 else f'gap EUR {gap/1e6:.1f}M'}. "
            "One or more metrics below lender threshold."
        )
    if signal == "APPROACHING":
        return (
            f"Approaching FID readiness — CEC {cec*100:.0f}%, FRI {fri*100:.0f}%, "
            f"RMR {rmr_val:.2f}x. Close remaining gaps for credit committee."
        )
    return (
        f"FID-ready — CEC {cec*100:.0f}%, FRI {fri*100:.0f}%, "
        f"S&U covered, RMR {rmr_val:.2f}x. Proceed to G10 preparation."
    )


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}", response_model=PreCODReport, status_code=200)
def compute_pre_cod_metrics(
    project_id: str,
    body: PreCODRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    packages_raw = db.execute(
        "SELECT * FROM development_packages WHERE project_id=?", (project_id,)
    ).fetchall()

    if not packages_raw:
        raise HTTPException(
            404,
            f"No development packages found for project {project_id}. "
            "Create packages via POST /api/v1/packages before computing metrics."
        )

    packages = [dict(r) for r in packages_raw]

    # Infer bankability state from package phase maturity
    phase_order = ["FEL_1", "FEL_2", "FEED", "FID", "CONSTRUCTION"]
    phases = {p["phase_required"] for p in packages}
    max_phase = max(phases, key=lambda x: phase_order.index(x) if x in phase_order else -1)
    phase_to_state = {
        "FEL_1": "SPECULATIVE", "FEL_2": "TECHNICALLY_PLAUSIBLE",
        "FEED": "COMMERCIALLY_PLAUSIBLE", "FID": "BUILDABLE",
        "CONSTRUCTION": "STRUCTURALLY_BANKABLE",
    }
    bankability_state = phase_to_state.get(max_phase, "SPECULATIVE")

    # Compute all six metrics
    cec_r = _compute_cec(packages)
    fri_r = _compute_fri(packages)
    rmr_r = _compute_rmr(body.rmr)
    cbm_r = _compute_cbm(body.cohort)
    llcr_r = _compute_llcr(body.llcr)
    suc_r  = _compute_suc(body.suc)

    # Capital gap and blocked packages
    COMMITTED = {"committed", "drawable", "drawn", "closed"}
    REQUIRED  = {"eligible", "approved", "committed", "drawable", "drawn"}
    committed_eur = sum(p["cost_amount"] for p in packages if p["workflow_state"] in COMMITTED)
    required_eur  = sum(p["cost_amount"] for p in packages if p["workflow_state"] in REQUIRED)
    capital_gap   = max(0.0, required_eur - committed_eur)
    blocked       = sum(1 for p in packages if p["workflow_state"] in ("identified", "scoped"))

    # Composite
    cbm_val  = cbm_r.value  if cbm_r.status  != "PENDING" else 0.0
    rmr_val  = rmr_r.value  if rmr_r.status  != "PENDING" else 0.0
    llcr_val = llcr_r.value if llcr_r.status != "PENDING" else 0.0
    suc_val  = suc_r.value  if suc_r.status  != "PENDING" else 0.0

    overall = _overall(
        cec_r.value, fri_r.value, rmr_val, cbm_val, llcr_val, suc_val
    )
    signal = _signal(cec_r.value, fri_r.value, rmr_val, suc_val)
    liner  = _one_liner(
        signal, cec_r.value, fri_r.value, rmr_val, suc_val, capital_gap
    )

    # DSCR treatment
    months_to_cod = body.months_to_cod
    dscr_promoted = bool(months_to_cod is not None and months_to_cod <= 6)

    now = datetime.now(timezone.utc).isoformat()

    # ── Governance stamp (Step 1) ────────────────────────────────────────────
    # Per-metric limitation is DERIVED from status (never hand-typed). A PENDING
    # metric states which input it is missing, so the limitation can't drift.
    _missing = {
        "LLCR": "requires PV(CFADS) over loan life + outstanding debt (post-FID model)",
        "SUC":  "requires committed sources + identified uses (S&U inputs)",
        "RMR":  "requires committed cash + months-to-milestone inputs",
        "CBM":  "requires the adjacency cohort median (not yet live)",
    }
    for nm, m in (("CEC", cec_r), ("FRI", fri_r), ("RMR", rmr_r), ("CBM", cbm_r), ("LLCR", llcr_r), ("SUC", suc_r)):
        m.known_limitation = (
            _missing.get(nm, "input not supplied") if m.status == "PENDING"
            else ("estimate — not independently verified" if m.data_freshness in ("estimated", "stale") else None)
        )
    _all = [cec_r, fri_r, rmr_r, cbm_r, llcr_r, suc_r]
    completeness = round(100.0 * sum(1 for m in _all if m.status != "PENDING") / len(_all), 1)
    _basis = body.data_basis if body.data_basis in DATA_BASIS_VALUES else "SEED"
    governance = PreCODGovernance(
        scenario_id=body.scenario_id or "UNSPECIFIED",
        assumption_set_id=hashlib.sha256(
            body.model_dump_json().encode()
        ).hexdigest()[:12],
        data_basis=_basis,
        input_completeness_pct=completeness,
        computed_at=now,
    )

    report = PreCODReport(
        project_id=project_id,
        computed_at=now,
        bankability_state=bankability_state,
        months_to_cod=months_to_cod,
        governance=governance,
        cec=cec_r,
        fri=fri_r,
        rmr=rmr_r,
        cbm=cbm_r,
        llcr=llcr_r,
        suc=suc_r,
        dscr_applicable=dscr_promoted,
        dscr_forward_projection=body.dscr_at_cod_projection,
        dscr_promoted=dscr_promoted,
        overall_score=overall,
        fid_readiness_signal=signal,
        capital_gap_eur=capital_gap,
        blocked_packages=blocked,
        one_liner=liner,
    )

    if body.save_snapshot:
        db.execute("""
            INSERT INTO pre_cod_snapshots
            (snapshot_id, project_id, computed_at, cec_value, fri_value,
             rmr_value, cbm_value, llcr_value, suc_value,
             overall_score, fid_signal, capital_gap_eur, report_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(uuid.uuid4()), project_id, now,
            cec_r.value, fri_r.value, rmr_val, cbm_val, llcr_val, suc_val,
            overall, signal, capital_gap, report.model_dump_json()
        ))
        db.commit()

    return report


@router.get("/{project_id}/history")
def get_metric_history(
    project_id: str,
    limit: int = Query(20, le=100),
    db: sqlite3.Connection = Depends(get_db)
):
    rows = db.execute("""
        SELECT snapshot_id, computed_at, cec_value, fri_value, rmr_value,
               cbm_value, llcr_value, suc_value, overall_score,
               fid_signal, capital_gap_eur
        FROM pre_cod_snapshots
        WHERE project_id=?
        ORDER BY computed_at DESC LIMIT ?
    """, (project_id, limit)).fetchall()
    return [dict(r) for r in rows]


@router.get("/portfolio/summary")
def portfolio_summary(
    project_ids: str = Query(..., description="Comma-separated project IDs"),
    db: sqlite3.Connection = Depends(get_db)
):
    ids = [p.strip() for p in project_ids.split(",") if p.strip()]
    results = []

    for pid in ids:
        rows = db.execute(
            "SELECT * FROM development_packages WHERE project_id=?", (pid,)
        ).fetchall()
        if not rows:
            continue
        pkgs = [dict(r) for r in rows]
        cec = _compute_cec(pkgs)
        fri = _compute_fri(pkgs)

        COMMITTED = {"committed", "drawable", "drawn", "closed"}
        REQUIRED  = {"eligible", "approved", "committed", "drawable", "drawn"}
        gap = max(0.0,
            sum(p["cost_amount"] for p in pkgs if p["workflow_state"] in REQUIRED) -
            sum(p["cost_amount"] for p in pkgs if p["workflow_state"] in COMMITTED)
        )
        signal = _signal(cec.value, fri.value, 0.0, 0.0)

        results.append({
            "project_id":         pid,
            "cec":                round(cec.value, 3),
            "fri":                round(fri.value, 3),
            "fid_signal":         signal,
            "capital_gap_eur":    gap,
            "blocked_packages":   sum(1 for p in pkgs if p["workflow_state"] in ("identified","scoped")),
        })

    return {
        "computed_at":          datetime.now(timezone.utc).isoformat(),
        "project_count":        len(results),
        "projects":             results,
        "portfolio_avg_cec":    round(sum(r["cec"] for r in results) / len(results), 3) if results else 0,
        "portfolio_avg_fri":    round(sum(r["fri"] for r in results) / len(results), 3) if results else 0,
        "projects_fid_ready":   sum(1 for r in results if r["fid_signal"] == "READY"),
        "total_capital_gap_eur": sum(r["capital_gap_eur"] for r in results),
    }
