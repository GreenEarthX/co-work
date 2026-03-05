from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# In-memory storage
capacities_db = []

class CapacityCreate(BaseModel):
    project_name: str
    molecule: str
    capacity_mtpd: float
    start_date: str  # Changed from date to str
    end_date: Optional[str] = None  # Changed from date to str

@router.post("/", status_code=201)
async def create_capacity(capacity: CapacityCreate):
    """Create a new production capacity"""
    
    print(f"Received capacity data: {capacity.dict()}")  # Debug log
    
    new_capacity = {
        "id": str(uuid4()),
        "project_name": capacity.project_name,
        "molecule": capacity.molecule,
        "capacity_mtpd": capacity.capacity_mtpd,
        "start_date": capacity.start_date,
        "end_date": capacity.end_date,
        "created_at": datetime.now().isoformat()
    }
    
    capacities_db.append(new_capacity)
    
    print(f"Created capacity: {new_capacity}")  # Debug log
    
    return new_capacity

@router.get("/")
async def list_capacities():
    """List all capacities"""
    return {"capacities": capacities_db, "total": len(capacities_db)}

@router.get("/{capacity_id}")
async def get_capacity(capacity_id: str):
    """Get a specific capacity"""
    for cap in capacities_db:
        if cap["id"] == capacity_id:
            return cap
    raise HTTPException(status_code=404, detail="Capacity not found")

@router.delete("/{capacity_id}")
async def delete_capacity(capacity_id: str):
    """Delete a capacity"""
    global capacities_db
    capacities_db = [c for c in capacities_db if c["id"] != capacity_id]
    return {"message": "Capacity deleted"}