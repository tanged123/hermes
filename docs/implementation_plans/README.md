# Hermes Implementation Plans

This directory contains detailed, step-by-step implementation plans for Hermes development.

## Architecture Overview

Hermes is a **multi-process simulation framework** with:

- **Execute/Core/Wrapper**: Process lifecycle management, scheduling, coordination
- **Data Backplane**: POSIX IPC (shared memory, semaphores, pipes)
- **Scripting Infrastructure**: Python API for injection/inspection
- **Language-Agnostic Modules**: C, C++, Python, Rust, etc.
- **YAML Configuration**: First-class citizen, no recompile needed

## Phase Overview

| Phase | Goal | Status |
|-------|------|--------|
| [Phase 1](phase1_foundation.md) | Foundation - IPC backplane, process management, YAML config | Not Started |
| [Phase 2](phase2_websocket.md) | WebSocket Server - Daedalus can connect and receive telemetry | Not Started |
| [Phase 3](phase3_multimodule.md) | Multi-Module & Wiring - Multiple modules with signal routing | Not Started |
| [Phase 4](phase4_polish.md) | Polish & Documentation - Production-ready for Daedalus | Not Started |

## Issue Tracking

All implementation tasks are tracked using **beads (bd)**. Each task has a unique issue ID.

### Quick Commands

```bash
# View available work
bd ready

# Start working on a task
bd update <id> --status in_progress

# Complete a task
bd close <id>

# View all phase 1 tasks
bd list --label phase1

# Sync with git
bd sync
```

## Phase 1 Issue Summary

### Core Infrastructure (P0)

| Issue ID | Task | Description |
|----------|------|-------------|
| `hermes-9yd` | Project Setup | pyproject.toml, directory structure, tooling |
| `hermes-71j` | Shared Memory | POSIX shared memory for signal data |
| `hermes-60w` | Synchronization | Semaphores for frame barriers |
| `hermes-8to` | YAML Configuration | Pydantic models for config parsing |

### Module Management (P1)

| Issue ID | Task | Description |
|----------|------|-------------|
| `hermes-ume` | Process Manager | Load, control, terminate module processes |
| `hermes-d5g` | Scheduler | Runtime scheduling (realtime, AFAP, single-frame) |
| `hermes-p7k` | Scripting API | Python injection/inspection interface |
| `hermes-anr` | CLI | `hermes run`, `hermes validate` commands |

### Protocol & Testing (P1-P2)

| Issue ID | Task | Description |
|----------|------|-------------|
| `hermes-xjl` | C Header | Module protocol for native modules |
| `hermes-gr1` | Tests | Unit tests and integration tests |

## Dependency Graph

```
Phase 1: Foundation
├── hermes-9yd Project Setup [READY]
│   │
│   ├── hermes-71j Shared Memory
│   │   │
│   │   ├── hermes-60w Synchronization ─────┐
│   │   │                                    │
│   │   ├── hermes-p7k Scripting API ───────┤
│   │   │                                    │
│   │   └── hermes-xjl C Header ────────────┤
│   │                                        │
│   └── hermes-8to YAML Config ─────────────┤
│                                            │
│                   ┌───────────────────────┤
│                   │                        │
│           hermes-ume Process Manager ◄────┘
│                   │
│           hermes-d5g Scheduler
│                   │
│           hermes-anr CLI ◄── hermes-8to
│                   │
│           hermes-gr1 Tests ◄── hermes-p7k, hermes-xjl

Phase 2: WebSocket (create after Phase 1)
│
Phase 3: Multi-Module (create after Phase 2)
│
Phase 4: Polish (create after Phase 3)
```

Use `bd blocked` to see current blockers, `bd ready` for available work.

## Working on Tasks

1. **Check available work:**
   ```bash
   bd ready
   ```

2. **Claim a task:**
   ```bash
   bd update <id> --status in_progress
   ```

3. **Reference the detailed plan:**
   Read the corresponding phase document for step-by-step instructions.

4. **Complete the task:**
   ```bash
   bd close <id>
   ```

5. **End of session:**
   ```bash
   bd sync
   git push
   ```

## Exit Criteria

Each phase has specific exit criteria that must be met before proceeding:

- **Phase 1:** `hermes run config.yaml` loads module processes, exchanges signals via shared memory
- **Phase 2:** External WebSocket client receives binary telemetry at 60 Hz
- **Phase 3:** Injection adapter can override Icarus inputs via wiring
- **Phase 4:** Hermes is documented and tested enough for Daedalus development

## Key Architecture Decisions

### Multi-Process vs In-Process

Hermes uses **separate processes** for each module, not in-process Python objects. This enables:
- Language-agnostic modules (C, C++, Rust, Python)
- Process isolation for stability
- True parallel execution on multi-core systems
- Clean resource cleanup on crash

### IPC Strategy

| Mechanism | Use Case |
|-----------|----------|
| Shared Memory | High-frequency signal data (60+ Hz) |
| Semaphores | Frame synchronization barriers |
| Named Pipes | Control messages (stage, reset, terminate) |

Modules can additionally use OS-provided resources like UDP, Unix sockets, etc.

### Operating Modes

| Mode | Description |
|------|-------------|
| `realtime` | Paced to wall-clock (HIL, visualization) |
| `afap` | As fast as possible (batch, Monte Carlo) |
| `single_frame` | Manual stepping (debug, scripted scenarios) |
