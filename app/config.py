from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Backend:
    """
    A single backend instance configuration.

    We keep this as simple data (host/port/name), so other modules can use it
    without depending on FastAPI or any networking libraries.
    """

    name: str
    host: str
    port: int

    @property
    def base_url(self) -> str:
        # Used by the load balancer to forward HTTP requests.
        return f"http://{self.host}:{self.port}"


# MVP: we hard-code 3 backends.
# You can later move this to a config file or env vars.
BACKENDS: list[Backend] = [
    Backend(name="backend-1", host="127.0.0.1", port=8001),
    Backend(name="backend-2", host="127.0.0.1", port=8002),
    Backend(name="backend-3", host="127.0.0.1", port=8003),
]


# TCP health check settings.
TCP_CONNECT_TIMEOUT_SECONDS = 0.2


# Backend "work" simulation (random delay bounds).
BACKEND_MIN_DELAY_SECONDS = 0.05
BACKEND_MAX_DELAY_SECONDS = 0.8


# Active load-balancing strategy.
# Supported values:
# - "round_robin"
# - "least_connections"
# - "least_response_time"
LOAD_BALANCING_STRATEGY = os.getenv("LB_STRATEGY", "round_robin").strip().lower()
