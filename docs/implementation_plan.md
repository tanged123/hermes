# Hermes Implementation Plan

**Version:** 0.1
**Date:** January 2026
**Status:** Implementation Ready

---

## 1. Overview

Hermes is a **System Test and Execution Platform (STEP)** that orchestrates simulation modules, routes signals between them, and serves telemetry to visualization clients. It is **not** a physics engine—it delegates computation to modules like Icarus.

### Goals

1. Load and manage multiple simulation modules via adapters
2. Route signals between modules based on wiring configuration
3. Execute synchronous simulation loops at configurable rates
4. Serve telemetry to Daedalus clients via WebSocket
5. Enable scripted test scenarios in Python

### Non-Goals (Phase 1)

- Real-time execution with hard deadlines
- Multi-threaded parallel module execution
- Distributed simulation across multiple hosts

---

## 2. Project Structure

```
hermes/
├── pyproject.toml              # Project metadata, dependencies
├── README.md
├── src/
│   └── hermes/
│       ├── __init__.py         # Public API exports
│       ├── py.typed            # PEP 561 marker
│       │
│       ├── core/               # Core abstractions
│       │   ├── __init__.py
│       │   ├── module.py       # ModuleAdapter protocol
│       │   ├── signal.py       # SignalDescriptor, SignalBus
│       │   ├── scheduler.py    # Synchronous scheduler
│       │   └── config.py       # Configuration dataclasses
│       │
│       ├── adapters/           # Module adapters
│       │   ├── __init__.py
│       │   ├── icarus.py       # IcarusAdapter (cffi)
│       │   ├── script.py       # ScriptAdapter (Python modules)
│       │   └── injection.py    # InjectionAdapter (signal injection)
│       │
│       ├── server/             # WebSocket server
│       │   ├── __init__.py
│       │   ├── protocol.py     # Message types, serialization
│       │   ├── telemetry.py    # Binary telemetry encoder
│       │   └── websocket.py    # WebSocket server (asyncio)
│       │
│       └── cli/                # Command-line interface
│           ├── __init__.py
│           └── main.py         # Entry point
│
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── test_signal_bus.py
│   ├── test_scheduler.py
│   ├── test_icarus_adapter.py
│   ├── test_protocol.py
│   └── integration/
│       └── test_full_loop.py
│
├── examples/
│   ├── basic_sim.yaml          # Minimal configuration
│   ├── multi_module.yaml       # Multiple modules with wiring
│   └── scripts/
│       └── test_attitude.py    # Example test script
│
└── docs/
    ├── implementation_plan.md  # This document
    └── protocol.md             # Wire protocol specification
```

---

## 3. Dependencies

### Runtime Dependencies

```toml
[project]
dependencies = [
    "websockets>=12.0",       # Async WebSocket server
    "pyyaml>=6.0",            # Configuration parsing
    "pydantic>=2.5",          # Config validation & dataclasses
    "structlog>=24.1",        # Structured logging
    "numpy>=1.26",            # Signal array operations
    "click>=8.1",             # CLI framework
]

# icarus Python bindings (pybind11) provided by nix environment
```

### Development Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.1",              # Linting + formatting
    "mypy>=1.8",              # Type checking
    "pre-commit>=3.6",
]
```

---

## 4. Core Abstractions

### 4.1 ModuleAdapter Protocol

```python
# src/hermes/core/module.py

from typing import Protocol, runtime_checkable
from hermes.core.signal import SignalDescriptor

@runtime_checkable
class ModuleAdapter(Protocol):
    """Interface for simulation modules."""

    @property
    def name(self) -> str:
        """Unique module identifier."""
        ...

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        """Available signals with metadata."""
        ...

    def stage(self) -> None:
        """Prepare for execution. Called once before run loop."""
        ...

    def step(self, dt: float) -> None:
        """Advance module by dt seconds."""
        ...

    def reset(self) -> None:
        """Return to initial conditions."""
        ...

    def get(self, signal: str) -> float:
        """Get signal value by local name (without module prefix)."""
        ...

    def set(self, signal: str, value: float) -> None:
        """Set signal value by local name."""
        ...

    def get_bulk(self, signals: list[str]) -> list[float]:
        """Get multiple signal values efficiently."""
        return [self.get(s) for s in signals]  # Default implementation

    def close(self) -> None:
        """Release resources."""
        ...
```

### 4.2 SignalDescriptor

```python
# src/hermes/core/signal.py

from dataclasses import dataclass
from enum import Enum
from typing import Literal

class SignalType(Enum):
    SCALAR = "f64"
    VEC3 = "vec3"
    QUAT = "quat"

@dataclass(frozen=True, slots=True)
class SignalDescriptor:
    """Metadata for a signal."""
    name: str                              # Local name (e.g., "Vehicle.position.x")
    type: SignalType = SignalType.SCALAR
    unit: str = ""
    writable: bool = True
    description: str = ""
```

### 4.3 SignalBus

```python
# src/hermes/core/signal.py (continued)

@dataclass
class Wire:
    """Connection between two signals."""
    src_module: str
    src_signal: str
    dst_module: str
    dst_signal: str
    gain: float = 1.0
    offset: float = 0.0

class SignalBus:
    """Routes signals between modules."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleAdapter] = {}
        self._wires: list[Wire] = []

    def register_module(self, module: ModuleAdapter) -> None:
        """Add a module to the bus."""
        self._modules[module.name] = module

    def add_wire(self, wire: Wire) -> None:
        """Add a signal wire."""
        self._validate_wire(wire)
        self._wires.append(wire)

    def route(self) -> None:
        """Transfer all wired signals (src → dst)."""
        for wire in self._wires:
            src = self._modules[wire.src_module]
            dst = self._modules[wire.dst_module]
            value = src.get(wire.src_signal)
            dst.set(wire.dst_signal, value * wire.gain + wire.offset)

    def get(self, qualified_name: str) -> float:
        """Get signal by qualified name (module.signal)."""
        module_name, signal_name = self._parse_qualified(qualified_name)
        return self._modules[module_name].get(signal_name)

    def set(self, qualified_name: str, value: float) -> None:
        """Set signal by qualified name."""
        module_name, signal_name = self._parse_qualified(qualified_name)
        self._modules[module_name].set(signal_name, value)

    def get_schema(self) -> dict:
        """Return full schema for all modules."""
        return {
            "modules": {
                name: {
                    "signals": {
                        sig.name: {"type": sig.type.value, "unit": sig.unit}
                        for sig in mod.signals.values()
                    }
                }
                for name, mod in self._modules.items()
            },
            "wiring": [
                {
                    "src": f"{w.src_module}.{w.src_signal}",
                    "dst": f"{w.dst_module}.{w.dst_signal}",
                }
                for w in self._wires
            ],
        }
```

### 4.4 Scheduler

```python
# src/hermes/core/scheduler.py

import time
from enum import Enum
from dataclasses import dataclass
from hermes.core.signal import SignalBus

class ExecutionMode(Enum):
    AS_FAST_AS_POSSIBLE = "afap"   # No pacing, max speed
    REAL_TIME = "realtime"          # Wall-clock pacing
    PAUSED = "paused"               # Waiting for step command

@dataclass
class SchedulerConfig:
    dt: float = 0.01                # 100 Hz default
    mode: ExecutionMode = ExecutionMode.AS_FAST_AS_POSSIBLE
    end_time: float | None = None   # None = run forever

class Scheduler:
    """Synchronous simulation scheduler."""

    def __init__(self, bus: SignalBus, config: SchedulerConfig) -> None:
        self._bus = bus
        self._config = config
        self._time: float = 0.0
        self._frame: int = 0
        self._running: bool = False

    @property
    def time(self) -> float:
        return self._time

    @property
    def frame(self) -> int:
        return self._frame

    def stage(self) -> None:
        """Stage all modules."""
        for module in self._bus._modules.values():
            module.stage()
        self._time = 0.0
        self._frame = 0

    def step(self) -> None:
        """Execute one simulation frame."""
        dt = self._config.dt

        # Step all modules in registration order
        # TODO: Topological sort based on wiring dependencies
        for module in self._bus._modules.values():
            module.step(dt)

        # Route signals between modules
        self._bus.route()

        # Advance time
        self._time += dt
        self._frame += 1

    def reset(self) -> None:
        """Reset all modules to initial state."""
        for module in self._bus._modules.values():
            module.reset()
        self._time = 0.0
        self._frame = 0

    async def run(self, callback=None) -> None:
        """Run simulation loop until end_time or stopped."""
        self._running = True
        wall_start = time.perf_counter()

        while self._running:
            # Check end condition
            if self._config.end_time and self._time >= self._config.end_time:
                break

            # Execute frame
            self.step()

            # Optional callback (for telemetry)
            if callback:
                await callback(self._frame, self._time)

            # Real-time pacing
            if self._config.mode == ExecutionMode.REAL_TIME:
                target_wall = wall_start + self._time
                sleep_time = target_wall - time.perf_counter()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        self._running = False

    def stop(self) -> None:
        """Stop the run loop."""
        self._running = False
```

---

## 5. Icarus Adapter

### 5.1 Using pybind11 Bindings

Icarus provides Python bindings via pybind11 (built with `BUILD_INTERFACES=ON`).
The adapter wraps these bindings to provide the `ModuleAdapter` interface.

```python
# src/hermes/adapters/icarus.py

from pathlib import Path
from hermes.core.signal import SignalDescriptor, SignalType

class IcarusAdapter:
    """Adapter for Icarus 6DOF simulation via pybind11 bindings."""

    def __init__(self, name: str, config_path: str | Path) -> None:
        self._name = name
        self._config_path = Path(config_path)

        # Import icarus pybind11 module
        import icarus
        self._sim = icarus.Simulator(str(self._config_path))
        self._icarus = icarus

        # Build signal descriptors
        self._signals: dict[str, SignalDescriptor] = {}
        for signal_name in self._sim.signals:
            self._signals[signal_name] = SignalDescriptor(
                name=signal_name,
                type=SignalType.SCALAR,
            )

    @property
    def name(self) -> str:
        return self._name

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        return self._signals

    def stage(self) -> None:
        self._sim.stage()

    def step(self, dt: float) -> None:
        if dt == 0 or dt == self._sim.dt:
            self._sim.step()
        else:
            self._sim.step(dt)

    def reset(self) -> None:
        self._sim.reset()

    def get(self, signal: str) -> float:
        try:
            return self._sim.get(signal)
        except self._icarus.SignalNotFoundError as e:
            raise KeyError(f"Signal not found: {signal}") from e

    def set(self, signal: str, value: float) -> None:
        try:
            self._sim.set(signal, value)
        except self._icarus.SignalNotFoundError as e:
            raise KeyError(f"Signal not found: {signal}") from e

    def get_time(self) -> float:
        return self._sim.time

    def close(self) -> None:
        self._sim = None
```

**Benefits of pybind11 over cffi:**
- No need to maintain C API definitions in Python
- Automatic numpy integration for state vectors
- Python exceptions mapped from C++ exceptions
- Better type safety and IDE support

### 5.2 InjectionAdapter (Signal Injection)

```python
# src/hermes/adapters/injection.py

from hermes.core.module import ModuleAdapter
from hermes.core.signal import SignalDescriptor

class InjectionAdapter:
    """Adapter for injecting test signals."""

    def __init__(self, name: str, signals: list[str]) -> None:
        self._name = name
        self._values: dict[str, float] = {s: 0.0 for s in signals}
        self._signals = {
            s: SignalDescriptor(name=s, writable=True) for s in signals
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        return self._signals

    def stage(self) -> None:
        pass

    def step(self, dt: float) -> None:
        pass  # Values persist until changed

    def reset(self) -> None:
        self._values = {s: 0.0 for s in self._values}

    def get(self, signal: str) -> float:
        return self._values[signal]

    def set(self, signal: str, value: float) -> None:
        self._values[signal] = value

    def close(self) -> None:
        pass
```

---

## 6. WebSocket Server

### 6.1 Protocol Messages

```python
# src/hermes/server/protocol.py

from dataclasses import dataclass
from enum import Enum
from typing import Any
import json

class MessageType(Enum):
    # Server → Client
    SCHEMA = "schema"
    EVENT = "event"
    ERROR = "error"
    ACK = "ack"

    # Client → Server
    COMMAND = "cmd"

@dataclass
class Command:
    """Client command."""
    action: str
    params: dict[str, Any]

    @classmethod
    def from_json(cls, data: str) -> "Command":
        obj = json.loads(data)
        return cls(
            action=obj["action"],
            params={k: v for k, v in obj.items() if k not in ("type", "action")},
        )

def make_schema_message(schema: dict, version: str = "0.2") -> str:
    """Create schema message JSON."""
    return json.dumps({
        "type": "schema",
        "version": version,
        **schema,
    })

def make_event_message(name: str, **data) -> str:
    """Create event message JSON."""
    return json.dumps({"type": "event", "name": name, **data})

def make_error_message(message: str, code: str = "ERROR") -> str:
    """Create error message JSON."""
    return json.dumps({"type": "error", "code": code, "message": message})

def make_ack_message(action: str) -> str:
    """Create acknowledgment message JSON."""
    return json.dumps({"type": "ack", "action": action})
```

### 6.2 Binary Telemetry

```python
# src/hermes/server/telemetry.py

import struct
from dataclasses import dataclass

@dataclass
class TelemetryConfig:
    """Telemetry streaming configuration."""
    rate_hz: float = 60.0
    subscribed_signals: list[str] | None = None  # None = all signals

class TelemetryEncoder:
    """Encodes telemetry frames as binary."""

    # Header format: frame(u32) + time(f64) + count(u16) + reserved(u16)
    HEADER_FORMAT = "<I d H H"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(self, signals: list[str]) -> None:
        self._signals = signals
        self._signal_format = f"<{len(signals)}d"

    @property
    def signals(self) -> list[str]:
        return self._signals

    def encode(self, frame: int, time: float, values: list[float]) -> bytes:
        """Encode a telemetry frame as binary."""
        header = struct.pack(
            self.HEADER_FORMAT,
            frame,
            time,
            len(values),
            0,  # reserved
        )
        payload = struct.pack(self._signal_format, *values)
        return header + payload

    @classmethod
    def decode_header(cls, data: bytes) -> tuple[int, float, int]:
        """Decode header, return (frame, time, count)."""
        frame, time, count, _ = struct.unpack(cls.HEADER_FORMAT, data[:cls.HEADER_SIZE])
        return frame, time, count
```

### 6.3 WebSocket Server

```python
# src/hermes/server/websocket.py

import asyncio
import structlog
from websockets.server import serve, WebSocketServerProtocol
from hermes.core.scheduler import Scheduler
from hermes.core.signal import SignalBus
from hermes.server.protocol import (
    Command, make_schema_message, make_event_message,
    make_error_message, make_ack_message,
)
from hermes.server.telemetry import TelemetryEncoder, TelemetryConfig

log = structlog.get_logger()

class HermesServer:
    """WebSocket server for Hermes protocol."""

    def __init__(
        self,
        bus: SignalBus,
        scheduler: Scheduler,
        host: str = "0.0.0.0",
        port: int = 8765,
        telemetry_config: TelemetryConfig | None = None,
    ) -> None:
        self._bus = bus
        self._scheduler = scheduler
        self._host = host
        self._port = port
        self._telemetry_config = telemetry_config or TelemetryConfig()

        self._clients: set[WebSocketServerProtocol] = set()
        self._encoder: TelemetryEncoder | None = None
        self._running = False

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._running = True
        async with serve(self._handler, self._host, self._port) as server:
            log.info("Server started", host=self._host, port=self._port)
            await server.wait_closed()

    async def _handler(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a client connection."""
        self._clients.add(websocket)
        log.info("Client connected", remote=websocket.remote_address)

        try:
            # Send schema on connect
            schema = self._bus.get_schema()
            await websocket.send(make_schema_message(schema))

            # Handle incoming messages
            async for message in websocket:
                await self._handle_message(websocket, message)

        except Exception as e:
            log.error("Client error", error=str(e))
        finally:
            self._clients.discard(websocket)
            log.info("Client disconnected", remote=websocket.remote_address)

    async def _handle_message(
        self, websocket: WebSocketServerProtocol, message: str
    ) -> None:
        """Process a client message."""
        try:
            cmd = Command.from_json(message)
            await self._execute_command(websocket, cmd)
        except Exception as e:
            await websocket.send(make_error_message(str(e)))

    async def _execute_command(
        self, websocket: WebSocketServerProtocol, cmd: Command
    ) -> None:
        """Execute a command."""
        match cmd.action:
            case "pause":
                self._scheduler.stop()
                await self._broadcast(make_event_message("state_changed", state="paused"))

            case "resume":
                asyncio.create_task(self._run_with_telemetry())
                await self._broadcast(make_event_message("state_changed", state="running"))

            case "reset":
                self._scheduler.reset()
                await self._broadcast(make_event_message("state_changed", state="reset"))

            case "step":
                count = cmd.params.get("count", 1)
                for _ in range(count):
                    self._scheduler.step()
                await self._send_telemetry_frame()

            case "set":
                signal = cmd.params["signal"]
                value = cmd.params["value"]
                self._bus.set(signal, value)
                await websocket.send(make_ack_message("set"))

            case "subscribe":
                signals = cmd.params["signals"]
                self._setup_telemetry(signals)
                await websocket.send(make_ack_message("subscribe"))

            case _:
                await websocket.send(make_error_message(f"Unknown action: {cmd.action}"))

    async def _run_with_telemetry(self) -> None:
        """Run simulation with telemetry streaming."""
        telemetry_interval = 1.0 / self._telemetry_config.rate_hz
        last_telemetry = 0.0

        async def callback(frame: int, time: float) -> None:
            nonlocal last_telemetry
            if time - last_telemetry >= telemetry_interval:
                await self._send_telemetry_frame()
                last_telemetry = time

        await self._scheduler.run(callback=callback)

    async def _send_telemetry_frame(self) -> None:
        """Send binary telemetry to all clients."""
        if not self._encoder or not self._clients:
            return

        values = [self._bus.get(s) for s in self._encoder.signals]
        data = self._encoder.encode(
            self._scheduler.frame,
            self._scheduler.time,
            values,
        )

        await asyncio.gather(
            *[client.send(data) for client in self._clients],
            return_exceptions=True,
        )

    async def _broadcast(self, message: str) -> None:
        """Broadcast text message to all clients."""
        if self._clients:
            await asyncio.gather(
                *[client.send(message) for client in self._clients],
                return_exceptions=True,
            )

    def _setup_telemetry(self, signals: list[str]) -> None:
        """Configure telemetry encoder for specified signals."""
        # Expand wildcards (e.g., "icarus.Vehicle.*")
        expanded = self._expand_signal_patterns(signals)
        self._encoder = TelemetryEncoder(expanded)

    def _expand_signal_patterns(self, patterns: list[str]) -> list[str]:
        """Expand wildcard patterns to concrete signal names."""
        import fnmatch

        all_signals = []
        schema = self._bus.get_schema()
        for module_name, module_data in schema["modules"].items():
            for signal_name in module_data["signals"]:
                all_signals.append(f"{module_name}.{signal_name}")

        result = []
        for pattern in patterns:
            if "*" in pattern:
                result.extend(fnmatch.filter(all_signals, pattern))
            else:
                result.append(pattern)
        return result
```

---

## 7. Configuration

### 7.1 Config Schema

```python
# src/hermes/core/config.py

from pathlib import Path
from pydantic import BaseModel, Field

class ModuleConfig(BaseModel):
    """Configuration for a single module."""
    adapter: str                     # "icarus", "script", "injection"
    config: str | None = None        # Path to module-specific config
    lib_path: str | None = None      # For icarus: path to .so
    script: str | None = None        # For script: path to .py
    signals: list[str] | None = None # For injection: signal names

class WireConfig(BaseModel):
    """Configuration for a signal wire."""
    src: str                         # "module.signal"
    dst: str                         # "module.signal"
    gain: float = 1.0
    offset: float = 0.0

class ExecutionConfig(BaseModel):
    """Execution settings."""
    mode: str = "afap"               # "afap", "realtime", "paused"
    rate_hz: float = 100.0           # Simulation rate
    end_time: float | None = None    # None = run until stopped

class ServerConfig(BaseModel):
    """WebSocket server settings."""
    host: str = "0.0.0.0"
    port: int = 8765
    telemetry_hz: float = 60.0

class HermesConfig(BaseModel):
    """Root configuration."""
    version: str = "0.2"
    modules: dict[str, ModuleConfig]
    wiring: list[WireConfig] = Field(default_factory=list)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "HermesConfig":
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
```

### 7.2 Example Configuration

```yaml
# examples/basic_sim.yaml
version: "0.2"

modules:
  icarus:
    adapter: icarus
    config: ./icarus_config.yaml

execution:
  mode: afap
  rate_hz: 100.0
  end_time: 60.0

server:
  host: "0.0.0.0"
  port: 8765
  telemetry_hz: 60.0
```

---

## 8. CLI Entry Point

```python
# src/hermes/cli/main.py

import asyncio
from pathlib import Path
import click
import structlog

from hermes.core.config import HermesConfig
from hermes.core.signal import SignalBus, Wire
from hermes.core.scheduler import Scheduler, SchedulerConfig, ExecutionMode
from hermes.adapters.icarus import IcarusAdapter
from hermes.adapters.injection import InjectionAdapter
from hermes.server.websocket import HermesServer
from hermes.server.telemetry import TelemetryConfig

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(),
    ],
)
log = structlog.get_logger()

ADAPTER_REGISTRY = {
    "icarus": IcarusAdapter,
    "injection": InjectionAdapter,
}

@click.group()
def cli():
    """Hermes - System Test and Execution Platform"""
    pass

@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
@click.option("--no-server", is_flag=True, help="Run without WebSocket server")
def run(config_path: Path, no_server: bool):
    """Run simulation from configuration file."""
    log.info("Loading configuration", path=config_path)
    config = HermesConfig.from_yaml(config_path)

    # Build signal bus
    bus = SignalBus()

    # Create modules
    for name, mod_config in config.modules.items():
        adapter_cls = ADAPTER_REGISTRY.get(mod_config.adapter)
        if adapter_cls is None:
            raise click.ClickException(f"Unknown adapter: {mod_config.adapter}")

        if mod_config.adapter == "icarus":
            adapter = adapter_cls(name, mod_config.config, mod_config.lib_path)
        elif mod_config.adapter == "injection":
            adapter = adapter_cls(name, mod_config.signals or [])
        else:
            raise click.ClickException(f"Adapter not implemented: {mod_config.adapter}")

        bus.register_module(adapter)
        log.info("Registered module", name=name, adapter=mod_config.adapter)

    # Add wiring
    for wire_config in config.wiring:
        src_module, src_signal = wire_config.src.rsplit(".", 1)
        dst_module, dst_signal = wire_config.dst.rsplit(".", 1)
        bus.add_wire(Wire(
            src_module=src_module,
            src_signal=src_signal,
            dst_module=dst_module,
            dst_signal=dst_signal,
            gain=wire_config.gain,
            offset=wire_config.offset,
        ))

    # Create scheduler
    scheduler_config = SchedulerConfig(
        dt=1.0 / config.execution.rate_hz,
        mode=ExecutionMode(config.execution.mode),
        end_time=config.execution.end_time,
    )
    scheduler = Scheduler(bus, scheduler_config)

    # Stage
    log.info("Staging simulation")
    scheduler.stage()

    if no_server:
        # Run without server
        log.info("Running simulation (no server)")
        asyncio.run(scheduler.run())
    else:
        # Run with WebSocket server
        telemetry_config = TelemetryConfig(rate_hz=config.server.telemetry_hz)
        server = HermesServer(
            bus, scheduler,
            host=config.server.host,
            port=config.server.port,
            telemetry_config=telemetry_config,
        )

        log.info("Starting server", host=config.server.host, port=config.server.port)
        asyncio.run(server.start())

@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
def schema(config_path: Path):
    """Print schema JSON for a configuration."""
    import json
    config = HermesConfig.from_yaml(config_path)

    bus = SignalBus()
    for name, mod_config in config.modules.items():
        # ... same adapter creation as above ...
        pass

    print(json.dumps(bus.get_schema(), indent=2))

def main():
    cli()

if __name__ == "__main__":
    main()
```

---

## 9. Implementation Phases

### Phase 1: Foundation

**Goal:** Minimal working system with Icarus adapter

| Task | Description | Deliverable |
|------|-------------|-------------|
| 1.1 | Project setup | `pyproject.toml`, dev dependencies, ruff/mypy config |
| 1.2 | Core abstractions | `ModuleAdapter`, `SignalDescriptor`, `SignalBus` |
| 1.3 | Icarus adapter | CFFI bindings, schema parsing, signal get/set |
| 1.4 | Synchronous scheduler | Basic step loop, time tracking |
| 1.5 | CLI skeleton | `hermes run config.yaml --no-server` |
| 1.6 | Tests | Unit tests for bus, scheduler, adapter |

**Exit Criteria:** `hermes run` steps Icarus and prints telemetry to console.

### Phase 2: WebSocket Server

**Goal:** Daedalus can connect and receive telemetry

| Task | Description | Deliverable |
|------|-------------|-------------|
| 2.1 | Protocol messages | JSON schema, command, event types |
| 2.2 | Binary telemetry | Encoder/decoder with header + payload |
| 2.3 | WebSocket server | asyncio server, client management |
| 2.4 | Command handling | pause, resume, reset, step, set |
| 2.5 | Telemetry streaming | Decimation, subscription |
| 2.6 | Integration test | Python client connecting and receiving |

**Exit Criteria:** External WebSocket client receives binary telemetry at 60 Hz.

### Phase 3: Multi-Module & Wiring

**Goal:** Multiple modules with signal routing

| Task | Description | Deliverable |
|------|-------------|-------------|
| 3.1 | Injection adapter | Simple value store for test signals |
| 3.2 | Wire configuration | YAML parsing, validation |
| 3.3 | Signal routing | `bus.route()` with gain/offset |
| 3.4 | Qualified names | `module.signal` parsing throughout |
| 3.5 | Schema generation | Combined schema from all modules |
| 3.6 | Multi-module test | Icarus + injection with wiring |

**Exit Criteria:** Injection adapter can override Icarus inputs via wiring.

### Phase 4: Polish & Documentation

**Goal:** Production-ready for Daedalus development

| Task | Description | Deliverable |
|------|-------------|-------------|
| 4.1 | Error handling | Proper exceptions, logging |
| 4.2 | Configuration validation | Pydantic schema, helpful errors |
| 4.3 | Protocol documentation | `docs/protocol.md` with examples |
| 4.4 | Example configurations | `examples/` directory |
| 4.5 | CI setup | GitHub Actions for tests, lint, type check |

**Exit Criteria:** Hermes is documented and tested enough for Daedalus to start development.

---

## 10. Testing Strategy

### Unit Tests

```python
# tests/test_signal_bus.py

def test_register_module():
    bus = SignalBus()
    adapter = MockAdapter("test")
    bus.register_module(adapter)
    assert "test" in bus._modules

def test_wire_routing():
    bus = SignalBus()
    src = MockAdapter("src", signals={"out": 42.0})
    dst = MockAdapter("dst", signals={"in": 0.0})
    bus.register_module(src)
    bus.register_module(dst)
    bus.add_wire(Wire("src", "out", "dst", "in"))

    bus.route()
    assert dst.get("in") == 42.0

def test_wire_with_gain():
    # ... test gain and offset application
```

### Integration Tests

```python
# tests/integration/test_full_loop.py

@pytest.mark.asyncio
async def test_icarus_step_loop():
    """Full integration: load Icarus, step, verify state changes."""
    adapter = IcarusAdapter("icarus", "tests/fixtures/ball_drop.yaml")
    bus = SignalBus()
    bus.register_module(adapter)

    scheduler = Scheduler(bus, SchedulerConfig(dt=0.01))
    scheduler.stage()

    # Initial altitude
    z0 = bus.get("icarus.Ball.position.z")

    # Step 100 times (1 second)
    for _ in range(100):
        scheduler.step()

    # Ball should have fallen
    z1 = bus.get("icarus.Ball.position.z")
    assert z1 < z0
```

### WebSocket Protocol Tests

```python
# tests/test_protocol.py

@pytest.mark.asyncio
async def test_client_receives_schema():
    """Client receives schema on connect."""
    async with websockets.connect("ws://localhost:8765") as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        assert data["type"] == "schema"
        assert "modules" in data
```

---

## 11. Nix Development Workflow

Hermes uses Nix flakes for reproducible development environments.

### Setup

```bash
cd hermes

# Enter development shell (includes Icarus bindings)
nix develop

# Or with direnv
echo "use flake" > .envrc
direnv allow
```

### Flake Structure

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    icarus.url = "path:/home/tanged/sources/icarus";  # Local dev
    # icarus.url = "github:tanged123/icarus";         # CI/prod
  };

  outputs = { self, nixpkgs, icarus, ... }: {
    devShells.default = mkShell {
      packages = [ pythonEnv icarusPackage ruff ];
      shellHook = ''
        export PYTHONPATH="${icarusPackage}/lib/python3.12/site-packages:$PYTHONPATH"
      '';
    };
  };
}
```

### Building

```bash
# Build Hermes package
nix build

# Run tests
nix develop -c pytest

# Format code
nix fmt
```

---

## 12. Open Questions for Implementation

1. **Signal type handling:** Should we support Vec3/Quat in the protocol, or flatten to scalars?
   - *Recommendation:* Flatten for Phase 1, add structured types later.

2. **Module ordering:** Should we implement topological sort for step order, or trust config order?
   - *Recommendation:* Config order for Phase 1, topo sort in Phase 3.

3. **Async vs sync step:** Should `module.step()` be async-capable for I/O-bound adapters?
   - *Recommendation:* Keep sync for Phase 1, revisit for ProcessAdapter.

4. **Recording:** Should Hermes handle recording, or delegate to Icarus?
   - *Recommendation:* Icarus records its own data; Hermes records cross-module signals separately.
