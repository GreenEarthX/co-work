"""
GEX Project Quality Rating Engine
Pure Python, no ORM dependencies. Can be used standalone or via API.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import json

FULL_SCALE = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]

# Score bands are deliberately simple and transparent.
RATING_BANDS: List[Tuple[str, float, float]] = [
    ("AAA", 92.0, 100.0),
    ("AA",  84.0,  91.999),
    ("A",   76.0,  83.999),
    ("BBB", 68.0,  75.999),
    ("BB",  60.0,  67.999),
    ("B",   52.0,  59.999),
    ("CCC", 44.0,  51.999),
    ("CC",  30.0,  43.999),
    ("C",    1.0,  29.999),
    ("D",    0.0,   0.999),
]

PILLAR_WEIGHTS = {
    "business_market":               0.20,
    "construction_technology":       0.20,
    "financial_resilience":          0.30,
    "legal_structural_counterparty": 0.20,
    "sustainability_certification":  0.10,
}

NOTCH_TO_POINTS = 3.0


@dataclass
class GateStatus:
    land_and_permits_ok:  bool
    technology_wrap_ok:   bool
    regulatory_path_ok:   bool
    funding_path_ok:      bool
    revenue_path_ok:      bool
    traceability_ok:      bool


@dataclass
class ProjectInputs:
    project_name:                    str
    phase:                           str
    business_market:                 float
    construction_technology:         float
    financial_resilience:            float
    legal_structural_counterparty:   float
    sustainability_certification:    float
    jurisdiction_notch:              int = 0
    sponsor_support_notch:           int = 0
    structure_notch:                 int = 0
    market_exposure_notch:           int = 0
    data_confidence_notch:           int = 0
    payment_default:                 bool = False
    distressed_exchange:             bool = False
    outlook_bias:                    int = 0   # -1 negative, 0 stable, +1 positive


@dataclass
class QuantitativeInputs:
    downside_min_dscr:              float
    base_case_dscr:                 float
    llcr:                           float
    contracted_revenue_pct:         float
    merchant_exposure_pct:          float
    equity_committed_pct_of_capex:  float
    subsidy_dependence_pct_of_ebitda: float
    schedule_buffer_months:         float
    dsra_months:                    float
    certification_confidence_pct:   float


@dataclass
class RatingResult:
    project_name:          str
    phase:                 str
    base_score:            float
    modifier_points:       float
    preliminary_score:     float
    final_score:           float
    rating:                str
    outlook:               str
    cap_reason:            str
    displayed_scale:       List[str]
    current_rank:          int
    peer_count:            int
    anonymous_peer_scores: List[float]
    quantitative_inputs:   Dict[str, float]
    pillar_scores:         Dict[str, float]
    gate_status:           Dict[str, bool]
    key_strengths:         List[str]
    key_constraints:       List[str]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clamp(x: float, low: float, high: float) -> float:
    return max(low, min(high, x))


def map_score_to_rating(score: float) -> str:
    for label, low, high in RATING_BANDS:
        if low <= score <= high:
            return label
    return "D"


def displayed_scale_for(rating: str, max_items: int = 7) -> List[str]:
    max_items = max(1, min(max_items, len(FULL_SCALE)))
    idx = FULL_SCALE.index(rating)
    half = max_items // 2
    start = max(0, idx - half)
    end = start + max_items
    if end > len(FULL_SCALE):
        end = len(FULL_SCALE)
        start = max(0, end - max_items)
    return FULL_SCALE[start:end]


# ─── Financial resilience scoring ────────────────────────────────────────────

def score_financial_resilience(q: QuantitativeInputs) -> float:
    score = 1.0

    # Downside DSCR — main anchor
    if q.downside_min_dscr >= 1.60:   score += 1.80
    elif q.downside_min_dscr >= 1.40: score += 1.45
    elif q.downside_min_dscr >= 1.25: score += 1.05
    elif q.downside_min_dscr >= 1.10: score += 0.60

    if q.base_case_dscr >= 2.00:   score += 0.70
    elif q.base_case_dscr >= 1.60: score += 0.50
    elif q.base_case_dscr >= 1.35: score += 0.30

    if q.llcr >= 2.20:   score += 0.50
    elif q.llcr >= 1.80: score += 0.35
    elif q.llcr >= 1.50: score += 0.20

    if q.contracted_revenue_pct >= 85: score += 0.40
    elif q.contracted_revenue_pct >= 65: score += 0.25

    if q.dsra_months >= 12: score += 0.35
    elif q.dsra_months >= 6: score += 0.20

    if q.merchant_exposure_pct > 45:   score -= 0.35
    elif q.merchant_exposure_pct > 25: score -= 0.15

    if q.subsidy_dependence_pct_of_ebitda > 50:   score -= 0.35
    elif q.subsidy_dependence_pct_of_ebitda > 25: score -= 0.15

    return round(clamp(score, 1.0, 5.0), 2)


def weighted_base_score(project: ProjectInputs) -> float:
    pillars = {
        "business_market":               clamp(project.business_market, 1.0, 5.0),
        "construction_technology":       clamp(project.construction_technology, 1.0, 5.0),
        "financial_resilience":          clamp(project.financial_resilience, 1.0, 5.0),
        "legal_structural_counterparty": clamp(project.legal_structural_counterparty, 1.0, 5.0),
        "sustainability_certification":  clamp(project.sustainability_certification, 1.0, 5.0),
    }
    return 100.0 * sum((pillars[k] / 5.0) * w for k, w in PILLAR_WEIGHTS.items())


def modifier_points(project: ProjectInputs) -> float:
    total_notches = (
        project.jurisdiction_notch
        + project.sponsor_support_notch
        + project.structure_notch
        + project.market_exposure_notch
        + project.data_confidence_notch
    )
    return total_notches * NOTCH_TO_POINTS


def cap_from_gates(gates: GateStatus, project: ProjectInputs) -> Tuple[float, str]:
    if project.payment_default or project.distressed_exchange:
        return 0.0, "Default / distressed exchange override"

    severe_fail = (
        not gates.land_and_permits_ok
        or not gates.technology_wrap_ok
        or not gates.funding_path_ok
    )
    moderate_fail = (
        not gates.revenue_path_ok
        or not gates.regulatory_path_ok
        or not gates.traceability_ok
    )

    if severe_fail:    return 51.999, "Hard gate failure - capped at CCC"
    if moderate_fail:  return 59.999, "Material gate failure - capped at B"
    return 100.0, "No gate cap"


def derive_outlook(project: ProjectInputs, final_score: float) -> str:
    if project.payment_default or project.distressed_exchange:
        return "Negative"
    if project.outlook_bias > 0 and final_score >= 52:
        return "Positive"
    if project.outlook_bias < 0:
        return "Negative"
    return "Stable"


def build_anonymous_peer_scores(current_score: float) -> List[float]:
    """30 existing platform projects + this project = 31 total."""
    base = [
        93.2, 89.7, 87.8, 85.9, 84.1, 82.6, 80.5, 78.8, 77.6, 76.2,
        74.9, 73.8, 72.7, 71.1, 69.8, 68.7, 66.9, 65.3, 63.4, 61.9,
        60.8, 59.7, 58.2, 56.9, 55.5, 53.6, 51.4, 49.1, 46.8, 42.7,
    ]
    return sorted(base + [round(current_score, 2)], reverse=True)


def rank_within_peers(score: float, peers_desc: List[float]) -> int:
    for i, s in enumerate(peers_desc, start=1):
        if abs(s - score) < 1e-9:
            return i
    return len(peers_desc)


def infer_key_strengths(
    project: ProjectInputs,
    q: QuantitativeInputs,
    gates: GateStatus,
) -> List[str]:
    strengths: List[str] = []
    if q.contracted_revenue_pct >= 70:
        strengths.append("Good contracted revenue visibility")
    if q.downside_min_dscr >= 1.25:
        strengths.append("Acceptable downside debt-service coverage")
    if q.certification_confidence_pct >= 80 and gates.traceability_ok:
        strengths.append("Credible certification and traceability pathway")
    if project.legal_structural_counterparty >= 4.0:
        strengths.append("Above-average contractual and structural protections")
    if project.construction_technology >= 4.0:
        strengths.append("Construction package and technology risk are relatively well controlled")
    return strengths[:4]


def infer_key_constraints(
    project: ProjectInputs,
    q: QuantitativeInputs,
    gates: GateStatus,
) -> List[str]:
    constraints: List[str] = []
    if q.merchant_exposure_pct > 25:
        constraints.append("Material residual merchant exposure remains")
    if q.subsidy_dependence_pct_of_ebitda > 25:
        constraints.append("Economics still depend meaningfully on policy support")
    if q.schedule_buffer_months < 4:
        constraints.append("Limited schedule buffer raises delay sensitivity")
    if project.construction_technology < 4.0:
        constraints.append("Execution complexity remains relevant during ramp-up")
    if not gates.revenue_path_ok:
        constraints.append("Revenue path is not yet fully bankable")
    return constraints[:4]


# ─── Core rating function ─────────────────────────────────────────────────────

def rate_project(
    project: ProjectInputs,
    gates: GateStatus,
    q: QuantitativeInputs,
) -> RatingResult:
    # Financial resilience overrides the passed-in value using quantitative inputs
    project = ProjectInputs(**asdict(project))
    project.financial_resilience = score_financial_resilience(q)

    base = weighted_base_score(project)
    mods = modifier_points(project)
    preliminary = base + mods
    cap, cap_reason = cap_from_gates(gates, project)
    final_score = round(clamp(min(preliminary, cap), 0.0, 100.0), 2)
    rating = map_score_to_rating(final_score)
    outlook = derive_outlook(project, final_score)
    peers = build_anonymous_peer_scores(final_score)
    current_rank = rank_within_peers(final_score, peers)

    pillar_scores = {
        "business_market":               round(project.business_market, 2),
        "construction_technology":       round(project.construction_technology, 2),
        "financial_resilience":          round(project.financial_resilience, 2),
        "legal_structural_counterparty": round(project.legal_structural_counterparty, 2),
        "sustainability_certification":  round(project.sustainability_certification, 2),
    }

    return RatingResult(
        project_name=project.project_name,
        phase=project.phase,
        base_score=round(base, 2),
        modifier_points=round(mods, 2),
        preliminary_score=round(preliminary, 2),
        final_score=final_score,
        rating=rating,
        outlook=outlook,
        cap_reason=cap_reason,
        displayed_scale=displayed_scale_for(rating, max_items=7),
        current_rank=current_rank,
        peer_count=len(peers),
        anonymous_peer_scores=peers,
        quantitative_inputs=asdict(q),
        pillar_scores=pillar_scores,
        gate_status=asdict(gates),
        key_strengths=infer_key_strengths(project, q, gates),
        key_constraints=infer_key_constraints(project, q, gates),
    )


# ─── Public wrapper (used by API layer) ───────────────────────────────────────

def calculate_project_rating(
    project: ProjectInputs,
    gates: GateStatus,
    quantitative: QuantitativeInputs,
    methodology_name: str = "GEX Project Quality Rating",
    methodology_version: str = "v1.0",
    reviewer_type: str = "internal",
    review_state: str = "draft_screening",
    peer_scores_desc: Optional[List[float]] = None,
) -> dict:
    """
    Public API entry point. Calls rate_project and returns a plain dict
    enriched with methodology metadata (for the API response / DB row).
    `peer_scores_desc` is accepted for future use when external peer pools
    are provided; currently the engine builds its own anonymous peer set.
    """
    result = rate_project(project, gates, quantitative)
    d = asdict(result)
    d["methodology_label"] = (
        f"{methodology_name} - {methodology_version} / {reviewer_type} / {review_state}"
    )
    d["methodology_name"] = methodology_name
    d["methodology_version"] = methodology_version
    d["reviewer_type"] = reviewer_type
    d["review_state"] = review_state
    return d


# ─── CLI smoke test ───────────────────────────────────────────────────────────

def _example_inputs() -> Tuple[ProjectInputs, GateStatus, QuantitativeInputs]:
    project = ProjectInputs(
        project_name="Project Helios e-Methanol",
        phase="Pre-COD / late construction",
        business_market=3.9,
        construction_technology=3.8,
        financial_resilience=3.0,
        legal_structural_counterparty=4.1,
        sustainability_certification=4.3,
        sponsor_support_notch=1,
        structure_notch=1,
        market_exposure_notch=-1,
    )
    gates = GateStatus(
        land_and_permits_ok=True, technology_wrap_ok=True,
        regulatory_path_ok=True, funding_path_ok=True,
        revenue_path_ok=True, traceability_ok=True,
    )
    q = QuantitativeInputs(
        downside_min_dscr=1.27, base_case_dscr=1.61, llcr=1.78,
        contracted_revenue_pct=72.0, merchant_exposure_pct=28.0,
        equity_committed_pct_of_capex=34.0, subsidy_dependence_pct_of_ebitda=24.0,
        schedule_buffer_months=3.0, dsra_months=6.0,
        certification_confidence_pct=86.0,
    )
    return project, gates, q


if __name__ == "__main__":
    project, gates, q = _example_inputs()
    result = calculate_project_rating(project, gates, q)
    print(json.dumps(result, indent=2))
