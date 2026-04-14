"""
═══════════════════════════════════════════════════════════════════════════
 ACM SERVICE — comms_service.py
 Ground Station Line-of-Sight (LOS)
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from ..core.physics import latlon_to_eci, RE

class CommsService:
    """
    Handles communication constraints between ground and fleet.
    """

    def __init__(self, ground_stations_path: str):
        self.stations = self._load_stations(ground_stations_path)

    def _load_stations(self, path: str) -> List[Dict]:
        try:
            df = pd.read_csv(path)
            stations = []
            for _, row in df.iterrows():
                # Correct for potential CSV header mismatches
                lat = row.get('latitude_deg', row.get('Latitude', 0.0))
                lon = row.get('longitude_deg', row.get('Longitude', 0.0))
                alt = row.get('elevation_m', row.get('Elevation_m', 0.0)) / 1000.0 # to km
                mask = row.get('min_elevation_angle_deg', row.get('Min_Elevation_Angle_deg', 5.0))
                
                stations.append({
                    "name": row['name' if 'name' in row else 'Station_Name'],
                    "r_eci": latlon_to_eci(lat, lon, alt),
                    "min_el": mask
                })
            return stations
        except Exception as e:
            print(f"[CommsService] Warning: Failed to load stations from {path}: {e}")
            return []

    def has_los(self, sat_r_eci: np.ndarray) -> bool:
        """
        Check if the satellite has line-of-sight to ANY ground station.
        Based on geometric visibility and elevation mask.
        """
        if not self.stations:
            return True # Fallback if no stations loaded

        sat_mag = np.linalg.norm(sat_r_eci)
        if sat_mag < RE: return False

        for gs in self.stations:
            gs_r = gs['r_eci']
            
            # Vector from Ground Station to Satellite
            rho = sat_r_eci - gs_r
            rho_mag = np.linalg.norm(rho)
            
            # Unit vectors
            u_gs = gs_r / np.linalg.norm(gs_r)
            u_rho = rho / rho_mag
            
            # Elevation Angle = 90 - angle between station zenith and rho
            # cos(theta) = u_gs . u_rho
            cos_zenith = np.dot(u_gs, u_rho)
            elev_angle = 90.0 - np.degrees(np.arccos(np.clip(cos_zenith, -1.0, 1.0)))
            
            if elev_angle >= gs['min_el']:
                return True
                
        return False
