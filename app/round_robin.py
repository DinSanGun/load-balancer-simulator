from __future__ import annotations

import threading

from .config import Backend


class RoundRobin:
    """
    Minimal round-robin selector.

    How round robin works:
    - Keep an index that points at "the next backend to use".
    - For each incoming request, return backends[index], then increment index.
    - When the index reaches the end, wrap around to 0.

    We also use a lock so multiple concurrent requests don't corrupt the index.
    (Even though this is MVP, it helps keep behavior predictable.)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idx = 0

    def next(self, backends: list[Backend]) -> Backend:
        if not backends:
            raise ValueError("No backends available")

        with self._lock:
            backend = backends[self._idx % len(backends)]
            self._idx = (self._idx + 1) % len(backends)
            return backend

