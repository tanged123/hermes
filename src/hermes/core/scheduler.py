"""Runtime simulation scheduler for Hermes.

This module provides the Scheduler class for controlling simulation
execution with support for multiple operating modes.

Operating Modes:
    realtime: Paced to wall-clock time (for HIL, visualization)
    afap: As fast as possible (for batch runs, Monte Carlo)
    single_frame: Manual stepping (for debugging, scripted scenarios)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from hermes.core.config import ExecutionConfig, ExecutionMode
    from hermes.core.process import ProcessManager

log = structlog.get_logger()


class Scheduler:
    """Runtime simulation scheduler.

    Controls simulation execution with support for realtime, AFAP,
    and single-frame modes. Coordinates with ProcessManager for
    module stepping and provides pause/resume/stop control.

    Example:
        >>> scheduler = Scheduler(process_mgr, config.execution)
        >>> scheduler.stage()
        >>> await scheduler.run(callback=my_telemetry_fn)
    """

    def __init__(
        self,
        process_mgr: ProcessManager,
        config: ExecutionConfig,
    ) -> None:
        """Initialize the scheduler.

        Args:
            process_mgr: ProcessManager for controlling modules
            config: Execution configuration (mode, rate, end_time)
        """
        self._pm = process_mgr
        self._config = config
        self._frame: int = 0
        self._time: float = 0.0
        self._running: bool = False
        self._paused: bool = False

    @property
    def frame(self) -> int:
        """Current simulation frame number."""
        return self._frame

    @property
    def time(self) -> float:
        """Current simulation time in seconds."""
        return self._time

    @property
    def dt(self) -> float:
        """Timestep in seconds."""
        return 1.0 / self._config.rate_hz

    @property
    def running(self) -> bool:
        """Whether the simulation run loop is active."""
        return self._running

    @property
    def paused(self) -> bool:
        """Whether the simulation is paused."""
        return self._paused

    @property
    def mode(self) -> ExecutionMode:
        """Current execution mode."""
        return self._config.mode

    def stage(self) -> None:
        """Stage simulation for execution.

        Calls stage() on all modules via ProcessManager and resets
        frame/time counters to zero.
        """
        log.info("Staging simulation")
        self._pm.stage_all()
        self._frame = 0
        self._time = 0.0
        self._pm.update_time(self._frame, self._time)
        log.debug("Simulation staged", frame=self._frame, time=self._time)

    def step(self, count: int = 1) -> None:
        """Execute N simulation frames.

        Args:
            count: Number of frames to execute (default: 1)

        Raises:
            ValueError: If count is not positive
        """
        if count < 1:
            raise ValueError(f"Step count must be positive, got {count}")

        for _ in range(count):
            # Update time before step so modules see current time
            self._pm.update_time(self._frame, self._time)

            # Execute all modules for this frame
            self._pm.step_all()

            # Advance simulation state
            self._time += self.dt
            self._frame += 1

        log.debug("Stepped", frames=count, frame=self._frame, time=self._time)

    def reset(self) -> None:
        """Reset simulation to initial state.

        Resets frame and time counters. Note: does not re-stage modules.
        """
        self._frame = 0
        self._time = 0.0
        self._pm.update_time(self._frame, self._time)
        log.info("Simulation reset")

    async def run(
        self,
        callback: Callable[[int, float], Awaitable[None]] | None = None,
    ) -> None:
        """Run simulation loop until stopped or end_time reached.

        In realtime mode, paces execution to wall-clock time.
        In AFAP mode, runs as fast as possible.
        In single_frame mode, waits for explicit step() calls.

        Args:
            callback: Optional async callback invoked after each frame
                     with (frame_number, simulation_time)
        """
        from hermes.core.config import ExecutionMode

        self._running = True
        wall_start = time.perf_counter()

        log.info(
            "Starting simulation loop",
            mode=self._config.mode.value,
            rate_hz=self._config.rate_hz,
            end_time=self._config.end_time,
        )

        try:
            while self._running:
                # Check end condition
                if self._config.end_time is not None and self._time >= self._config.end_time:
                    log.info("End time reached", time=self._time)
                    break

                # Pause handling
                if self._paused:
                    await asyncio.sleep(0.01)
                    continue

                # Single frame mode waits for explicit step()
                if self._config.mode == ExecutionMode.SINGLE_FRAME:
                    await asyncio.sleep(0.01)
                    continue

                # Execute one frame
                self.step()

                # Invoke callback if provided
                if callback is not None:
                    await callback(self._frame, self._time)

                # Real-time pacing
                if self._config.mode == ExecutionMode.REALTIME:
                    target_wall = wall_start + self._time
                    sleep_time = target_wall - time.perf_counter()
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

                # Yield to event loop periodically in AFAP mode
                if self._config.mode == ExecutionMode.AFAP and self._frame % 100 == 0:
                    await asyncio.sleep(0)

        finally:
            self._running = False

        log.info(
            "Simulation loop ended",
            frames=self._frame,
            time=self._time,
        )

    def pause(self) -> None:
        """Pause the run loop.

        The simulation will stop advancing but remain in the run loop.
        Use resume() to continue.
        """
        if not self._paused:
            self._paused = True
            log.info("Simulation paused", frame=self._frame)

    def resume(self) -> None:
        """Resume the run loop after pause."""
        if self._paused:
            self._paused = False
            log.info("Simulation resumed", frame=self._frame)

    def stop(self) -> None:
        """Stop the run loop.

        The simulation will exit the run() method cleanly.
        """
        self._running = False
        log.info("Simulation stopped", frame=self._frame)
