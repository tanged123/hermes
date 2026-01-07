"""Tests for shared memory management."""

from __future__ import annotations

import os
import uuid

import pytest

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalFlags, SignalType


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
        SignalDescriptor(name="velocity", type=SignalType.F64, flags=SignalFlags.WRITABLE),
    ]


class TestSharedMemoryManager:
    """Tests for SharedMemoryManager."""

    def test_create_and_destroy(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Should create and cleanly destroy shared memory."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)
            assert shm._mmap is not None
        finally:
            shm.destroy()

    def test_attach_and_detach(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Should attach to existing shared memory."""
        # Create the shared memory
        creator = SharedMemoryManager(shm_name)
        try:
            creator.create(test_signals)

            # Attach from another manager
            client = SharedMemoryManager(shm_name)
            client.attach()
            assert client._mmap is not None
            client.detach()
        finally:
            creator.destroy()

    def test_read_write_signals(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Should read and write signal values."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # Write and read back
            shm.set_signal("position.x", 1.5)
            shm.set_signal("position.y", 2.5)
            shm.set_signal("velocity", 10.0)

            assert shm.get_signal("position.x") == 1.5
            assert shm.get_signal("position.y") == 2.5
            assert shm.get_signal("velocity") == 10.0
        finally:
            shm.destroy()

    def test_frame_time_header(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Should read and write frame and time from header."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # Initial values
            assert shm.get_frame() == 0
            assert shm.get_time() == 0.0

            # Update values
            shm.set_frame(100)
            shm.set_time(1.5)

            assert shm.get_frame() == 100
            assert shm.get_time() == 1.5
        finally:
            shm.destroy()

    def test_invalid_signal_raises(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Should raise KeyError for nonexistent signal."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            with pytest.raises(KeyError):
                shm.get_signal("nonexistent.signal")

            with pytest.raises(KeyError):
                shm.set_signal("nonexistent.signal", 1.0)
        finally:
            shm.destroy()

    def test_shared_between_processes(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Shared memory should be visible across process fork."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)
            shm.set_signal("position.x", 42.0)

            # Fork and check from child
            pid = os.fork()
            if pid == 0:
                # Child process
                try:
                    child_shm = SharedMemoryManager(shm_name)
                    child_shm.attach()
                    value = child_shm.get_signal("position.x")
                    child_shm.detach()
                    os._exit(0 if value == 42.0 else 1)
                except Exception:
                    os._exit(1)
            else:
                # Parent waits for child
                _, status = os.waitpid(pid, 0)
                assert os.WEXITSTATUS(status) == 0
        finally:
            shm.destroy()

    def test_time_ns_integer(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Time should be stored and retrieved as integer nanoseconds."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # Set and get time_ns directly
            shm.set_time_ns(1_500_000_000)  # 1.5 seconds
            assert shm.get_time_ns() == 1_500_000_000
            assert isinstance(shm.get_time_ns(), int)

            # Float convenience method should convert
            assert shm.get_time() == 1.5
        finally:
            shm.destroy()

    def test_time_float_convenience(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Float set_time should convert to integer nanoseconds."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # Set via float convenience method
            shm.set_time(2.5)  # 2.5 seconds

            # Should be stored as integer nanoseconds
            assert shm.get_time_ns() == 2_500_000_000
            assert shm.get_time() == 2.5
        finally:
            shm.destroy()

    def test_time_ns_large_values(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Should handle large time values without overflow."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # 1 hour in nanoseconds = 3,600,000,000,000 ns
            one_hour_ns = 3_600_000_000_000
            shm.set_time_ns(one_hour_ns)
            assert shm.get_time_ns() == one_hour_ns

            # 1 day in nanoseconds
            one_day_ns = 86_400_000_000_000
            shm.set_time_ns(one_day_ns)
            assert shm.get_time_ns() == one_day_ns

            # 1 year in nanoseconds (well within u64 range)
            one_year_ns = 365 * 24 * 3600 * 1_000_000_000
            shm.set_time_ns(one_year_ns)
            assert shm.get_time_ns() == one_year_ns
        finally:
            shm.destroy()

    def test_name_property(self, shm_name: str) -> None:
        """Should return the shared memory name."""
        shm = SharedMemoryManager(shm_name)
        assert shm.name == shm_name

    def test_is_attached_property(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Should track attachment state."""
        shm = SharedMemoryManager(shm_name)
        assert shm.is_attached is False

        shm.create(test_signals)
        assert shm.is_attached is True

        shm.detach()
        assert shm.is_attached is False

        shm.destroy()

    def test_create_already_attached_raises(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Should raise if creating while already attached."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)
            with pytest.raises(RuntimeError, match="Already attached"):
                shm.create(test_signals)
        finally:
            shm.destroy()

    def test_attach_already_attached_raises(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Should raise if attaching while already attached."""
        creator = SharedMemoryManager(shm_name)
        try:
            creator.create(test_signals)

            client = SharedMemoryManager(shm_name)
            client.attach()
            with pytest.raises(RuntimeError, match="Already attached"):
                client.attach()
            client.detach()
        finally:
            creator.destroy()

    def test_get_signal_not_attached_raises(self, shm_name: str) -> None:
        """Should raise if reading signal when not attached."""
        shm = SharedMemoryManager(shm_name)
        with pytest.raises(RuntimeError, match="Not attached"):
            shm.get_signal("test")

    def test_set_signal_not_attached_raises(self, shm_name: str) -> None:
        """Should raise if writing signal when not attached."""
        shm = SharedMemoryManager(shm_name)
        with pytest.raises(RuntimeError, match="Not attached"):
            shm.set_signal("test", 1.0)

    def test_get_frame_not_attached_raises(self, shm_name: str) -> None:
        """Should raise if reading frame when not attached."""
        shm = SharedMemoryManager(shm_name)
        with pytest.raises(RuntimeError, match="Not attached"):
            shm.get_frame()

    def test_set_frame_not_attached_raises(self, shm_name: str) -> None:
        """Should raise if writing frame when not attached."""
        shm = SharedMemoryManager(shm_name)
        with pytest.raises(RuntimeError, match="Not attached"):
            shm.set_frame(1)

    def test_get_time_ns_not_attached_raises(self, shm_name: str) -> None:
        """Should raise if reading time_ns when not attached."""
        shm = SharedMemoryManager(shm_name)
        with pytest.raises(RuntimeError, match="Not attached"):
            shm.get_time_ns()

    def test_set_time_ns_not_attached_raises(self, shm_name: str) -> None:
        """Should raise if writing time_ns when not attached."""
        shm = SharedMemoryManager(shm_name)
        with pytest.raises(RuntimeError, match="Not attached"):
            shm.set_time_ns(1)

    def test_context_manager(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Should work as context manager."""
        shm = SharedMemoryManager(shm_name)
        shm.create(test_signals)
        try:
            with shm:
                assert shm.is_attached is True
            # After exit, should be detached
            assert shm.is_attached is False
        finally:
            # Clean up the underlying shared memory
            import contextlib

            import posix_ipc

            with contextlib.suppress(posix_ipc.ExistentialError):
                posix_ipc.unlink_shared_memory(shm_name)

    def test_signal_names(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Should return list of all signal names."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)
            names = shm.signal_names()
            assert "position.x" in names
            assert "position.y" in names
            assert "velocity" in names
            assert len(names) == 3
        finally:
            shm.destroy()
