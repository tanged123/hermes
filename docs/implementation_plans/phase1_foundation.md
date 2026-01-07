# Phase 1: Foundation

**Goal:** Core infrastructure with process management, IPC backplane, and YAML configuration
**Status:** Not Started
**Exit Criteria:** `hermes run config.yaml` loads a module process, exchanges signals via shared memory, and prints telemetry to console

---

## Architecture Overview

Hermes is a **multi-process simulation framework** with the following core components:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HERMES CORE                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Execute/Core/Wrapper                           │   │
│  │  • Process lifecycle (load, init, terminate)                      │   │
│  │  • Runtime scheduling (realtime, AFAP, single-frame)             │   │
│  │  • Coordination and shutdown                                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                 │                                        │
│                                 ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      Data Backplane                               │   │
│  │  • POSIX Shared Memory (signal data)                              │   │
│  │  • Semaphores (synchronization)                                   │   │
│  │  • Named Pipes/FIFOs (control messages)                          │   │
│  │  • Module can also use: UDP, Unix sockets, etc.                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                 │                                        │
│        ┌────────────────────────┼────────────────────────┐              │
│        ▼                        ▼                        ▼              │
│  ┌──────────┐            ┌──────────┐            ┌──────────┐          │
│  │ Module A │            │ Module B │            │ Module C │          │
│  │ (C/C++)  │            │ (Python) │            │ (Rust)   │          │
│  └──────────┘            └──────────┘            └──────────┘          │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                     Scripting Infrastructure                             │
│  • Python API for injection/inspection                                  │
│  • Programmatic simulation control                                      │
│  • Real-time value modification                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Process Isolation**: Each module runs as a separate process
2. **Language Agnostic**: Modules can be written in any language (C, C++, Python, Rust, etc.)
3. **IPC-First**: All inter-module communication via POSIX IPC primitives
4. **YAML Configuration**: First-class citizen - no recompile needed for configuration changes
5. **Explicit Scheduling**: User-defined execution order and timing

### Operating Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `realtime` | Paced to wall-clock time | Hardware-in-the-loop, visualization |
| `afap` | As fast as possible | Batch runs, Monte Carlo |
| `single_frame` | Manual step-by-step | Debugging, scripted scenarios |

---

## Dependencies

- Python 3.11+
- Nix flake with development environment
- POSIX-compliant OS (Linux, macOS)

---

## Task 1.1: Project Setup

**Issue ID:** `hermes-9yd`
**Priority:** Critical (P0)
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
       "pyyaml>=6.0",
       "pydantic>=2.5",
       "structlog>=24.1",
       "numpy>=1.26",
       "click>=8.1",
       "posix-ipc>=1.1.1",  # POSIX shared memory/semaphores
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
   server = [
       "websockets>=12.0",  # Optional for Phase 2
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
   ├── core/                    # Execute/Core/Wrapper
   │   ├── __init__.py
   │   ├── process.py           # Process lifecycle management
   │   ├── scheduler.py         # Runtime scheduling
   │   └── config.py            # YAML configuration models
   ├── backplane/               # Data Backplane
   │   ├── __init__.py
   │   ├── shm.py               # Shared memory management
   │   ├── signals.py           # Signal registry and routing
   │   └── sync.py              # Semaphores and synchronization
   ├── protocol/                # Module protocol definitions
   │   ├── __init__.py
   │   ├── messages.py          # IPC message formats
   │   └── module.py            # Module interface specification
   ├── scripting/               # Scripting infrastructure
   │   ├── __init__.py
   │   └── api.py               # Python injection/inspection API
   └── cli/
       ├── __init__.py
       └── main.py

   include/hermes/              # C headers for native modules
   └── module.h                 # Module protocol in C

   tests/
   ├── conftest.py
   ├── test_backplane/
   ├── test_core/
   └── fixtures/
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
- [ ] Directory structure matches specification

---

## Task 1.2: Data Backplane - Shared Memory

**Issue ID:** `hermes-71j`
**Priority:** Critical (P0)
**Blocked By:** `hermes-9yd`

### Objective
Implement the shared memory segment for inter-process signal communication.

### Concepts

**Signal Table**: A contiguous memory region containing all signal values:
```
┌─────────────────────────────────────────────────────────────┐
│                    Shared Memory Segment                     │
├─────────────────────────────────────────────────────────────┤
│ Header (64 bytes)                                            │
│   - magic: u32 ("HERM")                                     │
│   - version: u32                                            │
│   - frame: u64                                              │
│   - time: f64                                               │
│   - signal_count: u32                                       │
│   - reserved: [u8; 36]                                      │
├─────────────────────────────────────────────────────────────┤
│ Signal Directory (variable)                                  │
│   - [SignalEntry] × signal_count                            │
│     - name_offset: u32                                      │
│     - data_offset: u32                                      │
│     - data_type: u8 (0=f64, 1=f32, 2=i64, etc.)           │
│     - flags: u8 (writable, published, etc.)                │
├─────────────────────────────────────────────────────────────┤
│ String Table (variable)                                      │
│   - null-terminated signal names                            │
├─────────────────────────────────────────────────────────────┤
│ Data Region (aligned to 64 bytes)                           │
│   - Signal values in directory order                        │
│   - f64 values packed contiguously                         │
└─────────────────────────────────────────────────────────────┘
```

### Deliverables
- `src/hermes/backplane/shm.py`
- `src/hermes/backplane/signals.py`

### Steps

1. **Create `SignalDescriptor` dataclass**
   ```python
   from dataclasses import dataclass
   from enum import IntEnum

   class SignalType(IntEnum):
       F64 = 0
       F32 = 1
       I64 = 2
       I32 = 3
       BOOL = 4

   class SignalFlags(IntEnum):
       NONE = 0
       WRITABLE = 1 << 0
       PUBLISHED = 1 << 1  # Included in telemetry

   @dataclass(frozen=True)
   class SignalDescriptor:
       name: str
       type: SignalType = SignalType.F64
       flags: int = SignalFlags.NONE
       unit: str = ""
       description: str = ""
   ```

2. **Create `SharedMemoryManager`**
   ```python
   import posix_ipc
   import mmap
   import struct
   from typing import Any

   class SharedMemoryManager:
       """Manages the shared memory segment for signal data."""

       MAGIC = 0x4845524D  # "HERM"
       VERSION = 1
       HEADER_SIZE = 64

       def __init__(self, name: str, create: bool = False) -> None:
           self._name = name
           self._shm: posix_ipc.SharedMemory | None = None
           self._mmap: mmap.mmap | None = None

       def create(self, signals: list[SignalDescriptor]) -> None:
           """Create and initialize shared memory segment."""
           ...

       def attach(self) -> None:
           """Attach to existing shared memory segment."""
           ...

       def detach(self) -> None:
           """Detach from shared memory segment."""
           ...

       def destroy(self) -> None:
           """Destroy the shared memory segment."""
           ...

       def get_signal(self, name: str) -> float:
           """Read a signal value from shared memory."""
           ...

       def set_signal(self, name: str, value: float) -> None:
           """Write a signal value to shared memory."""
           ...

       def get_frame(self) -> int:
           """Get current frame number from header."""
           ...

       def set_frame(self, frame: int) -> None:
           """Set frame number in header."""
           ...

       def get_time(self) -> float:
           """Get current simulation time from header."""
           ...

       def set_time(self, time: float) -> None:
           """Set simulation time in header."""
           ...
   ```

3. **Create `SignalRegistry`**
   ```python
   class SignalRegistry:
       """Registry of all signals in the simulation."""

       def __init__(self) -> None:
           self._signals: dict[str, SignalDescriptor] = {}
           self._by_module: dict[str, list[str]] = {}

       def register(self, module: str, signal: SignalDescriptor) -> str:
           """Register a signal, returns qualified name."""
           qualified = f"{module}.{signal.name}"
           self._signals[qualified] = signal
           self._by_module.setdefault(module, []).append(qualified)
           return qualified

       def get(self, qualified_name: str) -> SignalDescriptor:
           """Get signal descriptor by qualified name."""
           ...

       def list_module(self, module: str) -> list[str]:
           """List all signals for a module."""
           ...

       def all_signals(self) -> dict[str, SignalDescriptor]:
           """Get all registered signals."""
           ...
   ```

4. **Write unit tests** in `tests/test_backplane/test_shm.py`
   - Create shared memory segment
   - Write and read signal values
   - Header frame/time operations
   - Attach from another "process" (simulated)
   - Cleanup and destruction

### Acceptance Criteria
- [ ] Shared memory segment can be created with signal list
- [ ] Signals can be read/written by name
- [ ] Header contains frame and time
- [ ] Multiple processes can attach (tested with fork or subprocess)
- [ ] Clean destruction without leaks
- [ ] `mypy src/hermes/backplane --strict` passes

---

## Task 1.3: Data Backplane - Synchronization

**Issue ID:** `hermes-60w`
**Priority:** Critical (P0)
**Blocked By:** `hermes-71j`

### Objective
Implement synchronization primitives for coordinated module execution.

### Concepts

**Frame Barrier**: All modules must complete before advancing:
```
                    Frame N                     Frame N+1
    ┌───────────────────────────────────┐
    │  Scheduler signals "step"          │
    │         │                          │
    │    ┌────┴────┬────────┐           │
    │    ▼         ▼        ▼           │
    │ Module A  Module B  Module C      │
    │    │         │        │           │
    │    └────┬────┴────────┘           │
    │         ▼                          │
    │  All wait on barrier               │──────▶ Next frame
    └───────────────────────────────────┘
```

### Deliverables
- `src/hermes/backplane/sync.py`

### Steps

1. **Create `FrameBarrier`**
   ```python
   import posix_ipc

   class FrameBarrier:
       """Synchronization barrier for frame execution."""

       def __init__(self, name: str, count: int, create: bool = False) -> None:
           self._name = name
           self._count = count
           self._sem_wait: posix_ipc.Semaphore | None = None
           self._sem_done: posix_ipc.Semaphore | None = None

       def create(self) -> None:
           """Create barrier semaphores."""
           ...

       def attach(self) -> None:
           """Attach to existing barrier."""
           ...

       def signal_step(self) -> None:
           """Scheduler: signal all modules to step."""
           ...

       def wait_step(self) -> None:
           """Module: wait for step signal."""
           ...

       def signal_done(self) -> None:
           """Module: signal completion."""
           ...

       def wait_all_done(self) -> None:
           """Scheduler: wait for all modules to complete."""
           ...

       def destroy(self) -> None:
           """Destroy barrier semaphores."""
           ...
   ```

2. **Create `ModuleSemaphores`**
   ```python
   class ModuleSemaphores:
       """Per-module semaphores for fine-grained control."""

       def __init__(self, module_name: str) -> None:
           self._name = module_name
           self._ready: posix_ipc.Semaphore | None = None
           self._step: posix_ipc.Semaphore | None = None
           self._done: posix_ipc.Semaphore | None = None

       # Lifecycle methods...
   ```

3. **Write unit tests** in `tests/test_backplane/test_sync.py`
   - Barrier with single process (trivial)
   - Barrier with subprocess (fork test)
   - Timeout on wait
   - Proper cleanup

### Acceptance Criteria
- [ ] FrameBarrier synchronizes N processes
- [ ] Semaphores survive process lifecycle
- [ ] Timeout prevents deadlock
- [ ] Clean destruction without orphan semaphores
- [ ] Works across fork boundaries

---

## Task 1.4: YAML Configuration

**Issue ID:** `hermes-8to`
**Priority:** Critical (P0)
**Blocked By:** `hermes-9yd`

### Objective
Implement first-class YAML configuration parsing with Pydantic validation.

### Configuration Schema

```yaml
# hermes.yaml - Example configuration
version: "0.2"

# Module definitions
modules:
  icarus:
    type: process                    # process | inproc | script
    executable: "./icarus_sim"       # Path to module executable
    config: "./icarus_config.yaml"   # Module-specific config
    signals:                         # Optional: override signal discovery
      - name: Vehicle.position.x
        type: f64
        unit: m
        writable: false

  injector:
    type: script
    script: "./inject.py"
    signals:
      - name: thrust_command
        type: f64
        unit: N
        writable: true

# Signal connections (wiring)
wiring:
  - src: injector.thrust_command
    dst: icarus.Vehicle.thrust
    gain: 1.0
    offset: 0.0

# Execution parameters
execution:
  mode: afap                         # realtime | afap | single_frame
  rate_hz: 100.0                     # Simulation rate
  end_time: 10.0                     # Optional: auto-terminate
  schedule:                          # Explicit execution order
    - icarus
    - injector

# Optional: Server configuration (Phase 2)
server:
  enabled: false
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

### Deliverables
- `src/hermes/core/config.py`

### Steps

1. **Create Pydantic models**
   ```python
   from pydantic import BaseModel, field_validator
   from pathlib import Path
   from enum import Enum

   class ModuleType(str, Enum):
       PROCESS = "process"    # External executable
       INPROC = "inproc"      # In-process (pybind11)
       SCRIPT = "script"      # Python script

   class ExecutionMode(str, Enum):
       REALTIME = "realtime"
       AFAP = "afap"
       SINGLE_FRAME = "single_frame"

   class SignalConfig(BaseModel):
       name: str
       type: str = "f64"
       unit: str = ""
       writable: bool = False
       published: bool = True

   class ModuleConfig(BaseModel):
       type: ModuleType
       executable: Path | None = None
       script: Path | None = None
       config: Path | None = None
       signals: list[SignalConfig] = []

       @field_validator("executable", "script", "config", mode="before")
       @classmethod
       def resolve_path(cls, v: str | Path | None) -> Path | None:
           if v is None:
               return None
           return Path(v)

   class WireConfig(BaseModel):
       src: str
       dst: str
       gain: float = 1.0
       offset: float = 0.0

       @field_validator("src", "dst")
       @classmethod
       def validate_qualified_name(cls, v: str) -> str:
           if "." not in v:
               raise ValueError(f"Expected 'module.signal' format: {v}")
           return v

   class ExecutionConfig(BaseModel):
       mode: ExecutionMode = ExecutionMode.AFAP
       rate_hz: float = 100.0
       end_time: float | None = None
       schedule: list[str] = []  # Empty = registration order

   class ServerConfig(BaseModel):
       enabled: bool = False
       host: str = "0.0.0.0"
       port: int = 8765
       telemetry_hz: float = 60.0

   class HermesConfig(BaseModel):
       version: str
       modules: dict[str, ModuleConfig]
       wiring: list[WireConfig] = []
       execution: ExecutionConfig = ExecutionConfig()
       server: ServerConfig = ServerConfig()

       @classmethod
       def from_yaml(cls, path: Path) -> "HermesConfig":
           import yaml
           with open(path) as f:
               data = yaml.safe_load(f)
           return cls.model_validate(data)
   ```

2. **Add validation logic**
   - Module names unique
   - Wire endpoints reference valid modules
   - Schedule contains only defined modules
   - Paths exist (optional, can defer to runtime)

3. **Write unit tests** in `tests/test_core/test_config.py`
   - Valid config loads
   - Missing required fields fail
   - Invalid enum values fail
   - Wire validation works
   - Path resolution works

### Acceptance Criteria
- [ ] Pydantic models parse all config fields
- [ ] Validation errors are clear and actionable
- [ ] `from_yaml()` loads and validates
- [ ] All enums have string serialization
- [ ] `mypy src/hermes/core/config.py --strict` passes

---

## Task 1.5: Process Manager

**Issue ID:** `hermes-ume`
**Priority:** High (P1)
**Blocked By:** `hermes-71j`, `hermes-60w`, `hermes-8to`

### Objective
Implement the core process lifecycle management for loading and controlling module processes.

### Deliverables
- `src/hermes/core/process.py`

### Concepts

**Module Lifecycle**:
```
    load()        stage()       step()...      terminate()
      │             │              │               │
      ▼             ▼              ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐     ┌─────────┐
│  INIT   │──▶│ STAGED  │──▶│ RUNNING │────▶│  DONE   │
└─────────┘   └─────────┘   └─────────┘     └─────────┘
      │                           │
      └───────── reset() ─────────┘
```

### Steps

1. **Create `ModuleProcess` class**
   ```python
   import subprocess
   from pathlib import Path
   from enum import Enum
   from dataclasses import dataclass

   class ModuleState(Enum):
       INIT = "init"
       STAGED = "staged"
       RUNNING = "running"
       PAUSED = "paused"
       DONE = "done"
       ERROR = "error"

   @dataclass
   class ModuleInfo:
       name: str
       pid: int
       state: ModuleState
       shm_name: str
       signals: list[str]

   class ModuleProcess:
       """Manages a single module subprocess."""

       def __init__(
           self,
           name: str,
           config: ModuleConfig,
           shm: SharedMemoryManager,
           barrier: FrameBarrier,
       ) -> None:
           self._name = name
           self._config = config
           self._shm = shm
           self._barrier = barrier
           self._process: subprocess.Popen | None = None
           self._state = ModuleState.INIT

       @property
       def name(self) -> str:
           return self._name

       @property
       def state(self) -> ModuleState:
           return self._state

       @property
       def pid(self) -> int | None:
           return self._process.pid if self._process else None

       def load(self) -> None:
           """Start the module process."""
           if self._config.type == ModuleType.PROCESS:
               self._start_external_process()
           elif self._config.type == ModuleType.SCRIPT:
               self._start_script_process()
           # INPROC handled differently (not a subprocess)

       def stage(self) -> None:
           """Signal module to initialize."""
           self._send_command("stage")
           self._state = ModuleState.STAGED

       def step(self) -> None:
           """Signal module to execute one frame."""
           # Uses barrier synchronization
           ...

       def terminate(self, timeout: float = 5.0) -> None:
           """Gracefully terminate the module."""
           self._send_command("terminate")
           if self._process:
               self._process.wait(timeout=timeout)
           self._state = ModuleState.DONE

       def kill(self) -> None:
           """Forcefully kill the module."""
           if self._process:
               self._process.kill()
           self._state = ModuleState.DONE

       def _start_external_process(self) -> None:
           """Start external executable."""
           ...

       def _start_script_process(self) -> None:
           """Start Python script as subprocess."""
           ...

       def _send_command(self, cmd: str) -> None:
           """Send command via named pipe."""
           ...
   ```

2. **Create `ProcessManager`**
   ```python
   class ProcessManager:
       """Coordinates all module processes."""

       def __init__(self, config: HermesConfig) -> None:
           self._config = config
           self._shm: SharedMemoryManager | None = None
           self._barrier: FrameBarrier | None = None
           self._modules: dict[str, ModuleProcess] = {}

       def initialize(self) -> None:
           """Create shared resources and load all modules."""
           # 1. Collect all signals from config
           # 2. Create shared memory segment
           # 3. Create synchronization barrier
           # 4. Load each module process
           ...

       def stage_all(self) -> None:
           """Stage all modules."""
           for module in self._execution_order():
               module.stage()

       def step_all(self) -> None:
           """Execute one frame across all modules."""
           # 1. Signal all modules to step
           # 2. Wait for all to complete
           # 3. Update frame/time in shared memory
           ...

       def terminate_all(self) -> None:
           """Gracefully terminate all modules."""
           for module in reversed(list(self._modules.values())):
               module.terminate()

       def _execution_order(self) -> list[ModuleProcess]:
           """Return modules in configured execution order."""
           schedule = self._config.execution.schedule
           if schedule:
               return [self._modules[name] for name in schedule]
           return list(self._modules.values())

       def __enter__(self) -> "ProcessManager":
           self.initialize()
           return self

       def __exit__(self, *args: Any) -> None:
           self.terminate_all()
   ```

3. **Write unit tests** in `tests/test_core/test_process.py`
   - Load mock module (Python script)
   - Stage and step
   - Terminate gracefully
   - Kill on timeout
   - Context manager cleanup

### Acceptance Criteria
- [ ] Can load external process modules
- [ ] Can load Python script modules
- [ ] Stage signals all modules
- [ ] Step uses barrier synchronization
- [ ] Terminate cleans up resources
- [ ] Context manager handles exceptions

---

## Task 1.6: Scheduler

**Issue ID:** `hermes-d5g`
**Priority:** High (P1)
**Blocked By:** `hermes-ume`

### Objective
Implement the runtime scheduler with support for all operating modes.

### Deliverables
- `src/hermes/core/scheduler.py`

### Steps

1. **Create `Scheduler` class**
   ```python
   import time
   import asyncio
   from typing import Callable, Awaitable

   class Scheduler:
       """Runtime simulation scheduler."""

       def __init__(
           self,
           process_mgr: ProcessManager,
           config: ExecutionConfig,
       ) -> None:
           self._pm = process_mgr
           self._config = config
           self._frame: int = 0
           self._time: float = 0.0
           self._running: bool = False
           self._paused: bool = False

       @property
       def frame(self) -> int:
           return self._frame

       @property
       def time(self) -> float:
           return self._time

       @property
       def dt(self) -> float:
           return 1.0 / self._config.rate_hz

       @property
       def running(self) -> bool:
           return self._running

       @property
       def paused(self) -> bool:
           return self._paused

       def stage(self) -> None:
           """Stage simulation (calls all modules)."""
           self._pm.stage_all()
           self._frame = 0
           self._time = 0.0

       def step(self, count: int = 1) -> None:
           """Execute N simulation frames."""
           for _ in range(count):
               self._pm.step_all()
               self._time += self.dt
               self._frame += 1

       def reset(self) -> None:
           """Reset simulation to initial state."""
           self._pm.reset_all()
           self._frame = 0
           self._time = 0.0

       async def run(
           self,
           callback: Callable[[int, float], Awaitable[None]] | None = None,
       ) -> None:
           """Run simulation loop until stopped or end_time reached."""
           self._running = True
           wall_start = time.perf_counter()

           while self._running:
               # Check end condition
               if self._config.end_time and self._time >= self._config.end_time:
                   break

               # Pause handling
               if self._paused:
                   await asyncio.sleep(0.01)
                   continue

               # Single frame mode waits for explicit step()
               if self._config.mode == ExecutionMode.SINGLE_FRAME:
                   await asyncio.sleep(0.01)
                   continue

               # Execute frame
               self.step()

               # Callback (for telemetry, logging)
               if callback:
                   await callback(self._frame, self._time)

               # Real-time pacing
               if self._config.mode == ExecutionMode.REALTIME:
                   target_wall = wall_start + self._time
                   sleep_time = target_wall - time.perf_counter()
                   if sleep_time > 0:
                       await asyncio.sleep(sleep_time)

               # Yield to event loop in AFAP mode
               if self._frame % 100 == 0:
                   await asyncio.sleep(0)

           self._running = False

       def pause(self) -> None:
           """Pause the run loop."""
           self._paused = True

       def resume(self) -> None:
           """Resume the run loop."""
           self._paused = False

       def stop(self) -> None:
           """Stop the run loop."""
           self._running = False
   ```

2. **Write unit tests** in `tests/test_core/test_scheduler.py`
   - Stage calls process manager
   - Step increments frame/time
   - Real-time mode paces correctly
   - AFAP mode runs fast
   - Single-frame mode waits
   - Pause/resume works
   - Stop halts loop
   - End time terminates

### Acceptance Criteria
- [ ] All three modes work correctly
- [ ] Frame and time tracked accurately
- [ ] Pause/resume functional
- [ ] Stop halts cleanly
- [ ] Real-time within 1ms tolerance
- [ ] Callback invoked each frame

---

## Task 1.7: Scripting Infrastructure

**Issue ID:** `hermes-p7k`
**Priority:** High (P1)
**Blocked By:** `hermes-71j`

### Objective
Provide a Python API for programmatic interaction with running simulations.

### Deliverables
- `src/hermes/scripting/api.py`

### Steps

1. **Create `SimulationAPI` class**
   ```python
   class SimulationAPI:
       """Python API for interacting with running simulations."""

       def __init__(self, shm_name: str) -> None:
           self._shm = SharedMemoryManager(shm_name)
           self._shm.attach()

       def get(self, signal: str) -> float:
           """Get signal value by qualified name."""
           return self._shm.get_signal(signal)

       def set(self, signal: str, value: float) -> None:
           """Set signal value by qualified name."""
           self._shm.set_signal(signal, value)

       def get_frame(self) -> int:
           """Get current simulation frame."""
           return self._shm.get_frame()

       def get_time(self) -> float:
           """Get current simulation time."""
           return self._shm.get_time()

       def wait_frame(self, target: int, timeout: float = 10.0) -> bool:
           """Wait until simulation reaches target frame."""
           start = time.time()
           while self.get_frame() < target:
               if time.time() - start > timeout:
                   return False
               time.sleep(0.001)
           return True

       def inject(self, values: dict[str, float]) -> None:
           """Inject multiple values at once."""
           for signal, value in values.items():
               self.set(signal, value)

       def sample(self, signals: list[str]) -> dict[str, float]:
           """Sample multiple signals at once."""
           return {s: self.get(s) for s in signals}

       def close(self) -> None:
           """Detach from shared memory."""
           self._shm.detach()

       def __enter__(self) -> "SimulationAPI":
           return self

       def __exit__(self, *args: Any) -> None:
           self.close()
   ```

2. **Example usage script**
   ```python
   # scripts/example_inject.py
   from hermes.scripting import SimulationAPI

   with SimulationAPI("/hermes_sim") as sim:
       # Wait for simulation to start
       sim.wait_frame(10)

       # Inject a thrust command
       sim.set("injector.thrust_command", 1000.0)

       # Wait and sample results
       sim.wait_frame(100)
       pos = sim.get("icarus.Vehicle.position.z")
       print(f"Altitude at frame 100: {pos:.2f} m")
   ```

3. **Write unit tests** in `tests/test_scripting/test_api.py`

### Acceptance Criteria
- [ ] Can attach to running simulation
- [ ] Get/set signals work
- [ ] wait_frame blocks correctly
- [ ] inject/sample work with multiple signals
- [ ] Clean detach on close

---

## Task 1.8: CLI Implementation

**Issue ID:** `hermes-anr`
**Priority:** High (P1)
**Blocked By:** `hermes-d5g`, `hermes-8to`

### Objective
Create the command-line interface for running Hermes simulations.

### Deliverables
- `src/hermes/cli/main.py`

### Steps

1. **Implement CLI**
   ```python
   import asyncio
   from pathlib import Path
   import click
   import structlog

   from hermes import __version__
   from hermes.core.config import HermesConfig
   from hermes.core.process import ProcessManager
   from hermes.core.scheduler import Scheduler

   structlog.configure(
       processors=[
           structlog.dev.ConsoleRenderer(),
       ],
   )
   log = structlog.get_logger()

   @click.group()
   @click.version_option(version=__version__)
   def cli() -> None:
       """Hermes - Simulation Orchestration Platform"""
       pass

   @cli.command()
   @click.argument("config_path", type=click.Path(exists=True, path_type=Path))
   @click.option("--verbose", "-v", is_flag=True, help="Verbose output")
   def run(config_path: Path, verbose: bool) -> None:
       """Run simulation from configuration file."""
       log.info("Loading configuration", path=str(config_path))
       config = HermesConfig.from_yaml(config_path)

       with ProcessManager(config) as pm:
           scheduler = Scheduler(pm, config.execution)

           log.info("Staging simulation")
           scheduler.stage()

           log.info("Running simulation", mode=config.execution.mode.value)

           async def telemetry_callback(frame: int, time: float) -> None:
               if frame % 100 == 0:
                   log.info("Frame", frame=frame, time=f"{time:.3f}")

           asyncio.run(scheduler.run(callback=telemetry_callback))
           log.info("Simulation complete", frames=scheduler.frame, time=scheduler.time)

   @cli.command()
   @click.argument("config_path", type=click.Path(exists=True, path_type=Path))
   def validate(config_path: Path) -> None:
       """Validate configuration file."""
       try:
           config = HermesConfig.from_yaml(config_path)
           log.info("Configuration valid", modules=len(config.modules))
       except Exception as e:
           log.error("Configuration invalid", error=str(e))
           raise SystemExit(1)

   @cli.command()
   def list_signals() -> None:
       """List signals from a running simulation."""
       # Connect to shared memory and list signals
       pass

   def main() -> None:
       cli()

   if __name__ == "__main__":
       main()
   ```

2. **Create example config** at `examples/basic_sim.yaml`

3. **Write integration tests**

### Acceptance Criteria
- [ ] `hermes --help` shows commands
- [ ] `hermes --version` shows version
- [ ] `hermes run config.yaml` executes simulation
- [ ] `hermes validate config.yaml` validates config
- [ ] Console shows frame progress
- [ ] Clean exit on completion/Ctrl+C

---

## Task 1.9: Module Protocol (C Header)

**Issue ID:** `hermes-xjl`
**Priority:** Medium (P2)
**Blocked By:** `hermes-71j`

### Objective
Define the C interface for native modules to implement.

### Deliverables
- `include/hermes/module.h`
- `examples/c_module/`

### C Header
```c
/* include/hermes/module.h - Hermes Module Protocol */
#ifndef HERMES_MODULE_H
#define HERMES_MODULE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Module lifecycle callbacks */
typedef struct {
    /* Initialize module, return 0 on success */
    int (*init)(const char* config_path, const char* shm_name);

    /* Stage module for execution */
    int (*stage)(void);

    /* Execute one simulation step */
    int (*step)(double dt);

    /* Reset to initial conditions */
    int (*reset)(void);

    /* Cleanup and shutdown */
    void (*terminate)(void);

    /* Get signal value by name */
    double (*get_signal)(const char* name);

    /* Set signal value by name */
    void (*set_signal)(const char* name, double value);

    /* Get list of signal names (null-terminated array) */
    const char** (*list_signals)(void);

} hermes_module_t;

/* Module entry point - must be implemented by module */
hermes_module_t* hermes_module_create(void);
void hermes_module_destroy(hermes_module_t* module);

/* Shared memory helpers */
void* hermes_shm_attach(const char* name);
void hermes_shm_detach(void* shm);
double hermes_shm_get(void* shm, const char* signal);
void hermes_shm_set(void* shm, const char* signal, double value);

#ifdef __cplusplus
}
#endif

#endif /* HERMES_MODULE_H */
```

### Acceptance Criteria
- [ ] Header compiles with C11 and C++17
- [ ] Example C module builds
- [ ] Can be loaded by Hermes
- [ ] Signal access works

---

## Task 1.10: Unit Tests & Integration

**Issue ID:** `hermes-gr1`
**Priority:** High (P1)
**Blocked By:** `hermes-anr`, `hermes-p7k`, `hermes-xjl`

### Objective
Comprehensive test coverage for Phase 1 components.

### Test Structure
```
tests/
├── conftest.py              # Shared fixtures
├── test_backplane/
│   ├── test_shm.py          # Shared memory tests
│   ├── test_signals.py      # Signal registry tests
│   └── test_sync.py         # Synchronization tests
├── test_core/
│   ├── test_config.py       # Configuration tests
│   ├── test_process.py      # Process management tests
│   └── test_scheduler.py    # Scheduler tests
├── test_scripting/
│   └── test_api.py          # Scripting API tests
├── integration/
│   └── test_basic_sim.py    # End-to-end test
└── fixtures/
    ├── basic_sim.yaml       # Test configuration
    └── mock_module.py       # Mock module for testing
```

### Acceptance Criteria
- [ ] All unit tests pass
- [ ] Integration test runs full simulation
- [ ] Coverage >80% for core modules
- [ ] Tests can run without external dependencies
- [ ] Mock modules for isolated testing

---

## Phase 1 Completion Checklist

Before moving to Phase 2, verify:

- [ ] All Phase 1 issues closed
- [ ] `./scripts/ci.sh` passes (lint + typecheck + tests)
- [ ] `hermes run examples/basic_sim.yaml` works with mock module
- [ ] Shared memory IPC functional
- [ ] Console shows frame/time telemetry
- [ ] Python scripting API works
- [ ] Clean git history with atomic commits
- [ ] `bd sync && git push` completed

---

## Beads Integration

### Phase 1 Issues (Created)

| Issue ID | Task | Priority | Status |
|----------|------|----------|--------|
| `hermes-9yd` | Project Setup | P0 | **READY** |
| `hermes-71j` | Shared Memory | P0 | Blocked |
| `hermes-60w` | Synchronization | P0 | Blocked |
| `hermes-8to` | YAML Configuration | P0 | Blocked |
| `hermes-ume` | Process Manager | P1 | Blocked |
| `hermes-d5g` | Scheduler | P1 | Blocked |
| `hermes-p7k` | Scripting Infrastructure | P1 | Blocked |
| `hermes-anr` | CLI Implementation | P1 | Blocked |
| `hermes-xjl` | Module Protocol (C Header) | P2 | Blocked |
| `hermes-gr1` | Tests & Integration | P1 | Blocked |

### Workflow
```bash
bd ready                              # Check available work
bd update hermes-9yd --status in_progress  # Start task
# ... do work ...
bd close hermes-9yd                   # Complete task
bd sync && git push                   # End of session
```

---

## Next Phase Preview

Phase 2 (WebSocket Server) will build on this foundation:
- Add `src/hermes/server/` package
- Implement protocol messages (JSON)
- Binary telemetry encoder
- WebSocket server with asyncio
- Command handling (pause, resume, reset, step, set)

See `phase2_websocket.md` for details.
