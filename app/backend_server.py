from __future__ import annotations

import os
import random
import time

from fastapi import FastAPI

from .config import BACKEND_MAX_DELAY_SECONDS, BACKEND_MIN_DELAY_SECONDS


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

    def _simulate_work() -> float:
        delay = random.uniform(BACKEND_MIN_DELAY_SECONDS, BACKEND_MAX_DELAY_SECONDS)
        time.sleep(delay)
        return delay

    @app.get("/")
    def root() -> dict[str, object]:
        delay = _simulate_work()
        return {"message": f"Hello from {server_name}", "delay_seconds": round(delay, 4)}

    @app.get("/health")
    def health() -> dict[str, str]:
        # Usually health checks should be very fast, so we do not delay here.
        return {"status": "OK"}

    return app


# Convenience: when running `uvicorn app.backend_server:app ...`,
# we build the app using an env var name (defaults to "backend").
app = create_app(os.getenv("BACKEND_NAME", "backend"))

