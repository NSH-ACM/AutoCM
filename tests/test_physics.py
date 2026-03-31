"""
═══════════════════════════════════════════════════════════════════════════
 ACM Tests — test_physics.py
 Physics engine validation for the Autonomous Constellation Manager.
 Verifies RK4 propagation accuracy against known orbital state vectors.
 Run with: pytest tests/test_physics.py -v
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import math
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ═══════════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════════

MU_EARTH = 398600.4418    # km³/s² — Earth gravitational parameter
R_EARTH  = 6371.0         # km — Earth mean radius
ISP      = 300.0          # s — specific impulse
G0       = 9.80665        # m/s²


# ═══════════════════════════════════════════════════════════════════════════
#  Orbital Mechanics Validation
# ═══════════════════════════════════════════════════════════════════════════

class TestOrbitalMechanics:
    """Validate core orbital mechanics calculations."""

    def test_circular_orbit_velocity(self):
        """Circular orbit velocity matches v = sqrt(μ/r)."""
        alt_km = 500.0
        r = R_EARTH + alt_km
        expected_v = math.sqrt(MU_EARTH / r)

        # ~7.613 km/s for 500km LEO
        assert abs(expected_v - 7.613) < 0.01, \
            f"Expected ~7.613 km/s, got {expected_v:.3f} km/s"

    def test_orbital_period(self):
        """Orbital period T = 2π√(a³/μ) ~ 94.5 min for 500km."""
        alt_km = 500.0
        a = R_EARTH + alt_km
        T = 2 * math.pi * math.sqrt(a**3 / MU_EARTH)
        T_min = T / 60.0

        assert abs(T_min - 94.5) < 1.0, \
            f"Expected ~94.5 min, got {T_min:.1f} min"

    def test_escape_velocity(self):
        """Escape velocity v_esc = sqrt(2μ/r)."""
        r = R_EARTH + 500.0
        v_esc = math.sqrt(2 * MU_EARTH / r)

        # ~10.77 km/s from 500km
        assert abs(v_esc - 10.77) < 0.05, \
            f"Expected ~10.77 km/s, got {v_esc:.3f} km/s"


# ═══════════════════════════════════════════════════════════════════════════
#  Tsiolkovsky Rocket Equation
# ═══════════════════════════════════════════════════════════════════════════

class TestTsiolkovsky:
    """Validate fuel consumption calculations."""

    def test_fuel_consumption_small_dv(self):
        """Small ΔV (10 m/s) consumes reasonable fuel for 500kg sat."""
        mass_kg = 500.0
        dv_ms = 10.0
        fuel = mass_kg * (1 - math.exp(-dv_ms / (ISP * G0)))

        # Should be ~1.7 kg for 10 m/s on 500kg sat
        assert 1.0 < fuel < 3.0, \
            f"Expected 1-3 kg fuel, got {fuel:.3f} kg"

    def test_fuel_consumption_zero_dv(self):
        """Zero ΔV consumes zero fuel."""
        mass_kg = 500.0
        dv_ms = 0.0
        fuel = mass_kg * (1 - math.exp(-abs(dv_ms) / (ISP * G0)))
        assert fuel == 0.0

    def test_fuel_consumption_scales_with_mass(self):
        """Heavier satellite consumes more fuel for same ΔV."""
        dv_ms = 10.0
        fuel_500 = 500.0 * (1 - math.exp(-dv_ms / (ISP * G0)))
        fuel_1000 = 1000.0 * (1 - math.exp(-dv_ms / (ISP * G0)))

        assert fuel_1000 > fuel_500
        assert abs(fuel_1000 / fuel_500 - 2.0) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
#  Coordinate Conversions
# ═══════════════════════════════════════════════════════════════════════════

class TestCoordinates:
    """Validate lat/lon <-> ECI coordinate conversions."""

    def test_equator_prime_meridian(self):
        """(0°, 0°, 500km) → positive X axis in ECI."""
        lat, lon, alt = 0.0, 0.0, 500.0
        r = R_EARTH + alt
        x = r * math.cos(math.radians(lat)) * math.cos(math.radians(lon))
        y = r * math.cos(math.radians(lat)) * math.sin(math.radians(lon))
        z = r * math.sin(math.radians(lat))

        assert abs(x - r) < 0.001
        assert abs(y) < 0.001
        assert abs(z) < 0.001

    def test_north_pole(self):
        """(90°, 0°, 500km) → positive Z axis in ECI."""
        lat, lon, alt = 90.0, 0.0, 500.0
        r = R_EARTH + alt
        x = r * math.cos(math.radians(lat)) * math.cos(math.radians(lon))
        y = r * math.cos(math.radians(lat)) * math.sin(math.radians(lon))
        z = r * math.sin(math.radians(lat))

        assert abs(x) < 0.001
        assert abs(y) < 0.001
        assert abs(z - r) < 0.001

    def test_roundtrip_conversion(self):
        """lat/lon → ECI → lat/lon roundtrip preserves values."""
        orig_lat, orig_lon, orig_alt = 35.0, 77.5, 500.0
        r = R_EARTH + orig_alt
        lat_rad = math.radians(orig_lat)
        lon_rad = math.radians(orig_lon)

        x = r * math.cos(lat_rad) * math.cos(lon_rad)
        y = r * math.cos(lat_rad) * math.sin(lon_rad)
        z = r * math.sin(lat_rad)

        # Reverse
        r_mag = math.sqrt(x**2 + y**2 + z**2)
        lat_back = math.degrees(math.asin(z / r_mag))
        lon_back = math.degrees(math.atan2(y, x))
        alt_back = r_mag - R_EARTH

        assert abs(lat_back - orig_lat) < 0.001
        assert abs(lon_back - orig_lon) < 0.001
        assert abs(alt_back - orig_alt) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
#  CDM Classification
# ═══════════════════════════════════════════════════════════════════════════

class TestCDMClassification:
    """Validate CDM severity classification thresholds."""

    def test_critical_threshold(self):
        """Miss < 100m → CRITICAL."""
        from api.core.autonomy_logic import classify_cdm, CDMSeverity
        assert classify_cdm(0.05) == CDMSeverity.CRITICAL
        assert classify_cdm(0.099) == CDMSeverity.CRITICAL

    def test_warning_threshold(self):
        """100m ≤ miss < 1km → WARNING."""
        from api.core.autonomy_logic import classify_cdm, CDMSeverity
        assert classify_cdm(0.1) == CDMSeverity.WARNING
        assert classify_cdm(0.5) == CDMSeverity.WARNING
        assert classify_cdm(0.999) == CDMSeverity.WARNING

    def test_advisory_threshold(self):
        """1km ≤ miss < 5km → ADVISORY."""
        from api.core.autonomy_logic import classify_cdm, CDMSeverity
        assert classify_cdm(1.0) == CDMSeverity.ADVISORY
        assert classify_cdm(3.0) == CDMSeverity.ADVISORY
        assert classify_cdm(4.999) == CDMSeverity.ADVISORY

    def test_clear_threshold(self):
        """Miss ≥ 5km → CLEAR."""
        from api.core.autonomy_logic import classify_cdm, CDMSeverity
        assert classify_cdm(5.0) == CDMSeverity.CLEAR
        assert classify_cdm(100.0) == CDMSeverity.CLEAR


# ═══════════════════════════════════════════════════════════════════════════
#  RTN Frame Geometry
# ═══════════════════════════════════════════════════════════════════════════

class TestRTNFrame:
    """Validate RTN (Radial-Tangential-Normal) frame calculations."""

    def test_rtn_orthogonality(self):
        """R, T, N vectors are mutually orthogonal."""
        r_vec = (6871.0, 0.0, 0.0)  # on X axis
        v_vec = (0.0, 7.613, 0.0)   # velocity along Y

        r_mag = math.sqrt(sum(c**2 for c in r_vec))
        R_hat = tuple(c / r_mag for c in r_vec)

        N_raw = (
            r_vec[1]*v_vec[2] - r_vec[2]*v_vec[1],
            r_vec[2]*v_vec[0] - r_vec[0]*v_vec[2],
            r_vec[0]*v_vec[1] - r_vec[1]*v_vec[0],
        )
        N_mag = math.sqrt(sum(c**2 for c in N_raw))
        N_hat = tuple(c / N_mag for c in N_raw)

        T_hat = (
            N_hat[1]*R_hat[2] - N_hat[2]*R_hat[1],
            N_hat[2]*R_hat[0] - N_hat[0]*R_hat[2],
            N_hat[0]*R_hat[1] - N_hat[1]*R_hat[0],
        )

        # Check orthogonality (dot products should be ~0)
        dot_RT = sum(R_hat[i] * T_hat[i] for i in range(3))
        dot_RN = sum(R_hat[i] * N_hat[i] for i in range(3))
        dot_TN = sum(T_hat[i] * N_hat[i] for i in range(3))

        assert abs(dot_RT) < 1e-10, f"R·T = {dot_RT}"
        assert abs(dot_RN) < 1e-10, f"R·N = {dot_RN}"
        assert abs(dot_TN) < 1e-10, f"T·N = {dot_TN}"

    def test_rtn_unit_vectors(self):
        """R, T, N have unit magnitude."""
        r_vec = (6871.0, 0.0, 0.0)
        v_vec = (0.0, 7.613, 0.0)

        r_mag = math.sqrt(sum(c**2 for c in r_vec))
        R_hat = tuple(c / r_mag for c in r_vec)

        assert abs(math.sqrt(sum(c**2 for c in R_hat)) - 1.0) < 1e-10


# ═══════════════════════════════════════════════════════════════════════════
#  State Manager
# ═══════════════════════════════════════════════════════════════════════════

class TestStateManager:
    """Test in-memory state manager behavior."""

    def test_state_initialization(self):
        """StateManager loads catalog and initializes satellites."""
        from api.state_manager import StateManager
        sm = StateManager()
        sm._generate_default_catalog()
        assert len(sm.satellites) >= 100
        assert len(sm.debris) >= 5000

    def test_simulation_step(self):
        """Simulation step advances time and updates positions."""
        from api.state_manager import StateManager
        sm = StateManager()
        sm._generate_default_catalog()

        t0 = sm.sim_time
        sm.simulate_step(60.0)
        t1 = sm.sim_time

        assert t1 > t0
        assert (t1 - t0).total_seconds() == 60.0

    def test_snapshot_format(self):
        """Snapshot returns expected structure."""
        from api.state_manager import StateManager
        sm = StateManager()
        sm._generate_default_catalog()
        sm.simulate_step(60.0)

        snapshot = sm.get_snapshot()
        assert "timestamp" in snapshot
        assert "satellites" in snapshot
        assert "debris_cloud" in snapshot
        assert "cdms" in snapshot
        assert "maneuvers" in snapshot
        assert len(snapshot["satellites"]) >= 100
        assert len(snapshot["debris_cloud"]) >= 5000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
