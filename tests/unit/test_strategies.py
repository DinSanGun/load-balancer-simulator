from __future__ import annotations

import time

from app.config import Backend
from app.strategies import LeastConnectionsStrategy, LeastResponseTimeStrategy, RoundRobinStrategy


BACKENDS = [
    Backend(name="backend-1", host="127.0.0.1", port=8001),
    Backend(name="backend-2", host="127.0.0.1", port=8002),
    Backend(name="backend-3", host="127.0.0.1", port=8003),
]


def test_round_robin_rotates_in_order() -> None:
    strategy = RoundRobinStrategy()
    picks = [strategy.choose_backend(BACKENDS).name for _ in range(6)]
    assert picks == ["backend-1", "backend-2", "backend-3", "backend-1", "backend-2", "backend-3"]


def test_least_connections_prefers_backend_with_fewer_active_requests() -> None:
    strategy = LeastConnectionsStrategy()
    busy_backend = BACKENDS[0]
    strategy.on_request_start(busy_backend)  # backend-1 now has one active request

    chosen = strategy.choose_backend(BACKENDS)
    assert chosen.name in {"backend-2", "backend-3"}


def test_least_connections_tie_break_is_deterministic_rotation() -> None:
    strategy = LeastConnectionsStrategy()
    picks = []
    for _ in range(6):
        backend = strategy.choose_backend(BACKENDS)
        strategy.on_request_start(backend)
        strategy.on_request_end(backend, None, success=True)
        picks.append(backend.name)

    assert picks == ["backend-1", "backend-2", "backend-3", "backend-1", "backend-2", "backend-3"]


def test_least_response_time_prefers_lowest_average_response_time() -> None:
    strategy = LeastResponseTimeStrategy()
    strategy._probe_every = 10_000  # keep selection deterministic for this unit test

    now = time.perf_counter()
    strategy.on_request_end(BACKENDS[0], now - 0.30, success=True)  # slower
    strategy.on_request_end(BACKENDS[1], now - 0.10, success=True)  # fastest
    strategy.on_request_end(BACKENDS[2], now - 0.20, success=True)  # medium

    chosen = strategy.choose_backend(BACKENDS)
    assert chosen.name == "backend-2"
