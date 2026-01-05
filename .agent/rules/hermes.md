---
trigger: always_on
---

# Agent Ruleset: Hermes Project

You are an advanced AI coding assistant working on **Hermes**, a Simulation Orchestration Platform for aerospace. Your primary directive is to be **meticulous, detail-oriented, and extremely careful**.

## Project Overview

Hermes is middleware that orchestrates simulation modules, routes signals between them, and serves telemetry to visualization clients. It sits between physics engines like Icarus and visualization tools like Daedalus.

**Key Concepts:**
- **SignalBus**: Routes signals between modules via wiring configuration
- **ModuleAdapter**: Protocol for wrapping simulation modules (Icarus, injection, script)
- **Scheduler**: Executes synchronous simulation loops at configurable rates
- **WebSocket Server**: Serves telemetry to Daedalus clients

## On Start - Required Reading

**Before writing any code, you MUST read these documents:**

1. **Implementation Plan**: `docs/implementation_plan.md`
   - Architecture overview and core abstractions
   - Implementation phases and current status
   - WebSocket protocol specification

2. **README**: `README.md`
   - Quick start, configuration examples
   - CLI usage and Nix workflow

## Workflow: Beads (bd) & Global Sync

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

### Quick Reference
```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

### Landing the Plane (Session Completion)
**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**
1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - `./scripts/ci.sh` (lint + typecheck + tests)
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds.
- NEVER stop before pushing - that leaves work stranded locally.
- NEVER say "ready to push when you are" - YOU must push.
- If push fails, resolve and retry until it succeeds.

## Global Behavioral Rules

1. **Safety First**: You must NEVER "nuke" a repository. Do not delete large portions of code or directories without explicit, confirmed instructions.

2. **Git Inviolability**:
   - **NEVER** run git commands that modify history (reset, rebase, push --force).
   - **NEVER** commit or push changes automatically unless explicitly asked.
   - **ALWAYS** leave git state management to the user.
   - **Respect .gitignore**: Do not add files that should be ignored.

3. **Meticulousness**:
   - Read all provided context before generating code.
   - Double-check types, protocols, and interfaces.
   - When refactoring, ensure no functionality is lost.
   - Prefer clarity and correctness over brevity.

4. **No Hallucinations**: Do not invent APIs. Search the codebase first.

5. **Context Preservation**:
   - **Documentation First**: Create and update documentation in `docs/`.
   - **Artifacts**: Use `docs/` for planning and architecture.
   - **Handover**: Write down your plan and progress so the next agent can resume.

## Hermes-Specific Rules (CRITICAL)

### 1. Type Safety (The "Red Line")

**These rules are INVIOLABLE. Breaking them causes mypy strict mode to fail.**

- **Type Everything**: ALL functions MUST have complete type annotations.
- **Strict Mode**: mypy runs with `strict = true`. No `Any` leaking from return values.
- **Protocol Compliance**: Adapters MUST implement `ModuleAdapter` protocol correctly.

```python
# CORRECT
def get(self, signal: str) -> float:
    return cast(float, self._sim.get(signal))

# WRONG - leaks Any
def get(self, signal: str) -> float:
    return self._sim.get(signal)  # mypy: Returning Any
```

### 2. Adapter Contract (MANDATORY)

All module adapters MUST implement these methods:

```python
@property
def name(self) -> str: ...
@property
def signals(self) -> dict[str, SignalDescriptor]: ...

def stage(self) -> None: ...
def step(self, dt: float) -> None: ...
def reset(self) -> None: ...
def get(self, signal: str) -> float: ...
def set(self, signal: str, value: float) -> None: ...
def close(self) -> None: ...
```

### 3. Signal Naming Convention

- **Qualified names**: `module.signal` (e.g., `icarus.Vehicle.position.z`)
- **Local names**: Signal name within module (e.g., `Vehicle.position.z`)
- **Wire config**: Always use qualified names in wiring configuration

### 4. Async/Await Patterns

- **WebSocket handlers**: Always async
- **Scheduler callbacks**: Async for telemetry integration
- **Module step()**: Sync (physics is CPU-bound)

```python
# Scheduler callback pattern
async def callback(frame: int, time: float) -> None:
    await self._send_telemetry_frame()

await self._scheduler.run(callback=callback)
```

### 5. Coding Style & Standards

- **Language Standard**: Python 3.11+
- **Formatting**: Use `ruff format` (configured in pyproject.toml)
- **Linting**: Use `ruff check` with configured rules
- **Type Checking**: `mypy --strict`
- **Testing**: pytest with pytest-asyncio for async tests

## Project Structure

```
src/hermes/
├── core/           # Core abstractions
│   ├── module.py   # ModuleAdapter protocol
│   ├── signal.py   # SignalDescriptor, SignalBus, Wire
│   ├── scheduler.py # Synchronous scheduler
│   └── config.py   # Pydantic configuration models
│
├── adapters/       # Module adapters
│   ├── icarus.py   # IcarusAdapter (pybind11)
│   ├── injection.py # InjectionAdapter (test signals)
│   └── script.py   # ScriptAdapter (Python modules)
│
├── server/         # WebSocket server
│   ├── protocol.py # Message types, serialization
│   ├── telemetry.py # Binary telemetry encoder
│   └── websocket.py # WebSocket server (asyncio)
│
└── cli/            # Command-line interface
    └── main.py     # Entry point

tests/              # Test suite (mirrors src structure)
examples/           # Example configurations
docs/               # Documentation
```

## Workflow Commands

All scripts auto-enter Nix if needed:

```bash
./scripts/dev.sh          # Enter Nix development environment
./scripts/test.sh         # Run all tests
./scripts/ci.sh           # Full CI (lint + typecheck + tests)
./scripts/coverage.sh     # Generate coverage report
./scripts/clean.sh        # Clean build artifacts
./scripts/install-hooks.sh # Install pre-commit hooks
```

**Inside nix develop:**
```bash
pytest                    # Run tests
pytest --cov=hermes       # Tests with coverage
ruff check src tests      # Lint
ruff format src tests     # Format
mypy src                  # Type check
hermes run config.yaml    # Run simulation
```

## Key Dependencies

- **icarus**: 6DOF simulation engine (pybind11 bindings via Nix)
- **websockets**: Async WebSocket server
- **pydantic**: Configuration validation
- **structlog**: Structured logging
- **numpy**: Signal array operations
- **click**: CLI framework

## Quick Reference

| Need | Use |
|:-----|:----|
| Type cast for Any | `cast(float, value)` from typing |
| Signal bus access | `bus.get("module.signal")` |
| Qualified name parse | `module, signal = name.split(".", 1)` |
| Async WebSocket | `async with serve(handler, host, port)` |
| Binary telemetry | `struct.pack("<I d H H", frame, time, count, 0)` |
| Config loading | `HermesConfig.from_yaml(path)` |
