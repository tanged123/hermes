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
