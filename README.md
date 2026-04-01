# AutoCM — Autonomous Constellation Manager

**National Space Hackathon 2026**  
**Team:** Project AETHER  
**Event:** IIT Delhi National Space Hackathon

---

## Project Overview

AutoCM is a high-performance autonomous constellation management system designed for real-time debris avoidance and orbital slot maintenance in Low Earth Orbit (LEO). The system integrates a C++ physics engine with a Python FastAPI backend to deliver millisecond-latency conjunction detection and autonomous maneuver planning for 10,000+ orbital objects.

### Key Achievements

- **High-Fidelity Physics**: J2-perturbed RK4 orbital propagation (Section 3.2 compliant)
- **Real-Time Conjunction Detection**: KD-Tree optimized for 10,000+ objects with O(N log N) complexity
- **Rulebook-Compliant API**: Full Section 4.2 compliance with nested validation objects
- **Mission Constraints**: 10s signal delay, 600s thruster cooldown, 10km station-keeping (Section 5)
- **RTN-to-ECI Transformation**: Proper maneuver frame conversions for fuel-efficient burns

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoCM Architecture                       │
├─────────────────────────────────────────────────────────────┤
│  Frontend      │  Backend API        │  Physics Engine      │
│  (Dashboard)   │  (FastAPI)          │  (C++17)             │
├────────────────┼─────────────────────┼──────────────────────┤
│  - WebSocket   │  - /api/telemetry   │  - J2 Propagation    │
│  - CesiumJS    │  - /api/maneuver/*│  - RK4 Integration   │
│  - D3.js       │  - /api/simulation/*│  - KD-Tree Search   │
└────────────────┴─────────────────────┴──────────────────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Physics Engine | C++17 + pybind11 | J2/RK4 propagation, KD-Tree screening |
| API Backend | FastAPI (Python 3.13) | REST endpoints, WebSocket telemetry |
| Frontend | HTML5 + CesiumJS 1.114 | 3D orbital visualization |
| Deployment | Docker + Docker Compose | Containerized orchestration |

---

## Quick Start

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum, 8GB recommended

### Docker Deployment

```bash
# Clone the repository
git clone <repository-url>
cd AutoCM

# Build and deploy
docker compose up --build

# Access the application
# Dashboard: http://localhost:8000
# API Docs:  http://localhost:8000/docs
```

The C++ physics engine will be automatically compiled during the Docker build process.

### Manual Development Setup

```bash
# 1. Install Python dependencies
python -m pip install -r api/requirements.txt

# 2. Build C++ physics engine
cd engine
mkdir -p build && cd build
cmake ..
make -j4
cd ../..

# 3. Start the API server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Access dashboard at http://localhost:8000
```

---

## API Documentation

### Core Endpoints (Section 4 Compliant)

#### Telemetry Ingestion
```http
POST /api/satellites/telemetry
Content-Type: application/json

{
  "timestamp": "2026-03-12T08:30:00Z",
  "objects": [
    {
      "id": "SAT-001",
      "type": "satellite",
      "r": {"x": 6878.137, "y": 0.0, "z": 0.0},
      "v": {"x": 0.0, "y": 7.35, "z": 0.0}
    }
  ]
}
```

#### Maneuver Schedule
```http
POST /api/maneuver/schedule
Content-Type: application/json

{
  "satelliteId": "SAT-001",
  "maneuver_sequence": [
    {
      "burn_id": "B001",
      "burnTime": "2026-03-12T08:30:00Z",
      "deltaV_vector": {"x": 0.01, "y": 0.0, "z": 0.0}
    }
  ]
}

# Response
{
  "status": "SCHEDULED",
  "validation": {
    "ground_station_los": true,
    "sufficient_fuel": true,
    "projected_mass_remaining_kg": 547.2
  },
  "scheduled_count": 1,
  "failed_count": 0
}
```

#### Simulation Control
```http
POST /api/simulation/step
{
  "step_seconds": 60
}

GET /api/simulation/status

POST /api/simulation/run
POST /api/simulation/stop
```

#### Visualization Snapshot
```http
GET /api/visualization/snapshot

# Response
{
  "timestamp": "2026-03-12T08:30:00Z",
  "satellites": [...],
  "debris_cloud": [["DEB-001", 45.2, 120.5, 550.0], ...]
}
```

### WebSocket Endpoint

```
ws://localhost:8000/ws/telemetry
```

Real-time telemetry stream with 2-second update intervals.

---

## Physics Engine

### J2 Perturbation Model

The J2 acceleration accounts for Earth's equatorial bulge:

```
a_J2 = (3/2) * J2 * μ * R_E² / r⁵

J2 = 1.08263 × 10⁻³
μ = 398600.4418 km³/s²
R_E = 6378.137 km
```

### RK4 Integration

4th-order Runge-Kutta with O(dt⁴) global error:

```cpp
StateVector rk4_step(const StateVector& s, double dt) {
    // k1 = f(t, y)
    // k2 = f(t + dt/2, y + dt*k1/2)
    // k3 = f(t + dt/2, y + dt*k2/2)
    // k4 = f(t + dt, y + dt*k3)
    // y_{n+1} = y_n + (dt/6)*(k1 + 2k2 + 2k3 + k4)
}
```

### KD-Tree Conjunction Detection

| Metric | Performance |
|--------|-------------|
| Build Time | O(N log N) |
| Query Time | O(log N) |
| 10,000 Debris | < 2 ms |
| Full Assessment | < 10 ms |

---

## Mission Constraints

| Constraint | Value | Implementation |
|------------|-------|----------------|
| Uplink Latency | 10 seconds | API boundary enforcement |
| Thruster Cooldown | 600 seconds | Per-satellite tracking |
| Station-Keeping | ±10 km | 3D Euclidean distance |
| EOL Threshold | < 5% fuel | Autonomous graveyard |
| Miss Distance Alert | < 100 m | CRITICAL classification |
| Conjunction Threshold | < 5 km | WARNING classification |

---

## Testing

### Automated Tests

```bash
# Run API compliance tests
pytest tests/test_api.py -v

# Run physics validation tests
pytest tests/test_physics.py -v
```

### Manual Verification

```bash
# Deploy with docker-compose
docker compose up -d

# Inject test threat and verify autonomous response
node scripts/inject_threat.js --satellite SAT-001 --severity critical

# Monitor logs for evasion maneuver
docker compose logs -f api | grep "EVASION\|RECOVERY"
```

---

## Documentation

- **[TECHNICAL_REPORT.md](TECHNICAL_REPORT.md)**: Detailed J2/RK4 numerical methods, KD-Tree optimization, architecture diagrams
- **[API Reference](http://localhost:8000/docs)**: Interactive Swagger/OpenAPI documentation
- **[Problem Statement](docs/problem_statement.pdf)**: Original hackathon requirements

---

## Project Structure

```
AutoCM/
├── api/                    # FastAPI backend
│   ├── main.py            # API entry point
│   ├── state_manager.py   # Simulation state & RTN transforms
│   ├── engine_wrapper.py  # Python/C++ bridge
│   └── routers/           # API endpoint modules
├── core/                  # Autonomy logic
│   └── autonomy_logic.py  # Decision engine
├── engine/                # C++ physics core
│   ├── propagator.cpp     # J2 + RK4
│   ├── propagator.h
│   ├── conjunction.cpp    # KD-Tree
│   └── conjunction.h
├── tests/                 # Test suite
│   ├── test_api.py
│   └── test_physics.py
├── data/                  # Catalogs, ground stations
├── frontend/              # Dashboard
├── Dockerfile             # Container build
├── docker-compose.yml     # Deployment config
├── README.md              # This file
└── TECHNICAL_REPORT.md    # Detailed technical docs
```

---

## License

This project is developed for the **National Space Hackathon 2026**. All rights reserved by the Project AETHER team.

---

**Contact:** [Team Contact Information]  
**Repository:** [GitHub/Repository URL]  
**Demo Video:** [Demo Link]
