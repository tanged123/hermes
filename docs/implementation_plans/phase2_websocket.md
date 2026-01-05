# Phase 2: WebSocket Server

**Goal:** Daedalus can connect and receive telemetry
**Status:** Not Started
**Blocked By:** Phase 1 Complete
**Exit Criteria:** External WebSocket client receives binary telemetry at 60 Hz

---

## Overview

Phase 2 adds the WebSocket server that enables Daedalus (and other clients) to connect, receive telemetry streams, and send control commands. This transforms Hermes from a console application into a network service.

The WebSocket server reads signal data from the **shared memory backplane** established in Phase 1, enabling efficient telemetry streaming without copying data through the scheduler.

## Architecture Context

```
┌─────────────────────────────────────────────────────────────────┐
│                         HERMES                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Shared Memory Backplane                 │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                    │    │
│  │  │ Header  │ │ Signals │ │  Data   │                    │    │
│  │  │frame/time│ │Directory│ │ Region  │                    │    │
│  │  └─────────┘ └─────────┘ └─────────┘                    │    │
│  └──────────────────────┬──────────────────────────────────┘    │
│                         │                                        │
│         ┌───────────────┼───────────────┐                       │
│         │               │               │                       │
│         ▼               ▼               ▼                       │
│   ┌──────────┐   ┌──────────┐   ┌──────────────┐               │
│   │ Module A │   │ Module B │   │  WebSocket   │◄─── Daedalus  │
│   │ Process  │   │ Process  │   │   Server     │               │
│   └──────────┘   └──────────┘   └──────────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Dependencies

- Phase 1 complete (backplane, process manager, scheduler)
- `websockets>=12.0`

---

## Task 2.1: Protocol Messages

**Issue ID:** (create after Phase 1)
**Priority:** Critical (P0)
**Blocked By:** Phase 1

### Objective
Define the JSON message protocol for client-server communication.

### Deliverables
- `src/hermes/server/protocol.py`
- Message type enum
- Command dataclass with parsing
- Message factory functions

### Message Types

**Server → Client:**
| Type | Description |
|------|-------------|
| `schema` | Full signal schema on connect |
| `event` | State changes (paused, running, reset) |
| `error` | Error responses |
| `ack` | Command acknowledgments |

**Client → Server:**
| Type | Description |
|------|-------------|
| `cmd` | Control commands with action and params |

### Message Format
```python
from dataclasses import dataclass
from enum import Enum
import json

class MessageType(str, Enum):
    SCHEMA = "schema"
    EVENT = "event"
    ERROR = "error"
    ACK = "ack"
    CMD = "cmd"

@dataclass
class ServerMessage:
    type: MessageType
    payload: dict

    def to_json(self) -> str:
        return json.dumps({"type": self.type.value, **self.payload})

@dataclass
class Command:
    action: str
    params: dict

    @classmethod
    def from_json(cls, data: str) -> "Command":
        parsed = json.loads(data)
        return cls(action=parsed["action"], params=parsed.get("params", {}))
```

### Acceptance Criteria
- [ ] All message types defined
- [ ] JSON serialization/deserialization works
- [ ] Unit tests for protocol parsing
- [ ] `docs/protocol.md` started with examples

---

## Task 2.2: Binary Telemetry

**Issue ID:** (create after Phase 1)
**Priority:** Critical (P0)
**Blocked By:** Task 2.1

### Objective
Implement efficient binary telemetry encoding that reads from shared memory.

### Deliverables
- `src/hermes/server/telemetry.py`
- `TelemetryEncoder` class

### Binary Format
```
Header (24 bytes):
  - magic: u32 (4 bytes) - 0x48455254 ("HERT")
  - frame: u64 (8 bytes)
  - time: f64 (8 bytes)
  - count: u32 (4 bytes)

Payload:
  - values: f64[] (8 bytes * count)

Total: 24 + 8*N bytes per frame
```

### Implementation
```python
import struct
from hermes.backplane.shm import SharedMemoryManager

class TelemetryEncoder:
    MAGIC = 0x48455254  # "HERT"
    HEADER_FORMAT = "<I Q d I"  # magic, frame, time, count
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(self, shm: SharedMemoryManager, signals: list[str]) -> None:
        self._shm = shm
        self._signals = signals

    def encode(self) -> bytes:
        """Encode current state from shared memory to binary frame."""
        frame = self._shm.get_frame()
        time = self._shm.get_time()
        count = len(self._signals)

        header = struct.pack(
            self.HEADER_FORMAT,
            self.MAGIC, frame, time, count
        )

        values = [self._shm.get_signal(s) for s in self._signals]
        payload = struct.pack(f"<{count}d", *values)

        return header + payload
```

### Acceptance Criteria
- [ ] Encoder reads from shared memory
- [ ] Binary format matches specification
- [ ] Round-trip test passes (encode → decode)
- [ ] Signal order matches subscription order
- [ ] Handles empty signal list

---

## Task 2.3: WebSocket Server

**Issue ID:** (create after Phase 1)
**Priority:** Critical (P0)
**Blocked By:** Task 2.2

### Objective
Create the async WebSocket server with client management.

### Deliverables
- `src/hermes/server/websocket.py`
- `HermesServer` class

### Features
- Accept multiple client connections
- Send schema on connect (read from shared memory registry)
- Broadcast telemetry to all clients
- Handle client disconnects gracefully
- Structured logging for connections

### Implementation Sketch
```python
import asyncio
import websockets
from websockets.server import WebSocketServerProtocol
import structlog

log = structlog.get_logger()

class HermesServer:
    def __init__(
        self,
        shm: SharedMemoryManager,
        host: str = "0.0.0.0",
        port: int = 8765,
    ) -> None:
        self._shm = shm
        self._host = host
        self._port = port
        self._clients: set[WebSocketServerProtocol] = set()
        self._encoder: TelemetryEncoder | None = None

    async def start(self) -> None:
        async with websockets.serve(self._handler, self._host, self._port):
            log.info("Server started", host=self._host, port=self._port)
            await asyncio.Future()  # Run forever

    async def _handler(self, ws: WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        log.info("Client connected", remote=ws.remote_address)
        try:
            await self._send_schema(ws)
            async for message in ws:
                await self._handle_message(ws, message)
        finally:
            self._clients.discard(ws)
            log.info("Client disconnected", remote=ws.remote_address)

    async def broadcast_telemetry(self) -> None:
        """Broadcast binary telemetry to all clients."""
        if not self._clients or not self._encoder:
            return
        frame = self._encoder.encode()
        await asyncio.gather(
            *[c.send(frame) for c in self._clients],
            return_exceptions=True,
        )
```

### Acceptance Criteria
- [ ] Server starts and accepts connections
- [ ] Schema sent to new clients
- [ ] Multiple clients can connect
- [ ] Clean disconnect handling
- [ ] Proper async context management

---

## Task 2.4: Command Handling

**Issue ID:** (create after Phase 1)
**Priority:** High (P1)
**Blocked By:** Task 2.3

### Objective
Implement handlers for client control commands that interface with the scheduler.

### Commands

| Action | Params | Description |
|--------|--------|-------------|
| `pause` | - | Pause simulation loop |
| `resume` | - | Start/resume simulation |
| `reset` | - | Reset all modules to initial conditions |
| `step` | `count` | Execute N frames (default 1) |
| `set` | `signal`, `value` | Set signal value in shared memory |
| `subscribe` | `signals` | Configure telemetry subscription |

### Implementation
```python
async def _handle_command(self, ws: WebSocketServerProtocol, cmd: Command) -> None:
    match cmd.action:
        case "pause":
            self._scheduler.pause()
            await self._broadcast_event("paused")
            await ws.send(make_ack("pause"))

        case "resume":
            self._scheduler.resume()
            await self._broadcast_event("running")
            await ws.send(make_ack("resume"))

        case "reset":
            self._scheduler.reset()
            await self._broadcast_event("reset")
            await ws.send(make_ack("reset"))

        case "step":
            count = cmd.params.get("count", 1)
            self._scheduler.step(count)
            await ws.send(make_ack("step", {"count": count}))

        case "set":
            signal = cmd.params["signal"]
            value = cmd.params["value"]
            self._shm.set_signal(signal, value)
            await ws.send(make_ack("set"))

        case "subscribe":
            signals = cmd.params["signals"]
            self._encoder = TelemetryEncoder(self._shm, signals)
            await ws.send(make_ack("subscribe", {"count": len(signals)}))

        case _:
            await ws.send(make_error(f"Unknown action: {cmd.action}"))
```

### Acceptance Criteria
- [ ] All commands implemented
- [ ] Error responses for invalid commands
- [ ] State change events broadcast to all clients
- [ ] Ack sent for successful commands
- [ ] `set` writes to shared memory

---

## Task 2.5: Telemetry Streaming

**Issue ID:** (create after Phase 1)
**Priority:** High (P1)
**Blocked By:** Task 2.4

### Objective
Stream telemetry to connected clients at configurable rate.

### Features
- Configurable rate (default 60 Hz)
- Signal subscription with wildcards
- Decimation (send at telemetry rate, not sim rate)
- Binary frame broadcast

### Signal Patterns
```python
def expand_pattern(pattern: str, registry: SignalRegistry) -> list[str]:
    """Expand signal pattern to list of qualified names."""
    if pattern == "*":
        return list(registry.all_signals().keys())
    if pattern.endswith(".*"):
        module = pattern[:-2]
        return registry.list_module(module)
    return [pattern]  # Exact match
```

### Telemetry Loop
```python
async def telemetry_loop(self, rate_hz: float = 60.0) -> None:
    """Background task that broadcasts telemetry at fixed rate."""
    interval = 1.0 / rate_hz
    while True:
        await asyncio.sleep(interval)
        await self.broadcast_telemetry()
```

### Acceptance Criteria
- [ ] Telemetry streams at configured rate
- [ ] Subscription filters work
- [ ] Wildcards expand correctly
- [ ] Binary frames sent to all clients
- [ ] Decimation independent of sim rate

---

## Task 2.6: Server Integration

**Issue ID:** (create after Phase 1)
**Priority:** High (P1)
**Blocked By:** Task 2.5

### Objective
Integrate WebSocket server with CLI and scheduler.

### CLI Changes
```python
@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
@click.option("--no-server", is_flag=True, help="Run without WebSocket server")
def run(config_path: Path, no_server: bool) -> None:
    """Run simulation from configuration file."""
    config = HermesConfig.from_yaml(config_path)

    with ProcessManager(config) as pm:
        scheduler = Scheduler(pm, config.execution)

        async def main() -> None:
            tasks = []

            # Start WebSocket server if enabled
            if not no_server and config.server.enabled:
                server = HermesServer(
                    shm=pm.shm,
                    host=config.server.host,
                    port=config.server.port,
                )
                tasks.append(asyncio.create_task(server.start()))
                tasks.append(asyncio.create_task(
                    server.telemetry_loop(config.server.telemetry_hz)
                ))

            # Run simulation
            scheduler.stage()
            await scheduler.run()

            # Cleanup
            for task in tasks:
                task.cancel()

        asyncio.run(main())
```

### Acceptance Criteria
- [ ] `hermes run config.yaml` starts server if enabled
- [ ] `hermes run config.yaml --no-server` skips server
- [ ] Server shuts down cleanly on simulation end
- [ ] Ctrl+C terminates both server and simulation

---

## Task 2.7: Integration Test

**Issue ID:** (create after Phase 1)
**Priority:** High (P1)
**Blocked By:** Task 2.6

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
9. Verify simulation paused
10. Disconnect cleanly

### Deliverables
- `tests/integration/test_websocket.py`
- Test fixture for server lifecycle

### Test Implementation
```python
import pytest
import asyncio
import websockets
import struct

@pytest.fixture
async def hermes_server():
    """Start Hermes server for testing."""
    # Start server in background
    # Yield connection URL
    # Cleanup on exit

@pytest.mark.asyncio
async def test_telemetry_stream(hermes_server):
    async with websockets.connect(hermes_server) as ws:
        # Receive schema
        schema = await ws.recv()
        assert "modules" in json.loads(schema)

        # Subscribe to signals
        await ws.send(json.dumps({
            "action": "subscribe",
            "params": {"signals": ["*"]}
        }))
        ack = await ws.recv()
        assert json.loads(ack)["type"] == "ack"

        # Start simulation
        await ws.send(json.dumps({"action": "resume"}))

        # Receive telemetry
        frame = await ws.recv()
        assert isinstance(frame, bytes)
        magic, = struct.unpack("<I", frame[:4])
        assert magic == 0x48455254
```

### Acceptance Criteria
- [ ] Client connects and receives schema
- [ ] Telemetry frames decode correctly
- [ ] Commands execute properly
- [ ] Clean shutdown on test end

---

## Beads Integration

Issues will be created after Phase 1 is complete:

```bash
# Create Phase 2 issues
bd create --title "Protocol Messages" -d "JSON message types and serialization" -p 0 -l phase2,server
bd create --title "Binary Telemetry" -d "Efficient binary encoder reading from shared memory" -p 0 -l phase2,server
bd create --title "WebSocket Server" -d "asyncio WebSocket server with client management" -p 0 -l phase2,server
bd create --title "Command Handling" -d "pause, resume, reset, step, set, subscribe commands" -p 1 -l phase2,server
bd create --title "Telemetry Streaming" -d "Decimation, subscription wildcards, broadcast" -p 1 -l phase2,server
bd create --title "Server Integration" -d "CLI integration and server lifecycle" -p 1 -l phase2,cli
bd create --title "WebSocket Integration Test" -d "Python client end-to-end test" -p 1 -l phase2,tests

# View phase 2 work
bd list --label phase2
```

---

## Phase 2 Completion Checklist

- [ ] All Phase 2 issues closed
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
Main Process:
  │
  ├── Process Manager
  │   ├── Module Process 1
  │   ├── Module Process 2
  │   └── ...
  │
  ├── Scheduler Task (asyncio)
  │   └── step() → update shared memory
  │
  └── WebSocket Server (asyncio)
      ├── Client Handler 1
      ├── Client Handler 2
      ├── Telemetry Loop (reads shared memory)
      └── ...
```

### Telemetry Flow

```
Scheduler.step()
    │
    ▼
Shared Memory Updated
    │
    ▼
Telemetry Loop (60 Hz)
    │
    ├─ Read frame/time from header
    │
    ├─ Read subscribed signals from data region
    │
    ├─ Encode binary frame
    │
    └─ Broadcast to clients
```

---

## Next Phase Preview

Phase 3 (Multi-Module & Wiring) will add:
- Signal wiring between modules
- Wire routing through shared memory
- Dynamic module configuration
- Cross-module telemetry

See `phase3_multimodule.md` for details.
