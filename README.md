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

## Features (Planned / Later)

- Multiple backend services (FastAPI)
- Load balancer with support for:
  - Round Robin
  - Least Connections
  - Least Response Time
- HTTP request forwarding
- TCP-based health checks for backend availability
- Client simulator for generating high request loads
- Performance metrics:
  - Response time
  - Throughput
  - Load distribution per instance
- Results export (CSV / JSON)

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