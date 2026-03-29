# Demo results and charts

This folder contains **checked-in sample outputs** from the benchmark runner so you can inspect **JSON**, **CSV**, and **PNG charts** without running anything locally.

**[`charts/`](charts/)** holds a small set of **renamed PNGs** used in the main README’s [Demo / Example Results](../README.md#demo--example-results) section (same charts as in the scenario subfolders, copied under clearer filenames).

Each subdirectory is one **named scenario** (see `app/benchmark_scenarios.py`). All runs used the same workload for fair comparison:

- **40** requests per strategy run  
- **2** concurrent client workers  
- **1** repetition per strategy  

(Regenerate your own files anytime with `app.benchmark_runner` and `app.visualize_results`; see the main [README](../README.md).)

## Layout per scenario

| File | Description |
|------|-------------|
| `benchmark_summary.json` | Full self-describing benchmark output (scenario, backend behaviors, per-strategy metrics, `raw_runs`). |
| `benchmark_comparison.csv` | Same run as a flat CSV row per strategy. |
| `benchmark_summary_response_time.png` | Bar chart: average response time (ms) per strategy. |
| `benchmark_summary_throughput.png` | Bar chart: average throughput (req/s) per strategy. |
| `benchmark_summary_backend_distribution.png` | Grouped bars: request counts per backend per strategy. |

## Scenarios included

| Directory | Scenario | Idea |
|-----------|----------|------|
| `balanced/` | `balanced` | Similar backends; moderate delay and jitter; no simulated failures. |
| `flaky_backend/` | `flaky_backend` | One backend with intermittent simulated HTTP 500 responses. |
| `one_slow_backend/` | `one_slow_backend` | One backend much slower than the others. |

## Regenerate charts from the JSON

From the repository root:

```bash
source .venv/bin/activate
python -m app.visualize_results examples/balanced/benchmark_summary.json -o examples/balanced
```

## Note on success counts

Occasional **failed** client requests can appear under real timing (timeouts, short runs). The JSON files record exact `successful_requests` / `failed_requests` per strategy.
