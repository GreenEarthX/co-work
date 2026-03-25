"""
OT/IT Boundary — Plant Data Ingestion API
==========================================
Receives one-way data push from OT gateways.
GEX NEVER initiates connections to OT. This endpoint is the DMZ boundary.

mTLS verified in production (via nginx/envoy). Dev: gateway_id + SHA-256.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.ot_boundary import (
    validate_inbound, store_plant_data, get_plant_data,
    get_gateways, init_ot_db, ALLOWED_DATA_TYPES,
)

router = APIRouter()

try:
    init_ot_db()
except Exception:
    pass


# ─── Models ──────────────────────────────────────────────────────────────────

class PlantDataIngest(BaseModel):
    gateway_id: str
    project_id: str
    data_type: str
    payload: dict
    sha256_hash: str   # SHA-256 of canonical JSON payload


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/health")
def plant_health():
    return {"status": "ok", "service": "plant_data_ingest",
            "allowed_data_types": list(ALLOWED_DATA_TYPES)}


@router.post("/ingest")
async def ingest(
    body: PlantDataIngest,
    request: Request,
    x_gateway_cert: Optional[str] = Header(default=None),
):
    """
    Accept inbound OT data push from a registered gateway.
    Validates: gateway registration, data type allowlist, SHA-256 integrity.
    Returns 200 on success, 422 on validation failure, 403 on rejected.
    """
    source_ip = request.client.host if request.client else None

    result = validate_inbound(
        gateway_id=body.gateway_id,
        data_type=body.data_type,
        payload=body.payload,
        claimed_sha256=body.sha256_hash,
        source_ip=source_ip,
    )

    if not result.valid:
        raise HTTPException(
            status_code=403 if "Gateway" in (result.reason or "") else 422,
            detail={"reason": result.reason, "gateway_id": body.gateway_id},
        )

    record_id = store_plant_data(
        gateway_id=body.gateway_id,
        project_id=body.project_id,
        data_type=body.data_type,
        payload=body.payload,
        sha256_hash=body.sha256_hash,
    )

    return {
        "status": "accepted",
        "record_id": record_id,
        "gateway_id": body.gateway_id,
        "data_type": body.data_type,
        "sha256_verified": result.sha256_match,
    }


@router.get("/data/{project_id}")
def get_data(
    project_id: str,
    data_type: Optional[str] = None,
    limit: int = 100,
    x_demo_company: Optional[str] = Header(default=None),
):
    """Retrieve stored plant data for a project. CISO/Producer workspace view."""
    rows = get_plant_data(project_id, data_type, min(limit, 500))
    return {"project_id": project_id, "total": len(rows), "records": rows}


@router.get("/gateways")
def list_gateways(
    project_id: Optional[str] = None,
    x_demo_company: Optional[str] = Header(default=None),
):
    """List registered OT gateways. CISO monitoring view."""
    gws = get_gateways(project_id)
    return {"total": len(gws), "gateways": gws}


@router.get("/gateways/{gateway_id}")
def get_gateway(
    gateway_id: str,
    x_demo_company: Optional[str] = Header(default=None),
):
    gws = get_gateways()
    gw = next((g for g in gws if g["id"] == gateway_id), None)
    if not gw:
        raise HTTPException(status_code=404, detail="Gateway not found")
    return gw


@router.get("/demo/{project_id}")
def demo_plant_data(project_id: str):
    """Returns seeded demo plant data for CISO dashboard when no real OT is connected."""
    return {
        "project_id": project_id,
        "note": "Demo data — no OT gateway connected in dev",
        "records": [
            {
                "id": "pd-001",
                "project_id": project_id,
                "gateway_id": "gw-breizh-001",
                "data_type": "PRODUCTION_VOLUME",
                "payload_json": {"value": 4.2, "unit": "t/day NH3", "timestamp": "2026-03-17T08:00:00Z"},
                "sha256_hash": "sha256:demo",
                "received_at": "2026-03-17T08:01:00Z",
            },
            {
                "id": "pd-002",
                "project_id": project_id,
                "gateway_id": "gw-breizh-001",
                "data_type": "ELECTROLYSER_EFFICIENCY",
                "payload_json": {"value": 52.1, "unit": "kWh/kg H2", "timestamp": "2026-03-17T08:00:00Z"},
                "sha256_hash": "sha256:demo",
                "received_at": "2026-03-17T08:01:00Z",
            },
            {
                "id": "pd-003",
                "project_id": project_id,
                "gateway_id": "gw-breizh-001",
                "data_type": "GHG_MEASUREMENT",
                "payload_json": {"value": 0.82, "unit": "gCO2eq/MJ", "standard": "RED III", "timestamp": "2026-03-17T07:00:00Z"},
                "sha256_hash": "sha256:demo",
                "received_at": "2026-03-17T07:01:00Z",
            },
            {
                "id": "pd-004",
                "project_id": project_id,
                "gateway_id": "gw-breizh-001",
                "data_type": "PLANT_STATUS",
                "payload_json": {"status": "OPERATING", "uptime_pct": 94.3, "timestamp": "2026-03-17T08:00:00Z"},
                "sha256_hash": "sha256:demo",
                "received_at": "2026-03-17T08:01:00Z",
            },
        ],
    }
