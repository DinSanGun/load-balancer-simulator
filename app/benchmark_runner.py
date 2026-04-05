from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import time

import requests

from .benchmark_scenarios import BenchmarkScenario, get_scenario, list_scenario_names, scenario_backend_behaviors_dict
from .client_simulator import SimulationResult, run_simulation
from .config import BACKENDS, Backend, BackendBehavior
from .healthcheck import tcp_is_reachable


STRATEGIES = ["round_robin", "least_connections", "least_response_time"]


def _build_target_url(host: str, port: int, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"http://{host}:{port}{normalized_path}"


def _wait_for_lb(url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            requests.get(url, timeout=0.5)
            return
        except requests.RequestException:
            time.sleep(0.2)
    raise RuntimeError(f"Load balancer did not become ready: {url}")


def _start_load_balancer(
    strategy: str,
    host: str,
    port: int,
    *,
    lb_max_in_flight: int | None = None,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["LB_STRATEGY"] = strategy
    if lb_max_in_flight is not None:
        env["LB_MAX_IN_FLIGHT"] = str(lb_max_in_flight)
    # Start uvicorn as a child process so runner can benchmark each strategy
    # under the same scenario, one after another.
    return subprocess.Popen(
        [
            "uvicorn",
            "app.load_balancer:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _env_with_backend_behavior(base: dict[str, str], backend: Backend, behavior: BackendBehavior) -> dict[str, str]:
    """Build env for one backend process; matches config.get_backend_behavior env var names."""
    env = dict(base)
    env["BACKEND_NAME"] = backend.name
    prefix = backend.name.upper().replace("-", "_")
    env[f"{prefix}_FIXED_DELAY_MS"] = str(behavior.fixed_delay_ms)
    env[f"{prefix}_JITTER_MS"] = str(behavior.jitter_ms)
    env[f"{prefix}_FAILURE_RATE"] = str(behavior.failure_rate)
    return env


def _start_backend_server(backend: Backend, behavior: BackendBehavior) -> subprocess.Popen[bytes]:
    env = _env_with_backend_behavior(os.environ, backend, behavior)
    return subprocess.Popen(
        [
            "uvicorn",
            "app.backend_server:app",
            "--host",
            backend.host,
            "--port",
            str(backend.port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_backend_tcp(backend: Backend, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if tcp_is_reachable(backend):
            return
        time.sleep(0.15)
    raise RuntimeError(f"Backend did not become reachable: {backend.name} ({backend.host}:{backend.port})")


def _start_backends_for_scenario(scenario: BenchmarkScenario) -> list[subprocess.Popen[bytes]]:
    """Start one uvicorn per backend with behavior from the named scenario."""
    procs: list[subprocess.Popen[bytes]] = []
    by_name = {b.name: b for b in BACKENDS}
    for name, behavior in scenario.backends.items():
        backend = by_name.get(name)
        if backend is None:
            raise ValueError(f"Scenario references unknown backend {name!r}")
        procs.append(_start_backend_server(backend, behavior))
    for name in scenario.backends:
        _wait_for_backend_tcp(by_name[name])
    return procs


def _aggregate_runs(strategy: str, runs: list[SimulationResult]) -> dict[str, object]:
    total_requests = sum(r.total_requests for r in runs)
    successes = sum(r.successful_requests for r in runs)
    failures = sum(r.failed_requests for r in runs)
    overloads = sum(r.overload_rejected_requests for r in runs)
    avg_response = sum(r.average_response_time_ms for r in runs) / len(runs)
    min_response = min(r.min_response_time_ms for r in runs)
    max_response = max(r.max_response_time_ms for r in runs)
    avg_throughput = sum(r.throughput_rps for r in runs) / len(runs)
    avg_success_throughput = sum(r.successful_throughput_rps for r in runs) / len(runs)

    distribution: dict[str, int] = {}
    for run in runs:
        for backend, count in run.requests_per_backend.items():
            distribution[backend] = distribution.get(backend, 0) + count

    return {
        "strategy": strategy,
        "repetitions": len(runs),
        "total_requests": total_requests,
        "successful_requests": successes,
        "failed_requests": failures,
        "overload_rejected_requests": overloads,
        "average_response_time_ms": round(avg_response, 3),
        "min_response_time_ms": round(min_response, 3),
        "max_response_time_ms": round(max_response, 3),
        "average_throughput_rps": round(avg_throughput, 3),
        "successful_throughput_rps": round(avg_success_throughput, 3),
        "requests_per_backend": distribution,
    }


def run_benchmarks(
    total_requests: int,
    concurrency: int,
    path: str,
    timeout: float,
    repetitions: int,
    host: str,
    port: int,
    progress_every: int,
    scenario: BenchmarkScenario | None = None,
    lb_max_in_flight: int | None = None,
) -> dict[str, object]:
    target_url = _build_target_url(host, port, path)
    all_results: dict[str, list[SimulationResult]] = {s: [] for s in STRATEGIES}

    backend_procs: list[subprocess.Popen[bytes]] = []
    try:
        if scenario is not None:
            print(f"Starting backends for scenario={scenario.name!r} ...")
            backend_procs = _start_backends_for_scenario(scenario)

        for strategy in STRATEGIES:
            for rep in range(1, repetitions + 1):
                print(f"Running strategy={strategy} repetition={rep}/{repetitions} ...")
                proc = _start_load_balancer(
                    strategy=strategy,
                    host=host,
                    port=port,
                    lb_max_in_flight=lb_max_in_flight,
                )
                try:
                    _wait_for_lb(target_url)
                    result = run_simulation(
                        total_requests=total_requests,
                        target_url=target_url,
                        timeout_seconds=timeout,
                        concurrency=concurrency,
                        progress_every=progress_every,
                        progress_label=f"{strategy} rep {rep}/{repetitions}",
                    )
                    result.strategy_label = strategy
                    all_results[strategy].append(result)
                finally:
                    _stop_process(proc)
    finally:
        for p in backend_procs:
            _stop_process(p)

    strategy_summaries = [_aggregate_runs(strategy, runs) for strategy, runs in all_results.items()]

    benchmark_parameters: dict[str, object] = {
        "total_requests_per_run": total_requests,
        "concurrency": concurrency,
        "path": path,
        "timeout_seconds": timeout,
        "repetitions_per_strategy": repetitions,
        "target_host": host,
        "target_port": port,
        "backends_started_by_runner": scenario is not None,
        "load_balancer_max_in_flight": lb_max_in_flight,
    }

    out: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scenario_name": scenario.name if scenario else None,
        "scenario_description": scenario.description if scenario else None,
        "backend_behaviors": scenario_backend_behaviors_dict(scenario) if scenario else None,
        "benchmark_parameters": benchmark_parameters,
        "strategies": strategy_summaries,
        "raw_runs": {strategy: [asdict(run) for run in runs] for strategy, runs in all_results.items()},
    }
    return out


def save_outputs(summary: dict[str, object]) -> tuple[Path, Path]:
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = results_dir / f"benchmark_summary_{timestamp}.json"
    csv_path = results_dir / f"benchmark_comparison_{timestamp}.csv"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "scenario_name",
                "strategy",
                "repetitions",
                "total_requests",
                "successful_requests",
                "failed_requests",
                "overload_rejected_requests",
                "average_response_time_ms",
                "min_response_time_ms",
                "max_response_time_ms",
                "average_throughput_rps",
                "successful_throughput_rps",
                "requests_per_backend",
            ]
        )
        scenario_name = summary.get("scenario_name") or ""
        for row in summary["strategies"]:
            writer.writerow(
                [
                    scenario_name,
                    row["strategy"],
                    row["repetitions"],
                    row["total_requests"],
                    row["successful_requests"],
                    row["failed_requests"],
                    row["overload_rejected_requests"],
                    row["average_response_time_ms"],
                    row["min_response_time_ms"],
                    row["max_response_time_ms"],
                    row["average_throughput_rps"],
                    row["successful_throughput_rps"],
                    json.dumps(row["requests_per_backend"], sort_keys=True),
                ]
            )

    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark all load balancing strategies")
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help=(
            "Named backend behavior preset (starts backends automatically). "
            "If omitted, start backends yourself with desired env vars. "
            f"Options: {', '.join(list_scenario_names())}"
        ),
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Print available scenario names and exit",
    )
    parser.add_argument("--requests", type=int, default=200, help="Requests per run (default: 200)")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent request workers (default: 1)")
    parser.add_argument("--path", type=str, default="/", help="Request path (default: /)")
    parser.add_argument("--timeout", type=float, default=3.0, help="Request timeout in seconds (default: 3.0)")
    parser.add_argument("--repetitions", type=int, default=1, help="Runs per strategy (default: 1)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Load balancer host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Load balancer port (default: 8000)")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print progress every N completed requests per run (0 disables, default: 100)",
    )
    parser.add_argument(
        "--lb-max-in-flight",
        type=int,
        default=None,
        help=(
            "If set, each benchmark load balancer process uses this LB_MAX_IN_FLIGHT "
            "(lower + higher --concurrency triggers 503 overload). Omit for default (100)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_scenarios:
        for name in list_scenario_names():
            sc = get_scenario(name)
            print(f"{sc.name}: {sc.description}")
        sys.exit(0)

    scenario_obj: BenchmarkScenario | None = None
    if args.scenario is not None:
        scenario_obj = get_scenario(args.scenario)

    if args.requests <= 0:
        raise ValueError("--requests must be > 0")
    if args.concurrency <= 0:
        raise ValueError("--concurrency must be > 0")
    if args.repetitions <= 0:
        raise ValueError("--repetitions must be > 0")
    if args.progress_every < 0:
        raise ValueError("--progress-every must be 0 or greater")
    if args.lb_max_in_flight is not None and args.lb_max_in_flight < 1:
        raise ValueError("--lb-max-in-flight must be >= 1 when provided")

    summary = run_benchmarks(
        total_requests=args.requests,
        concurrency=args.concurrency,
        path=args.path,
        timeout=args.timeout,
        repetitions=args.repetitions,
        host=args.host,
        port=args.port,
        progress_every=args.progress_every,
        scenario=scenario_obj,
        lb_max_in_flight=args.lb_max_in_flight,
    )
    json_path, csv_path = save_outputs(summary)

    print("\n=== Benchmark Complete ===")
    if scenario_obj:
        print(f"Scenario: {scenario_obj.name} — {scenario_obj.description}")
    print(f"JSON summary: {json_path}")
    print(f"CSV summary:  {csv_path}")
    print("Strategy overview:")
    for row in summary["strategies"]:
        print(
            f"- {row['strategy']}: avg={row['average_response_time_ms']} ms, "
            f"throughput={row['average_throughput_rps']} req/s, "
            f"success={row['successful_requests']}/{row['total_requests']}, "
            f"overload_503={row['overload_rejected_requests']}"
        )


if __name__ == "__main__":
    main()

