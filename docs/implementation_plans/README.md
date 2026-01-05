# Hermes Implementation Plans

This directory contains detailed, step-by-step implementation plans for Hermes development.

## Phase Overview

| Phase | Goal | Status |
|-------|------|--------|
| [Phase 1](phase1_foundation.md) | Foundation - Minimal working system with Icarus adapter | Not Started |
| [Phase 2](phase2_websocket.md) | WebSocket Server - Daedalus can connect and receive telemetry | Not Started |
| [Phase 3](phase3_multimodule.md) | Multi-Module & Wiring - Multiple modules with signal routing | Not Started |
| [Phase 4](phase4_polish.md) | Polish & Documentation - Production-ready for Daedalus | Not Started |

## Issue Tracking

All implementation tasks are tracked using **beads (bd)**. Each task has a unique issue ID (e.g., `HRM-001`).

### Quick Commands

```bash
# View available work
bd ready

# Start working on a task
bd update HRM-001 --status in_progress

# Complete a task
bd close HRM-001

# View all phase 1 tasks
bd list --label phase1

# Sync with git
bd sync
```

## Issue Summary

### Phase 1: Foundation
- `hermes-9yd` Project Setup (P0) - **READY**
- `hermes-71j` Core Abstractions (P0)
- `hermes-60w` Icarus Adapter (P0)
- `hermes-8to` Synchronous Scheduler (P0)
- `hermes-ume` CLI Skeleton (P1)
- `hermes-d5g` Phase 1 Tests (P1)

### Phase 2: WebSocket (to be created after Phase 1)
- Protocol Messages
- Binary Telemetry
- WebSocket Server
- Command Handling
- Telemetry Streaming
- WebSocket Integration Test

### Phase 3: Multi-Module (to be created after Phase 2)
- Injection Adapter
- Wire Configuration
- Signal Routing
- Qualified Names
- Schema Generation
- Multi-Module Test

### Phase 4: Polish (to be created after Phase 3)
- Error Handling
- Configuration Validation
- Protocol Documentation
- Example Configurations
- CI Setup

## Working on Tasks

1. **Check available work:**
   ```bash
   bd ready
   ```

2. **Claim a task:**
   ```bash
   bd update HRM-001 --status in_progress
   ```

3. **Reference the detailed plan:**
   Read the corresponding phase document for step-by-step instructions.

4. **Complete the task:**
   ```bash
   bd close HRM-001
   ```

5. **End of session:**
   ```bash
   bd sync
   git push
   ```

## Dependency Graph

```
Phase 1: Foundation
├── hermes-9yd Project Setup [READY]
│   └── hermes-71j Core Abstractions
│       ├── hermes-60w Icarus Adapter ──┐
│       ├── hermes-8to Scheduler ───────┼──► hermes-ume CLI Skeleton
│       └── hermes-d5g Tests            │
│                                       │
Phase 2: WebSocket (create after Phase 1)
│
Phase 3: Multi-Module (create after Phase 2)
│
Phase 4: Polish (create after Phase 3)
```

Use `bd blocked` to see current blockers, `bd ready` for available work.

## Exit Criteria

Each phase has specific exit criteria that must be met before proceeding:

- **Phase 1:** `hermes run` steps Icarus and prints telemetry to console
- **Phase 2:** External WebSocket client receives binary telemetry at 60 Hz
- **Phase 3:** Injection adapter can override Icarus inputs via wiring
- **Phase 4:** Hermes is documented and tested enough for Daedalus development
