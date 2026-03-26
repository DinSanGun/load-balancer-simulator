from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod

from .config import Backend


class LoadBalancingStrategy(ABC):
    """
    Small strategy abstraction used by the load balancer.

    `choose_backend` picks a backend from the current healthy set.
    `on_request_start` / `on_request_end` let strategies track runtime state.
    """

    @abstractmethod
    def choose_backend(self, backends: list[Backend]) -> Backend:
        """Pick one backend from healthy backends."""

    def on_request_start(self, backend: Backend) -> object | None:
        """
        Optional hook called immediately before forwarding to backend.
        Return any per-request context you want passed into on_request_end.
        """

        return None

    def on_request_end(
        self,
        backend: Backend,
        started_context: object | None,
        *,
        success: bool,
    ) -> None:
        """
        Optional hook called after forwarding finishes (success or failure).
        `success` indicates whether backend request completed successfully.
        """

        return None


class RoundRobinStrategy(LoadBalancingStrategy):
    """
    Round Robin:
    - Keep an index for "next backend"
    - Use it, increment it, and wrap around
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idx = 0

    def choose_backend(self, backends: list[Backend]) -> Backend:
        if not backends:
            raise ValueError("No backends available")

        with self._lock:
            backend = backends[self._idx % len(backends)]
            self._idx = (self._idx + 1) % len(backends)
            return backend


class LeastConnectionsStrategy(LoadBalancingStrategy):
    """
    Least Connections:
    - Track active requests per backend
    - Pick backend with lowest active count
    - Increment before forwarding, decrement when done (or failed)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_counts: dict[str, int] = {}

    def choose_backend(self, backends: list[Backend]) -> Backend:
        if not backends:
            raise ValueError("No backends available")

        with self._lock:
            for b in backends:
                self._active_counts.setdefault(b.name, 0)
            return min(backends, key=lambda b: (self._active_counts.get(b.name, 0), b.name))

    def on_request_start(self, backend: Backend) -> object | None:
        with self._lock:
            self._active_counts[backend.name] = self._active_counts.get(backend.name, 0) + 1
        return None

    def on_request_end(
        self,
        backend: Backend,
        started_context: object | None,
        *,
        success: bool,
    ) -> None:
        with self._lock:
            current = self._active_counts.get(backend.name, 0)
            self._active_counts[backend.name] = max(0, current - 1)


class LeastResponseTimeStrategy(LoadBalancingStrategy):
    """
    Least Response Time:
    - Measure response duration for each backend request
    - Keep a simple running average per backend
    - Pick backend with the smallest average

    For new backends with no measurements yet, we try them first in round-robin
    order so each backend gets initial timing data.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._avg_seconds: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._cold_start_idx = 0

    def choose_backend(self, backends: list[Backend]) -> Backend:
        if not backends:
            raise ValueError("No backends available")

        with self._lock:
            unknown = [b for b in backends if b.name not in self._avg_seconds]
            if unknown:
                backend = unknown[self._cold_start_idx % len(unknown)]
                self._cold_start_idx = (self._cold_start_idx + 1) % max(1, len(unknown))
                return backend

            return min(backends, key=lambda b: (self._avg_seconds.get(b.name, float("inf")), b.name))

    def on_request_start(self, backend: Backend) -> object | None:
        return time.perf_counter()

    def on_request_end(
        self,
        backend: Backend,
        started_context: object | None,
        *,
        success: bool,
    ) -> None:
        # Update timing only on successful backend responses.
        if not success or not isinstance(started_context, float):
            return

        elapsed = time.perf_counter() - started_context
        with self._lock:
            old_count = self._counts.get(backend.name, 0)
            old_avg = self._avg_seconds.get(backend.name, 0.0)
            new_count = old_count + 1
            new_avg = ((old_avg * old_count) + elapsed) / new_count
            self._counts[backend.name] = new_count
            self._avg_seconds[backend.name] = new_avg


def build_strategy(name: str) -> LoadBalancingStrategy:
    """
    Create a strategy from config value.
    Unknown values fall back to round robin for safety.
    """

    key = name.strip().lower()
    if key == "least_connections":
        return LeastConnectionsStrategy()
    if key == "least_response_time":
        return LeastResponseTimeStrategy()
    return RoundRobinStrategy()

