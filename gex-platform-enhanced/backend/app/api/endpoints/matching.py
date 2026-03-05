from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import random

router = APIRouter()

# In-memory storage
matches_db = []

class MatchRequest(BaseModel):
    rfq_id: Optional[str] = None
    molecule: str
    volume_mtpd: float
    price_max: Optional[float] = None
    criteria: Dict[str, Any]

class MatchResult(BaseModel):
    id: str
    offer_id: str
    counterparty: str
    molecule: str
    score: float
    volume_mtpd: float
    price: float
    distance_km: int
    breakdown: Dict[str, float]

@router.post("/run")
async def run_matching(request: MatchRequest):
    """Run matching algorithm based on criteria"""
    
    # Mock matching results (in real app, this would query offers_db and score them)
    mock_matches = [
        {
            "id": str(uuid4()),
            "offer_id": str(uuid4()),
            "counterparty": "*** Industrial GmbH",
            "molecule": request.molecule,
            "score": round(85 + random.random() * 10, 2),
            "volume_mtpd": request.volume_mtpd * random.uniform(0.7, 1.2),
            "price": (request.price_max or 7.0) * random.uniform(0.85, 0.98),
            "distance_km": random.randint(150, 800),
            "breakdown": {
                "price_fit": round(random.uniform(80, 95), 1),
                "volume_fit": round(random.uniform(85, 98), 1),
                "window_fit": round(random.uniform(90, 100), 1),
                "distance_fit": round(random.uniform(75, 90), 1),
                "compliance_fit": round(random.uniform(85, 95), 1),
                "spec_fit": round(random.uniform(80, 95), 1)
            },
            "matched_at": datetime.now().isoformat()
        }
        for i in range(5)  # Return 5 mock matches
    ]
    
    # Sort by score descending
    mock_matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Store matches
    for match in mock_matches:
        matches_db.append(match)
    
    return {
        "matches": mock_matches,
        "total": len(mock_matches),
        "criteria": request.criteria
    }

@router.get("/")
async def list_matches(molecule: Optional[str] = None, min_score: Optional[float] = None):
    """List all matches with optional filtering"""
    filtered_matches = matches_db
    
    if molecule:
        filtered_matches = [m for m in filtered_matches if m["molecule"] == molecule]
    if min_score:
        filtered_matches = [m for m in filtered_matches if m["score"] >= min_score]
    
    # Sort by score descending
    filtered_matches.sort(key=lambda x: x["score"], reverse=True)
    
    return {
        "matches": filtered_matches,
        "total": len(filtered_matches)
    }

@router.get("/{match_id}")
async def get_match(match_id: str):
    """Get a specific match with detailed breakdown"""
    for match in matches_db:
        if match["id"] == match_id:
            return match
    raise HTTPException(status_code=404, detail="Match not found")

@router.post("/{match_id}/accept")
async def accept_match(match_id: str):
    """Accept a match and move to due diligence"""
    for match in matches_db:
        if match["id"] == match_id:
            match["status"] = "accepted"
            match["accepted_at"] = datetime.now().isoformat()
            return {
                "message": "Match accepted",
                "match": match,
                "next_step": "due_diligence"
            }
    raise HTTPException(status_code=404, detail="Match not found")