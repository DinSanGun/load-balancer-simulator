from __future__ import annotations

import os
import random
import time

from fastapi import FastAPI
from fastapi import HTTPException

from .config import get_backend_behavior


def create_app(server_name: str) -> FastAPI:
    """
    Backend service FastAPI app.

    For the MVP each backend has:
    - GET /        -> identifies the server
    - GET /health  -> basic health endpoint

    We add a small random delay to simulate processing time.
    (This is intentionally simple and synchronous.)
    """

    app = FastAPI(title=f"Backend Service ({server_name})")
    behavior = get_backend_behavior(server_name)

    def _simulate_work() -> float:
        """
        Simulate backend runtime conditions with simple knobs:
        - fixed delay (always)
        - jitter (small random extra delay)
        """

        fixed_seconds = behavior.fixed_delay_ms / 1000.0
        jitter_seconds = random.uniform(0.0, behavior.jitter_ms / 1000.0) if behavior.jitter_ms > 0 else 0.0
        delay = fixed_seconds + jitter_seconds
        if delay > 0:
            time.sleep(delay)
        return delay

    def _should_fail() -> bool:
        """
        Return True if this request should fail based on configured probability.
        """

        if behavior.failure_rate <= 0:
            return False
        return random.random() < behavior.failure_rate

    @app.get("/")
    def root() -> dict[str, object]:
        delay = _simulate_work()
        if _should_fail():
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Simulated backend failure",
                    "backend": server_name,
                },
            )
        return {"message": f"Hello from {server_name}", "delay_seconds": round(delay, 4)}

    @app.get("/health")
    def health() -> dict[str, str]:
        # Usually health checks should be very fast, so we do not delay here.
        return {"status": "OK"}

    return app


# Convenience: when running `uvicorn app.backend_server:app ...`,
# we build the app using an env var name (defaults to "backend").
app = create_app(os.getenv("BACKEND_NAME", "backend"))

