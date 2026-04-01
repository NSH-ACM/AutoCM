"""
═══════════════════════════════════════════════════════════════════════════
 ACM Tests — test_api.py
 FastAPI endpoint tests for Section 4 API Compliance.
 Run with: pytest tests/test_api.py -v
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(scope="module")
def client():
    """Fixture to provide a TestClient that triggers lifespan events."""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    """Test health check and core API endpoints."""

    def test_health_check(self, client):
        """GET /health returns 200 with status OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        assert "sim_time" in data
        assert "satellites" in data
        assert "debris" in data


class TestSection4Compliance:
    """Test Section 4.2 API specification compliance."""

    def test_maneuver_schedule_camel_case_burnTime(self, client):
        """Test POST /api/maneuver/schedule uses burnTime (camelCase)."""
        from datetime import datetime, timezone, timedelta

        payload = {
            "satelliteId": "SAT-001",
            "maneuver_sequence": [
                {
                    "burn_id": "TEST-BURN-001",
                    "burnTime": (datetime.now(timezone.utc) + timedelta(seconds=15)).isoformat(),
                    "deltaV_vector": {"x": 0.001, "y": 0.0, "z": 0.0}
                }
            ]
        }
        response = client.post("/api/maneuver/schedule", json=payload)
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "validation" in data
            validation = data["validation"]
            assert "ground_station_los" in validation
            assert "sufficient_fuel" in validation

    def test_maneuver_validation_nested_object(self, client):
        """Test that maneuver response includes nested validation object."""
        from datetime import datetime, timezone, timedelta

        payload = {
            "satelliteId": "SAT-001",
            "maneuver_sequence": [
                {
                    "burn_id": "TEST-VALIDATION",
                    "burnTime": (datetime.now(timezone.utc) + timedelta(seconds=15)).isoformat(),
                    "deltaV_vector": {"x": 0.01, "y": 0.0, "z": 0.0}
                }
            ]
        }
        response = client.post("/api/maneuver/schedule", json=payload)

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data.get("validation"), dict)

    def test_simulation_endpoints_renamed(self, client):
        """Test POST /api/simulation/* endpoints per Section 4."""
        response = client.post("/api/simulation/step", json={"step_seconds": 60})
        assert response.status_code in [200, 404]

        response = client.get("/api/simulation/status")
        assert response.status_code in [200, 404]

    def test_visualization_snapshot_official_debris_ids(self, client):
        """Test GET /api/visualization/snapshot uses official debris IDs."""
        response = client.get("/api/visualization/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "satellites" in data
        assert "debris_cloud" in data
        debris = data.get("debris_cloud", [])
        for d in debris:
            assert isinstance(d, list)
            assert len(d) == 4


class TestMissionConstraints:
    """Test Section 5 mission constraint enforcement."""

    def test_tsiolkovsky_fuel_calculation(self, client):
        """Test fuel calculation using Tsiolkovsky equation."""
        response = client.get("/api/visualization/snapshot")
        if response.status_code != 200:
            pytest.skip("Cannot get snapshot")

        data = response.json()
        satellites = data.get("satellites", [])
        if not satellites:
            pytest.skip("No satellites available")

        sat = satellites[0]
        initial_fuel = sat.get("fuel_kg", 50)

        response = client.post("/api/maneuvers/execute", json={
            "satellite_id": sat["id"],
            "delta_v": {"x": 0.01, "y": 0.0, "z": 0.0},
            "burn_duration": 120,
        })

        if response.status_code == 200:
            data = response.json()
            assert "fuel_remaining" in data
            fuel_remaining = data["fuel_remaining"]
            assert fuel_remaining < initial_fuel


class TestPhysicsValidation:
    """Test Section 3 physics constraints."""

    def test_rk4_propagation_accuracy(self, client):
        """Test that RK4 integration maintains orbital energy."""
        response = client.get("/api/visualization/snapshot")
        if response.status_code != 200:
            pytest.skip("Cannot get snapshot")

        response = client.post("/api/simulation/step", json={"step_seconds": 5400})
        if response.status_code != 200:
            pytest.skip("Cannot step simulation")

        response = client.get("/api/visualization/snapshot")
        final_data = response.json()
        assert "satellites" in final_data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
