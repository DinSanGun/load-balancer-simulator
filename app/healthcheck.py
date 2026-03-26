from __future__ import annotations

import socket

from .config import Backend, TCP_CONNECT_TIMEOUT_SECONDS


def tcp_is_reachable(backend: Backend) -> bool:
    """
    TCP health check (very small + simple).

    What it does:
    - Attempts to open a TCP connection to (host, port).
    - If the TCP connection succeeds, we consider the backend "reachable".
    - If it times out or fails (connection refused / no route), we consider it unhealthy.

    Why this is useful:
    - It does NOT require a specific HTTP endpoint to exist.
    - It only checks that something is listening on that port.
    - It is fast and easy to understand for an MVP.
    """

    try:
        # create_connection performs:
        # - DNS resolution (if needed)
        # - TCP 3-way handshake
        # If any part fails, it raises an exception.
        with socket.create_connection(
            (backend.host, backend.port),
            timeout=TCP_CONNECT_TIMEOUT_SECONDS,
        ):
            return True
    except OSError:
        return False


def filter_healthy_backends(backends: list[Backend]) -> list[Backend]:
    """Return only backends that pass the TCP health check."""
    return [b for b in backends if tcp_is_reachable(b)]

