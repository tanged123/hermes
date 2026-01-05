# Phase 4: Polish & Documentation

**Goal:** Production-ready for Daedalus development
**Status:** Not Started
**Blocked By:** Phase 3 Complete
**Exit Criteria:** Hermes is documented and tested enough for Daedalus to start development

---

## Overview

Phase 4 focuses on production hardening, comprehensive documentation, and developer experience. This phase ensures Hermes is stable, well-documented, and easy to use for the Daedalus visualization frontend.

## Dependencies

- Phase 3 complete (multi-module wiring functional)
- All core features implemented

---

## Task 4.1: Error Handling

**Issue ID:** `HRM-019`
**Priority:** High
**Blocked By:** Phase 3

### Objective
Comprehensive error handling with clear, actionable messages.

### Areas to Address

**Configuration Errors:**
- Invalid YAML syntax
- Missing required fields
- Unknown adapter type
- Invalid signal references
- Circular wire dependencies

**Runtime Errors:**
- Module load failures
- Signal not found
- Icarus binding errors
- WebSocket connection issues

**Client Errors:**
- Invalid command format
- Unknown command action
- Missing required parameters

### Deliverables
- Custom exception hierarchy
- Structured error logging
- Client-facing error messages
- Error recovery where possible

### Exception Hierarchy
```python
class HermesError(Exception):
    """Base exception for Hermes errors."""
    pass

class ConfigError(HermesError):
    """Configuration-related errors."""
    pass

class ModuleError(HermesError):
    """Module adapter errors."""
    pass

class SignalError(HermesError):
    """Signal routing errors."""
    pass

class ProtocolError(HermesError):
    """WebSocket protocol errors."""
    pass
```

### Acceptance Criteria
- [ ] All errors have clear messages
- [ ] Config errors show line numbers where possible
- [ ] Runtime errors logged with context
- [ ] Client receives structured error responses
- [ ] No unhandled exceptions in normal operation

---

## Task 4.2: Configuration Validation

**Issue ID:** `HRM-020`
**Priority:** High
**Blocked By:** HRM-019

### Objective
Comprehensive configuration validation with helpful error messages.

### Validation Rules

**Schema Validation:**
- Version compatibility check
- Required fields present
- Types match expected
- Enum values valid

**Semantic Validation:**
- Module names unique
- Signal references valid
- Wire endpoints exist
- No self-wiring
- Writable signals only as destinations

**Cross-Reference Validation:**
- Adapter configs exist (file paths)
- No orphan wires
- Complete module graphs

### Pydantic Features
```python
from pydantic import BaseModel, field_validator, model_validator

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

    @model_validator(mode="after")
    def validate_not_self_wire(self) -> "WireConfig":
        if self.src == self.dst:
            raise ValueError("Cannot wire signal to itself")
        return self
```

### Acceptance Criteria
- [ ] Pydantic models catch all format errors
- [ ] Custom validators for semantic rules
- [ ] Error messages include context
- [ ] Config validation runs before module loading
- [ ] Invalid configs fail fast with clear message

---

## Task 4.3: Protocol Documentation

**Issue ID:** `HRM-021`
**Priority:** High
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
   - Schema message format
   - Event message format
   - Error message format
   - Ack message format

4. **Client Commands**
   - Command message format
   - Available actions with parameters
   - Response expectations

5. **Binary Telemetry**
   - Header format (with byte offsets)
   - Payload format
   - Signal ordering
   - Decoding example (TypeScript/Python)

6. **Examples**
   - Full connection transcript
   - TypeScript client example
   - Python client example

### Acceptance Criteria
- [ ] All message types documented
- [ ] Binary format has byte-level detail
- [ ] Code examples compile/run
- [ ] Reviewed by Daedalus developer
- [ ] No undocumented features

---

## Task 4.4: Example Configurations

**Issue ID:** `HRM-022`
**Priority:** Medium
**Blocked By:** Phase 3

### Objective
Comprehensive examples for common use cases.

### Examples Directory
```
examples/
├── basic_sim.yaml         # Minimal single-module config
├── multi_module.yaml      # Multiple modules with wiring
├── injection_test.yaml    # Signal injection for testing
├── realtime.yaml          # Real-time paced execution
├── headless.yaml          # No-server batch simulation
└── scripts/
    └── test_attitude.py   # Python test scenario
```

### Each Example Includes
- Descriptive comments
- Required Icarus configs (or stubs)
- Expected behavior description

### Acceptance Criteria
- [ ] All examples load successfully
- [ ] Comments explain each section
- [ ] Covers common use cases
- [ ] README references examples

---

## Task 4.5: CI Setup

**Issue ID:** `HRM-023`
**Priority:** Medium
**Blocked By:** HRM-020

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
      - run: nix develop -c ruff check src tests
      - run: nix develop -c ruff format --check src tests

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v24
      - run: nix develop -c mypy src

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v24
      - run: nix develop -c pytest --cov=hermes
      - uses: codecov/codecov-action@v3
```

### Quality Gates
- Lint (ruff check)
- Format check (ruff format --check)
- Type check (mypy --strict)
- Tests (pytest with coverage)
- Coverage threshold (>80%)

### Acceptance Criteria
- [ ] CI runs on all PRs
- [ ] All checks must pass to merge
- [ ] Coverage reported to Codecov
- [ ] Nix environment cached
- [ ] Badge in README

---

## Beads Integration

```bash
# Create Phase 4 issues (after Phase 3 complete)
bd create -t "Error Handling" -d "Exception hierarchy and structured logging" -p high -l phase4,quality
bd create -t "Configuration Validation" -d "Pydantic validators with helpful errors" -p high -l phase4,config
bd create -t "Protocol Documentation" -d "docs/protocol.md with examples" -p high -l phase4,docs
bd create -t "Example Configurations" -d "examples/ directory with common scenarios" -p medium -l phase4,docs
bd create -t "CI Setup" -d "GitHub Actions for lint, typecheck, test" -p medium -l phase4,devops

# View phase 4 work
bd list --label phase4
```

---

## Phase 4 Completion Checklist

- [ ] All HRM-019 through HRM-023 issues closed
- [ ] `./scripts/ci.sh` passes
- [ ] No unhandled exceptions in normal operation
- [ ] Config errors are clear and actionable
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
- **ScriptAdapter**: Python scripted modules
- **ProcessAdapter**: External process modules
- **Recording**: Signal history recording
- **Playback**: Replay recorded sessions
- **Topological Sort**: Automatic module ordering
- **Multi-rate**: Different modules at different rates
- **Distributed**: Multiple hosts

### Technical Debt
- Performance profiling and optimization
- Memory leak detection
- Stress testing (many clients)
- Security hardening

---

## Final Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Hermes v0.2                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Configuration                                               │
│  ┌──────────┐                                               │
│  │  YAML    │──▶ Pydantic Validation ──▶ HermesConfig       │
│  └──────────┘                                               │
│                                                              │
│  Module Layer                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  Icarus  │  │Injection │  │  Script  │  (future)        │
│  │  Adapter │  │ Adapter  │  │  Adapter │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       │             │             │                         │
│       └─────────────┼─────────────┘                         │
│                     │                                        │
│  Core Layer         ▼                                        │
│  ┌──────────────────────────────────────┐                   │
│  │             SignalBus                 │                   │
│  │  • Module Registry                    │                   │
│  │  • Wire Routing                       │                   │
│  │  • Schema Generation                  │                   │
│  └──────────────────┬───────────────────┘                   │
│                     │                                        │
│  ┌──────────────────▼───────────────────┐                   │
│  │            Scheduler                  │                   │
│  │  • Frame Loop                         │                   │
│  │  • Time Tracking                      │                   │
│  │  • Mode Control                       │                   │
│  └──────────────────┬───────────────────┘                   │
│                     │                                        │
│  Server Layer       ▼                                        │
│  ┌──────────────────────────────────────┐                   │
│  │         WebSocket Server              │                   │
│  │  • Protocol Handling                  │                   │
│  │  • Telemetry Streaming               │                   │
│  │  • Client Management                  │                   │
│  └──────────────────┬───────────────────┘                   │
│                     │                                        │
└─────────────────────┼────────────────────────────────────────┘
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
