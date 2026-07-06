"""Fuel catalogue administration and conversion routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.auth import has_platform_admin_access
from app.core.fuel_catalog import (
    convert_fuel_value,
    deactivate_fuel,
    get_fuel,
    load_fuel_catalog,
    upsert_fuel,
)

router = APIRouter(prefix="/fuels", tags=["fuels"])


class FuelMeasuresRequest(BaseModel):
    trading_unit: str
    price_unit: str
    mass_unit: str
    energy_unit: str
    specific_energy_unit: str = "kWh/kg"
    specific_energy_value: float | None = Field(default=None, gt=0)
    capacity_unit: str
    emissions_unit: str


class FuelConversionRuleRequest(BaseModel):
    from_unit: str
    to_unit: str
    multiplier: float
    offset: float = 0.0
    dimension: str = "custom"
    rule_type: str = "custom"
    note: str | None = None


class FuelUpsertRequest(BaseModel):
    id: str
    label: str
    offered: bool = True
    status: str = "active_catalog"
    legacy_aliases: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    measures: FuelMeasuresRequest
    conversion_rules: list[FuelConversionRuleRequest] = Field(default_factory=list)
    sort_order: int = 0
    is_active: bool = True


def _require_platform_admin(request: Request) -> dict[str, Any]:
    payload = getattr(request.state, "auth_user_payload", None)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if not has_platform_admin_access(payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the GEX administrator can modify the fuel catalogue",
        )
    return payload


@router.get("")
async def list_catalogue(
    include_inactive: bool = Query(default=False),
    offered_only: bool = Query(default=False),
):
    return load_fuel_catalog(
        offered_only=offered_only,
        include_inactive=include_inactive,
    )


@router.get("/{fuel_id}")
async def fuel_detail(
    fuel_id: str,
    include_inactive: bool = Query(default=False),
):
    fuel = get_fuel(fuel_id, include_inactive=include_inactive)
    if not fuel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel not found")
    return fuel


@router.get("/{fuel_id}/convert")
async def convert_units(
    fuel_id: str,
    value: float = Query(...),
    from_unit: str = Query(...),
    to_unit: str = Query(...),
):
    try:
        return convert_fuel_value(fuel_id, value, from_unit, to_unit)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{fuel_id}")
async def upsert_catalogue_fuel(
    fuel_id: str,
    body: FuelUpsertRequest,
    request: Request,
):
    actor = _require_platform_admin(request)
    if body.id != fuel_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fuel id in path and body must match",
        )
    return upsert_fuel(body.model_dump(), updated_by=actor["email"])


@router.delete("/{fuel_id}")
async def deactivate_catalogue_fuel(fuel_id: str, request: Request):
    actor = _require_platform_admin(request)
    fuel = get_fuel(fuel_id, include_inactive=True)
    if not fuel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel not found")
    deactivate_fuel(fuel_id, updated_by=actor["email"])
    return {"status": "ok", "fuel_id": fuel_id, "is_active": False}
