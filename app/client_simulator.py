from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import time

import requests


@dataclass
class SimulationResult:
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    requests_per_backend: dict[str, int]
    target_url: str
    strategy_label: str
    generated_at: str


def run_simulation(total_requests: int, target_url: str, timeout_seconds: float) -> SimulationResult:
    """
    Send many GET requests to the load balancer and collect basic metrics.

    This is intentionally sequential (one request at a time) to keep logic easy
    to understand for learning and interviews.
    """

    successes = 0
    failures = 0
    durations_ms: list[float] = []
    backend_counter: Counter[str] = Counter()

    for _ in range(total_requests):
        started = time.perf_counter()
        try:
            response = requests.get(target_url, timeout=timeout_seconds)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            durations_ms.append(elapsed_ms)

            if 200 <= response.status_code < 300:
                successes += 1
            else:
                failures += 1

            # Preferred source: response header added by load balancer.
            backend_name = response.headers.get("X-Backend")
            if not backend_name:
                # Fallback: parse JSON payload if header is missing.
                try:
                    data = response.json()
                    backend_name = str(data.get("backend", "unknown"))
                except ValueError:
                    backend_name = "unknown"
            backend_counter[backend_name] += 1
        except requests.RequestException:
            failures += 1

    avg_ms = sum(durations_ms) / len(durations_ms) if durations_ms else 0.0
    min_ms = min(durations_ms) if durations_ms else 0.0
    max_ms = max(durations_ms) if durations_ms else 0.0

    return SimulationResult(
        total_requests=total_requests,
        successful_requests=successes,
        failed_requests=failures,
        average_response_time_ms=round(avg_ms, 3),
        min_response_time_ms=round(min_ms, 3),
        max_response_time_ms=round(max_ms, 3),
        requests_per_backend=dict(backend_counter),
        target_url=target_url,
        strategy_label="unknown",
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )


def save_result(result: SimulationResult, strategy_label: str) -> Path:
    """
    Save simulation result to `results/` as JSON.
    """

    result.strategy_label = strategy_label
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_strategy = strategy_label.replace(" ", "_").lower()
    path = results_dir / f"simulation_{safe_strategy}_{timestamp}.json"
    path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return path


def print_summary(result: SimulationResult, output_path: Path) -> None:
    print("\n=== Simulation Summary ===")
    print(f"Target URL:            {result.target_url}")
    print(f"Strategy label:        {result.strategy_label}")
    print(f"Total requests:        {result.total_requests}")
    print(f"Successful requests:   {result.successful_requests}")
    print(f"Failed requests:       {result.failed_requests}")
    print(f"Average response (ms): {result.average_response_time_ms}")
    print(f"Min response (ms):     {result.min_response_time_ms}")
    print(f"Max response (ms):     {result.max_response_time_ms}")
    print("Requests per backend:")
    if result.requests_per_backend:
        for backend_name, count in sorted(result.requests_per_backend.items()):
            print(f"  - {backend_name}: {count}")
    else:
        print("  - (none)")
    print(f"Saved result:          {output_path}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple load balancer client simulator")
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of GET requests to send (default: 100)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:8000/",
        help="Load balancer URL to test (default: http://127.0.0.1:8000/)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Request timeout in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--strategy-label",
        type=str,
        default="unknown",
        help="Label to store in result file (example: round_robin)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.requests <= 0:
        raise ValueError("--requests must be greater than 0")

    result = run_simulation(
        total_requests=args.requests,
        target_url=args.url,
        timeout_seconds=args.timeout,
    )
    output_path = save_result(result, args.strategy_label)
    print_summary(result, output_path)


if __name__ == "__main__":
    main()

