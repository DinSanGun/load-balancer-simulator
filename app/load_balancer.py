from __future__ import annotations

import logging

import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import BACKENDS, Backend
from .healthcheck import filter_healthy_backends
from .round_robin import RoundRobin


logger = logging.getLogger("load_balancer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Load Balancer (MVP)")
rr = RoundRobin()


def _forward_get_root(backend: Backend) -> tuple[int, dict[str, object]]:
    """
    HTTP forwarding (MVP).

    The load balancer receives a client request, then performs its own HTTP request
    to a backend server and returns the backend's response to the client.

    In this MVP:
    - we only forward GET /
    - we use the `requests` library (simple, blocking)
    - we return JSON
    """

    url = f"{backend.base_url}/"
    resp = requests.get(url, timeout=2.0)

    # If the backend returned non-JSON, this would raise.
    # For this MVP, our backend always returns JSON.
    data: dict[str, object] = resp.json()
    return resp.status_code, data


@app.get("/")
def root() -> JSONResponse:
    """
    Route one request using Round Robin over healthy backends.

    - First, do a *TCP* health check for each backend (socket connect).
    - Keep only healthy ones.
    - Select the next backend using round robin.
    - Forward the HTTP request to that backend.
    - Log which backend handled it.
    """

    healthy = filter_healthy_backends(BACKENDS)
    if not healthy:
        return JSONResponse(
            status_code=503,
            content={"error": "No healthy backends available"},
        )

    backend = rr.next(healthy)

    try:
        status_code, payload = _forward_get_root(backend)
    except requests.RequestException as e:
        # A backend can become unreachable between the TCP check and the HTTP call.
        # Keep the MVP behavior simple: return a 502.
        logger.warning("Forwarding failed to %s (%s:%s): %s", backend.name, backend.host, backend.port, e)
        return JSONResponse(
            status_code=502,
            content={"error": "Backend request failed", "backend": backend.name},
        )

    logger.info("Routed request to %s (%s:%s)", backend.name, backend.host, backend.port)

    # Add a small hint header so it's visible in curl output.
    return JSONResponse(
        status_code=status_code,
        content={"backend": backend.name, "backend_response": payload},
        headers={"X-Backend": backend.name},
    )

