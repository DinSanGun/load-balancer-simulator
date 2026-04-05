from __future__ import annotations

import logging
import threading

import requests
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import (
    BACKENDS,
    Backend,
    LOAD_BALANCING_STRATEGY,
    LOAD_BALANCER_MAX_IN_FLIGHT,
    LOAD_BALANCER_OVERLOAD_ERROR_TEXT,
)
from .healthcheck import filter_healthy_backends, tcp_is_reachable
from .strategies import LoadBalancingStrategy, build_strategy


logger = logging.getLogger("load_balancer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Explicit strategy names accepted by the control plane (matches build_strategy routing).
VALID_CONTROL_STRATEGIES: frozenset[str] = frozenset(
    ("round_robin", "least_connections", "least_response_time")
)

app = FastAPI(title="Load Balancer (MVP)")

_strategy_lock = threading.Lock()
active_strategy_name: str = LOAD_BALANCING_STRATEGY.strip().lower()
strategy: LoadBalancingStrategy = build_strategy(active_strategy_name)
logger.info("Active strategy: %s", active_strategy_name)

control_router = APIRouter(prefix="/control", tags=["control-plane"])


class OverloadState:
    """Small process-local overload guard + counters."""

    def __init__(self, max_in_flight: int) -> None:
        self._lock = threading.Lock()
        self.max_in_flight = max_in_flight
        self.active_requests = 0
        self.rejected_requests_total = 0
        self.peak_active_requests = 0

    def try_acquire(self) -> bool:
        with self._lock:
            if self.active_requests >= self.max_in_flight:
                self.rejected_requests_total += 1
                return False
            self.active_requests += 1
            if self.active_requests > self.peak_active_requests:
                self.peak_active_requests = self.active_requests
            return True

    def release(self) -> None:
        with self._lock:
            self.active_requests = max(0, self.active_requests - 1)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "max_in_flight_requests": self.max_in_flight,
                "active_requests": self.active_requests,
                "rejected_requests_total": self.rejected_requests_total,
                "peak_active_requests": self.peak_active_requests,
            }

    def reset_for_tests(self, *, max_in_flight: int | None = None) -> None:
        with self._lock:
            if max_in_flight is not None:
                self.max_in_flight = max(1, max_in_flight)
            self.active_requests = 0
            self.rejected_requests_total = 0
            self.peak_active_requests = 0

    def set_max_in_flight(self, value: int) -> int:
        """Update the admission limit at runtime (process-local)."""
        if value < 1:
            raise ValueError("max_in_flight must be >= 1")
        with self._lock:
            self.max_in_flight = value
        return value


overload_state = OverloadState(max_in_flight=LOAD_BALANCER_MAX_IN_FLIGHT)
logger.info("Max in-flight requests: %s", LOAD_BALANCER_MAX_IN_FLIGHT)


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
    Route one request over healthy backends using configured strategy.

    - First, do a *TCP* health check for each backend (socket connect).
    - Keep only healthy ones.
    - Select one backend using the chosen strategy.
    - Forward the HTTP request to that backend.
    - Log which backend handled it.
    """

    if not overload_state.try_acquire():
        return JSONResponse(
            status_code=503,
            content={"error": LOAD_BALANCER_OVERLOAD_ERROR_TEXT},
        )

    backend: Backend | None = None
    request_ctx: object | None = None

    try:
        healthy = filter_healthy_backends(BACKENDS)
        if not healthy:
            return JSONResponse(
                status_code=503,
                content={"error": "No healthy backends available"},
            )

        with _strategy_lock:
            current_strategy = strategy

        backend = current_strategy.choose_backend(healthy)
        request_ctx = current_strategy.on_request_start(backend)

        try:
            status_code, payload = _forward_get_root(backend)
        except requests.RequestException as e:
            # A backend can become unreachable between the TCP check and the HTTP call.
            # Keep the MVP behavior simple: return a 502.
            current_strategy.on_request_end(backend, request_ctx, success=False)
            logger.warning("Forwarding failed to %s (%s:%s): %s", backend.name, backend.host, backend.port, e)
            return JSONResponse(
                status_code=502,
                content={"error": "Backend request failed", "backend": backend.name},
            )
        else:
            current_strategy.on_request_end(backend, request_ctx, success=True)

        logger.info("Routed request to %s (%s:%s)", backend.name, backend.host, backend.port)

        # Add a small hint header so it's visible in curl output.
        return JSONResponse(
            status_code=status_code,
            content={"backend": backend.name, "backend_response": payload},
            headers={"X-Backend": backend.name},
        )
    finally:
        overload_state.release()


@app.get("/lb/status")
def lb_status() -> JSONResponse:
    """Minimal local status endpoint for strategy + overload counters."""
    with _strategy_lock:
        name = active_strategy_name
    data = {
        "strategy": name,
        **overload_state.snapshot(),
    }
    return JSONResponse(status_code=200, content=data)


class StrategyUpdateBody(BaseModel):
    strategy: str = Field(..., min_length=1, description="One of: round_robin, least_connections, least_response_time")


class MaxInFlightBody(BaseModel):
    max_in_flight: int = Field(..., ge=1, le=1_000_000, description="Max concurrent in-flight requests at the load balancer")


@control_router.get("/status")
def control_status() -> JSONResponse:
    """
    Demo-friendly unified status (process-local control plane MVP).
    Separate from the data-plane forwarding path; useful for demos and inspection.
    """
    with _strategy_lock:
        strat = active_strategy_name
    backends = [
        {
            "name": b.name,
            "host": b.host,
            "port": b.port,
            "tcp_reachable": tcp_is_reachable(b),
        }
        for b in BACKENDS
    ]
    payload = {
        "layer": "control_plane_mvp",
        "scope": "process_local",
        "note": "Educational demo only: no auth, no persistence, not for production.",
        "active_strategy": strat,
        "backends": backends,
        **overload_state.snapshot(),
    }
    return JSONResponse(status_code=200, content=payload)


@control_router.post("/strategy")
def control_set_strategy(body: StrategyUpdateBody) -> JSONResponse:
    """Switch routing strategy at runtime (in-process)."""
    global strategy, active_strategy_name

    key = body.strategy.strip().lower()
    if key not in VALID_CONTROL_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_strategy",
                "message": f"Must be one of: {sorted(VALID_CONTROL_STRATEGIES)}",
                "allowed": sorted(VALID_CONTROL_STRATEGIES),
            },
        )

    new_strategy = build_strategy(key)
    with _strategy_lock:
        strategy = new_strategy
        active_strategy_name = key

    logger.info("Control plane: active strategy set to %s", key)
    return JSONResponse(
        status_code=200,
        content={"active_strategy": key, "message": "Strategy updated"},
    )


@control_router.post("/max-in-flight")
def control_set_max_in_flight(body: MaxInFlightBody) -> JSONResponse:
    """Update max in-flight admission limit at runtime (in-process)."""
    overload_state.set_max_in_flight(body.max_in_flight)
    snap = overload_state.snapshot()
    logger.info("Control plane: max_in_flight set to %s", body.max_in_flight)
    return JSONResponse(
        status_code=200,
        content={
            "max_in_flight_requests": snap["max_in_flight_requests"],
            "message": "Max in-flight limit updated",
        },
    )


app.include_router(control_router)

