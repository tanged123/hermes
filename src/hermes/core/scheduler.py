"""Synchronous simulation scheduler."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Coroutine, Any

if TYPE_CHECKING:
    from hermes.core.signal import SignalBus


class ExecutionMode(Enum):
    """Scheduler execution modes."""

    AS_FAST_AS_POSSIBLE = "afap"  # No pacing, maximum speed
    REAL_TIME = "realtime"  # Wall-clock pacing
    PAUSED = "paused"  # Waiting for step command


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""

    dt: float = 0.01  # 100 Hz default
    mode: ExecutionMode = ExecutionMode.AS_FAST_AS_POSSIBLE
    end_time: float | None = None  # None = run forever


class Scheduler:
    """Synchronous simulation scheduler.

    Manages the simulation loop, stepping all modules and routing signals
    each frame. Supports multiple execution modes including real-time pacing.
    """

    def __init__(self, bus: SignalBus, config: SchedulerConfig) -> None:
        """Initialize scheduler.

        Args:
            bus: Signal bus with registered modules
            config: Scheduler configuration
        """
        self._bus = bus
        self._config = config
        self._time: float = 0.0
        self._frame: int = 0
        self._running: bool = False
        self._staged: bool = False

    @property
    def time(self) -> float:
        """Current simulation time (seconds)."""
        return self._time

    @property
    def frame(self) -> int:
        """Current frame number."""
        return self._frame

    @property
    def dt(self) -> float:
        """Timestep (seconds)."""
        return self._config.dt

    @property
    def is_running(self) -> bool:
        """Whether the run loop is active."""
        return self._running

    @property
    def is_staged(self) -> bool:
        """Whether modules have been staged."""
        return self._staged

    def stage(self) -> None:
        """Stage all modules.

        Prepares all registered modules for execution by calling
        their stage() method. Must be called before step() or run().
        """
        for module in self._bus.modules.values():
            module.stage()
        self._time = 0.0
        self._frame = 0
        self._staged = True

    def step(self) -> None:
        """Execute one simulation frame.

        Steps all modules, routes signals, and advances time.
        Modules are stepped in registration order.

        Raises:
            RuntimeError: If not staged
        """
        if not self._staged:
            raise RuntimeError("Scheduler not staged. Call stage() first.")

        dt = self._config.dt

        # Step all modules in registration order
        # TODO: Topological sort based on wiring dependencies
        for module in self._bus.modules.values():
            module.step(dt)

        # Route signals between modules
        self._bus.route()

        # Advance time
        self._time += dt
        self._frame += 1

    def reset(self) -> None:
        """Reset all modules to initial state.

        Resets time to zero and calls reset() on all modules.
        Simulation remains staged after reset.
        """
        for module in self._bus.modules.values():
            module.reset()
        self._time = 0.0
        self._frame = 0

    async def run(
        self,
        callback: Callable[[int, float], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """Run simulation loop until end_time or stopped.

        Args:
            callback: Optional async callback called each frame with (frame, time).
                     Used for telemetry streaming.
        """
        if not self._staged:
            raise RuntimeError("Scheduler not staged. Call stage() first.")

        self._running = True
        wall_start = time.perf_counter()

        try:
            while self._running:
                # Check end condition
                if self._config.end_time is not None and self._time >= self._config.end_time:
                    break

                # Check for pause mode
                if self._config.mode == ExecutionMode.PAUSED:
                    await asyncio.sleep(0.1)
                    continue

                # Execute frame
                self.step()

                # Optional callback (for telemetry)
                if callback is not None:
                    await callback(self._frame, self._time)

                # Real-time pacing
                if self._config.mode == ExecutionMode.REAL_TIME:
                    target_wall = wall_start + self._time
                    sleep_time = target_wall - time.perf_counter()
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                else:
                    # Yield to event loop occasionally in AFAP mode
                    if self._frame % 100 == 0:
                        await asyncio.sleep(0)

        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the run loop."""
        self._running = False

    def pause(self) -> None:
        """Pause execution (switch to PAUSED mode)."""
        self._config.mode = ExecutionMode.PAUSED

    def resume(self, mode: ExecutionMode = ExecutionMode.AS_FAST_AS_POSSIBLE) -> None:
        """Resume execution with specified mode."""
        self._config.mode = mode
