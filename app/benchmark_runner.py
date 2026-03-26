from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import subprocess
import time

import requests

from .client_simulator import SimulationResult, run_simulation


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


def _start_load_balancer(strategy: str, host: str, port: int) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["LB_STRATEGY"] = strategy
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


def _aggregate_runs(strategy: str, runs: list[SimulationResult]) -> dict[str, object]:
    total_requests = sum(r.total_requests for r in runs)
    successes = sum(r.successful_requests for r in runs)
    failures = sum(r.failed_requests for r in runs)
    avg_response = sum(r.average_response_time_ms for r in runs) / len(runs)
    min_response = min(r.min_response_time_ms for r in runs)
    max_response = max(r.max_response_time_ms for r in runs)
    avg_throughput = sum(r.throughput_rps for r in runs) / len(runs)

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
        "average_response_time_ms": round(avg_response, 3),
        "min_response_time_ms": round(min_response, 3),
        "max_response_time_ms": round(max_response, 3),
        "average_throughput_rps": round(avg_throughput, 3),
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
) -> dict[str, object]:
    target_url = _build_target_url(host, port, path)
    all_results: dict[str, list[SimulationResult]] = {s: [] for s in STRATEGIES}

    for strategy in STRATEGIES:
        for rep in range(1, repetitions + 1):
            print(f"Running strategy={strategy} repetition={rep}/{repetitions} ...")
            proc = _start_load_balancer(strategy=strategy, host=host, port=port)
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

    strategy_summaries = [_aggregate_runs(strategy, runs) for strategy, runs in all_results.items()]
    return {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "scenario": {
            "total_requests_per_run": total_requests,
            "concurrency": concurrency,
            "path": path,
            "timeout_seconds": timeout,
            "repetitions_per_strategy": repetitions,
            "target_host": host,
            "target_port": port,
        },
        "strategies": strategy_summaries,
        "raw_runs": {strategy: [asdict(run) for run in runs] for strategy, runs in all_results.items()},
    }


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
                "strategy",
                "repetitions",
                "total_requests",
                "successful_requests",
                "failed_requests",
                "average_response_time_ms",
                "min_response_time_ms",
                "max_response_time_ms",
                "average_throughput_rps",
                "requests_per_backend",
            ]
        )
        for row in summary["strategies"]:
            writer.writerow(
                [
                    row["strategy"],
                    row["repetitions"],
                    row["total_requests"],
                    row["successful_requests"],
                    row["failed_requests"],
                    row["average_response_time_ms"],
                    row["min_response_time_ms"],
                    row["max_response_time_ms"],
                    row["average_throughput_rps"],
                    json.dumps(row["requests_per_backend"], sort_keys=True),
                ]
            )

    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark all load balancing strategies")
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.requests <= 0:
        raise ValueError("--requests must be > 0")
    if args.concurrency <= 0:
        raise ValueError("--concurrency must be > 0")
    if args.repetitions <= 0:
        raise ValueError("--repetitions must be > 0")
    if args.progress_every < 0:
        raise ValueError("--progress-every must be 0 or greater")

    summary = run_benchmarks(
        total_requests=args.requests,
        concurrency=args.concurrency,
        path=args.path,
        timeout=args.timeout,
        repetitions=args.repetitions,
        host=args.host,
        port=args.port,
        progress_every=args.progress_every,
    )
    json_path, csv_path = save_outputs(summary)

    print("\n=== Benchmark Complete ===")
    print(f"JSON summary: {json_path}")
    print(f"CSV summary:  {csv_path}")
    print("Strategy overview:")
    for row in summary["strategies"]:
        print(
            f"- {row['strategy']}: avg={row['average_response_time_ms']} ms, "
            f"throughput={row['average_throughput_rps']} req/s, "
            f"success={row['successful_requests']}/{row['total_requests']}"
        )


if __name__ == "__main__":
    main()

