"""End-to-end WebSocket integration tests.

These tests verify the complete WebSocket communication flow:
1. Server startup with real scheduler
2. Client connection and schema reception
3. Signal subscription
4. Telemetry streaming
5. Control commands
6. Clean shutdown
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid

import pytest
import websockets

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.server import HermesServer, ServerConfig
from hermes.server.protocol import EventType
from hermes.server.telemetry import TelemetryEncoder


@pytest.fixture
def shm_with_signals() -> SharedMemoryManager:
    """Create shared memory with test signals."""
    shm_name = f"/hermes_e2e_{uuid.uuid4().hex[:8]}"
    signals = [
        SignalDescriptor(name="sim.time", type=SignalType.F64),
        SignalDescriptor(name="sim.frame", type=SignalType.F64),
        SignalDescriptor(name="sensor.temperature", type=SignalType.F64),
        SignalDescriptor(name="sensor.pressure", type=SignalType.F64),
        SignalDescriptor(name="controller.output", type=SignalType.F64),
    ]

    shm = SharedMemoryManager(shm_name)
    shm.create(signals)

    # Initialize with some values
    shm.set_frame(0)
    shm.set_time_ns(0)
    shm.set_signal("sim.time", 0.0)
    shm.set_signal("sim.frame", 0.0)
    shm.set_signal("sensor.temperature", 25.0)
    shm.set_signal("sensor.pressure", 101325.0)
    shm.set_signal("controller.output", 0.0)

    yield shm

    shm.destroy()


@pytest.fixture
def mock_scheduler() -> MockScheduler:
    """Create a mock scheduler for testing."""
    return MockScheduler()


class MockScheduler:
    """Mock scheduler for testing control commands."""

    def __init__(self) -> None:
        self.paused = False
        self.frame = 0
        self.time_ns = 0
        self.reset_called = False
        self.stepped_frames = 0

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def reset(self) -> None:
        self.reset_called = True
        self.frame = 0
        self.time_ns = 0

    def step(self, count: int) -> None:
        self.stepped_frames += count
        self.frame += count
        self.time_ns += count * 10_000_000  # 10ms per frame

    def stop(self) -> None:
        pass


class TestWebSocketEndToEnd:
    """End-to-end tests for WebSocket server."""

    @pytest.fixture
    async def running_server(
        self, shm_with_signals: SharedMemoryManager, mock_scheduler: MockScheduler
    ) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0, telemetry_hz=100.0)
        server = HermesServer(shm_with_signals, mock_scheduler, config)
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_full_workflow(
        self,
        running_server: HermesServer,
        shm_with_signals: SharedMemoryManager,
        mock_scheduler: MockScheduler,
    ) -> None:
        """Test complete client workflow: connect, subscribe, telemetry, control."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # 1. Receive schema on connect
            schema_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            schema = json.loads(schema_msg)

            assert schema["type"] == "schema"
            assert "modules" in schema
            assert "sim" in schema["modules"]
            assert "sensor" in schema["modules"]
            assert "controller" in schema["modules"]

            # 2. Subscribe to sensor signals
            await ws.send(
                json.dumps(
                    {
                        "action": "subscribe",
                        "params": {"signals": ["sensor.*"]},
                    }
                )
            )
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            assert ack["type"] == "ack"
            assert ack["action"] == "subscribe"
            assert ack["count"] == 2

            # 3. Resume simulation
            await ws.send(json.dumps({"action": "resume"}))

            # We receive both ack and event, order may vary
            msg1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            msg2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            messages = {msg1["type"]: msg1, msg2["type"]: msg2}
            assert "ack" in messages
            assert "event" in messages
            assert messages["ack"]["action"] == "resume"
            assert messages["event"]["event"] == "running"
            assert not mock_scheduler.paused

            # 4. Update shared memory and broadcast telemetry
            shm_with_signals.set_frame(42)
            shm_with_signals.set_time_ns(420_000_000)  # 420ms
            shm_with_signals.set_signal("sensor.temperature", 30.0)
            shm_with_signals.set_signal("sensor.pressure", 102000.0)

            await running_server.broadcast_telemetry()

            # 5. Receive and verify binary telemetry
            frame_data = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert isinstance(frame_data, bytes)

            frame, time, values = TelemetryEncoder.decode(frame_data)
            assert frame == 42
            assert time == pytest.approx(0.42)
            assert len(values) == 2
            # Values should match subscription order
            assert values[0] == pytest.approx(30.0)  # temperature
            assert values[1] == pytest.approx(102000.0)  # pressure

            # 6. Step simulation
            await ws.send(json.dumps({"action": "step", "params": {"count": 5}}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            assert ack["type"] == "ack"
            assert ack["action"] == "step"
            assert ack["count"] == 5
            assert mock_scheduler.stepped_frames == 5

            # 7. Pause simulation
            await ws.send(json.dumps({"action": "pause"}))

            # We receive both ack and event, order may vary
            msg1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            msg2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            messages = {msg1["type"]: msg1, msg2["type"]: msg2}
            assert "ack" in messages
            assert "event" in messages
            assert messages["ack"]["action"] == "pause"
            assert messages["event"]["event"] == "paused"
            assert mock_scheduler.paused

            # 8. Set signal value
            await ws.send(
                json.dumps(
                    {
                        "action": "set",
                        "params": {"signal": "controller.output", "value": 75.0},
                    }
                )
            )
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            assert ack["type"] == "ack"
            assert ack["action"] == "set"
            assert shm_with_signals.get_signal("controller.output") == pytest.approx(75.0)

            # 9. Reset simulation
            await ws.send(json.dumps({"action": "reset"}))

            # We receive both ack and event, order may vary
            msg1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            msg2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            messages = {msg1["type"]: msg1, msg2["type"]: msg2}
            assert "ack" in messages
            assert "event" in messages
            assert messages["ack"]["action"] == "reset"
            assert messages["event"]["event"] == "reset"
            assert mock_scheduler.reset_called

        # Client disconnected - verify server is still running
        await asyncio.sleep(0.1)  # Allow disconnect to process
        assert running_server.client_count == 0
        assert running_server.is_running

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, running_server: HermesServer) -> None:
        """Multiple clients should each receive telemetry for their subscription."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws1:
            await asyncio.wait_for(ws1.recv(), timeout=2.0)  # Schema

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws2:
                await asyncio.wait_for(ws2.recv(), timeout=2.0)  # Schema

                # Client 1 subscribes to sensor signals
                await ws1.send(
                    json.dumps(
                        {
                            "action": "subscribe",
                            "params": {"signals": ["sensor.*"]},
                        }
                    )
                )
                ack1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=2.0))
                assert ack1["count"] == 2

                # Client 2 subscribes to all signals
                await ws2.send(
                    json.dumps(
                        {
                            "action": "subscribe",
                            "params": {"signals": ["*"]},
                        }
                    )
                )
                ack2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=2.0))
                assert ack2["count"] == 5

                # Broadcast telemetry
                await running_server.broadcast_telemetry()

                # Each client should receive their own telemetry frame
                frame1 = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                frame2 = await asyncio.wait_for(ws2.recv(), timeout=2.0)

                assert isinstance(frame1, bytes)
                assert isinstance(frame2, bytes)

                _, _, values1 = TelemetryEncoder.decode(frame1)
                _, _, values2 = TelemetryEncoder.decode(frame2)

                assert len(values1) == 2  # sensor.* only
                assert len(values2) == 5  # all signals

    @pytest.mark.asyncio
    async def test_error_handling(self, running_server: HermesServer) -> None:
        """Server should handle errors gracefully."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Send invalid JSON
            await ws.send("not json")
            error = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert error["type"] == "error"
            assert "Invalid JSON" in error["message"]

            # Send unknown command
            await ws.send(json.dumps({"action": "fly_to_moon"}))
            error = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert error["type"] == "error"
            assert "Unknown action" in error["message"]

            # Send set with unknown signal
            await ws.send(
                json.dumps(
                    {
                        "action": "set",
                        "params": {"signal": "nonexistent.signal", "value": 1.0},
                    }
                )
            )
            error = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert error["type"] == "error"
            assert "Unknown signal" in error["message"]

            # Connection should still work after errors
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": []}}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert ack["type"] == "ack"

    @pytest.mark.asyncio
    async def test_telemetry_loop(
        self, shm_with_signals: SharedMemoryManager, mock_scheduler: MockScheduler
    ) -> None:
        """Telemetry loop should broadcast at configured rate."""
        config = ServerConfig(host="127.0.0.1", port=0, telemetry_hz=50.0)  # 20ms interval
        server = HermesServer(shm_with_signals, mock_scheduler, config)

        try:
            await server.start_background()
            assert server._server is not None
            port = server._server.sockets[0].getsockname()[1]

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

                # Subscribe
                await ws.send(
                    json.dumps({"action": "subscribe", "params": {"signals": ["sensor.*"]}})
                )
                await asyncio.wait_for(ws.recv(), timeout=2.0)  # Ack

                # Start telemetry loop
                task = server.start_telemetry_loop()

                # Receive multiple frames
                frames_received = 0
                try:
                    for _ in range(5):
                        frame_data = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        assert isinstance(frame_data, bytes)
                        frames_received += 1
                except TimeoutError:
                    pass

                # Should have received some frames
                assert frames_received >= 2

                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_client_disconnect_cleanup(self, running_server: HermesServer) -> None:
        """Server should clean up after client disconnects."""
        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        # Connect and disconnect multiple times
        for _ in range(3):
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema
                await asyncio.sleep(0.05)
                assert running_server.client_count == 1

            await asyncio.sleep(0.1)
            assert running_server.client_count == 0

        # Server should still be running
        assert running_server.is_running


class TestTelemetryBinaryFormat:
    """Tests for binary telemetry format verification."""

    @pytest.fixture
    async def running_server(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server for testing."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_telemetry_frame_format(
        self, running_server: HermesServer, shm_with_signals: SharedMemoryManager
    ) -> None:
        """Binary telemetry frames should match documented format."""
        import struct

        assert running_server._server is not None
        port = running_server._server.sockets[0].getsockname()[1]

        # Set known values
        shm_with_signals.set_frame(123)
        shm_with_signals.set_time_ns(4_500_000_000)  # 4.5 seconds
        shm_with_signals.set_signal("sensor.temperature", 100.0)
        shm_with_signals.set_signal("sensor.pressure", 200.0)

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Subscribe to 2 signals
            await ws.send(
                json.dumps(
                    {
                        "action": "subscribe",
                        "params": {"signals": ["sensor.temperature", "sensor.pressure"]},
                    }
                )
            )
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Ack

            # Trigger telemetry
            await running_server.broadcast_telemetry()
            frame_data = await asyncio.wait_for(ws.recv(), timeout=2.0)

            # Verify header (24 bytes)
            assert len(frame_data) == 24 + 2 * 8  # Header + 2 f64 values

            magic, frame, time, count = struct.unpack("<I Q d I", frame_data[:24])

            assert magic == 0x48455254  # "HERT"
            assert frame == 123
            assert time == pytest.approx(4.5)
            assert count == 2

            # Verify payload
            values = struct.unpack("<2d", frame_data[24:])
            assert values[0] == pytest.approx(100.0)
            assert values[1] == pytest.approx(200.0)


class TestTelemetryInterleaving:
    """Tests for message interleaving during active telemetry streaming."""

    @pytest.fixture
    async def server_with_telemetry(
        self, shm_with_signals: SharedMemoryManager, mock_scheduler: MockScheduler
    ) -> HermesServer:
        """Start a server with telemetry loop running."""
        config = ServerConfig(host="127.0.0.1", port=0, telemetry_hz=100.0)
        server = HermesServer(shm_with_signals, mock_scheduler, config)
        await server.start_background()
        server.start_telemetry_loop()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_json_commands_during_telemetry_stream(
        self,
        server_with_telemetry: HermesServer,
    ) -> None:
        """JSON commands should work correctly while telemetry is streaming."""
        assert server_with_telemetry._server is not None
        port = server_with_telemetry._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # Receive schema
            schema = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert schema["type"] == "schema"

            # Subscribe to all signals - this starts telemetry flow
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["*"]}}))

            # Collect messages, handling both binary and JSON
            ack_received = False
            telemetry_count = 0
            timeout = 1.0
            start = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start < timeout:
                try:
                    data = await asyncio.wait_for(ws.recv(), timeout=0.1)
                    if isinstance(data, bytes):
                        telemetry_count += 1
                    else:
                        msg = json.loads(data)
                        if msg["type"] == "ack" and msg["action"] == "subscribe":
                            ack_received = True
                            break
                except TimeoutError:
                    continue

            assert ack_received, "Subscribe ack should be received despite telemetry"
            # Telemetry may or may not have arrived yet depending on timing

    @pytest.mark.asyncio
    async def test_resume_command_with_active_telemetry(
        self,
        server_with_telemetry: HermesServer,
        mock_scheduler: MockScheduler,
    ) -> None:
        """Resume command should return ack+event even with telemetry streaming."""
        assert server_with_telemetry._server is not None
        port = server_with_telemetry._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Subscribe first
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["*"]}}))

            # Wait for ack, skipping any binary frames
            while True:
                data = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if isinstance(data, str):
                    ack = json.loads(data)
                    assert ack["type"] == "ack"
                    break

            # Now resume - we should get both ack and event despite telemetry
            await ws.send(json.dumps({"action": "resume"}))

            # Collect JSON messages (ack and event), skipping binary
            json_messages: dict[str, dict] = {}
            attempts = 0
            max_attempts = 20  # Allow for interleaved telemetry

            while len(json_messages) < 2 and attempts < max_attempts:
                data = await asyncio.wait_for(ws.recv(), timeout=0.5)
                if isinstance(data, str):
                    msg = json.loads(data)
                    json_messages[msg["type"]] = msg
                attempts += 1

            assert "ack" in json_messages, "Should receive ack"
            assert "event" in json_messages, "Should receive event"
            assert json_messages["ack"]["action"] == "resume"
            assert json_messages["event"]["event"] == "running"
            assert not mock_scheduler.paused

    @pytest.mark.asyncio
    async def test_multiple_commands_during_telemetry(
        self,
        server_with_telemetry: HermesServer,
    ) -> None:
        """Multiple commands should work correctly with interleaved telemetry."""
        assert server_with_telemetry._server is not None
        port = server_with_telemetry._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Subscribe
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["*"]}}))

            # Helper to get next JSON message
            async def get_json_message() -> dict:
                while True:
                    data = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    if isinstance(data, str):
                        return json.loads(data)

            ack = await get_json_message()
            assert ack["action"] == "subscribe"

            # Send multiple set commands rapidly
            for i in range(5):
                await ws.send(
                    json.dumps(
                        {
                            "action": "set",
                            "params": {"signal": "sensor.temperature", "value": float(i)},
                        }
                    )
                )

            # All acks should arrive (interspersed with telemetry)
            acks_received = 0
            for _ in range(50):  # Allow for lots of telemetry
                try:
                    data = await asyncio.wait_for(ws.recv(), timeout=0.2)
                    if isinstance(data, str):
                        msg = json.loads(data)
                        if msg["type"] == "ack" and msg["action"] == "set":
                            acks_received += 1
                            if acks_received >= 5:
                                break
                except TimeoutError:
                    break

            assert acks_received == 5, f"Should receive all 5 set acks, got {acks_received}"


class TestEdgeCases:
    """Tests for edge cases and error paths."""

    @pytest.fixture
    async def server_no_scheduler(self, shm_with_signals: SharedMemoryManager) -> HermesServer:
        """Start a server without scheduler."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)  # No scheduler
        await server.start_background()
        yield server
        await server.stop()

    @pytest.mark.asyncio
    async def test_control_commands_without_scheduler(
        self, server_no_scheduler: HermesServer
    ) -> None:
        """Control commands should return error when no scheduler attached."""
        assert server_no_scheduler._server is not None
        port = server_no_scheduler._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Test all control commands
            for action in ["pause", "resume", "reset", "step"]:
                params = {"count": 1} if action == "step" else {}
                await ws.send(json.dumps({"action": action, "params": params}))
                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

                assert response["type"] == "error", f"{action} should return error"
                assert "No scheduler" in response["message"]

    @pytest.mark.asyncio
    async def test_set_invalid_value_type(self, server_no_scheduler: HermesServer) -> None:
        """Set command with invalid value type should return error."""
        assert server_no_scheduler._server is not None
        port = server_no_scheduler._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Send set with non-numeric value
            await ws.send(
                json.dumps(
                    {
                        "action": "set",
                        "params": {"signal": "sensor.temperature", "value": "not_a_number"},
                    }
                )
            )
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))

            assert response["type"] == "error"
            assert "Invalid value" in response["message"]

    @pytest.mark.asyncio
    async def test_binary_message_from_client(self, server_no_scheduler: HermesServer) -> None:
        """Server should handle binary messages from client gracefully."""
        assert server_no_scheduler._server is not None
        port = server_no_scheduler._server.sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Send binary data (not expected from client)
            await ws.send(b"\x00\x01\x02\x03")

            # Connection should still work - send a valid command
            await ws.send(json.dumps({"action": "subscribe", "params": {"signals": []}}))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert response["type"] == "ack"

    @pytest.mark.asyncio
    async def test_broadcast_telemetry_no_clients(
        self, shm_with_signals: SharedMemoryManager
    ) -> None:
        """Broadcast telemetry with no clients should not error."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()

        try:
            # No clients connected - should not raise
            await server.broadcast_telemetry()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_broadcast_event_no_clients(
        self, shm_with_signals: SharedMemoryManager, mock_scheduler: MockScheduler
    ) -> None:
        """Broadcast event with no clients should not error."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, mock_scheduler, config)
        await server.start_background()

        try:
            # No clients - calling pause should broadcast event without error
            mock_scheduler.paused = False

            # Connect briefly then disconnect
            port = server._server.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

            # Wait for disconnect to process
            await asyncio.sleep(0.1)
            assert server.client_count == 0

            # Now trigger event broadcast with no clients - should not error
            await server._broadcast_event(EventType.PAUSED)

        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_telemetry_send_failure_handled(
        self, shm_with_signals: SharedMemoryManager
    ) -> None:
        """Telemetry send failure should be logged but not crash server."""
        config = ServerConfig(host="127.0.0.1", port=0)
        server = HermesServer(shm_with_signals, config=config)
        await server.start_background()

        try:
            assert server._server is not None
            port = server._server.sockets[0].getsockname()[1]

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)  # Schema

                # Subscribe
                await ws.send(json.dumps({"action": "subscribe", "params": {"signals": ["*"]}}))
                await asyncio.wait_for(ws.recv(), timeout=2.0)  # Ack

                # Force close the websocket from client side
                await ws.close()

            # Give server time to process disconnect
            await asyncio.sleep(0.1)

            # Server should still be running and not crash when broadcasting
            # to a client that was just connected
            await server.broadcast_telemetry()
            assert server.is_running

        finally:
            await server.stop()
