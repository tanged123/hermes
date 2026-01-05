---
trigger: always_on
---

# Agent Ruleset: Hermes Project

You are an advanced AI coding assistant working on **Hermes**, a Simulation Orchestration Platform for aerospace. Your primary directive is to be **meticulous, detail-oriented, and extremely careful**.

## Project Overview

Hermes is a **multi-process simulation framework** that orchestrates simulation modules, routes signals between them, and serves telemetry to visualization clients. It sits between physics engines like Icarus and visualization tools like Daedalus.

**Core Components:**
- **Execute/Core/Wrapper**: Process lifecycle management (load, init, schedule, terminate)
- **Data Backplane**: POSIX IPC (shared memory, semaphores, pipes) for inter-module communication
- **Scripting Infrastructure**: Python API for injection/inspection
- **WebSocket Server**: Serves telemetry to Daedalus clients

**Key Principles:**
- **Process Isolation**: Each module runs as a separate process
- **Language Agnostic**: Modules can be written in C, C++, Python, Rust, etc.
- **IPC-First**: All inter-module communication via POSIX IPC primitives
- **YAML Configuration**: First-class citizen, no recompile needed

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

### 2. Module Protocol (MANDATORY)

Modules (in any language) must implement these lifecycle methods:

```python
# Python module interface
def init(config_path: str, shm_name: str) -> int: ...  # 0 = success
def stage() -> int: ...
def step(dt: float) -> int: ...
def reset() -> int: ...
def terminate() -> None: ...
def get_signal(name: str) -> float: ...
def set_signal(name: str, value: float) -> None: ...
def list_signals() -> list[str]: ...
```

```c
// C module interface (include/hermes/module.h)
typedef struct {
    int (*init)(const char* config_path, const char* shm_name);
    int (*stage)(void);
    int (*step)(double dt);
    int (*reset)(void);
    void (*terminate)(void);
    double (*get_signal)(const char* name);
    void (*set_signal)(const char* name, double value);
    const char** (*list_signals)(void);
} hermes_module_t;
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
├── core/              # Execute/Core/Wrapper
│   ├── process.py     # Process lifecycle management
│   ├── scheduler.py   # Runtime scheduling
│   └── config.py      # Pydantic configuration models
│
├── backplane/         # Data Backplane
│   ├── shm.py         # Shared memory management
│   ├── signals.py     # Signal registry and routing
│   └── sync.py        # Semaphores and synchronization
│
├── protocol/          # Module protocol definitions
│   ├── messages.py    # IPC message formats
│   └── module.py      # Module interface specification
│
├── scripting/         # Scripting infrastructure
│   └── api.py         # Python injection/inspection API
│
├── server/            # WebSocket server (Phase 2)
│   ├── protocol.py    # Message types, serialization
│   ├── telemetry.py   # Binary telemetry encoder
│   └── websocket.py   # WebSocket server (asyncio)
│
└── cli/               # Command-line interface
    └── main.py        # Entry point

include/hermes/        # C headers for native modules
└── module.h           # Module protocol in C

tests/                 # Test suite (mirrors src structure)
examples/              # Example configurations
docs/                  # Documentation
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

- **posix-ipc**: POSIX shared memory and semaphores
- **pydantic**: Configuration validation
- **structlog**: Structured logging
- **numpy**: Signal array operations
- **click**: CLI framework
- **websockets**: Async WebSocket server (Phase 2)

## Quick Reference

| Need | Use |
|:-----|:----|
| Type cast for Any | `cast(float, value)` from typing |
| Signal access (shared memory) | `shm.get_signal("module.signal")` |
| Qualified name parse | `module, signal = name.split(".", 1)` |
| Shared memory attach | `posix_ipc.SharedMemory(name)` |
| Semaphore create | `posix_ipc.Semaphore(name, flags=posix_ipc.O_CREAT)` |
| Config loading | `HermesConfig.from_yaml(path)` |
| Binary telemetry | `struct.pack("<I Q d I", magic, frame, time, count)` |
