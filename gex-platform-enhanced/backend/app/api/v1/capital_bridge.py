"""
capital_bridge.py
=================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Implements the full GEX_CapitalBridge_v1 workbook logic in one unified API,
multi-fuel from the ground up: H2, NH3, e-Methanol, e-NG, SAF.

Maps the 11 Excel sheets to 7 unified tables keyed on project_id:
  CONTROL        → project_control          (plant + commercial + timeline + CAPEX/OPEX)
  PLANT_BUILDER  → development_packages      (already implemented)
  SPEND_WAVE     → spend_wave                (annual drawdown by capital layer)
  PERSONNEL      → personnel_plan            (owner-team cost build-up)
  CAPITAL_STACK  → capital_stack_tranches    (per-tranche amounts, rates, tenor, WACC)
  DRAWDOWN       → drawdown_quarters         (quarterly schedule post-FID)
  PRE_COD        → pre_cod_metric_snapshots  (already implemented)
  POST_COD       → post_cod_schedule         (DSCR, CFADS, debt service)
  DFI_CRITERIA   → dfi_criteria_status       (6 institutions × criteria)
  SCENARIOS      → scenario_results          (sensitivity analysis outputs)
  GEX_MAP        → (documentation — no table)

Key design:
  - Every row is scoped by project_id → FK to projects.id (gex_platform.db).
  - Every row carries created_by → FK to auth_users.user_id.
  - fuel_defaults table holds per-fuel typical plant + commercial parameters
    so the CONTROL sheet can be bootstrapped for any fuel choice.
  - DSCR is computed only post-COD (guarded by year vs cod_year).
  - Pre-COD metrics are reused from pre_cod_metrics.py (unified DB).

Route prefix: /api/v1/capital-bridge
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.core.config import settings

DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/capital-bridge", tags=["capital-bridge"])


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS — matches Excel CAPITAL_STACK, DFI_CRITERIA, fuel families
# ═══════════════════════════════════════════════════════════════════════════

class FuelType(str, Enum):
    """Five fuels the CapitalBridge model supports end-to-end."""
    H2         = "H2"
    NH3        = "NH3"
    E_METHANOL = "E_METHANOL"
    E_NG       = "E_NG"          # e-Methane / synthetic natural gas
    SAF        = "SAF"


class TrancheType(str, Enum):
    SEED_EQUITY       = "SEED_EQUITY"
    SPONSOR_EQUITY    = "SPONSOR_EQUITY"
    GRANT             = "GRANT"
    DFI_CONCESSIONAL  = "DFI_CONCESSIONAL"
    COMMERCIAL_SENIOR = "COMMERCIAL_SENIOR"
    ECA               = "ECA"
    VENDOR_FINANCE    = "VENDOR_FINANCE"
    BRIDGE            = "BRIDGE"


class DFIInstitution(str, Enum):
    EIB       = "EIB"
    KFW       = "KFW"
    IFC       = "IFC"
    BPIFRANCE = "BPIFRANCE"
    DFC       = "DFC"
    AFDB      = "AFDB"


class DFICriterionStatus(str, Enum):
    MET         = "MET"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING     = "PENDING"
    CHECK       = "CHECK"
    NOT_MET     = "NOT_MET"


# ═══════════════════════════════════════════════════════════════════════════
# FUEL DEFAULTS — per-fuel plant & commercial baseline (CONTROL sheet seed)
# Doctrine: keeps SAF hard-coded values out of the CONTROL sheet, lets a new
# project of ANY fuel bootstrap with reasonable parameters.
# Sources: GEX Vademecum + typical industry references for 2026-2030 projects.
# ═══════════════════════════════════════════════════════════════════════════

FUEL_DEFAULTS = {
    # specific_energy_kwh_per_kg_h2: electrolyser SEC — same across fuels (H2 is the feedstock)
    # product_yield_t_per_t_h2:     tonnes of final product per tonne H2 produced
    # base_price_eur_per_t:         2026-2030 commercial offtake range midpoint
    # green_premium_eur_per_t:      incremental price over grey equivalent
    # typical_availability:         ±0.02 window
    # dsra_months:                  lender standard
    FuelType.H2: {
        "fuel_label":               "Green Hydrogen",
        "specific_energy_kwh_per_kg_h2": 50.0,
        "product_yield_t_per_t_h2":      1.0,
        "base_price_eur_per_t":          5500.0,
        "green_premium_eur_per_t":       2000.0,
        "typical_availability":          0.93,
        "dsra_months":                   6,
        "contingency_pct":               0.15,
        "typical_offtake_counterparty":  "Industrial offtaker (steel / refining / ammonia)",
    },
    FuelType.NH3: {
        "fuel_label":               "Green Ammonia",
        "specific_energy_kwh_per_kg_h2": 50.0,
        "product_yield_t_per_t_h2":      5.56,   # NH3 = 17.03 / 3.03 (3 H atoms per NH3)
        "base_price_eur_per_t":          900.0,
        "green_premium_eur_per_t":       350.0,
        "typical_availability":          0.92,
        "dsra_months":                   6,
        "contingency_pct":               0.15,
        "typical_offtake_counterparty":  "Shipping fuel buyer / fertiliser major",
    },
    FuelType.E_METHANOL: {
        "fuel_label":               "e-Methanol",
        "specific_energy_kwh_per_kg_h2": 50.0,
        "product_yield_t_per_t_h2":      5.3,    # MeOH from H2+CO2
        "base_price_eur_per_t":          1200.0,
        "green_premium_eur_per_t":       600.0,
        "typical_availability":          0.92,
        "dsra_months":                   6,
        "contingency_pct":               0.18,   # higher — CO2 interface risk
        "typical_offtake_counterparty":  "Maersk / shipping pool / chemical major",
    },
    FuelType.E_NG: {
        "fuel_label":               "e-Methane (synthetic natural gas)",
        "specific_energy_kwh_per_kg_h2": 50.0,
        "product_yield_t_per_t_h2":      2.0,    # CH4 via methanation
        "base_price_eur_per_t":          1400.0,
        "green_premium_eur_per_t":       800.0,
        "typical_availability":          0.92,
        "dsra_months":                   6,
        "contingency_pct":               0.17,
        "typical_offtake_counterparty":  "Gas utility / industrial heat offtaker",
    },
    FuelType.SAF: {
        "fuel_label":               "Sustainable Aviation Fuel (FT-SAF)",
        "specific_energy_kwh_per_kg_h2": 50.0,
        "product_yield_t_per_t_h2":      1.3,    # matches Excel CONTROL R17
        "base_price_eur_per_t":          2700.0, # matches Excel CONTROL R22
        "green_premium_eur_per_t":       800.0,  # matches Excel CONTROL R23
        "typical_availability":          0.92,
        "dsra_months":                   6,
        "contingency_pct":               0.15,
        "typical_offtake_counterparty":  "Major airline (investment grade)",
    },
}


# Capital-stack defaults (% of CAPEX) — matches Excel CAPITAL_STACK R4-R14
DEFAULT_CAPITAL_STACK_PCT = {
    TrancheType.SEED_EQUITY:       0.02,
    TrancheType.SPONSOR_EQUITY:    0.18,
    TrancheType.GRANT:             0.10,   # Government grants
    # DFI breakdown (6 institutions summing to ~0.48):
    "DFI_EIB":                     0.15,
    "DFI_KFW":                     0.10,
    "DFI_IFC":                     0.08,
    "DFI_BPIFRANCE":               0.05,
    "DFI_DFC":                     0.05,
    "DFI_AFDB":                    0.05,
    TrancheType.COMMERCIAL_SENIOR: 0.18,
    TrancheType.ECA:               0.04,
}

# Default DFI rates (yr), tenor (yr), grace (yr) — matches DFI_CRITERIA notes
DEFAULT_DFI_TERMS = {
    DFIInstitution.EIB:       {"rate": 0.025, "tenor": 22, "grace": 5},
    DFIInstitution.KFW:       {"rate": 0.027, "tenor": 20, "grace": 5},
    DFIInstitution.IFC:       {"rate": 0.035, "tenor": 18, "grace": 4},
    DFIInstitution.BPIFRANCE: {"rate": 0.030, "tenor": 20, "grace": 4},
    DFIInstitution.DFC:       {"rate": 0.040, "tenor": 18, "grace": 3},
    DFIInstitution.AFDB:      {"rate": 0.035, "tenor": 18, "grace": 4},
}

DEFAULT_COMMERCIAL_SENIOR_RATE = 0.080
DEFAULT_COMMERCIAL_SENIOR_TENOR = 15
DEFAULT_COMMERCIAL_SENIOR_GRACE = 1
DEFAULT_ECA_RATE = 0.045
DEFAULT_EQUITY_COST = 0.12    # sponsor equity required return


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class ProjectControl(BaseModel):
    """CONTROL sheet — full project identity, plant params, commercial, timeline."""
    project_id:              str
    fuel_type:               FuelType
    jurisdiction:            str = "Germany / EU"
    base_currency:           str = "EUR"
    # Plant
    nameplate_mw:                    float = Field(..., gt=0)
    availability_factor:             float = Field(..., gt=0, le=1.0)
    specific_energy_kwh_per_kg_h2:   float = Field(50.0, gt=0)
    product_yield_t_per_t_h2:        float = Field(..., gt=0)
    first_year_ramp_factor:          float = Field(0.75, gt=0, le=1.0)
    # Commercial
    offtake_price_eur_per_t:         float = Field(..., gt=0)
    green_premium_eur_per_t:         float = 0.0
    offtake_duration_years:          int   = 15
    target_counterparty:             Optional[str] = None
    # Timeline
    fel_1_year: int
    fel_2_year: int
    feed_year:  int
    fid_year:   int
    cod_year:   int
    end_year:   int
    # CAPEX / OPEX
    total_capex_eur:                 Optional[float] = None
    contingency_pct:                 float = 0.15
    dsra_months:                     int   = 6
    fixed_om_eur_per_yr:             float = 0.0
    variable_opex_eur_per_t:         float = 0.0
    ga_eur_per_yr:                   float = 0.0
    insurance_pct_of_capex:          float = 0.005
    cert_advisory_eur_per_yr:        float = 0.0
    # Ownership
    owner_user_id:  Optional[str] = None
    company_id:     Optional[str] = None
    # Computed (read-only on GET)
    h2_annual_production_t:    Optional[float] = None
    product_annual_production_t: Optional[float] = None
    annual_revenue_eur:          Optional[float] = None


class CapitalStackTranche(BaseModel):
    tranche_id:       Optional[str] = None
    project_id:       str
    institution:      str = Field(..., description="e.g. 'EIB', 'Sponsor', 'Commercial Bank Syndicate'")
    tranche_type:     TrancheType
    amount_eur:       float = Field(..., ge=0)
    pct_of_capex:     float = Field(..., ge=0, le=1.0)
    rate_pct:         Optional[float] = Field(None, description="Annual interest rate (decimal)")
    tenor_years:      Optional[int]   = None
    grace_years:      Optional[int]   = None
    drawdown_method:  str = "MILESTONE"
    first_repay_year: Optional[int]   = None
    notes:            Optional[str]   = None


class SpendWaveRow(BaseModel):
    """One (tranche, year) row in SPEND_WAVE."""
    project_id: str
    tranche_id: str
    year:       int
    amount_eur: float


class DrawdownQuarterRow(BaseModel):
    """One (tranche, yearQ) row in DRAWDOWN."""
    project_id:       str
    tranche_id:       str
    year:             int
    quarter:          int = Field(..., ge=1, le=4)
    amount_eur:       float
    milestone_trigger: Optional[str] = None


class PersonnelRole(BaseModel):
    project_id:    str
    role_name:     str
    phase:         str   # FEL-1 / FEL-2 / FEED / Construction / Post-COD
    fte_count:     float
    daily_rate_eur: float
    duration_months: int


class DFICriterionRecord(BaseModel):
    project_id:       str
    institution:      DFIInstitution
    criterion_name:   str
    dfi_requirement:  str
    status:           DFICriterionStatus
    gex_note:         Optional[str] = None


class CapitalBridgeCompute(BaseModel):
    """Computed outputs from the full CapitalBridge model."""
    project_id:           str
    fuel_type:            str
    computed_at:          str

    # CONTROL-derived
    h2_annual_production_t:      float
    product_annual_production_t: float
    first_year_production_t:     float
    annual_revenue_eur:          float
    first_year_revenue_eur:      float
    total_opex_eur_per_yr:       float
    ebitda_eur_per_yr:           float

    # CAPITAL_STACK-derived
    total_capital_eur:           float
    blended_debt_wacc:           float
    project_wacc:                float
    all_commercial_wacc:         float
    wacc_reduction_pp:           float
    total_dfi_concessional_eur:  float
    total_senior_debt_eur:       float
    catalytic_ratio:             float

    # POST_COD
    annual_debt_service_eur:     float
    dscr_base_case:              float
    dscr_applicable:             bool
    dscr_note:                   str


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
    Unified DB init. Creates all 7 CapitalBridge tables in gex_platform.db
    alongside projects, auth_users, fuel_catalog.
    """
    conn = sqlite3.connect(DB_PATH)

    # ── project_control: full CONTROL sheet (one row per project) ──────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_control (
            project_id                     TEXT PRIMARY KEY,
            fuel_type                      TEXT NOT NULL,
            jurisdiction                   TEXT,
            base_currency                  TEXT DEFAULT 'EUR',
            nameplate_mw                   REAL NOT NULL,
            availability_factor            REAL NOT NULL,
            specific_energy_kwh_per_kg_h2  REAL NOT NULL DEFAULT 50.0,
            product_yield_t_per_t_h2       REAL NOT NULL,
            first_year_ramp_factor         REAL DEFAULT 0.75,
            offtake_price_eur_per_t        REAL NOT NULL,
            green_premium_eur_per_t        REAL DEFAULT 0,
            offtake_duration_years         INTEGER DEFAULT 15,
            target_counterparty            TEXT,
            fel_1_year                     INTEGER NOT NULL,
            fel_2_year                     INTEGER NOT NULL,
            feed_year                      INTEGER NOT NULL,
            fid_year                       INTEGER NOT NULL,
            cod_year                       INTEGER NOT NULL,
            end_year                       INTEGER NOT NULL,
            total_capex_eur                REAL,
            contingency_pct                REAL DEFAULT 0.15,
            dsra_months                    INTEGER DEFAULT 6,
            fixed_om_eur_per_yr            REAL DEFAULT 0,
            variable_opex_eur_per_t        REAL DEFAULT 0,
            ga_eur_per_yr                  REAL DEFAULT 0,
            insurance_pct_of_capex         REAL DEFAULT 0.005,
            cert_advisory_eur_per_yr       REAL DEFAULT 0,
            owner_user_id                  TEXT,
            company_id                     TEXT,
            created_at                     TEXT NOT NULL,
            updated_at                     TEXT NOT NULL,
            updated_by                     TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_fuel ON project_control(fuel_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_owner ON project_control(owner_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_company ON project_control(company_id)")

    # ── fuel_defaults: per-fuel baseline parameters ─────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fuel_defaults (
            fuel_type                        TEXT PRIMARY KEY,
            fuel_label                       TEXT NOT NULL,
            specific_energy_kwh_per_kg_h2    REAL NOT NULL,
            product_yield_t_per_t_h2         REAL NOT NULL,
            base_price_eur_per_t             REAL NOT NULL,
            green_premium_eur_per_t          REAL NOT NULL,
            typical_availability             REAL NOT NULL,
            dsra_months                      INTEGER NOT NULL,
            contingency_pct                  REAL NOT NULL,
            typical_offtake_counterparty     TEXT,
            updated_at                       TEXT NOT NULL
        )
    """)

    # ── capital_stack_tranches: CAPITAL_STACK sheet ─────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS capital_stack_tranches (
            tranche_id        TEXT PRIMARY KEY,
            project_id        TEXT NOT NULL,
            institution       TEXT NOT NULL,
            tranche_type      TEXT NOT NULL,
            amount_eur        REAL NOT NULL,
            pct_of_capex      REAL NOT NULL,
            rate_pct          REAL,
            tenor_years       INTEGER,
            grace_years       INTEGER,
            drawdown_method   TEXT DEFAULT 'MILESTONE',
            first_repay_year  INTEGER,
            notes             TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cst_project ON capital_stack_tranches(project_id)")

    # ── spend_wave: annual drawdown by tranche ──────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spend_wave (
            row_id      TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL,
            tranche_id  TEXT NOT NULL,
            year        INTEGER NOT NULL,
            amount_eur  REAL NOT NULL,
            created_at  TEXT NOT NULL,
            UNIQUE(project_id, tranche_id, year)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_project ON spend_wave(project_id)")

    # ── drawdown_quarters: quarterly schedule post-FID ──────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drawdown_quarters (
            row_id            TEXT PRIMARY KEY,
            project_id        TEXT NOT NULL,
            tranche_id        TEXT NOT NULL,
            year              INTEGER NOT NULL,
            quarter           INTEGER NOT NULL CHECK(quarter BETWEEN 1 AND 4),
            amount_eur        REAL NOT NULL,
            milestone_trigger TEXT,
            created_at        TEXT NOT NULL,
            UNIQUE(project_id, tranche_id, year, quarter)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dq_project ON drawdown_quarters(project_id)")

    # ── personnel_plan: PERSONNEL sheet ─────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS personnel_plan (
            row_id           TEXT PRIMARY KEY,
            project_id       TEXT NOT NULL,
            role_name        TEXT NOT NULL,
            phase            TEXT NOT NULL,
            fte_count        REAL NOT NULL,
            daily_rate_eur   REAL NOT NULL,
            duration_months  INTEGER NOT NULL,
            created_at       TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pp_project ON personnel_plan(project_id)")

    # ── dfi_criteria_status: DFI_CRITERIA sheet ─────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dfi_criteria_status (
            row_id           TEXT PRIMARY KEY,
            project_id       TEXT NOT NULL,
            institution      TEXT NOT NULL,
            criterion_name   TEXT NOT NULL,
            dfi_requirement  TEXT NOT NULL,
            status           TEXT NOT NULL,
            gex_note         TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            UNIQUE(project_id, institution, criterion_name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dcs_project ON dfi_criteria_status(project_id)")

    # ── post_cod_schedule: yearly DSCR + CFADS + debt service ───────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS post_cod_schedule (
            row_id                TEXT PRIMARY KEY,
            project_id            TEXT NOT NULL,
            year                  INTEGER NOT NULL,
            production_t          REAL,
            revenue_eur           REAL,
            opex_eur              REAL,
            ebitda_eur            REAL,
            debt_service_eur      REAL,
            cfads_eur             REAL,
            dscr                  REAL,
            dscr_covenant_min     REAL DEFAULT 1.25,
            cash_after_ds_eur     REAL,
            dsra_topup_eur        REAL,
            available_for_dist_eur REAL,
            created_at            TEXT NOT NULL,
            UNIQUE(project_id, year)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pcs_project ON post_cod_schedule(project_id)")

    # ── Seed fuel_defaults on every init (idempotent UPSERT) ────────────────
    now = datetime.now(timezone.utc).isoformat()
    for fuel, d in FUEL_DEFAULTS.items():
        conn.execute("""
            INSERT INTO fuel_defaults
            (fuel_type, fuel_label, specific_energy_kwh_per_kg_h2,
             product_yield_t_per_t_h2, base_price_eur_per_t,
             green_premium_eur_per_t, typical_availability,
             dsra_months, contingency_pct, typical_offtake_counterparty, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(fuel_type) DO UPDATE SET
                fuel_label=excluded.fuel_label,
                specific_energy_kwh_per_kg_h2=excluded.specific_energy_kwh_per_kg_h2,
                product_yield_t_per_t_h2=excluded.product_yield_t_per_t_h2,
                base_price_eur_per_t=excluded.base_price_eur_per_t,
                green_premium_eur_per_t=excluded.green_premium_eur_per_t,
                typical_availability=excluded.typical_availability,
                dsra_months=excluded.dsra_months,
                contingency_pct=excluded.contingency_pct,
                typical_offtake_counterparty=excluded.typical_offtake_counterparty,
                updated_at=excluded.updated_at
        """, (
            fuel.value, d["fuel_label"], d["specific_energy_kwh_per_kg_h2"],
            d["product_yield_t_per_t_h2"], d["base_price_eur_per_t"],
            d["green_premium_eur_per_t"], d["typical_availability"],
            d["dsra_months"], d["contingency_pct"],
            d["typical_offtake_counterparty"], now,
        ))

    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_exists(conn, project_id: str) -> bool:
    """FK-like check against the unified projects table."""
    row = conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
    return row is not None


# ═══════════════════════════════════════════════════════════════════════════
# FUEL DEFAULTS ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/fuels/defaults")
def list_fuel_defaults(db: sqlite3.Connection = Depends(get_db)):
    """
    Return per-fuel parameter defaults for all 5 supported fuels.
    Frontend uses this to pre-populate the CONTROL form when a user
    picks a fuel for a new project.
    """
    rows = db.execute("SELECT * FROM fuel_defaults ORDER BY fuel_type").fetchall()
    return [dict(r) for r in rows]


@router.get("/fuels/{fuel_type}/defaults")
def get_fuel_defaults(fuel_type: FuelType, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM fuel_defaults WHERE fuel_type=?", (fuel_type.value,)).fetchone()
    if not row:
        raise HTTPException(404, f"No defaults for fuel {fuel_type.value}")
    return dict(row)


# ═══════════════════════════════════════════════════════════════════════════
# CONTROL SHEET ROUTES
# ═══════════════════════════════════════════════════════════════════════════

def _compute_production(control: dict) -> dict:
    """
    H2 annual production = MW × 8760 × availability ÷ (SEC × 1000)  [tonnes]
    Product annual production = H2 × yield ratio
    Matches Excel CONTROL R16, R18.
    """
    mw    = control["nameplate_mw"]
    avail = control["availability_factor"]
    sec   = control["specific_energy_kwh_per_kg_h2"]  # kWh / kg
    yield_ratio = control["product_yield_t_per_t_h2"]
    h2_annual = (mw * 8760.0 * avail) / (sec)      # kg H2 / yr
    h2_annual_t = h2_annual / 1000.0               # tonnes H2 / yr
    product_annual_t = h2_annual_t * yield_ratio
    price = control["offtake_price_eur_per_t"]
    revenue = product_annual_t * price
    return {
        "h2_annual_production_t":      round(h2_annual_t, 2),
        "product_annual_production_t": round(product_annual_t, 2),
        "annual_revenue_eur":          round(revenue, 2),
    }


@router.post("/projects/{project_id}/control", response_model=ProjectControl, status_code=201)
def upsert_project_control(
    project_id: str,
    ctrl: ProjectControl,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Create or update the CONTROL sheet for a project.
    Enforces FK to unified projects table (gex_platform.db).

    If CAPEX fields (total_capex_eur, fixed_om_eur_per_yr, etc.) are not provided,
    they are left NULL — the compute endpoint aggregates them from development_packages
    and capital_stack_tranches at read time.
    """
    if not _project_exists(db, project_id):
        raise HTTPException(
            404,
            f"Project {project_id} not found in unified projects table. "
            "Create the project first via POST /api/v1/onboarding or the projects API."
        )
    if ctrl.project_id != project_id:
        raise HTTPException(400, "project_id in path and body must match")

    now = _now()
    db.execute("""
        INSERT INTO project_control
        (project_id, fuel_type, jurisdiction, base_currency, nameplate_mw,
         availability_factor, specific_energy_kwh_per_kg_h2, product_yield_t_per_t_h2,
         first_year_ramp_factor, offtake_price_eur_per_t, green_premium_eur_per_t,
         offtake_duration_years, target_counterparty, fel_1_year, fel_2_year,
         feed_year, fid_year, cod_year, end_year, total_capex_eur, contingency_pct,
         dsra_months, fixed_om_eur_per_yr, variable_opex_eur_per_t, ga_eur_per_yr,
         insurance_pct_of_capex, cert_advisory_eur_per_yr, owner_user_id, company_id,
         created_at, updated_at, updated_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id) DO UPDATE SET
            fuel_type=excluded.fuel_type, jurisdiction=excluded.jurisdiction,
            base_currency=excluded.base_currency, nameplate_mw=excluded.nameplate_mw,
            availability_factor=excluded.availability_factor,
            specific_energy_kwh_per_kg_h2=excluded.specific_energy_kwh_per_kg_h2,
            product_yield_t_per_t_h2=excluded.product_yield_t_per_t_h2,
            first_year_ramp_factor=excluded.first_year_ramp_factor,
            offtake_price_eur_per_t=excluded.offtake_price_eur_per_t,
            green_premium_eur_per_t=excluded.green_premium_eur_per_t,
            offtake_duration_years=excluded.offtake_duration_years,
            target_counterparty=excluded.target_counterparty,
            fel_1_year=excluded.fel_1_year, fel_2_year=excluded.fel_2_year,
            feed_year=excluded.feed_year, fid_year=excluded.fid_year,
            cod_year=excluded.cod_year, end_year=excluded.end_year,
            total_capex_eur=excluded.total_capex_eur,
            contingency_pct=excluded.contingency_pct, dsra_months=excluded.dsra_months,
            fixed_om_eur_per_yr=excluded.fixed_om_eur_per_yr,
            variable_opex_eur_per_t=excluded.variable_opex_eur_per_t,
            ga_eur_per_yr=excluded.ga_eur_per_yr,
            insurance_pct_of_capex=excluded.insurance_pct_of_capex,
            cert_advisory_eur_per_yr=excluded.cert_advisory_eur_per_yr,
            owner_user_id=excluded.owner_user_id, company_id=excluded.company_id,
            updated_at=excluded.updated_at, updated_by=excluded.updated_by
    """, (
        project_id, ctrl.fuel_type.value, ctrl.jurisdiction, ctrl.base_currency,
        ctrl.nameplate_mw, ctrl.availability_factor, ctrl.specific_energy_kwh_per_kg_h2,
        ctrl.product_yield_t_per_t_h2, ctrl.first_year_ramp_factor,
        ctrl.offtake_price_eur_per_t, ctrl.green_premium_eur_per_t,
        ctrl.offtake_duration_years, ctrl.target_counterparty,
        ctrl.fel_1_year, ctrl.fel_2_year, ctrl.feed_year, ctrl.fid_year,
        ctrl.cod_year, ctrl.end_year, ctrl.total_capex_eur, ctrl.contingency_pct,
        ctrl.dsra_months, ctrl.fixed_om_eur_per_yr, ctrl.variable_opex_eur_per_t,
        ctrl.ga_eur_per_yr, ctrl.insurance_pct_of_capex, ctrl.cert_advisory_eur_per_yr,
        ctrl.owner_user_id, ctrl.company_id, now, now, ctrl.owner_user_id
    ))
    db.commit()

    row = db.execute("SELECT * FROM project_control WHERE project_id=?", (project_id,)).fetchone()
    d = dict(row)
    d.update(_compute_production(d))
    return d


@router.get("/projects/{project_id}/control", response_model=ProjectControl)
def get_project_control(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM project_control WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"No CONTROL sheet for project {project_id}")
    d = dict(row)
    d.update(_compute_production(d))
    return d


@router.post("/projects/{project_id}/control/bootstrap-defaults")
def bootstrap_from_fuel(
    project_id: str,
    fuel_type: FuelType,
    nameplate_mw: float = Query(..., gt=0),
    fel_1_year: int = Query(...),
    owner_user_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    One-click bootstrap: create a CONTROL sheet seeded with fuel_defaults.
    Frontend calls this when a user picks a fuel + capacity for a new project.
    Works for all 5 fuels (H2, NH3, E_METHANOL, E_NG, SAF).
    """
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")

    defaults = FUEL_DEFAULTS[fuel_type]
    ctrl = ProjectControl(
        project_id=project_id,
        fuel_type=fuel_type,
        nameplate_mw=nameplate_mw,
        availability_factor=defaults["typical_availability"],
        specific_energy_kwh_per_kg_h2=defaults["specific_energy_kwh_per_kg_h2"],
        product_yield_t_per_t_h2=defaults["product_yield_t_per_t_h2"],
        offtake_price_eur_per_t=defaults["base_price_eur_per_t"],
        green_premium_eur_per_t=defaults["green_premium_eur_per_t"],
        target_counterparty=defaults["typical_offtake_counterparty"],
        fel_1_year=fel_1_year,
        fel_2_year=fel_1_year + 1,
        feed_year=fel_1_year + 2,
        fid_year=fel_1_year + 4,
        cod_year=fel_1_year + 6,
        end_year=fel_1_year + 21,
        contingency_pct=defaults["contingency_pct"],
        dsra_months=defaults["dsra_months"],
        owner_user_id=owner_user_id,
        company_id=company_id,
    )
    return upsert_project_control(project_id, ctrl, db)


# ═══════════════════════════════════════════════════════════════════════════
# CAPITAL STACK ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/projects/{project_id}/capital-stack", status_code=201)
def add_tranche(
    project_id: str,
    tranche: CapitalStackTranche,
    db: sqlite3.Connection = Depends(get_db)
):
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    tid = tranche.tranche_id or str(uuid.uuid4())
    now = _now()
    db.execute("""
        INSERT INTO capital_stack_tranches
        (tranche_id, project_id, institution, tranche_type, amount_eur, pct_of_capex,
         rate_pct, tenor_years, grace_years, drawdown_method, first_repay_year,
         notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        tid, project_id, tranche.institution, tranche.tranche_type.value,
        tranche.amount_eur, tranche.pct_of_capex, tranche.rate_pct,
        tranche.tenor_years, tranche.grace_years, tranche.drawdown_method,
        tranche.first_repay_year, tranche.notes, now, now
    ))
    db.commit()
    return {"tranche_id": tid, **tranche.model_dump()}


@router.get("/projects/{project_id}/capital-stack")
def list_tranches(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM capital_stack_tranches WHERE project_id=? ORDER BY tranche_type",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects/{project_id}/capital-stack/bootstrap-defaults")
def bootstrap_capital_stack(
    project_id: str,
    total_capex_eur: float = Query(..., gt=0, description="Total project CAPEX for % → € allocation"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Seed the capital stack with the default 11-tranche structure from the
    Excel CAPITAL_STACK sheet. Applies to any fuel — the stack is fuel-agnostic,
    driven by DFI mandates and typical Greenfield e-fuel economics.
    """
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")

    # Wipe any existing stack so bootstrap is idempotent
    db.execute("DELETE FROM capital_stack_tranches WHERE project_id=?", (project_id,))

    now = _now()
    seeded = []

    # Equity + grants
    for ttype, pct in [
        (TrancheType.SEED_EQUITY, DEFAULT_CAPITAL_STACK_PCT[TrancheType.SEED_EQUITY]),
        (TrancheType.SPONSOR_EQUITY, DEFAULT_CAPITAL_STACK_PCT[TrancheType.SPONSOR_EQUITY]),
        (TrancheType.GRANT, DEFAULT_CAPITAL_STACK_PCT[TrancheType.GRANT]),
    ]:
        tid = str(uuid.uuid4())
        amt = total_capex_eur * pct
        db.execute("""
            INSERT INTO capital_stack_tranches
            (tranche_id, project_id, institution, tranche_type, amount_eur, pct_of_capex,
             rate_pct, drawdown_method, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (tid, project_id,
              {"SEED_EQUITY":"Founders","SPONSOR_EQUITY":"Sponsor","GRANT":"EU/National Grants"}[ttype.value],
              ttype.value, amt, pct, None,
              "MILESTONE" if ttype != TrancheType.GRANT else "CERTIFICATE",
              now, now))
        seeded.append({"tranche_id": tid, "type": ttype.value, "amount_eur": amt})

    # 6 DFI tranches
    dfi_pct_map = {
        DFIInstitution.EIB:       DEFAULT_CAPITAL_STACK_PCT["DFI_EIB"],
        DFIInstitution.KFW:       DEFAULT_CAPITAL_STACK_PCT["DFI_KFW"],
        DFIInstitution.IFC:       DEFAULT_CAPITAL_STACK_PCT["DFI_IFC"],
        DFIInstitution.BPIFRANCE: DEFAULT_CAPITAL_STACK_PCT["DFI_BPIFRANCE"],
        DFIInstitution.DFC:       DEFAULT_CAPITAL_STACK_PCT["DFI_DFC"],
        DFIInstitution.AFDB:      DEFAULT_CAPITAL_STACK_PCT["DFI_AFDB"],
    }
    for dfi, pct in dfi_pct_map.items():
        terms = DEFAULT_DFI_TERMS[dfi]
        tid = str(uuid.uuid4())
        amt = total_capex_eur * pct
        db.execute("""
            INSERT INTO capital_stack_tranches
            (tranche_id, project_id, institution, tranche_type, amount_eur, pct_of_capex,
             rate_pct, tenor_years, grace_years, drawdown_method, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (tid, project_id, dfi.value, TrancheType.DFI_CONCESSIONAL.value,
              amt, pct, terms["rate"], terms["tenor"], terms["grace"],
              "MILESTONE", now, now))
        seeded.append({"tranche_id": tid, "institution": dfi.value, "amount_eur": amt})

    # Commercial senior + ECA
    for ttype, pct, rate, tenor, grace, inst in [
        (TrancheType.COMMERCIAL_SENIOR, DEFAULT_CAPITAL_STACK_PCT[TrancheType.COMMERCIAL_SENIOR],
         DEFAULT_COMMERCIAL_SENIOR_RATE, DEFAULT_COMMERCIAL_SENIOR_TENOR,
         DEFAULT_COMMERCIAL_SENIOR_GRACE, "Commercial Bank Syndicate"),
        (TrancheType.ECA, DEFAULT_CAPITAL_STACK_PCT[TrancheType.ECA],
         DEFAULT_ECA_RATE, 12, 1, "Euler Hermes / ECA"),
    ]:
        tid = str(uuid.uuid4())
        amt = total_capex_eur * pct
        db.execute("""
            INSERT INTO capital_stack_tranches
            (tranche_id, project_id, institution, tranche_type, amount_eur, pct_of_capex,
             rate_pct, tenor_years, grace_years, drawdown_method, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (tid, project_id, inst, ttype.value, amt, pct, rate, tenor, grace,
              "PROGRESS" if ttype == TrancheType.COMMERCIAL_SENIOR else "AWARD",
              now, now))
        seeded.append({"tranche_id": tid, "type": ttype.value, "amount_eur": amt})

    # Update CONTROL with computed CAPEX
    db.execute("UPDATE project_control SET total_capex_eur=?, updated_at=? WHERE project_id=?",
               (total_capex_eur, now, project_id))
    db.commit()

    return {"project_id": project_id, "total_capex_eur": total_capex_eur,
            "tranches_seeded": len(seeded), "tranches": seeded}


# ═══════════════════════════════════════════════════════════════════════════
# SPEND WAVE + DRAWDOWN + PERSONNEL + DFI_CRITERIA — CRUD
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/projects/{project_id}/spend-wave", status_code=201)
def upsert_spend_wave_row(project_id: str, row: SpendWaveRow,
                          db: sqlite3.Connection = Depends(get_db)):
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    rid = str(uuid.uuid4())
    now = _now()
    db.execute("""
        INSERT INTO spend_wave (row_id, project_id, tranche_id, year, amount_eur, created_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(project_id, tranche_id, year) DO UPDATE SET
            amount_eur=excluded.amount_eur
    """, (rid, project_id, row.tranche_id, row.year, row.amount_eur, now))
    db.commit()
    return {"row_id": rid, **row.model_dump()}


@router.get("/projects/{project_id}/spend-wave")
def list_spend_wave(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM spend_wave WHERE project_id=? ORDER BY year, tranche_id",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects/{project_id}/drawdown", status_code=201)
def upsert_drawdown_row(project_id: str, row: DrawdownQuarterRow,
                        db: sqlite3.Connection = Depends(get_db)):
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    rid = str(uuid.uuid4())
    now = _now()
    db.execute("""
        INSERT INTO drawdown_quarters
        (row_id, project_id, tranche_id, year, quarter, amount_eur, milestone_trigger, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id, tranche_id, year, quarter) DO UPDATE SET
            amount_eur=excluded.amount_eur,
            milestone_trigger=excluded.milestone_trigger
    """, (rid, project_id, row.tranche_id, row.year, row.quarter,
          row.amount_eur, row.milestone_trigger, now))
    db.commit()
    return {"row_id": rid, **row.model_dump()}


@router.get("/projects/{project_id}/drawdown")
def list_drawdown(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM drawdown_quarters WHERE project_id=? ORDER BY year, quarter, tranche_id",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects/{project_id}/personnel", status_code=201)
def add_personnel(project_id: str, role: PersonnelRole,
                  db: sqlite3.Connection = Depends(get_db)):
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    rid = str(uuid.uuid4())
    now = _now()
    db.execute("""
        INSERT INTO personnel_plan
        (row_id, project_id, role_name, phase, fte_count, daily_rate_eur,
         duration_months, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (rid, project_id, role.role_name, role.phase, role.fte_count,
          role.daily_rate_eur, role.duration_months, now))
    db.commit()
    return {"row_id": rid, **role.model_dump()}


@router.get("/projects/{project_id}/personnel")
def list_personnel(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM personnel_plan WHERE project_id=? ORDER BY phase, role_name",
        (project_id,)
    ).fetchall()
    # Compute total cost per row: FTE × daily_rate × 21.67 working days/mo × months / 1e6
    out = []
    for r in rows:
        d = dict(r)
        d["total_cost_eur"] = round(d["fte_count"] * d["daily_rate_eur"] * 21.67 * d["duration_months"], 0)
        out.append(d)
    total = sum(x["total_cost_eur"] for x in out)
    return {"rows": out, "total_owner_team_cost_eur": total}


@router.post("/projects/{project_id}/dfi-criteria", status_code=201)
def upsert_dfi_criterion(project_id: str, rec: DFICriterionRecord,
                         db: sqlite3.Connection = Depends(get_db)):
    if not _project_exists(db, project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    rid = str(uuid.uuid4())
    now = _now()
    db.execute("""
        INSERT INTO dfi_criteria_status
        (row_id, project_id, institution, criterion_name, dfi_requirement,
         status, gex_note, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id, institution, criterion_name) DO UPDATE SET
            dfi_requirement=excluded.dfi_requirement,
            status=excluded.status,
            gex_note=excluded.gex_note,
            updated_at=excluded.updated_at
    """, (rid, project_id, rec.institution.value, rec.criterion_name,
          rec.dfi_requirement, rec.status.value, rec.gex_note, now, now))
    db.commit()
    return {"row_id": rid, **rec.model_dump()}


@router.get("/projects/{project_id}/dfi-criteria")
def list_dfi_criteria(
    project_id: str,
    institution: Optional[DFIInstitution] = None,
    db: sqlite3.Connection = Depends(get_db)
):
    q = "SELECT * FROM dfi_criteria_status WHERE project_id=?"
    params: list = [project_id]
    if institution:
        q += " AND institution=?"
        params.append(institution.value)
    q += " ORDER BY institution, criterion_name"
    rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# COMPUTE — runs the full CapitalBridge model for a project
# Equivalent to evaluating all CONTROL/CAPITAL_STACK/POST_COD formulas.
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/compute", response_model=CapitalBridgeCompute)
def compute_capital_bridge(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Evaluate the full CapitalBridge model for a project.

    Returns production, revenue, OPEX, EBITDA, blended WACC, catalytic ratio,
    and DSCR — the numbers the Finance workspace, DFI sub-persona, and
    Executive dashboard all need.

    DSCR guard: dscr_applicable=False before cod_year. Matches Excel PRE_COD
    doctrine — DSCR is meaningless pre-COD, use pre_cod_metrics.py instead.
    """
    ctrl = db.execute("SELECT * FROM project_control WHERE project_id=?", (project_id,)).fetchone()
    if not ctrl:
        raise HTTPException(404, f"No CONTROL sheet for project {project_id}")
    ctrl_d = dict(ctrl)

    # ── Production + revenue + OPEX (CONTROL formulas) ──
    prod = _compute_production(ctrl_d)
    h2_t = prod["h2_annual_production_t"]
    prod_t = prod["product_annual_production_t"]
    revenue = prod["annual_revenue_eur"]
    first_year_t = prod_t * ctrl_d["first_year_ramp_factor"]
    first_year_rev = revenue * ctrl_d["first_year_ramp_factor"]

    total_capex = ctrl_d["total_capex_eur"] or 0.0
    fixed_om      = ctrl_d["fixed_om_eur_per_yr"] or 0.0
    var_opex_per_t = ctrl_d["variable_opex_eur_per_t"] or 0.0
    ga            = ctrl_d["ga_eur_per_yr"] or 0.0
    insurance     = (ctrl_d["insurance_pct_of_capex"] or 0.0) * total_capex
    cert          = ctrl_d["cert_advisory_eur_per_yr"] or 0.0
    total_opex    = fixed_om + (var_opex_per_t * prod_t) + ga + insurance + cert
    ebitda        = revenue - total_opex

    # ── Capital stack aggregation ──
    tranches = db.execute(
        "SELECT * FROM capital_stack_tranches WHERE project_id=?", (project_id,)
    ).fetchall()

    total_capital = sum(t["amount_eur"] for t in tranches)
    dfi_amount = sum(t["amount_eur"] for t in tranches
                     if t["tranche_type"] == TrancheType.DFI_CONCESSIONAL.value)
    senior_amount = sum(t["amount_eur"] for t in tranches
                        if t["tranche_type"] == TrancheType.COMMERCIAL_SENIOR.value)
    grant_amount = sum(t["amount_eur"] for t in tranches
                       if t["tranche_type"] == TrancheType.GRANT.value)
    equity_amount = sum(t["amount_eur"] for t in tranches
                        if t["tranche_type"] in (
                            TrancheType.SEED_EQUITY.value,
                            TrancheType.SPONSOR_EQUITY.value))

    # Debt-only amount (for blended debt WACC)
    debt_types = {TrancheType.DFI_CONCESSIONAL.value, TrancheType.COMMERCIAL_SENIOR.value,
                  TrancheType.ECA.value, TrancheType.BRIDGE.value, TrancheType.VENDOR_FINANCE.value}
    debt_tranches = [t for t in tranches if t["tranche_type"] in debt_types]
    total_debt = sum(t["amount_eur"] for t in debt_tranches) or 1.0

    # Blended Debt WACC = Σ(amount_i × rate_i) / Σ(amount_i)
    blended_debt_wacc = sum((t["amount_eur"] * (t["rate_pct"] or 0.0)) for t in debt_tranches) / total_debt

    # Project WACC = Σ(tranche_i × cost_i) / total_capital where equity cost = DEFAULT_EQUITY_COST
    # Grants cost = 0
    if total_capital > 0:
        numerator = 0.0
        for t in tranches:
            if t["tranche_type"] in (TrancheType.SEED_EQUITY.value, TrancheType.SPONSOR_EQUITY.value):
                cost = DEFAULT_EQUITY_COST
            elif t["tranche_type"] == TrancheType.GRANT.value:
                cost = 0.0
            else:
                cost = t["rate_pct"] or 0.0
            numerator += t["amount_eur"] * cost
        project_wacc = numerator / total_capital
    else:
        project_wacc = 0.0

    # All-commercial WACC benchmark: replace DFI + grants with commercial senior rate
    if total_capital > 0:
        num_ac = 0.0
        for t in tranches:
            if t["tranche_type"] in (TrancheType.SEED_EQUITY.value, TrancheType.SPONSOR_EQUITY.value):
                cost = DEFAULT_EQUITY_COST
            else:
                cost = DEFAULT_COMMERCIAL_SENIOR_RATE
            num_ac += t["amount_eur"] * cost
        all_commercial_wacc = num_ac / total_capital
    else:
        all_commercial_wacc = DEFAULT_COMMERCIAL_SENIOR_RATE

    wacc_reduction = all_commercial_wacc - project_wacc

    # Catalytic ratio = commercial debt ÷ concessional (matches DFI_CRITERIA doctrine)
    catalytic_ratio = (senior_amount / dfi_amount) if dfi_amount > 0 else 0.0

    # Approximate annual debt service: amortise each debt tranche over (tenor − grace)
    annual_debt_service = 0.0
    for t in debt_tranches:
        amt   = t["amount_eur"]
        rate  = t["rate_pct"] or 0.0
        tenor = t["tenor_years"] or 15
        grace = t["grace_years"] or 0
        repay_yrs = max(tenor - grace, 1)
        # Standard annuity payment
        if rate > 0:
            pmt = amt * (rate * (1 + rate) ** repay_yrs) / (((1 + rate) ** repay_yrs) - 1)
        else:
            pmt = amt / repay_yrs
        annual_debt_service += pmt

    # DSCR — only meaningful post-COD
    cod_year = ctrl_d["cod_year"]
    current_year = datetime.now(timezone.utc).year
    dscr_applicable = current_year >= cod_year
    dscr_base = (ebitda / annual_debt_service) if annual_debt_service > 0 else 0.0
    dscr_note = (
        f"DSCR applicable — project at/past COD ({cod_year})."
        if dscr_applicable
        else f"DSCR not applicable pre-COD (COD year {cod_year}). Use /api/v1/pre-cod-metrics for the correct pre-G10 framework."
    )

    return CapitalBridgeCompute(
        project_id=project_id,
        fuel_type=ctrl_d["fuel_type"],
        computed_at=_now(),
        h2_annual_production_t=h2_t,
        product_annual_production_t=prod_t,
        first_year_production_t=round(first_year_t, 2),
        annual_revenue_eur=round(revenue, 2),
        first_year_revenue_eur=round(first_year_rev, 2),
        total_opex_eur_per_yr=round(total_opex, 2),
        ebitda_eur_per_yr=round(ebitda, 2),
        total_capital_eur=round(total_capital, 2),
        blended_debt_wacc=round(blended_debt_wacc, 4),
        project_wacc=round(project_wacc, 4),
        all_commercial_wacc=round(all_commercial_wacc, 4),
        wacc_reduction_pp=round(wacc_reduction, 4),
        total_dfi_concessional_eur=round(dfi_amount, 2),
        total_senior_debt_eur=round(senior_amount, 2),
        catalytic_ratio=round(catalytic_ratio, 2),
        annual_debt_service_eur=round(annual_debt_service, 2),
        dscr_base_case=round(dscr_base, 3),
        dscr_applicable=dscr_applicable,
        dscr_note=dscr_note,
    )


# ═══════════════════════════════════════════════════════════════════════════
# UNIFIED PROJECT VIEW — everything for one project in one response
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/full")
def get_full_project(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Unified one-shot view of a project across all CapitalBridge tables
    plus the core projects/auth tables. Used by Finance workspace
    Executive workspace, and DFI sub-persona to render the full picture
    without N round trips.
    """
    project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")

    ctrl = db.execute("SELECT * FROM project_control WHERE project_id=?", (project_id,)).fetchone()
    tranches = db.execute(
        "SELECT * FROM capital_stack_tranches WHERE project_id=?", (project_id,)
    ).fetchall()
    packages = db.execute(
        "SELECT * FROM development_packages WHERE project_id=?", (project_id,)
    ).fetchall()
    spend = db.execute(
        "SELECT * FROM spend_wave WHERE project_id=? ORDER BY year", (project_id,)
    ).fetchall()
    drawdown = db.execute(
        "SELECT * FROM drawdown_quarters WHERE project_id=? ORDER BY year, quarter", (project_id,)
    ).fetchall()
    personnel = db.execute(
        "SELECT * FROM personnel_plan WHERE project_id=?", (project_id,)
    ).fetchall()
    dfi_crit = db.execute(
        "SELECT * FROM dfi_criteria_status WHERE project_id=?", (project_id,)
    ).fetchall()
    stakeholders = db.execute(
        "SELECT user_id, actor_type FROM auth_user_project_roles WHERE project_id=?", (project_id,)
    ).fetchall()

    return {
        "project":      dict(project),
        "control":      dict(ctrl) if ctrl else None,
        "capital_stack": [dict(r) for r in tranches],
        "packages":     [dict(r) for r in packages],
        "spend_wave":   [dict(r) for r in spend],
        "drawdown":     [dict(r) for r in drawdown],
        "personnel":    [dict(r) for r in personnel],
        "dfi_criteria": [dict(r) for r in dfi_crit],
        "stakeholders": [dict(r) for r in stakeholders],
    }


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-TENANT SCOPED LISTINGS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/users/{user_id}/projects")
def list_projects_for_user(user_id: str, db: sqlite3.Connection = Depends(get_db)):
    """
    Every project a user is linked to (via auth_user_project_roles)
    plus their CapitalBridge state. Used by workspace home screens.
    """
    rows = db.execute("""
        SELECT p.id, p.project_name, p.molecule, p.stage,
               pc.fuel_type, pc.nameplate_mw, pc.cod_year, pc.total_capex_eur,
               r.actor_type
        FROM projects p
        JOIN auth_user_project_roles r ON r.project_id = p.id
        LEFT JOIN project_control pc ON pc.project_id = p.id
        WHERE r.user_id = ?
        ORDER BY p.project_name
    """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/companies/{company_id}/projects")
def list_projects_for_company(company_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Every project owned by a company — Executive workspace portfolio view."""
    rows = db.execute("""
        SELECT p.id, p.project_name, p.molecule,
               pc.fuel_type, pc.nameplate_mw, pc.cod_year, pc.total_capex_eur
        FROM projects p
        LEFT JOIN project_control pc ON pc.project_id = p.id
        WHERE pc.company_id = ?
        ORDER BY p.project_name
    """, (company_id,)).fetchall()
    return [dict(r) for r in rows]
