# Hermes WebSocket Protocol

This document describes the WebSocket protocol used for communication between Hermes and connected clients (e.g., Daedalus visualization).

## Overview

### Connection Lifecycle

1. Client connects to Hermes WebSocket server (default: `ws://localhost:8765`)
2. Server sends **schema** message with signal definitions
3. Client sends **subscribe** command to select signals for telemetry
4. Server streams binary telemetry frames at configured rate
5. Client can send control commands (pause, resume, reset, step, set)
6. Client disconnects gracefully

### Transport

- **Protocol**: WebSocket (RFC 6455)
- **Default Port**: 8765
- **Text Messages**: JSON for commands and responses
- **Binary Messages**: Packed telemetry data

## Message Format

### Server Messages (JSON)

All server messages are JSON objects with a `type` field:

```json
{"type": "schema", ...}
{"type": "event", ...}
{"type": "error", ...}
{"type": "ack", ...}
```

### Client Commands (JSON)

All client commands are JSON objects with an `action` field:

```json
{"action": "subscribe", "params": {...}}
{"action": "pause"}
{"action": "resume"}
```

## Server Messages

### schema

Sent immediately upon client connection. Contains full signal schema.

```json
{
  "type": "schema",
  "modules": {
    "module_name": {
      "signals": [
        {"name": "signal_name", "type": "f64"},
        {"name": "position.x", "type": "f64", "unit": "m"},
        {"name": "throttle", "type": "f64", "writable": true}
      ]
    }
  },
  "wiring": [
    {"src": "inputs.throttle", "dst": "physics.throttle_cmd", "gain": 1.0}
  ]
}
```

**Fields:**
- `modules`: Object mapping module names to their signals
- `signals[].name`: Local signal name (without module prefix)
- `signals[].type`: Data type (f64, f32, i64, i32, bool)
- `signals[].unit`: Optional physical unit string
- `signals[].writable`: Optional, true if signal can be modified via `set`
- `wiring`: Optional list of wire configurations between modules

### event

Broadcast to all clients when simulation state changes.

```json
{"type": "event", "event": "running"}
{"type": "event", "event": "paused"}
{"type": "event", "event": "reset"}
{"type": "event", "event": "stopped"}
```

**Event Types:**
- `running`: Simulation started or resumed
- `paused`: Simulation paused
- `reset`: Simulation reset to initial conditions
- `stopped`: Simulation ended

### error

Sent in response to invalid commands.

```json
{
  "type": "error",
  "message": "Unknown action: invalid_action"
}
```

**Fields:**
- `message`: Human-readable error description
- `code`: Optional numeric error code

### ack

Acknowledgment of successful command execution.

```json
{"type": "ack", "action": "subscribe", "count": 10, "signals": [...]}
{"type": "ack", "action": "pause"}
{"type": "ack", "action": "step", "count": 1, "frame": 42}
{"type": "ack", "action": "set", "signal": "inputs.throttle", "value": 0.75}
```

**Fields:**
- `action`: The command that was executed
- Additional action-specific fields

## Client Commands

### subscribe

Subscribe to signals for telemetry streaming.

```json
{
  "action": "subscribe",
  "params": {
    "signals": ["*"]
  }
}
```

**Params:**
- `signals`: List of signal patterns to subscribe to

**Signal Patterns:**
- `"*"` - All signals
- `"module.*"` - All signals from a specific module
- `"module.signal"` - Specific signal by qualified name

**Response:**
```json
{
  "type": "ack",
  "action": "subscribe",
  "count": 10,
  "signals": ["module.signal1", "module.signal2", ...]
}
```

### pause

Pause simulation execution.

```json
{"action": "pause"}
```

### resume

Resume paused simulation.

```json
{"action": "resume"}
```

### reset

Reset simulation to initial conditions.

```json
{"action": "reset"}
```

### step

Execute one or more simulation frames.

```json
{"action": "step"}
{"action": "step", "params": {"count": 10}}
```

**Params:**
- `count`: Optional, number of frames to execute (default: 1)

**Response:**
```json
{
  "type": "ack",
  "action": "step",
  "count": 10,
  "frame": 142
}
```

### set

Set a signal value (only for writable signals).

```json
{
  "action": "set",
  "params": {
    "signal": "inputs.throttle",
    "value": 0.75
  }
}
```

**Params:**
- `signal`: Qualified signal name (module.signal)
- `value`: Numeric value to set

**Response:**
```json
{
  "type": "ack",
  "action": "set",
  "signal": "inputs.throttle",
  "value": 0.75
}
```

## Binary Telemetry

After subscribing, the server streams binary telemetry frames at the configured rate (default: 60 Hz).

### Frame Format

Binary frames use little-endian byte order throughout.

```
┌──────────────────────────────────────────────────────────────┐
│                      Header (24 bytes)                       │
├──────────────────────────────────────────────────────────────┤
│                    Payload (8×N bytes)                       │
└──────────────────────────────────────────────────────────────┘
```

### Header (24 bytes)

| Offset | Size | Type | Field | Description |
|--------|------|------|-------|-------------|
| 0 | 4 | u32 | magic | 0x48455254 ("HERT" in ASCII) |
| 4 | 8 | u64 | frame | Frame number |
| 12 | 8 | f64 | time | Simulation time in seconds |
| 20 | 4 | u32 | count | Number of signal values |

### Payload

| Offset | Size | Type | Field | Description |
|--------|------|------|-------|-------------|
| 24 | 8×N | f64[] | values | Signal values in subscription order |

**Total Frame Size:** 24 + 8×N bytes

### Decoding Example (Python)

```python
import struct

HEADER_FORMAT = "<I Q d I"  # magic, frame, time, count
HEADER_SIZE = 24
MAGIC = 0x48455254

def decode_telemetry(data: bytes) -> tuple[int, float, list[float]]:
    """Decode binary telemetry frame."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Frame too short: {len(data)} < {HEADER_SIZE}")

    magic, frame, time, count = struct.unpack(
        HEADER_FORMAT, data[:HEADER_SIZE]
    )

    if magic != MAGIC:
        raise ValueError(f"Invalid magic: {magic:#x}")

    if count > 0:
        values = list(struct.unpack(
            f"<{count}d",
            data[HEADER_SIZE:HEADER_SIZE + count * 8]
        ))
    else:
        values = []

    return frame, time, values
```

## Signal Pattern Matching

When subscribing to signals, patterns are matched as follows:

| Pattern | Matches |
|---------|---------|
| `*` | All signals |
| `module.*` | All signals from `module` |
| `module.signal` | Exact signal (if it exists) |

Patterns can be combined in a single subscribe command:

```json
{
  "action": "subscribe",
  "params": {
    "signals": ["physics.*", "sensors.position.x", "sensors.position.y"]
  }
}
```

Duplicate signals are automatically removed while preserving order.

## Client Example (Python)

```python
import asyncio
import json
import struct
import websockets

async def main():
    async with websockets.connect("ws://localhost:8765") as ws:
        # Receive schema
        schema = json.loads(await ws.recv())
        print(f"Connected, {len(schema['modules'])} modules")

        # Subscribe to all signals
        await ws.send(json.dumps({
            "action": "subscribe",
            "params": {"signals": ["*"]}
        }))
        ack = json.loads(await ws.recv())
        print(f"Subscribed to {ack['count']} signals")

        # Receive telemetry
        for _ in range(100):
            data = await ws.recv()
            if isinstance(data, bytes):
                magic, frame, time, count = struct.unpack(
                    "<I Q d I", data[:24]
                )
                print(f"Frame {frame}: t={time:.3f}s, {count} values")

asyncio.run(main())
```

## Configuration

Server settings in `config.yaml`:

```yaml
server:
  enabled: true
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

**Fields:**
- `enabled`: Whether to start WebSocket server
- `host`: Bind address (use 0.0.0.0 for all interfaces)
- `port`: Listen port
- `telemetry_hz`: Telemetry broadcast rate

## Error Handling

Common error scenarios:

| Error | Cause | Resolution |
|-------|-------|------------|
| "Unknown action: X" | Invalid command action | Check action name |
| "Command missing 'action' field" | Malformed command | Include action field |
| "Unknown signal: X" | Signal doesn't exist | Check signal name |
| "step 'count' must be positive" | Invalid step count | Use count >= 1 |

The server logs warnings for invalid messages but maintains the connection.
