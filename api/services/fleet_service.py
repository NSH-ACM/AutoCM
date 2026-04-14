"""
═══════════════════════════════════════════════════════════════════════════
 ACM SERVICE — fleet_service.py
 Registry for Satellites and Debris
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

from typing import Dict, List, Optional
from ..models import Satellite, Debris, Vector3
from ..core.physics import eci_to_latlon, latlon_to_eci
import numpy as np

class FleetService:
    """
    Manages the in-memory collection of all orbital objects.
    """

    def __init__(self):
        self.satellites: Dict[str, Satellite] = {}
        self.debris: Dict[str, Debris] = {}

    def add_satellite(self, sat: Satellite):
        self.satellites[sat.id] = sat

    def add_debris(self, deb: Debris):
        self.debris[deb.id] = deb

    def update_satellite_state(self, sat_id: str, r: np.ndarray, v: np.ndarray):
        """Updates internal state and converts back to Geodetic for UI."""
        if sat_id in self.satellites:
            sat = self.satellites[sat_id]
            sat.r = Vector3.from_np(r)
            sat.v = Vector3.from_np(v)
            
            lat, lon, alt = eci_to_latlon(r)
            sat.lat = lat
            sat.lon = lon
            sat.alt_km = alt

    def get_satellites_list(self) -> List[Dict]:
        return [s.model_dump() for s in self.satellites.values()]

    def get_debris_snapshot(self) -> List[List]:
        """Returns flattened [ID, lat, lon, alt] as required by Section 6.3."""
        return [
            [d.id, d.lat, d.lon, d.alt_km] 
            for d in self.debris.values()
        ]

    def deduct_fuel(self, sat_id: str, amount_kg: float):
        if sat_id in self.satellites:
            self.satellites[sat_id].fuel_kg = max(0.0, self.satellites[sat_id].fuel_kg - amount_kg)
            if self.satellites[sat_id].fuel_kg < 2.5: # 5% EOL threshold
                self.satellites[sat_id].status = "EOL"
