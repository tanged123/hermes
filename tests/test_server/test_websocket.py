"""Tests for WebSocket server."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import websockets

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.server.telemetry import TelemetryEncoder
from hermes.server.websocket import (
    ClientState,
    HermesServer,
    ServerConfig,
)


@pytest.fixture
def shm_with_signals() -> SharedMemoryManager:
    """Create shared memory with test signals."""
    shm_name = f"/hermes_ws_test_{uuid.uuid4().hex[:8]}"
    signals = [
        SignalDescriptor(name="sensor.x", type=SignalType.F64),
        SignalDescriptor(name="sensor.y", type=SignalType.F64),
        SignalDescriptor(name="controller.output", type=SignalType.F64),
    ]

    shm = SharedMemoryManager(shm_name)
    shm.create(signals)

    yield shm

    shm.destroy()


@pytest.fixture
def server_config() -> ServerConfig:
    """Create test server configuration with random port."""
    return ServerConfig(host="127.0.0.1", port=0, telemetry_hz=60.0)


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = ServerConfig()

        assert config.host == "0.0.0.0"
        assert config.port == 8765
        assert config.telemetry_hz == 60.0

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = ServerConfig(host="localhost", port=9999, telemetry_hz=30.0)

        assert config.host == "localhost"
        assert config.port == 9999
        assert config.telemetry_hz == 30.0


class TestClientState:
    """Tests for ClientState dataclass."""

    def test_default_values(self) -> None:
        """Should have correct defaults."""
        # Create a mock websocket
        from unittest.mock import MagicMock

        mock_ws = MagicMock()
        state = ClientState(ws=mock_ws)

        assert state.ws is mock_ws
        assert state.encoder is None
        assert state.remote == ""


class TestHermesServerInit:
    """Tests for HermesServer initialization."""

    def test_create_without_scheduler(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should create server without scheduler."""
        server = HermesServer(shm_with_signals)

        assert server.client_count == 0
        assert not server.is_running

    def test_create_with_config(
        self, shm_with_signals: SharedMemoryManager, server_config: ServerConfig
    ) -> None:
        """Should create server with custom config."""
        server = HermesServer(shm_with_signals, config=server_config)

        assert server.client_count == 0
        assert server._config == server_config


class TestHermesServerPatternExpansion:
    """Tests for signal pattern expansion."""

    def test_expand_wildcard_all(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should expand '*' to all signals."""
        server = HermesServer(shm_with_signals)
        expanded = server._expand_signal_patterns(["*"])

        assert "sensor.x" in expanded
        assert "sensor.y" in expanded
        assert "controller.output" in expanded
        assert len(expanded) == 3

    def test_expand_module_wildcard(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should expand 'module.*' to module signals."""
        server = HermesServer(shm_with_signals)
        expanded = server._expand_signal_patterns(["sensor.*"])

        assert "sensor.x" in expanded
        assert "sensor.y" in expanded
        assert "controller.output" not in expanded
        assert len(expanded) == 2

    def test_expand_exact_match(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should match exact signal names."""
        server = HermesServer(shm_with_signals)
        expanded = server._expand_signal_patterns(["sensor.x"])

        assert expanded == ["sensor.x"]

    def test_expand_unknown_exact_ignored(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should ignore unknown exact signal names."""
        server = HermesServer(shm_with_signals)
        expanded = server._expand_signal_patterns(["nonexistent.signal"])

        assert expanded == []

    def test_expand_removes_duplicates(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should remove duplicates while preserving order."""
        server = HermesServer(shm_with_signals)
        expanded = server._expand_signal_patterns(["sensor.x", "*", "sensor.x"])

        # sensor.x should appear only once
        assert expanded.count("sensor.x") == 1
        # First occurrence should be preserved (sensor.x before others from *)
        assert expanded[0] == "sensor.x"

    def test_expand_multiple_patterns(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should handle multiple patterns."""
        server = HermesServer(shm_with_signals)
        expanded = server._expand_signal_patterns(["sensor.*", "controller.*"])

        assert "sensor.x" in expanded
        assert "sensor.y" in expanded
        assert "controller.output" in expanded
        assert len(expanded) == 3


class TestHermesServerConnection:
    """Tests for server connection handling."""

    @pytest.fixture
    async def running_server(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0)  # port=0 for random
        server = HermesServer(shm_with_signals, config=config)

        await server.start_background()

        yield server

        await server.stop()

    @pytest.mark.asyncio
    async def test_server_starts_and_stops(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should start and stop cleanly."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)

        await server.start_background()
        assert server.is_running

        await server.stop()
        assert not server.is_running

    @pytest.mark.asyncio
    async def test_client_connect_receives_schema(self, running_server: HermesServer) -> None:
        """Client should receive schema on connect."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # First message should be schema
            message = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(message)

            assert data["type"] == "schema"
            assert "modules" in data
            assert "sensor" in data["modules"]
            assert "controller" in data["modules"]

    @pytest.mark.asyncio
    async def test_client_count_tracks_connections(self, running_server: HermesServer) -> None:
        """Should track connected clients."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        assert running_server.client_count == 0

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Consume schema
            await asyncio.sleep(0.05)  # Allow server to process
            assert running_server.client_count == 1

        # Wait for disconnect to process
        await asyncio.sleep(0.1)
        assert running_server.client_count == 0

    @pytest.mark.asyncio
    async def test_multiple_clients(self, running_server: HermesServer) -> None:
        """Should handle multiple clients."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws1:
            await asyncio.wait_for(ws1.recv(), timeout=2.0)
            await asyncio.sleep(0.05)
            assert running_server.client_count == 1

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws2:
                await asyncio.wait_for(ws2.recv(), timeout=2.0)
                await asyncio.sleep(0.05)
                assert running_server.client_count == 2

            await asyncio.sleep(0.1)
            assert running_server.client_count == 1

        await asyncio.sleep(0.1)
        assert running_server.client_count == 0


class TestHermesServerSubscribe:
    """Tests for subscribe command."""

    @pytest.fixture
    async def running_server(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_subscribe_all_signals(self, running_server: HermesServer) -> None:
        """Should subscribe to all signals with wildcard."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Subscribe to all
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["*"]}}))
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)

            assert data["type"] == "ack"
            assert data["action"] == "subscribe"
            assert data["count"] == 3

    @pytest.mark.asyncio
    async def test_subscribe_module_wildcard(self, running_server: HermesServer) -> None:
        """Should subscribe to module signals with wildcard."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["sensor.*"]}}))
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)

            assert data["type"] == "ack"
            assert data["count"] == 2
            assert "sensor.x" in data["signals"]
            assert "sensor.y" in data["signals"]


class TestHermesServerSetCommand:
    """Tests for set command."""

    @pytest.fixture
    async def running_server(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_set_signal_value(
        self, running_server: HermesServer, shm_with_signals: SharedMemoryManager
    ) -> None:
        """Should set signal value in shared memory."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            await ws.send(
                json.dumps(
                    {
                        "action": "set",
                        "params": {"signal": "sensor.x", "value": 42.5},
                    }
                )
            )
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)

            assert data["type"] == "ack"
            assert data["action"] == "set"

            # Verify value in shared memory
            assert shm_with_signals.get_signal("sensor.x") == pytest.approx(42.5)

    @pytest.mark.asyncio
    async def test_set_unknown_signal_error(self, running_server: HermesServer) -> None:
        """Should return error for unknown signal."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            await ws.send(
                json.dumps(
                    {
                        "action": "set",
                        "params": {"signal": "nonexistent", "value": 1.0},
                    }
                )
            )
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)

            assert data["type"] == "error"
            assert "Unknown signal" in data["message"]


class TestHermesServerTelemetry:
    """Tests for telemetry broadcasting."""

    @pytest.fixture
    async def running_server(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0, telemetry_hz=100.0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_broadcast_telemetry_to_subscribed(
        self, running_server: HermesServer, shm_with_signals: SharedMemoryManager
    ) -> None:
        """Should broadcast telemetry to subscribed clients."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        # Set up test data
        shm_with_signals.set_frame(42)
        shm_with_signals.set_time_ns(1_000_000_000)
        shm_with_signals.set_signal("sensor.x", 10.0)
        shm_with_signals.set_signal("sensor.y", 20.0)

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Subscribe
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["sensor.*"]}}))
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Ack

            # Trigger broadcast
            await running_server.broadcast_telemetry()

            # Receive binary telemetry
            frame_data = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert isinstance(frame_data, bytes)

            # Decode and verify
            frame, time, values = TelemetryEncoder.decode(frame_data)
            assert frame == 42
            assert time == pytest.approx(1.0)
            assert len(values) == 2

    @pytest.mark.asyncio
    async def test_unsubscribed_client_no_telemetry(self, running_server: HermesServer) -> None:
        """Clients without subscription should not receive telemetry."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Don't subscribe - trigger broadcast
            await running_server.broadcast_telemetry()

            # Should not receive anything (timeout expected)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), timeout=0.2)


class TestHermesServerInvalidCommands:
    """Tests for invalid command handling."""

    @pytest.fixture
    async def running_server(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_invalid_json_error(self, running_server: HermesServer) -> None:
        """Should return error for invalid JSON."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            await ws.send("not valid json")
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)

            assert data["type"] == "error"
            assert "Invalid JSON" in data["message"]

    @pytest.mark.asyncio
    async def test_unknown_action_error(self, running_server: HermesServer) -> None:
        """Should return error for unknown action."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            await ws.send(json.dumps({"action": "unknown_action"}))
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)

            assert data["type"] == "error"
            assert "Unknown action" in data["message"]


class TestHermesServerSignalsWithoutDots:
    """Tests for signals without module.signal format."""

    @pytest.fixture
    def shm_with_simple_signals(self) -> SharedMemoryManager:
        """Create shared memory with signals that have no dots."""
        shm_name = f"/hermes_simple_{uuid.uuid4().hex[:8]}"
        signals = [
            SignalDescriptor(name="temperature", type=SignalType.F64),
            SignalDescriptor(name="pressure", type=SignalType.F64),
            SignalDescriptor(name="sensor.x", type=SignalType.F64),  # Mixed: with dot
        ]

        shm = SharedMemoryManager(shm_name)
        shm.create(signals)

        yield shm

        shm.destroy()

    @pytest.mark.asyncio
    async def test_schema_groups_dotless_signals_under_default(
        self, shm_with_simple_signals: SharedMemoryManager
    ) -> None:
        """Signals without dots should appear under _default module."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_simple_signals, config=config)
        await server.start_background()

        try:
            assert server._server is not None
            port = server._server.sockets[0].getsockname()[1]

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                schema_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                schema = json.loads(schema_msg)

                assert schema["type"] == "schema"
                modules = schema["modules"]

                # Dotless signals go to _default
                assert "_default" in modules
                default_signals = [s["name"] for s in modules["_default"]["signals"]]
                assert "temperature" in default_signals
                assert "pressure" in default_signals

                # Dotted signal goes to its module
                assert "sensor" in modules
                sensor_signals = [s["name"] for s in modules["sensor"]["signals"]]
                assert "x" in sensor_signals

        finally:
            await server.stop()
