# Hermes

**System Test and Execution Platform (STEP) for Aerospace Simulation**

Hermes orchestrates simulation modules, routes signals between them, and serves telemetry to visualization clients. It is the middleware layer between physics engines like Icarus and visualization tools like Daedalus.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HERMES (STEP)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  Icarus  │  │  GNC SW  │  │ Injection│              │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       └─────────────┴─────────────┘                    │
│              Signal Bus (routing)                       │
│                      │                                 │
│         ┌───────────┴───────────┐                      │
│         │  WebSocket Server     │                      │
│         └───────────────────────┘                      │
└─────────────────────────────────────────────────────────┘
                       │
              ┌────────┴────────┐
              │    Daedalus     │
              └─────────────────┘
```

## Installation (Nix)

Hermes uses Nix flakes for reproducible development. The flake takes Icarus
as an input, providing the pybind11 Python bindings automatically.

```bash
# Enter development shell
nix develop

# Or with direnv (recommended)
echo "use flake" > .envrc
direnv allow
```

The dev shell includes:
- Python 3.11+ with all dependencies
- Icarus Python bindings (pybind11)
- ruff, mypy, pytest

### Without Nix

```bash
# Ensure Icarus Python bindings are installed and in PYTHONPATH
pip install -e ".[dev]"
```

## Quick Start

```bash
# Run simulation from config file
hermes run examples/basic_sim.yaml

# Run without WebSocket server (console output only)
hermes run examples/basic_sim.yaml --no-server

# Print schema JSON
hermes schema examples/basic_sim.yaml
```

## Configuration

```yaml
version: "0.2"

modules:
  icarus:
    adapter: icarus
    config: ./icarus_config.yaml

  injection:
    adapter: injection
    signals:
      - disturbance.force.x
      - disturbance.force.y

wiring:
  - src: injection.disturbance.force.x
    dst: icarus.Environment.external_force.x
    gain: 1.0
    offset: 0.0

execution:
  mode: afap           # afap, realtime, paused
  rate_hz: 100.0
  end_time: 60.0

server:
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

## Development

```bash
# Run tests (inside nix develop)
pytest

# Run tests with coverage
pytest --cov=hermes

# Lint and format
ruff check src tests
ruff format src tests

# Or use nix formatter (includes ruff + nixfmt)
nix fmt

# Type check
mypy src

# Build package
nix build
```

## Protocol

Hermes uses a two-channel WebSocket protocol:

**Control Channel (JSON):**
- Schema on connect
- Commands: pause, resume, reset, step, set, subscribe

**Telemetry Channel (Binary):**
- 16-byte header: frame (u32) + time (f64) + count (u16) + reserved
- Payload: signal values as f64 array

See `docs/protocol.md` for full specification.

## License

MIT
