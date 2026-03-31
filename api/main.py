import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from routers import telemetry
from state_manager import state

app = FastAPI(title="Systems Orchestration API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry.router, prefix="/api/v1")

# Track active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Wait for any messages from client if necessary
            data = await websocket.receive_text()
            # Could process client messages here
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_state_loop():
    """Background task to broadcast the current state to all connected clients."""
    while True:
        # Example broadcasting the current state at ~10Hz
        await asyncio.sleep(0.1)
        if manager.active_connections:
            message = {
                "type": "state_update",
                "satellites": state.get_all_satellites(),
                "debris": state.get_all_debris()
            }
            await manager.broadcast(message)

@app.on_event("startup")
async def startup_event():
    # Start the broadcast loop in the background
    asyncio.create_task(broadcast_state_loop())

@app.get("/")
async def root():
    return {"message": "Systems Orchestration API is running"}
