# Phase 3.5: Icarus Integration

**Goal:** Integrate Icarus 6DOF physics simulator as a Hermes module
**Status:** Not Started
**Blocked By:** Phase 3 Complete
**Exit Criteria:** Icarus simulator runs within Hermes with signal injection via wiring

---

## Overview

Phase 3.5 integrates [Icarus](https://github.com/tanged123/icarus), a 6DOF aerospace simulation engine, as a first-class module type in Hermes. This enables real physics simulation scenarios with:

- Full 6DOF rigid body dynamics
- Signal injection for control inputs
- Telemetry streaming of physics outputs
- WebSocket visualization via Daedalus

## Integration Strategy

### Why pybind11 (not C FFI)

Icarus provides two external interfaces:

1. **C API** (`icarus.h`) - Universal FFI for any language
2. **Python API** (pybind11) - Pythonic interface with numpy integration

We use the **pybind11 Python API** because:
- Native Python objects (`icarus.Simulator`)
- Dict-like signal access (`sim["Vehicle.position.z"]`)
- Numpy integration for state vectors
- Schema introspection via `sim.schema_json`
- No ctypes/cffi complexity
- Hermes is already Python

### Icarus Python API Quick Reference

```python
import icarus

# Create simulator from YAML config
sim = icarus.Simulator("config/rocket_6dof.yaml")

# Lifecycle
sim.stage()                      # Validate, apply ICs
sim.step()                       # Execute one dt
sim.step(0.005)                  # Explicit dt override
sim.reset()                      # Reset to ICs

# Signal access (dict-like)
alt = sim["Vehicle.position.z"]  # Read signal
sim["Vehicle.thrust"] = 1000.0   # Write signal

# Properties
sim.time                         # Current MET (seconds)
sim.dt                           # Configured timestep
sim.end_time                     # Configured end time
sim.lifecycle                    # Current lifecycle state

# Introspection
sim.signals                      # List of all signal names
sim.signal_count                 # Total signals
sim.schema_json                  # Data dictionary as dict
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              HERMES                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   Shared Memory Backplane                          │ │
│  │                                                                     │ │
│  │  ┌───────────────────────────┐   ┌───────────────────┐            │ │
│  │  │     Icarus Signals        │   │ Injection Signals │            │ │
│  │  │  Rocket.EOM.position.*    │◄──│ thrust_cmd, etc   │            │ │
│  │  │  Rocket.EOM.velocity.*    │   └───────────────────┘            │ │
│  │  │  Rocket.Engine.thrust     │                                     │ │
│  │  │  Rocket.Mass.total        │                                     │ │
│  │  └───────────────────────────┘                                     │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                    │                                                     │
│                    ▼                                                     │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    IcarusModule (Python)                          │  │
│  │                                                                    │  │
│  │   ┌────────────────────────────────────────────────────────────┐  │  │
│  │   │              icarus.Simulator (pybind11)                   │  │  │
│  │   │                                                             │  │  │
│  │   │  • 6DOF rigid body dynamics                                │  │  │
│  │   │  • Component-based architecture                            │  │  │
│  │   │  • Signal backplane (internal)                             │  │  │
│  │   │  • Configurable from YAML                                  │  │  │
│  │   └────────────────────────────────────────────────────────────┘  │  │
│  │                                                                    │  │
│  │   Signal Bridge:                                                   │  │
│  │   • stage(): Discover signals from sim.schema_json                │  │
│  │   • step():  Read inputs from Hermes shm → Icarus                 │  │
│  │              Call sim.step()                                       │  │
│  │              Write Icarus outputs → Hermes shm                    │  │
│  │   • reset(): Call sim.reset(), re-sync signals                    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Task 3.5.1: Icarus Module Type

**Priority:** P0 (Critical)
**Blocked By:** Phase 3

### Objective
Add `icarus` as a new module type in Hermes configuration.

### Configuration Schema
```yaml
modules:
  rocket:
    type: icarus
    config: ./config/rocket_6dof.yaml   # Icarus YAML config
    prefix: Rocket                       # Signal namespace prefix
    options:
      discover_signals: true             # Auto-discover from schema
      sync_inputs: true                  # Sync writable signals each step
      sync_outputs: true                 # Sync output signals each step
```

### Config Changes
```python
# src/hermes/core/config.py

class ModuleType(str, Enum):
    PROCESS = "process"
    INPROC = "inproc"
    SCRIPT = "script"
    ICARUS = "icarus"  # NEW


class ModuleConfig(BaseModel):
    type: ModuleType
    executable: Path | None = None
    script: Path | None = None
    config: Path | None = None
    prefix: str | None = None  # NEW: signal namespace prefix
    signals: list[SignalConfig] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_type_fields(self) -> ModuleConfig:
        if self.type == ModuleType.PROCESS and self.executable is None:
            raise ValueError("'executable' required for process modules")
        if self.type == ModuleType.SCRIPT and self.script is None:
            raise ValueError("'script' required for script modules")
        if self.type == ModuleType.ICARUS and self.config is None:
            raise ValueError("'config' required for icarus modules")
        return self
```

### Acceptance Criteria
- [ ] `icarus` module type validates in config
- [ ] `config` path required for icarus modules
- [ ] `prefix` optional (defaults to module name)
- [ ] Options parsed correctly

---

## Task 3.5.2: Icarus Module Implementation

**Priority:** P0 (Critical)
**Blocked By:** Task 3.5.1

### Objective
Implement the IcarusModule class that wraps icarus.Simulator.

### Deliverables
- `src/hermes/modules/icarus_module.py`

### Implementation
```python
"""Icarus physics module wrapper for Hermes."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager

log = structlog.get_logger()


class IcarusModule:
    """Wraps Icarus simulator as a Hermes module.

    Bridges signals between Hermes shared memory and Icarus internal
    signal backplane. On each step:
    1. Copy writable signals from Hermes → Icarus
    2. Execute Icarus physics step
    3. Copy output signals from Icarus → Hermes
    """

    def __init__(
        self,
        module_name: str,
        shm: SharedMemoryManager,
        config_path: Path,
        prefix: str | None = None,
        discover_signals: bool = True,
        sync_inputs: bool = True,
        sync_outputs: bool = True,
    ) -> None:
        """Initialize Icarus module.

        Args:
            module_name: Hermes module name
            shm: Shared memory manager
            config_path: Path to Icarus YAML config
            prefix: Signal namespace prefix (defaults to module_name)
            discover_signals: Auto-discover signals from Icarus schema
            sync_inputs: Sync writable signals to Icarus each step
            sync_outputs: Sync output signals from Icarus each step
        """
        self._name = module_name
        self._shm = shm
        self._config_path = config_path
        self._prefix = prefix or module_name
        self._discover_signals = discover_signals
        self._sync_inputs = sync_inputs
        self._sync_outputs = sync_outputs

        # Icarus simulator instance (created in stage)
        self._sim: icarus.Simulator | None = None

        # Signal mappings discovered during stage
        self._input_signals: list[str] = []   # Writable signals to sync in
        self._output_signals: list[str] = []  # Output signals to sync out

    def stage(self) -> None:
        """Stage the Icarus simulator.

        Creates simulator, stages it, discovers signals, and registers
        them with Hermes shared memory.
        """
        import icarus

        log.info(
            "Staging Icarus module",
            name=self._name,
            config=str(self._config_path),
        )

        # Create and stage Icarus simulator
        self._sim = icarus.Simulator(str(self._config_path))
        self._sim.stage()

        # Discover signals from Icarus schema
        if self._discover_signals:
            self._discover_and_register_signals()

        # Initial sync: write Icarus state to Hermes shm
        self._sync_outputs_to_hermes()

        log.info(
            "Icarus module staged",
            name=self._name,
            signals=len(self._input_signals) + len(self._output_signals),
        )

    def _discover_and_register_signals(self) -> None:
        """Discover signals from Icarus and register with Hermes shm."""
        assert self._sim is not None

        schema = self._sim.schema_json

        # Parse Icarus schema to find all signals
        # Schema format: {"components": {...}, "signals": [...], ...}
        for signal_name in self._sim.signals:
            # Map Icarus signal to Hermes qualified name
            hermes_name = f"{self._prefix}.{signal_name}"

            # Determine if signal is writable (inputs) or read-only (outputs)
            # For now, assume all signals are outputs (read from Icarus)
            # Inputs are explicitly wired via Hermes wiring config
            self._output_signals.append(signal_name)

            # Register signal with Hermes shared memory
            # Initial value comes from Icarus
            value = self._sim[signal_name]
            self._shm.set_signal(hermes_name, float(value))

        log.debug(
            "Discovered Icarus signals",
            outputs=len(self._output_signals),
        )

    def step(self, dt: float) -> None:
        """Execute one physics step.

        1. Sync inputs from Hermes to Icarus (if enabled)
        2. Step Icarus simulator
        3. Sync outputs from Icarus to Hermes (if enabled)
        """
        assert self._sim is not None

        # Sync inputs: Hermes shm → Icarus
        if self._sync_inputs:
            self._sync_inputs_to_icarus()

        # Execute Icarus physics
        self._sim.step(dt)

        # Sync outputs: Icarus → Hermes shm
        if self._sync_outputs:
            self._sync_outputs_to_hermes()

    def _sync_inputs_to_icarus(self) -> None:
        """Copy writable signal values from Hermes to Icarus."""
        assert self._sim is not None

        for signal_name in self._input_signals:
            hermes_name = f"{self._prefix}.{signal_name}"
            value = self._shm.get_signal(hermes_name)
            self._sim[signal_name] = value

    def _sync_outputs_to_hermes(self) -> None:
        """Copy output signal values from Icarus to Hermes."""
        assert self._sim is not None

        for signal_name in self._output_signals:
            hermes_name = f"{self._prefix}.{signal_name}"
            value = self._sim[signal_name]
            self._shm.set_signal(hermes_name, float(value))

    def reset(self) -> None:
        """Reset Icarus to initial conditions."""
        assert self._sim is not None

        self._sim.reset()
        self._sync_outputs_to_hermes()

    @property
    def time(self) -> float:
        """Current Icarus simulation time."""
        if self._sim is None:
            return 0.0
        return self._sim.time

    @property
    def signal_count(self) -> int:
        """Number of registered signals."""
        return len(self._input_signals) + len(self._output_signals)
```

### Acceptance Criteria
- [ ] Creates icarus.Simulator from config path
- [ ] Stages simulator correctly
- [ ] Discovers signals from schema_json
- [ ] Registers signals with Hermes shared memory
- [ ] Syncs inputs from Hermes to Icarus
- [ ] Syncs outputs from Icarus to Hermes
- [ ] Reset works correctly

---

## Task 3.5.3: Signal Discovery from Icarus Schema

**Priority:** P0 (Critical)
**Blocked By:** Task 3.5.2

### Objective
Parse Icarus schema and register signals with correct metadata.

### Icarus Schema Format
```python
# sim.schema_json returns:
{
    "simulation": {"name": "Rocket 6DOF Test", "dt": 0.01, "t_end": 100.0},
    "components": [
        {
            "name": "EOM",
            "entity": "Rocket",
            "type": "RigidBody6DOF",
            "outputs": [
                {"name": "position.x", "type": "double", "unit": "m"},
                {"name": "position.y", "type": "double", "unit": "m"},
                {"name": "position.z", "type": "double", "unit": "m"},
                {"name": "velocity.x", "type": "double", "unit": "m/s"},
                ...
            ],
            "inputs": [
                {"name": "force.x", "type": "double", "unit": "N"},
                ...
            ]
        }
    ],
    "summary": {"total_signals": 42, "total_states": 13}
}
```

### Hermes Signal Mapping
```
Icarus Signal:     Rocket.EOM.position.x
Hermes Signal:     rocket.Rocket.EOM.position.x  (with module prefix)
                   ^^^^^^ ^^^^^^^^^^^^^^^^^^^^^
                   prefix icarus_signal_name
```

### Enhanced Signal Discovery
```python
def _discover_and_register_signals(self) -> None:
    """Discover signals from Icarus schema with full metadata."""
    assert self._sim is not None

    schema = self._sim.schema_json

    for component in schema.get("components", []):
        entity = component.get("entity", "")
        comp_name = component.get("name", "")
        comp_prefix = f"{entity}.{comp_name}" if entity else comp_name

        # Register outputs (read from Icarus → Hermes)
        for sig in component.get("outputs", []):
            icarus_name = f"{comp_prefix}.{sig['name']}"
            hermes_name = f"{self._prefix}.{icarus_name}"

            self._output_signals.append(icarus_name)

            # Register with Hermes shm (value from Icarus)
            value = self._sim[icarus_name]
            self._shm.set_signal(hermes_name, float(value))

        # Register inputs (writable via Hermes → Icarus)
        for sig in component.get("inputs", []):
            icarus_name = f"{comp_prefix}.{sig['name']}"
            hermes_name = f"{self._prefix}.{icarus_name}"

            self._input_signals.append(icarus_name)

            # Register as writable signal
            self._shm.set_signal(hermes_name, 0.0)
```

### Acceptance Criteria
- [ ] Parses Icarus schema correctly
- [ ] Distinguishes inputs (writable) from outputs (read-only)
- [ ] Maps signal names with correct prefix
- [ ] Preserves unit metadata where available
- [ ] Handles nested entity.component.signal names

---

## Task 3.5.4: ProcessManager Icarus Support

**Priority:** P0 (Critical)
**Blocked By:** Task 3.5.3

### Objective
Update ProcessManager to instantiate IcarusModule for `icarus` type.

### Implementation
```python
# src/hermes/core/process.py

def _create_module(self, name: str, config: ModuleConfig) -> Module:
    """Create module instance based on type."""
    if config.type == ModuleType.ICARUS:
        from hermes.modules.icarus_module import IcarusModule

        return IcarusModule(
            module_name=name,
            shm=self._shm,
            config_path=config.config,
            prefix=config.prefix or name,
            discover_signals=config.options.get("discover_signals", True),
            sync_inputs=config.options.get("sync_inputs", True),
            sync_outputs=config.options.get("sync_outputs", True),
        )

    # ... existing module types
```

### Acceptance Criteria
- [ ] ProcessManager creates IcarusModule for icarus type
- [ ] Config options passed correctly
- [ ] Lifecycle methods called correctly

---

## Task 3.5.5: Icarus Integration Test

**Priority:** P1 (High)
**Blocked By:** Task 3.5.4

### Objective
End-to-end test with real Icarus physics.

### Test Configuration
```yaml
# tests/fixtures/icarus_test.yaml
version: "0.2"

modules:
  rocket:
    type: icarus
    config: ${ICARUS_CONFIG}/rocket_6dof.yaml
    prefix: rocket
    options:
      discover_signals: true

  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: thrust_cmd
        type: f64
        writable: true

wiring:
  - src: inputs.thrust_cmd
    dst: rocket.Rocket.Engine.throttle
    gain: 1.0

execution:
  mode: afap
  rate_hz: 100.0
  end_time: 1.0  # Short test

server:
  enabled: false
```

### Test Implementation
```python
import pytest

# Skip if icarus not available
icarus = pytest.importorskip("icarus")


class TestIcarusIntegration:
    """Integration tests for Icarus module."""

    def test_icarus_module_stages(self, icarus_config):
        """Icarus module should stage successfully."""
        with ProcessManager.from_yaml(icarus_config) as pm:
            sched = Scheduler(pm, pm.config.execution)
            sched.stage()

            # Verify signals discovered
            signals = pm.shm.signal_names()
            assert any("position" in s for s in signals)
            assert any("velocity" in s for s in signals)

    def test_icarus_physics_step(self, icarus_config):
        """Icarus physics should advance state."""
        with ProcessManager.from_yaml(icarus_config) as pm:
            sched = Scheduler(pm, pm.config.execution)
            sched.stage()

            # Get initial altitude
            initial_z = pm.shm.get_signal("rocket.Rocket.EOM.position.z")

            # Step simulation
            sched.step()

            # Altitude should change (free fall or thrust)
            new_z = pm.shm.get_signal("rocket.Rocket.EOM.position.z")
            assert new_z != initial_z

    def test_wiring_to_icarus(self, icarus_config_with_injection):
        """Wire routing should inject values into Icarus."""
        with ProcessManager.from_yaml(icarus_config_with_injection) as pm:
            sched = Scheduler(pm, pm.config.execution)
            sched.stage()

            # Set throttle via injection
            pm.shm.set_signal("inputs.thrust_cmd", 0.5)

            # Step (wire routes injection → icarus)
            sched.step()

            # Verify throttle was received by Icarus
            # (Would need to check internal Icarus state or observe thrust effect)
```

### Acceptance Criteria
- [ ] Icarus module stages without error
- [ ] Signals discovered and registered
- [ ] Physics advances state correctly
- [ ] Wire routing works to Icarus inputs
- [ ] Reset restores initial state

---

## Task 3.5.6: Example Configuration

**Priority:** P1 (High)
**Blocked By:** Task 3.5.5

### Objective
Create complete example configuration for Icarus simulation.

### Deliverables
- `examples/icarus_rocket.yaml` - Hermes config
- Documentation for running with Icarus

### Example Configuration
```yaml
# examples/icarus_rocket.yaml
#
# Hermes configuration for Icarus 6DOF rocket simulation
#
# Prerequisites:
#   1. Build Icarus with Python bindings:
#      cd /path/to/icarus && ./scripts/build.sh --python
#   2. Add to PYTHONPATH:
#      export PYTHONPATH=/path/to/icarus/build/python:$PYTHONPATH
#   3. Run simulation:
#      hermes run examples/icarus_rocket.yaml

version: "0.2"

modules:
  # Icarus 6DOF physics simulator
  rocket:
    type: icarus
    config: ../references/icarus/config/rocket_6dof.yaml
    prefix: rocket
    options:
      discover_signals: true
      sync_inputs: true
      sync_outputs: true

  # Injection module for test inputs
  inputs:
    type: script
    script: hermes.modules.injection
    signals:
      - name: throttle
        type: f64
        unit: "%"
        writable: true
      - name: pitch_cmd
        type: f64
        unit: deg
        writable: true
      - name: yaw_cmd
        type: f64
        unit: deg
        writable: true

wiring:
  # Route throttle command to engine
  - src: inputs.throttle
    dst: rocket.Rocket.Engine.throttle

  # Route attitude commands (deg → rad)
  - src: inputs.pitch_cmd
    dst: rocket.Rocket.GNC.pitch_cmd
    gain: 0.0174533

  - src: inputs.yaw_cmd
    dst: rocket.Rocket.GNC.yaw_cmd
    gain: 0.0174533

execution:
  mode: afap
  rate_hz: 100.0
  end_time: 100.0
  schedule:
    - inputs   # Injection first (writes commands)
    - rocket   # Physics second (reads commands, computes dynamics)

server:
  enabled: true
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

### Acceptance Criteria
- [ ] Example runs successfully with Icarus
- [ ] Documentation explains prerequisites
- [ ] Wire routing works for control inputs
- [ ] Telemetry streams physics outputs

---

## Dependencies & Prerequisites

### Icarus Python Bindings

Hermes requires Icarus Python bindings installed:

```bash
# Build Icarus with Python bindings
cd /path/to/icarus
./scripts/build.sh --python

# Add to PYTHONPATH
export PYTHONPATH=/path/to/icarus/build/python:$PYTHONPATH

# Verify
python -c "import icarus; print(icarus.__version__)"
```

### Nix Integration (Future)

For seamless development:

```nix
# flake.nix addition
{
  inputs.icarus.url = "github:tanged123/icarus";

  outputs = { self, nixpkgs, icarus, ... }:
    let
      icarusPython = icarus.packages.x86_64-linux.python;
    in {
      devShells.default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [
            icarusPython
            ps.numpy
            ps.pyyaml
            # ... other hermes deps
          ]))
        ];
      };
    };
}
```

---

## Phase 3.5 Completion Checklist

- [ ] All Phase 3.5 tasks complete
- [ ] `./scripts/ci.sh` passes
- [ ] Icarus module type works
- [ ] Signal discovery from schema works
- [ ] Wire routing to Icarus inputs works
- [ ] Telemetry streams Icarus outputs
- [ ] Example configuration works
- [ ] Documentation updated

---

## Architecture After Phase 3.5

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            HERMES v0.4                                   │
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
│  ┌──────────┐  ┌──────────┴─┐  ┌────────────────────────┐             │
│  │ Injection│  │  Icarus    │  │  Other Modules         │             │
│  │  Module  │  │  Module    │  │  (script, process...)  │             │
│  │          │  │            │  │                        │             │
│  │  Simple  │  │  pybind11  │  │                        │             │
│  │  signals │  │  wrapper   │  │                        │             │
│  └────┬─────┘  └─────┬──────┘  └────────────────────────┘             │
│       │              │                                                   │
│       │     ┌────────┴────────┐                                         │
│       │     │ icarus.Simulator│  ◄── 6DOF Physics Engine               │
│       │     │ (C++ via pybind)│                                         │
│       │     └─────────────────┘                                         │
│       │                                                                  │
│       └──────────────┬───────────────────────────────────────           │
│                      │                                                   │
│  Core Layer          ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Wire Router                                  │  │
│  │  inputs.throttle → rocket.Rocket.Engine.throttle                 │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                            │
│  ┌──────────────────────────▼───────────────────────────────────────┐  │
│  │                        Scheduler                                  │  │
│  │  1. Step injection module                                        │  │
│  │  2. Step icarus module (physics)                                 │  │
│  │  3. Route wires                                                  │  │
│  │  4. Update frame/time                                            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     WebSocket Server                              │  │
│  │  Telemetry: rocket.Rocket.EOM.position.* @ 60Hz                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                      ┌───────────────┐
                      │   Daedalus    │
                      │ Visualization │
                      │               │
                      │ 3D rocket     │
                      │ telemetry     │
                      │ graphs        │
                      └───────────────┘
```

---

## Next Phase: Phase 4 (Polish & Documentation)

Phase 4 will focus on:
- Comprehensive error handling
- Configuration validation enhancements
- Protocol documentation
- Performance optimization
- CI/CD pipeline setup

See `phase4_polish.md` for details.
