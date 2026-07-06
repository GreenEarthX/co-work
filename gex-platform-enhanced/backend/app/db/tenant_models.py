"""
ORM models for tenant isolation tables (migration 020).

These are separate from models.py to keep the original market models intact
while we layer multi-tenancy on top.
"""

from datetime import date, datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.models import Base, TimestampMixin


class Tenant(Base):
    """One row per company — the unit of isolation."""
    __tablename__ = "tenants"

    company_id   = Column(Text, primary_key=True)
    company_name = Column(Text, nullable=False)
    company_type = Column(Text, nullable=False)   # PRODUCER | OFFTAKER | THIRD_PARTY
    jurisdiction = Column(Text, nullable=False, server_default="EU")
    is_active    = Column(Boolean, nullable=False, server_default="true")
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at   = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    projects_owned  = relationship("Project", back_populates="owner_tenant",
                                   foreign_keys="Project.owner_tenant_id")
    access_grants   = relationship("ProjectAccess", back_populates="tenant",
                                   foreign_keys="ProjectAccess.company_id")


class Project(Base):
    """A green-fuel project — only visible to its owner and granted stakeholders."""
    __tablename__ = "projects"

    project_id      = Column(Text, primary_key=True)
    project_name    = Column(Text, nullable=False)
    owner_tenant_id = Column(Text, ForeignKey("tenants.company_id", ondelete="RESTRICT"),
                             nullable=False, index=True)
    molecule        = Column(Text, nullable=False)
    status          = Column(Text, nullable=False, server_default="development")
    jurisdiction    = Column(Text, nullable=False, server_default="EU")
    capex_eur       = Column(Numeric(18, 2))
    capacity_mtpd   = Column(Numeric(10, 4))
    completion_date = Column(DateTime(timezone=True))
    metadata_json   = Column(JSONB, server_default="'{}'")
    is_active       = Column(Boolean, nullable=False, server_default="true")
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at      = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    owner_tenant    = relationship("Tenant", back_populates="projects_owned",
                                   foreign_keys=[owner_tenant_id])
    access_grants   = relationship("ProjectAccess", back_populates="project",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_projects_owner",    "owner_tenant_id"),
        Index("idx_projects_molecule", "molecule"),
        Index("idx_projects_status",   "status"),
    )


class ProjectProfileIntelligence(Base):
    """Backend-owned general narrative and linked public facts for a project."""
    __tablename__ = "project_profile_intelligence"

    record_id      = Column(Text, primary_key=True)
    project_id     = Column(Text, ForeignKey("projects.project_id", ondelete="CASCADE"),
                            nullable=False, index=True)
    narrative      = Column(Text, nullable=False)
    source_scope   = Column(Text, nullable=False, server_default="GEX_PUBLIC_PREFILL")
    access_tier    = Column(Text, nullable=False, server_default="STAKEHOLDER")
    backend_store  = Column(Text, nullable=False, server_default="project_profile_intelligence")
    linked_records = Column(JSONB, server_default="'[]'")
    metadata_json  = Column(JSONB, server_default="'{}'")
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at     = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    __table_args__ = (
        Index("idx_project_profile_intelligence_project", "project_id"),
    )


class ProjectAccess(Base):
    """
    Junction table: which company can access which project, as which actor type.

    A prosumer (e.g. BremenThree) gets two rows per project:
      company_id=brementhree_ag, actor_type=OFFTAKER
      company_id=brementhree_ag, actor_type=PRODUCER
    """
    __tablename__ = "project_access"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    project_id  = Column(Text, ForeignKey("projects.project_id", ondelete="CASCADE"),
                         nullable=False)
    company_id  = Column(Text, ForeignKey("tenants.company_id", ondelete="CASCADE"),
                         nullable=False)
    actor_type  = Column(Text, nullable=False)
    access_role = Column(Text, nullable=False, server_default="STAKEHOLDER")
    granted_by  = Column(Text)
    granted_at  = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    project = relationship("Project", back_populates="access_grants")
    tenant  = relationship("Tenant",  back_populates="access_grants",
                           foreign_keys=[company_id])

    __table_args__ = (
        UniqueConstraint("project_id", "company_id", "actor_type",
                         name="uq_project_access"),
        Index("idx_project_access_project", "project_id"),
        Index("idx_project_access_company", "company_id"),
    )
