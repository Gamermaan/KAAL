from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
from core.state_manager import terminal_state

app = FastAPI(title="KAAL Web Console")

# Serve static files (React build – optional)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    """Serve the main dashboard HTML."""
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>KAAL Console</title></head>
    <body>
        <h1>KAAL Web Console</h1>
        <p>Build the React frontend and place it in web/static/ to enable the full dashboard.</p>
        <p>API endpoints:</p>
        <ul>
            <li><a href="/api/agents">/api/agents</a></li>
            <li><a href="/docs">/docs</a> (Swagger)</li>
        </ul>
    </body>
    </html>
    """)

@app.get("/api/agents")
async def get_agents():
    """Return a list of currently registered agents."""
    from console.relay_manager import RelayManager
    mgr = RelayManager()
    return {"agents": mgr.agents}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real‑time updates."""
    await terminal_state.register_client(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming client messages if needed
    except:
        terminal_state.remove_client(websocket)
