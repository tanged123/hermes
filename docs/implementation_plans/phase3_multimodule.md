# Phase 3: Multi-Module & Wiring

**Goal:** Multiple modules with signal routing
**Status:** Not Started
**Blocked By:** Phase 2 Complete
**Exit Criteria:** Wire routing works between Python script modules with gain/offset transforms

---

## Overview

Phase 3 extends Hermes to support multiple simulation modules with signal wiring between them. This phase focuses on the **generic infrastructure** for multi-module orchestration using pure Python modules for testing.

The infrastructure built here will be reused by Phase 3.5 (Icarus Integration) for actual physics simulation.

## Architecture Context

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              HERMES                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   Shared Memory Backplane                          │ │
│  │                                                                     │ │
│  │  ┌───────────────────┐         ┌───────────────────┐              │ │
│  │  │  Physics Signals  │ ◄─wire──│ Injection Signals │              │ │
│  │  │  (output, state)  │         │ (input_cmd, etc)  │              │ │
│  │  └───────────────────┘         └───────────────────┘              │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                    │                        │                            │
│                    ▼                        ▼                            │
│  ┌──────────────────────┐    ┌──────────────────────┐                  │
│  │   Physics Module     │    │   Injection Module    │                  │
│  │   (Python Script)    │    │   (Python Script)     │                  │
│  │                      │    │                       │                  │
│  │  • Reads inputs      │    │  • Writes commands    │                  │
│  │  • Simple dynamics   │    │  • Scripted values    │                  │
│  │  • Writes outputs    │    │  • Test scenarios     │                  │
│  └──────────────────────┘    └──────────────────────┘                  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        Wire Router                                 │ │
│  │  After each step: src → transform → dst                           │ │
│  │  dst_value = src_value * gain + offset                            │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Dependencies

- Phase 2 complete (WebSocket server functional)
- Core IPC backplane from Phase 1

---

## Task 3.1: Injection Module

**Priority:** P0 (Critical)
**Blocked By:** Phase 2

### Objective
Create a simple Python module that stores and exposes injectable signals.

### Deliverables
- `src/hermes/modules/injection.py`
- Module runner integration

### Features
- Configurable signal list from YAML
- Values persist between steps (no internal dynamics)
- All signals writable via shared memory
- Zero initial values
- Implements module protocol (stage, step, reset)

### Configuration
```yaml
modules:
  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: thrust_cmd
        type: f64
        unit: N
        writable: true
      - name: pitch_cmd
        type: f64
        unit: deg
        writable: true
```

### Implementation
```python
"""Injection module for test signal input."""
from hermes.backplane.shm import SharedMemoryManager


class InjectionModule:
    """Simple module that holds writable signal values.

    Values persist between steps - no internal dynamics.
    External systems can write to these signals via shared memory
    or WebSocket commands, and wires route them to physics modules.
    """

    def __init__(self, module_name: str, shm: SharedMemoryManager, signals: list[str]) -> None:
        self._name = module_name
        self._shm = shm
        self._signals = signals

    def stage(self) -> None:
        """Stage module - write initial zeros to all signals."""
        for signal in self._signals:
            self._shm.set_signal(f"{self._name}.{signal}", 0.0)

    def step(self, dt: float) -> None:
        """Step module - no-op, values persist."""
        pass

    def reset(self) -> None:
        """Reset all signals to zero."""
        for signal in self._signals:
            self._shm.set_signal(f"{self._name}.{signal}", 0.0)
```

### Acceptance Criteria
- [ ] Implements module protocol (stage, step, reset)
- [ ] Signals configurable via YAML
- [ ] Values readable/writable through shared memory
- [ ] Step is no-op (values persist)
- [ ] Reset zeros all values

---

## Task 3.2: Mock Physics Module

**Priority:** P0 (Critical)
**Blocked By:** Task 3.1

### Objective
Create a simple physics module for testing wire routing without external dependencies.

### Deliverables
- `src/hermes/modules/mock_physics.py`
- Test fixtures

### Features
- Reads input signals (writable)
- Computes simple dynamics: `output = input * 2 + state`
- Writes output signals (read-only)
- Maintains internal state across steps

### Configuration
```yaml
modules:
  physics:
    type: script
    script: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
        writable: false
      - name: state
        type: f64
        writable: false
```

### Implementation
```python
"""Mock physics module for testing wire routing."""
from hermes.backplane.shm import SharedMemoryManager


class MockPhysicsModule:
    """Simple physics module with basic dynamics.

    Computes: output = input * 2 + state
    State accumulates: state += input * dt
    """

    def __init__(self, module_name: str, shm: SharedMemoryManager) -> None:
        self._name = module_name
        self._shm = shm
        self._state = 0.0

    def stage(self) -> None:
        """Initialize signals to zero."""
        self._state = 0.0
        self._shm.set_signal(f"{self._name}.input", 0.0)
        self._shm.set_signal(f"{self._name}.output", 0.0)
        self._shm.set_signal(f"{self._name}.state", 0.0)

    def step(self, dt: float) -> None:
        """Execute physics step."""
        input_val = self._shm.get_signal(f"{self._name}.input")

        # Simple dynamics
        self._state += input_val * dt
        output = input_val * 2.0 + self._state

        self._shm.set_signal(f"{self._name}.output", output)
        self._shm.set_signal(f"{self._name}.state", self._state)

    def reset(self) -> None:
        """Reset to initial state."""
        self._state = 0.0
        self._shm.set_signal(f"{self._name}.input", 0.0)
        self._shm.set_signal(f"{self._name}.output", 0.0)
        self._shm.set_signal(f"{self._name}.state", 0.0)
```

### Acceptance Criteria
- [ ] Implements module protocol
- [ ] Reads input from shared memory
- [ ] Computes deterministic output
- [ ] Maintains state across steps
- [ ] Reset restores initial state

---

## Task 3.3: Wire Router

**Priority:** P0 (Critical)
**Blocked By:** Task 3.2

### Objective
Implement signal transfer with gain and offset through shared memory.

### Deliverables
- `src/hermes/core/router.py`
- `WireRouter` class
- Wire validation

### Wire Transform
```
dst_value = src_value * gain + offset
```

### Implementation
```python
"""Wire router for inter-module signal routing."""
from dataclasses import dataclass

from hermes.backplane.shm import SharedMemoryManager
from hermes.core.config import WireConfig


@dataclass
class CompiledWire:
    """Pre-validated wire for fast routing."""
    src: str
    dst: str
    gain: float
    offset: float


class WireRouter:
    """Routes signals between modules via shared memory.

    Wires are executed after all modules step, transferring
    values from source signals to destination signals with
    optional gain and offset transforms.
    """

    def __init__(self, shm: SharedMemoryManager) -> None:
        self._shm = shm
        self._wires: list[CompiledWire] = []

    def add_wire(self, config: WireConfig) -> None:
        """Add a wire from configuration.

        Args:
            config: Wire configuration with src, dst, gain, offset
        """
        self._wires.append(CompiledWire(
            src=config.src,
            dst=config.dst,
            gain=config.gain,
            offset=config.offset,
        ))

    def validate(self) -> None:
        """Validate all wires against shared memory registry.

        Raises:
            ValueError: If source or destination signal not found
        """
        signal_names = set(self._shm.signal_names())

        for wire in self._wires:
            if wire.src not in signal_names:
                raise ValueError(f"Wire source signal not found: {wire.src}")
            if wire.dst not in signal_names:
                raise ValueError(f"Wire destination signal not found: {wire.dst}")

    def route(self) -> None:
        """Execute all wire transfers."""
        for wire in self._wires:
            value = self._shm.get_signal(wire.src)
            transformed = value * wire.gain + wire.offset
            self._shm.set_signal(wire.dst, transformed)

    @property
    def wire_count(self) -> int:
        """Number of configured wires."""
        return len(self._wires)

    def clear(self) -> None:
        """Remove all wires."""
        self._wires.clear()
```

### Scheduler Integration
```python
def step(self) -> None:
    """Execute one simulation frame."""
    # 1. Step all modules
    self._pm.step_all()

    # 2. Route signals (after all modules have updated)
    self._router.route()

    # 3. Update time
    self._time_ns += self._dt_ns
    self._frame += 1
```

### Acceptance Criteria
- [ ] Values transfer correctly through shared memory
- [ ] Gain multiplies value
- [ ] Offset adds to result
- [ ] Multiple wires work
- [ ] Order matches config order
- [ ] Routing happens after all modules step
- [ ] Validation catches missing signals

---

## Task 3.4: Scheduler Wire Integration

**Priority:** P0 (Critical)
**Blocked By:** Task 3.3

### Objective
Integrate wire routing into the scheduler execution loop.

### Deliverables
- Updated `Scheduler` class
- Wire setup during `stage()`

### Implementation
```python
class Scheduler:
    def __init__(self, pm: ProcessManager, config: ExecutionConfig) -> None:
        self._pm = pm
        self._config = config
        self._router = WireRouter(pm.shm)
        # ... existing init

    def stage(self) -> None:
        """Stage simulation with wire validation."""
        # Stage all modules
        self._pm.stage_all()

        # Configure wires from config
        for wire_config in self._pm.config.wiring:
            self._router.add_wire(wire_config)

        # Validate wires against actual signals
        self._router.validate()

        # ... existing stage logic

    def _execute_frame(self) -> None:
        """Execute single simulation frame."""
        # Step all modules
        self._pm.step_all()

        # Route signals
        self._router.route()

        # Update frame/time
        # ...
```

### Acceptance Criteria
- [ ] Wires configured from HermesConfig
- [ ] Wire validation during stage
- [ ] Routing executes after module steps
- [ ] Clear errors for invalid wires

---

## Task 3.5: Multi-Module Integration Test

**Priority:** P1 (High)
**Blocked By:** Task 3.4

### Objective
Integration test with multiple modules and wiring.

### Deliverables
- `tests/test_integration/test_multimodule.py`
- Multi-module example config

### Test Scenarios

1. **Basic Wiring**
   - Injection module → Physics module
   - Verify value transfer with gain/offset

2. **Multiple Wires**
   - Multiple injection signals routed to physics
   - Verify all transfers work

3. **Wire Validation**
   - Missing source signal → clear error
   - Missing destination signal → clear error

4. **Reset Behavior**
   - Reset should re-initialize all modules
   - Wire state preserved (wires are config, not state)

### Test Implementation
```python
import pytest
from hermes.core.config import HermesConfig
from hermes.core.process import ProcessManager
from hermes.core.scheduler import Scheduler


class TestMultiModuleWiring:
    """Tests for multi-module wire routing."""

    def test_basic_wire_routing(self, tmp_path):
        """Wire should transfer value with gain/offset."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
version: "0.2"
modules:
  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
  physics:
    type: script
    script: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64

wiring:
  - src: inputs.cmd
    dst: physics.input
    gain: 2.0
    offset: 10.0

execution:
  mode: single_frame
  rate_hz: 100.0
""")

        with ProcessManager.from_yaml(config_yaml) as pm:
            sched = Scheduler(pm, pm.config.execution)
            sched.stage()

            # Set injection value
            pm.shm.set_signal("inputs.cmd", 5.0)

            # Step simulation (routes wires)
            sched.step()

            # Wire transform: 5.0 * 2.0 + 10.0 = 20.0
            assert pm.shm.get_signal("physics.input") == pytest.approx(20.0)

    def test_invalid_wire_source_raises(self, tmp_path):
        """Invalid wire source should raise during stage."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
version: "0.2"
modules:
  physics:
    type: script
    script: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true

wiring:
  - src: nonexistent.signal
    dst: physics.input

execution:
  mode: single_frame
  rate_hz: 100.0
""")

        with ProcessManager.from_yaml(config_yaml) as pm:
            sched = Scheduler(pm, pm.config.execution)

            with pytest.raises(ValueError, match="source signal not found"):
                sched.stage()
```

### Acceptance Criteria
- [ ] Basic wire routing works
- [ ] Gain/offset transforms correct
- [ ] Multiple wires work
- [ ] Wire validation catches errors
- [ ] Reset preserves wire config
- [ ] All tests pass

---

## Task 3.6: Multi-Module Schema for WebSocket

**Priority:** P1 (High)
**Blocked By:** Task 3.5

### Objective
Include wiring information in schema sent to WebSocket clients.

### Schema Format
```json
{
  "type": "schema",
  "payload": {
    "version": "0.2",
    "modules": {
      "inputs": {
        "signals": [
          {"name": "cmd", "type": "f64", "writable": true}
        ]
      },
      "physics": {
        "signals": [
          {"name": "input", "type": "f64", "writable": true},
          {"name": "output", "type": "f64", "writable": false}
        ]
      }
    },
    "wiring": [
      {"src": "inputs.cmd", "dst": "physics.input", "gain": 2.0, "offset": 10.0}
    ]
  }
}
```

### Acceptance Criteria
- [ ] Schema includes all modules
- [ ] Schema includes all signals with metadata
- [ ] Schema includes wiring configuration
- [ ] JSON serializable
- [ ] Sent to clients on connect

---

## Task 3.7: Multi-Rate Scheduling

**Priority:** P1 (High)
**Blocked By:** Task 3.4

### Objective
Support modules running at different rates within the same simulation. Physics modules typically need higher fidelity (e.g., 1000 Hz) than control/flight software modules (e.g., 200 Hz).

### Concept
The scheduler defines a **major frame** at the slowest module rate. Faster modules step multiple times per major frame. Wire routing happens at the major frame boundary after all sub-steps complete.

```
Major frame at 200 Hz (5ms):
  ┌─────────────────────────────────────────────┐
  │  flight_sw.step(dt=5ms)        # 1x @ 200Hz │
  │  physics.step(dt=1ms)          # 5x @ 1kHz  │
  │  physics.step(dt=1ms)                        │
  │  physics.step(dt=1ms)                        │
  │  physics.step(dt=1ms)                        │
  │  physics.step(dt=1ms)                        │
  │  wire_router.route()                          │
  └─────────────────────────────────────────────┘
```

### Configuration
```yaml
execution:
  mode: realtime
  rate_hz: 200.0       # Major frame rate (GCD or explicit)
  schedule:
    - name: flight_sw
      rate_hz: 200.0   # 1x per major frame
    - name: physics
      rate_hz: 1000.0  # 5x per major frame
```

### Implementation

#### 1. Config (`src/hermes/core/config.py`)

Add `ScheduleEntry` model with backwards-compatible string coercion:

```python
class ScheduleEntry(BaseModel):
    """Single entry in execution schedule."""

    name: str
    rate_hz: float | None = None  # None = inherit execution.rate_hz

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_string(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            return {"name": value}
        return value
```

Change `ExecutionConfig.schedule` from `list[str]` to `list[ScheduleEntry]`.

Add model validator on `ExecutionConfig` to check integer multiple constraint:
```python
ratio = module_rate / major_rate
if abs(ratio - round(ratio)) > 1e-6:
    raise ValueError(...)
```

Add `ExecutionConfig.get_major_frame_rate_hz()` — returns min rate across entries.

Update `HermesConfig.get_module_names()` to extract `.name` from entries.

#### 2. Scheduler (`src/hermes/core/scheduler.py`)

In `__init__`, compute `_dt_ns` from major frame rate and pre-compute per-module substeps:
```python
self._module_substeps: dict[str, tuple[int, float]] = {}
# e.g. {"inputs": (1, 0.005), "physics": (5, 0.001)}
```

In `step()`, when schedule exists, iterate modules in order and sub-step each:
```python
for entry in schedule:
    substeps, module_dt = self._module_substeps[entry.name]
    inproc = self._pm.get_inproc_module(entry.name)
    for _ in range(substeps):
        inproc.step(module_dt)
```

Wire routing once per major frame (before modules, same as current).
Fallback to `step_all()` when no schedule is configured.

#### 3. ProcessManager (`src/hermes/core/process.py`)

Minimal changes. `get_inproc_module()` already exists. `step_all()` stays for
the no-schedule fallback. May need `step_all()` to accept optional `dt` if
major frame rate differs from `config.rate_hz`.

### Validation Rules
- Module `rate_hz` must be >= major frame rate
- Module `rate_hz` must be an integer multiple of major frame rate
- Clear error if rates are incompatible

### Test Plan
- **Config**: `ScheduleEntry` string coercion, multi-rate validation (valid + invalid), `get_major_frame_rate_hz()`, backwards compat
- **Scheduler**: Substep computation, verify fast module steps Nx with correct dt
- **Integration**: Injection @ 200Hz + physics @ 1000Hz, verify state accumulates 5x per major frame

### Files to Modify
- `src/hermes/core/config.py`
- `src/hermes/core/scheduler.py`
- `src/hermes/core/process.py` (minor)
- `tests/test_core/test_config.py`
- `tests/test_core/test_scheduler.py`
- `tests/test_integration/test_multimodule.py`

### Acceptance Criteria
- [ ] Per-module `rate_hz` in schedule config
- [ ] Faster modules step multiple times per major frame
- [ ] Each module gets correct `dt` for its rate
- [ ] Wire routing at major frame boundary
- [ ] Validation rejects non-integer rate ratios
- [ ] Backwards compatible (omitted `rate_hz` defaults to execution rate)
- [ ] Integration test with 2 modules at different rates

---

## Phase 3 Completion Checklist

- [ ] All Phase 3 tasks complete
- [ ] `./scripts/ci.sh` passes
- [ ] Injection module works
- [ ] Mock physics module works
- [ ] Wire routing works with gain/offset
- [ ] Multi-rate scheduling works
- [ ] Multi-module schema served to WebSocket clients
- [ ] Integration tests pass
- [ ] Example configuration works

---

## Example Configuration

```yaml
# examples/multi_module.yaml
version: "0.2"

modules:
  # Injection module for test inputs
  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: thrust_cmd
        type: f64
        unit: N
        writable: true
      - name: pitch_cmd
        type: f64
        unit: deg
        writable: true

  # Mock physics for testing
  physics:
    type: script
    script: hermes.modules.mock_physics
    signals:
      - name: thrust_input
        type: f64
        unit: N
        writable: true
      - name: pitch_input
        type: f64
        unit: rad
        writable: true
      - name: altitude
        type: f64
        unit: m
      - name: velocity
        type: f64
        unit: m/s

wiring:
  # Route injection to physics inputs
  - src: inputs.thrust_cmd
    dst: physics.thrust_input

  - src: inputs.pitch_cmd
    dst: physics.pitch_input
    gain: 0.0174533  # deg to rad

execution:
  mode: afap
  rate_hz: 200.0
  end_time: 10.0
  schedule:
    - name: inputs                # Injection first
      rate_hz: 200.0              # Major frame rate
    - name: physics               # Physics second
      rate_hz: 1000.0             # 5x per major frame

server:
  enabled: true
  port: 8765
  telemetry_hz: 60.0
```

---

## Architecture After Phase 3

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            HERMES v0.3                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Configuration                                                          │
│  ┌──────────┐                                                           │
│  │  YAML    │──▶ Pydantic Validation ──▶ HermesConfig                  │
│  └──────────┘         │                                                 │
│                       ▼                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   Shared Memory Backplane                          │ │
│  │  ┌─────────┐ ┌─────────────────┐ ┌─────────────────┐              │ │
│  │  │ Header  │ │ Signal Registry │ │  Data Region    │              │ │
│  │  └─────────┘ └─────────────────┘ └─────────────────┘              │ │
│  └─────────────────────────┬──────────────────────────────────────────┘ │
│                            │                                             │
│  Module Layer              │                                             │
│  ┌──────────┐  ┌──────────┴─┐                                          │
│  │ Injection│  │   Mock     │   ◄── Python script modules              │
│  │  Module  │  │  Physics   │                                          │
│  └────┬─────┘  └─────┬──────┘                                          │
│       │              │                                                   │
│       └──────────────┤                                                   │
│                      │                                                   │
│  Core Layer          ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Wire Router                                  │  │
│  │  • Executes wires after module steps                             │  │
│  │  • Applies gain/offset transforms                                │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                            │
│  ┌──────────────────────────▼───────────────────────────────────────┐  │
│  │                        Scheduler                                  │  │
│  │  • Major frame loop with wire routing                            │  │
│  │  • Multi-rate sub-stepping per module                            │  │
│  │  • Time tracking                                                  │  │
│  │  • Mode control                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Next Phase: Phase 3.5 (Icarus Integration)

Phase 3.5 integrates the Icarus 6DOF physics simulator as a module type,
enabling real aerospace simulation scenarios.

See `phase3.5_icarus.md` for details.
