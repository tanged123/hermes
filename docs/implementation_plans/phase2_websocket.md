# Phase 2: WebSocket Server

**Goal:** Daedalus can connect and receive telemetry
**Status:** Not Started
**Blocked By:** Phase 1 Complete
**Exit Criteria:** External WebSocket client receives binary telemetry at 60 Hz

---

## Overview

Phase 2 adds the WebSocket server that enables Daedalus (and other clients) to connect, receive telemetry streams, and send control commands. This transforms Hermes from a console application into a network service.

## Dependencies

- Phase 1 complete (core abstractions, scheduler, Icarus adapter)
- `websockets>=12.0`

---

## Task 2.1: Protocol Messages

**Issue ID:** `HRM-007`
**Priority:** Critical
**Blocked By:** Phase 1

### Objective
Define the JSON message protocol for client-server communication.

### Deliverables
- `src/hermes/server/protocol.py`
- Message type enum
- Command dataclass with parsing
- Message factory functions:
  - `make_schema_message()`
  - `make_event_message()`
  - `make_error_message()`
  - `make_ack_message()`

### Message Types

**Server → Client:**
- `schema` - Full signal schema on connect
- `event` - State changes (paused, running, reset)
- `error` - Error responses
- `ack` - Command acknowledgments

**Client → Server:**
- `cmd` - Control commands with action and params

### Acceptance Criteria
- [ ] All message types defined
- [ ] JSON serialization/deserialization works
- [ ] Unit tests for protocol parsing
- [ ] `docs/protocol.md` updated with examples

---

## Task 2.2: Binary Telemetry

**Issue ID:** `HRM-008`
**Priority:** Critical
**Blocked By:** HRM-007

### Objective
Implement efficient binary telemetry encoding for high-frequency signal streaming.

### Deliverables
- `src/hermes/server/telemetry.py`
- `TelemetryConfig` dataclass
- `TelemetryEncoder` class

### Binary Format

```
Header (16 bytes):
  - frame: u32 (4 bytes)
  - time: f64 (8 bytes)
  - count: u16 (2 bytes)
  - reserved: u16 (2 bytes)

Payload:
  - values: f64[] (8 bytes * count)
```

Total: 16 + 8*N bytes per frame

### Acceptance Criteria
- [ ] Encoder produces correct binary format
- [ ] Decoder matches encoder (round-trip test)
- [ ] Signal order matches subscription order
- [ ] Handles empty signal list

---

## Task 2.3: WebSocket Server

**Issue ID:** `HRM-009`
**Priority:** Critical
**Blocked By:** HRM-008

### Objective
Create the async WebSocket server with client management.

### Deliverables
- `src/hermes/server/websocket.py`
- `HermesServer` class

### Features
- Accept multiple client connections
- Send schema on connect
- Broadcast telemetry to all clients
- Handle client disconnects gracefully
- Structured logging for connections

### Acceptance Criteria
- [ ] Server starts and accepts connections
- [ ] Schema sent to new clients
- [ ] Multiple clients can connect
- [ ] Clean disconnect handling
- [ ] Proper async context management

---

## Task 2.4: Command Handling

**Issue ID:** `HRM-010`
**Priority:** High
**Blocked By:** HRM-009

### Objective
Implement handlers for client control commands.

### Commands

| Action | Params | Description |
|--------|--------|-------------|
| `pause` | - | Stop simulation loop |
| `resume` | - | Start/resume simulation |
| `reset` | - | Reset to initial conditions |
| `step` | `count` | Execute N frames (default 1) |
| `set` | `signal`, `value` | Set signal value |
| `subscribe` | `signals` | Configure telemetry subscription |

### Acceptance Criteria
- [ ] All commands implemented
- [ ] Error responses for invalid commands
- [ ] State change events broadcast
- [ ] Ack sent for set/subscribe

---

## Task 2.5: Telemetry Streaming

**Issue ID:** `HRM-011`
**Priority:** High
**Blocked By:** HRM-010

### Objective
Stream telemetry to connected clients at configurable rate.

### Features
- Configurable rate (default 60 Hz)
- Signal subscription (wildcards supported)
- Decimation (send at telemetry rate, not sim rate)
- Binary frame broadcast

### Signal Patterns
- Exact: `icarus.Vehicle.position.x`
- Wildcard: `icarus.Vehicle.*`
- All: `*`

### Acceptance Criteria
- [ ] Telemetry streams at configured rate
- [ ] Subscription filters work
- [ ] Wildcards expand correctly
- [ ] Binary frames sent to all clients

---

## Task 2.6: Integration Test

**Issue ID:** `HRM-012`
**Priority:** High
**Blocked By:** HRM-011

### Objective
End-to-end test with Python WebSocket client.

### Test Scenario
1. Start Hermes with test config
2. Connect WebSocket client
3. Receive schema message
4. Send subscribe command
5. Send resume command
6. Receive binary telemetry frames
7. Verify frame format and values
8. Send pause command
9. Disconnect cleanly

### Deliverables
- `tests/integration/test_websocket.py`
- Test fixture for server lifecycle

### Acceptance Criteria
- [ ] Client connects and receives schema
- [ ] Telemetry frames decode correctly
- [ ] Commands execute properly
- [ ] Clean shutdown on test end

---

## Beads Integration

```bash
# Create Phase 2 issues (after Phase 1 complete)
bd create -t "Protocol Messages" -d "JSON message types and serialization" -p critical -l phase2,server
bd create -t "Binary Telemetry" -d "Efficient binary encoder for telemetry" -p critical -l phase2,server
bd create -t "WebSocket Server" -d "asyncio WebSocket server with client management" -p critical -l phase2,server
bd create -t "Command Handling" -d "pause, resume, reset, step, set commands" -p high -l phase2,server
bd create -t "Telemetry Streaming" -d "Decimation, subscription, broadcast" -p high -l phase2,server
bd create -t "WebSocket Integration Test" -d "Python client end-to-end test" -p high -l phase2,tests

# View phase 2 work
bd list --label phase2
```

---

## Phase 2 Completion Checklist

- [ ] All HRM-007 through HRM-012 issues closed
- [ ] `./scripts/ci.sh` passes
- [ ] `hermes run config.yaml` starts WebSocket server
- [ ] External client can connect and receive telemetry
- [ ] 60 Hz telemetry verified
- [ ] `docs/protocol.md` complete
- [ ] `bd sync && git push` completed

---

## Implementation Notes

### Async Architecture

```
Main Thread:
  ├── WebSocket Server (asyncio)
  │   ├── Client Handler 1
  │   ├── Client Handler 2
  │   └── ...
  │
  └── Simulation Task (asyncio)
      ├── Scheduler.run()
      └── Telemetry Callback
```

### Telemetry Flow

```
Scheduler.step()
    │
    ▼
Callback(frame, time)
    │
    ├─ Check decimation (60 Hz gate)
    │
    ├─ Collect subscribed signals
    │
    ├─ Encode binary frame
    │
    └─ Broadcast to clients
```

---

## Next Phase Preview

Phase 3 (Multi-Module & Wiring) will add:
- InjectionAdapter for test signals
- Full wiring configuration
- Multi-module schema generation
- Cross-module signal routing

See `phase3_multimodule.md` for details.
