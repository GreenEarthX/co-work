"""
additionality.py
================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

DFI Additionality Test and Development Impact Tracking.

Why this exists:
  Every DFI institution (EIB, KfW, IFC, BpiFrance, DFC, AfDB) must demonstrate
  to its shareholders — usually governments — that:
    1. The project would NOT have happened without concessional capital (additionality)
    2. The project generates measurable development impact (jobs, emissions, energy access)
    3. The concessional capital mobilises sufficient commercial capital (catalytic ratio)

  Without a passing additionality test, the DFI's investment committee will reject
  the deal regardless of financial merit.

  GEX makes these tests auditable, repeatable, and transparent — replacing the DFI's
  internal Excel model with a platform-computed, evidence-backed result.

Integration:
  - Consumes: CONTROL sheet inputs (WACC, rates, CAPEX) via routes_finance_model.py proxy
  - Consumes: development_packages.py (development impact KPIs)
  - Consumes: gex_pf_engine/cfads.py → blended_wacc() and project_irr() when implemented
  - Surfaces in: Finance workspace → DFI sub-persona view (Vademecum task 2.8)
  - Surfaces in: DFI_CRITERIA sheet (Excel model Sheet 9)
  - Feeds: Gate G10 Financial Close conditions precedent checklist

DFI sub-persona (ABAC):
  ALIGN in abac.py: actor_type=DFI_CONCESSIONAL can see additionality results
  for projects where they are a committed tranche holder.

Route prefix: /api/v1/additionality
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

# Unified DB — single store across all modules.
from app.core.config import settings
DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/additionality", tags=["additionality"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class DFIInstitution(str, Enum):
    EIB        = "EIB"
    KFW        = "KFW"
    IFC        = "IFC"
    BPIFRANCE  = "BPIFRANCE"
    DFC        = "DFC"
    AFDB       = "AFDB"
    OTHER      = "OTHER"


class AdditionalityStatus(str, Enum):
    PASSED       = "PASSED"     # Project IRR without DFI < hurdle rate
    FAILED       = "FAILED"     # Project bankable without DFI — not eligible
    MARGINAL     = "MARGINAL"   # IRR gap <1pp — requires further justification
    PENDING      = "PENDING"    # Insufficient data to compute
    WAIVED       = "WAIVED"     # DFI applied policy waiver (rare, requires board approval)


class ImpactStatus(str, Enum):
    MET          = "MET"
    IN_PROGRESS  = "IN_PROGRESS"
    PENDING      = "PENDING"
    NOT_MET      = "NOT_MET"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# Per-DFI minimum additionality requirements (IRR hurdle rates for their mandates)
DFI_HURDLE_RATES = {
    DFIInstitution.EIB:       0.092,   # EIB: project IRR must be below 9.2% without EIB
    DFIInstitution.KFW:       0.090,   # KfW: 9.0%
    DFIInstitution.IFC:       0.085,   # IFC: 8.5% — emerging market adjustment
    DFIInstitution.BPIFRANCE: 0.090,   # BpiFrance: 9.0%
    DFIInstitution.DFC:       0.100,   # DFC: 10.0% — higher risk tolerance mandate
    DFIInstitution.AFDB:      0.080,   # AfDB: 8.0% — regional development mandate
    DFIInstitution.OTHER:     0.090,
}

# Per-DFI minimum catalytic ratio requirements
DFI_CATALYTIC_MINIMUMS = {
    DFIInstitution.EIB:       2.5,
    DFIInstitution.KFW:       2.0,
    DFIInstitution.IFC:       3.0,
    DFIInstitution.BPIFRANCE: 2.0,
    DFIInstitution.DFC:       2.5,
    DFIInstitution.AFDB:      2.0,
    DFIInstitution.OTHER:     2.0,
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class AdditionalityInput(BaseModel):
    """
    Inputs for additionality test.
    In production, many of these come from the Excel model CONTROL sheet
    via the routes_finance_model.py proxy to gex_pf_engine.
    """
    project_id:              str
    dfi_institution:         DFIInstitution
    tranche_amount_eur:      float = Field(..., gt=0, description="DFI tranche size in EUR")
    total_capex_eur:         float = Field(..., gt=0)

    # IRR inputs — come from cfads.py when PF Engine integration is complete
    project_irr_with_dfi:    float = Field(..., description="Project equity IRR with concessional tranche")
    project_irr_without_dfi: float = Field(..., description="Project equity IRR at all-commercial rates")
    commercial_hurdle_rate:  float = Field(0.12, description="Sponsor equity required return")

    # Capital stack context
    commercial_debt_pct:     float = Field(..., description="% of CAPEX as commercial senior debt")
    total_concessional_pct:  float = Field(..., description="% of CAPEX as all concessional tranches")
    grant_pct:               float = Field(0.0,  description="% of CAPEX as grants")

    # WACC context
    blended_wacc:            float = Field(..., description="Blended WACC from cfads.py")
    all_commercial_wacc:     float = Field(..., description="All-commercial WACC benchmark")

    # Impact KPIs
    jobs_construction:       int   = Field(0, description="Construction-phase jobs created")
    jobs_operational:        int   = Field(0, description="Permanent operational jobs")
    emissions_avoided_tco2e: float = Field(0, description="Annual CO2e tonnes avoided vs fossil baseline")
    energy_access_mwh:       float = Field(0, description="New clean energy access (MWh/yr) if applicable")
    host_nation_gdp_eur:     float = Field(0, description="Estimated GDP contribution to host nation")
    female_workforce_pct:    float = Field(0, description="Female workforce %")
    local_procurement_pct:   float = Field(0, description="Local procurement % of total project spend")

    # Debt-for-nature link (if applicable)
    debt_swap_id:            Optional[str] = Field(None, description="Links to sovereign D4N instrument")
    sovereign_debt_retired_usd: float = Field(0, description="USD sovereign debt retired via D4N swap")
    carbon_attribution_pct:  float = Field(0, description="% of carbon credits attributed to host nation")

    assessed_by:             str = Field(..., description="Actor ID performing the assessment")
    notes:                   Optional[str] = None


class AdditionalityResult(BaseModel):
    """
    Full additionality assessment result.
    This is the document the DFI investment committee reviews.
    """
    assessment_id:           str
    project_id:              str
    dfi_institution:         str
    computed_at:             str

    # Core additionality test
    additionality_status:        AdditionalityStatus
    irr_without_dfi:             float
    irr_with_dfi:                float
    dfi_hurdle_rate:             float
    irr_gap:                     float    # hurdle - irr_without_dfi (positive = additional)
    irr_improvement:             float    # irr_with_dfi - irr_without_dfi
    passes_irr_test:             bool
    irr_test_narrative:          str

    # WACC impact
    wacc_reduction_pp:           float    # percentage points
    wacc_reduction_narrative:    str

    # Catalytic ratio
    catalytic_ratio:             float    # commercial EUR / concessional EUR
    catalytic_minimum:           float    # DFI minimum requirement
    passes_catalytic_test:       bool
    catalytic_narrative:         str

    # Development impact
    impact_score:                float    # 0–100 composite
    jobs_construction:           int
    jobs_operational:            int
    emissions_avoided_tco2e:     float
    energy_access_mwh:           float
    female_workforce_pct:        float
    local_procurement_pct:       float
    impact_status:               ImpactStatus
    impact_narrative:            str

    # Sovereign / D4N (if applicable)
    is_sovereign_linked:         bool
    sovereign_debt_retired_usd:  float
    carbon_attribution_pct:      float
    sovereign_narrative:         str

    # Overall verdict
    overall_verdict:             str   # ELIGIBLE | NOT_ELIGIBLE | CONDITIONAL
    conditions:                  list[str]
    recommended_actions:         list[str]

    # G10 connection
    g10_pre_condition_met:       bool
    g10_note:                    str


class ImpactKPIUpdate(BaseModel):
    """Update impact KPIs as project progresses — feeds DFI annual reporting."""
    jobs_construction:       Optional[int]   = None
    jobs_operational:        Optional[int]   = None
    emissions_avoided_tco2e: Optional[float] = None
    energy_access_mwh:       Optional[float] = None
    female_workforce_pct:    Optional[float] = None
    local_procurement_pct:   Optional[float] = None
    host_nation_gdp_eur:     Optional[float] = None
    reporting_period:        str = Field(..., description="e.g. '2026-Q1'")
    updated_by:              str


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Create additionality tables.
    UPDM target (PostgreSQL): add FK to projects, concessional_tranches,
    sovereign_instruments, and enable RLS for DFI sub-persona.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS additionality_assessments (
            assessment_id          TEXT PRIMARY KEY,
            project_id             TEXT NOT NULL,
            dfi_institution        TEXT NOT NULL,
            tranche_amount_eur     REAL NOT NULL,
            total_capex_eur        REAL NOT NULL,
            irr_with_dfi           REAL NOT NULL,
            irr_without_dfi        REAL NOT NULL,
            commercial_hurdle_rate REAL NOT NULL,
            blended_wacc           REAL NOT NULL,
            all_commercial_wacc    REAL NOT NULL,
            commercial_debt_pct    REAL NOT NULL,
            total_concessional_pct REAL NOT NULL,
            grant_pct              REAL NOT NULL,
            jobs_construction      INTEGER DEFAULT 0,
            jobs_operational       INTEGER DEFAULT 0,
            emissions_avoided_tco2e REAL DEFAULT 0,
            energy_access_mwh      REAL DEFAULT 0,
            host_nation_gdp_eur    REAL DEFAULT 0,
            female_workforce_pct   REAL DEFAULT 0,
            local_procurement_pct  REAL DEFAULT 0,
            debt_swap_id           TEXT,
            sovereign_debt_retired_usd REAL DEFAULT 0,
            carbon_attribution_pct REAL DEFAULT 0,
            additionality_status   TEXT NOT NULL,
            overall_verdict        TEXT NOT NULL,
            impact_score           REAL,
            g10_pre_condition_met  INTEGER DEFAULT 0,
            result_json            TEXT NOT NULL,
            assessed_by            TEXT NOT NULL,
            notes                  TEXT,
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aa_project ON additionality_assessments(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aa_dfi ON additionality_assessments(dfi_institution)")

    # Impact KPI history (for DFI annual reporting — post-COD monitoring)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dfi_impact_kpis (
            kpi_id               TEXT PRIMARY KEY,
            assessment_id        TEXT NOT NULL,
            project_id           TEXT NOT NULL,
            dfi_institution      TEXT NOT NULL,
            reporting_period     TEXT NOT NULL,
            jobs_construction    INTEGER,
            jobs_operational     INTEGER,
            emissions_avoided    REAL,
            energy_access_mwh    REAL,
            female_pct           REAL,
            local_procurement_pct REAL,
            host_nation_gdp_eur  REAL,
            updated_by           TEXT NOT NULL,
            created_at           TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dik_project ON dfi_impact_kpis(project_id)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

def _compute_additionality(inp: AdditionalityInput) -> AdditionalityResult:
    """
    Core additionality computation.

    Three tests must pass for DFI eligibility:
      1. IRR test:        project_irr_without_dfi < dfi_hurdle_rate
      2. Catalytic test:  commercial_debt / concessional >= dfi_minimum_ratio
      3. Impact:          at least minimum KPIs met

    The WACC reduction quantifies the financial value the DFI delivers —
    this is GEX's quantification of the Hidalgo entropy-reduction argument.
    """
    institution = inp.dfi_institution
    hurdle       = DFI_HURDLE_RATES.get(institution, 0.090)
    cat_minimum  = DFI_CATALYTIC_MINIMUMS.get(institution, 2.0)

    # ── IRR TEST ──────────────────────────────────────────────────────────
    irr_gap         = hurdle - inp.project_irr_without_dfi
    irr_improvement = inp.project_irr_with_dfi - inp.project_irr_without_dfi
    passes_irr      = inp.project_irr_without_dfi < hurdle

    if irr_gap > 0.03:
        irr_status = AdditionalityStatus.PASSED
        irr_narrative = (
            f"Project IRR without {institution.value} ({inp.project_irr_without_dfi*100:.1f}%) "
            f"is {irr_gap*100:.1f}pp below the {institution.value} hurdle rate "
            f"({hurdle*100:.1f}%). Project clearly requires concessional support. "
            f"DFI participation improves IRR to {inp.project_irr_with_dfi*100:.1f}% — "
            f"a {irr_improvement*100:.1f}pp uplift enabling equity investment."
        )
    elif 0 < irr_gap <= 0.03:
        irr_status = AdditionalityStatus.MARGINAL
        irr_narrative = (
            f"IRR gap of {irr_gap*100:.1f}pp is marginal. "
            f"{institution.value} investment committee will require additional "
            f"justification beyond the IRR test alone. Recommend supplementing "
            f"with strong development impact evidence and sovereign context."
        )
    else:
        irr_status = AdditionalityStatus.FAILED
        irr_narrative = (
            f"Project IRR without {institution.value} ({inp.project_irr_without_dfi*100:.1f}%) "
            f"exceeds the hurdle rate ({hurdle*100:.1f}%). The project is commercially viable "
            f"without concessional support. {institution.value} should not participate — "
            f"their mandate requires additionality."
        )
    passes_irr = irr_gap > 0

    # ── WACC REDUCTION ───────────────────────────────────────────────────
    wacc_reduction = inp.all_commercial_wacc - inp.blended_wacc
    wacc_narrative = (
        f"DFI blending reduces project WACC from {inp.all_commercial_wacc*100:.2f}% "
        f"(all-commercial) to {inp.blended_wacc*100:.2f}% (blended). "
        f"That is a {wacc_reduction*100:.2f}pp reduction — "
        f"directly lowering levelised cost and enabling commercial senior debt commitment."
    )

    # ── CATALYTIC RATIO ──────────────────────────────────────────────────
    # Commercial capital mobilised per EUR of concessional
    if inp.total_concessional_pct > 0:
        cat_ratio = inp.commercial_debt_pct / inp.total_concessional_pct
    else:
        cat_ratio = 0.0
    passes_cat = cat_ratio >= cat_minimum

    cat_narrative = (
        f"Catalytic ratio: {cat_ratio:.1f}x "
        f"(€{cat_ratio:.1f} commercial per €1.00 concessional). "
        f"{institution.value} minimum: {cat_minimum:.1f}x. "
        + ("PASSES." if passes_cat else
           f"FAILS — below {institution.value} minimum. Increase commercial debt "
           f"percentage or reduce concessional tranche size.")
    )

    # ── DEVELOPMENT IMPACT ───────────────────────────────────────────────
    impact_score = _score_impact(inp)
    impact_status, impact_narrative = _impact_narrative(inp, institution)

    # ── SOVEREIGN / D4N ──────────────────────────────────────────────────
    is_sovereign = bool(inp.debt_swap_id and inp.sovereign_debt_retired_usd > 0)
    if is_sovereign:
        sovereign_narrative = (
            f"Project linked to Debt-for-Nature swap {inp.debt_swap_id}. "
            f"USD {inp.sovereign_debt_retired_usd/1e6:.1f}M sovereign debt retired. "
            f"{inp.carbon_attribution_pct*100:.0f}% of carbon credits attributed to host nation. "
            f"This is a premium ESG asset — strengthens {institution.value} mandate alignment "
            f"and enables sovereign ESG certification pathway in GEX."
        )
    else:
        sovereign_narrative = "No debt-for-nature sovereign linkage for this assessment."

    # ── OVERALL VERDICT ──────────────────────────────────────────────────
    conditions   = []
    actions      = []

    if not passes_irr:
        conditions.append(f"IRR additionality test failed — IRR without {institution.value} exceeds hurdle")
        actions.append("Re-assess project structure or remove DFI tranche from capital stack")
    if not passes_cat:
        conditions.append(f"Catalytic ratio {cat_ratio:.1f}x below {institution.value} minimum {cat_minimum:.1f}x")
        actions.append(f"Increase commercial senior debt % or reduce concessional % to achieve {cat_minimum:.1f}x ratio")
    if impact_score < 50:
        conditions.append("Development impact score below minimum threshold (50/100)")
        actions.append("Document jobs, emissions avoided, and energy access figures with verified data")
    if irr_status == AdditionalityStatus.MARGINAL:
        conditions.append("IRR gap is marginal — supplementary justification required")
        actions.append("Prepare supplementary additionality memo with market failure evidence")

    if not conditions:
        verdict = "ELIGIBLE"
    elif all(c for c in [not passes_irr, not passes_cat]):
        verdict = "NOT_ELIGIBLE"
    else:
        verdict = "CONDITIONAL"

    # G10 pre-condition: additionality must be PASSED or MARGINAL (with conditions)
    g10_met  = verdict in ("ELIGIBLE", "CONDITIONAL") and passes_irr
    g10_note = (
        f"G10 Financial Close: {institution.value} additionality is {verdict}. "
        + ("DFI commitment can proceed to term sheet." if g10_met else
           "Resolve conditions before DFI term sheet can be issued.")
    )

    return AdditionalityResult(
        assessment_id=str(uuid.uuid4()),
        project_id=inp.project_id,
        dfi_institution=institution.value,
        computed_at=datetime.now(timezone.utc).isoformat(),
        additionality_status=irr_status,
        irr_without_dfi=inp.project_irr_without_dfi,
        irr_with_dfi=inp.project_irr_with_dfi,
        dfi_hurdle_rate=hurdle,
        irr_gap=round(irr_gap, 4),
        irr_improvement=round(irr_improvement, 4),
        passes_irr_test=passes_irr,
        irr_test_narrative=irr_narrative,
        wacc_reduction_pp=round(wacc_reduction, 4),
        wacc_reduction_narrative=wacc_narrative,
        catalytic_ratio=round(cat_ratio, 2),
        catalytic_minimum=cat_minimum,
        passes_catalytic_test=passes_cat,
        catalytic_narrative=cat_narrative,
        impact_score=impact_score,
        jobs_construction=inp.jobs_construction,
        jobs_operational=inp.jobs_operational,
        emissions_avoided_tco2e=inp.emissions_avoided_tco2e,
        energy_access_mwh=inp.energy_access_mwh,
        female_workforce_pct=inp.female_workforce_pct,
        local_procurement_pct=inp.local_procurement_pct,
        impact_status=impact_status,
        impact_narrative=impact_narrative,
        is_sovereign_linked=is_sovereign,
        sovereign_debt_retired_usd=inp.sovereign_debt_retired_usd,
        carbon_attribution_pct=inp.carbon_attribution_pct,
        sovereign_narrative=sovereign_narrative,
        overall_verdict=verdict,
        conditions=conditions,
        recommended_actions=actions,
        g10_pre_condition_met=g10_met,
        g10_note=g10_note,
    )


def _score_impact(inp: AdditionalityInput) -> float:
    """
    Development impact score (0–100).
    Weighted composite of KPIs relevant to DFI mandates.
    Each KPI scored against minimum expectations for a 150MW e-fuel project.
    """
    score = 0.0
    # Jobs (30 points)
    if inp.jobs_construction >= 50:  score += 15
    elif inp.jobs_construction >= 20: score += 8
    if inp.jobs_operational >= 15:   score += 15
    elif inp.jobs_operational >= 5:   score += 8
    # Emissions (35 points)
    if inp.emissions_avoided_tco2e >= 100_000: score += 35
    elif inp.emissions_avoided_tco2e >= 50_000: score += 20
    elif inp.emissions_avoided_tco2e >= 10_000: score += 10
    # Gender inclusion (15 points)
    if inp.female_workforce_pct >= 0.30: score += 15
    elif inp.female_workforce_pct >= 0.20: score += 8
    # Local procurement (20 points)
    if inp.local_procurement_pct >= 0.40: score += 20
    elif inp.local_procurement_pct >= 0.20: score += 10
    return min(score, 100.0)


def _impact_narrative(inp: AdditionalityInput, institution: DFIInstitution):
    """Per-DFI impact narrative — each institution weights KPIs differently."""
    narratives = {
        DFIInstitution.IFC: (
            f"IFC Performance Standards: {inp.jobs_construction} construction jobs, "
            f"{inp.jobs_operational} permanent positions. "
            f"{inp.emissions_avoided_tco2e/1000:.0f}k tCO2e/yr avoided. "
            f"Female workforce: {inp.female_workforce_pct*100:.0f}%. "
            f"EDGE certification in progress — biodiversity baseline required (PS6)."
        ),
        DFIInstitution.AFDB: (
            f"AfDB mandate: host-nation economic impact. "
            f"Local procurement: {inp.local_procurement_pct*100:.0f}% "
            f"(target: 40% for full score). "
            f"GDP contribution: €{inp.host_nation_gdp_eur/1e6:.1f}M. "
            + (f"Sovereign D4N linkage: {inp.debt_swap_id} — "
               f"{inp.carbon_attribution_pct*100:.0f}% carbon credits to host nation."
               if inp.debt_swap_id else "No D4N linkage.")
        ),
        DFIInstitution.DFC: (
            f"DFC (BUILD Act): U.S. national security alignment. "
            f"{inp.emissions_avoided_tco2e/1000:.0f}k tCO2e/yr. "
            f"Energy security contribution: {inp.energy_access_mwh/1000:.0f}GWh clean energy. "
            f"U.S. procurement preference: check supplier sourcing."
        ),
    }
    narrative = narratives.get(institution,
        f"Development impact: {inp.jobs_construction + inp.jobs_operational} jobs total, "
        f"{inp.emissions_avoided_tco2e/1000:.0f}k tCO2e/yr avoided, "
        f"local procurement {inp.local_procurement_pct*100:.0f}%."
    )
    score = _score_impact(inp)
    if score >= 70:
        status = ImpactStatus.MET
    elif score >= 40:
        status = ImpactStatus.IN_PROGRESS
    elif score > 0:
        status = ImpactStatus.PENDING
    else:
        status = ImpactStatus.NOT_MET
    return status, narrative


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/assess", response_model=AdditionalityResult, status_code=201)
def assess_additionality(
    inp: AdditionalityInput,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Run a full additionality assessment for a DFI tranche.

    Produces the document the DFI investment committee reviews.
    Persists the result and links it to G10 Financial Close conditions.

    Called from:
      - Finance workspace DFI sub-persona view (Vademecum task 2.8)
      - DFI_CRITERIA sheet reconciliation
      - G10 CP checklist validation (Vademecum task 2.10)

    In production, project_irr_without_dfi and blended_wacc come from
    the PF Engine via routes_finance_model.py proxy:
      POST /api/v1/finance-model/metrics/calculate
    """
    result = _compute_additionality(inp)
    now = datetime.now(timezone.utc).isoformat()

    db.execute("""
        INSERT INTO additionality_assessments
        (assessment_id, project_id, dfi_institution, tranche_amount_eur,
         total_capex_eur, irr_with_dfi, irr_without_dfi, commercial_hurdle_rate,
         blended_wacc, all_commercial_wacc, commercial_debt_pct,
         total_concessional_pct, grant_pct, jobs_construction, jobs_operational,
         emissions_avoided_tco2e, energy_access_mwh, host_nation_gdp_eur,
         female_workforce_pct, local_procurement_pct, debt_swap_id,
         sovereign_debt_retired_usd, carbon_attribution_pct,
         additionality_status, overall_verdict, impact_score,
         g10_pre_condition_met, result_json, assessed_by, notes,
         created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        result.assessment_id, inp.project_id, inp.dfi_institution.value,
        inp.tranche_amount_eur, inp.total_capex_eur,
        inp.project_irr_with_dfi, inp.project_irr_without_dfi,
        inp.commercial_hurdle_rate, inp.blended_wacc, inp.all_commercial_wacc,
        inp.commercial_debt_pct, inp.total_concessional_pct, inp.grant_pct,
        inp.jobs_construction, inp.jobs_operational,
        inp.emissions_avoided_tco2e, inp.energy_access_mwh, inp.host_nation_gdp_eur,
        inp.female_workforce_pct, inp.local_procurement_pct,
        inp.debt_swap_id, inp.sovereign_debt_retired_usd, inp.carbon_attribution_pct,
        result.additionality_status.value, result.overall_verdict,
        result.impact_score, int(result.g10_pre_condition_met),
        result.model_dump_json(), inp.assessed_by, inp.notes, now, now
    ))
    db.commit()
    return result


@router.get("/project/{project_id}", response_model=list[dict])
def list_assessments(
    project_id: str,
    dfi: Optional[DFIInstitution] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    List all additionality assessments for a project.
    Finance workspace DFI sub-persona sees all assessments for their institution.
    """
    q = "SELECT * FROM additionality_assessments WHERE project_id=?"
    params: list = [project_id]
    if dfi:
        q += " AND dfi_institution=?"; params.append(dfi.value)
    q += " ORDER BY created_at DESC"
    rows = db.execute(q, params).fetchall()
    return [json.loads(r["result_json"]) for r in rows]


@router.get("/project/{project_id}/g10-status")
def g10_additionality_status(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    G10 pre-condition check: are all committed DFI tranches additionality-cleared?

    Called by bankability_engine.py when evaluating gate G10.
    Returns a clear PASS / FAIL / INCOMPLETE per institution.

    If any committed DFI tranche lacks a PASSED or CONDITIONAL assessment,
    G10 Financial Close cannot be granted.
    """
    rows = db.execute("""
        SELECT dfi_institution, additionality_status, overall_verdict,
               g10_pre_condition_met, created_at
        FROM additionality_assessments
        WHERE project_id=?
        ORDER BY created_at DESC
    """, (project_id,)).fetchall()

    if not rows:
        return {
            "project_id": project_id,
            "g10_ready": False,
            "note": "No additionality assessments found. "
                    "Run POST /api/v1/additionality/assess for each committed DFI tranche.",
            "assessments": []
        }

    # Latest assessment per institution
    latest: dict = {}
    for r in rows:
        inst = r["dfi_institution"]
        if inst not in latest:
            latest[inst] = dict(r)

    all_pass = all(v["g10_pre_condition_met"] for v in latest.values())

    return {
        "project_id": project_id,
        "g10_ready": all_pass,
        "note": (
            "All DFI tranches have passed additionality. G10 pre-condition met."
            if all_pass else
            "One or more DFI tranches have not passed additionality. "
            "G10 Financial Close is blocked until all conditions are resolved."
        ),
        "assessments": [
            {
                "institution": inst,
                "status": v["additionality_status"],
                "verdict": v["overall_verdict"],
                "g10_pre_condition_met": bool(v["g10_pre_condition_met"]),
                "assessed_at": v["created_at"],
            }
            for inst, v in latest.items()
        ]
    }


@router.post("/{assessment_id}/impact-kpi", status_code=201)
def update_impact_kpis(
    assessment_id: str,
    kpi: ImpactKPIUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Update development impact KPIs for a reporting period.

    Used by:
      - DFI sub-persona for annual board reporting
      - AfDB/IFC mandate compliance (PS1 annual reporting)
      - Executive workspace impact dashboard

    Post-COD, these KPIs are populated from operational data.
    Pre-COD, they are forecast values used for DFI appraisal.
    """
    row = db.execute(
        "SELECT project_id, dfi_institution FROM additionality_assessments WHERE assessment_id=?",
        (assessment_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Assessment {assessment_id} not found")

    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        INSERT INTO dfi_impact_kpis
        (kpi_id, assessment_id, project_id, dfi_institution, reporting_period,
         jobs_construction, jobs_operational, emissions_avoided, energy_access_mwh,
         female_pct, local_procurement_pct, host_nation_gdp_eur, updated_by, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), assessment_id, row["project_id"], row["dfi_institution"],
        kpi.reporting_period, kpi.jobs_construction, kpi.jobs_operational,
        kpi.emissions_avoided_tco2e, kpi.energy_access_mwh,
        kpi.female_workforce_pct, kpi.local_procurement_pct, kpi.host_nation_gdp_eur,
        kpi.updated_by, now
    ))
    db.commit()
    return {"status": "recorded", "assessment_id": assessment_id, "period": kpi.reporting_period}


@router.get("/{assessment_id}/impact-history")
def get_impact_history(assessment_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Return all KPI snapshots for an assessment — shows impact trajectory over time.
    Used in DFI annual reporting and CISO/Executive dashboards.
    """
    rows = db.execute("""
        SELECT * FROM dfi_impact_kpis
        WHERE assessment_id=?
        ORDER BY created_at ASC
    """, (assessment_id,)).fetchall()
    return [dict(r) for r in rows]
