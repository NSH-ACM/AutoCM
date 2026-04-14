"""
═══════════════════════════════════════════════════════════════════════════
 ACM CORE — physics.py
 Pure Python J2-aware RK4 Propagator
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

import numpy as np
from typing import Tuple, Dict

# ── Official Constants (Section 3.2) ──────────────────────────────────────────
MU = 398600.4418  # km^3/s^2 (Earth's Gravitational Parameter)
RE = 6378.137     # km (Earth's Equatorial Radius)
J2 = 1.08263e-3   # Earth's Oblateness Perturbation Constant

class J2RK4Propagator:
    """
    High-performance 4th-order Runge-Kutta integrator.
    Accounts for Earth's J2 perturbation which causes nodal regression
    and apsidal precession, essential for high-fidelity LEO simulation.
    """

    @staticmethod
    def get_accelerations(r: np.ndarray) -> np.ndarray:
        """
        Calculates the instantaneous acceleration vector [ax, ay, az].
        Includes Two-Body gravity and J2 perturbation.
        """
        r_mag = np.linalg.norm(r)
        if r_mag < 100.0:  # Surface/Center trap
            return np.zeros(3)

        # 1. Two-Body (Point Mass) Acceleration
        # a_2body = - (mu / r^3) * r
        a_2body = -MU * r / (r_mag**3)

        # 2. J2 Perturbation Acceleration (Section 3.2 formula)
        # factor = (3/2) * J2 * mu * RE^2 / r^5
        z_sq = r[2]**2
        r_sq = r_mag**2
        
        factor = (1.5 * J2 * MU * (RE**2)) / (r_mag**5)
        
        # J2 scaling terms
        j2_x = r[0] * (5 * (z_sq / r_sq) - 1)
        j2_y = r[1] * (5 * (z_sq / r_sq) - 1)
        j2_z = r[2] * (5 * (z_sq / r_sq) - 3)
        
        a_j2 = factor * np.array([j2_x, j2_y, j2_z])

        return a_2body + a_j2

    def _f(self, state: np.ndarray) -> np.ndarray:
        """State derivative function S' = f(S)."""
        # state = [x, y, z, vx, vy, vz]
        v = state[3:]
        a = self.get_accelerations(state[:3])
        return np.concatenate([v, a])

    def propagate(self, r: np.ndarray, v: np.ndarray, dt: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Integrate the state forward by dt seconds using RK4.
        """
        s = np.concatenate([r, v])
        
        k1 = self._f(s)
        k2 = self._f(s + 0.5 * dt * k1)
        k3 = self._f(s + 0.5 * dt * k2)
        k4 = self._f(s + dt * k3)
        
        s_next = s + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)
        
        return s_next[:3], s_next[3:]

    def batch_propagate(self, states: np.ndarray, dt: float) -> np.ndarray:
        """
        Propagate multiple objects at once for performance.
        Input states shape: (N, 6)
        """
        # Note: True vectorized RK4 is faster for large N, 
        # but simple map is safer for standard constellations.
        return np.array([self.propagate(s[:3], s[3:], dt) for s in states])

def eci_to_latlon(r: np.ndarray) -> Tuple[float, float, float]:
    """Convert ECI (km) to Lat (deg), Lon (deg), Alt (km)."""
    x, y, z = r
    r_mag = np.linalg.norm(r)
    
    lat = np.degrees(np.arcsin(z / r_mag)) if r_mag > 0 else 0
    lon = np.degrees(np.arctan2(y, x))
    alt = r_mag - RE
    
    return float(lat), float(lon), float(alt)

def latlon_to_eci(lat: float, lon: float, alt: float) -> np.ndarray:
    """Convert Lat (deg), Lon (deg), Alt (km) to ECI (km)."""
    r = RE + alt
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    
    x = r * np.cos(lat_rad) * np.cos(lon_rad)
    y = r * np.cos(lat_rad) * np.sin(lon_rad)
    z = r * np.sin(lat_rad)
    
    return np.array([x, y, z])
