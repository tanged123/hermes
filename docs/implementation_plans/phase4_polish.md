# Phase 4: Polish & Documentation

**Goal:** Production-ready for Daedalus development
**Status:** Not Started
**Blocked By:** Phase 3 Complete
**Exit Criteria:** Hermes is documented and tested enough for Daedalus to start development

---

## Overview

Phase 4 focuses on production hardening, comprehensive documentation, and developer experience. This phase ensures Hermes is stable, well-documented, and easy to use for the Daedalus visualization frontend.

With the multi-process IPC architecture, special attention is needed for:
- IPC error handling (shared memory, semaphores, pipes)
- Process lifecycle errors
- Cross-process debugging
- Resource cleanup on failure

## Dependencies

- Phase 3 complete (multi-module wiring functional)
- All core features implemented

---

## Task 4.1: Error Handling

**Issue ID:** (create after Phase 3)
**Priority:** High (P1)
**Blocked By:** Phase 3

### Objective
Comprehensive error handling with clear, actionable messages for all failure modes.

### Error Categories

**IPC Errors:**
- Shared memory create/attach failures
- Semaphore timeout
- Named pipe broken
- Resource cleanup failures

**Process Errors:**
- Module executable not found
- Module crash during execution
- Module timeout on step
- Orphan process cleanup

**Configuration Errors:**
- Invalid YAML syntax
- Missing required fields
- Unknown module type
- Invalid signal references
- Circular wire dependencies

**Runtime Errors:**
- Signal not found
- Write to read-only signal
- Wire validation failure
- WebSocket connection issues

### Exception Hierarchy
```python
class HermesError(Exception):
    """Base exception for Hermes errors."""
    pass

class ConfigError(HermesError):
    """Configuration-related errors."""
    pass

class IPCError(HermesError):
    """IPC communication errors."""
    pass

class SharedMemoryError(IPCError):
    """Shared memory specific errors."""
    pass

class SemaphoreError(IPCError):
    """Semaphore specific errors."""
    pass

class ProcessError(HermesError):
    """Module process errors."""
    pass

class ModuleError(ProcessError):
    """Module-specific errors."""
    def __init__(self, module: str, message: str) -> None:
        self.module = module
        super().__init__(f"[{module}] {message}")

class SignalError(HermesError):
    """Signal routing errors."""
    pass

class ProtocolError(HermesError):
    """WebSocket protocol errors."""
    pass
```

### Error Recovery Strategies
```python
class ProcessManager:
    def step_all(self) -> None:
        """Step all modules with error recovery."""
        for module in self._modules.values():
            try:
                module.step()
            except ModuleError as e:
                log.error("Module step failed", module=e.module, error=str(e))
                if self._config.on_module_error == "stop":
                    raise
                elif self._config.on_module_error == "skip":
                    continue
                elif self._config.on_module_error == "restart":
                    self._restart_module(module)
```

### Acceptance Criteria
- [ ] All error types have clear messages
- [ ] IPC errors include resource names
- [ ] Process errors include PID and exit code
- [ ] Config errors show YAML location where possible
- [ ] Runtime errors logged with full context
- [ ] No unhandled exceptions in normal operation
- [ ] Client receives structured error responses

---

## Task 4.2: Configuration Validation

**Issue ID:** (create after Phase 3)
**Priority:** High (P1)
**Blocked By:** Task 4.1

### Objective
Comprehensive configuration validation with helpful error messages.

### Validation Stages

**1. Schema Validation (Pydantic):**
- Version compatibility check
- Required fields present
- Types match expected
- Enum values valid

**2. Semantic Validation:**
- Module names unique
- Signal references valid
- Wire endpoints exist
- No self-wiring
- Writable signals only as destinations
- Schedule contains valid module names

**3. Cross-Reference Validation:**
- Executable paths exist
- Script modules importable
- Config file paths exist
- No orphan wires

**4. Runtime Validation:**
- Shared memory can be created
- Modules respond to ping
- Signal counts match expected

### Enhanced Pydantic Models
```python
from pydantic import BaseModel, field_validator, model_validator
from pathlib import Path

class ModuleConfig(BaseModel):
    type: ModuleType
    executable: Path | None = None
    script: str | None = None
    config: Path | None = None
    signals: list[SignalConfig] = []

    @model_validator(mode="after")
    def validate_module_type(self) -> "ModuleConfig":
        if self.type == ModuleType.PROCESS and not self.executable:
            raise ValueError("Process modules require 'executable'")
        if self.type == ModuleType.SCRIPT and not self.script:
            raise ValueError("Script modules require 'script'")
        return self

    @field_validator("executable", mode="after")
    @classmethod
    def validate_executable(cls, v: Path | None) -> Path | None:
        if v and not v.exists():
            raise ValueError(f"Executable not found: {v}")
        return v

class HermesConfig(BaseModel):
    version: str
    modules: dict[str, ModuleConfig]
    wiring: list[WireConfig] = []
    execution: ExecutionConfig = ExecutionConfig()
    server: ServerConfig = ServerConfig()

    @model_validator(mode="after")
    def validate_wiring(self) -> "HermesConfig":
        module_names = set(self.modules.keys())
        for wire in self.wiring:
            src_module = wire.src.split(".")[0]
            dst_module = wire.dst.split(".")[0]
            if src_module not in module_names:
                raise ValueError(f"Wire source module not found: {src_module}")
            if dst_module not in module_names:
                raise ValueError(f"Wire destination module not found: {dst_module}")
        return self

    @model_validator(mode="after")
    def validate_schedule(self) -> "HermesConfig":
        module_names = set(self.modules.keys())
        for name in self.execution.schedule:
            if name not in module_names:
                raise ValueError(f"Schedule references unknown module: {name}")
        return self
```

### Acceptance Criteria
- [ ] Pydantic models catch all format errors
- [ ] Custom validators for semantic rules
- [ ] Error messages include context (field name, value)
- [ ] Config validation runs before module loading
- [ ] Invalid configs fail fast with clear message
- [ ] Validation command: `hermes validate config.yaml`

---

## Task 4.3: Protocol Documentation

**Issue ID:** (create after Phase 3)
**Priority:** High (P1)
**Blocked By:** Phase 3

### Objective
Complete protocol documentation for Daedalus developers.

### Deliverables
- `docs/protocol.md` - Complete protocol specification

### Document Sections

1. **Overview**
   - Connection lifecycle
   - Message flow diagram
   - Transport layer (WebSocket)

2. **Message Format**
   - JSON text messages
   - Binary telemetry frames
   - Message type enum

3. **Server Messages**
   - Schema message format and example
   - Event message format and types
   - Error message format
   - Ack message format

4. **Client Commands**
   - Command message format
   - Available actions with parameters:
     - `pause` - Pause simulation
     - `resume` - Resume simulation
     - `reset` - Reset to initial conditions
     - `step` - Execute N frames
     - `set` - Set signal value
     - `subscribe` - Configure telemetry

5. **Binary Telemetry**
   - Header format with byte offsets
   ```
   Offset  Size  Type   Field
   0       4     u32    magic (0x48455254)
   4       8     u64    frame
   12      8     f64    time
   20      4     u32    count
   24      N*8   f64[]  values
   ```
   - Payload format
   - Signal ordering (matches subscription order)
   - Decoding examples (TypeScript, Python)

6. **Examples**
   - Full connection transcript
   - TypeScript client example
   - Python client example

### Acceptance Criteria
- [ ] All message types documented with examples
- [ ] Binary format has byte-level detail
- [ ] Code examples tested and working
- [ ] Reviewed by Daedalus developer
- [ ] No undocumented features

---

## Task 4.4: Example Configurations

**Issue ID:** (create after Phase 3)
**Priority:** Medium (P2)
**Blocked By:** Phase 3

### Objective
Comprehensive examples for common use cases.

### Examples Directory
```
examples/
├── basic_sim.yaml           # Minimal single-module config
├── multi_module.yaml        # Multiple modules with wiring
├── injection_test.yaml      # Signal injection for testing
├── realtime.yaml            # Real-time paced execution
├── headless.yaml            # No-server batch simulation
├── mock_module/             # Example mock module
│   ├── __init__.py
│   └── physics.py
└── scripts/
    ├── inject_thrust.py     # Python injection example
    ├── monitor_telemetry.py # Telemetry monitoring script
    └── test_scenario.py     # Full test scenario
```

### Example: Basic Simulation
```yaml
# examples/basic_sim.yaml
# Minimal single-module simulation

version: "0.2"

modules:
  physics:
    type: script
    script: examples.mock_module.physics
    signals:
      - name: position
        type: f64
        unit: m
      - name: velocity
        type: f64
        unit: m/s

execution:
  mode: afap
  rate_hz: 100.0
  end_time: 10.0

server:
  enabled: false
```

### Example: Injection Test
```yaml
# examples/injection_test.yaml
# Demonstrates signal injection for testing

version: "0.2"

modules:
  sim:
    type: script
    script: examples.mock_module.physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64

  inject:
    type: script
    script: hermes.modules.injection
    signals:
      - name: command
        type: f64
        writable: true

wiring:
  - src: inject.command
    dst: sim.input

execution:
  mode: single_frame
  rate_hz: 100.0

server:
  enabled: true
  port: 8765
```

### Acceptance Criteria
- [ ] All examples load successfully
- [ ] Each example has descriptive comments
- [ ] Covers common use cases
- [ ] README references examples
- [ ] Scripts are executable and documented

---

## Task 4.5: CI Setup

**Issue ID:** (create after Phase 3)
**Priority:** Medium (P2)
**Blocked By:** Task 4.2

### Objective
Continuous integration for quality gates.

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v24
      - uses: cachix/cachix-action@v12
        with:
          name: hermes
      - run: nix develop -c ruff check src tests
      - run: nix develop -c ruff format --check src tests

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v24
      - uses: cachix/cachix-action@v12
        with:
          name: hermes
      - run: nix develop -c mypy src

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v24
      - uses: cachix/cachix-action@v12
        with:
          name: hermes
      - run: nix develop -c pytest --cov=hermes --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  integration:
    runs-on: ubuntu-latest
    needs: [lint, typecheck, test]
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v24
      - uses: cachix/cachix-action@v12
        with:
          name: hermes
      - run: nix develop -c pytest tests/integration -v
```

### Quality Gates
| Gate | Tool | Threshold |
|------|------|-----------|
| Lint | ruff check | No errors |
| Format | ruff format --check | No changes |
| Type check | mypy --strict | No errors |
| Unit tests | pytest | 100% pass |
| Coverage | pytest-cov | >80% |
| Integration | pytest integration/ | 100% pass |

### Acceptance Criteria
- [ ] CI runs on all PRs
- [ ] All checks must pass to merge
- [ ] Coverage reported to Codecov
- [ ] Nix environment cached
- [ ] Badge in README

---

## Beads Integration

Issues will be created after Phase 3 is complete:

```bash
# Create Phase 4 issues
bd create --title "Error Handling" -d "Exception hierarchy and IPC error handling" -p 1 -l phase4,quality
bd create --title "Configuration Validation" -d "Pydantic validators with helpful errors" -p 1 -l phase4,config
bd create --title "Protocol Documentation" -d "docs/protocol.md with examples" -p 1 -l phase4,docs
bd create --title "Example Configurations" -d "examples/ directory with common scenarios" -p 2 -l phase4,docs
bd create --title "CI Setup" -d "GitHub Actions for lint, typecheck, test" -p 2 -l phase4,devops

# View phase 4 work
bd list --label phase4
```

---

## Phase 4 Completion Checklist

- [ ] All Phase 4 issues closed
- [ ] `./scripts/ci.sh` passes
- [ ] No unhandled exceptions in normal operation
- [ ] Config errors are clear and actionable
- [ ] IPC errors include resource context
- [ ] `docs/protocol.md` complete
- [ ] All examples work
- [ ] CI pipeline green
- [ ] README updated with badges
- [ ] `bd sync && git push` completed

---

## Post-Phase 4: What's Next?

After Phase 4, Hermes is ready for:

### Daedalus Integration
- Daedalus can connect and receive telemetry
- Full protocol documented
- Examples available

### Future Enhancements (Phase 5+)
- **Recording**: Signal history to file
- **Playback**: Replay recorded sessions
- **Topological Sort**: Automatic module ordering
- **Multi-rate**: Different modules at different rates
- **Distributed**: Multiple hosts via network IPC
- **GPU Signals**: Large array signals in GPU memory
- **Time Sync**: NTP-based time synchronization

### Technical Debt
- Performance profiling and optimization
- Memory leak detection (shared memory)
- Stress testing (many modules, clients)
- Security hardening (IPC permissions)

---

## Final Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HERMES v0.2                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Configuration                                                           │
│  ┌──────────┐                                                           │
│  │  YAML    │──▶ Pydantic Validation ──▶ HermesConfig                   │
│  └──────────┘                                                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   Shared Memory Backplane                          │ │
│  │  ┌─────────┐ ┌─────────────────┐ ┌─────────────────┐              │ │
│  │  │ Header  │ │ Signal Registry │ │  Data Region    │              │ │
│  │  │frame/time│ │ (names, types)  │ │ (f64 values)   │              │ │
│  │  └─────────┘ └─────────────────┘ └─────────────────┘              │ │
│  └─────────────────────────┬──────────────────────────────────────────┘ │
│                            │                                             │
│  Module Layer              │                                             │
│  ┌──────────┐  ┌──────────┴─┐  ┌──────────┐                            │
│  │  Icarus  │  │ Injection  │  │  Custom  │                            │
│  │  (C++)   │  │ (Python)   │  │ (Any)    │                            │
│  └────┬─────┘  └─────┬──────┘  └────┬─────┘                            │
│       │              │              │                                    │
│       └──────────────┼──────────────┘                                    │
│                      │                                                    │
│  Core Layer          ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      Process Manager                              │   │
│  │  • Module lifecycle    • Barrier sync    • Wire routing          │   │
│  └──────────────────────────┬───────────────────────────────────────┘   │
│                             │                                            │
│  ┌──────────────────────────▼───────────────────────────────────────┐   │
│  │                        Scheduler                                  │   │
│  │  • Frame loop    • Time tracking    • Mode control               │   │
│  └──────────────────────────┬───────────────────────────────────────┘   │
│                             │                                            │
│  Server Layer              ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     WebSocket Server                              │   │
│  │  • Protocol    • Telemetry streaming    • Client management      │   │
│  └──────────────────────────┬───────────────────────────────────────┘   │
│                             │                                            │
│  Scripting Layer           ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     SimulationAPI                                 │   │
│  │  • get/set signals    • wait_frame    • inject/sample           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
                              ▼
                      ┌───────────────┐
                      │   Daedalus    │
                      │ Visualization │
                      └───────────────┘
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Test Coverage | >80% |
| Type Coverage | 100% (strict mode) |
| Documentation | All public APIs |
| CI Pass Rate | 100% on main |
| Load Test | 10 clients @ 60Hz |
| Latency | <1ms telemetry encode |
| Memory | No leaks after 24h run |
| IPC Cleanup | Zero orphan resources |
