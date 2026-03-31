from fastapi.testclient import TestClient
from api.main import app
from api.state_manager import state

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Systems Orchestration API is running"}

def test_ingest_telemetry():
    payload = {
        "id": "SAT-001",
        "position": {"x": 1000.0, "y": 2000.0, "z": 3000.0},
        "velocity": {"vx": 7.0, "vy": 7.0, "vz": 7.0}
    }
    response = client.post("/api/v1/telemetry", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Check if state was updated
    assert state.get_satellite("SAT-001") == payload

def test_command_maneuver_not_found():
    payload = {
        "id": "NON-EXISTENT",
        "delta_v": {"vx": 1.0, "vy": 0.0, "vz": 0.0},
        "thrust_duration": 10.0
    }
    response = client.post("/api/v1/command/maneuver", json=payload)
    assert response.status_code == 404

def test_command_maneuver_success():
    # Insert SAT-002 first
    state.update_satellite("SAT-002", {"id": "SAT-002"})
    payload = {
        "id": "SAT-002",
        "delta_v": {"vx": 1.0, "vy": 0.0, "vz": 0.0},
        "thrust_duration": 10.0
    }
    response = client.post("/api/v1/command/maneuver", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
