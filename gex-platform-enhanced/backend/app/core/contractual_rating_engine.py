"""
GEX Contractual Credit Anchoring Engine
File: app/core/contractual_rating_engine.py

Pre-FID rating model. Replaces DSCR-based evaluation for development-stage projects.

Core principle: a project is NOT evaluated based on projected financial ratios.
A project is evaluated as a derivative of its offtake agreements and counterparties.
Bankability = f(contractual certainty of future revenues)

Phase-gated: used ONLY for states SPECULATIVE through CREDIT_APPROVED.
Post-FID (FINANCEABLE, OPERATIONAL) continues to use gex_project_rating_engine.py.

Pillar weights from 2026 Seed-to-FID Standard:
  Offtake Anchor:  40% (20% counterparty quality + 20% tenor & floor)
  Bankability:     20% (10% FID pathway + 10% subsidy certainty)
  Product Value:   25% (15% carbon intensity + 10% traceability/LCA)
  Execution:       15% (15% TRL & track record)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import logging

logger = logging.getLogger("gex.contractual_rating")


# ═══════════════════════════════════════════════════════════════
# INPUT MODELS
# ═══════════════════════════════════════════════════════════════

# Credit rating ordinal scale (S&P/Moody's equivalent)
CREDIT_ORDINAL: dict[str, int] = {
    "AAA": 22, "AA+": 21, "AA": 20, "AA-": 19,
    "A+": 18, "A": 17, "A-": 16,
    "BBB+": 15, "BBB": 14, "BBB-": 13,
    "BB+": 12, "BB": 11, "BB-": 10,
    "B+": 9, "B": 8, "B-": 7,
    "CCC+": 6, "CCC": 5, "CCC-": 4,
    "CC": 3, "C": 2, "D": 1, "NR": 0,
}


@dataclass
class OfftakeContract:
    """Single offtake agreement."""
    counterparty_name: str
    counterparty_rating: str          # S&P scale: "AA", "BBB+", etc.
    contracted_volume_tpa: float      # Tonnes per annum
    tenor_years: int
    price_floor_eur_t: float          # Minimum guaranteed price
    take_or_pay: bool = False
    cfd_protected: bool = False       # Contract-for-Difference protection
    corporate_floor: bool = False     # Corporate guarantee on floor


@dataclass
class ContractualRatingInput:
    """All inputs needed for pre-FID rating."""
    # Offtake Anchor (40%)
    offtake_contracts: list[OfftakeContract] = field(default_factory=list)
    nameplate_capacity_tpa: float = 0.0
    lcof_eur_t: float = 0.0           # Levelised Cost of Fuel

    # Bankability (20%)
    equity_cleared: bool = False
    grid_secured: bool = False
    epc_price_locked: bool = False
    subsidy_45v_eligible: bool = False
    subsidy_eu_h2_bank: bool = False
    subsidy_other: str = ""            # Free text for other subsidies

    # Product Value (25%)
    carbon_intensity_kgco2_per_kg: float = 0.0  # Lower is better
    tokenized_lca: bool = False        # Digital birth certificate exists
    tokenized_volume_pct: float = 0.0  # % of output tokenized

    # Execution (15%)
    trl: int = 1                       # Technology Readiness Level (1-9)
    land_permitted: bool = False
    developer_track_record_projects: int = 0  # Number of prior projects
    developer_track_record_mw: float = 0.0    # Prior MW deployed


# ═══════════════════════════════════════════════════════════════
# OUTPUT MODELS
# ═══════════════════════════════════════════════════════════════

@dataclass
class PillarScore:
    """Score for a single rating pillar."""
    pillar: str
    weight: float
    raw_score: float       # 0-100
    weighted_score: float  # raw * weight
    factors: dict[str, float] = field(default_factory=dict)
    commentary: str = ""


@dataclass
class ContractualRating:
    """Complete pre-FID rating output."""
    final_score: float                 # 0-100
    letter_rating: str                 # AAA through D
    outlook: str                       # POSITIVE, STABLE, NEGATIVE
    pillars: list[PillarScore] = field(default_factory=list)

    # Key metrics surfaced for UI
    ocr: float = 0.0                   # Offtake Coverage Ratio
    green_spread_eur_t: float = 0.0    # Offtake floor - LCOF
    cwar: str = "NR"                   # Counterparty Weighted Average Rating
    cwar_ordinal: float = 0.0
    tokenized_volume_pct: float = 0.0

    # Gate compatibility
    investment_grade: bool = False     # score >= 68 (BBB equivalent)
    committee_ready: bool = False      # score >= 76 (A equivalent)

    narrative: str = ""


# ═══════════════════════════════════════════════════════════════
# RATING ENGINE
# ═══════════════════════════════════════════════════════════════

class ContractualRatingEngine:
    """
    Pre-FID rating engine based on contractual credit anchoring.

    Core logic: a project is a derivative of its offtake agreements.
    The counterparty credit quality is the primary anchor.
    """

    # Letter rating scale (aligned with gex_project_rating_engine.py)
    RATING_SCALE = [
        (92.0, "AAA"), (84.0, "AA"), (76.0, "A"),
        (68.0, "BBB"), (60.0, "BB"), (52.0, "B"),
        (44.0, "CCC"), (30.0, "CC"), (1.0, "C"), (0.0, "D"),
    ]

    def rate(self, inp: ContractualRatingInput) -> ContractualRating:
        """Compute full pre-FID rating from contractual inputs."""

        p1 = self._pillar_offtake_anchor(inp)
        p2 = self._pillar_bankability(inp)
        p3 = self._pillar_product_value(inp)
        p4 = self._pillar_execution(inp)

        pillars = [p1, p2, p3, p4]
        final_score = sum(p.weighted_score for p in pillars)

        # Hard caps (same pattern as gex_project_rating_engine)
        if inp.nameplate_capacity_tpa > 0 and self._compute_ocr(inp) < 0.10:
            final_score = min(final_score, 29.9)  # Cap at C if near-zero offtake
        if inp.trl < 4:
            final_score = min(final_score, 51.9)  # Cap at B if unproven tech

        letter = self._score_to_letter(final_score)
        ocr = self._compute_ocr(inp)
        green_spread = self._compute_green_spread(inp)
        cwar, cwar_ord = self._compute_cwar(inp)

        # Outlook
        outlook = "STABLE"
        if final_score >= 68 and green_spread > 0 and ocr >= 0.8:
            outlook = "POSITIVE"
        elif final_score < 52 or ocr < 0.3:
            outlook = "NEGATIVE"

        narrative = self._build_narrative(inp, final_score, letter, ocr, green_spread, cwar)

        return ContractualRating(
            final_score=round(final_score, 1),
            letter_rating=letter,
            outlook=outlook,
            pillars=pillars,
            ocr=round(ocr, 3),
            green_spread_eur_t=round(green_spread, 1),
            cwar=cwar,
            cwar_ordinal=round(cwar_ord, 1),
            tokenized_volume_pct=round(inp.tokenized_volume_pct, 1),
            investment_grade=final_score >= 68,
            committee_ready=final_score >= 76,
            narrative=narrative,
        )

    # ── Pillar 1: Offtake Anchor (40%) ──────────────────────────

    def _pillar_offtake_anchor(self, inp: ContractualRatingInput) -> PillarScore:
        """
        40% weight. Two sub-factors:
          - 20% Counterparty Quality (CWAR)
          - 20% Tenor & Price Floor (Green Spread + contract structure)
        """
        # Factor 1: Counterparty Quality (20%)
        cwar, cwar_ord = self._compute_cwar(inp)
        # Map ordinal 0-22 to 0-100 score
        cq_score = min(cwar_ord / 22.0 * 100, 100)
        # Bonus for take-or-pay contracts
        top_count = sum(1 for c in inp.offtake_contracts if c.take_or_pay)
        if top_count > 0:
            cq_score = min(cq_score + 10, 100)

        # Factor 2: Tenor & Floor (20%)
        green_spread = self._compute_green_spread(inp)
        ocr = self._compute_ocr(inp)

        # Tenor score: longest offtake tenor, target 10+ years
        max_tenor = max((c.tenor_years for c in inp.offtake_contracts), default=0)
        tenor_score = min(max_tenor / 10.0 * 60, 60)  # max 60 from tenor

        # Floor score: green spread > 0 means floor > LCOF
        if green_spread > 0:
            floor_score = min(30 + green_spread / 10, 40)  # up to 40
        else:
            floor_score = max(0, 15 + green_spread / 5)  # penalty for negative

        # CfD/corporate floor protection bonus
        has_protection = any(c.cfd_protected or c.corporate_floor for c in inp.offtake_contracts)
        protection_bonus = 10 if has_protection else 0

        tf_score = min(tenor_score + floor_score + protection_bonus, 100)

        # OCR multiplier: scale both sub-factors by coverage
        ocr_mult = min(ocr / 0.8, 1.0)  # 80% OCR = full credit
        cq_adjusted = cq_score * ocr_mult
        tf_adjusted = tf_score * ocr_mult

        raw = (cq_adjusted + tf_adjusted) / 2
        weighted = raw * 0.40

        return PillarScore(
            pillar="Offtake Anchor",
            weight=0.40,
            raw_score=round(raw, 1),
            weighted_score=round(weighted, 1),
            factors={
                "counterparty_quality": round(cq_adjusted, 1),
                "tenor_and_floor": round(tf_adjusted, 1),
                "ocr": round(ocr, 3),
                "cwar": cwar_ord,
                "green_spread_eur_t": round(green_spread, 1),
                "max_tenor_years": max_tenor,
                "take_or_pay_count": top_count,
                "cfd_or_floor_protected": has_protection,
            },
            commentary=f"CWAR: {cwar}, OCR: {ocr:.0%}, Green Spread: \u20ac{green_spread:.0f}/t",
        )

    # ── Pillar 2: Bankability (20%) ─────────────────────────────

    def _pillar_bankability(self, inp: ContractualRatingInput) -> PillarScore:
        """
        20% weight. Two sub-factors:
          - 10% FID Pathway clarity (equity, grid, EPC)
          - 10% Subsidy certainty (45V, EU H2 Bank, other)
        """
        # FID Pathway (10%)
        fid_items = [inp.equity_cleared, inp.grid_secured, inp.epc_price_locked]
        fid_score = sum(1 for x in fid_items if x) / len(fid_items) * 100

        # Subsidy Certainty (10%)
        subsidy_count = sum([
            inp.subsidy_45v_eligible,
            inp.subsidy_eu_h2_bank,
            bool(inp.subsidy_other),
        ])
        subsidy_score = min(subsidy_count / 2.0 * 100, 100)  # 2+ subsidies = 100

        raw = (fid_score + subsidy_score) / 2
        weighted = raw * 0.20

        return PillarScore(
            pillar="Bankability",
            weight=0.20,
            raw_score=round(raw, 1),
            weighted_score=round(weighted, 1),
            factors={
                "fid_pathway": round(fid_score, 1),
                "subsidy_certainty": round(subsidy_score, 1),
                "equity_cleared": inp.equity_cleared,
                "grid_secured": inp.grid_secured,
                "epc_price_locked": inp.epc_price_locked,
                "subsidy_45v": inp.subsidy_45v_eligible,
                "subsidy_eu_h2_bank": inp.subsidy_eu_h2_bank,
            },
            commentary=f"FID pathway: {sum(fid_items)}/3 cleared, Subsidies: {subsidy_count} confirmed",
        )

    # ── Pillar 3: Product Value (25%) ───────────────────────────

    def _pillar_product_value(self, inp: ContractualRatingInput) -> PillarScore:
        """
        25% weight. Two sub-factors:
          - 15% Carbon Intensity (lower CI = higher green premium)
          - 10% Traceability (tokenized LCA = digital birth certificate)
        """
        # Carbon Intensity (15%)
        # Scale: 0 kgCO2/kg = 100, 4 kgCO2/kg = 0 (EU RED III threshold ~3.38)
        ci = inp.carbon_intensity_kgco2_per_kg
        if ci <= 0:
            ci_score = 100.0  # Perfect: zero emissions
        elif ci >= 4.0:
            ci_score = 0.0    # Fails RED III threshold
        else:
            ci_score = max(0, (4.0 - ci) / 4.0 * 100)

        # Traceability (10%)
        trace_score = 0.0
        if inp.tokenized_lca:
            trace_score = 60.0  # Base for having tokenized LCA
        if inp.tokenized_volume_pct > 0:
            trace_score += min(inp.tokenized_volume_pct / 100 * 40, 40)

        raw = (ci_score * 0.6 + trace_score * 0.4)  # Weighted within pillar
        weighted = raw * 0.25

        return PillarScore(
            pillar="Product Value",
            weight=0.25,
            raw_score=round(raw, 1),
            weighted_score=round(weighted, 1),
            factors={
                "carbon_intensity_score": round(ci_score, 1),
                "carbon_intensity_kgco2": ci,
                "traceability_score": round(trace_score, 1),
                "tokenized_lca": inp.tokenized_lca,
                "tokenized_volume_pct": inp.tokenized_volume_pct,
            },
            commentary=f"CI: {ci:.2f} kgCO2/kg \u2192 score {ci_score:.0f}/100, Tokenized: {inp.tokenized_volume_pct:.0f}%",
        )

    # ── Pillar 4: Execution (15%) ───────────────────────────────

    def _pillar_execution(self, inp: ContractualRatingInput) -> PillarScore:
        """
        15% weight. Single factor:
          - TRL & track record (technology proven, land permitted)
        """
        # TRL score: 1-3 = early, 4-6 = demo, 7-9 = commercial
        trl_score = min(inp.trl / 9.0 * 60, 60)

        # Land permitted
        land_score = 15 if inp.land_permitted else 0

        # Developer track record
        tr_projects = min(inp.developer_track_record_projects / 3.0 * 15, 15)
        tr_mw = min(inp.developer_track_record_mw / 100.0 * 10, 10)

        raw = min(trl_score + land_score + tr_projects + tr_mw, 100)
        weighted = raw * 0.15

        return PillarScore(
            pillar="Execution",
            weight=0.15,
            raw_score=round(raw, 1),
            weighted_score=round(weighted, 1),
            factors={
                "trl": inp.trl,
                "trl_score": round(trl_score, 1),
                "land_permitted": inp.land_permitted,
                "track_record_projects": inp.developer_track_record_projects,
                "track_record_mw": inp.developer_track_record_mw,
            },
            commentary=f"TRL {inp.trl}/9, Land: {'Yes' if inp.land_permitted else 'No'}, Prior: {inp.developer_track_record_projects} projects",
        )

    # ── Utility methods ─────────────────────────────────────────

    def _compute_ocr(self, inp: ContractualRatingInput) -> float:
        """Offtake Coverage Ratio = contracted_volume / nameplate_capacity"""
        if inp.nameplate_capacity_tpa <= 0:
            return 0.0
        total_contracted = sum(c.contracted_volume_tpa for c in inp.offtake_contracts)
        return min(total_contracted / inp.nameplate_capacity_tpa, 1.0)

    def _compute_green_spread(self, inp: ContractualRatingInput) -> float:
        """Green Spread = weighted average floor price - LCOF"""
        if not inp.offtake_contracts:
            return 0.0
        total_vol = sum(c.contracted_volume_tpa for c in inp.offtake_contracts)
        if total_vol == 0:
            return 0.0
        weighted_floor = sum(c.price_floor_eur_t * c.contracted_volume_tpa for c in inp.offtake_contracts) / total_vol
        return weighted_floor - inp.lcof_eur_t

    def _compute_cwar(self, inp: ContractualRatingInput) -> tuple[str, float]:
        """Counterparty Weighted Average Rating -- volume-weighted."""
        if not inp.offtake_contracts:
            return "NR", 0.0
        total_vol = sum(c.contracted_volume_tpa for c in inp.offtake_contracts)
        if total_vol == 0:
            return "NR", 0.0
        weighted_ord = sum(
            CREDIT_ORDINAL.get(c.counterparty_rating, 0) * c.contracted_volume_tpa
            for c in inp.offtake_contracts
        ) / total_vol
        # Map back to nearest letter
        best_match = "NR"
        best_diff = 999
        for letter, ordinal in CREDIT_ORDINAL.items():
            diff = abs(ordinal - weighted_ord)
            if diff < best_diff:
                best_diff = diff
                best_match = letter
        return best_match, weighted_ord

    def _score_to_letter(self, score: float) -> str:
        for threshold, letter in self.RATING_SCALE:
            if score >= threshold:
                return letter
        return "D"

    def _build_narrative(self, inp: ContractualRatingInput, score: float, letter: str,
                         ocr: float, green_spread: float, cwar: str) -> str:
        """Human-readable investment readiness narrative."""
        parts = [f"This project rates {letter} ({score:.0f}/100) under contractual credit anchoring."]

        if ocr >= 0.8:
            parts.append(f"Strong offtake coverage at {ocr:.0%} of nameplate capacity.")
        elif ocr >= 0.5:
            parts.append(f"Moderate offtake coverage at {ocr:.0%} — additional contracts would strengthen the rating.")
        else:
            parts.append(f"Weak offtake coverage at {ocr:.0%} — insufficient for investment-grade consideration.")

        if green_spread > 0:
            parts.append(f"Positive green spread of \u20ac{green_spread:.0f}/t above LCOF provides downside protection.")
        elif green_spread == 0:
            parts.append("Green spread is zero — offtake floor equals LCOF with no margin.")
        else:
            parts.append(f"Negative green spread of \u20ac{green_spread:.0f}/t — offtake floor below cost of production.")

        cwar_ord = CREDIT_ORDINAL.get(cwar, 0)
        if cwar_ord >= 17:  # A or better
            parts.append(f"Counterparty credit anchor is strong ({cwar}).")
        elif cwar_ord >= 13:  # BBB or better
            parts.append(f"Counterparty credit anchor is adequate ({cwar}) — investment-grade threshold.")
        else:
            parts.append(f"Counterparty credit anchor is weak ({cwar}) — below investment-grade.")

        return " ".join(parts)


# ── Singleton ──
_engine: ContractualRatingEngine | None = None

def get_contractual_rating_engine() -> ContractualRatingEngine:
    global _engine
    if _engine is None:
        _engine = ContractualRatingEngine()
    return _engine
