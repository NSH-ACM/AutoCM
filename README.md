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

The fastest way to deploy the orchestration servers and mission control dashboard is via Docker. 

```bash
docker compose up --build
```
*This command seamlessly builds the C++ physics core into a multi-staged Alpine/Ubuntu sequence, sets up the Python environment, spins up the socket connections, and statically serves the entire dashboard.*

After the server spins up, navigate to `http://localhost:8001` to access Mission Control.

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

- **State Model Details:** Refer to `api/state_manager.py` for exact data contracts regarding satellite status and telemetry schemas.
- **REST Endpoints:** The API provides Swagger OpenAPI definitions live at `http://localhost:8001/docs`. 
- **Conjunction Strategy:** Consult `api/core/autonomy_logic.py` for the severity classification models triggering the autonomous evassion subroutines.
