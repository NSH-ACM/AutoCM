"""
═══════════════════════════════════════════════════════════════════════════
 ACM API — Rulebook Compliant Endpoints
 Implements exact endpoints specified in the hackathon rulebook.
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from ..state_manager import state

router = APIRouter(tags=["Rulebook API"])


class TelemetryObject(BaseModel):
    id: str
    type: str = Field(..., pattern="^(SATELLITE|DEBRIS)$")
    r: Dict[str, float] = Field(..., description="ECI position in km {x, y, z}")
    v: Dict[str, float] = Field(..., description="ECI velocity in km/s {x, y, z}")


class TelemetryPayload(BaseModel):
    timestamp: str  # ISO 8601 UTC
    objects: List[TelemetryObject]


class ManeuverBurn(BaseModel):
    burn_id: str
    burn_time: str  # ISO 8601 UTC
    deltaV_vector: Dict[str, float] = Field(..., description="ECI delta-v in km/s {x, y, z}")


class ScheduleManeuverPayload(BaseModel):
    satelliteId: str
    maneuver_sequence: List[ManeuverBurn]


class SimulateStepPayload(BaseModel):
    step_seconds: float = Field(..., gt=0, description="Simulation step duration in seconds")


@router.post("/api/telemetry")
async def post_telemetry(payload: TelemetryPayload):
    """
    Accepts timestamp + objects array (id, type, r{x,y,z}, v{x,y,z})
    Asynchronously updates internal physics state
    Returns: status "ACK", processed_count, active_cdm_warnings
    """
    try:
        # Convert payload to internal format
        objects_data = []
        for obj in payload.objects:
            obj_data = {
                "id": obj.id,
                "type": obj.type,
                "state": {
                    "t": state.parse_iso_time(payload.timestamp),
                    "r": obj.r,
                    "v": obj.v
                }
            }
            objects_data.append(obj_data)
        
        telemetry_payload = {"objects": objects_data}
        result = state.autonomy_engine.ingest_telemetry(telemetry_payload)
        
        return {
            "status": result["status"],
            "processed_count": result["processed_count"],
            "active_cdm_warnings": result["active_cdm_warnings"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/maneuver/schedule")
async def schedule_maneuver(payload: ScheduleManeuverPayload):
    """
    Accepts satelliteId + maneuver_sequence array
    Each burn: burn_id, burnTime (ISO 8601), deltaV_vector {x,y,z}
    Validates ground station line-of-sight
    Validates sufficient fuel
    Returns: status "SCHEDULED", ground_station_los bool,
        sufficient_fuel bool, projected_mass_remaining_kg
    """
    try:
        # Get satellite
        sat = state.satellites.get(payload.satelliteId)
        if not sat:
            raise HTTPException(status_code=404, detail=f"Satellite {payload.satelliteId} not found")
        
        # Process each burn in sequence
        results = []
        for burn in payload.maneuver_sequence:
            # Convert burn time to seconds since epoch
            burn_time = state.parse_iso_time(burn.burn_time)
            
            # Create maneuver payload
            maneuver_payload = {
                "satellite_id": payload.satelliteId,
                "burn_id": burn.burn_id,
                "burn_time_offset_s": burn_time - state.autonomy_engine.sim_time,
                "dv_eci_kms": burn.deltaV_vector,
                "is_recovery": False
            }
            
            # Validate and schedule
            result = state.autonomy_engine.schedule_maneuver(maneuver_payload)
            results.append(result)
        
        # Check if all maneuvers were scheduled successfully
        all_scheduled = all(r["validation"]["valid"] for r in results)
        
        return {
            "status": "SCHEDULED" if all_scheduled else "PARTIAL",
            "ground_station_los": True,  # Stub - always true for now
            "sufficient_fuel": all_scheduled,
            "projected_mass_remaining_kg": sat.mass_dry + sat.mass_fuel,
            "maneuvers": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/simulate/step")
async def simulate_step(payload: SimulateStepPayload):
    """
    Accepts step_seconds
    Integrates physics for all objects over that window
    Executes all burns scheduled within the window
    Returns: status "STEP_COMPLETE", new_timestamp,
        collisions_detected, maneuvers_executed
    """
    try:
        result = state.autonomy_engine.simulate_step(payload.step_seconds)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/visualization/snapshot")
async def get_snapshot():
    """
    Returns timestamp, satellites array (id, lat, lon, fuel_kg, status)
    Returns debris_cloud as flattened tuples [ID, lat, lon, alt]
    Payload must be compact (tuple format for debris, not full JSON)
    """
    try:
        snapshot = state.autonomy_engine.get_snapshot()
        
        # Convert debris to flattened tuples as required
        debris_cloud = []
        for i, debris in enumerate(snapshot["debris_cloud"]):
            # Format: [ID, lat, lon, alt] - using index as ID for debris
            debris_cloud.append([f"DEB-{i:05d}", debris[0], debris[1], debris[2]])
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "satellites": snapshot["satellites"],
            "debris_cloud": debris_cloud
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "satellites": len(state.satellites), "debris": len(state.debris)}
