# Load Balancer Simulator

A Python FastAPI-based cloud load balancer simulator designed to compare different traffic distribution strategies under simulated load.

## Overview

This project simulates a cloud-style load balancer that distributes HTTP requests across multiple backend service instances.  
It focuses on understanding how different load balancing strategies affect performance and resource utilization.

## MVP (Implemented)

- 3 backend services (FastAPI)
  - `GET /` returns a message identifying the server (with a small random delay)
  - `GET /health` returns status OK
- 1 load balancer service (FastAPI)
  - `GET /` forwards requests to backends using HTTP (`requests`)
  - Strategy-based routing:
    - Round Robin
    - Least Connections
    - Least Response Time
  - TCP reachability health checks (Python sockets) to skip unhealthy backends
  - Logs which backend handled each request
- 1 client simulator script
  - Sends configurable number of `GET /` requests to the load balancer
  - Collects basic performance metrics
  - Saves simulation output to `results/*.json`

## Features (Planned / Later)

- Multiple backend services (FastAPI)
- Load balancer with support for:
  - Round Robin
  - Least Connections
  - Least Response Time
- HTTP request forwarding
- TCP-based health checks for backend availability
- Performance metrics:
  - Response time
  - Load distribution per instance
- Results export (JSON)

## Technologies

- Python
- FastAPI
- HTTP (request routing)
- TCP (health checks)

## Getting Started

### Project Structure

- `app/config.py`: backend list + simple settings (ports, delays, timeouts)
- `app/backend_server.py`: backend FastAPI service (`GET /` and `GET /health`)
- `app/load_balancer.py`: load balancer FastAPI service (`GET /` forwards to backends)
- `app/healthcheck.py`: TCP health check logic (socket connect)
- `app/strategies.py`: strategy abstraction + all strategy implementations
- `app/client_simulator.py`: sends requests + collects and saves metrics
- `app/benchmark_runner.py`: runs all strategies under same scenario and saves comparison files

### Setup

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the 3 backend services

Open 3 terminals (or run in the background). Each backend runs the same code, but on a different port + name.

Terminal 1:

```bash
source .venv/bin/activate
BACKEND_NAME=backend-1 uvicorn app.backend_server:app --host 127.0.0.1 --port 8001
```

Terminal 2:

```bash
source .venv/bin/activate
BACKEND_NAME=backend-2 uvicorn app.backend_server:app --host 127.0.0.1 --port 8002
```

Terminal 3:

```bash
source .venv/bin/activate
BACKEND_NAME=backend-3 uvicorn app.backend_server:app --host 127.0.0.1 --port 8003
```

Quick checks:

```bash
curl http://127.0.0.1:8001/
curl http://127.0.0.1:8002/health
```

### Run the load balancer

In a 4th terminal:

```bash
source .venv/bin/activate
uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
```

Or choose a strategy explicitly:

```bash
source .venv/bin/activate
LB_STRATEGY=round_robin uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
```

```bash
source .venv/bin/activate
LB_STRATEGY=least_connections uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
```

```bash
source .venv/bin/activate
LB_STRATEGY=least_response_time uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
```

### Run the client simulator

Run the simulator from the project root (with backend services + load balancer running):

```bash
source .venv/bin/activate
python -m app.client_simulator --requests 200 --concurrency 1 --url http://127.0.0.1:8000/ --strategy-label round_robin
```

What it collects per run:
- total requests
- successful requests
- failed requests
- average response time (ms)
- min response time (ms)
- max response time (ms)
- throughput (requests / second)
- requests handled per backend server

Output:
- prints a summary in console
- writes one JSON file to `results/` (for example: `results/simulation_round_robin_YYYYMMDD_HHMMSS.json`)

### Compare strategies (run one at a time)

1. Start backend services (`8001`, `8002`, `8003`)
2. Start load balancer with one strategy (example below)
3. Run simulator and save results with matching `--strategy-label`
4. Stop load balancer, restart with another strategy, repeat

Example strategy runs:

```bash
# Round Robin
LB_STRATEGY=round_robin uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
python -m app.client_simulator --requests 200 --strategy-label round_robin
```

```bash
# Least Connections
LB_STRATEGY=least_connections uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
python -m app.client_simulator --requests 200 --strategy-label least_connections
```

```bash
# Least Response Time
LB_STRATEGY=least_response_time uvicorn app.load_balancer:app --host 127.0.0.1 --port 8000
python -m app.client_simulator --requests 200 --strategy-label least_response_time
```

### Benchmark all strategies (same workload)

Use the benchmark runner to execute:
- `round_robin`
- `least_connections`
- `least_response_time`

with the same request count, concurrency, path, and timeout.

Important:
- Keep backend servers running (`8001`, `8002`, `8003`)
- Do not run another load balancer manually on benchmark host/port (`127.0.0.1:8000` by default), because the runner starts/stops it per strategy.

Example:

```bash
source .venv/bin/activate
python -m app.benchmark_runner --requests 300 --concurrency 5 --path / --timeout 3.0 --repetitions 2
```

Benchmark outputs:
- JSON summary: `results/benchmark_summary_*.json`
- CSV comparison: `results/benchmark_comparison_*.csv`

The benchmark summary includes, per strategy:
- total requests
- successful requests
- failed requests
- average/min/max response time
- average throughput
- backend request distribution

Now send requests to the load balancer:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/
```

You should see:
- Requests rotate between `backend-1`, `backend-2`, `backend-3` (round robin)
- Response header `X-Backend` telling you which backend was chosen
- Load balancer logs printing which backend handled each request

### How the key parts work (in plain terms)

- **HTTP forwarding**: the load balancer receives your `GET /`, then makes its own `GET /` HTTP request to a chosen backend using `requests.get(...)`, and returns the backend’s JSON response back to you.
- **TCP health checks**: before choosing a backend, the load balancer tries to open a TCP connection to each backend’s `(host, port)` using `socket.create_connection(...)`. If it can connect, that backend is considered reachable.
- **Round robin**: the load balancer keeps an internal index pointing to “who’s next”. Every request uses the next backend in the list and then increments the index (wrapping around at the end).
- **Least connections**: the load balancer tracks active request counts per backend, picks the one with the smallest count, increments before forwarding, and decrements when the request finishes or fails.
- **Least response time**: the load balancer measures backend response durations and keeps a simple running average per backend, then picks the backend with the lowest average response time.

## Goals

- Understand load balancing strategies in distributed systems
- Simulate real-world traffic patterns
- Build a modular system that can be extended (e.g., HTTPS/TLS support)

## Future Improvements

- HTTPS/TLS support
- Failure simulation (instance crashes)
- Visualization of results