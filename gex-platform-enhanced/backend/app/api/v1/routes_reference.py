"""
Reference data registry API — /api/v1/reference. Schema: alembic 061.

Reads are open to every authenticated caller: reference data is the same for all
tenants. Every write is GEX staff only (`is_platform_admin`), which is also what
RLS requires — the staff caller's connection runs as PLATFORM_ADMIN through the
request-bound tenant, so no escalated connection is opened here. A tenant that
reached the SQL anyway would be refused by the policy.

Approval enforces separation of duties: the approver is not the proposer.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core import reference_registry as reg
from app.core.reference_catalog import PARAMETERS, UNIT_FAMILIES
from app.core.request_tenant import payload_from_request

router = APIRouter()


class ProposalInput(BaseModel):
    parameter_key: str
    pathway: str = "ANY"
    region: str = "ANY"
    value_low: Optional[float] = None
    value_base: float
    value_high: Optional[float] = None
    unit: str
    currency: Optional[str] = None
    price_base_date: Optional[str] = None
    source_class: str
    source_name: str
    source_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    valid_from: Optional[str] = None
    note: Optional[str] = None


def _staff(request: Request) -> str:
    payload = payload_from_request(request) or {}
    if not payload.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail="GEX staff only: reference data is curated")
    actor = payload.get("user_id")
    if not actor:
        raise HTTPException(status_code=401, detail="authenticated identity required")
    return actor


def _conn():
    if not reg.registry_available():
        raise HTTPException(status_code=503,
                            detail="the reference registry needs FUELREF_DB_BACKEND=postgres")
    return reg._connection()


def _run(fn, *args, write: bool = False):
    conn = _conn()
    try:
        result = fn(conn, *args)
        if write:
            conn.commit()
        return result
    except reg.RegistryError as exc:
        conn.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/catalog")
def catalog():
    """The closed parameter catalog: keys, unit family and allowed units."""
    return [{"parameter_key": k, "family": d.family, "units": list(UNIT_FAMILIES[d.family]),
             "description": d.description} for k, d in sorted(PARAMETERS.items())]


@router.get("/parameters")
def list_parameters(key: Optional[str] = None, pathway: Optional[str] = None,
                    region: Optional[str] = None, as_of: Optional[str] = None):
    """Approved values in force on `as_of` (default today), filtered exactly."""
    return _run(reg.list_in_force, key, pathway, region, as_of)


@router.get("/resolve")
def resolve(key: str, pathway: str = "ANY", region: str = "ANY",
            as_of: Optional[str] = None):
    """The most specific value in force, falling back toward ANY. 404 if none."""
    row = _run(reg.resolve, key, pathway, region, as_of)
    if row is None:
        raise HTTPException(status_code=404,
                            detail=f"no approved {key} for {pathway}/{region}")
    return row


@router.get("/parameters/{ref_id}")
def get_parameter(ref_id: str):
    row = _run(reg.get_row, ref_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no reference row {ref_id}")
    return row


@router.post("/parameters", status_code=201)
def propose(body: ProposalInput, request: Request):
    actor = _staff(request)
    return _run(reg.propose, body.model_dump(), actor, write=True)


@router.post("/parameters/{ref_id}/approve")
def approve(ref_id: str, request: Request):
    actor = _staff(request)
    return _run(reg.approve, ref_id, actor, write=True)


@router.post("/parameters/{ref_id}/reject")
def reject(ref_id: str, request: Request):
    actor = _staff(request)
    return _run(reg.reject, ref_id, actor, write=True)


@router.get("/versions/latest")
def latest_version():
    v = _run(reg.latest_version)
    if v is None:
        raise HTTPException(status_code=404, detail="no reference version")
    return v


@router.get("/versions/{version_id}")
def get_version(version_id: str):
    v = _run(reg.get_version, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail=f"no reference version {version_id}")
    return v
