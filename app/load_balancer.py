from __future__ import annotations

import logging
import threading

import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import BACKENDS, Backend, LOAD_BALANCING_STRATEGY, LOAD_BALANCER_MAX_IN_FLIGHT
from .healthcheck import filter_healthy_backends
from .strategies import LoadBalancingStrategy, build_strategy


logger = logging.getLogger("load_balancer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Load Balancer (MVP)")
strategy: LoadBalancingStrategy = build_strategy(LOAD_BALANCING_STRATEGY)
logger.info("Active strategy: %s", LOAD_BALANCING_STRATEGY)


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
            content={"error": "Load balancer overloaded. Try again shortly."},
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

        backend = strategy.choose_backend(healthy)
        request_ctx = strategy.on_request_start(backend)

        try:
            status_code, payload = _forward_get_root(backend)
        except requests.RequestException as e:
            # A backend can become unreachable between the TCP check and the HTTP call.
            # Keep the MVP behavior simple: return a 502.
            strategy.on_request_end(backend, request_ctx, success=False)
            logger.warning("Forwarding failed to %s (%s:%s): %s", backend.name, backend.host, backend.port, e)
            return JSONResponse(
                status_code=502,
                content={"error": "Backend request failed", "backend": backend.name},
            )
        else:
            strategy.on_request_end(backend, request_ctx, success=True)

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
    data = {
        "strategy": LOAD_BALANCING_STRATEGY,
        **overload_state.snapshot(),
    }
    return JSONResponse(status_code=200, content=data)

