#!/usr/bin/env python3
"""
KAAL HTTPS Profile – High-Performance Reverse Proxy
Proxies all agent HTTP traffic to the core server with:
  - Persistent connection pool (TCP keep-alive)
  - Minimal header overhead
  - Aggressive timeouts for fast failure
"""

import asyncio
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
import uvicorn
import logging
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("https_profile")

# Core server URL (internal)
CORE_URL = "http://localhost:5000"
# Shared secret for profile-to-core authentication
INTERNAL_API_KEY = "KAAL-INTERNAL-SECURE-KEY-2024"

# Shared aiohttp session with connection pooling
session: Optional[aiohttp.ClientSession] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global session
    # Create a high-performance session with connection pooling
    connector = aiohttp.TCPConnector(
        limit=100,            # Max simultaneous connections
        limit_per_host=50,    # Max connections to core server
        keepalive_timeout=60, # Keep TCP connections alive for 60s
        enable_cleanup_closed=True,
        force_close=False,    # Reuse connections (HTTP keep-alive)
    )
    # Aggressive timeouts for fast interactive feel
    timeout = aiohttp.ClientTimeout(
        total=10,        # Total request timeout
        connect=3,       # Connection timeout
        sock_connect=3,  # Socket connect timeout
        sock_read=8,     # Socket read timeout
    )
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        # Pre-set the internal auth header on ALL requests
        headers={"X-Internal-Key": INTERNAL_API_KEY},
    )
    logger.info("HTTPS Profile started, forwarding to core at %s", CORE_URL)
    yield
    if session:
        await session.close()

app = FastAPI(title="KAAL HTTPS Profile", lifespan=lifespan)


async def proxy_request(request: Request) -> Response:
    """Forward the incoming request to the core server and return its response."""
    # Build the target URL (preserve path and query)
    path = request.url.path
    query = request.url.query
    target_url = f"{CORE_URL}{path}"
    if query:
        target_url += f"?{query}"

    # Only forward Content-Type (minimal header set for speed)
    headers = {}
    ct = request.headers.get("content-type")
    if ct:
        headers["Content-Type"] = ct

    # Read body if present
    body = await request.body()

    try:
        async with session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=body if body else None,
        ) as resp:
            response_body = await resp.read()
            # Only forward essential response headers
            resp_headers = {}
            for key in ("content-type", "content-length"):
                if key in resp.headers:
                    resp_headers[key] = resp.headers[key]
            return Response(
                content=response_body,
                status_code=resp.status,
                headers=resp_headers,
            )
    except asyncio.TimeoutError:
        logger.warning(f"Timeout proxying {request.method} {path}")
        return Response(status_code=504, content="Gateway Timeout")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return Response(status_code=502, content="Bad Gateway")


# ── Proxy Routes ──

@app.api_route("/api/v1/agent_message", methods=["POST"])
async def agent_message(request: Request):
    return await proxy_request(request)

@app.api_route("/api/v1/task/{agent_id}", methods=["GET"])
async def get_task(request: Request):
    return await proxy_request(request)

@app.api_route("/api/v1/register", methods=["POST"])
async def register(request: Request):
    return await proxy_request(request)

@app.api_route("/api/v1/result", methods=["POST"])
async def result(request: Request):
    return await proxy_request(request)

@app.api_route("/api/health", methods=["GET"])
async def health(request: Request):
    return await proxy_request(request)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5001,
        log_level="info",
        # Performance: disable access logging to reduce overhead
        access_log=False,
    )
