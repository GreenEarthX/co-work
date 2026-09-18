"""
adjacency.py — Adjacency Doctrine (§3.5)

Computes proximity matrix, density scores, and cohort benchmarks
for the GEX platform's project comparison engine.

The operative mechanism from Hidalgo's Atlas of Economic Complexity:
proximity(A, B) = min(P(A|B), P(B|A))

Four dimensions define project adjacency:
  - fuel_pathway (e.g. E_METHANOL, SAF, GREEN_H2)
  - jurisdiction (ISO country code)
  - certifier_ecosystem (e.g. DNV, TUV, BUREAU_VERITAS)
  - technology_class (e.g. SOEC, PEM, ALKALINE)

density(j) = Σᵢ proximity(i, j) × xᵢ  (normalized)
where xᵢ = 1 if project i is on the platform.

Exports:
  compute_proximity_matrix(projects) → NxN float matrix
  density_score(project, all_projects) → float 0-1
  cohort_benchmark(project, all_projects, metrics) → CohortBenchmark
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProximityDimension:
    fuel_pathway: str
    jurisdiction: str
    certifier_ecosystem: str
    technology_class: str


@dataclass
class CohortBenchmark:
    density_score: float
    cohort_n: int
    cohort_dscr_p25: float
    cohort_dscr_p50: float
    cohort_dscr_p75: float
    cohort_completion_rate: float
    cohort_tie_p50: float
    confidence_flag: bool


def compute_proximity(a: ProximityDimension, b: ProximityDimension) -> float:
    """
    Simplified proximity: count matching dimensions / total dimensions.
    Full implementation uses conditional probability from historical cohort data.
    """
    matches = sum([
        a.fuel_pathway == b.fuel_pathway,
        a.jurisdiction == b.jurisdiction,
        a.certifier_ecosystem == b.certifier_ecosystem,
        a.technology_class == b.technology_class,
    ])
    return matches / 4.0


def compute_proximity_matrix(projects: list[ProximityDimension]) -> list[list[float]]:
    n = len(projects)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 1.0
            else:
                matrix[i][j] = compute_proximity(projects[i], projects[j])
    return matrix


def density_score(project: ProximityDimension, all_projects: list[ProximityDimension]) -> float:
    if not all_projects:
        return 0.0
    others = [p for p in all_projects if p is not project]
    if not others:
        return 0.0
    total = sum(compute_proximity(p, project) for p in others)
    return total / len(others)


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    k = (len(data) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(data) - 1)
    return data[f] + (k - f) * (data[c] - data[f])


def cohort_benchmark(
    project: ProximityDimension,
    all_projects: list[ProximityDimension],
    project_metrics: Optional[dict[int, dict]] = None,
    proximity_threshold: float = 0.5,
) -> CohortBenchmark:
    """
    project_metrics: dict mapping list index to {dscr: float, completed: bool, tie: float}
    proximity_threshold: minimum proximity to include in cohort (default 0.5)
    """
    peers = [
        i for i, p in enumerate(all_projects)
        if p is not project and compute_proximity(p, project) > proximity_threshold
    ]

    cohort_n = len(peers)
    ds = density_score(project, all_projects)

    if not project_metrics or not peers:
        return CohortBenchmark(
            density_score=ds,
            cohort_n=cohort_n,
            cohort_dscr_p25=0.0,
            cohort_dscr_p50=0.0,
            cohort_dscr_p75=0.0,
            cohort_completion_rate=0.0,
            cohort_tie_p50=0.0,
            confidence_flag=cohort_n < 5,
        )

    dscrs = sorted(
        project_metrics[i]["dscr"]
        for i in peers
        if i in project_metrics and "dscr" in project_metrics[i]
    )
    completions = [
        project_metrics[i].get("completed", False)
        for i in peers if i in project_metrics
    ]
    ties = sorted(
        project_metrics[i]["tie"]
        for i in peers
        if i in project_metrics and "tie" in project_metrics[i]
    )

    return CohortBenchmark(
        density_score=ds,
        cohort_n=cohort_n,
        cohort_dscr_p25=_percentile(dscrs, 25),
        cohort_dscr_p50=_percentile(dscrs, 50),
        cohort_dscr_p75=_percentile(dscrs, 75),
        cohort_completion_rate=(
            sum(1 for c in completions if c) / len(completions) if completions else 0.0
        ),
        cohort_tie_p50=_percentile(ties, 50),
        confidence_flag=cohort_n < 5,
    )


# ═══════════════════════════════════════════════════════════════════════════
# WEIGHTED PROXIMITY — dimension-specific weights
# ═══════════════════════════════════════════════════════════════════════════

# Default weights for the 4 proximity dimensions
# fuel_pathway is most important for project comparability
DIMENSION_WEIGHTS = {
    "fuel_pathway": 0.40,
    "jurisdiction": 0.25,
    "certifier_ecosystem": 0.20,
    "technology_class": 0.15,
}


def compute_weighted_proximity(
    a: ProximityDimension,
    b: ProximityDimension,
    weights: Optional[dict[str, float]] = None,
) -> float:
    """
    Weighted proximity: dimensions contribute differently to similarity.
    Returns 0-1.
    """
    w = weights or DIMENSION_WEIGHTS
    score = 0.0
    total_weight = sum(w.values())
    if a.fuel_pathway == b.fuel_pathway:
        score += w.get("fuel_pathway", 0.25)
    if a.jurisdiction == b.jurisdiction:
        score += w.get("jurisdiction", 0.25)
    if a.certifier_ecosystem == b.certifier_ecosystem:
        score += w.get("certifier_ecosystem", 0.25)
    if a.technology_class == b.technology_class:
        score += w.get("technology_class", 0.25)
    return score / total_weight if total_weight > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# BATCH COMPUTATION — for nightly cache refresh
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BatchBenchmarkResult:
    """Result of computing benchmarks for all projects in a batch."""
    project_id: str
    dimensions: ProximityDimension
    benchmark: CohortBenchmark
    peer_ids: list[str] = field(default_factory=list)


def compute_all_benchmarks(
    projects: dict[str, ProximityDimension],
    project_metrics: Optional[dict[str, dict]] = None,
    proximity_threshold: float = 0.3,
) -> list[BatchBenchmarkResult]:
    """
    Compute benchmarks for all projects in a single pass.
    Designed for nightly batch computation that feeds the
    backend adjacency_cache table.

    Args:
        projects: {project_id: ProximityDimension}
        project_metrics: {project_id: {dscr, completed, tie}}
        proximity_threshold: minimum proximity for cohort inclusion

    Returns:
        List of BatchBenchmarkResult for each project
    """
    ids = list(projects.keys())
    dims = [projects[pid] for pid in ids]

    # Build index-based metrics dict
    idx_metrics: dict[int, dict] = {}
    if project_metrics:
        for i, pid in enumerate(ids):
            if pid in project_metrics:
                idx_metrics[i] = project_metrics[pid]

    results = []
    for i, pid in enumerate(ids):
        proj = dims[i]
        bm = cohort_benchmark(
            project=proj,
            all_projects=dims,
            project_metrics=idx_metrics if idx_metrics else None,
            proximity_threshold=proximity_threshold,
        )
        # Identify peer IDs
        peer_ids = [
            ids[j] for j, p in enumerate(dims)
            if j != i and compute_proximity(p, proj) > proximity_threshold
        ]
        results.append(BatchBenchmarkResult(
            project_id=pid,
            dimensions=proj,
            benchmark=bm,
            peer_ids=peer_ids,
        ))

    return results
