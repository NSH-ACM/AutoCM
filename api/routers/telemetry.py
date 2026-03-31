"""
═══════════════════════════════════════════════════════════════════════════
 ACM API — Telemetry Router
 Telemetry ingestion and constellation status endpoints.
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from ..state_manager import state

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


class TelemetryPayload(BaseModel):
    satellite_id: str
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    alt_km: Optional[float] = Field(None, ge=0, le=2000)
    fuel_kg: Optional[float] = Field(None, ge=0)
    status: Optional[str] = Field(None, pattern="^(NOMINAL|EVADING|RECOVERING|EOL)$")


class BulkTelemetryPayload(BaseModel):
    entries: List[TelemetryPayload]


@router.post("/ingest")
async def ingest_telemetry(payload: TelemetryPayload):
    """Ingest telemetry data for a single satellite."""
    telemetry = {}
    updated = []
    for field_name in ["lat", "lon", "alt_km", "fuel_kg", "status"]:
        val = getattr(payload, field_name, None)
        if val is not None:
            telemetry[field_name] = val
            updated.append(field_name)

    if not telemetry:
        raise HTTPException(status_code=400, detail="No telemetry fields provided")

    success = state.ingest_telemetry(payload.satellite_id, telemetry)
    if not success:
        raise HTTPException(status_code=404, detail=f"Satellite {payload.satellite_id} not found")

    return {"status": "OK", "satellite_id": payload.satellite_id, "updated_fields": updated}


@router.post("/ingest/bulk")
async def ingest_bulk(payload: BulkTelemetryPayload):
    """Ingest telemetry for multiple satellites."""
    results, errors = [], []
    for entry in payload.entries:
        telemetry = {k: getattr(entry, k) for k in ["lat","lon","alt_km","fuel_kg","status"] if getattr(entry, k) is not None}
        if state.ingest_telemetry(entry.satellite_id, telemetry):
            results.append(entry.satellite_id)
        else:
            errors.append(entry.satellite_id)
    return {"status": "OK", "ingested": len(results), "failed": len(errors), "errors": errors}


@router.get("/satellite/{satellite_id}")
async def get_satellite(satellite_id: str):
    """Get current telemetry for a satellite."""
    sat = state.satellites.get(satellite_id)
    if not sat:
        raise HTTPException(status_code=404, detail=f"Satellite {satellite_id} not found")
    return {"satellite": sat.to_dict(), "eci_position": sat.r, "eci_velocity": sat.v}


@router.get("/constellation")
async def get_constellation():
    """Get constellation-wide statistics."""
    return state.get_stats()


@router.get("/cdms")
async def get_cdms():
    """Get active Conjunction Data Messages."""
    return {
        "cdms": [c.to_dict() for c in state.cdms],
        "count": len(state.cdms),
        "critical": len([c for c in state.cdms if c.missDistance < 0.1]),
    }
