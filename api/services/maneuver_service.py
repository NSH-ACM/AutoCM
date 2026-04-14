"""
═══════════════════════════════════════════════════════════════════════════
 ACM SERVICE — maneuver_service.py
 Burn Scheduling and Validation
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from ..models import Maneuver, Satellite, Vector3
from ..core.navigation import Navigator
import numpy as np

class ManeuverService:
    """
    Manages the lifecycle of satellite maneuvers (Evasion and Recovery).
    """

    def __init__(self):
        self.navigator = Navigator()
        self.scheduled_burns: Dict[str, List[Maneuver]] = {} # sat_id -> sorted list of burns
        self.executed_burns: List[Maneuver] = []
        self.cooldown_tracker: Dict[str, datetime] = {} # sat_id -> last burn time

    def schedule_burns(self, sat_id: str, burns: List[Maneuver], current_fuel_kg: float) -> Dict:
        """
        Validates and schedules a sequence of burns.
        Checks: Fuel budget, Thruster cooldown (600s), and scheduling order.
        """
        if sat_id not in self.scheduled_burns:
            self.scheduled_burns[sat_id] = []
        
        results = {"scheduled": [], "failed": []}
        temp_fuel = current_fuel_kg
        
        # Sort incoming burns by time
        sorted_burns = sorted(burns, key=lambda b: b.burnTime)
        
        for burn in sorted_burns:
            # 1. Cooldown Check (600s = 10 mins)
            last_burn = self.cooldown_tracker.get(sat_id)
            if last_burn and (burn.burnTime - last_burn).total_seconds() < 600:
                results["failed"].append({"id": burn.burn_id, "reason": "Thruster cooldown violation (600s)"})
                continue
            
            # 2. Fuel Check
            # Using Navigator to compute cost based on dry mass + current fuel
            dv_mag = np.linalg.norm(burn.deltaV_vector.to_np()) * 1000.0 # to m/s
            fuel_cost = self.navigator.compute_fuel_cost(500.0 + temp_fuel, dv_mag)
            
            if fuel_cost > temp_fuel:
                results["failed"].append({"id": burn.burn_id, "reason": "Insufficient propellant"})
                continue
            
            # 3. ACK
            burn.fuel_cost_kg = fuel_cost
            self.scheduled_burns[sat_id].append(burn)
            self.cooldown_tracker[sat_id] = burn.burnTime
            temp_fuel -= fuel_cost
            results["scheduled"].append(burn.burn_id)

        # Re-sort schedule
        self.scheduled_burns[sat_id].sort(key=lambda b: b.burnTime)
        
        return results

    def get_pending_burns(self, sat_id: str, start_time: datetime, end_time: datetime) -> List[Maneuver]:
        """Returns burns occurring within a specific window."""
        if sat_id not in self.scheduled_burns:
            return []
            
        pending = [b for b in self.scheduled_burns[sat_id] if start_time <= b.burnTime < end_time]
        return pending

    def mark_executed(self, sat_id: str, burn_id: str):
        """Clean up schedule after execution."""
        if sat_id in self.scheduled_burns:
            self.scheduled_burns[sat_id] = [b for b in self.scheduled_burns[sat_id] if b.burn_id != burn_id]
