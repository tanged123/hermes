"""Runtime simulation scheduler for Hermes.

This module provides the Scheduler class for controlling simulation
execution with support for multiple operating modes.

Operating Modes:
    realtime: Paced to wall-clock time (for HIL, visualization)
    afap: As fast as possible (for batch runs, Monte Carlo)
    single_frame: Manual stepping (for debugging, scripted scenarios)

Determinism:
    Time is tracked internally as integer nanoseconds to ensure
    reproducibility across runs and platforms. The float `time` property
    is provided for API convenience, while `time_ns` gives the exact value.

    For rates that don't divide evenly into 1 billion (e.g., 600 Hz),
    the timestep is rounded to the nearest nanosecond. This introduces
    bounded error (~0.72ms/hour at 600 Hz) but remains deterministic.
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
    from hermes.core.router import WireRouter

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

    # Nanoseconds per second (for time conversions)
    NANOSECONDS_PER_SECOND: int = 1_000_000_000

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
        self._time_ns: int = 0  # Time in nanoseconds for determinism
        self._dt_ns: int = config.get_dt_ns()  # Major frame timestep in ns
        self._running: bool = False
        self._paused: bool = False
        self._router: WireRouter | None = None

        # Pre-compute per-module substep counts and dt values
        self._module_substeps: dict[str, tuple[int, float]] = {}
        major_rate = config.get_major_frame_rate_hz()
        for entry in config.schedule:
            entry_rate = entry.rate_hz if entry.rate_hz is not None else config.rate_hz
            substeps = round(entry_rate / major_rate)
            module_dt = 1.0 / entry_rate
            self._module_substeps[entry.name] = (substeps, module_dt)
            if substeps > 1:
                log.info(
                    "Multi-rate module",
                    module=entry.name,
                    rate_hz=entry_rate,
                    substeps=substeps,
                    dt=module_dt,
                )

    @property
    def frame(self) -> int:
        """Current simulation frame number."""
        return self._frame

    @property
    def time(self) -> float:
        """Current simulation time in seconds.

        This is derived from `time_ns` for API convenience.
        For deterministic comparisons, use `time_ns` instead.
        """
        return self._time_ns / self.NANOSECONDS_PER_SECOND

    @property
    def time_ns(self) -> int:
        """Current simulation time in nanoseconds.

        This is the authoritative time value for deterministic simulations.
        Use this for exact comparisons and reproducibility.
        """
        return self._time_ns

    @property
    def dt(self) -> float:
        """Timestep in seconds.

        Derived from `dt_ns` for API convenience.
        """
        return self._dt_ns / self.NANOSECONDS_PER_SECOND

    @property
    def dt_ns(self) -> int:
        """Timestep in nanoseconds.

        This is the authoritative timestep value for deterministic simulations.
        """
        return self._dt_ns

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

        Calls stage() on all modules via ProcessManager, configures
        wire routing, and resets frame/time counters to zero.
        """
        from hermes.core.router import WireRouter

        log.info("Staging simulation")
        self._pm.stage_all()

        # Configure wire routing
        shm = self._pm.shm
        if shm is not None and self._pm.config.wiring:
            self._router = WireRouter(shm)
            for wire_config in self._pm.config.wiring:
                self._router.add_wire(wire_config)
            self._router.validate()
            log.info("Wire routing configured", wires=self._router.wire_count)

        self._frame = 0
        self._time_ns = 0
        self._pm.update_time(self._frame, self._time_ns)
        log.debug("Simulation staged", frame=self._frame, time_ns=self._time_ns)

    def step(self, count: int = 1) -> None:
        """Execute N major frames.

        Each major frame routes wires, then steps each module according to
        its configured rate (faster modules sub-step multiple times).

        Args:
            count: Number of major frames to execute (default: 1)

        Raises:
            ValueError: If count is not positive
        """
        if count < 1:
            raise ValueError(f"Step count must be positive, got {count}")

        for _ in range(count):
            # Update time before step so modules see current time
            self._pm.update_time(self._frame, self._time_ns)

            # Route signals before stepping so modules see current wired values
            if self._router is not None:
                self._router.route()

            # Execute modules
            if self._module_substeps:
                # Multi-rate: step each module per its rate
                for entry in self._config.schedule:
                    substeps, module_dt = self._module_substeps[entry.name]
                    inproc = self._pm.get_inproc_module(entry.name)
                    if inproc is not None:
                        for _ in range(substeps):
                            inproc.step(module_dt)
            else:
                # No schedule: step all modules at base rate
                self._pm.step_all()

            # Advance simulation state using integer arithmetic for determinism
            self._frame += 1
            self._time_ns = self._frame * self._dt_ns

        # Build schedule summary for debug: "inputs:1 physics:5"
        if self._module_substeps:
            sched_str = " ".join(
                f"{name}:{substeps}" for name, (substeps, _) in self._module_substeps.items()
            )
            log.debug("Stepped", frame=self._frame, time_ns=self._time_ns, schedule=sched_str)
        else:
            log.debug("Stepped", frame=self._frame, time_ns=self._time_ns)

    def reset(self) -> None:
        """Reset simulation to initial state.

        Resets frame and time counters. Note: does not re-stage modules.
        """
        self._frame = 0
        self._time_ns = 0
        self._pm.update_time(self._frame, self._time_ns)
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
                     with (frame_number, simulation_time_seconds)
        """
        from hermes.core.config import ExecutionMode

        self._running = True
        wall_start = time.perf_counter()
        pause_start: float | None = None  # Track when pause began

        # Get end time in nanoseconds for deterministic comparison
        end_time_ns = self._config.get_end_time_ns()

        log.info(
            "Starting simulation loop",
            mode=self._config.mode.value,
            major_frame_hz=self._config.get_major_frame_rate_hz(),
            end_time=self._config.end_time,
        )

        try:
            while self._running:
                # Check end condition using integer comparison for determinism
                if end_time_ns is not None and self._time_ns >= end_time_ns:
                    log.info("End time reached", time_ns=self._time_ns)
                    break

                # Pause handling with wall_start adjustment for realtime mode
                if self._paused:
                    if pause_start is None:
                        pause_start = time.perf_counter()
                    await asyncio.sleep(0.01)
                    continue
                elif pause_start is not None:
                    # Resuming from pause: adjust wall_start to account for pause duration
                    pause_duration = time.perf_counter() - pause_start
                    wall_start += pause_duration
                    pause_start = None

                # Single frame mode waits for explicit step()
                if self._config.mode == ExecutionMode.SINGLE_FRAME:
                    await asyncio.sleep(0.01)
                    continue

                # Execute one frame
                self.step()

                # Invoke callback if provided (uses float time for API convenience)
                if callback is not None:
                    await callback(self._frame, self.time)

                # Real-time pacing (uses float time for wall-clock sync)
                if self._config.mode == ExecutionMode.REALTIME:
                    target_wall = wall_start + self.time
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
            time_ns=self._time_ns,
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
