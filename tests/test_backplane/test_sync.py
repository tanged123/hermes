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
