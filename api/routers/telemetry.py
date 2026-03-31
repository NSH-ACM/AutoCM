from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from state_manager import state

router = APIRouter()

class TelemetryPayload(BaseModel):
    id: str
    position: Dict[str, float]
    velocity: Dict[str, float]

class ManeuverCommand(BaseModel):
    id: str
    delta_v: Dict[str, float]
    thrust_duration: float

@router.post("/telemetry")
async def ingest_telemetry(payload: TelemetryPayload):
    # Update the in-memory cache
    state.update_satellite(payload.id, payload.dict())
    return {"status": "success", "message": f"Telemetry updated for {payload.id}"}

@router.post("/command/maneuver")
async def command_maneuver(payload: ManeuverCommand):
    # Ensure satellite exists
    if not state.get_satellite(payload.id):
        raise HTTPException(status_code=404, detail="Satellite not found")
    
    # In a full system, this would queue a command to the physics engine/edge
    return {"status": "success", "message": f"Maneuver commanded for {payload.id}", "maneuver": payload.dict()}

@router.get("/state")
async def get_state():
    return {
        "satellites": state.get_all_satellites(),
        "debris": state.get_all_debris()
    }
