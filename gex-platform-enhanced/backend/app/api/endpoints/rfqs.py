from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# In-memory storage
rfqs_db = []

class RFQCreate(BaseModel):
    molecule: str  # H2, NH3, SAF, eMeOH
    volume_mtpd: float
    price_max: Optional[float] = None
    delivery_start: str
    delivery_end: str
    criteria: Dict[str, Any]  # Matching criteria (purity, distance, etc.)

class RFQResponse(BaseModel):
    id: str
    molecule: str
    volume_mtpd: float
    price_max: Optional[float]
    delivery_start: str
    delivery_end: str
    criteria: Dict[str, Any]
    status: str
    created_at: str

@router.post("/", status_code=201)
async def create_rfq(rfq: RFQCreate):
    """Create a new Request for Quote"""
    new_rfq = {
        "id": str(uuid4()),
        "molecule": rfq.molecule,
        "volume_mtpd": rfq.volume_mtpd,
        "price_max": rfq.price_max,
        "delivery_start": rfq.delivery_start,
        "delivery_end": rfq.delivery_end,
        "criteria": rfq.criteria,
        "status": "open",
        "created_at": datetime.now().isoformat()
    }
    rfqs_db.append(new_rfq)
    return new_rfq

@router.get("/")
async def list_rfqs(molecule: Optional[str] = None, status: Optional[str] = None):
    """List all RFQs with optional filtering"""
    filtered_rfqs = rfqs_db
    
    if molecule:
        filtered_rfqs = [r for r in filtered_rfqs if r["molecule"] == molecule]
    if status:
        filtered_rfqs = [r for r in filtered_rfqs if r["status"] == status]
    
    return {
        "rfqs": filtered_rfqs,
        "total": len(filtered_rfqs)
    }

@router.get("/{rfq_id}")
async def get_rfq(rfq_id: str):
    """Get a specific RFQ"""
    for rfq in rfqs_db:
        if rfq["id"] == rfq_id:
            return rfq
    raise HTTPException(status_code=404, detail="RFQ not found")

@router.patch("/{rfq_id}/status")
async def update_rfq_status(rfq_id: str, status: str):
    """Update RFQ status (open, matched, closed)"""
    for rfq in rfqs_db:
        if rfq["id"] == rfq_id:
            rfq["status"] = status
            rfq["updated_at"] = datetime.now().isoformat()
            return rfq
    raise HTTPException(status_code=404, detail="RFQ not found")

@router.delete("/{rfq_id}")
async def delete_rfq(rfq_id: str):
    """Delete an RFQ"""
    global rfqs_db
    rfqs_db = [r for r in rfqs_db if r["id"] != rfq_id]
    return {"message": "RFQ deleted"}