"""Tests for synchronization primitives."""

from __future__ import annotations

import os
import uuid

import pytest

from hermes.backplane.sync import FrameBarrier


@pytest.fixture
def barrier_name() -> str:
    """Generate unique barrier name for test isolation."""
    return f"/hermes_barrier_{uuid.uuid4().hex[:8]}"


class TestFrameBarrier:
    """Tests for FrameBarrier synchronization."""

    def test_create_and_destroy(self, barrier_name: str) -> None:
        """Should create and cleanly destroy barrier."""
        barrier = FrameBarrier(barrier_name, 2)
        try:
            barrier.create()
            assert barrier._step_sem is not None
            assert barrier._done_sem is not None
        finally:
            barrier.destroy()

    def test_attach_and_close(self, barrier_name: str) -> None:
        """Should attach to existing barrier."""
        creator = FrameBarrier(barrier_name, 2)
        try:
            creator.create()

            client = FrameBarrier(barrier_name, 2)
            client.attach()
            assert client._step_sem is not None
            client.close()
        finally:
            creator.destroy()

    def test_signal_step_wait_step(self, barrier_name: str) -> None:
        """Should signal and wait for step in single thread."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()

            # Signal step (scheduler side)
            barrier.signal_step()

            # Wait for step (module side) - should return immediately
            result = barrier.wait_step(timeout=1.0)
            assert result is True
        finally:
            barrier.destroy()

    def test_wait_step_timeout(self, barrier_name: str) -> None:
        """Should timeout if step not signaled."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()

            # Wait without signal - should timeout
            result = barrier.wait_step(timeout=0.1)
            assert result is False
        finally:
            barrier.destroy()

    def test_signal_done_wait_done(self, barrier_name: str) -> None:
        """Should signal and wait for done."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()

            # Signal done (module side)
            barrier.signal_done()

            # Wait for done (scheduler side)
            result = barrier.wait_all_done(timeout=1.0)
            assert result is True
        finally:
            barrier.destroy()

    def test_fork_synchronization(self, barrier_name: str) -> None:
        """Should synchronize across fork boundary."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()

            pid = os.fork()
            if pid == 0:
                # Child: wait for step, signal done
                try:
                    child_barrier = FrameBarrier(barrier_name, 1)
                    child_barrier.attach()

                    if not child_barrier.wait_step(timeout=2.0):
                        os._exit(1)

                    child_barrier.signal_done()
                    child_barrier.close()
                    os._exit(0)
                except Exception:
                    os._exit(2)
            else:
                # Parent: signal step, wait for done
                barrier.signal_step()
                result = barrier.wait_all_done(timeout=2.0)

                _, status = os.waitpid(pid, 0)
                assert os.WEXITSTATUS(status) == 0
                assert result is True
        finally:
            barrier.destroy()


class TestFrameBarrierProperties:
    """Tests for FrameBarrier properties."""

    def test_name_property(self, barrier_name: str) -> None:
        """Should return barrier name."""
        barrier = FrameBarrier(barrier_name, 3)
        assert barrier.name == barrier_name

    def test_count_property(self, barrier_name: str) -> None:
        """Should return module count."""
        barrier = FrameBarrier(barrier_name, 5)
        assert barrier.count == 5


class TestFrameBarrierErrors:
    """Tests for FrameBarrier error handling."""

    def test_create_already_created_raises(self, barrier_name: str) -> None:
        """Should raise if creating twice."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()
            with pytest.raises(RuntimeError, match="already created"):
                barrier.create()
        finally:
            barrier.destroy()

    def test_attach_already_attached_raises(self, barrier_name: str) -> None:
        """Should raise if attaching twice."""
        creator = FrameBarrier(barrier_name, 1)
        try:
            creator.create()

            client = FrameBarrier(barrier_name, 1)
            client.attach()
            with pytest.raises(RuntimeError, match="Already attached"):
                client.attach()
            client.close()
        finally:
            creator.destroy()

    def test_signal_step_not_created_raises(self, barrier_name: str) -> None:
        """Should raise if signaling step without creating."""
        barrier = FrameBarrier(barrier_name, 1)
        with pytest.raises(RuntimeError, match="not created"):
            barrier.signal_step()

    def test_wait_step_not_created_raises(self, barrier_name: str) -> None:
        """Should raise if waiting step without creating."""
        barrier = FrameBarrier(barrier_name, 1)
        with pytest.raises(RuntimeError, match="not created"):
            barrier.wait_step()

    def test_signal_done_not_created_raises(self, barrier_name: str) -> None:
        """Should raise if signaling done without creating."""
        barrier = FrameBarrier(barrier_name, 1)
        with pytest.raises(RuntimeError, match="not created"):
            barrier.signal_done()

    def test_wait_all_done_not_created_raises(self, barrier_name: str) -> None:
        """Should raise if waiting done without creating."""
        barrier = FrameBarrier(barrier_name, 1)
        with pytest.raises(RuntimeError, match="not created"):
            barrier.wait_all_done()


class TestFrameBarrierContextManager:
    """Tests for FrameBarrier context manager."""

    def test_context_manager(self, barrier_name: str) -> None:
        """Should work as context manager."""
        creator = FrameBarrier(barrier_name, 1)
        creator.create()

        try:
            with FrameBarrier(barrier_name, 1) as client:
                client.attach()
                assert client._step_sem is not None
            # After exit, semaphores should be closed
            assert client._step_sem is None
        finally:
            creator.destroy()


class TestFrameBarrierMultipleProcesses:
    """Tests for FrameBarrier with multiple processes."""

    def test_wait_all_done_timeout(self, barrier_name: str) -> None:
        """Should timeout if not all modules signal done."""
        barrier = FrameBarrier(barrier_name, 2)  # Expect 2 modules
        try:
            barrier.create()

            # Only signal done once (not twice)
            barrier.signal_done()

            # Should timeout waiting for second done
            result = barrier.wait_all_done(timeout=0.1)
            assert result is False
        finally:
            barrier.destroy()

    def test_multiple_signals(self, barrier_name: str) -> None:
        """Should handle multiple step/done cycles."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()

            for _ in range(5):
                barrier.signal_step()
                assert barrier.wait_step(timeout=1.0) is True
                barrier.signal_done()
                assert barrier.wait_all_done(timeout=1.0) is True
        finally:
            barrier.destroy()
