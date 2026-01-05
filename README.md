# Hermes ⚚

[![Hermes CI](https://github.com/tanged123/hermes/actions/workflows/ci.yml/badge.svg)](https://github.com/tanged123/hermes/actions/workflows/ci.yml)
[![Format Check](https://github.com/tanged123/hermes/actions/workflows/format.yml/badge.svg)](https://github.com/tanged123/hermes/actions/workflows/format.yml)
[![codecov](https://codecov.io/github/tanged123/hermes/graph/badge.svg)](https://codecov.io/github/tanged123/hermes)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://tanged123.github.io/hermes/)

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

## Quick Start

Hermes uses Nix for reproducible builds. Install [Nix](https://nixos.org/download.html) first.

```bash
# Enter development environment
./scripts/dev.sh

# Run tests
./scripts/test.sh

# Run CI (lint + typecheck + tests)
./scripts/ci.sh

# Run with coverage
./scripts/coverage.sh

# Generate documentation
./scripts/generate_docs.sh

# Clean build artifacts
./scripts/clean.sh

# Install pre-commit hooks (auto-format on commit)
./scripts/install-hooks.sh
```

### Using Hermes

```bash
# Run simulation from config file
hermes run examples/basic_sim.yaml

# Run without WebSocket server (console output only)
hermes run examples/basic_sim.yaml --no-server

# Print schema JSON
hermes schema examples/basic_sim.yaml
```

### Nix Packages

```bash
nix build              # Build hermes package
nix develop            # Enter development shell (includes icarus bindings)
```

### Using as a Dependency

```nix
{
  inputs.hermes.url = "github:tanged123/hermes";

  outputs = { self, nixpkgs, hermes, ... }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      hermesPkg = hermes.packages.x86_64-linux.default;
    in {
      devShells.default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [ hermesPkg ]))
        ];
      };
    };
}
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
