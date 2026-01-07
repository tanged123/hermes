# Phase 3: Multi-Module & Wiring

**Goal:** Multiple modules with signal routing
**Status:** Not Started
**Blocked By:** Phase 2 Complete
**Exit Criteria:** Injection module can override simulation inputs via wiring

---

## Overview

Phase 3 extends Hermes to support multiple simulation modules with signal wiring between them. This enables test scenarios where external signals can be injected into the simulation (e.g., overriding sensor inputs, commanding actuators).

With the multi-process IPC architecture, modules are separate processes that communicate through shared memory. Wire routing reads values from source signals and writes to destination signals after each simulation step.

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
│  │  │  Icarus Signals   │ ◄─wire──│ Injection Signals │              │ │
│  │  │  (Vehicle.*)      │         │ (thrust_cmd, etc) │              │ │
│  │  └───────────────────┘         └───────────────────┘              │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                    │                        │                            │
│                    ▼                        ▼                            │
│  ┌──────────────────────┐    ┌──────────────────────┐                  │
│  │   Icarus Module      │    │   Injection Module    │                  │
│  │   (C++ Process)      │    │   (Python Script)     │                  │
│  │                      │    │                       │                  │
│  │  • Reads inputs      │    │  • Writes commands    │                  │
│  │  • Computes physics  │    │  • Scripted values    │                  │
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

**Issue ID:** (create after Phase 2)
**Priority:** Critical (P0)
**Blocked By:** Phase 2

### Objective
Create a simple Python module that stores and exposes injectable signals.

### Deliverables
- `src/hermes/modules/injection.py`
- Module runner script

### Features
- Configurable signal list from YAML
- Values persist between steps (no internal dynamics)
- All signals writable via shared memory
- Zero initial values
- Implements module protocol

### Configuration
```yaml
modules:
  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: thrust_command
        type: f64
        unit: N
        writable: true
      - name: pitch_command
        type: f64
        unit: deg
        writable: true
```

### Implementation
```python
"""Injection module for test signal input."""
import sys
from hermes.backplane.shm import SharedMemoryManager

class InjectionModule:
    """Simple module that holds writable signal values."""

    def __init__(self, shm_name: str, signals: list[str]) -> None:
        self._shm = SharedMemoryManager(shm_name)
        self._shm.attach()
        self._signals = signals
        self._values: dict[str, float] = {s: 0.0 for s in signals}

    def init(self, config_path: str) -> int:
        """Initialize module (no-op for injection)."""
        return 0

    def stage(self) -> int:
        """Stage module - write initial zeros."""
        for signal in self._signals:
            self._shm.set_signal(f"inputs.{signal}", 0.0)
        return 0

    def step(self, dt: float) -> int:
        """Step module - values persist, no dynamics."""
        return 0

    def reset(self) -> int:
        """Reset to zeros."""
        for signal in self._signals:
            self._shm.set_signal(f"inputs.{signal}", 0.0)
        return 0

    def terminate(self) -> None:
        """Cleanup."""
        self._shm.detach()
```

### Acceptance Criteria
- [ ] Implements module protocol
- [ ] Signals configurable via YAML
- [ ] Values readable/writable through shared memory
- [ ] Step is no-op (values persist)
- [ ] Reset zeros all values

---

## Task 3.2: Wire Configuration

**Issue ID:** (create after Phase 2)
**Priority:** Critical (P0)
**Blocked By:** Task 3.1

### Objective
Parse and validate wiring configuration from YAML.

### Deliverables
- Enhanced `WireConfig` in `config.py`
- Wire validation in ProcessManager

### Wire Format
```yaml
wiring:
  - src: inputs.thrust_command
    dst: icarus.Vehicle.thrust
    gain: 1.0
    offset: 0.0

  - src: inputs.pitch_command
    dst: icarus.Vehicle.control.pitch
    gain: 0.0174533  # deg to rad
```

### Validation Rules
- Source module must exist in config
- Source signal must exist in shared memory registry
- Destination module must exist in config
- Destination signal must exist and be writable
- No self-wiring (src == dst)
- No circular dependencies (future enhancement)

### Implementation
```python
from pydantic import BaseModel, model_validator

class WireConfig(BaseModel):
    src: str
    dst: str
    gain: float = 1.0
    offset: float = 0.0

    @model_validator(mode="after")
    def validate_wire(self) -> "WireConfig":
        if self.src == self.dst:
            raise ValueError("Cannot wire signal to itself")
        if "." not in self.src:
            raise ValueError(f"Source must be qualified name: {self.src}")
        if "." not in self.dst:
            raise ValueError(f"Destination must be qualified name: {self.dst}")
        return self

class WireValidator:
    """Validates wires against shared memory registry."""

    def __init__(self, shm: SharedMemoryManager) -> None:
        self._shm = shm

    def validate(self, wire: WireConfig) -> None:
        # Check source exists
        try:
            self._shm.get_signal(wire.src)
        except KeyError:
            raise ValueError(f"Source signal not found: {wire.src}")

        # Check destination exists and is writable
        try:
            desc = self._shm.get_descriptor(wire.dst)
            if not desc.flags & SignalFlags.WRITABLE:
                raise ValueError(f"Destination not writable: {wire.dst}")
        except KeyError:
            raise ValueError(f"Destination signal not found: {wire.dst}")
```

### Acceptance Criteria
- [ ] Wire config parses from YAML
- [ ] Validation errors are clear and actionable
- [ ] Gain/offset have defaults (1.0, 0.0)
- [ ] Invalid configs rejected with helpful messages

---

## Task 3.3: Wire Router

**Issue ID:** (create after Phase 2)
**Priority:** Critical (P0)
**Blocked By:** Task 3.2

### Objective
Implement signal transfer with gain and offset through shared memory.

### Deliverables
- `src/hermes/core/router.py`
- `WireRouter` class

### Implementation
```python
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
    """Routes signals between modules via shared memory."""

    def __init__(self, shm: SharedMemoryManager) -> None:
        self._shm = shm
        self._wires: list[CompiledWire] = []

    def add_wire(self, config: WireConfig) -> None:
        """Add a wire (must be validated first)."""
        self._wires.append(CompiledWire(
            src=config.src,
            dst=config.dst,
            gain=config.gain,
            offset=config.offset,
        ))

    def route(self) -> None:
        """Execute all wire transfers."""
        for wire in self._wires:
            value = self._shm.get_signal(wire.src)
            transformed = value * wire.gain + wire.offset
            self._shm.set_signal(wire.dst, transformed)

    def clear(self) -> None:
        """Remove all wires."""
        self._wires.clear()
```

### Routing Order
1. All modules step (update their signals)
2. Router executes all wires in definition order
3. Telemetry is sampled (sees post-routing values)

### Scheduler Integration
```python
def step(self) -> None:
    """Execute one simulation frame."""
    # 1. Step all modules
    self._pm.step_all()

    # 2. Route signals
    self._router.route()

    # 3. Update time
    self._time += self.dt
    self._frame += 1
```

### Acceptance Criteria
- [ ] Values transfer correctly through shared memory
- [ ] Gain multiplies value
- [ ] Offset adds to result
- [ ] Multiple wires work
- [ ] Order matches config order
- [ ] Routing happens after all modules step

---

## Task 3.4: Multi-Module Schema

**Issue ID:** (create after Phase 2)
**Priority:** High (P1)
**Blocked By:** Task 3.3

### Objective
Generate combined schema from all registered modules for WebSocket clients.

### Schema Format
```json
{
  "version": "0.2",
  "modules": {
    "icarus": {
      "type": "process",
      "signals": {
        "Vehicle.position.x": {"type": "f64", "unit": "m", "writable": false},
        "Vehicle.position.y": {"type": "f64", "unit": "m", "writable": false},
        "Vehicle.thrust": {"type": "f64", "unit": "N", "writable": true}
      }
    },
    "inputs": {
      "type": "script",
      "signals": {
        "thrust_command": {"type": "f64", "unit": "N", "writable": true}
      }
    }
  },
  "wiring": [
    {
      "src": "inputs.thrust_command",
      "dst": "icarus.Vehicle.thrust",
      "gain": 1.0,
      "offset": 0.0
    }
  ]
}
```

### Implementation
```python
def get_schema(self) -> dict:
    """Generate schema from shared memory registry."""
    schema = {
        "version": "0.2",
        "modules": {},
        "wiring": [],
    }

    # Collect signals by module
    for qualified_name, descriptor in self._registry.all_signals().items():
        module, signal = qualified_name.split(".", 1)
        if module not in schema["modules"]:
            schema["modules"][module] = {"signals": {}}
        schema["modules"][module]["signals"][signal] = {
            "type": descriptor.type.name.lower(),
            "unit": descriptor.unit,
            "writable": bool(descriptor.flags & SignalFlags.WRITABLE),
        }

    # Add wiring info
    for wire in self._wires:
        schema["wiring"].append({
            "src": wire.src,
            "dst": wire.dst,
            "gain": wire.gain,
            "offset": wire.offset,
        })

    return schema
```

### Acceptance Criteria
- [ ] All modules included in schema
- [ ] All signals listed with metadata
- [ ] Wiring included in schema
- [ ] JSON serializable
- [ ] Sent to clients on connect

---

## Task 3.5: Dynamic Signal Discovery

**Issue ID:** (create after Phase 2)
**Priority:** High (P1)
**Blocked By:** Task 3.4

### Objective
Allow modules to dynamically register their signals during initialization.

### Signal Discovery Protocol
```python
# Module advertises signals during init
def init(self, config_path: str, shm_name: str) -> int:
    # Read config
    config = load_config(config_path)

    # Register signals with shared memory
    for signal in self.discover_signals():
        shm.register_signal(
            name=f"{self.name}.{signal.name}",
            type=signal.type,
            flags=signal.flags,
            unit=signal.unit,
        )

    return 0
```

### Signal Advertisement via YAML
```yaml
modules:
  icarus:
    type: process
    executable: ./icarus_sim
    config: ./icarus_config.yaml
    # Signals discovered from icarus at runtime
    # OR explicitly listed:
    signals:
      - name: Vehicle.position.x
        type: f64
        unit: m
        writable: false
```

### Acceptance Criteria
- [ ] Modules can register signals during init
- [ ] Static signal lists from YAML work
- [ ] Dynamic discovery from executables work
- [ ] Signal metadata stored in registry

---

## Task 3.6: Multi-Module Integration Test

**Issue ID:** (create after Phase 2)
**Priority:** High (P1)
**Blocked By:** Task 3.5

### Objective
Integration test with multiple modules and wiring.

### Test Scenario
1. Configure mock "physics" module with input/output signals
2. Configure injection module with command signals
3. Wire `inputs.command` → `physics.input`
4. Set injection value via scripting API
5. Step simulation
6. Verify physics module received wired value
7. Verify telemetry shows both modules

### Deliverables
- `tests/integration/test_multimodule.py`
- Multi-module example config
- Mock physics module for testing

### Test Implementation
```python
@pytest.fixture
def multi_module_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""
version: "0.2"
modules:
  physics:
    type: script
    script: tests.fixtures.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
        writable: false

  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: command
        type: f64
        writable: true

wiring:
  - src: inputs.command
    dst: physics.input
    gain: 2.0
    offset: 10.0

execution:
  mode: single_frame
  rate_hz: 100.0
""")
    return config

def test_wiring(multi_module_config):
    with ProcessManager.from_yaml(multi_module_config) as pm:
        scheduler = Scheduler(pm, pm.config.execution)
        scheduler.stage()

        # Set injection value
        pm.shm.set_signal("inputs.command", 5.0)

        # Step simulation
        scheduler.step()

        # Wire should transform: 5.0 * 2.0 + 10.0 = 20.0
        assert pm.shm.get_signal("physics.input") == 20.0
```

### Acceptance Criteria
- [ ] Both modules register successfully
- [ ] Wire validation passes
- [ ] Signal routing works with gain/offset
- [ ] Combined schema correct
- [ ] End-to-end test passes

---

## Example Multi-Module Configuration

```yaml
# examples/multi_module.yaml
version: "0.2"

modules:
  icarus:
    type: process
    executable: ./icarus_sim
    config: ./icarus_config.yaml

  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: thrust_command
        type: f64
        unit: N
        writable: true
      - name: pitch_command
        type: f64
        unit: deg
        writable: true
      - name: yaw_command
        type: f64
        unit: deg
        writable: true

wiring:
  - src: inputs.thrust_command
    dst: icarus.Vehicle.thrust

  - src: inputs.pitch_command
    dst: icarus.Vehicle.control.pitch
    gain: 0.0174533  # deg to rad

  - src: inputs.yaw_command
    dst: icarus.Vehicle.control.yaw
    gain: 0.0174533

execution:
  mode: afap
  rate_hz: 100.0
  end_time: 10.0
  schedule:
    - inputs    # Injection first
    - icarus    # Physics second

server:
  enabled: true
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

---

## Beads Integration

Issues will be created after Phase 2 is complete:

```bash
# Create Phase 3 issues
bd create --title "Injection Module" -d "Python script module for test signal input" -p 0 -l phase3,module
bd create --title "Wire Configuration" -d "YAML parsing and validation for wiring" -p 0 -l phase3,config
bd create --title "Wire Router" -d "Signal routing with gain/offset via shared memory" -p 0 -l phase3,core
bd create --title "Multi-Module Schema" -d "Combined schema generation for WebSocket" -p 1 -l phase3,server
bd create --title "Dynamic Signal Discovery" -d "Runtime signal registration by modules" -p 1 -l phase3,core
bd create --title "Multi-Module Integration Test" -d "End-to-end test with wiring" -p 1 -l phase3,tests

# View phase 3 work
bd list --label phase3
```

---

## Phase 3 Completion Checklist

- [ ] All Phase 3 issues closed
- [ ] `./scripts/ci.sh` passes
- [ ] Injection module works standalone
- [ ] Multi-module config loads successfully
- [ ] Wiring routes signals correctly with transforms
- [ ] Combined schema served to WebSocket clients
- [ ] Integration test passes
- [ ] `bd sync && git push` completed

---

## Architecture After Phase 3

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            HERMES v0.2                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Configuration                                                          │
│  ┌──────────┐                                                           │
│  │  YAML    │──▶ Pydantic Validation ──▶ HermesConfig                  │
│  └──────────┘                                                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   Shared Memory Backplane                          │ │
│  │  ┌─────────┐ ┌─────────────────┐ ┌─────────────────┐              │ │
│  │  │ Header  │ │ Signal Registry │ │  Data Region    │              │ │
│  │  └─────────┘ └─────────────────┘ └─────────────────┘              │ │
│  └─────────────────────────┬──────────────────────────────────────────┘ │
│                            │                                             │
│  Module Layer              │                                             │
│  ┌──────────┐  ┌──────────┴─┐  ┌──────────┐                           │
│  │  Icarus  │  │ Injection  │  │  Script  │  (future)                 │
│  │  Process │  │  Module    │  │  Module  │                           │
│  └────┬─────┘  └─────┬──────┘  └────┬─────┘                           │
│       │              │              │                                   │
│       └──────────────┼──────────────┘                                   │
│                      │                                                   │
│  Core Layer          ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Process Manager                              │  │
│  │  • Module lifecycle                                               │  │
│  │  • Barrier synchronization                                        │  │
│  │  • Wire routing                                                   │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                            │
│  ┌──────────────────────────▼───────────────────────────────────────┐  │
│  │                        Scheduler                                  │  │
│  │  • Frame loop                                                     │  │
│  │  • Time tracking                                                  │  │
│  │  • Mode control                                                   │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                            │
│  Server Layer              ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     WebSocket Server                              │  │
│  │  • Protocol handling                                              │  │
│  │  • Telemetry streaming (reads shared memory)                     │  │
│  │  • Client management                                              │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                            │
└─────────────────────────────┼────────────────────────────────────────────┘
                              │
                              ▼
                      ┌───────────────┐
                      │   Daedalus    │
                      │ Visualization │
                      └───────────────┘
```

---

## Next Phase Preview

Phase 4 (Polish & Documentation) will:
- Add comprehensive error handling for IPC failures
- Enhance configuration validation
- Complete protocol documentation
- Create example configurations
- Set up CI/CD pipeline

See `phase4_polish.md` for details.
