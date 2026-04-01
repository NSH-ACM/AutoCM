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
    burnTime: str  # ISO 8601 UTC - camelCase per spec Section 4.2
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
    Returns: status "SCHEDULED", nested validation object per spec Section 4.2
    """
    try:
        # Load ground stations if not already loaded
        if not state.ground_stations:
            state.load_ground_stations()

        # Get satellite
        sat = state.satellites.get(payload.satelliteId)
        if not sat:
            raise HTTPException(status_code=404, detail=f"Satellite {payload.satelliteId} not found")

        # Process each burn in sequence with full validation
        scheduled_burns = []
        failed_burns = []
        total_fuel_cost = 0.0

        for burn in payload.maneuver_sequence:
            # Parse burn time
            try:
                burn_time = datetime.fromisoformat(burn.burnTime.replace('Z', '+00:00'))
            except ValueError:
                failed_burns.append({
                    "burn_id": burn.burn_id,
                    "error": f"Invalid burnTime format: {burn.burnTime}"
                })
                continue

            # Validate maneuver against all constraints
            validation = state.validate_maneuver(
                sat_id=payload.satelliteId,
                burn_time=burn_time,
                delta_v=burn.deltaV_vector,
                check_cooldown=True
            )

            if validation["valid"]:
                # Schedule the burn
                state.record_burn(payload.satelliteId, burn_time)
                scheduled_burns.append({
                    "burn_id": burn.burn_id,
                    "burnTime": burn.burnTime,
                    "status": "SCHEDULED",
                    "fuel_cost_kg": validation["fuel_cost_kg"]
                })
                total_fuel_cost += validation["fuel_cost_kg"]
            else:
                failed_burns.append({
                    "burn_id": burn.burn_id,
                    "error": "; ".join(validation["errors"]),
                    "validation": validation
                })

        # Calculate projected mass
        projected_mass = max(0, sat.fuel_kg - total_fuel_cost) + 500.0  # 500kg dry mass

        # Return per spec Section 4.2 with nested validation object
        all_scheduled = len(failed_burns) == 0

        return {
            "status": "SCHEDULED" if all_scheduled else "REJECTED",
            "validation": {
                "ground_station_los": all(
                    b.get("validation", {}).get("ground_station_los", False)
                    for b in failed_burns
                ) if failed_burns else True,
                "sufficient_fuel": sat.fuel_kg >= total_fuel_cost,
                "projected_mass_remaining_kg": round(projected_mass, 3)
            },
            "scheduled_count": len(scheduled_burns),
            "failed_count": len(failed_burns),
            "scheduled_burns": scheduled_burns,
            "failed_burns": failed_burns
        }
    except HTTPException:
        raise
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
    Uses official debris IDs from catalog (Section 6.3)
    """
    try:
        snapshot = state.get_snapshot()

        # Convert debris to flattened tuples as required
        # Use official debris IDs from catalog, not generated DEB-XXXXX
        debris_cloud = []
        for deb in state.debris:
            # Format: [ID, lat, lon, alt] - using official catalog ID
            debris_cloud.append([deb.id, deb.lat, deb.lon, deb.alt_km])

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
