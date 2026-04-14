"""
═══════════════════════════════════════════════════════════════════════════
 ACM SERVICE — decision_service.py
 Autonomous Decision Engine (Intelligence Layer)
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import numpy as np

from ..models import Satellite, CDM, Maneuver, Vector3
from .maneuver_service import ManeuverService
from .fleet_service import FleetService

class DecisionService:
    """
    Analyzes CDMs and initiates autonomous evasion maneuvers.
    Implementation of Sections 5.1, 5.2, and 6 rulebook requirements.
    """

    def __init__(self, fleet: FleetService, maneuver: ManeuverService):
        self.fleet = fleet
        self.maneuver = maneuver
        
        # Risk Thresholds (Section 3.3 / 5.2)
        self.CRITICAL_DISTANCE_KM = 0.1 # 100m
        self.WARNING_DISTANCE_KM = 1.0  # 1km

    def process_cdms(self, cdms: List[CDM], sim_time: datetime) -> List[Dict]:
        """
        Processes a batch of CDMs and triggers evasions if thresholds are breached.
        """
        actions_taken = []
        
        # 1. Filter for Critical CDMs (Miss < 100m)
        critical_cdms = [c for c in cdms if c.missDistance < self.CRITICAL_DISTANCE_KM]
        
        # Group by satellite (one evasion per satellite per window)
        sats_to_evade = {}
        for cdm in critical_cdms:
            if cdm.satelliteId not in sats_to_evade:
                sats_to_evade[cdm.satelliteId] = cdm
            elif cdm.missDistance < sats_to_evade[cdm.satelliteId].missDistance:
                sats_to_evade[cdm.satelliteId] = cdm

        # 2. Planning
        for sat_id, cdm in sats_to_evade.items():
            sat = self.fleet.satellites.get(sat_id)
            if not sat or sat.status in ["EOL", "EVADING"]:
                continue
                
            # Plan burn for T-30 minutes (or T-15 if late)
            tca = cdm.tca
            burn_time = tca - timedelta(minutes=30)
            
            # If TCA is too close, skip autonomous (Manual intervention needed)
            if (burn_time - sim_time).total_seconds() < 0:
                continue

            # Compute RTN-frame evasion (Section 5)
            # Strategy: Prograde burn (standard for LEO evasion)
            dv_total_ms = 10.0 # 10 m/s default evasion
            
            # Transform to ECI based on current state (simplified assumption for now)
            # In v2, we compute the RTN vectors dynamically
            r_vec = sat.r.to_np()
            v_vec = sat.v.to_np()
            
            # Unit Transverse (Along-Track) = V / |V|
            t_hat = v_vec / np.linalg.norm(v_vec)
            dv_vec = t_hat * (dv_total_ms / 1000.0) # km/s
            
            burn = Maneuver(
                burn_id=f"AUTO-EVA-{cdm.debrisId}",
                satelliteId=sat_id,
                burnTime=burn_time,
                deltaV_vector=Vector3.from_np(dv_vec)
            )
            
            # Schedule
            res = self.maneuver.schedule_burns(sat_id, [burn], sat.fuel_kg)
            if res.get("status") == "SCHEDULED":
                sat.status = "EVADING"
                actions_taken.append({
                    "satellite_id": sat_id,
                    "type": "EVASION_TRIGGERED",
                    "tca": tca.isoformat(),
                    "maneuver_id": burn.burn_id
                })
        
        return actions_taken
