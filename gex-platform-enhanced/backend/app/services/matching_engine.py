"""
Matching Engine Service - Core Algorithm

This service implements the molecule-specific matching algorithm
that scores offers against buyer RFQs.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from app.db.models import Offer, RFQ, Match
from app.schemas import MatchBreakdown


# Molecule-specific configuration
MOLECULE_CONFIG = {
    "H2": {
        "unit": "kg",
        "price_unit": "EUR/kg",
        "volume_unit": "t/day (MTPD)",
        "weights": {
            "price_fit": 20,
            "volume_fit": 15,
            "window_fit": 15,
            "distance_fit": 10,
            "compliance_fit": 15,
            "counterparty_fit": 10,
            "spec_fit": 15,
        },
    },
    "NH3": {
        "unit": "t",
        "price_unit": "USD/t",
        "volume_unit": "t/day",
        "weights": {
            "price_fit": 18,
            "volume_fit": 12,
            "window_fit": 12,
            "distance_fit": 8,
            "compliance_fit": 18,
            "counterparty_fit": 10,
            "spec_fit": 22,
        },
    },
    "SAF": {
        "unit": "t",
        "price_unit": "USD/t",
        "volume_unit": "t/day",
        "weights": {
            "price_fit": 20,
            "volume_fit": 10,
            "window_fit": 10,
            "distance_fit": 5,
            "compliance_fit": 20,
            "counterparty_fit": 10,
            "spec_fit": 25,
        },
    },
    "eMeOH": {
        "unit": "t",
        "price_unit": "USD/t",
        "volume_unit": "t/day",
        "weights": {
            "price_fit": 18,
            "volume_fit": 12,
            "window_fit": 12,
            "distance_fit": 8,
            "compliance_fit": 18,
            "counterparty_fit": 10,
            "spec_fit": 22,
        },
    },
}


class MatchingEngine:
    """Intelligent matching engine for green fuels"""
    
    def __init__(self):
        self.tolerance = 0.2  # 20% tolerance for numeric ranges
    
    def score_offer(self, rfq: RFQ, offer: Offer) -> Dict:
        """
        Score an offer against an RFQ
        
        Returns dict with:
        - total: Overall score (0-100)
        - breakdown: Component scores
        """
        if rfq.molecule != offer.token.capacity.molecule:
            return {"total": 0, "breakdown": {}}
        
        molecule = rfq.molecule
        weights = MOLECULE_CONFIG[molecule]["weights"]
        
        # Calculate individual components
        price_score = self._score_price(rfq, offer)
        volume_score = self._score_volume(rfq, offer)
        window_score = self._score_delivery_window(rfq, offer)
        distance_score = self._score_distance(rfq, offer)
        compliance_score = self._score_compliance(rfq, offer)
        counterparty_score = self._score_counterparty(offer)
        spec_score = self._score_specifications(rfq, offer, molecule)
        
        # Calculate weighted total
        total = (
            price_score * weights["price_fit"] +
            volume_score * weights["volume_fit"] +
            window_score * weights["window_fit"] +
            distance_score * weights["distance_fit"] +
            compliance_score * weights["compliance_fit"] +
            counterparty_score * weights["counterparty_fit"] +
            spec_score * weights["spec_fit"]
        ) / 100  # Normalize because weights sum to 100
        
        breakdown = MatchBreakdown(
            price_fit=round(price_score, 2),
            volume_fit=round(volume_score, 2),
            window_fit=round(window_score, 2),
            distance_fit=round(distance_score, 2),
            compliance_fit=round(compliance_score, 2),
            counterparty_fit=round(counterparty_score, 2),
            spec_fit=round(spec_score, 2),
        )
        
        return {
            "total": round(total, 2),
            "breakdown": breakdown.dict(),
        }
    
    def _score_price(self, rfq: RFQ, offer: Offer) -> float:
        """Score price fit (0-100)"""
        if not rfq.price_max or not offer.price_min:
            return 100.0  # Neutral if no price constraints
        
        # Use midpoint of offer range
        offer_price = (offer.price_min + (offer.price_max or offer.price_min)) / 2
        
        if offer_price <= rfq.price_max:
            return 100.0
        
        # Linear decay beyond max price
        tolerance = rfq.price_max * self.tolerance
        if offer_price > rfq.price_max + tolerance:
            return 0.0
        
        # Linear interpolation
        excess = offer_price - rfq.price_max
        return 100.0 * (1 - excess / tolerance)
    
    def _score_volume(self, rfq: RFQ, offer: Offer) -> float:
        """Score volume fit (0-100)"""
        requested = rfq.volume_mtpd
        available = offer.volume_mtpd
        
        if available >= requested:
            return 100.0
        
        # Partial fulfillment score
        ratio = available / requested
        
        # Full score above 80% fulfillment
        if ratio >= 0.8:
            return 100.0
        
        # Linear decay below 80%
        return ratio * 125  # Scale so 80% = 100
    
    def _score_delivery_window(self, rfq: RFQ, offer: Offer) -> float:
        """Score delivery window overlap (0-100)"""
        rfq_start = rfq.delivery_start
        rfq_end = rfq.delivery_end
        offer_start = offer.token.delivery_start
        offer_end = offer.token.delivery_end
        
        # Calculate overlap
        overlap_start = max(rfq_start, offer_start)
        overlap_end = min(rfq_end, offer_end)
        
        if overlap_start > overlap_end:
            return 0.0  # No overlap
        
        overlap_days = (overlap_end - overlap_start).days
        requested_days = (rfq_end - rfq_start).days
        
        if requested_days == 0:
            return 100.0
        
        ratio = overlap_days / requested_days
        return min(100.0, ratio * 100)
    
    def _score_distance(self, rfq: RFQ, offer: Offer) -> float:
        """Score distance fit (0-100)"""
        # TODO: Implement geospatial distance calculation using PostGIS
        # For now, return neutral score
        max_distance = rfq.criteria.get("max_distance_km", None)
        if not max_distance:
            return 100.0
        
        # Placeholder: assume 1000km distance
        actual_distance = 1000
        
        if actual_distance <= max_distance:
            return 100.0
        
        # Linear decay to 0 at 2x max distance
        if actual_distance >= max_distance * 2:
            return 0.0
        
        excess = actual_distance - max_distance
        return 100.0 * (1 - excess / max_distance)
    
    def _score_compliance(self, rfq: RFQ, offer: Offer) -> float:
        """Score compliance fit (0-100)"""
        min_rfnbo = rfq.criteria.get("min_compliance", {}).get("RFNBO", 0)
        min_45v = rfq.criteria.get("min_compliance", {}).get("45V", 0)
        min_red = rfq.criteria.get("min_compliance", {}).get("REDIII", 0)
        
        token = offer.token
        actual_rfnbo = token.compliance_rfnbo or 0
        actual_45v = token.compliance_45v or 0
        actual_red = token.compliance_red or 0
        
        # Average of three compliance scores
        scores = []
        
        if min_rfnbo > 0:
            scores.append(min(100, actual_rfnbo / min_rfnbo * 100))
        
        if min_45v > 0:
            scores.append(min(100, actual_45v / min_45v * 100))
        
        if min_red > 0:
            scores.append(min(100, actual_red / min_red * 100))
        
        if not scores:
            return 100.0  # No compliance requirements
        
        return sum(scores) / len(scores)
    
    def _score_counterparty(self, offer: Offer) -> float:
        """Score counterparty quality (0-100)"""
        # TODO: Implement actual counterparty rating system
        # For now, return placeholder
        return 80.0
    
    def _score_specifications(self, rfq: RFQ, offer: Offer, molecule: str) -> float:
        """Score technical specifications match (0-100)"""
        rfq_specs = rfq.criteria.get("specifications", {})
        offer_specs = offer.specifications or {}
        
        if not rfq_specs:
            return 100.0  # No spec requirements
        
        # Molecule-specific spec scoring
        if molecule == "H2":
            return self._score_h2_specs(rfq_specs, offer_specs)
        elif molecule == "NH3":
            return self._score_nh3_specs(rfq_specs, offer_specs)
        elif molecule == "SAF":
            return self._score_saf_specs(rfq_specs, offer_specs)
        elif molecule == "eMeOH":
            return self._score_emeoh_specs(rfq_specs, offer_specs)
        
        return 100.0
    
    def _score_h2_specs(self, rfq_specs: Dict, offer_specs: Dict) -> float:
        """H2-specific specification scoring"""
        scores = []
        
        # Purity
        if "purity_pct" in rfq_specs:
            min_purity = rfq_specs["purity_pct"]
            actual = offer_specs.get("purity_pct", 0)
            if actual >= min_purity:
                scores.append(100.0)
            else:
                scores.append(max(0, actual / min_purity * 100))
        
        # Form (gas, liquid, LOHC)
        if "form" in rfq_specs:
            req_form = rfq_specs["form"]
            actual_form = offer_specs.get("form")
            if req_form == "Any" or req_form == actual_form:
                scores.append(100.0)
            else:
                scores.append(0.0)
        
        return sum(scores) / len(scores) if scores else 100.0
    
    def _score_nh3_specs(self, rfq_specs: Dict, offer_specs: Dict) -> float:
        """NH3-specific specification scoring"""
        scores = []
        
        # Grade
        if "grade" in rfq_specs:
            req_grade = rfq_specs["grade"]
            actual_grade = offer_specs.get("grade")
            if req_grade == "Any" or req_grade == actual_grade:
                scores.append(100.0)
            else:
                scores.append(0.0)
        
        # Purity
        if "purity_pct" in rfq_specs:
            min_purity = rfq_specs["purity_pct"]
            actual = offer_specs.get("purity_pct", 0)
            scores.append(min(100.0, actual / min_purity * 100))
        
        return sum(scores) / len(scores) if scores else 100.0
    
    def _score_saf_specs(self, rfq_specs: Dict, offer_specs: Dict) -> float:
        """SAF-specific specification scoring"""
        scores = []
        
        # ASTM pathway
        if "astm_pathway" in rfq_specs:
            req_pathway = rfq_specs["astm_pathway"]
            actual_pathway = offer_specs.get("astm_pathway")
            if req_pathway == "Any" or req_pathway == actual_pathway:
                scores.append(100.0)
            else:
                scores.append(0.0)
        
        # Blend percentage
        if "blend_pct" in rfq_specs:
            req_blend = rfq_specs["blend_pct"]
            actual_blend = offer_specs.get("blend_pct", 0)
            if actual_blend >= req_blend:
                scores.append(100.0)
            else:
                scores.append(max(0, actual_blend / req_blend * 100))
        
        return sum(scores) / len(scores) if scores else 100.0
    
    def _score_emeoh_specs(self, rfq_specs: Dict, offer_specs: Dict) -> float:
        """eMeOH-specific specification scoring"""
        scores = []
        
        # Purity
        if "purity_pct" in rfq_specs:
            min_purity = rfq_specs["purity_pct"]
            actual = offer_specs.get("purity_pct", 0)
            scores.append(min(100.0, actual / min_purity * 100))
        
        # Grade
        if "grade" in rfq_specs:
            req_grade = rfq_specs["grade"]
            actual_grade = offer_specs.get("grade")
            if req_grade == "Any" or req_grade == actual_grade:
                scores.append(100.0)
            else:
                scores.append(0.0)
        
        return sum(scores) / len(scores) if scores else 100.0


# Singleton instance
matching_engine = MatchingEngine()
