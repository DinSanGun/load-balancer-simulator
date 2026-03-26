# Load Balancer Simulator

A Python FastAPI-based cloud load balancer simulator designed to compare different traffic distribution strategies under simulated load.

## Overview

This project simulates a cloud-style load balancer that distributes HTTP requests across multiple backend service instances.  
It focuses on understanding how different load balancing strategies affect performance and resource utilization.

## Features (Planned)

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

Project setup and run instructions will be added as development progresses.

## Goals

- Understand load balancing strategies in distributed systems
- Simulate real-world traffic patterns
- Build a modular system that can be extended (e.g., HTTPS/TLS support)

## Future Improvements

- HTTPS/TLS support
- Failure simulation (instance crashes)
- Visualization of results