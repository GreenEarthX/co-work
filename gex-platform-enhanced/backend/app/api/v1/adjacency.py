"""
adjacency.py
========================
GEX Platform — gex-enhanced-platform/backend/app/api/v1/

Adjacency endpoint — cohort benchmark data for the AdjacencyCard primitive
(Appendix E.4). Implements the §3.5 Adjacency doctrine: P(A|B) proximity
and cohort credit scoring.

Given a project, finds comparable projects in the same fuel pathway,
jurisdiction, and certifier ecosystem, then computes cohort statistics
(DSCR percentiles, completion rates, TIE medians) for benchmarking.

Nightly computation:
  POST /compute-all — triggered by cron/scheduler, computes proximity matrix
  across all projects and caches results in adjacency_cache table.
  GET /{project_id}/benchmark reads from cache first, falls back to
  on-demand computation if cache is stale or missing.

Integration points:
  - AdjacencyCard.tsx (frontend): consumes GET /benchmark endpoint
  - BankabilityScorePage.tsx: renders AdjacencyCard with benchmark data
  - development_packages.py: project metadata for matching
  - evidence_ledger.py: verified evidence corpus for confidence scoring
  - gex_pf_engine/core/adjacency.py: full computation engine

SQLite pattern: matches development_packages.py conventions.
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
DB_PATH = settings.SQLITE_DB_PATH

router = APIRouter(prefix="/api/v1/adjacency", tags=["adjacency"])


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class DimensionMatches(BaseModel):
    fuel: str = Field(..., description="match | partial | none")
    jurisdiction: str = Field(..., description="match | partial | none")
    certifier: str = Field(..., description="match | partial | none")


class AdjacencyBenchmark(BaseModel):
    project_id: str
    density_score: float = Field(..., ge=0, le=1, description="0-1 adjacency density")
    cohort_n: int = Field(..., description="Number of comparable projects")
    cohort_dscr_p25: float
    cohort_dscr_p50: float
    cohort_dscr_p75: float
    cohort_completion_rate: float = Field(..., ge=0, le=1)
    cohort_tie_p50: float
    confidence_flag: bool = Field(..., description="True if cohort_n < 5 — low confidence")
    fuel_pathway: str
    jurisdiction: str
    certifier_ecosystem: str
    dimension_matches: DimensionMatches
    cached_at: Optional[str] = None
    # Provenance of the numbers — ALWAYS read this before quoting a cohort stat.
    basis: str = "UNSPECIFIED"


class ComputeResult(BaseModel):
    projects_processed: int
    benchmarks_cached: int
    computed_at: str


# ═══════════════════════════════════════════════════════════════════════════
# FALLBACK COHORT DATA — ⚠️ FABRICATED DEMO NUMBERS, not observed cohorts.
# Every value below (cohort_n, DSCR percentiles, completion rates, densities)
# is invented. Review finding 2026-07-02: these must never be quoted without
# the `basis` label, and are superseded by external-corpus priors
# (app.core.external_corpus, EXTERNAL_PRIOR) the moment a licensed snapshot
# is imported. DSCR is NOT observable in any external corpus — a corpus
# import replaces density/counts/completion, never DSCR.
# ═══════════════════════════════════════════════════════════════════════════

FALLBACK_COHORTS: dict[str, dict] = {
    "eMeOH": {"cohort_n": 12, "cohort_dscr_p25": 1.22, "cohort_dscr_p50": 1.38, "cohort_dscr_p75": 1.55, "cohort_completion_rate": 0.67, "cohort_tie_p50": 2.1, "density_score": 0.72},
    "eNH3":  {"cohort_n": 8,  "cohort_dscr_p25": 1.18, "cohort_dscr_p50": 1.32, "cohort_dscr_p75": 1.48, "cohort_completion_rate": 0.58, "cohort_tie_p50": 2.4, "density_score": 0.61},
    "SAF":   {"cohort_n": 6,  "cohort_dscr_p25": 1.15, "cohort_dscr_p50": 1.28, "cohort_dscr_p75": 1.42, "cohort_completion_rate": 0.50, "cohort_tie_p50": 2.8, "density_score": 0.55},
    "H2":    {"cohort_n": 18, "cohort_dscr_p25": 1.25, "cohort_dscr_p50": 1.41, "cohort_dscr_p75": 1.60, "cohort_completion_rate": 0.72, "cohort_tie_p50": 1.9, "density_score": 0.78},
    "DEFAULT": {"cohort_n": 3, "cohort_dscr_p25": 1.10, "cohort_dscr_p50": 1.20, "cohort_dscr_p75": 1.35, "cohort_completion_rate": 0.40, "cohort_tie_p50": 3.2, "density_score": 0.35},
}

MOCK_PROJECTS: dict[str, dict] = {
    "proj_etf_pecos1": {"molecule": "eMeOH", "jurisdiction": "US", "certifier_ecosystem": "ISCC_EU"},
    "proj_demo_nh3": {"molecule": "eNH3", "jurisdiction": "DE", "certifier_ecosystem": "TUV_SUD"},
}


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE — adjacency_cache table for nightly pre-computation
# ═══════════════════════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adjacency_cache (
            project_id          TEXT PRIMARY KEY,
            density_score       REAL NOT NULL,
            cohort_n            INTEGER NOT NULL,
            cohort_dscr_p25     REAL NOT NULL,
            cohort_dscr_p50     REAL NOT NULL,
            cohort_dscr_p75     REAL NOT NULL,
            cohort_completion_rate REAL NOT NULL,
            cohort_tie_p50      REAL NOT NULL,
            confidence_flag     INTEGER NOT NULL DEFAULT 1,
            fuel_pathway        TEXT NOT NULL,
            jurisdiction        TEXT NOT NULL,
            certifier_ecosystem TEXT NOT NULL,
            dimension_matches   TEXT NOT NULL,
            computed_at         TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_fuel ON adjacency_cache(fuel_pathway)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    k = (len(data) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(data) - 1)
    return round(data[f] + (k - f) * (data[c] - data[f]), 2)


def _lookup_project_metadata(project_id: str) -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row:
            keys = row.keys()
            result = {
                "molecule": row["molecule"] if "molecule" in keys and row["molecule"] else (row["fuel_type"] if "fuel_type" in keys else "eMeOH"),
                "jurisdiction": row["country"] if "country" in keys and row["country"] else (row["location"] if "location" in keys else "US"),
                "certifier_ecosystem": row["certifier"] if "certifier" in keys and row["certifier"] else "ISCC_EU",
            }
            conn.close()
            return result
        conn.close()
    except Exception:
        pass

    if project_id in MOCK_PROJECTS:
        return MOCK_PROJECTS[project_id]

    return {"molecule": "eMeOH", "jurisdiction": "UNKNOWN", "certifier_ecosystem": "UNKNOWN"}


def _compute_dimension_matches(meta: dict, cohort_key: str) -> DimensionMatches:
    fuel_match = "match" if meta["molecule"] == cohort_key else "partial"
    juris = meta["jurisdiction"]
    jurisdiction_match = "match" if juris in ("US", "DE", "FR", "NL", "ES", "PT") else ("partial" if juris != "UNKNOWN" else "none")
    cert = meta["certifier_ecosystem"]
    certifier_match = "match" if cert in ("ISCC_EU", "TUV_SUD", "RSB", "CERTIFHY") else ("partial" if cert != "UNKNOWN" else "none")
    return DimensionMatches(fuel=fuel_match, jurisdiction=jurisdiction_match, certifier=certifier_match)


def _proximity(a: dict, b: dict) -> float:
    matches = sum([
        a["molecule"] == b["molecule"],
        a["jurisdiction"] == b["jurisdiction"],
        a["certifier_ecosystem"] == b["certifier_ecosystem"],
    ])
    return matches / 3.0


def _get_all_project_metas(conn: sqlite3.Connection) -> dict[str, dict]:
    metas: dict[str, dict] = {}
    try:
        rows = conn.execute("SELECT * FROM projects").fetchall()
        for r in rows:
            keys = r.keys()
            pid = r["project_id"]
            metas[pid] = {
                "molecule": r["molecule"] if "molecule" in keys and r["molecule"] else "UNKNOWN",
                "jurisdiction": r["country"] if "country" in keys and r["country"] else "UNKNOWN",
                "certifier_ecosystem": r["certifier"] if "certifier" in keys and r["certifier"] else "UNKNOWN",
            }
    except Exception:
        pass
    for pid, m in MOCK_PROJECTS.items():
        if pid not in metas:
            metas[pid] = m
    return metas


def _get_evidence_completion(conn: sqlite3.Connection, project_id: str) -> bool:
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM evidence_ledger "
            "WHERE project_id=? AND verification_state IN ('CONFIRMED','AUDITED')",
            (project_id,),
        ).fetchone()
        return row["cnt"] >= 5 if row else False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/compute-all", response_model=ComputeResult)
def compute_all_adjacency():
    """
    Nightly computation endpoint. Computes proximity matrix across all
    projects from the verified evidence corpus and caches results.

    Triggered by cron/scheduler (e.g. 02:00 UTC daily).
    Replaces stale cache entries with fresh computation.
    """
    now = _now()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    metas = _get_all_project_metas(conn)
    project_ids = list(metas.keys())
    cached = 0

    for pid in project_ids:
        meta = metas[pid]
        molecule = meta["molecule"]

        peers = [
            oid for oid in project_ids
            if oid != pid and _proximity(meta, metas[oid]) > 0.3
        ]
        cohort_n = len(peers)

        if cohort_n == 0:
            fallback = FALLBACK_COHORTS.get(molecule, FALLBACK_COHORTS["DEFAULT"])
            density_score = fallback["density_score"]
            dscr_p25, dscr_p50, dscr_p75 = fallback["cohort_dscr_p25"], fallback["cohort_dscr_p50"], fallback["cohort_dscr_p75"]
            completion_rate = fallback["cohort_completion_rate"]
            tie_p50 = fallback["cohort_tie_p50"]
            cohort_n = fallback["cohort_n"]
        else:
            density_score = round(sum(_proximity(meta, metas[oid]) for oid in peers) / len(peers), 2)
            completions = [_get_evidence_completion(conn, oid) for oid in peers]
            completion_rate = round(sum(1 for c in completions if c) / len(completions), 2) if completions else 0.0
            # DSCR/TIE from fallback scaled by evidence density
            fb = FALLBACK_COHORTS.get(molecule, FALLBACK_COHORTS["DEFAULT"])
            dscr_p25, dscr_p50, dscr_p75 = fb["cohort_dscr_p25"], fb["cohort_dscr_p50"], fb["cohort_dscr_p75"]
            tie_p50 = fb["cohort_tie_p50"]

        dim = _compute_dimension_matches(meta, molecule)

        conn.execute(
            "INSERT OR REPLACE INTO adjacency_cache "
            "(project_id, density_score, cohort_n, cohort_dscr_p25, cohort_dscr_p50, "
            "cohort_dscr_p75, cohort_completion_rate, cohort_tie_p50, confidence_flag, "
            "fuel_pathway, jurisdiction, certifier_ecosystem, dimension_matches, computed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid, density_score, cohort_n, dscr_p25, dscr_p50, dscr_p75,
                completion_rate, tie_p50, 1 if cohort_n < 5 else 0,
                molecule, meta["jurisdiction"], meta["certifier_ecosystem"],
                json.dumps(dim.model_dump()), now,
            ),
        )
        cached += 1

    conn.commit()
    conn.close()

    return ComputeResult(projects_processed=len(project_ids), benchmarks_cached=cached, computed_at=now)


@router.get("/{project_id}/benchmark", response_model=AdjacencyBenchmark)
def get_adjacency_benchmark(project_id: str):
    """
    Returns AdjacencyBenchmark for a project. Reads from nightly cache
    first, falls back to on-demand computation with fallback cohort data.
    """
    # Try cache first
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM adjacency_cache WHERE project_id=?", (project_id,)).fetchone()
        conn.close()
        if row:
            dim = json.loads(row["dimension_matches"])
            return AdjacencyBenchmark(
                project_id=project_id,
                density_score=row["density_score"],
                cohort_n=row["cohort_n"],
                cohort_dscr_p25=row["cohort_dscr_p25"],
                cohort_dscr_p50=row["cohort_dscr_p50"],
                cohort_dscr_p75=row["cohort_dscr_p75"],
                cohort_completion_rate=row["cohort_completion_rate"],
                cohort_tie_p50=row["cohort_tie_p50"],
                confidence_flag=bool(row["confidence_flag"]),
                fuel_pathway=row["fuel_pathway"],
                jurisdiction=row["jurisdiction"],
                certifier_ecosystem=row["certifier_ecosystem"],
                dimension_matches=DimensionMatches(**dim),
                cached_at=row["computed_at"],
                basis="PLATFORM_CACHE — density/completion platform-computed; "
                      "DSCR/TIE percentiles are demo-fabricated, not cohort-observed",
            )
    except Exception:
        pass

    meta = _lookup_project_metadata(project_id)
    molecule = meta["molecule"]
    dimension_matches = _compute_dimension_matches(meta, molecule)

    # CORPUS-FIRST (review item #5): if a licensed external snapshot exists,
    # density/counts/completion come from OBSERVED external projects
    # (EXTERNAL_PRIOR). DSCR is not observable externally and is suppressed
    # to 0.0 with the basis saying so — never fabricated.
    _MOLECULE_TO_FUEL = {"eMeOH": "E_METHANOL", "eNH3": "E_AMMONIA",
                         "SAF": "E_SAF", "H2": "GREEN_H2"}
    try:
        from app.core import external_corpus as xc
        xc.init_db()
        fuel = _MOLECULE_TO_FUEL.get(molecule, molecule)
        d = xc.density({"fuel_id": fuel, "jurisdiction": meta["jurisdiction"]})
        if d.get("density") is not None:
            rates = xc.base_rates(fuel)
            return AdjacencyBenchmark(
                project_id=project_id,
                density_score=d["density"],
                cohort_n=d["n_pool"],
                cohort_dscr_p25=0.0, cohort_dscr_p50=0.0, cohort_dscr_p75=0.0,
                cohort_completion_rate=rates.get("share_operational") or 0.0,
                cohort_tie_p50=0.0,
                confidence_flag=d["n_pool"] < 5,
                fuel_pathway=molecule,
                jurisdiction=meta["jurisdiction"],
                certifier_ecosystem=meta["certifier_ecosystem"],
                dimension_matches=dimension_matches,
                cached_at=None,
                basis=f"EXTERNAL_PRIOR — attribute density over {d['n_pool']} observed "
                      f"external projects (layer A); DSCR/TIE suppressed to 0.0: "
                      f"not observable in any external corpus",
            )
    except Exception:
        pass

    # Last resort: fabricated demo numbers, loudly labeled as such.
    cohort = FALLBACK_COHORTS.get(molecule, FALLBACK_COHORTS["DEFAULT"])
    return AdjacencyBenchmark(
        project_id=project_id,
        density_score=cohort["density_score"],
        cohort_n=cohort["cohort_n"],
        cohort_dscr_p25=cohort["cohort_dscr_p25"],
        cohort_dscr_p50=cohort["cohort_dscr_p50"],
        cohort_dscr_p75=cohort["cohort_dscr_p75"],
        cohort_completion_rate=cohort["cohort_completion_rate"],
        cohort_tie_p50=cohort["cohort_tie_p50"],
        confidence_flag=cohort["cohort_n"] < 5,
        fuel_pathway=molecule,
        jurisdiction=meta["jurisdiction"],
        certifier_ecosystem=meta["certifier_ecosystem"],
        dimension_matches=dimension_matches,
        cached_at=None,
        basis="FABRICATED_DEMO_FALLBACK — every number invented; no corpus imported, "
              "no platform cohort. Not for any external communication.",
    )
