"""
═══════════════════════════════════════════════════════════════════════════
 ACM SERVICE — simulation_service.py
 Main Orchestration and Physics Loop
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np

from ..core.physics import J2RK4Propagator
from .fleet_service import FleetService
from .conjunction_service import ConjunctionService
from .maneuver_service import ManeuverService
from .comms_service import CommsService

class SimulationService:
    """
    Heartbeat of the ACM. Orchestrates physics, logic, and maneuvers.
    """

    def __init__(self, fleet: FleetService, conj: ConjunctionService, 
                 maneuver: ManeuverService, comms: CommsService, decision: Any):
        self.fleet = fleet
        self.conj = conj
        self.maneuver = maneuver
        self.comms = comms
        self.decision = decision
        self.propagator = J2RK4Propagator()
        
        self.sim_time = datetime(2026, 3, 12, 8, 0, 0)
        self.running = False
        self.step_seconds = 60.0

    def step(self, dt: float) -> Dict[str, Any]:
        """
        Advances the entire constellation state by dt seconds.
        Performs: Propagation, Burn Execution, and Screening.
        """
        initial_time = self.sim_time
        target_time = initial_time + timedelta(seconds=dt)
        
        maneuvers_executed = 0
        collisions_detected = 0

        # ── 1. Propagate Satellites ──────────────────────────────────────────
        for sat_id, sat in self.fleet.satellites.items():
            if sat.status == "EOL": continue
            
            # Check for scheduled burns in this window
            pending = self.maneuver.get_pending_burns(sat_id, initial_time, target_time)
            
            # For simplicity in this 'step', we propagate to the burn time, 
            # apply burn, then propagate the rest of the window.
            # (In a real high-fidelity sim, we'd handle multiple burns per step).
            
            curr_r = sat.r.to_np()
            curr_v = sat.v.to_np()
            
            if pending:
                for burn in pending:
                    # Time from step start to burn
                    dt_to_burn = (burn.burnTime - initial_time).total_seconds()
                    
                    # Propagate to burn point
                    if dt_to_burn > 0:
                        curr_r, curr_v = self.propagator.propagate(curr_r, curr_v, dt_to_burn)
                    
                    # Apply IMPULSIVE burn (Section 5.1)
                    dv = burn.deltaV_vector.to_np()
                    curr_v += dv
                    
                    # Deduct fuel
                    self.fleet.deduct_fuel(sat_id, burn.fuel_cost_kg)
                    self.maneuver.mark_executed(sat_id, burn.burn_id)
                    maneuvers_executed += 1
                    
                    # Reset 'initial' for the remaining part of the window
                    window_rem = dt - dt_to_burn
                    if window_rem > 0:
                        curr_r, curr_v = self.propagator.propagate(curr_r, curr_v, window_rem)
            else:
                # Standard propagation for full window
                curr_r, curr_v = self.propagator.propagate(curr_r, curr_v, dt)

            # Update Registry
            self.fleet.update_satellite_state(sat_id, curr_r, curr_v)

        # ── 2. Propagate Debris ──────────────────────────────────────────────
        for deb_id, deb in self.fleet.debris.items():
            curr_r = deb.r.to_np()
            curr_v = deb.v.to_np()
            
            # Use same J2 propagator for consistency (v2 Goal)
            new_r, new_v = self.propagator.propagate(curr_r, curr_v, dt)
            
            # Update debris registry (flat update)
            from ..core.physics import eci_to_latlon
            deb.r.x, deb.r.y, deb.r.z = new_r
            deb.v.x, deb.v.y, deb.v.z = new_v
            deb.lat, deb.lon, deb.alt_km = eci_to_latlon(new_r)

        # ── 3. Screen for Conjunctions ───────────────────────────────────────
        sats = list(self.fleet.satellites.values())
        debs = list(self.fleet.debris.values())
        self.conj.screen_fleet(sats, debs, target_time)
        
        # Check for immediate collisions (Section 3.3)
        for cdm in self.conj.active_cdms:
            if cdm.missDistance < 0.1: # 100m
                collisions_detected += 1

        self.sim_time = target_time
        
        # ── 4. Autonomous Intelligence ───────────────────────────────────────
        if self.decision:
            self.decision.process_cdms(self.conj.active_cdms, self.sim_time)
        
        return {
            "status": "STEP_COMPLETE",
            "new_timestamp": self.sim_time.isoformat(),
            "collisions_detected": collisions_detected,
            "maneuvers_executed": maneuvers_executed
        }
