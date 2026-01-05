# Phase 3: Multi-Module & Wiring

**Goal:** Multiple modules with signal routing
**Status:** Not Started
**Blocked By:** Phase 2 Complete
**Exit Criteria:** Injection adapter can override Icarus inputs via wiring

---

## Overview

Phase 3 extends Hermes to support multiple simulation modules with signal wiring between them. This enables test scenarios where external signals can be injected into the simulation (e.g., overriding sensor inputs, commanding actuators).

## Dependencies

- Phase 2 complete (WebSocket server functional)
- Core abstractions stable

---

## Task 3.1: Injection Adapter

**Issue ID:** `HRM-013`
**Priority:** Critical
**Blocked By:** Phase 2

### Objective
Create a simple adapter that stores and exposes injectable signals.

### Deliverables
- `src/hermes/adapters/injection.py`
- `InjectionAdapter` class

### Features
- Configurable signal list
- Values persist between steps
- All signals writable
- Zero initial values

### Example Usage
```yaml
modules:
  inputs:
    adapter: injection
    signals:
      - commanded_thrust
      - wind_speed
      - sensor_override
```

### Acceptance Criteria
- [ ] Implements ModuleAdapter protocol
- [ ] Signals configurable via config
- [ ] Values readable/writable
- [ ] Step is no-op (values persist)
- [ ] Reset zeros all values

---

## Task 3.2: Wire Configuration

**Issue ID:** `HRM-014`
**Priority:** Critical
**Blocked By:** HRM-013

### Objective
Parse and validate wiring configuration from YAML.

### Deliverables
- Enhanced `WireConfig` in `config.py`
- Validation logic in `SignalBus`

### Wire Format
```yaml
wiring:
  - src: inputs.commanded_thrust
    dst: icarus.Vehicle.thrust
    gain: 1.0
    offset: 0.0

  - src: inputs.wind_speed
    dst: icarus.Environment.wind.x
```

### Validation Rules
- Source module must exist
- Source signal must exist
- Destination module must exist
- Destination signal must exist
- Destination signal must be writable
- No circular dependencies (future)

### Acceptance Criteria
- [ ] Wire config parses from YAML
- [ ] Validation errors are clear
- [ ] Gain/offset have defaults
- [ ] Invalid configs rejected with helpful messages

---

## Task 3.3: Signal Routing

**Issue ID:** `HRM-015`
**Priority:** Critical
**Blocked By:** HRM-014

### Objective
Implement signal transfer with gain and offset.

### Logic
```python
def route(self) -> None:
    for wire in self._wires:
        value = src.get(wire.src_signal)
        transformed = value * wire.gain + wire.offset
        dst.set(wire.dst_signal, transformed)
```

### Routing Order
- Routes execute after all modules step
- Routes execute in definition order
- Future: topological sort for chained routes

### Acceptance Criteria
- [ ] Values transfer correctly
- [ ] Gain multiplies value
- [ ] Offset adds to result
- [ ] Multiple wires work
- [ ] Order matches config order

---

## Task 3.4: Qualified Names

**Issue ID:** `HRM-016`
**Priority:** High
**Blocked By:** HRM-015

### Objective
Consistent qualified name handling throughout the system.

### Format
- Qualified: `module.signal` (e.g., `icarus.Vehicle.position.z`)
- Local: `signal` within module context (e.g., `Vehicle.position.z`)

### Parsing
```python
def _parse_qualified(self, name: str) -> tuple[str, str]:
    """Parse 'module.signal' into (module, signal)."""
    parts = name.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid qualified name: {name}")
    return parts[0], parts[1]
```

### Acceptance Criteria
- [ ] Consistent parsing across codebase
- [ ] Clear error messages for invalid names
- [ ] Works with nested signal names
- [ ] Documentation updated

---

## Task 3.5: Schema Generation

**Issue ID:** `HRM-017`
**Priority:** High
**Blocked By:** HRM-016

### Objective
Generate combined schema from all registered modules.

### Schema Format
```json
{
  "version": "0.2",
  "modules": {
    "icarus": {
      "signals": {
        "Vehicle.position.x": {"type": "f64", "unit": "m"},
        "Vehicle.position.y": {"type": "f64", "unit": "m"}
      }
    },
    "inputs": {
      "signals": {
        "commanded_thrust": {"type": "f64", "unit": "N"}
      }
    }
  },
  "wiring": [
    {
      "src": "inputs.commanded_thrust",
      "dst": "icarus.Vehicle.thrust"
    }
  ]
}
```

### Acceptance Criteria
- [ ] All modules included
- [ ] All signals listed with metadata
- [ ] Wiring included
- [ ] JSON serializable
- [ ] Sent to clients on connect

---

## Task 3.6: Multi-Module Test

**Issue ID:** `HRM-018`
**Priority:** High
**Blocked By:** HRM-017

### Objective
Integration test with Icarus + Injection modules.

### Test Scenario
1. Configure Icarus module
2. Configure Injection module with `thrust_command`
3. Wire `inputs.thrust_command` → `icarus.Vehicle.thrust`
4. Set injection value
5. Step simulation
6. Verify Icarus received value
7. Verify telemetry shows both modules

### Deliverables
- `tests/integration/test_multimodule.py`
- Multi-module example config

### Acceptance Criteria
- [ ] Both modules register successfully
- [ ] Wire validation passes
- [ ] Signal routing works
- [ ] Combined schema correct
- [ ] End-to-end test passes

---

## Beads Integration

```bash
# Create Phase 3 issues (after Phase 2 complete)
bd create -t "Injection Adapter" -d "Simple value store for test signals" -p critical -l phase3,adapter
bd create -t "Wire Configuration" -d "YAML parsing and validation for wiring" -p critical -l phase3,config
bd create -t "Signal Routing" -d "bus.route() with gain/offset support" -p critical -l phase3,core
bd create -t "Qualified Names" -d "Consistent module.signal parsing" -p high -l phase3,core
bd create -t "Schema Generation" -d "Combined schema from all modules" -p high -l phase3,server
bd create -t "Multi-Module Test" -d "Icarus + injection integration test" -p high -l phase3,tests

# View phase 3 work
bd list --label phase3
```

---

## Phase 3 Completion Checklist

- [ ] All HRM-013 through HRM-018 issues closed
- [ ] `./scripts/ci.sh` passes
- [ ] `InjectionAdapter` works standalone
- [ ] Multi-module config loads successfully
- [ ] Wiring routes signals correctly
- [ ] Combined schema served to clients
- [ ] Integration test passes
- [ ] `bd sync && git push` completed

---

## Example Multi-Module Configuration

```yaml
# examples/multi_module.yaml
version: "0.2"

modules:
  icarus:
    adapter: icarus
    config: ./icarus_config.yaml

  inputs:
    adapter: injection
    signals:
      - thrust_command
      - pitch_command
      - yaw_command

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

server:
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

---

## Architecture After Phase 3

```
┌─────────────────────────────────────────────────┐
│                  Hermes Server                   │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────────┐         ┌──────────────┐      │
│  │   Icarus     │◄────────│  Injection   │      │
│  │   Adapter    │  Wire   │   Adapter    │      │
│  └──────────────┘         └──────────────┘      │
│         │                        │              │
│         └────────┬───────────────┘              │
│                  │                              │
│            ┌─────▼─────┐                        │
│            │ SignalBus │                        │
│            └─────┬─────┘                        │
│                  │                              │
│            ┌─────▼─────┐                        │
│            │ Scheduler │                        │
│            └─────┬─────┘                        │
│                  │                              │
│            ┌─────▼─────┐                        │
│            │ WebSocket │◄───── Daedalus         │
│            │  Server   │                        │
│            └───────────┘                        │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Next Phase Preview

Phase 4 (Polish & Documentation) will:
- Add comprehensive error handling
- Enhance configuration validation
- Complete protocol documentation
- Create example configurations
- Set up CI/CD pipeline

See `phase4_polish.md` for details.
