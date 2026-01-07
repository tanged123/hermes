"""Tests for the scripting API."""

from __future__ import annotations

import uuid

import pytest

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.scripting.api import SimulationAPI


@pytest.fixture
def shm_name() -> str:
    """Generate unique shared memory name for test isolation."""
    return f"/hermes_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_signals() -> list[SignalDescriptor]:
    """Create test signal descriptors."""
    return [
        SignalDescriptor(name="position.x", type=SignalType.F64),
        SignalDescriptor(name="position.y", type=SignalType.F64),
        SignalDescriptor(name="velocity", type=SignalType.F64),
    ]


@pytest.fixture
def setup_shm(shm_name: str, test_signals: list[SignalDescriptor]) -> SharedMemoryManager:
    """Create shared memory for testing."""
    shm = SharedMemoryManager(shm_name)
    shm.create(test_signals)
    yield shm
    shm.destroy()


class TestSimulationAPI:
    """Tests for SimulationAPI."""

    def test_context_manager(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should work as context manager."""
        _ = setup_shm  # Fixture needed to create shared memory
        with SimulationAPI(shm_name) as api:
            assert api is not None

    def test_get_set_signal(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should get and set signal values."""
        _ = setup_shm  # Fixture needed to create shared memory
        with SimulationAPI(shm_name) as api:
            api.set("position.x", 10.0)
            api.set("position.y", 20.0)

            assert api.get("position.x") == 10.0
            assert api.get("position.y") == 20.0

    def test_get_frame_time(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should get frame and time from header."""
        setup_shm.set_frame(42)
        setup_shm.set_time(1.5)

        with SimulationAPI(shm_name) as api:
            assert api.get_frame() == 42
            assert api.get_time() == 1.5

    def test_inject_multiple(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should inject multiple values at once."""
        _ = setup_shm  # Fixture needed to create shared memory
        with SimulationAPI(shm_name) as api:
            api.inject(
                {
                    "position.x": 1.0,
                    "position.y": 2.0,
                    "velocity": 3.0,
                }
            )

            assert api.get("position.x") == 1.0
            assert api.get("position.y") == 2.0
            assert api.get("velocity") == 3.0

    def test_sample_multiple(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should sample multiple signals at once."""
        setup_shm.set_signal("position.x", 10.0)
        setup_shm.set_signal("position.y", 20.0)

        with SimulationAPI(shm_name) as api:
            values = api.sample(["position.x", "position.y"])

            assert values["position.x"] == 10.0
            assert values["position.y"] == 20.0

    def test_wait_frame_immediate(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should return immediately if frame already reached."""
        setup_shm.set_frame(100)

        with SimulationAPI(shm_name) as api:
            result = api.wait_frame(50, timeout=0.1)
            assert result is True

    def test_wait_frame_timeout(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should timeout if frame not reached."""
        setup_shm.set_frame(10)

        with SimulationAPI(shm_name) as api:
            result = api.wait_frame(100, timeout=0.1)
            assert result is False


class TestSimulationAPIConnection:
    """Tests for SimulationAPI connection management."""

    def test_connect_disconnect(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should connect and disconnect manually."""
        _ = setup_shm
        api = SimulationAPI(shm_name)
        api.connect()
        assert api._attached is True
        api.disconnect()
        assert api._attached is False

    def test_connect_already_connected_raises(
        self, shm_name: str, setup_shm: SharedMemoryManager
    ) -> None:
        """Should raise if already connected."""
        _ = setup_shm
        api = SimulationAPI(shm_name)
        api.connect()
        try:
            with pytest.raises(RuntimeError, match="Already connected"):
                api.connect()
        finally:
            api.disconnect()

    def test_disconnect_not_connected(self, shm_name: str) -> None:
        """Should not raise if disconnecting when not connected."""
        api = SimulationAPI(shm_name)
        api.disconnect()  # Should not raise

    def test_get_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if getting signal when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.get("position.x")

    def test_set_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if setting signal when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.set("position.x", 1.0)

    def test_get_frame_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if getting frame when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.get_frame()

    def test_get_time_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if getting time when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.get_time()

    def test_get_time_ns_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if getting time_ns when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.get_time_ns()

    def test_wait_frame_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if waiting for frame when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.wait_frame(10)

    def test_wait_time_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if waiting for time when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.wait_time(1.0)

    def test_wait_time_ns_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if waiting for time_ns when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.wait_time_ns(1_000_000_000)

    def test_list_signals_not_connected_raises(self, shm_name: str) -> None:
        """Should raise if listing signals when not connected."""
        api = SimulationAPI(shm_name)
        with pytest.raises(RuntimeError, match="Not connected"):
            api.list_signals()


class TestSimulationAPITimeNs:
    """Tests for nanosecond time methods."""

    def test_get_time_ns(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should get time in nanoseconds."""
        setup_shm.set_time_ns(1_500_000_000)

        with SimulationAPI(shm_name) as api:
            assert api.get_time_ns() == 1_500_000_000
            assert isinstance(api.get_time_ns(), int)

    def test_wait_time_immediate(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should return immediately if time already reached."""
        setup_shm.set_time(2.0)

        with SimulationAPI(shm_name) as api:
            result = api.wait_time(1.0, timeout=0.1)
            assert result is True

    def test_wait_time_timeout(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should timeout if time not reached."""
        setup_shm.set_time(0.5)

        with SimulationAPI(shm_name) as api:
            result = api.wait_time(2.0, timeout=0.1)
            assert result is False

    def test_wait_time_ns_immediate(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should return immediately if time_ns already reached."""
        setup_shm.set_time_ns(2_000_000_000)

        with SimulationAPI(shm_name) as api:
            result = api.wait_time_ns(1_000_000_000, timeout=0.1)
            assert result is True

    def test_wait_time_ns_timeout(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should timeout if time_ns not reached."""
        setup_shm.set_time_ns(500_000_000)

        with SimulationAPI(shm_name) as api:
            result = api.wait_time_ns(2_000_000_000, timeout=0.1)
            assert result is False


class TestSimulationAPIListSignals:
    """Tests for list_signals method."""

    def test_list_signals(self, shm_name: str, setup_shm: SharedMemoryManager) -> None:
        """Should list all signal names."""
        _ = setup_shm

        with SimulationAPI(shm_name) as api:
            signals = api.list_signals()
            assert "position.x" in signals
            assert "position.y" in signals
            assert "velocity" in signals
