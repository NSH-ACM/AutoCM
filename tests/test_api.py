"""
═══════════════════════════════════════════════════════════════════════════
 ACM Tests — test_api.py
 FastAPI endpoint tests for the Autonomous Constellation Manager.
 Run with: pytest tests/test_api.py -v
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
#  Health & Core Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthEndpoints:
    """Test health check and core API endpoints."""

    def test_health_check(self):
        """GET /health returns 200 with status OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        assert "sim_time" in data
        assert "satellites" in data
        assert "debris" in data

    def test_snapshot(self):
        """GET /api/visualization/snapshot returns full state."""
        response = client.get("/api/visualization/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "satellites" in data
        assert "debris_cloud" in data
        assert "cdms" in data
        assert "maneuvers" in data
        assert len(data["satellites"]) > 0

    def test_constellation_stats(self):
        """GET /api/constellation/stats returns statistics."""
        response = client.get("/api/constellation/stats")
        assert response.status_code == 200
        data = response.json()
        assert "satellites" in data
        assert "fuel" in data
        assert "conjunctions" in data
        assert "maneuvers" in data
        assert data["satellites"]["total"] > 0


# ═══════════════════════════════════════════════════════════════════════════
#  Telemetry Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestTelemetryEndpoints:
    """Test telemetry ingestion and query endpoints."""

    def test_get_constellation_telemetry(self):
        """GET /api/telemetry/constellation returns stats."""
        response = client.get("/api/telemetry/constellation")
        assert response.status_code == 200
        data = response.json()
        assert data["satellites"]["total"] > 0

    def test_get_satellite_telemetry(self):
        """GET /api/telemetry/satellite/{id} returns satellite data."""
        # First get a valid sat ID
        snapshot = client.get("/api/visualization/snapshot").json()
        sat_id = snapshot["satellites"][0]["id"]

        response = client.get(f"/api/telemetry/satellite/{sat_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["satellite"]["id"] == sat_id
        assert "eci_position" in data
        assert "eci_velocity" in data

    def test_get_satellite_not_found(self):
        """GET /api/telemetry/satellite/INVALID returns 404."""
        response = client.get("/api/telemetry/satellite/SAT-INVALID-99")
        assert response.status_code == 404

    def test_ingest_telemetry(self):
        """POST /api/telemetry/ingest updates satellite state."""
        snapshot = client.get("/api/visualization/snapshot").json()
        sat_id = snapshot["satellites"][0]["id"]

        response = client.post("/api/telemetry/ingest", json={
            "satellite_id": sat_id,
            "lat": 25.0,
            "lon": 80.0,
            "fuel_kg": 45.0,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        assert "lat" in data["updated_fields"]
        assert "lon" in data["updated_fields"]
        assert "fuel_kg" in data["updated_fields"]

    def test_ingest_telemetry_invalid_satellite(self):
        """POST /api/telemetry/ingest with invalid satellite returns 404."""
        response = client.post("/api/telemetry/ingest", json={
            "satellite_id": "SAT-NONEXISTENT-00",
            "lat": 10.0,
        })
        assert response.status_code == 404

    def test_ingest_telemetry_no_fields(self):
        """POST /api/telemetry/ingest with no fields returns 400."""
        snapshot = client.get("/api/visualization/snapshot").json()
        sat_id = snapshot["satellites"][0]["id"]

        response = client.post("/api/telemetry/ingest", json={
            "satellite_id": sat_id,
        })
        assert response.status_code == 400

    def test_get_cdms(self):
        """GET /api/telemetry/cdms returns CDM list."""
        # First run a simulation step to generate CDMs
        client.post("/api/simulate/step", json={"step_seconds": 60})

        response = client.get("/api/telemetry/cdms")
        assert response.status_code == 200
        data = response.json()
        assert "cdms" in data
        assert "count" in data
        assert "critical" in data


# ═══════════════════════════════════════════════════════════════════════════
#  Maneuver Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestManeuverEndpoints:
    """Test maneuver command endpoints."""

    def test_execute_maneuver(self):
        """POST /api/maneuvers/execute applies delta-V."""
        snapshot = client.get("/api/visualization/snapshot").json()
        # Find a NOMINAL satellite
        sat = next((s for s in snapshot["satellites"] if s["status"] == "NOMINAL"), None)
        assert sat is not None, "No NOMINAL satellite found"

        response = client.post("/api/maneuvers/execute", json={
            "satellite_id": sat["id"],
            "delta_v": {"x": 0.001, "y": 0.0, "z": 0.0},
            "burn_duration": 120,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        assert "fuel_remaining" in data

    def test_execute_maneuver_eol_satellite(self):
        """POST /api/maneuvers/execute on EOL satellite returns 400."""
        snapshot = client.get("/api/visualization/snapshot").json()
        eol_sat = next((s for s in snapshot["satellites"] if s["status"] == "EOL"), None)
        if eol_sat is None:
            pytest.skip("No EOL satellite in test data")

        response = client.post("/api/maneuvers/execute", json={
            "satellite_id": eol_sat["id"],
            "delta_v": {"x": 0.001, "y": 0.0, "z": 0.0},
            "burn_duration": 120,
        })
        assert response.status_code == 400

    def test_schedule_evasion(self):
        """POST /api/maneuvers/schedule-evasion plans an evasion burn."""
        snapshot = client.get("/api/visualization/snapshot").json()
        sat = next((s for s in snapshot["satellites"] if s["status"] == "NOMINAL"), None)
        assert sat is not None

        response = client.post("/api/maneuvers/schedule-evasion", json={
            "satellite_id": sat["id"],
            "strategy": "PROGRADE",
            "dv_magnitude_ms": 5.0,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "PROGRADE"
        assert data["dv_magnitude_ms"] == 5.0

    def test_maneuver_history(self):
        """GET /api/maneuvers/history returns maneuver records."""
        response = client.get("/api/maneuvers/history")
        assert response.status_code == 200
        data = response.json()
        assert "maneuvers" in data
        assert "total_dv_ms" in data


# ═══════════════════════════════════════════════════════════════════════════
#  Simulation Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulationEndpoints:
    """Test simulation control endpoints."""

    def test_simulate_step(self):
        """POST /api/simulate/step advances simulation."""
        response = client.post("/api/simulate/step", json={"step_seconds": 60})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        assert "sim_time" in data

    def test_simulation_status(self):
        """GET /api/simulate/status returns sim state."""
        response = client.get("/api/simulate/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "sim_time" in data

    def test_start_stop_simulation(self):
        """POST /api/simulate/run and /stop toggle simulation."""
        response = client.post("/api/simulate/run", json={
            "step_seconds": 30,
            "real_interval_ms": 2000,
        })
        assert response.status_code == 200
        assert response.json()["running"] is True

        response = client.post("/api/simulate/stop")
        assert response.status_code == 200
        assert response.json()["running"] is False


# ═══════════════════════════════════════════════════════════════════════════
#  Alerts Endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestAlertEndpoints:
    """Test alert feed endpoints."""

    def test_get_alerts(self):
        """GET /api/alerts returns alert list."""
        response = client.get("/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "latest_id" in data

    def test_get_alerts_since(self):
        """GET /api/alerts?after=0 returns all alerts."""
        response = client.get("/api/alerts?after=0")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  Dashboard Serving
# ═══════════════════════════════════════════════════════════════════════════

class TestDashboard:
    """Test dashboard static file serving."""

    def test_serve_dashboard(self):
        """GET / serves the dashboard HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
