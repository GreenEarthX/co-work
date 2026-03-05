"""
Pydantic Schemas for API Validation
"""
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ===== Capacity Schemas =====
class CapacityCreate(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255)
    molecule: str = Field(..., pattern="^(H2|NH3|SAF|eMeOH)$")
    capacity_mtpd: float = Field(..., gt=0)
    start_date: date
    end_date: Optional[date] = None
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_lon: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v, info):
        if v and info.data.get("start_date") and v < info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class CapacityResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_name: str
    molecule: str
    capacity_mtpd: float
    start_date: date
    end_date: Optional[date]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== Tokenisation Schemas =====
class TokenCreate(BaseModel):
    capacity_id: UUID
    tokenised_pct: float = Field(..., ge=0, le=100)
    delivery_start: date
    delivery_end: date
    compliance_rfnbo: Optional[int] = Field(None, ge=0, le=100)
    compliance_45v: Optional[int] = Field(None, ge=0, le=100)
    compliance_red: Optional[int] = Field(None, ge=0, le=100)

    @field_validator("delivery_end")
    @classmethod
    def validate_delivery_end(cls, v, info):
        if v < info.data.get("delivery_start"):
            raise ValueError("delivery_end must be after delivery_start")
        return v


class TokenResponse(BaseModel):
    id: UUID
    capacity_id: UUID
    tokenised_pct: float
    tokenised_mtpd: float
    delivery_start: date
    delivery_end: date
    compliance_rfnbo: Optional[int]
    compliance_45v: Optional[int]
    compliance_red: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Offer Schemas =====
class OfferCreate(BaseModel):
    token_id: UUID
    offer_type: str = Field(..., pattern="^(indicative|firm)$")
    volume_mtpd: float = Field(..., gt=0)
    price_min: Optional[float] = Field(None, gt=0)
    price_max: Optional[float] = Field(None, gt=0)
    price_currency: str = Field(default="EUR", pattern="^(EUR|USD|GBP)$")
    visibility: str = Field(default="public", pattern="^(public|private|auction)$")
    expires_at: Optional[datetime] = None
    specifications: Optional[Dict] = None

    @field_validator("price_max")
    @classmethod
    def validate_price_max(cls, v, info):
        price_min = info.data.get("price_min")
        if price_min and v and v < price_min:
            raise ValueError("price_max must be >= price_min")
        return v


class OfferResponse(BaseModel):
    id: UUID
    organization_id: UUID
    token_id: UUID
    offer_type: str
    volume_mtpd: float
    price_min: Optional[float]
    price_max: Optional[float]
    price_currency: str
    visibility: str
    status: str
    specifications: Optional[Dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ===== RFQ Schemas =====
class RFQCreate(BaseModel):
    molecule: str = Field(..., pattern="^(H2|NH3|SAF|eMeOH)$")
    volume_mtpd: float = Field(..., gt=0)
    price_max: Optional[float] = Field(None, gt=0)
    delivery_start: date
    delivery_end: date
    criteria: Dict = Field(..., description="Molecule-specific criteria")

    @field_validator("delivery_end")
    @classmethod
    def validate_delivery_end(cls, v, info):
        if v < info.data.get("delivery_start"):
            raise ValueError("delivery_end must be after delivery_start")
        return v


class RFQResponse(BaseModel):
    id: UUID
    buyer_org_id: UUID
    molecule: str
    volume_mtpd: float
    price_max: Optional[float]
    delivery_start: date
    delivery_end: date
    criteria: Dict
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Matching Schemas =====
class MatchBreakdown(BaseModel):
    price_fit: float
    volume_fit: float
    window_fit: float
    distance_fit: float
    compliance_fit: float
    counterparty_fit: float
    spec_fit: float


class MatchResponse(BaseModel):
    id: UUID
    rfq_id: UUID
    offer_id: UUID
    score: float
    breakdown: MatchBreakdown
    matched_at: datetime

    class Config:
        from_attributes = True


class MatchingRequest(BaseModel):
    rfq_id: UUID
    min_score: float = Field(default=50.0, ge=0, le=100)
    max_results: int = Field(default=10, ge=1, le=100)


# ===== Pagination =====
class PaginatedResponse(BaseModel):
    items: List[BaseModel]
    total: int
    page: int
    page_size: int
    total_pages: int


# ===== Health Check =====
class HealthCheck(BaseModel):
    status: str
    environment: str
    version: str
