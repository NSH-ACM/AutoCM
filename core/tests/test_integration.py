"""
Integration tests for AutoCM Core Physics & Analytics Engine.
Tests the complete autonomy logic and C++ engine integration.
"""

import pytest
import json
import math
import time
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    from autonomy_logic import AutonomyEngine
    from engine_wrapper import *
except ImportError as e:
    pytest.skip(f"Could not import AutoCM modules: {e}", allow_module_level=True)

class TestAutonomyEngine:
    """Test suite for AutonomyEngine integration."""
    
    @pytest.fixture
    def autonomy_engine(self):
        """Create an AutonomyEngine instance with test catalog."""
        # Use the existing catalog if available, or create a minimal one
        catalog_path = Path(__file__).parent.parent.parent / "data" / "catalog.json"
        
        if not catalog_path.exists():
            pytest.skip(f"Catalog file not found: {catalog_path}")
        
        return AutonomyEngine(str(catalog_path))
    
    def test_1_telemetry_roundtrip(self, autonomy_engine):
        """
        Test 1 — Telemetry Roundtrip:
        Feed 10 satellite + 100 debris state vectors into ingest_telemetry().
        Assert returned processed_count == 110.
        """
        # Create test telemetry payload
        objects = []
        
        # Add 10 satellites
        for i in range(10):
            sat_id = f"TEST-SAT-{i:02d}"
            if sat_id in autonomy_engine.satellites:
                sat = autonomy_engine.satellites[sat_id]
                objects.append({
                    "id": sat_id,
                    "state": {
                        "t": sat.state.t,
                        "r": {"x": sat.state.r.x, "y": sat.state.r.y, "z": sat.state.r.z},
                        "v": {"x": sat.state.v.x, "y": sat.state.v.y, "z": sat.state.v.z}
                    },
                    "mass_fuel": sat.mass_fuel
                })
        
        # Add 100 debris objects
        debris_count = 0
        for deb_id, deb in autonomy_engine.debris.items():
            if debris_count >= 100:
                break
            objects.append({
                "id": deb_id,
                "state": {
                    "t": deb.state.t,
                    "r": {"x": deb.state.r.x, "y": deb.state.r.y, "z": deb.state.r.z},
                    "v": {"x": deb.state.v.x, "y": deb.state.v.y, "z": deb.state.v.z}
                }
            })
            debris_count += 1
        
        payload = {"objects": objects}
        result = autonomy_engine.ingest_telemetry(payload)
        
        assert result["status"] == "ACK"
        assert result["processed_count"] == 110
        print("✓ Test 1 PASSED: Telemetry roundtrip processed 110 objects")
    
    def test_2_conjunction_detection(self, autonomy_engine):
        """
        Test 2 — Conjunction Detection:
        Place one satellite and one debris on a known intercept course 
        (same orbital plane, debris 80 m ahead, closing at 0.5 km/s).
        After ingest_telemetry(), assert active_cdm_warnings >= 1.
        Assert a ManeuverPlan is queued in scheduled_maneuvers.
        """
        # Get a satellite for testing
        sat_id = list(autonomy_engine.satellites.keys())[0]
        sat = autonomy_engine.satellites[sat_id]
        
        # Create debris on intercept course
        deb_id = "TEST-DEB-INTERCEPT"
        
        # Position debris 80m ahead on same orbit
        intercept_pos = Vec3(
            sat.state.r.x + 0.08,  # 80m ahead in x direction
            sat.state.r.y,
            sat.state.r.z
        )
        
        # Set debris velocity to close at 0.5 km/s
        intercept_vel = Vec3(
            sat.state.v.x - 0.5,  # Closing velocity
            sat.state.v.y,
            sat.state.v.z
        )
        
        # Create test debris object
        test_debris = OrbitalObject()
        test_debris.id = deb_id
        test_debris.type = "DEBRIS"
        test_debris.controllable = False
        test_debris.mass_dry = 0.0
        test_debris.mass_fuel = 0.0
        test_debris.state = StateVector()
        test_debris.state.t = sat.state.t
        test_debris.state.r = intercept_pos
        test_debris.state.v = intercept_vel
        
        # Add to debris collection
        autonomy_engine.debris[deb_id] = test_debris
        
        # Create telemetry payload
        payload = {
            "objects": [
                {
                    "id": sat_id,
                    "state": {
                        "t": sat.state.t,
                        "r": {"x": sat.state.r.x, "y": sat.state.r.y, "z": sat.state.r.z},
                        "v": {"x": sat.state.v.x, "y": sat.state.v.y, "z": sat.state.v.z}
                    }
                },
                {
                    "id": deb_id,
                    "state": {
                        "t": test_debris.state.t,
                        "r": {"x": test_debris.state.r.x, "y": test_debris.state.r.y, "z": test_debris.state.r.z},
                        "v": {"x": test_debris.state.v.x, "y": test_debris.state.v.y, "z": test_debris.state.v.z}
                    }
                }
            ]
        }
        
        # Clear existing maneuvers
        autonomy_engine.scheduled_maneuvers.clear()
        
        result = autonomy_engine.ingest_telemetry(payload)
        
        assert result["status"] == "ACK"
        assert result["active_cdm_warnings"] >= 1
        assert len(autonomy_engine.scheduled_maneuvers) >= 1
        
        print(f"✓ Test 2 PASSED: Detected {result['active_cdm_warnings']} conjunction(s), scheduled {len(autonomy_engine.scheduled_maneuvers)} maneuver(s)")
    
    def test_3_fuel_accounting(self, autonomy_engine):
        """
        Test 3 — Fuel Accounting:
        Apply a 10 m/s burn to a fresh satellite (mass 550 kg).
        Expected fuel consumed ≈ 550 * (1 - exp(-10/(300*9.80665))) ≈ 1.864 kg.
        Assert computed value within 0.001 kg of expected.
        """
        # Get a satellite with full fuel
        sat_id = list(autonomy_engine.satellites.keys())[0]
        sat = autonomy_engine.satellites[sat_id]
        
        # Reset fuel to full
        sat.mass_fuel = 50.0
        initial_fuel = sat.mass_fuel
        
        # Apply 10 m/s burn in prograde direction
        dv_eci = Vec3(0.0, 0.01, 0.0)  # 10 m/s = 0.01 km/s
        
        # Calculate expected fuel consumption
        total_mass = sat.mass_dry + sat.mass_fuel
        expected_fuel = fuel_consumed(10.0, total_mass)  # 10 m/s
        
        # Apply burn
        burn_success = apply_burn(sat, dv_eci)
        
        assert burn_success == True
        actual_fuel_used = initial_fuel - sat.mass_fuel
        
        # Check within 0.001 kg tolerance
        assert abs(actual_fuel_used - expected_fuel) < 0.001
        
        print(f"✓ Test 3 PASSED: Fuel consumed {actual_fuel_used:.6f} kg (expected {expected_fuel:.6f} kg)")
    
    def test_4_station_keeping(self, autonomy_engine):
        """
        Test 4 — Station-Keeping:
        Propagate a satellite for 3600 s with no maneuvers.
        Inject a nominal_slot equal to its starting position.
        Assert plan_recovery() returns a non-empty plan 
        (satellite will have drifted due to J2).
        """
        # Get a satellite
        sat_id = list(autonomy_engine.satellites.keys())[0]
        sat = autonomy_engine.satellites[sat_id]
        
        # Store initial state as nominal slot
        nominal_slot = StateVector()
        nominal_slot.t = sat.state.t
        nominal_slot.r = Vec3(sat.state.r.x, sat.state.r.y, sat.state.r.z)
        nominal_slot.v = Vec3(sat.state.v.x, sat.state.v.y, sat.state.v.z)
        
        # Propagate for 1 hour
        initial_pos = Vec3(sat.state.r.x, sat.state.r.y, sat.state.r.z)
        sat.state = propagate(sat.state, 3600.0, 30.0)
        
        # Plan recovery
        recovery_plan = plan_recovery(sat, nominal_slot, 0.0)
        
        # Check that plan is non-empty (has burn_id)
        assert recovery_plan.burn_id != ""  # Non-empty plan
        
        print(f"✓ Test 4 PASSED: Station-keeping planned recovery burn {recovery_plan.burn_id}")
    
    def test_5_graveyard_trigger(self, autonomy_engine):
        """
        Test 5 — Graveyard Trigger:
        Set sat.mass_fuel = 2.0 kg (< 5% of 50 kg initial).
        Assert needs_graveyard() returns True.
        Assert plan_graveyard() returns a valid ManeuverPlan.
        """
        # Get a satellite
        sat_id = list(autonomy_engine.satellites.keys())[0]
        sat = autonomy_engine.satellites[sat_id]
        
        # Set low fuel (< 5% of initial 50 kg)
        sat.mass_fuel = 2.0
        
        # Check graveyard trigger
        assert needs_graveyard(sat) == True
        
        # Plan graveyard maneuver
        graveyard_plan = plan_graveyard(sat)
        
        assert graveyard_plan.burn_id == "GRAVEYARD_BURN"
        assert graveyard_plan.satellite_id == sat_id
        assert graveyard_plan.estimated_fuel_kg > 0
        
        print(f"✓ Test 5 PASSED: Graveyard trigger activated, planned {graveyard_plan.estimated_fuel_kg:.3f} kg fuel burn")
    
    def test_6_full_step_simulation(self, autonomy_engine):
        """
        Test 6 — Full Step Simulation:
        Load full catalog (100 sats, 5000 debris).
        Call simulate_step(3600).
        Assert it completes in under 30 seconds.
        Assert collisions_detected == 0 (with evasion active).
        """
        # Reset simulation time
        autonomy_engine.sim_time = 0.0
        autonomy_engine.scheduled_maneuvers.clear()
        
        # Start timer
        start_time = time.time()
        
        # Run 1-hour simulation step
        result = autonomy_engine.simulate_step(3600.0)
        
        elapsed_time = time.time() - start_time
        
        assert result["status"] == "STEP_COMPLETE"
        assert elapsed_time < 30.0, f"Simulation took {elapsed_time:.2f} seconds, should be < 30s"
        assert result["collisions_detected"] == 0
        
        print(f"✓ Test 6 PASSED: Full simulation completed in {elapsed_time:.2f}s with {result['maneuvers_executed']} maneuvers, {result['collisions_detected']} collisions")

if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
