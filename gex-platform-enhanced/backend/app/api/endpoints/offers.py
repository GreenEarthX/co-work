from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# In-memory storage
offers_db = []

class OfferCreate(BaseModel):
    molecule: str  # H2, NH3, SAF, eMeOH, HVO,eNG
    volume_mtpd: float
    price_min: float
    price_max: float
    price_currency: str = "EUR"
    delivery_start: str
    delivery_end: str
    offer_type: str = "indicative"  # indicative, firm
    visibility: str = "public"  # public, private
    specifications: Optional[Dict[str, Any]] = None

class OfferResponse(BaseModel):
    id: str
    molecule: str
    volume_mtpd: float
    price_min: float
    price_max: float
    price_currency: str
    delivery_start: str
    delivery_end: str
    offer_type: str
    visibility: str
    status: str
    specifications: Optional[Dict[str, Any]]
    created_at: str

@router.post("/", status_code=201)
async def create_offer(offer: OfferCreate):
    """Create a new market offer"""
    new_offer = {
        "id": str(uuid4()),
        "molecule": offer.molecule,
        "volume_mtpd": offer.volume_mtpd,
        "price_min": offer.price_min,
        "price_max": offer.price_max,
        "price_currency": offer.price_currency,
        "delivery_start": offer.delivery_start,
        "delivery_end": offer.delivery_end,
        "offer_type": offer.offer_type,
        "visibility": offer.visibility,
        "status": "active",
        "specifications": offer.specifications or {},
        "created_at": datetime.now().isoformat()
    }
    offers_db.append(new_offer)
    return new_offer

@router.get("/")
async def list_offers(molecule: Optional[str] = None, status: Optional[str] = None):
    """List all offers with optional filtering"""
    filtered_offers = offers_db
    
    if molecule:
        filtered_offers = [o for o in filtered_offers if o["molecule"] == molecule]
    if status:
        filtered_offers = [o for o in filtered_offers if o["status"] == status]
    
    return {
        "offers": filtered_offers,
        "total": len(filtered_offers)
    }

@router.get("/{offer_id}")
async def get_offer(offer_id: str):
    """Get a specific offer"""
    for offer in offers_db:
        if offer["id"] == offer_id:
            return offer
    raise HTTPException(status_code=404, detail="Offer not found")

@router.patch("/{offer_id}/status")
async def update_offer_status(offer_id: str, status: str):
    """Update offer status (active, matched, expired, withdrawn)"""
    for offer in offers_db:
        if offer["id"] == offer_id:
            offer["status"] = status
            offer["updated_at"] = datetime.now().isoformat()
            return offer
    raise HTTPException(status_code=404, detail="Offer not found")

@router.delete("/{offer_id}")
async def delete_offer(offer_id: str):
    """Delete an offer"""
    global offers_db
    offers_db = [o for o in offers_db if o["id"] != offer_id]
    return {"message": "Offer deleted"}