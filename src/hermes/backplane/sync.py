"""Synchronization primitives for frame coordination.

This module provides semaphore-based synchronization for coordinating
module execution across processes.

Frame Barrier Protocol:
    1. Scheduler calls signal_step() - releases all modules
    2. Each module calls wait_step() - blocks until released
    3. Each module executes and calls signal_done()
    4. Scheduler calls wait_all_done() - blocks until all complete
    5. Repeat for next frame
"""

from __future__ import annotations

import contextlib

import posix_ipc


class FrameBarrier:
    """Synchronization barrier for frame execution.

    Coordinates multiple module processes to execute frames in lockstep.
    Uses two semaphores:
    - step_sem: Scheduler signals modules to start stepping
    - done_sem: Modules signal completion to scheduler

    Example:
        # Scheduler side
        barrier = FrameBarrier("/hermes_barrier", count=3)
        barrier.create()
        barrier.signal_step()  # Release all modules
        barrier.wait_all_done()  # Wait for all to finish

        # Module side
        barrier = FrameBarrier("/hermes_barrier", count=3)
        barrier.attach()
        barrier.wait_step()  # Wait for scheduler
        # ... execute frame ...
        barrier.signal_done()  # Signal completion
    """

    def __init__(self, name: str, count: int) -> None:
        """Initialize frame barrier.

        Args:
            name: Base name for semaphores (e.g., "/hermes_barrier")
            count: Number of module processes to synchronize
        """
        self._name = name
        self._count = count
        self._step_sem: posix_ipc.Semaphore | None = None
        self._done_sem: posix_ipc.Semaphore | None = None

    @property
    def name(self) -> str:
        """Barrier name."""
        return self._name

    @property
    def count(self) -> int:
        """Number of processes to synchronize."""
        return self._count

    def create(self) -> None:
        """Create barrier semaphores.

        Raises:
            RuntimeError: If already created
            posix_ipc.ExistentialError: If semaphores already exist
        """
        if self._step_sem is not None:
            raise RuntimeError("Barrier already created")

        # Create semaphores with initial value 0
        self._step_sem = posix_ipc.Semaphore(
            f"{self._name}_step",
            posix_ipc.O_CREX,
            initial_value=0,
        )
        self._done_sem = posix_ipc.Semaphore(
            f"{self._name}_done",
            posix_ipc.O_CREX,
            initial_value=0,
        )

    def attach(self) -> None:
        """Attach to existing barrier semaphores.

        Raises:
            RuntimeError: If already attached
            posix_ipc.ExistentialError: If semaphores don't exist
        """
        if self._step_sem is not None:
            raise RuntimeError("Already attached to barrier")

        self._step_sem = posix_ipc.Semaphore(f"{self._name}_step")
        self._done_sem = posix_ipc.Semaphore(f"{self._name}_done")

    def signal_step(self) -> None:
        """Scheduler: signal all modules to execute a step.

        Releases the step semaphore `count` times so all modules
        can proceed.
        """
        if self._step_sem is None:
            raise RuntimeError("Barrier not created/attached")

        for _ in range(self._count):
            self._step_sem.release()

    def wait_step(self, timeout: float | None = None) -> bool:
        """Module: wait for step signal from scheduler.

        Args:
            timeout: Maximum seconds to wait, None for infinite

        Returns:
            True if signaled, False if timeout
        """
        if self._step_sem is None:
            raise RuntimeError("Barrier not created/attached")

        try:
            self._step_sem.acquire(timeout)
            return True
        except Exception:  # posix_ipc.BusyError on timeout
            return False

    def signal_done(self) -> None:
        """Module: signal that step execution is complete."""
        if self._done_sem is None:
            raise RuntimeError("Barrier not created/attached")

        self._done_sem.release()

    def wait_all_done(self, timeout: float | None = None) -> bool:
        """Scheduler: wait for all modules to complete.

        Args:
            timeout: Maximum seconds to wait per module, None for infinite

        Returns:
            True if all done, False if any timeout
        """
        if self._done_sem is None:
            raise RuntimeError("Barrier not created/attached")

        for _ in range(self._count):
            try:
                self._done_sem.acquire(timeout)
            except Exception:  # posix_ipc.BusyError on timeout
                return False
        return True

    def close(self) -> None:
        """Close semaphore handles without destroying."""
        if self._step_sem is not None:
            self._step_sem.close()
            self._step_sem = None
        if self._done_sem is not None:
            self._done_sem.close()
            self._done_sem = None

    def destroy(self) -> None:
        """Destroy the barrier semaphores.

        Should only be called by the creator after all users close.
        """
        self.close()
        with contextlib.suppress(posix_ipc.ExistentialError):
            posix_ipc.unlink_semaphore(f"{self._name}_step")
        with contextlib.suppress(posix_ipc.ExistentialError):
            posix_ipc.unlink_semaphore(f"{self._name}_done")

    def __enter__(self) -> FrameBarrier:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
