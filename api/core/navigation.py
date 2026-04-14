"""
═══════════════════════════════════════════════════════════════════════════
 ACM CORE — navigation.py
 RTN Frames and Propulsion Logic
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

import numpy as np
from typing import Dict, Tuple

# ── Propulsion Constants (Section 5.1) ────────────────────────────────────────
ISP_S = 300.0       # Specific Impulse (s)
G0_MS2 = 9.80665    # Standard Gravity (m/s^2)
M_DRY_KG = 500.0    # Dry Mass (kg)

class Navigator:
    """
    Handles orbital coordinate transforms (ECI <-> RTN) and maneuver math.
    """

    @staticmethod
    def get_rtn_matrix(r_eci: np.ndarray, v_eci: np.ndarray) -> np.ndarray:
        """
        Computes the rotation matrix R from ECI to RTN frame.
        R: Radial (along r)
        T: Transverse (v-component perpendicular to R, in orbital plane)
        N: Normal (perpendicular to orbital plane, r x v)
        """
        r_mag = np.linalg.norm(r_eci)
        if r_mag < 1e-9:
            return np.eye(3)

        # 1. Radial Unit Vector
        u_r = r_eci / r_mag

        # 2. Normal Unit Vector (Angular Momentum direction)
        h = np.cross(r_eci, v_eci)
        h_mag = np.linalg.norm(h)
        u_n = h / h_mag if h_mag > 1e-9 else np.array([0, 0, 1])

        # 3. Transverse Unit Vector (completes right-handed system)
        u_t = np.cross(u_n, u_r)

        # Matrix to transform ECI -> RTN is [u_r, u_t, u_n]^T
        return np.vstack([u_r, u_t, u_n])

    def eci_to_rtn(self, vec_eci: np.ndarray, r_eci: np.ndarray, v_eci: np.ndarray) -> np.ndarray:
        """Transforms a vector (like delta-v) from ECI to RTN."""
        m = self.get_rtn_matrix(r_eci, v_eci)
        return m @ vec_eci

    def rtn_to_eci(self, vec_rtn: np.ndarray, r_eci: np.ndarray, v_eci: np.ndarray) -> np.ndarray:
        """Transforms a vector (like delta-v) from RTN to ECI."""
        m = self.get_rtn_matrix(r_eci, v_eci)
        # Transformation from RTN -> ECI is just the transpose (inverse)
        return m.T @ vec_rtn

    @staticmethod
    def compute_fuel_cost(m_current_kg: float, dv_mag_ms: float) -> float:
        """
        Tsiolkovsky Rocket Equation (Section 5.1).
        Delta_m = m_cur * (1 - exp(-dv / (Isp * g0)))
        """
        return m_current_kg * (1.0 - np.exp(-abs(dv_mag_ms) / (ISP_S * G0_MS2)))

    def plan_evasion(self, r_eci: np.ndarray, v_eci: np.ndarray, strategy: str = "T+") -> np.ndarray:
        """
        Calculates a standard 10m/s evasion burn in RTN.
        Strategies:
            'T+': Prograde (most efficient for altitude change)
            'T-': Retrograde
            'N+': Normal (cross-track)
        """
        dv_rtn = np.zeros(3)
        dv_mag_kms = 0.010 # 10 m/s as required for standoff
        
        if strategy == "T+":
            dv_rtn[1] = dv_mag_kms
        elif strategy == "T-":
            dv_rtn[1] = -dv_mag_kms
        elif strategy == "R+":
            dv_rtn[0] = dv_mag_kms
            
        return self.rtn_to_eci(dv_rtn, r_eci, v_eci)
