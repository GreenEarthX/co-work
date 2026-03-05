"""
Database Models
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Enum, Float,
    ForeignKey, Integer, JSON, Numeric, String, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Organization(Base, TimestampMixin):
    """Organizations (producers, buyers, certifiers)"""
    __tablename__ = "organizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # producer, buyer, certifier
    
    # Relationships
    users = relationship("User", back_populates="organization")
    capacities = relationship("Capacity", back_populates="organization")
    offers = relationship("Offer", back_populates="organization")
    rfqs = relationship("RFQ", back_populates="buyer_organization")


class User(Base, TimestampMixin):
    """Platform users"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    email = Column(String(255), unique=True, nullable=False)
    role = Column(String(50), nullable=False)  # admin, trader, viewer
    auth_provider_id = Column(String(255), unique=True)  # Clerk/Auth0 ID
    
    # Relationships
    organization = relationship("Organization", back_populates="users")


class Capacity(Base, TimestampMixin):
    """Production capacity baseline"""
    __tablename__ = "capacities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    project_name = Column(String(255), nullable=False)
    molecule = Column(String(10), nullable=False)  # H2, NH3, SAF, eMeOH
    capacity_mtpd = Column(Numeric(10, 2), nullable=False)
    location = Column(Geometry("POINT", srid=4326))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    organization = relationship("Organization", back_populates="capacities")
    tokens = relationship("Token", back_populates="capacity")
    
    __table_args__ = (
        Index("idx_capacities_org_molecule", "organization_id", "molecule"),
    )


class Token(Base, TimestampMixin):
    """Tokenised tradable inventory"""
    __tablename__ = "tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    capacity_id = Column(UUID(as_uuid=True), ForeignKey("capacities.id"))
    tokenised_pct = Column(Numeric(5, 2), nullable=False)
    tokenised_mtpd = Column(Numeric(10, 2), nullable=False)
    delivery_start = Column(Date, nullable=False)
    delivery_end = Column(Date, nullable=False)
    
    # Compliance scores (0-100)
    compliance_rfnbo = Column(Integer)
    compliance_45v = Column(Integer)
    compliance_red = Column(Integer)
    
    # Relationships
    capacity = relationship("Capacity", back_populates="tokens")
    offers = relationship("Offer", back_populates="token")
    
    __table_args__ = (
        CheckConstraint("tokenised_pct >= 0 AND tokenised_pct <= 100"),
        CheckConstraint("compliance_rfnbo >= 0 AND compliance_rfnbo <= 100"),
        CheckConstraint("compliance_45v >= 0 AND compliance_45v <= 100"),
        CheckConstraint("compliance_red >= 0 AND compliance_red <= 100"),
    )


class Offer(Base, TimestampMixin):
    """Market offers from producers"""
    __tablename__ = "offers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    token_id = Column(UUID(as_uuid=True), ForeignKey("tokens.id"))
    offer_type = Column(String(20), nullable=False)  # indicative, firm
    volume_mtpd = Column(Numeric(10, 2), nullable=False)
    price_min = Column(Numeric(10, 2))
    price_max = Column(Numeric(10, 2))
    price_currency = Column(String(3), default="EUR")
    visibility = Column(String(20), default="public")  # public, private, auction
    status = Column(String(20), default="active")  # active, matched, expired, withdrawn
    expires_at = Column(DateTime)
    
    # Technical specifications (JSON)
    specifications = Column(JSON)
    
    # Relationships
    organization = relationship("Organization", back_populates="offers")
    token = relationship("Token", back_populates="offers")
    matches = relationship("Match", back_populates="offer")
    
    __table_args__ = (
        Index("idx_offers_status_molecule", "status"),
    )


class RFQ(Base, TimestampMixin):
    """Buyer Request for Quotes"""
    __tablename__ = "rfqs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    buyer_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    molecule = Column(String(10), nullable=False)
    volume_mtpd = Column(Numeric(10, 2), nullable=False)
    price_max = Column(Numeric(10, 2))
    delivery_start = Column(Date, nullable=False)
    delivery_end = Column(Date, nullable=False)
    
    # Molecule-specific criteria (JSON)
    criteria = Column(JSON, nullable=False)
    
    status = Column(String(20), default="open")  # open, matched, closed
    
    # Relationships
    buyer_organization = relationship("Organization", back_populates="rfqs")
    matches = relationship("Match", back_populates="rfq")
    
    __table_args__ = (
        Index("idx_rfqs_molecule_status", "molecule", "status"),
    )


class Match(Base):
    """Matching results between RFQs and Offers"""
    __tablename__ = "matches"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    rfq_id = Column(UUID(as_uuid=True), ForeignKey("rfqs.id"))
    offer_id = Column(UUID(as_uuid=True), ForeignKey("offers.id"))
    score = Column(Numeric(5, 2), nullable=False)
    
    # Breakdown of scoring components (JSON)
    breakdown = Column(JSON, nullable=False)
    
    matched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    rfq = relationship("RFQ", back_populates="matches")
    offer = relationship("Offer", back_populates="matches")
    dd_pipeline = relationship("DDPipeline", back_populates="match", uselist=False)
    
    __table_args__ = (
        Index("idx_matches_score", "rfq_id", "score"),
        CheckConstraint("score >= 0 AND score <= 100"),
    )


class DDPipeline(Base, TimestampMixin):
    """Due Diligence Pipeline Stages"""
    __tablename__ = "dd_pipeline"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"))
    stage = Column(String(50), nullable=False)  # kyc, credit, technical, legal, complete
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    status = Column(String(20), default="pending")  # pending, in_progress, approved, rejected
    notes = Column(Text)
    completed_at = Column(DateTime)
    
    # Relationships
    match = relationship("Match", back_populates="dd_pipeline")


class AuditLog(Base):
    """Immutable audit trail"""
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)  # create, update, delete
    old_values = Column(JSON)
    new_values = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_timestamp", "timestamp"),
    )
