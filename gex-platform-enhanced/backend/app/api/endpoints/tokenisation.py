from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# In-memory storage
tokens_db = []

class TokenCreate(BaseModel):
    capacity_id: str
    tokenised_pct: float  # 0-100
    tokenised_mtpd: float
    delivery_start: str
    delivery_end: str
    compliance_rfnbo: Optional[int] = None
    compliance_45v: Optional[int] = None
    compliance_red: Optional[int] = None

class TokenResponse(BaseModel):
    id: str
    capacity_id: str
    tokenised_pct: float
    tokenised_mtpd: float
    delivery_start: str
    delivery_end: str
    compliance_rfnbo: Optional[int]
    compliance_45v: Optional[int]
    compliance_red: Optional[int]
    status: str
    created_at: str

@router.post("/", status_code=201)
async def create_token(token: TokenCreate):
    """Tokenise a portion of production capacity"""
    
    # Validate percentage
    if token.tokenised_pct < 0 or token.tokenised_pct > 100:
        raise HTTPException(status_code=400, detail="Tokenised percentage must be between 0 and 100")
    
    new_token = {
        "id": str(uuid4()),
        "capacity_id": token.capacity_id,
        "tokenised_pct": token.tokenised_pct,
        "tokenised_mtpd": token.tokenised_mtpd,
        "delivery_start": token.delivery_start,
        "delivery_end": token.delivery_end,
        "compliance_rfnbo": token.compliance_rfnbo,
        "compliance_45v": token.compliance_45v,
        "compliance_red": token.compliance_red,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }
    tokens_db.append(new_token)
    return new_token

@router.get("/")
async def list_tokens(capacity_id: Optional[str] = None):
    """List all tokens with optional filtering by capacity"""
    filtered_tokens = tokens_db
    
    if capacity_id:
        filtered_tokens = [t for t in filtered_tokens if t["capacity_id"] == capacity_id]
    
    return {
        "tokens": filtered_tokens,
        "total": len(filtered_tokens)
    }

@router.get("/{token_id}")
async def get_token(token_id: str):
    """Get a specific token"""
    for token in tokens_db:
        if token["id"] == token_id:
            return token
    raise HTTPException(status_code=404, detail="Token not found")

@router.patch("/{token_id}/compliance")
async def update_compliance(
    token_id: str,
    compliance_rfnbo: Optional[int] = None,
    compliance_45v: Optional[int] = None,
    compliance_red: Optional[int] = None
):
    """Update compliance scores for a token"""
    for token in tokens_db:
        if token["id"] == token_id:
            if compliance_rfnbo is not None:
                token["compliance_rfnbo"] = compliance_rfnbo
            if compliance_45v is not None:
                token["compliance_45v"] = compliance_45v
            if compliance_red is not None:
                token["compliance_red"] = compliance_red
            token["updated_at"] = datetime.now().isoformat()
            return token
    raise HTTPException(status_code=404, detail="Token not found")

@router.delete("/{token_id}")
async def delete_token(token_id: str):
    """Delete a token"""
    global tokens_db
    tokens_db = [t for t in tokens_db if t["id"] != token_id]
    return {"message": "Token deleted"}