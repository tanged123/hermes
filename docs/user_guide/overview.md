# Hermes Overview

## What is Hermes?

Hermes is a **multi-process simulation orchestration platform** designed for aerospace and robotics applications. It provides the infrastructure to coordinate multiple simulation modules—written in any language (C, C++, Python, Rust)—running as separate processes, communicating through high-performance POSIX IPC primitives.

## The Problem Hermes Solves

Modern simulation systems often need to:

1. **Integrate heterogeneous modules**: Physics engines in C++, control systems in Python, sensor models in Rust—all need to work together
2. **Maintain deterministic execution**: Modules must execute in a defined order with synchronized timesteps
3. **Support real-time and batch modes**: Hardware-in-the-loop testing requires wall-clock pacing; Monte Carlo runs need maximum speed
4. **Enable runtime inspection**: Engineers need to observe and inject values without recompiling

Traditional approaches—linking everything into one process or using network protocols—each have drawbacks:

| Approach | Problem |
|----------|---------|
| Monolithic linking | Language barriers, crash propagation, build complexity |
| Network IPC (TCP/UDP) | Latency, serialization overhead, complexity |
| File-based | Far too slow for real-time |

## The Hermes Solution

Hermes uses **POSIX shared memory** and **semaphores** for zero-copy, sub-microsecond-latency communication between processes, with **nanosecond-precision time tracking** for deterministic simulations:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           HERMES CORE                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                    Scheduler                                │     │
│  │  • Execution modes: realtime, afap, single_frame           │     │
│  │  • Frame timing and pacing                                  │     │
│  │  • Pause/resume/stop control                               │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                │                                     │
│                                ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                   Process Manager                           │     │
│  │  • Module lifecycle (load, stage, terminate)               │     │
│  │  • Subprocess spawning and monitoring                       │     │
│  │  • Coordination via barrier synchronization                 │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                │                                     │
│                                ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                     Data Backplane                          │     │
│  │  • POSIX Shared Memory (signal data exchange)              │     │
│  │  • Semaphores (frame synchronization)                       │     │
│  │  • Signal Registry (name → offset mapping)                  │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                │                                     │
│        ┌───────────────────────┼───────────────────────┐            │
│        ▼                       ▼                       ▼            │
│  ┌──────────┐           ┌──────────┐           ┌──────────┐        │
│  │ Module A │           │ Module B │           │ Module C │        │
│  │ (C/C++)  │           │ (Python) │           │ (Rust)   │        │
│  └──────────┘           └──────────┘           └──────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. Process Isolation

Each module runs as a separate OS process. Benefits:
- **Fault isolation**: One module crashing doesn't bring down others
- **Language freedom**: Use the best tool for each job
- **Independent deployment**: Update modules without rebuilding the whole system

### 2. Configuration-First

Everything is configured via YAML—no recompilation needed:
- Module definitions and paths
- Signal wiring between modules
- Execution parameters (rate, mode, duration)

### 3. Explicit Scheduling

Hermes doesn't guess execution order. You define it:
```yaml
execution:
  schedule:
    - sensors      # Run first
    - controller   # Then controller
    - actuators    # Finally actuators
```

### 4. Zero-Copy IPC

Shared memory means signals are exchanged without copying:
- Modules write directly to shared memory
- Other modules read directly from it
- Only synchronization requires system calls

### 5. Deterministic Time Tracking

Time is tracked as integer nanoseconds internally:
- **Reproducible**: Same results every run, across platforms
- **No drift**: Uses multiplication (frame × dt), not accumulation
- **Flexible rates**: Any positive rate_hz is supported (non-divisible rates rounded)
- **Bounded error**: 600 Hz has ~0.72ms error per hour (vs ~720ms with microseconds)

## Operating Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `realtime` | Paced to wall-clock time | Hardware-in-the-loop, visualization |
| `afap` | As fast as possible | Batch runs, Monte Carlo simulations |
| `single_frame` | Manual stepping | Debugging, scripted scenarios |

## The Hermes Ecosystem

Hermes is part of a larger simulation stack:

- **Icarus**: 6-DOF physics engine (provides the dynamics)
- **Hermes**: Orchestration layer (this project)
- **Daedalus**: Web-based visualization (consumes telemetry)

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Icarus  │────▶│ Hermes  │────▶│Daedalus │
│ Physics │     │  Orch   │     │  Viz    │
└─────────┘     └─────────┘     └─────────┘
```

## What's Implemented (Phase 1)

Phase 1 establishes the core infrastructure:

- **Shared Memory Backplane**: Signal storage and exchange
- **Synchronization Primitives**: Frame barrier for lockstep execution
- **Configuration System**: Pydantic-validated YAML loading
- **Process Manager**: Module lifecycle and subprocess management
- **Scheduler**: Multi-mode execution control with nanosecond precision
- **Deterministic Time**: Integer nanosecond tracking for reproducibility
- **CLI**: Command-line interface for running simulations
- **Scripting API**: Python interface for runtime inspection/injection

## Next Steps

Future phases will add:

- **WebSocket Server**: Real-time telemetry streaming
- **Icarus Integration**: Native physics engine bindings
- **Advanced Features**: Checkpointing, replay, distributed execution
