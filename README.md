# AutoCM — Autonomous Constellation Manager

**National Space Hackathon 2026**
**Team:** Project AETHER
**Component:** Systems Orchestration & Interactive Dashboard (Person B)

AutoCM is a real-time, high-fidelity mission control orchestrator designed to autonomously manage large-scale satellite constellations in low-earth orbit continuously threatened by space debris. 

## Features
- **High-Performance Physics Engine:** C++17 based backend with `pybind11` integration. Includes RK4 orbital propagators and precise conjunction miss-distance algorithms.
- **Microservice Orchestration:** A single powerful FastAPI instance that caches in-memory constellation telemetry and executes RTN-frame autonomous evasion maneuvers.
- **Real-Time Data Streams:** WebSocket `/ws/telemetry` pushes seamless live updates to the frontend at ~10ms hardware latency.
- **Glassmorphic UX Dashboard:** Vanilla ES6 frontend utilizing built-in CesiumJS (1.114) for 3D globe visualization and D3.js radar mappings for conjunction threat assessments.

## Quick Start (Docker)

The application is fully containerized and strictly adheres to the **National Space Hackathon 2026** deployment requirements.

```bash
docker compose up --build
```
*This command compiles the C++ physics core (J2/RK4), initializes the FastAPI backend, and serves the "Orbital Insight" visualizer.*

After deployment, the API is accessible at `http://localhost:8000`.
The Mission Control Dashboard is available at `http://localhost:8000/dashboard` (or per your frontend routing).

## Local Development (Without Docker)

If you'd like to work directly on the source or run the simulation tests:

**1. Install Python Dependencies**
```bash
python -m pip install -r api/requirements.txt
```

**2. Compile C++ Engine (Optional)**
```bash
cd engine
mkdir build && cd build
cmake ..
make -j4
```
*If skipping compilation, the API will gracefully fall back to native slow Python approximations (MOCK_PY).*

**3. Boot System Orchestrator**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```
Navigate your browser to `http://localhost:8001`.

## Documentation

Detailed technical documentation is available in the repository:
- **[TECHNICAL_REPORT.md](TECHNICAL_REPORT.md)**: Deep dive into J2/RK4 numerical methods and KD-Tree spatial optimization.
- **REST Endpoints**: Swagger OpenAPI definitions are available live at `http://localhost:8000/docs`.
- **Conjunction Strategy**: See `api/autonomy_logic.py` for risk-assessment and decision models.

## API Compliance (Section 4)
- `POST /api/telemetry`: High-frequency state vector ingestion.
- `POST /api/maneuver/schedule`: Autonomous burn sequence scheduling.
- `POST /api/simulate/step`: High-fidelity physics integration "tick".
- `GET /api/visualization/snapshot`: Optimized situational awareness data.
