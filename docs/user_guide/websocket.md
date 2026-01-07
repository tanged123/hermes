# WebSocket Server

Hermes includes a WebSocket server for streaming real-time telemetry to external clients like visualization tools, dashboards, or custom applications.

## Overview

The WebSocket server provides:
- **Schema broadcast**: Clients receive signal definitions on connect
- **Signal subscription**: Subscribe to specific signals or patterns
- **Binary telemetry**: Efficient binary streaming at configurable rates
- **Control commands**: Pause, resume, step, reset simulation remotely
- **Signal injection**: Set signal values from external clients

## Configuration

Enable the WebSocket server in your YAML configuration:

```yaml
server:
  enabled: true          # Enable the server
  host: "0.0.0.0"        # Bind address (0.0.0.0 = all interfaces)
  port: 8765             # WebSocket port
  telemetry_hz: 60.0     # Telemetry streaming rate in Hz
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Whether to start the WebSocket server |
| `host` | string | `"0.0.0.0"` | Address to bind to |
| `port` | int | `8765` | Port number |
| `telemetry_hz` | float | `60.0` | Telemetry broadcast rate in Hz |

### Command-Line Overrides

```bash
# Disable server even if enabled in config
python -m hermes.cli.main run config.yaml --no-server

# Override port
python -m hermes.cli.main run config.yaml --port 9000
```

## Client Connection

### Connection Flow

1. Client connects to `ws://host:port`
2. Server sends schema message (JSON)
3. Client subscribes to signals
4. Client receives binary telemetry frames
5. Client can send control commands anytime

### Schema Message

On connect, the server sends a schema describing available signals:

```json
{
  "type": "schema",
  "modules": {
    "vehicle": {
      "signals": [
        {"name": "position.x", "type": "f64"},
        {"name": "position.y", "type": "f64"},
        {"name": "velocity.x", "type": "f64"},
        {"name": "velocity.y", "type": "f64"}
      ]
    }
  }
}
```

### Signal Subscription

Subscribe to signals using patterns:

```json
// Subscribe to all signals
{"action": "subscribe", "params": {"signals": ["*"]}}

// Subscribe to specific module
{"action": "subscribe", "params": {"signals": ["vehicle.*"]}}

// Subscribe to specific signals
{"action": "subscribe", "params": {"signals": ["vehicle.position.x", "vehicle.velocity.x"]}}
```

Server responds with acknowledgment:

```json
{
  "type": "ack",
  "action": "subscribe",
  "count": 4,
  "signals": ["vehicle.position.x", "vehicle.position.y", "vehicle.velocity.x", "vehicle.velocity.y"]
}
```

## Telemetry Format

Telemetry is sent as binary frames for efficiency. Each frame contains:

```
┌──────────────────────────────────────────────────┐
│ Header (24 bytes)                                │
├────────────┬────────────┬────────────┬──────────┤
│ Magic (4B) │ Frame (8B) │ Time (8B)  │ Count(4B)│
│ 0x48455254 │ uint64     │ float64    │ uint32   │
│ "HERT"     │ frame num  │ seconds    │ # values │
├────────────┴────────────┴────────────┴──────────┤
│ Payload (count * 8 bytes)                       │
│ [value0: f64, value1: f64, ...]                 │
└──────────────────────────────────────────────────┘
```

- **Magic**: 0x48455254 ("HERT" in little-endian)
- **Frame**: Current simulation frame number (uint64)
- **Time**: Simulation time in seconds (float64)
- **Count**: Number of signal values following (uint32)
- **Values**: Signal values in subscription order (float64 each)

### Decoding in Python

```python
import struct

def decode_telemetry(data: bytes) -> tuple[int, float, list[float]]:
    """Decode a binary telemetry frame."""
    magic, frame, time_s, count = struct.unpack("<IQdI", data[:24])

    if magic != 0x48455254:
        raise ValueError(f"Invalid magic: 0x{magic:08X}")

    values = list(struct.unpack(f"<{count}d", data[24:]))
    return frame, time_s, values
```

## Control Commands

### Pause Simulation

```json
{"action": "pause"}
```

Response:
```json
{"type": "ack", "action": "pause"}
{"type": "event", "event": "paused"}
```

### Resume Simulation

```json
{"action": "resume"}
```

Response:
```json
{"type": "ack", "action": "resume"}
{"type": "event", "event": "running"}
```

### Step Simulation

Advance by a specified number of frames (requires paused state):

```json
{"action": "step", "params": {"count": 10}}
```

Response:
```json
{"type": "ack", "action": "step", "count": 10, "frame": 110}
```

### Reset Simulation

```json
{"action": "reset"}
```

Response:
```json
{"type": "ack", "action": "reset"}
{"type": "event", "event": "reset"}
```

### Set Signal Value

```json
{"action": "set", "params": {"signal": "controller.input", "value": 42.5}}
```

Response:
```json
{"type": "ack", "action": "set", "signal": "controller.input", "value": 42.5}
```

Error response (unknown signal):
```json
{"type": "error", "message": "Unknown signal: controller.nonexistent"}
```

## Complete Example

### Configuration (`websocket_telemetry.yaml`)

```yaml
version: "0.2"

modules:
  vehicle:
    type: script
    script: ./mock_module.py
    signals:
      - name: position.x
        type: f64
        unit: m
      - name: position.y
        type: f64
        unit: m
      - name: velocity.x
        type: f64
        unit: m/s
      - name: velocity.y
        type: f64
        unit: m/s

execution:
  mode: realtime
  rate_hz: 100.0

server:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  telemetry_hz: 60.0
```

### Python Client

```python
#!/usr/bin/env python3
"""Simple WebSocket client for Hermes."""

import asyncio
import json
import struct
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        # Receive schema
        schema = json.loads(await ws.recv())
        print(f"Connected! Modules: {list(schema['modules'].keys())}")

        # Subscribe to all signals
        await ws.send(json.dumps({
            "action": "subscribe",
            "params": {"signals": ["*"]}
        }))
        ack = json.loads(await ws.recv())
        print(f"Subscribed to {ack['count']} signals")

        # Resume simulation
        await ws.send(json.dumps({"action": "resume"}))
        await ws.recv()  # ack
        await ws.recv()  # event

        # Receive telemetry
        print("\nReceiving telemetry (Ctrl+C to stop)...")
        while True:
            data = await ws.recv()
            if isinstance(data, bytes):
                _, frame, time_s, count = struct.unpack("<IQdI", data[:24])
                values = struct.unpack(f"<{count}d", data[24:])
                print(f"Frame {frame}: t={time_s:.3f}s, values={values}")

asyncio.run(main())
```

### Running the Example

Terminal 1:
```bash
python -m hermes.cli.main run examples/websocket_telemetry.yaml
```

Terminal 2:
```bash
python examples/websocket_client.py
```

## Error Handling

### Error Message Format

```json
{"type": "error", "message": "Description of the error"}
```

### Common Errors

| Error | Cause |
|-------|-------|
| `Invalid JSON` | Malformed JSON in client message |
| `Unknown action` | Unrecognized command action |
| `Unknown signal` | Signal name not found in schema |
| `No scheduler attached` | Control command sent but no scheduler available |

## Security Considerations

- Bind to `127.0.0.1` for local-only access
- Use `0.0.0.0` only in trusted networks
- No authentication is implemented (yet)
- Consider a reverse proxy with auth for production use

## Integration with Daedalus

The WebSocket server is designed for integration with the Daedalus visualization tool. Daedalus connects as a client and:

1. Receives the schema to build UI automatically
2. Subscribes to signals for real-time plotting
3. Sends control commands (pause/resume/step) via UI buttons
4. Injects signal values for testing scenarios

See the Daedalus documentation for specific integration details.

## Performance

- Binary telemetry minimizes bandwidth (24-byte header + 8 bytes per signal)
- Telemetry rate is independent of simulation rate
- Multiple clients supported (each with independent subscriptions)
- Server handles client disconnects gracefully

### Bandwidth Calculation

For 100 signals at 60 Hz:
- Frame size: 24 + (100 × 8) = 824 bytes
- Bandwidth: 824 × 60 = 49,440 bytes/sec ≈ 48 KB/s
