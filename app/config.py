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


@dataclass(frozen=True)
class BackendBehavior:
    """
    Optional runtime behavior simulation for a backend.

    - fixed_delay_ms: base delay applied to every request
    - jitter_ms: random extra delay in range [0, jitter_ms]
    - failure_rate: probability [0.0, 1.0] of simulated HTTP 500
    """

    fixed_delay_ms: int = 0
    jitter_ms: int = 0
    failure_rate: float = 0.0


# Per-backend defaults (simple and explicit).
# Values can be overridden with environment variables at runtime.
BACKEND_BEHAVIORS: dict[str, BackendBehavior] = {
    "backend-1": BackendBehavior(),
    "backend-2": BackendBehavior(),
    "backend-3": BackendBehavior(),
}


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_backend_behavior(server_name: str) -> BackendBehavior:
    """
    Resolve backend behavior for this backend instance.

    Precedence:
    1) Backend-specific environment variables (highest)
    2) Global environment variables
    3) BACKEND_BEHAVIORS defaults
    """

    defaults = BACKEND_BEHAVIORS.get(server_name, BackendBehavior())
    prefix = server_name.upper().replace("-", "_")

    fixed_delay_ms = _get_env_int(
        f"{prefix}_FIXED_DELAY_MS",
        _get_env_int("BACKEND_FIXED_DELAY_MS", defaults.fixed_delay_ms),
    )
    jitter_ms = _get_env_int(
        f"{prefix}_JITTER_MS",
        _get_env_int("BACKEND_JITTER_MS", defaults.jitter_ms),
    )
    failure_rate = _get_env_float(
        f"{prefix}_FAILURE_RATE",
        _get_env_float("BACKEND_FAILURE_RATE", defaults.failure_rate),
    )

    # Clamp values so invalid env values do not break behavior.
    fixed_delay_ms = max(0, fixed_delay_ms)
    jitter_ms = max(0, jitter_ms)
    failure_rate = min(1.0, max(0.0, failure_rate))

    return BackendBehavior(
        fixed_delay_ms=fixed_delay_ms,
        jitter_ms=jitter_ms,
        failure_rate=failure_rate,
    )


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

# Simple overload guard:
# maximum number of in-flight requests the load balancer accepts at once.
# New requests above this limit are rejected with HTTP 503.
LOAD_BALANCER_MAX_IN_FLIGHT = max(1, _get_env_int("LB_MAX_IN_FLIGHT", 100))

# JSON error body for overload 503; client/benchmark match on this to classify overload vs other failures.
LOAD_BALANCER_OVERLOAD_ERROR_TEXT = "Load balancer overloaded. Try again shortly."

# Label used in `requests_per_backend` counters for overload 503 responses (no X-Backend).
LB_OVERLOAD_REQUEST_LABEL = "__overload_503__"
