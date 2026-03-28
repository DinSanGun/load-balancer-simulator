from __future__ import annotations

from dataclasses import dataclass

from .config import BackendBehavior


@dataclass(frozen=True)
class BenchmarkScenario:
    """
    Named benchmark scenario: explicit per-backend behavior for repeatable runs.

    Values map directly onto backend env vars (see get_backend_behavior in config.py).
    """

    name: str
    description: str
    backends: dict[str, BackendBehavior]


# Explicit, readable presets for demos and comparisons.
SCENARIOS: dict[str, BenchmarkScenario] = {
    "balanced": BenchmarkScenario(
        name="balanced",
        description="All backends similar: moderate fixed delay and low jitter; no simulated failures.",
        backends={
            "backend-1": BackendBehavior(fixed_delay_ms=100, jitter_ms=30, failure_rate=0.0),
            "backend-2": BackendBehavior(fixed_delay_ms=100, jitter_ms=30, failure_rate=0.0),
            "backend-3": BackendBehavior(fixed_delay_ms=100, jitter_ms=30, failure_rate=0.0),
        },
    ),
    "one_slow_backend": BenchmarkScenario(
        name="one_slow_backend",
        description="One backend is much slower than the others; highlights response-time and connection-based strategies.",
        backends={
            "backend-1": BackendBehavior(fixed_delay_ms=80, jitter_ms=20, failure_rate=0.0),
            "backend-2": BackendBehavior(fixed_delay_ms=400, jitter_ms=100, failure_rate=0.0),
            "backend-3": BackendBehavior(fixed_delay_ms=120, jitter_ms=40, failure_rate=0.0),
        },
    ),
    "flaky_backend": BenchmarkScenario(
        name="flaky_backend",
        description="One backend has intermittent simulated HTTP 500 responses; others are stable.",
        backends={
            "backend-1": BackendBehavior(fixed_delay_ms=100, jitter_ms=30, failure_rate=0.0),
            "backend-2": BackendBehavior(fixed_delay_ms=100, jitter_ms=30, failure_rate=0.0),
            "backend-3": BackendBehavior(fixed_delay_ms=150, jitter_ms=50, failure_rate=0.12),
        },
    ),
    "high_jitter": BenchmarkScenario(
        name="high_jitter",
        description="All backends have low fixed delay but high jitter; stresses variance in least-response-time estimates.",
        backends={
            "backend-1": BackendBehavior(fixed_delay_ms=50, jitter_ms=220, failure_rate=0.0),
            "backend-2": BackendBehavior(fixed_delay_ms=50, jitter_ms=220, failure_rate=0.0),
            "backend-3": BackendBehavior(fixed_delay_ms=50, jitter_ms=220, failure_rate=0.0),
        },
    ),
}


def get_scenario(name: str) -> BenchmarkScenario:
    key = name.strip().lower()
    if key not in SCENARIOS:
        known = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown scenario {name!r}. Choose one of: {known}")
    return SCENARIOS[key]


def list_scenario_names() -> list[str]:
    return sorted(SCENARIOS.keys())


def scenario_backend_behaviors_dict(scenario: BenchmarkScenario) -> dict[str, dict[str, float | int]]:
    """JSON-serializable map of backend name -> behavior fields."""
    out: dict[str, dict[str, float | int]] = {}
    for backend_name, behavior in scenario.backends.items():
        out[backend_name] = {
            "fixed_delay_ms": behavior.fixed_delay_ms,
            "jitter_ms": behavior.jitter_ms,
            "failure_rate": behavior.failure_rate,
        }
    return out
