"""
GEX Bankability — EPC/OEM Performance Matrix API (v2.0)

Endpoints:
  GET    /api/v1/performance/{project_id}/kpis
  POST   /api/v1/performance/{project_id}/kpis
  PATCH  /api/v1/performance/{project_id}/kpis/{kpi_id}
  GET    /api/v1/performance/{project_id}/kpis/{kpi_id}/history
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class KPITarget(BaseModel):
    kpi_name: str
    target_value: float
    target_unit: str
    target_condition: Optional[str] = None
    test_method: Optional[str] = None
    remedy: Optional[str] = None
    ld_formula: Optional[str] = None
    ld_cap_eur: Optional[float] = None
    parent_guarantee: bool = False
    spares_sla: Optional[str] = None
    warranty_hours: Optional[int] = None

class KPIActual(BaseModel):
    actual_value: float
    actual_date: str
    status: str = "TESTED"    # PENDING | TESTED | PASS | FAIL | REMEDIATION


# Pre-seeded KPIs from Playbook §5A
_PRESET_KPIS = [
    {
        "id": "kpi-001", "kpi_name": "Net Efficiency (kWh/kg H₂)",
        "target_value": 54.0, "target_unit": "kWh/kg",
        "target_condition": "at P50 conditions, stack rated performance",
        "test_method": "Commissioning test; quarterly M&V via SCADA",
        "remedy": "LDs €/kg shortfall vs target; mandatory OEM tuning plan",
        "ld_formula": "(target - actual) × volume_kg × ld_rate_eur",
        "ld_cap_eur": 2_000_000,
        "parent_guarantee": True,
        "warranty_hours": 40_000,
        "status": "PENDING",
    },
    {
        "id": "kpi-002", "kpi_name": "System Availability (%)",
        "target_value": 95.0, "target_unit": "%",
        "target_condition": "rolling 12-month average, excluding planned maintenance",
        "test_method": "SCADA uptime logs + OEM reports; quarterly audit",
        "remedy": "LDs €/day downtime; extended warranty; mandatory spares stock",
        "ld_formula": "(target_pct - actual_pct) × capacity_kgd × product_price",
        "ld_cap_eur": 5_000_000,
        "parent_guarantee": True,
        "warranty_hours": 80_000,
        "status": "PENDING",
    },
    {
        "id": "kpi-003", "kpi_name": "Ramp Rate (%/min)",
        "target_value": 5.0, "target_unit": "%/min",
        "target_condition": "from 20% to 100% rated load",
        "test_method": "Dynamic performance test at commissioning; OEM logs quarterly",
        "remedy": "Cycle-related LDs; curtailment protocol activation",
        "ld_cap_eur": 500_000,
        "status": "PENDING",
    },
    {
        "id": "kpi-004", "kpi_name": "Degradation Rate (%/1,000h)",
        "target_value": 0.5, "target_unit": "%/1,000h",
        "target_condition": "stack performance degradation from baseline",
        "test_method": "Stack polarisation curve tests; annual OEM inspection",
        "remedy": "OEM replacement of degraded stack sections at OEM cost up to warranty hours",
        "warranty_hours": 80_000,
        "status": "PENDING",
    },
    {
        "id": "kpi-005", "kpi_name": "Start-up Time (min)",
        "target_value": 15.0, "target_unit": "minutes",
        "target_condition": "cold start to 50% rated load",
        "test_method": "SATs (Site Acceptance Tests) at commissioning",
        "remedy": "Penalties per overrun; revised O&M SOP if repeated failures",
        "status": "PENDING",
    },
    {
        "id": "kpi-006", "kpi_name": "M&V Data Access",
        "target_value": 99.0, "target_unit": "% uptime",
        "target_condition": "API data feed availability; timestamped at 15-min intervals",
        "test_method": "Automated API health monitoring; periodic audit",
        "remedy": "Payment holdback if data missing; SLA credits",
        "status": "PENDING",
    },
    {
        "id": "kpi-007", "kpi_name": "Cybersecurity & Safety (IEC 62443 / SIL)",
        "target_value": 2.0, "target_unit": "SIL level",
        "target_condition": "SIL 2 per IEC 62443 for critical control loops",
        "test_method": "Third-party penetration test; HAZOP/LOPA review",
        "remedy": "Cure plan within 30 days; step-in rights for lenders",
        "status": "PENDING",
    },
]


@router.get("/{project_id}/kpis")
async def get_kpis(project_id: str):
    """Return all EPC/OEM performance KPIs for a project."""
    kpis = [{**k, "project_id": project_id} for k in _PRESET_KPIS]
    return {
        "project_id": project_id,
        "kpis": kpis,
        "total": len(kpis),
        "pass_count": 0,
        "fail_count": 0,
        "pending_count": len(kpis),
    }


@router.post("/{project_id}/kpis")
async def create_kpi(project_id: str, kpi: KPITarget):
    """Add a custom KPI target to the project's performance matrix."""
    return {
        "created": True,
        "project_id": project_id,
        "kpi_id": f"kpi-{project_id}-custom",
        "kpi": kpi,
    }


@router.patch("/{project_id}/kpis/{kpi_id}")
async def record_actual(project_id: str, kpi_id: str, actual: KPIActual):
    """Record actual test result against a KPI target."""
    return {
        "updated": True,
        "kpi_id": kpi_id,
        "project_id": project_id,
        "actual_value": actual.actual_value,
        "actual_date": actual.actual_date,
        "status": actual.status,
    }


@router.get("/{project_id}/kpis/{kpi_id}/history")
async def get_kpi_history(project_id: str, kpi_id: str):
    """Version history for a KPI target (previous values + changes)."""
    return {
        "project_id": project_id,
        "kpi_id": kpi_id,
        "history": [],  # Replace with DB query in production
    }
