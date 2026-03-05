bankability.py
"""
Bankability API Endpoints
Provides evidence tracking and persona-scoped views
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from app.services.bankability_client import bankability_client

router = APIRouter()

@router.get("/projects/{project_id}/bankability/{persona}")
async def get_bankability_view(project_id: str, persona: str):
    """Get persona-scoped bankability view for workspace"""
    try:
        # TODO: Get evidence from database
        evidence_rows = []  # Query bankability_evidence table
        
        result = await bankability_client.evaluate_for_persona(
            project_id=project_id,
            evidence_rows=evidence_rows,
            persona=persona.upper()
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/projects/{project_id}/evidence/{evidence_key}")
async def update_evidence(project_id: str, evidence_key: str, evidence_data: dict):
    """Update evidence status and re-evaluate bankability"""
    try:
        # TODO: Update database
        # TODO: Get all evidence for project
        evidence_rows = []
        
        # Evaluate bankability after update
        result = await bankability_client.evaluate(
            project_id=project_id,
            evidence_rows=evidence_rows
        )
        
        # TODO: Store snapshot in database
        # TODO: Emit event
        # TODO: Push via WebSocket
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/projects/{project_id}/bankability/executive")
async def get_executive_view(project_id: str):
    """Get executive multi-persona view"""
    try:
        evidence_rows = []  # Query database
        
        result = await bankability_client.evaluate_multi_persona(
            project_id=project_id,
            evidence_rows=evidence_rows,
            personas=["PRODUCER", "FINANCE", "REGULATOR", "EXECUTIVE"]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/bankability/health")
async def bankability_health():
    """Check bankability engine health"""
    return await bankability_client.health()
EOF