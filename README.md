# AutoCM v2 — Autonomous Constellation Manager

**National Space Hackathon 2026**

---

## Project Overview

AutoCM v2 is a high-performance, **Pure Python** autonomous constellation management system. It has been re-architected for maximum reliability and maintainability without sacrificing the millisecond-latency performance required for real-time debris avoidance in Low Earth Orbit (LEO). 

The system utilizes a J2-aware RK4 propagator and `cKDTree`-optimized proximity screening to manage 10,000+ orbital objects with high fidelity and zero C++ build complexity.

### Key Achievements

- **Pure Python Performance**: High-fidelity orbital mechanics powered by `numpy` and `scipy`.
- **J2-Aware Propagator**: 4th-order Runge-Kutta (RK4) integration accounting for Earth's oblateness (Section 3.2).
- **Sub-10ms Screening**: `scipy.spatial.cKDTree` proximity queries handle 10k+ debris objects at O(N log N) complexity.
- **Service-Oriented Architecture**: Modular backend with specialized services for Fleet, Maneuvers, Comms, and Conjunctions.
- **Mission Control Dashboard**: Premium D3.js visualization with high-fidelity orbit trails, dynamic terminators, and Gantt-style maneuver tracking.
- **Zero-Build Deployment**: Docker-native deployment on Ubuntu 22.04 with zero external build dependencies.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoCM v2 Architecture                   │
├─────────────────────────────────────────────────────────────┤
│  Frontend      │  Backend Services   │  Physics Engine      │
│  (Mission Ctrl)│  (FastAPI)          │  (Numpy/Scipy)       │
├────────────────┼─────────────────────┼──────────────────────┤
│  - D3.js Map   │  - Fleet Control    │  - J2 RK4 Propagator │
│  - Gantt Chart │  - Maneuver Valid.  │  - RTN Navigation    │
│  - WebSocket   │  - Comms (LOS)      │  - KD-Tree Screening │
└────────────────┴─────────────────────┴──────────────────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Core Mechanics | Python 3.11 + Scipy | J2/RK4 propagation, KD-Tree screening |
| API Backend | FastAPI | Service-oriented REST & WebSocket |
| Dashboard | D3.js + HTML5/CSS3 | High-fidelity Mission Control UI |
| Deployment | Docker (Ubuntu 22.04) | Hackathon-compliant orchestration |

---

## Quick Start (Zero Build)

### Prerequisites

- Docker Engine 24.0+
- Docker Compose 2.0+

### Docker Deployment

```bash
# Clone the repository
git clone <repository-url>
cd AutoCM

# Deploy instantly
docker compose up --build

# Reach Mission Control
# Dashboard: http://localhost:8000
# API Docs:  http://localhost:8000/docs
```

---

## API Documentation (Section 4 Compliant)

### Telemetry Ingestion (Section 4.1)
Accepts high-frequency state vectors and triggers real-time conjunction screening.
```http
POST /api/satellites/telemetry
```

### Maneuver Schedule (Section 4.2)
Validates burns against fuel mass, 600s thruster cooldown, and 10s command latency.
```http
POST /api/maneuver/schedule
```

### Simulation Control (Section 4.3)
Step or continuous execution with J2 propagation windowing.
```http
POST /api/simulation/step
```

---

## Physics & Autonomy

### J2 Perturbation Model
Propagates state by accounting for the $J_2$ zonal harmonic, essential for modeling nodal regression and perigee shift in LEO.

### RTN Navigation
All maneuevers are planned in the **Radial-Transverse-Normal (RTN)** local frame and transformed to ECI for execution, ensuring optimal fuel utilization for station-keeping.

### Mission Constraints
| Constraint | Spec | Enforcement |
|------------|-------|-------------|
| Command Latency | 10s | WebSocket/API timestamp validation |
| Thruster Cooldown | 600s | Dedicated `ManeuverService` tracker |
| Comms LOS | Elevation Mask | `CommsService` geometric check |
| Fuel Model | Tsiolkovsky | Propellant mass depletion logic |

---

## Project Structure

```
AutoCM/
├── api/                    # FastAPI Core
│   ├── main.py            # Entry point
│   ├── state_manager.py   # System Facade
│   ├── models.py          # Pydantic Schemas
│   ├── services/          # Modular logic (Fleet, Comms, Sim)
│   └── core/              # Physics (Propagators, Screeners)
├── data/                  # Static Catalogs & GS Database
├── frontend/              # D3.js Visualization layer
├── tests/                 # Compliance test suite
├── Dockerfile             # Ubuntu 22.04 base
└── README.md              # This file
```

---

## License

Developed for the **National Space Hackathon 2026**.
