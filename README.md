# Hermes ⚚

[![Hermes CI](https://github.com/tanged123/hermes/actions/workflows/ci.yml/badge.svg)](https://github.com/tanged123/hermes/actions/workflows/ci.yml)
[![Format Check](https://github.com/tanged123/hermes/actions/workflows/format.yml/badge.svg)](https://github.com/tanged123/hermes/actions/workflows/format.yml)
[![codecov](https://codecov.io/github/tanged123/hermes/graph/badge.svg)](https://codecov.io/github/tanged123/hermes)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://tanged123.github.io/hermes/)

**Multi-Process Simulation Orchestration Platform**

Hermes coordinates simulation modules running as separate processes, enabling language-agnostic integration (C, C++, Python, Rust) through high-performance POSIX IPC. It provides deterministic execution scheduling, real-time pacing, and runtime inspection capabilities.

## Why Hermes?

Modern simulations often need to integrate heterogeneous components:
- Physics engines in C++
- Control systems in Python
- Sensor models in Rust

Hermes solves this by using **POSIX shared memory** for zero-copy signal exchange and **semaphores** for microsecond-latency synchronization—all configured via YAML, no recompilation needed.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           HERMES CORE                                │
├─────────────────────────────────────────────────────────────────────┤
│  Scheduler          Process Manager           Data Backplane         │
│  • realtime         • Module lifecycle        • POSIX Shared Memory │
│  • afap             • Subprocess mgmt         • Semaphore barriers   │
│  • single_frame     • Coordination            • Signal registry      │
├─────────────────────────────────────────────────────────────────────┤
│        ┌───────────────────┼───────────────────┐                    │
│        ▼                   ▼                   ▼                    │
│  ┌──────────┐       ┌──────────┐       ┌──────────┐                │
│  │ Module A │       │ Module B │       │ Module C │                │
│  │ (C/C++)  │       │ (Python) │       │ (Rust)   │                │
│  └──────────┘       └──────────┘       └──────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

Hermes uses Nix for reproducible builds. Install [Nix](https://nixos.org/download.html) first.

```bash
# Enter development environment
nix develop

# Run CI (lint + typecheck + tests)
./scripts/ci.sh

# Validate a configuration
python -m hermes.cli.main validate examples/basic_sim.yaml

# Run a simulation
python -m hermes.cli.main run examples/basic_sim.yaml
```

## Configuration

```yaml
version: "0.2"

modules:
  vehicle:
    type: script                    # script | process | inproc
    script: ./vehicle.py
    signals:
      - name: position.x
        type: f64
        unit: m
      - name: velocity.x
        type: f64
        unit: m/s
        writable: true

  controller:
    type: process
    executable: ./controller_bin
    config: ./controller.yaml

wiring:
  - src: vehicle.position.x
    dst: controller.position_input
    gain: 1.0
    offset: 0.0

execution:
  mode: afap                        # afap | realtime | single_frame
  rate_hz: 100.0
  end_time: 60.0
  schedule:                         # Explicit execution order
    - vehicle
    - controller

server:
  enabled: false                    # WebSocket server (Phase 2)
```

## Execution Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `afap` | As fast as possible | Batch runs, Monte Carlo |
| `realtime` | Paced to wall-clock | Hardware-in-the-loop, visualization |
| `single_frame` | Manual stepping | Debugging, scripted scenarios |

## Core Components

### Scheduler
Controls simulation execution with support for multiple operating modes, pause/resume, and async callbacks.

### ProcessManager
Manages module subprocess lifecycles—spawning, staging, stepping, and graceful termination.

### SharedMemoryManager
Zero-copy signal exchange via POSIX shared memory with header tracking (frame, time, signal count).

### FrameBarrier
Semaphore-based synchronization ensuring all modules execute in lockstep each frame.

### SimulationAPI
Python API for runtime inspection and injection into running simulations.

## Scripting API

```python
from hermes.scripting.api import SimulationAPI

with SimulationAPI("/hermes_sim") as sim:
    # Read signals
    pos = sim.get("vehicle.position.x")

    # Write signals
    sim.set("controller.thrust_cmd", 1000.0)

    # Batch operations
    state = sim.sample(["vehicle.position.x", "vehicle.velocity.x"])

    # Wait for frame
    sim.wait_frame(100, timeout=10.0)
```

## Development

```bash
# Inside nix develop
pytest                          # Run tests
pytest --cov=hermes             # With coverage
ruff check src tests            # Lint
mypy src                        # Type check
nix fmt                         # Format all files
```

## Documentation

- [Overview](docs/user_guide/overview.md) - What Hermes is and why
- [Architecture](docs/user_guide/architecture.md) - Core classes and data flow
- [Quickstart](docs/user_guide/quickstart.md) - Get running in minutes

## Project Status

**Phase 1 Complete:**
- POSIX shared memory backplane
- Semaphore synchronization
- YAML configuration with Pydantic validation
- Process lifecycle management
- Multi-mode scheduler (realtime/afap/single_frame)
- CLI (run, validate, list-signals)
- Scripting API for inspection/injection
- 66 unit tests

**Coming in Phase 2:**
- WebSocket server for real-time telemetry
- Binary telemetry encoding
- Icarus physics engine integration

## License

MIT
