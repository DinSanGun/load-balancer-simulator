from __future__ import annotations

import app.client_simulator as cs
from app.config import LB_OVERLOAD_REQUEST_LABEL, LOAD_BALANCER_OVERLOAD_ERROR_TEXT


class _Resp:
    def __init__(self, status_code: int, headers: dict | None = None, payload: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self) -> dict:
        return dict(self._payload)


def test_perform_request_success(monkeypatch) -> None:
    monkeypatch.setattr(
        cs.requests,
        "get",
        lambda url, timeout: _Resp(200, {"X-Backend": "backend-1"}, {"message": "ok"}),
    )
    outcome, ms, label = cs._perform_request("http://127.0.0.1:8000/", 3.0)
    assert outcome == "success"
    assert ms > 0
    assert label == "backend-1"


def test_perform_request_overload_503(monkeypatch) -> None:
    monkeypatch.setattr(
        cs.requests,
        "get",
        lambda url, timeout: _Resp(503, {}, {"error": LOAD_BALANCER_OVERLOAD_ERROR_TEXT}),
    )
    outcome, ms, label = cs._perform_request("http://127.0.0.1:8000/", 3.0)
    assert outcome == "overload"
    assert ms > 0
    assert label == LB_OVERLOAD_REQUEST_LABEL


def test_perform_request_503_no_backends_is_failure_not_overload(monkeypatch) -> None:
    monkeypatch.setattr(
        cs.requests,
        "get",
        lambda url, timeout: _Resp(503, {}, {"error": "No healthy backends available"}),
    )
    outcome, ms, label = cs._perform_request("http://127.0.0.1:8000/", 3.0)
    assert outcome == "failure"
    assert label == "http_error"


def test_run_simulation_buckets_sum_to_total(monkeypatch) -> None:
    outcomes = ["success", "overload", "failure", "success"]

    def fake_perform(url: str, timeout: float) -> tuple[str, float, str]:
        o = outcomes.pop(0)
        if o == "success":
            return "success", 10.0, "b1"
        if o == "overload":
            return "overload", 2.0, LB_OVERLOAD_REQUEST_LABEL
        return "failure", 0.0, "request_error"

    monkeypatch.setattr(cs, "_perform_request", fake_perform)
    result = cs.run_simulation(
        total_requests=4,
        target_url="http://x/",
        timeout_seconds=1.0,
        concurrency=1,
        progress_every=0,
    )
    assert result.successful_requests == 2
    assert result.overload_rejected_requests == 1
    assert result.failed_requests == 1
    assert result.successful_requests + result.overload_rejected_requests + result.failed_requests == 4
