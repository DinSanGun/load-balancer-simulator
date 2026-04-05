from __future__ import annotations

from fastapi.testclient import TestClient

import app.load_balancer as lb
from app.strategies import LeastConnectionsStrategy, RoundRobinStrategy


def setup_function() -> None:
    lb.overload_state.reset_for_tests(max_in_flight=100)
    lb.strategy = RoundRobinStrategy()
    lb.active_strategy_name = "round_robin"


def test_control_status_has_core_fields(monkeypatch) -> None:
    monkeypatch.setattr(lb, "tcp_is_reachable", lambda _b: True)
    client = TestClient(lb.app)
    r = client.get("/control/status")
    assert r.status_code == 200
    data = r.json()
    assert data["layer"] == "control_plane_mvp"
    assert data["scope"] == "process_local"
    assert data["active_strategy"] == "round_robin"
    assert "max_in_flight_requests" in data
    assert "active_requests" in data
    assert "peak_active_requests" in data
    assert "rejected_requests_total" in data
    assert len(data["backends"]) == 3
    assert all("tcp_reachable" in b for b in data["backends"])


def test_post_strategy_updates_runtime_strategy() -> None:
    client = TestClient(lb.app)
    r = client.post("/control/strategy", json={"strategy": "least_connections"})
    assert r.status_code == 200
    assert r.json()["active_strategy"] == "least_connections"

    assert isinstance(lb.strategy, LeastConnectionsStrategy)
    st = client.get("/control/status").json()
    assert st["active_strategy"] == "least_connections"


def test_post_strategy_rejects_invalid() -> None:
    client = TestClient(lb.app)
    r = client.post("/control/strategy", json={"strategy": "weighted_magic"})
    assert r.status_code == 400
    assert "invalid_strategy" in str(r.json())


def test_post_max_in_flight_updates_limit() -> None:
    client = TestClient(lb.app)
    r = client.post("/control/max-in-flight", json={"max_in_flight": 42})
    assert r.status_code == 200
    assert r.json()["max_in_flight_requests"] == 42

    snap = lb.overload_state.snapshot()
    assert snap["max_in_flight_requests"] == 42


def test_post_max_in_flight_rejects_below_one() -> None:
    client = TestClient(lb.app)
    r = client.post("/control/max-in-flight", json={"max_in_flight": 0})
    assert r.status_code == 422
