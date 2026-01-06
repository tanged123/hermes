# Architecture & Core Classes

This document describes the core classes implemented in Hermes Phase 1 and how they work together.

## Module Layout

```
src/hermes/
├── backplane/           # IPC infrastructure
│   ├── shm.py          # Shared memory management
│   ├── signals.py      # Signal types and registry
│   └── sync.py         # Synchronization primitives
├── core/               # Orchestration logic
│   ├── config.py       # YAML configuration models
│   ├── process.py      # Process lifecycle management
│   └── scheduler.py    # Execution scheduling
├── scripting/          # Runtime API
│   └── api.py          # Python inspection/injection
└── cli/                # Command-line interface
    └── main.py         # CLI commands
```

---

## Backplane Layer

The backplane provides the low-level IPC primitives for inter-process communication.

### SignalType & SignalFlags

```python
from hermes.backplane.signals import SignalType, SignalFlags

# Signal data types
SignalType.F64   # 64-bit float (default)
SignalType.F32   # 32-bit float
SignalType.I64   # 64-bit integer
SignalType.I32   # 32-bit integer
SignalType.BOOL  # Boolean

# Signal property flags
SignalFlags.NONE       # No special properties
SignalFlags.WRITABLE   # Can be modified via scripting API
SignalFlags.PUBLISHED  # Included in telemetry streams
```

### SignalDescriptor

Immutable metadata about a signal:

```python
from hermes.backplane.signals import SignalDescriptor, SignalType, SignalFlags

desc = SignalDescriptor(
    name="position.x",
    type=SignalType.F64,
    flags=SignalFlags.WRITABLE | SignalFlags.PUBLISHED,
    unit="m",
    description="X position in world frame"
)
```

### SignalRegistry

Central registry mapping qualified signal names to descriptors:

```python
from hermes.backplane.signals import SignalRegistry, SignalDescriptor

registry = SignalRegistry()

# Register signals with module prefix
registry.register("vehicle", SignalDescriptor(name="position.x"))
registry.register("vehicle", SignalDescriptor(name="velocity.x"))

# Lookup
desc = registry.get("vehicle.position.x")

# List all signals for a module
vehicle_signals = registry.list_module("vehicle")
# ["vehicle.position.x", "vehicle.velocity.x"]
```

### SharedMemoryManager

Manages the POSIX shared memory segment containing all signal values:

```python
from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor

# Create shared memory (scheduler side)
shm = SharedMemoryManager("/hermes_sim")
shm.create([
    SignalDescriptor(name="position.x"),
    SignalDescriptor(name="velocity.x"),
])

# Read/write signals
shm.set_signal("position.x", 100.0)
value = shm.get_signal("position.x")

# Frame and time tracking
shm.set_frame(42)
shm.set_time(0.42)           # Float seconds (convenience)
shm.set_time_ns(420_000_000) # Integer nanoseconds (authoritative)
frame = shm.get_frame()
time = shm.get_time()        # Float seconds
time_ns = shm.get_time_ns()  # Integer nanoseconds

# Cleanup
shm.destroy()
```

**Shared Memory Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Header (64 bytes)                                            │
│   - magic: u32 ("HERM")                                     │
│   - version: u32 (currently 3)                              │
│   - frame: u64                                              │
│   - time_ns: u64 (nanoseconds for determinism)              │
│   - signal_count: u32                                       │
├─────────────────────────────────────────────────────────────┤
│ Signal Directory                                             │
│   - [SignalEntry] × signal_count                            │
├─────────────────────────────────────────────────────────────┤
│ String Table (signal names)                                  │
├─────────────────────────────────────────────────────────────┤
│ Data Region (signal values)                                  │
└─────────────────────────────────────────────────────────────┘
```

**Deterministic Time Tracking:**

Time is stored as integer nanoseconds (u64) rather than floating-point
seconds. This ensures bit-exact reproducibility across runs and platforms.
For rates that don't divide evenly into 1 billion (e.g., 600 Hz), the
timestep is rounded to the nearest nanosecond, introducing bounded error
(~0.72ms/hour at 600 Hz) that does not accumulate.

### FrameBarrier

Semaphore-based synchronization for coordinating module execution:

```python
from hermes.backplane.sync import FrameBarrier

# Scheduler creates the barrier
barrier = FrameBarrier("/hermes_barrier", count=3)  # 3 modules
barrier.create()

# Each module attaches
module_barrier = FrameBarrier("/hermes_barrier", count=3)
module_barrier.attach()

# Frame synchronization protocol:
# 1. Scheduler signals all modules to step
barrier.signal_step()

# 2. Each module waits for the signal
module_barrier.wait_step(timeout=5.0)

# 3. Module executes its step...

# 4. Module signals completion
module_barrier.signal_done()

# 5. Scheduler waits for all modules
barrier.wait_all_done(timeout=5.0)

# Cleanup
barrier.destroy()
```

---

## Core Layer

The core layer implements orchestration logic.

### Configuration Models

Pydantic models for YAML configuration:

```python
from hermes.core.config import (
    HermesConfig,
    ModuleConfig,
    ModuleType,
    ExecutionConfig,
    ExecutionMode,
    WireConfig,
    SignalConfig,
)

# Load from YAML
config = HermesConfig.from_yaml("simulation.yaml")

# Access configuration
for name, module in config.modules.items():
    print(f"Module: {name}, Type: {module.type}")

# Execution settings
dt = config.get_dt()  # Timestep in seconds
order = config.get_module_names()  # Execution order
```

**Module Types:**

| Type | Description |
|------|-------------|
| `ModuleType.PROCESS` | External executable (C, C++, Rust) |
| `ModuleType.SCRIPT` | Python script as subprocess |
| `ModuleType.INPROC` | In-process (future: pybind11) |

**Execution Modes:**

| Mode | Description |
|------|-------------|
| `ExecutionMode.REALTIME` | Paced to wall-clock |
| `ExecutionMode.AFAP` | As fast as possible |
| `ExecutionMode.SINGLE_FRAME` | Manual stepping |

### ModuleProcess

Manages a single module subprocess:

```python
from hermes.core.process import ModuleProcess, ModuleState

# ModuleProcess handles:
# - Spawning the subprocess
# - Environment setup (SHM name, barrier name)
# - Lifecycle transitions

module.load()       # Start the process
module.stage()      # Signal to initialize
module.terminate()  # Graceful shutdown
module.kill()       # Force kill

# State tracking
state = module.state  # ModuleState.INIT, STAGED, RUNNING, DONE, ERROR
pid = module.pid      # Process ID
alive = module.is_alive  # Whether process is running
```

**Module Lifecycle:**

```
    load()        stage()       step()...      terminate()
      │             │              │               │
      ▼             ▼              ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐     ┌─────────┐
│  INIT   │──▶│ STAGED  │──▶│ RUNNING │────▶│  DONE   │
└─────────┘   └─────────┘   └─────────┘     └─────────┘
```

### ProcessManager

Coordinates all module processes and IPC resources:

```python
from hermes.core.process import ProcessManager
from hermes.core.config import HermesConfig

config = HermesConfig.from_yaml("sim.yaml")

# Context manager handles setup and cleanup
with ProcessManager(config) as pm:
    pm.load_all()    # Start all module processes
    pm.stage_all()   # Stage all modules

    # Run simulation frames
    for _ in range(100):
        pm.update_time(frame, time)
        pm.step_all()  # Synchronized step

# Automatically calls pm.terminate_all() on exit
```

**ProcessManager responsibilities:**

1. Create shared memory segment with all signals
2. Create synchronization barrier
3. Spawn and manage module processes
4. Coordinate frame stepping via barrier
5. Clean up resources on shutdown

### Scheduler

High-level simulation control:

```python
from hermes.core.scheduler import Scheduler
from hermes.core.process import ProcessManager
from hermes.core.config import HermesConfig

config = HermesConfig.from_yaml("sim.yaml")

with ProcessManager(config) as pm:
    pm.load_all()

    scheduler = Scheduler(pm, config.execution)

    # Stage simulation
    scheduler.stage()

    # Manual stepping
    scheduler.step(10)  # Run 10 frames

    # Or run until end_time
    async def telemetry(frame: int, time: float) -> None:
        if frame % 100 == 0:
            print(f"Frame {frame}, Time {time:.3f}s")

    await scheduler.run(callback=telemetry)

    # Control
    scheduler.pause()
    scheduler.resume()
    scheduler.stop()
```

**Scheduler properties:**

| Property | Description |
|----------|-------------|
| `frame` | Current frame number |
| `time` | Current simulation time (float seconds, derived from time_ns) |
| `time_ns` | Current simulation time (integer nanoseconds, authoritative) |
| `dt` | Timestep (float seconds, derived from dt_ns) |
| `dt_ns` | Timestep (integer nanoseconds, authoritative) |
| `running` | Whether run loop is active |
| `paused` | Whether simulation is paused |
| `mode` | Current execution mode |

**Deterministic Time:**

The scheduler uses integer nanoseconds internally for determinism. Any positive
`rate_hz` is allowed—rates that don't divide evenly into 1 billion are rounded
to the nearest nanosecond.

---

## Scripting Layer

### SimulationAPI

Python API for runtime inspection and injection:

```python
from hermes.scripting.api import SimulationAPI

# Connect to running simulation
with SimulationAPI("/hermes_sim") as sim:
    # Read signals
    x = sim.get("vehicle.position.x")

    # Write signals (if writable)
    sim.set("controller.thrust_cmd", 1000.0)

    # Batch operations
    sim.inject({
        "controller.thrust_cmd": 1000.0,
        "controller.pitch_cmd": 0.1,
    })

    values = sim.sample([
        "vehicle.position.x",
        "vehicle.position.y",
    ])

    # Wait for specific frame
    sim.wait_frame(100, timeout=10.0)

    # Get timing info
    frame = sim.get_frame()
    time = sim.get_time()        # Float seconds
    time_ns = sim.get_time_ns()  # Integer nanoseconds (deterministic)

    # Wait for specific time (nanosecond version for determinism)
    sim.wait_time_ns(1_000_000_000, timeout=10.0)  # Wait for 1 second
```

---

## CLI Layer

### Commands

```bash
# Run simulation
hermes run config.yaml
hermes run config.yaml --verbose
hermes run config.yaml --quiet

# Validate configuration
hermes validate config.yaml

# List signals from running simulation
hermes list-signals --shm-name /hermes_sim
```

---

## Data Flow

Here's how data flows through the system during a simulation frame:

```
1. Scheduler.step() called
        │
        ▼
2. ProcessManager.update_time()
   - Writes frame/time to shared memory
        │
        ▼
3. ProcessManager.step_all()
   - FrameBarrier.signal_step() releases all modules
        │
        ▼
4. Each module:
   - FrameBarrier.wait_step() returns
   - Reads inputs from shared memory
   - Executes physics/logic
   - Writes outputs to shared memory
   - FrameBarrier.signal_done()
        │
        ▼
5. ProcessManager waits:
   - FrameBarrier.wait_all_done()
        │
        ▼
6. Scheduler increments frame/time
        │
        ▼
7. Repeat for next frame
```

---

## Thread/Process Safety

- **SharedMemoryManager**: Thread-safe for concurrent reads; writes should be synchronized externally
- **FrameBarrier**: Designed for multi-process synchronization
- **Scheduler**: Single-threaded; use async/await for non-blocking operation
- **SignalRegistry**: Not thread-safe; populate before starting simulation
