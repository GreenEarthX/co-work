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

import uuid
import json
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

# Unified DB — single store across all modules.
from app.core.db_backend import domain_connection, domain_is_postgres

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
    # Handoff v4, task 6 (JML 2026-11-17): additionality is an ASSESSMENT of
    # evidenced criteria. GEX states what is evidenced; the DFI decides.
    NOT_ASSESSABLE = "NOT_ASSESSABLE"                    # a core criterion has no evidence
    EVIDENCED = "EVIDENCED_FOR_DFI_DECISION"             # every core criterion is evidenced


class ImpactStatus(str, Enum):
    MET          = "MET"
    IN_PROGRESS  = "IN_PROGRESS"
    PENDING      = "PENDING"
    NOT_MET      = "NOT_MET"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# The per-DFI hurdle and catalytic tables that lived here (EIB 9.2 % …) were code
# constants with no source. They are proposed values in the reference registry
# now, attributed to each DFI as party (scripts/propose_decision_policies_20261117.py),
# and read through app/core/decision_policy.py — "GEX proposed" until the DFI's
# own reference establishes them.

CORE_CRITERIA = ("financing_unavailable", "risk_mitigation", "mobilisation")
# Their labels are in the one vocabulary (app/core/vocabulary.py, additionality_criterion).
from app.core.vocabulary import display_label  # noqa: E402


class EvidenceRef(BaseModel):
    reference: str = Field(..., min_length=1, description="Document, letter or term sheet")
    document_sha256: Optional[str] = Field(None, description="sha256 of a document on file")
    description: Optional[str] = None


class Criterion(BaseModel):
    statement: Optional[str] = None
    evidence: list[EvidenceRef] = []


class Mobilisation(Criterion):
    commercial_eur: Optional[float] = Field(None, ge=0)
    dfi_eur: Optional[float] = Field(None, gt=0)


class DebtTerms(BaseModel):
    debt_eur: float = Field(..., ge=0)
    interest_rate: float = Field(..., ge=0)
    debt_tenor_years: int = Field(..., ge=0)
    grant_eur: float = Field(0.0, ge=0)


class AdditionalityInput(BaseModel):
    """An additionality assessment: evidenced criteria, and the engine-computed
    IRR with and without the DFI's terms as ONE input. The caller types no IRR."""
    project_id:              str
    dfi_institution:         DFIInstitution
    tranche_amount_eur:      float = Field(..., gt=0, description="DFI tranche size in EUR")
    total_capex_eur:         float = Field(..., gt=0)

    financing_unavailable:   Criterion = Criterion()
    risk_mitigation:         Criterion = Criterion()
    mobilisation:            Mobilisation = Mobilisation()
    standards_contribution:  Criterion = Criterion()

    # The returns case the IRRs are computed on (the PF engine's ReturnsRequest,
    # without financing), and the two financing structures compared.
    returns_inputs:          Optional[dict] = None
    terms_with_dfi:          Optional[DebtTerms] = None
    terms_without_dfi:       Optional[DebtTerms] = None

    # Impact KPIs
    jobs_construction:       int   = Field(0, description="Construction-phase jobs created")
    jobs_operational:        int   = Field(0, description="Permanent operational jobs")
    emissions_avoided_tco2e: float = Field(0, description="Annual CO2e tonnes avoided vs fossil baseline")
    energy_access_mwh:       float = Field(0, description="New clean energy access (MWh/yr) if applicable")
    host_nation_gdp_eur:     float = Field(0, description="Estimated GDP contribution to host nation")
    female_workforce_pct:    float = Field(0, description="Female workforce %")
    local_procurement_pct:   float = Field(0, description="Local procurement % of total project spend")

    debt_swap_id:            Optional[str] = Field(None, description="Links to sovereign D4N instrument")
    sovereign_debt_retired_usd: float = Field(0, description="USD sovereign debt retired via D4N swap")
    carbon_attribution_pct:  float = Field(0, description="% of carbon credits attributed to host nation")

    assessed_by:             str = Field(..., description="Actor ID performing the assessment")
    notes:                   Optional[str] = None


class AdditionalityResult(BaseModel):
    """What the DFI's investment committee reviews: each criterion with its
    evidence, the IRR input with its boundary, and the attributed decision tests."""
    assessment_id:           str
    project_id:              str
    dfi_institution:         str
    computed_at:             str
    additionality_status:    AdditionalityStatus
    message:                 str
    criteria:                list[dict]
    irr_input:               dict
    decision_tests:          list[dict]
    impact_score:            float
    impact_status:           ImpactStatus
    impact_narrative:        str
    jobs_construction:       int
    jobs_operational:        int
    emissions_avoided_tco2e: float
    energy_access_mwh:       float
    female_workforce_pct:    float
    local_procurement_pct:   float
    is_sovereign_linked:     bool
    sovereign_debt_retired_usd: float
    carbon_attribution_pct:  float
    sovereign_narrative:     str
    overall_verdict:         str
    g10_pre_condition_met:   bool
    g10_note:                str


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
    # Follows DOMAIN_DB_BACKEND; resolved per request, never at import,
    # so 044's project-scoped policies see THIS caller's tenant.
    conn = domain_connection()
    if not domain_is_postgres():
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
    if domain_is_postgres():
        # Migrations 043/044 own these tables and their RLS policies. gex_app
        # has no CREATE on schema public, so this DDL cannot run there — and
        # must not: a runtime-created table would carry no policy.
        return
    conn = domain_connection()
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

def _criterion_view(name: str, crit: Criterion) -> dict:
    evidenced = any(e.reference.strip() for e in crit.evidence)
    view = {"criterion": name, "label": display_label("additionality_criterion", name), "core": name in CORE_CRITERIA,
            "status": "EVIDENCED" if evidenced else "NOT_EVIDENCED",
            "statement": crit.statement, "evidence": [e.model_dump() for e in crit.evidence]}
    if isinstance(crit, Mobilisation):
        ratio = (crit.commercial_eur / crit.dfi_eur
                 if evidenced and crit.commercial_eur is not None and crit.dfi_eur else None)
        view.update(commercial_eur=crit.commercial_eur, dfi_eur=crit.dfi_eur, catalytic_ratio=ratio)
    return view


def _compute_additionality(inp: AdditionalityInput, irr_input: dict) -> AdditionalityResult:
    """Pure: the criteria, the IRR input (already engine-computed) and the tests."""
    from app.core import decision_policy as dp

    institution = inp.dfi_institution
    criteria = [_criterion_view(n, getattr(inp, n)) for n in
                ("financing_unavailable", "risk_mitigation", "mobilisation", "standards_contribution")]
    missing = [c["label"] for c in criteria if c["core"] and c["status"] != "EVIDENCED"]
    ratio = next(c for c in criteria if c["criterion"] == "mobilisation").get("catalytic_ratio")
    tests = [
        dp.evaluate("DFI_IRR", irr_input.get("irr_without_dfi"), party=institution.value),
        dp.evaluate("DFI_CATALYTIC", ratio, party=institution.value),
    ]
    if missing:
        status = AdditionalityStatus.NOT_ASSESSABLE
        message = ("not assessable — no evidence for: " + "; ".join(missing)
                   + ". An IRR comparison alone does not establish additionality.")
    else:
        status = AdditionalityStatus.EVIDENCED
        message = (f"Every core criterion is evidenced. The decision is {institution.value}'s; "
                   f"GEX states the evidence and the attributed tests, and decides nothing.")

    impact_score = _score_impact(inp)
    impact_status, impact_narrative = _impact_narrative(inp, institution)
    is_sovereign = bool(inp.debt_swap_id and inp.sovereign_debt_retired_usd > 0)
    sovereign_narrative = (
        f"Linked to debt-for-nature swap {inp.debt_swap_id}; USD {inp.sovereign_debt_retired_usd/1e6:.1f}M "
        f"sovereign debt retired (as stated)." if is_sovereign else
        "No debt-for-nature sovereign linkage for this assessment.")
    return AdditionalityResult(
        assessment_id=str(uuid.uuid4()), project_id=inp.project_id,
        dfi_institution=institution.value, computed_at=datetime.now(timezone.utc).isoformat(),
        additionality_status=status, message=message, criteria=criteria,
        irr_input=irr_input, decision_tests=tests,
        impact_score=impact_score, impact_status=impact_status, impact_narrative=impact_narrative,
        jobs_construction=inp.jobs_construction, jobs_operational=inp.jobs_operational,
        emissions_avoided_tco2e=inp.emissions_avoided_tco2e, energy_access_mwh=inp.energy_access_mwh,
        female_workforce_pct=inp.female_workforce_pct, local_procurement_pct=inp.local_procurement_pct,
        is_sovereign_linked=is_sovereign, sovereign_debt_retired_usd=inp.sovereign_debt_retired_usd,
        carbon_attribution_pct=inp.carbon_attribution_pct, sovereign_narrative=sovereign_narrative,
        overall_verdict=status.value,
        # Clearing a DFI tranche for financial close is the DFI's own decision, recorded by it.
        g10_pre_condition_met=False,
        g10_note=f"G10: {institution.value}'s own additionality decision is required; this assessment "
                 f"is evidence for it, not the decision.",
    )


async def _engine_irrs(inp: AdditionalityInput, request=None) -> dict:
    """The project IRR with and without the DFI's terms, both from the PF engine,
    on the same returns case and boundary. None when the case is not supplied."""
    if not (inp.returns_inputs and inp.terms_with_dfi and inp.terms_without_dfi):
        return {"irr_with_dfi": None, "irr_without_dfi": None, "basis": "NOT_COMPUTED",
                "note": "No returns case and terms were supplied, so the engine computed no IRR. "
                        "IRRs are never typed."}
    from app.api.v1.routes_finance_model import _call_model
    out = {}
    for label, terms in (("with_dfi", inp.terms_with_dfi), ("without_dfi", inp.terms_without_dfi)):
        body = {**inp.returns_inputs, **terms.model_dump()}
        r = (await _call_model("/returns/calculate", method="POST", json_data=body, request=request))["returns"]
        out[f"irr_{label}"] = r["unlevered_irr"]
        out[f"equity_irr_{label}"] = r["levered_irr"]
        out["valuation_boundary"] = r.get("valuation_boundary")
        out["scenario"] = r.get("scenario")
        out["model_version"] = r.get("model_version")
    out["basis"] = "ENGINE_COMPUTED"
    out["note"] = ("Unlevered (project) IRR from the PF engine on the same case under each financing; "
                   "ONE input to the assessment, shown with its boundary.")
    return out


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
async def assess_additionality(
    inp: AdditionalityInput,
    db: Any = Depends(get_db)
):
    """An additionality assessment for one DFI tranche: each criterion with its
    evidence, the engine-computed IRR with and without the DFI's terms as one
    input, and the DFI's attributed decision tests. Without evidence on the
    availability of finance, risk mitigation and mobilisation the result is
    NOT_ASSESSABLE, whatever the IRRs say."""
    irr_input = await _engine_irrs(inp)
    result = _compute_additionality(inp, irr_input)
    now = datetime.now(timezone.utc).isoformat()
    mob = inp.mobilisation
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
        irr_input.get("irr_with_dfi"), irr_input.get("irr_without_dfi"), None, None, None,
        None if mob.commercial_eur is None else mob.commercial_eur / inp.total_capex_eur,
        None if mob.dfi_eur is None else mob.dfi_eur / inp.total_capex_eur, None,
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
    db: Any = Depends(get_db)
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
def g10_additionality_status(project_id: str, db: Any = Depends(get_db)):
    """
    Which DFI tranches have an evidenced additionality assessment.

    GEX decides no additionality (handoff v4, task 6): `g10_ready` is True only
    when each DFI's OWN decision is recorded, which this module never records,
    so it stays False. The assessments are evidence for the DFI's decision.
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
            "Every DFI tranche's own additionality decision is recorded."
            if all_pass else
            "Additionality is each DFI's decision; GEX holds the evidenced assessments, "
            "not the decisions."
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
    db: Any = Depends(get_db)
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
def get_impact_history(assessment_id: str, db: Any = Depends(get_db)):
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
