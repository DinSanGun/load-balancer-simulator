from __future__ import annotations

from fastapi.testclient import TestClient

import app.load_balancer as lb
from app.config import BACKENDS
from app.strategies import LoadBalancingStrategy, RoundRobinStrategy


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


def setup_function() -> None:
    lb.overload_state.reset_for_tests(max_in_flight=100)
    lb.strategy = RoundRobinStrategy()


def test_forwards_requests_to_healthy_backend(monkeypatch) -> None:
    backend = BACKENDS[0]
    monkeypatch.setattr(lb, "filter_healthy_backends", lambda _: [backend])
    monkeypatch.setattr(lb, "strategy", RoundRobinStrategy())

    def fake_get(url: str, timeout: float):
        assert url == f"{backend.base_url}/"
        assert timeout == 2.0
        return _FakeResponse(200, {"message": "ok from backend"})

    monkeypatch.setattr(lb.requests, "get", fake_get)

    client = TestClient(lb.app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["x-backend"] == backend.name
    body = response.json()
    assert body["backend"] == backend.name
    assert body["backend_response"]["message"] == "ok from backend"


def test_unhealthy_backends_are_skipped(monkeypatch) -> None:
    healthy_backend = BACKENDS[2]
    monkeypatch.setattr(lb, "filter_healthy_backends", lambda _: [healthy_backend])
    monkeypatch.setattr(lb, "strategy", RoundRobinStrategy())

    called = {"url": ""}

    def fake_get(url: str, timeout: float):
        called["url"] = url
        return _FakeResponse(200, {"message": "ok"})

    monkeypatch.setattr(lb.requests, "get", fake_get)

    client = TestClient(lb.app)
    response = client.get("/")

    assert response.status_code == 200
    assert called["url"] == f"{healthy_backend.base_url}/"
    assert response.json()["backend"] == healthy_backend.name


def test_backend_failure_response_is_returned_to_client(monkeypatch) -> None:
    backend = BACKENDS[1]
    monkeypatch.setattr(lb, "filter_healthy_backends", lambda _: [backend])
    monkeypatch.setattr(lb, "strategy", RoundRobinStrategy())
    monkeypatch.setattr(
        lb.requests,
        "get",
        lambda url, timeout: _FakeResponse(500, {"error": "Simulated backend failure", "backend": backend.name}),
    )

    client = TestClient(lb.app)
    response = client.get("/")

    assert response.status_code == 500
    body = response.json()
    assert body["backend"] == backend.name
    assert "backend_response" in body


def test_rejects_with_503_when_overload_limit_is_reached(monkeypatch) -> None:
    backend = BACKENDS[0]
    lb.overload_state.reset_for_tests(max_in_flight=1)
    monkeypatch.setattr(lb, "filter_healthy_backends", lambda _: [backend])
    monkeypatch.setattr(lb.requests, "get", lambda url, timeout: _FakeResponse(200, {"message": "ok"}))

    # Simulate one request already in flight.
    assert lb.overload_state.try_acquire() is True
    try:
        client = TestClient(lb.app)
        response = client.get("/")
    finally:
        lb.overload_state.release()

    assert response.status_code == 503
    assert response.json() == {"error": "Load balancer overloaded. Try again shortly."}

    status = TestClient(lb.app).get("/lb/status").json()
    assert status["rejected_requests_total"] == 1


def test_overload_counters_update_for_success_and_failure_paths(monkeypatch) -> None:
    backend = BACKENDS[1]
    lb.overload_state.reset_for_tests(max_in_flight=2)
    monkeypatch.setattr(lb, "filter_healthy_backends", lambda _: [backend])
    monkeypatch.setattr(lb, "strategy", RoundRobinStrategy())

    client = TestClient(lb.app)

    monkeypatch.setattr(lb.requests, "get", lambda url, timeout: _FakeResponse(200, {"message": "ok"}))
    ok_response = client.get("/")
    assert ok_response.status_code == 200

    def raise_request_error(url: str, timeout: float):
        raise lb.requests.RequestException("simulated network failure")

    monkeypatch.setattr(lb.requests, "get", raise_request_error)
    failed_response = client.get("/")
    assert failed_response.status_code == 502

    status = client.get("/lb/status").json()
    assert status["active_requests"] == 0
    assert status["peak_active_requests"] == 1
    assert status["rejected_requests_total"] == 0


def test_rejected_requests_do_not_touch_strategy_state(monkeypatch) -> None:
    class _SpyStrategy(LoadBalancingStrategy):
        def __init__(self) -> None:
            self.choose_calls = 0
            self.start_calls = 0
            self.end_calls = 0

        def choose_backend(self, backends):
            self.choose_calls += 1
            return backends[0]

        def on_request_start(self, backend):
            self.start_calls += 1
            return None

        def on_request_end(self, backend, started_context, *, success):
            self.end_calls += 1

    spy = _SpyStrategy()
    lb.strategy = spy
    lb.overload_state.reset_for_tests(max_in_flight=1)

    # Hold one slot to force overload reject.
    assert lb.overload_state.try_acquire() is True
    try:
        response = TestClient(lb.app).get("/")
    finally:
        lb.overload_state.release()

    assert response.status_code == 503
    assert spy.choose_calls == 0
    assert spy.start_calls == 0
    assert spy.end_calls == 0
