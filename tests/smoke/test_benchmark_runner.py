from __future__ import annotations

import json

import app.benchmark_runner as br
from app.client_simulator import SimulationResult


class _FakeProcess:
    def terminate(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        return None


def test_benchmark_runner_creates_summary_files_with_expected_structure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(br, "_start_load_balancer", lambda strategy, host, port: _FakeProcess())
    monkeypatch.setattr(br, "_wait_for_lb", lambda url, timeout_seconds=10.0: None)
    monkeypatch.setattr(br, "_stop_process", lambda proc: None)

    def fake_run_simulation(
        total_requests: int,
        target_url: str,
        timeout_seconds: float,
        concurrency: int = 1,
        progress_every: int = 0,
        progress_label: str = "simulation",
    ) -> SimulationResult:
        strategy = progress_label.split(" rep ")[0]
        return SimulationResult(
            total_requests=total_requests,
            successful_requests=total_requests,
            failed_requests=0,
            average_response_time_ms=100.0,
            min_response_time_ms=90.0,
            max_response_time_ms=120.0,
            total_duration_seconds=1.0,
            throughput_rps=float(total_requests),
            requests_per_backend={"backend-1": total_requests},
            target_url=target_url,
            strategy_label=strategy,
            generated_at="2026-01-01T00:00:00Z",
        )

    monkeypatch.setattr(br, "run_simulation", fake_run_simulation)
    monkeypatch.chdir(tmp_path)

    summary = br.run_benchmarks(
        total_requests=5,
        concurrency=1,
        path="/",
        timeout=1.0,
        repetitions=1,
        host="127.0.0.1",
        port=8000,
        progress_every=0,
    )
    json_path, csv_path = br.save_outputs(summary)

    assert json_path.exists()
    assert csv_path.exists()

    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(parsed.keys()) == {"generated_at", "scenario", "strategies", "raw_runs"}
    assert len(parsed["strategies"]) == 3
