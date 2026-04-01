"""
═══════════════════════════════════════════════════════════════════════════
 ACM API — main.py
 FastAPI entry point with WebSocket support for real-time telemetry.
 National Space Hackathon 2026

 Run with:  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .state_manager import state
from .routers.telemetry import router as telemetry_router
from .routers.maneuvers import router as maneuvers_router
from .routers.rulebook_api import router as rulebook_router


# ═══════════════════════════════════════════════════════════════════════════
#  Application Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load catalog and begin simulation loop."""
    print("═" * 70)
    print("  AUTONOMOUS CONSTELLATION MANAGER — FastAPI Backend")
    print("  National Space Hackathon 2026")
    print("═" * 70)

    # Load satellite & debris catalog
    catalog_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "catalog.json"
    )
    state.load_catalog(catalog_path)

    # Start background simulation loop
    sim_task = asyncio.create_task(_simulation_loop())
    ws_task = asyncio.create_task(_websocket_broadcast_loop())

    print(f"[API] Server ready — {len(state.satellites)} satellites, "
          f"{len(state.debris)} debris tracked")
    print(f"[API] Dashboard: http://localhost:8000")
    print(f"[API] API Docs:  http://localhost:8000/docs")

    yield

    # Shutdown
    sim_task.cancel()
    ws_task.cancel()
    print("[API] Shutdown complete")


# ═══════════════════════════════════════════════════════════════════════════
#  FastAPI Application
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="ACM — Autonomous Constellation Manager",
    description="Real-time satellite constellation management with autonomous "
                "collision avoidance. National Space Hackathon 2026.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow dashboard on any origin during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Include Routers ───────────────────────────────────────────────────────

app.include_router(telemetry_router, prefix="/api")
app.include_router(maneuvers_router, prefix="/api")
app.include_router(rulebook_router)  # Rulebook compliant endpoints


# ═══════════════════════════════════════════════════════════════════════════
#  Core API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "OK",
        "sim_time": state.sim_time.isoformat(),
        "satellites": len(state.satellites),
        "debris": len(state.debris),
        "ws_clients": len(state.ws_clients),
    }


@app.get("/api/visualization/snapshot")
async def get_snapshot():
    """Full state snapshot for dashboard visualization."""
    return state.get_snapshot()


@app.get("/api/constellation/stats")
async def get_constellation_stats():
    """Constellation statistics including ΔV totals."""
    return state.get_stats()


@app.get("/api/alerts")
async def get_alerts(after: int = 0):
    """Get mission alerts (since-based polling)."""
    alerts = state.get_alerts_since(after)
    latest_id = alerts[0]["id"] if alerts else after
    return {"alerts": alerts, "latest_id": latest_id}


# ── Simulation Control ────────────────────────────────────────────────────

@app.post("/api/simulation/step")
async def simulation_step(body: dict = None):
    """Advance simulation by one step (Section 4 endpoint)."""
    step_seconds = 60
    if body and "step_seconds" in body:
        step_seconds = body["step_seconds"]
    
    # Use the autonomy engine for spec-compliant simulation
    result = state.autonomy_engine.simulate_step(step_seconds)
    return result


@app.post("/api/simulation/run")
async def simulation_run(body: dict = None):
    """Start continuous simulation (Section 4 endpoint)."""
    if body:
        state.step_seconds = body.get("step_seconds", 60)
        state.real_interval_ms = body.get("real_interval_ms", 1000)
    state.sim_running = True
    return {"status": "OK", "running": True}


@app.post("/api/simulation/stop")
async def simulation_stop():
    """Stop continuous simulation (Section 4 endpoint)."""
    state.sim_running = False
    return {"status": "OK", "running": False}


@app.get("/api/simulation/status")
async def simulation_get_status():
    """Get simulation status (Section 4 endpoint)."""
    return {
        "running": state.sim_running,
        "sim_time": state.sim_time.isoformat(),
        "step_seconds": state.step_seconds,
        "real_interval_ms": state.real_interval_ms,
    }


# Legacy endpoint aliases for backward compatibility
@app.post("/api/simulate/step")
async def simulate_step_legacy(body: dict = None):
    """Legacy endpoint - redirects to /api/simulation/step"""
    return await simulation_step(body)


@app.post("/api/simulate/run")
async def start_simulation_legacy(body: dict = None):
    """Legacy endpoint - redirects to /api/simulation/run"""
    return await simulation_run(body)


@app.post("/api/simulate/stop")
async def stop_simulation_legacy():
    """Legacy endpoint - redirects to /api/simulation/stop"""
    return await simulation_stop()


@app.get("/api/simulate/status")
async def simulation_status_legacy():
    """Legacy endpoint - redirects to /api/simulation/status"""
    return await simulation_get_status()


# ═══════════════════════════════════════════════════════════════════════════
#  WebSocket — Real-time Telemetry Stream
# ═══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry streaming.
    Clients receive snapshot updates every simulation tick.
    Clients can also send commands via the WebSocket.
    """
    await websocket.accept()
    state.register_ws(websocket)
    client_id = id(websocket)
    print(f"[WS] Client {client_id} connected ({len(state.ws_clients)} total)")

    try:
        # Send initial snapshot
        snapshot = state.get_snapshot()
        await websocket.send_json({
            "type": "snapshot",
            "data": snapshot,
        })

        # Listen for client commands while connected
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=30.0
                )
                msg = json.loads(data)
                await _handle_ws_message(websocket, msg)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat", "ts": time.time()})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Client {client_id} error: {e}")
    finally:
        state.unregister_ws(websocket)
        print(f"[WS] Client {client_id} disconnected ({len(state.ws_clients)} remaining)")


async def _handle_ws_message(websocket: WebSocket, msg: dict):
    """Handle incoming WebSocket commands from clients with 10s signal delay."""
    msg_type = msg.get("type", "")
    command_timestamp = msg.get("timestamp")
    
    # Enforce 10-second signal delay (Section 4.2)
    current_time = time.time()
    if command_timestamp:
        time_diff = current_time - command_timestamp
        if time_diff < 10.0:
            await websocket.send_json({
                "type": "error",
                "message": f"Command violates 10s signal delay. Received after {time_diff:.2f}s, need 10s minimum."
            })
            return
    
    if msg_type == "simulate_step":
        dt = msg.get("step_seconds", 60)
        state.simulate_step(dt)
        await websocket.send_json({
            "type": "step_complete",
            "sim_time": state.sim_time.isoformat(),
        })

    elif msg_type == "subscribe":
        # Client subscribes to specific satellite updates
        await websocket.send_json({"type": "subscribed", "status": "OK"})

    elif msg_type == "command_maneuver":
        sat_id = msg.get("satellite_id")
        delta_v = msg.get("delta_v", {"x": 0, "y": 0, "z": 0})
        result = state.execute_maneuver(sat_id, delta_v, 300.0)
        await websocket.send_json({"type": "maneuver_result", "data": result})

    elif msg_type == "inject_threat":
        # Allow injecting a threat for demonstration
        sat_id = msg.get("satellite_id")
        if sat_id and sat_id in state.satellites:
            state.satellites[sat_id].status = "EVADING"
            state._add_alert("THREAT_INJECTION", "CRITICAL",
                           f"Manual threat injected for {sat_id}", sat_id)
            await websocket.send_json({"type": "threat_injected", "satellite_id": sat_id})

    else:
        await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})


# ═══════════════════════════════════════════════════════════════════════════
#  Background Loops
# ═══════════════════════════════════════════════════════════════════════════

async def _simulation_loop():
    """Background simulation loop — advances state when sim_running=True."""
    while True:
        try:
            if state.sim_running:
                state.autonomy_engine.simulate_step(state.step_seconds)
            await asyncio.sleep(state.real_interval_ms / 1000.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[SIM] Error in simulation loop: {e}")
            await asyncio.sleep(1)


async def _websocket_broadcast_loop():
    """Broadcast snapshots to all connected WebSocket clients."""
    while True:
        try:
            if state.ws_clients:
                snapshot = state.get_snapshot()
                msg = json.dumps({"type": "snapshot", "data": snapshot})
                dead_clients = set()

                for ws in list(state.ws_clients):
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        dead_clients.add(ws)

                for ws in dead_clients:
                    state.unregister_ws(ws)

            await asyncio.sleep(2.0)  # Broadcast every 2 seconds
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WS] Broadcast error: {e}")
            await asyncio.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════
#  Static Files — Serve Dashboard
# ═══════════════════════════════════════════════════════════════════════════

# Serve the frontend dashboard
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/css", StaticFiles(directory=os.path.join(_frontend_dir, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(_frontend_dir, "js")), name="js")

    @app.get("/")
    async def serve_dashboard():
        """Serve the main dashboard HTML."""
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @app.get("/dashboard.html")
    async def serve_minimal_dashboard():
        """Serve the minimal dashboard HTML."""
        return FileResponse(os.path.join(_frontend_dir, "dashboard.html"))
