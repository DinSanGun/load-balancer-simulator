from __future__ import annotations

import json
from pathlib import Path

import app.visualize_results as vr


def test_run_visualization_emits_overload_chart_when_metrics_present(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scenario_name": "overload_saturation",
        "scenario_description": "x",
        "backend_behaviors": {},
        "benchmark_parameters": {
            "total_requests_per_run": 100,
            "concurrency": 20,
            "load_balancer_max_in_flight": 5,
        },
        "strategies": [
            {
                "strategy": "round_robin",
                "repetitions": 1,
                "total_requests": 100,
                "successful_requests": 80,
                "failed_requests": 0,
                "overload_rejected_requests": 20,
                "average_response_time_ms": 10.0,
                "min_response_time_ms": 1.0,
                "max_response_time_ms": 20.0,
                "average_throughput_rps": 50.0,
                "successful_throughput_rps": 40.0,
                "requests_per_backend": {"backend-1": 80, "__overload_503__": 20},
            },
            {
                "strategy": "least_connections",
                "repetitions": 1,
                "total_requests": 100,
                "successful_requests": 80,
                "failed_requests": 0,
                "overload_rejected_requests": 20,
                "average_response_time_ms": 10.0,
                "min_response_time_ms": 1.0,
                "max_response_time_ms": 20.0,
                "average_throughput_rps": 50.0,
                "successful_throughput_rps": 40.0,
                "requests_per_backend": {"backend-1": 80, "__overload_503__": 20},
            },
            {
                "strategy": "least_response_time",
                "repetitions": 1,
                "total_requests": 100,
                "successful_requests": 80,
                "failed_requests": 0,
                "overload_rejected_requests": 20,
                "average_response_time_ms": 10.0,
                "min_response_time_ms": 1.0,
                "max_response_time_ms": 20.0,
                "average_throughput_rps": 50.0,
                "successful_throughput_rps": 40.0,
                "requests_per_backend": {"backend-1": 80, "__overload_503__": 20},
            },
        ],
    }
    p = tmp_path / "bench.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    out = vr.run_visualization(p, tmp_path / "charts")
    assert any(x.name.endswith("_overload_503.png") for x in out)
    assert len(out) == 4


def test_run_visualization_skips_overload_chart_when_zero(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scenario_name": None,
        "scenario_description": None,
        "backend_behaviors": None,
        "benchmark_parameters": {"total_requests_per_run": 10, "concurrency": 1},
        "strategies": [
            {
                "strategy": "round_robin",
                "repetitions": 1,
                "total_requests": 10,
                "successful_requests": 10,
                "failed_requests": 0,
                "overload_rejected_requests": 0,
                "average_response_time_ms": 1.0,
                "min_response_time_ms": 1.0,
                "max_response_time_ms": 1.0,
                "average_throughput_rps": 10.0,
                "successful_throughput_rps": 10.0,
                "requests_per_backend": {"backend-1": 10},
            },
            {
                "strategy": "least_connections",
                "repetitions": 1,
                "total_requests": 10,
                "successful_requests": 10,
                "failed_requests": 0,
                "overload_rejected_requests": 0,
                "average_response_time_ms": 1.0,
                "min_response_time_ms": 1.0,
                "max_response_time_ms": 1.0,
                "average_throughput_rps": 10.0,
                "successful_throughput_rps": 10.0,
                "requests_per_backend": {"backend-1": 10},
            },
            {
                "strategy": "least_response_time",
                "repetitions": 1,
                "total_requests": 10,
                "successful_requests": 10,
                "failed_requests": 0,
                "overload_rejected_requests": 0,
                "average_response_time_ms": 1.0,
                "min_response_time_ms": 1.0,
                "max_response_time_ms": 1.0,
                "average_throughput_rps": 10.0,
                "successful_throughput_rps": 10.0,
                "requests_per_backend": {"backend-1": 10},
            },
        ],
    }
    p = tmp_path / "bench.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    out = vr.run_visualization(p, tmp_path / "charts")
    assert len(out) == 3
    assert not any("overload_503" in x.name for x in out)


def test_subtitle_includes_overload_total() -> None:
    data = {
        "strategies": [
            {"overload_rejected_requests": 10},
            {"overload_rejected_requests": 5},
            {"overload_rejected_requests": 3},
        ]
    }
    assert vr._total_overload_rejections(data) == 18
    assert "total HTTP 503 overload=18" in vr._subtitle_meta(data)
