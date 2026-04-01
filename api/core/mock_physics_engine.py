"""
ACM — Mock Physics Engine
Python-based fallback for orbital mechanics and conjunction screening.
Provides simplified models for propagation and LOS checks.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

def propagate(objects: List[Dict], dt_seconds: float) -> List[Dict]:
    """Simple linear drift propagation for mock purposes."""
    updated = []
    for obj in objects:
        new_obj = obj.copy()
        r = obj["r"]
        v = obj["v"]
        
        # Simple r = r0 + v*dt
        new_r = {
            "x": r["x"] + v["x"] * dt_seconds,
            "y": r["y"] + v["y"] * dt_seconds,
            "z": r["z"] + v["z"] * dt_seconds
        }
        
        # In a real mock, we'd update v to keep it circular, 
        # but for a quick test, linear drift is fine.
        new_obj["r"] = new_r
        updated.append(new_obj)
    return updated

def detect_conjunctions(satellites: List[Dict], debris: List[Dict], 
                        lookahead_seconds: float, epoch_iso: Optional[str] = None) -> List[Dict]:
    """Simplified conjunction screening using distance at current epoch."""
    cdms = []
    for sat in satellites:
        for deb in debris:
            # Distance calculation
            dx = sat["r"]["x"] - deb["r"]["x"]
            dy = sat["r"]["y"] - deb["r"]["y"]
            dz = sat["r"]["z"] - deb["r"]["z"]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            
            if dist < 5.0: # 5km threshold
                cdms.append({
                    "satelliteId": sat["id"],
                    "debrisId": deb["id"],
                    "missDistance": round(dist, 3),
                    "probability": 0.001 if dist < 1.0 else 0.0001,
                    "tca": epoch_iso or datetime.now(timezone.utc).isoformat()
                })
    return cdms

def check_los(satellite: Dict, ground_stations: List[Dict], timestamp: str) -> bool:
    """Mock LOS check: always true for testing."""
    return True

def check_los_batch(satellites: List[Dict], ground_stations: List[Dict], timestamp: str) -> List[Dict]:
    """Mock batch LOS check."""
    return [{"id": s["id"], "visible": True, "max_elevation_deg": 45.0} for s in satellites]

def plan_evasion(satellite: Dict, debris: Dict) -> Optional[Dict]:
    """Mock evasion planning."""
    return {
        "deltaV_ECI": {"x": 0.005, "y": 0.002, "z": 0.0},
        "dvMagnitude_ms": 5.4,
        "fuelCostKg": 0.15,
        "strategy": "PROGRADE"
    }

def plan_recovery(evasion_dv: Dict, mass_kg: float) -> Dict:
    """Mock recovery planning."""
    return {
        "deltaV_ECI": {"x": -evasion_dv["x"], "y": -evasion_dv["y"], "z": -evasion_dv["z"]},
        "dvMagnitude_ms": 5.4,
        "fuelCostKg": 0.15
    }

def get_engine_stats() -> Dict:
    """Mock engine stats."""
    return {"mode": "MOCK", "objects_tracked": 0}
