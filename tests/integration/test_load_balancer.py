from __future__ import annotations

from fastapi.testclient import TestClient

import app.load_balancer as lb
from app.config import BACKENDS
from app.strategies import RoundRobinStrategy


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


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
