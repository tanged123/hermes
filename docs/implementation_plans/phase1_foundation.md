# Phase 1: Foundation

**Goal:** Minimal working system with Icarus adapter
**Status:** Not Started
**Exit Criteria:** `hermes run` steps Icarus and prints telemetry to console

---

## Overview

Phase 1 establishes the foundational infrastructure for Hermes. By the end of this phase, we'll have a working simulation loop that can load Icarus via pybind11 bindings, step the simulation, and output telemetry to the console.

## Dependencies

- Nix flake configured with Icarus pybind11 bindings
- Python 3.11+
- Development tools (ruff, mypy, pytest)

---

## Task 1.1: Project Setup

**Issue ID:** `HRM-001`
**Priority:** Critical
**Blocked By:** None

### Objective
Set up the Python project structure with proper packaging, dev dependencies, and tooling configuration.

### Steps

1. **Create `pyproject.toml`**
   ```toml
   [project]
   name = "hermes"
   version = "0.1.0"
   description = "Simulation Orchestration Platform"
   requires-python = ">=3.11"
   dependencies = [
       "websockets>=12.0",
       "pyyaml>=6.0",
       "pydantic>=2.5",
       "structlog>=24.1",
       "numpy>=1.26",
       "click>=8.1",
   ]

   [project.optional-dependencies]
   dev = [
       "pytest>=8.0",
       "pytest-asyncio>=0.23",
       "pytest-cov>=4.1",
       "ruff>=0.1",
       "mypy>=1.8",
       "pre-commit>=3.6",
   ]

   [project.scripts]
   hermes = "hermes.cli.main:main"

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"
   ```

2. **Create directory structure**
   ```
   src/hermes/
   ├── __init__.py
   ├── py.typed
   ├── core/
   │   └── __init__.py
   ├── adapters/
   │   └── __init__.py
   ├── server/
   │   └── __init__.py
   └── cli/
       └── __init__.py
   ```

3. **Configure ruff** (in `pyproject.toml`)
   ```toml
   [tool.ruff]
   target-version = "py311"
   line-length = 88

   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM"]

   [tool.ruff.format]
   quote-style = "double"
   ```

4. **Configure mypy** (in `pyproject.toml`)
   ```toml
   [tool.mypy]
   strict = true
   python_version = "3.11"
   warn_return_any = true
   warn_unused_ignores = true
   ```

5. **Configure pytest** (in `pyproject.toml`)
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   testpaths = ["tests"]
   ```

6. **Create `src/hermes/__init__.py`** with version
   ```python
   """Hermes - Simulation Orchestration Platform."""
   __version__ = "0.1.0"
   ```

7. **Create development scripts**
   - `scripts/dev.sh` - Enter Nix environment
   - `scripts/test.sh` - Run pytest
   - `scripts/ci.sh` - Full CI (lint + typecheck + tests)

### Acceptance Criteria
- [ ] `pip install -e .` succeeds
- [ ] `ruff check src` runs without config errors
- [ ] `mypy src` runs (may have errors, but config works)
- [ ] `pytest` runs (may have no tests yet)
- [ ] `hermes --help` shows CLI usage

### Estimated Effort
Small (< 1 hour)

---

## Task 1.2: Core Abstractions

**Issue ID:** `HRM-002`
**Priority:** Critical
**Blocked By:** HRM-001

### Objective
Implement the core abstractions: `ModuleAdapter` protocol, `SignalDescriptor`, and `SignalBus`.

### Steps

1. **Create `src/hermes/core/module.py`**

   ```python
   from typing import Protocol, runtime_checkable
   from hermes.core.signal import SignalDescriptor

   @runtime_checkable
   class ModuleAdapter(Protocol):
       """Interface for simulation modules."""

       @property
       def name(self) -> str:
           """Unique module identifier."""
           ...

       @property
       def signals(self) -> dict[str, SignalDescriptor]:
           """Available signals with metadata."""
           ...

       def stage(self) -> None:
           """Prepare for execution. Called once before run loop."""
           ...

       def step(self, dt: float) -> None:
           """Advance module by dt seconds."""
           ...

       def reset(self) -> None:
           """Return to initial conditions."""
           ...

       def get(self, signal: str) -> float:
           """Get signal value by local name."""
           ...

       def set(self, signal: str, value: float) -> None:
           """Set signal value by local name."""
           ...

       def get_bulk(self, signals: list[str]) -> list[float]:
           """Get multiple signal values efficiently."""
           ...

       def close(self) -> None:
           """Release resources."""
           ...
   ```

2. **Create `src/hermes/core/signal.py`**

   Implement:
   - `SignalType` enum (SCALAR, VEC3, QUAT)
   - `SignalDescriptor` frozen dataclass
   - `Wire` dataclass with gain/offset
   - `SignalBus` class with:
     - `register_module(module: ModuleAdapter)`
     - `add_wire(wire: Wire)`
     - `route()` - transfer wired signals
     - `get(qualified_name: str) -> float`
     - `set(qualified_name: str, value: float)`
     - `get_schema() -> dict`
     - `_parse_qualified(name: str) -> tuple[str, str]`
     - `_validate_wire(wire: Wire)` - ensure modules/signals exist

3. **Write unit tests** in `tests/test_signal_bus.py`

   Test cases:
   - Register module
   - Add valid wire
   - Reject wire with invalid module
   - Reject wire with invalid signal
   - Route signal from src to dst
   - Route with gain and offset
   - Get/set qualified names
   - Schema generation

### Acceptance Criteria
- [ ] `ModuleAdapter` is a runtime-checkable Protocol
- [ ] `SignalBus` can register modules and add wires
- [ ] `bus.route()` transfers values correctly
- [ ] `bus.get_schema()` returns valid JSON-serializable dict
- [ ] All unit tests pass
- [ ] `mypy src/hermes/core --strict` passes

### Estimated Effort
Medium (1-2 hours)

---

## Task 1.3: Icarus Adapter

**Issue ID:** `HRM-003`
**Priority:** Critical
**Blocked By:** HRM-002

### Objective
Create an adapter that wraps Icarus pybind11 bindings to implement the `ModuleAdapter` protocol.

### Prerequisites
- Icarus must be built with `BUILD_INTERFACES=ON`
- pybind11 module available in Nix environment

### Steps

1. **Verify Icarus bindings** in Nix shell
   ```python
   import icarus
   sim = icarus.Simulator("path/to/config.yaml")
   print(sim.signals)  # Should list available signals
   ```

2. **Create `src/hermes/adapters/icarus.py`**

   ```python
   from pathlib import Path
   from typing import cast
   from hermes.core.module import ModuleAdapter
   from hermes.core.signal import SignalDescriptor, SignalType

   class IcarusAdapter:
       """Adapter for Icarus 6DOF simulation via pybind11 bindings."""

       def __init__(self, name: str, config_path: str | Path) -> None:
           self._name = name
           self._config_path = Path(config_path)

           # Import and initialize icarus
           import icarus
           self._sim = icarus.Simulator(str(self._config_path))
           self._icarus = icarus

           # Build signal descriptors from icarus.signals
           self._signals = self._build_signals()

       @property
       def name(self) -> str:
           return self._name

       @property
       def signals(self) -> dict[str, SignalDescriptor]:
           return self._signals

       def stage(self) -> None:
           self._sim.stage()

       def step(self, dt: float) -> None:
           # Use icarus native dt if matching, else override
           if dt == 0 or dt == self._sim.dt:
               self._sim.step()
           else:
               self._sim.step(dt)

       def reset(self) -> None:
           self._sim.reset()

       def get(self, signal: str) -> float:
           try:
               return cast(float, self._sim.get(signal))
           except self._icarus.SignalNotFoundError as e:
               raise KeyError(f"Signal not found: {signal}") from e

       def set(self, signal: str, value: float) -> None:
           try:
               self._sim.set(signal, value)
           except self._icarus.SignalNotFoundError as e:
               raise KeyError(f"Signal not found: {signal}") from e

       def get_bulk(self, signals: list[str]) -> list[float]:
           return [self.get(s) for s in signals]

       def get_time(self) -> float:
           return cast(float, self._sim.time)

       def close(self) -> None:
           self._sim = None  # type: ignore[assignment]

       def _build_signals(self) -> dict[str, SignalDescriptor]:
           signals: dict[str, SignalDescriptor] = {}
           for signal_name in self._sim.signals:
               signals[signal_name] = SignalDescriptor(
                   name=signal_name,
                   type=SignalType.SCALAR,
               )
           return signals
   ```

3. **Handle icarus import gracefully**

   The adapter should raise a clear error if icarus bindings aren't available:
   ```python
   try:
       import icarus
   except ImportError as e:
       raise ImportError(
           "Icarus bindings not found. Ensure you're in the Nix development environment."
       ) from e
   ```

4. **Create test fixture** at `tests/fixtures/ball_drop.yaml`

   A minimal Icarus config for testing (coordinate with Icarus project).

5. **Write unit tests** in `tests/test_icarus_adapter.py`

   Test cases (mark as `pytest.mark.icarus` for conditional skip):
   - Create adapter from valid config
   - Stage and step work
   - Get/set signals
   - KeyError on invalid signal
   - Protocol compliance check

### Acceptance Criteria
- [ ] `IcarusAdapter` implements `ModuleAdapter` protocol
- [ ] Can load Icarus config and list signals
- [ ] `stage()`, `step()`, `reset()` call underlying simulator
- [ ] `get()`/`set()` work with proper type casting
- [ ] Clear error message when icarus not available
- [ ] Unit tests pass (or skip if icarus unavailable)

### Estimated Effort
Medium (1-2 hours)

---

## Task 1.4: Synchronous Scheduler

**Issue ID:** `HRM-004`
**Priority:** Critical
**Blocked By:** HRM-002

### Objective
Implement the synchronous scheduler that executes simulation frames.

### Steps

1. **Create `src/hermes/core/scheduler.py`**

   ```python
   import asyncio
   import time
   from enum import Enum
   from dataclasses import dataclass
   from typing import Callable, Awaitable
   from hermes.core.signal import SignalBus

   class ExecutionMode(Enum):
       AS_FAST_AS_POSSIBLE = "afap"
       REAL_TIME = "realtime"
       PAUSED = "paused"

   @dataclass
   class SchedulerConfig:
       dt: float = 0.01  # 100 Hz default
       mode: ExecutionMode = ExecutionMode.AS_FAST_AS_POSSIBLE
       end_time: float | None = None

   class Scheduler:
       """Synchronous simulation scheduler."""

       def __init__(self, bus: SignalBus, config: SchedulerConfig) -> None:
           self._bus = bus
           self._config = config
           self._time: float = 0.0
           self._frame: int = 0
           self._running: bool = False

       @property
       def time(self) -> float:
           return self._time

       @property
       def frame(self) -> int:
           return self._frame

       @property
       def dt(self) -> float:
           return self._config.dt

       @property
       def running(self) -> bool:
           return self._running

       def stage(self) -> None:
           """Stage all modules."""
           for module in self._bus._modules.values():
               module.stage()
           self._time = 0.0
           self._frame = 0

       def step(self) -> None:
           """Execute one simulation frame."""
           dt = self._config.dt

           # Step all modules in registration order
           for module in self._bus._modules.values():
               module.step(dt)

           # Route signals between modules
           self._bus.route()

           # Advance time
           self._time += dt
           self._frame += 1

       def reset(self) -> None:
           """Reset all modules to initial state."""
           for module in self._bus._modules.values():
               module.reset()
           self._time = 0.0
           self._frame = 0

       async def run(
           self,
           callback: Callable[[int, float], Awaitable[None]] | None = None,
       ) -> None:
           """Run simulation loop until end_time or stopped."""
           self._running = True
           wall_start = time.perf_counter()

           while self._running:
               # Check end condition
               if self._config.end_time and self._time >= self._config.end_time:
                   break

               # Execute frame
               self.step()

               # Optional callback (for telemetry)
               if callback:
                   await callback(self._frame, self._time)

               # Real-time pacing
               if self._config.mode == ExecutionMode.REAL_TIME:
                   target_wall = wall_start + self._time
                   sleep_time = target_wall - time.perf_counter()
                   if sleep_time > 0:
                       await asyncio.sleep(sleep_time)

               # Yield to event loop periodically in AFAP mode
               if self._frame % 100 == 0:
                   await asyncio.sleep(0)

           self._running = False

       def stop(self) -> None:
           """Stop the run loop."""
           self._running = False
   ```

2. **Write unit tests** in `tests/test_scheduler.py`

   Test cases:
   - Stage calls all modules
   - Step increments time and frame
   - Step calls route()
   - Reset returns to initial state
   - run() stops at end_time
   - run() calls callback
   - stop() halts run loop

### Acceptance Criteria
- [ ] Scheduler stages all registered modules
- [ ] `step()` advances time by dt
- [ ] `step()` calls `bus.route()` after stepping modules
- [ ] `run()` loop respects end_time
- [ ] `stop()` can halt running simulation
- [ ] Real-time mode paces correctly (within tolerance)
- [ ] All unit tests pass

### Estimated Effort
Small (< 1 hour)

---

## Task 1.5: CLI Skeleton

**Issue ID:** `HRM-005`
**Priority:** High
**Blocked By:** HRM-004, HRM-003

### Objective
Create the command-line interface for running Hermes simulations.

### Steps

1. **Create `src/hermes/core/config.py`**

   Implement Pydantic models for configuration:
   - `ModuleConfig`
   - `WireConfig`
   - `ExecutionConfig`
   - `ServerConfig`
   - `HermesConfig` (root, with `from_yaml()` classmethod)

2. **Create `src/hermes/cli/main.py`**

   ```python
   import asyncio
   from pathlib import Path
   import click
   import structlog

   from hermes.core.config import HermesConfig
   from hermes.core.signal import SignalBus, Wire
   from hermes.core.scheduler import Scheduler, SchedulerConfig, ExecutionMode
   from hermes.adapters.icarus import IcarusAdapter

   structlog.configure(
       processors=[
           structlog.dev.ConsoleRenderer(),
       ],
   )
   log = structlog.get_logger()

   ADAPTER_REGISTRY: dict[str, type] = {
       "icarus": IcarusAdapter,
   }

   @click.group()
   @click.version_option()
   def cli() -> None:
       """Hermes - Simulation Orchestration Platform"""
       pass

   @cli.command()
   @click.argument("config_path", type=click.Path(exists=True, path_type=Path))
   @click.option("--no-server", is_flag=True, help="Run without WebSocket server")
   @click.option("--verbose", "-v", is_flag=True, help="Verbose output")
   def run(config_path: Path, no_server: bool, verbose: bool) -> None:
       """Run simulation from configuration file."""
       log.info("Loading configuration", path=str(config_path))
       config = HermesConfig.from_yaml(config_path)

       # Build signal bus and load modules
       bus = SignalBus()
       _load_modules(bus, config)
       _add_wiring(bus, config)

       # Create scheduler
       scheduler_config = SchedulerConfig(
           dt=1.0 / config.execution.rate_hz,
           mode=ExecutionMode(config.execution.mode),
           end_time=config.execution.end_time,
       )
       scheduler = Scheduler(bus, scheduler_config)

       # Stage and run
       log.info("Staging simulation")
       scheduler.stage()

       log.info("Running simulation", mode=config.execution.mode)

       async def telemetry_callback(frame: int, time: float) -> None:
           if frame % 100 == 0:  # Print every 100 frames
               log.info("Frame", frame=frame, time=f"{time:.3f}")

       asyncio.run(scheduler.run(callback=telemetry_callback))
       log.info("Simulation complete", frames=scheduler.frame, time=scheduler.time)

   def main() -> None:
       cli()

   if __name__ == "__main__":
       main()
   ```

3. **Create example config** at `examples/basic_sim.yaml`

   ```yaml
   version: "0.2"

   modules:
     icarus:
       adapter: icarus
       config: ./icarus_config.yaml

   execution:
     mode: afap
     rate_hz: 100.0
     end_time: 1.0  # Run for 1 second

   server:
     host: "0.0.0.0"
     port: 8765
   ```

4. **Update `src/hermes/__init__.py`** exports

   Export public API:
   - `SignalBus`, `SignalDescriptor`, `Wire`
   - `Scheduler`, `SchedulerConfig`, `ExecutionMode`
   - `ModuleAdapter`
   - `IcarusAdapter`

### Acceptance Criteria
- [ ] `hermes --help` shows available commands
- [ ] `hermes --version` shows version
- [ ] `hermes run config.yaml --no-server` executes simulation
- [ ] Console output shows frame progress
- [ ] Clean exit after end_time reached
- [ ] Error handling for missing config file

### Estimated Effort
Medium (1-2 hours)

---

## Task 1.6: Unit Tests

**Issue ID:** `HRM-006`
**Priority:** High
**Blocked By:** HRM-002, HRM-003, HRM-004

### Objective
Comprehensive unit test coverage for Phase 1 components.

### Steps

1. **Create `tests/conftest.py`** with fixtures

   ```python
   import pytest
   from hermes.core.signal import SignalBus, SignalDescriptor, SignalType

   class MockAdapter:
       """Mock adapter for testing."""

       def __init__(
           self,
           name: str,
           signals: dict[str, float] | None = None,
       ) -> None:
           self._name = name
           self._values = signals or {}
           self._signals = {
               s: SignalDescriptor(name=s, type=SignalType.SCALAR)
               for s in self._values
           }
           self._staged = False
           self._step_count = 0

       @property
       def name(self) -> str:
           return self._name

       @property
       def signals(self) -> dict[str, SignalDescriptor]:
           return self._signals

       def stage(self) -> None:
           self._staged = True

       def step(self, dt: float) -> None:
           self._step_count += 1

       def reset(self) -> None:
           self._step_count = 0

       def get(self, signal: str) -> float:
           return self._values[signal]

       def set(self, signal: str, value: float) -> None:
           self._values[signal] = value

       def get_bulk(self, signals: list[str]) -> list[float]:
           return [self.get(s) for s in signals]

       def close(self) -> None:
           pass

   @pytest.fixture
   def signal_bus() -> SignalBus:
       return SignalBus()

   @pytest.fixture
   def mock_adapter() -> MockAdapter:
       return MockAdapter("test", {"signal1": 1.0, "signal2": 2.0})
   ```

2. **Create `tests/test_signal_bus.py`**

   Test SignalBus functionality comprehensively.

3. **Create `tests/test_scheduler.py`**

   Test Scheduler with mock adapters.

4. **Create `tests/test_config.py`**

   Test configuration loading and validation.

5. **Add pytest markers** in `pyproject.toml`
   ```toml
   [tool.pytest.ini_options]
   markers = [
       "icarus: tests requiring Icarus bindings",
       "slow: slow-running tests",
   ]
   ```

6. **Verify coverage**
   ```bash
   pytest --cov=hermes --cov-report=term-missing
   ```

   Target: >80% coverage for core modules.

### Acceptance Criteria
- [ ] All tests pass with `pytest`
- [ ] Tests can run without Icarus (skip markers)
- [ ] Coverage >80% for `hermes.core`
- [ ] MockAdapter implements ModuleAdapter protocol
- [ ] No flaky tests

### Estimated Effort
Medium (1-2 hours)

---

## Phase 1 Completion Checklist

Before moving to Phase 2, verify:

- [ ] All HRM-001 through HRM-006 issues closed
- [ ] `./scripts/ci.sh` passes (lint + typecheck + tests)
- [ ] `hermes run examples/basic_sim.yaml --no-server` works
- [ ] Console shows frame/time telemetry
- [ ] Clean git history with atomic commits
- [ ] `bd sync && git push` completed

---

## Beads Integration

### Issue Creation Commands

```bash
# Create all Phase 1 issues
bd create -t "Project Setup" -d "pyproject.toml, dev dependencies, ruff/mypy config" -p critical -l phase1,setup
bd create -t "Core Abstractions" -d "ModuleAdapter, SignalDescriptor, SignalBus" -p critical -l phase1,core
bd create -t "Icarus Adapter" -d "pybind11 bindings wrapper implementing ModuleAdapter" -p critical -l phase1,adapter
bd create -t "Synchronous Scheduler" -d "Basic step loop, time tracking" -p critical -l phase1,core
bd create -t "CLI Skeleton" -d "hermes run config.yaml --no-server" -p high -l phase1,cli
bd create -t "Phase 1 Tests" -d "Unit tests for bus, scheduler, adapter" -p high -l phase1,tests
```

### Workflow

```bash
# Check available work
bd ready

# Start working on a task
bd update HRM-001 --status in_progress

# Complete task
bd close HRM-001

# Sync at end of session
bd sync
git push
```

---

## Next Phase Preview

Phase 2 (WebSocket Server) will build on this foundation:
- Add `src/hermes/server/` package
- Implement protocol messages (JSON)
- Binary telemetry encoder
- WebSocket server with asyncio
- Command handling (pause, resume, reset, step, set)
- Remove `--no-server` requirement

See `phase2_websocket.md` for details.
