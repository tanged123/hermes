"""Tests for the scheduler module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hermes.core.config import ExecutionConfig, ExecutionMode
from hermes.core.scheduler import Scheduler


@pytest.fixture
def mock_process_manager() -> MagicMock:
    """Create a mock ProcessManager."""
    pm = MagicMock()
    pm.stage_all = MagicMock()
    pm.step_all = MagicMock()
    pm.update_time = MagicMock()
    return pm


@pytest.fixture
def default_config() -> ExecutionConfig:
    """Create default execution config."""
    return ExecutionConfig(
        mode=ExecutionMode.AFAP,
        rate_hz=100.0,
        end_time=None,
    )


class TestSchedulerProperties:
    """Tests for Scheduler properties."""

    def test_initial_state(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """Scheduler should start in correct initial state."""
        scheduler = Scheduler(mock_process_manager, default_config)

        assert scheduler.frame == 0
        assert scheduler.time == 0.0
        assert scheduler.dt == 0.01  # 1/100 Hz
        assert scheduler.running is False
        assert scheduler.paused is False
        assert scheduler.mode == ExecutionMode.AFAP

    def test_dt_calculation(self, mock_process_manager: MagicMock) -> None:
        """dt should be calculated from rate_hz."""
        config = ExecutionConfig(rate_hz=50.0)
        scheduler = Scheduler(mock_process_manager, config)
        assert scheduler.dt == 0.02  # 1/50 Hz


class TestSchedulerStage:
    """Tests for Scheduler.stage()."""

    def test_stage_calls_process_manager(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """stage() should call pm.stage_all()."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.stage()

        mock_process_manager.stage_all.assert_called_once()

    def test_stage_resets_counters(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """stage() should reset frame and time to zero."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler._frame = 100
        scheduler._time_us = 1_500_000  # 1.5 seconds in microseconds

        scheduler.stage()

        assert scheduler.frame == 0
        assert scheduler.time == 0.0
        assert scheduler.time_us == 0

    def test_stage_updates_shm_time(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """stage() should update shared memory time with time_us."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.stage()

        # update_time now takes (frame, time_us) where time_us is in microseconds
        mock_process_manager.update_time.assert_called_with(0, 0)


class TestSchedulerStep:
    """Tests for Scheduler.step()."""

    def test_step_increments_frame_and_time(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """step() should increment frame and time."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.step()

        assert scheduler.frame == 1
        assert scheduler.time == pytest.approx(0.01)

    def test_step_calls_process_manager(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """step() should call pm.step_all()."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.step()

        mock_process_manager.step_all.assert_called_once()
        mock_process_manager.update_time.assert_called()

    def test_step_count(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """step(n) should execute n frames."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.step(5)

        assert scheduler.frame == 5
        assert scheduler.time == pytest.approx(0.05)
        assert mock_process_manager.step_all.call_count == 5

    def test_step_invalid_count(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """step() should reject non-positive count."""
        scheduler = Scheduler(mock_process_manager, default_config)

        with pytest.raises(ValueError):
            scheduler.step(0)

        with pytest.raises(ValueError):
            scheduler.step(-1)


class TestSchedulerReset:
    """Tests for Scheduler.reset()."""

    def test_reset_clears_counters(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """reset() should clear frame and time."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler._frame = 100
        scheduler._time_us = 1_500_000  # 1.5 seconds in microseconds

        scheduler.reset()

        assert scheduler.frame == 0
        assert scheduler.time == 0.0
        assert scheduler.time_us == 0


class TestSchedulerPauseResume:
    """Tests for pause/resume functionality."""

    def test_pause_sets_flag(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """pause() should set paused flag."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.pause()
        assert scheduler.paused is True

    def test_resume_clears_flag(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """resume() should clear paused flag."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler._paused = True
        scheduler.resume()
        assert scheduler.paused is False

    def test_stop_clears_running(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """stop() should clear running flag."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler._running = True
        scheduler.stop()
        assert scheduler.running is False


class TestSchedulerRun:
    """Tests for Scheduler.run() async method."""

    @pytest.mark.asyncio
    async def test_run_with_end_time(self, mock_process_manager: MagicMock) -> None:
        """run() should stop at end_time."""
        config = ExecutionConfig(
            mode=ExecutionMode.AFAP,
            rate_hz=100.0,
            end_time=0.05,  # 5 frames
        )
        scheduler = Scheduler(mock_process_manager, config)

        await scheduler.run()

        # Should have run ~5 frames (may be 5 or 6 depending on timing)
        assert scheduler.frame >= 5
        assert scheduler.time >= 0.05

    @pytest.mark.asyncio
    async def test_run_with_callback(self, mock_process_manager: MagicMock) -> None:
        """run() should invoke callback each frame."""
        config = ExecutionConfig(
            mode=ExecutionMode.AFAP,
            rate_hz=100.0,
            end_time=0.03,
        )
        scheduler = Scheduler(mock_process_manager, config)

        frames_received: list[int] = []

        async def callback(frame: int, _time: float) -> None:
            frames_received.append(frame)

        await scheduler.run(callback=callback)

        assert len(frames_received) >= 3

    @pytest.mark.asyncio
    async def test_run_stop(self, mock_process_manager: MagicMock) -> None:
        """stop() should terminate run loop."""
        config = ExecutionConfig(
            mode=ExecutionMode.AFAP,
            rate_hz=100.0,
            end_time=None,  # Would run forever
        )
        scheduler = Scheduler(mock_process_manager, config)

        async def stop_after_frames(frame: int, _time: float) -> None:
            if frame >= 10:
                scheduler.stop()

        await scheduler.run(callback=stop_after_frames)

        assert scheduler.frame >= 10
        assert scheduler.running is False


class TestSchedulerDeterminism:
    """Tests for deterministic integer microsecond time tracking."""

    def test_time_us_exact_integer(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """time_us should be exact integer, not floating point."""
        scheduler = Scheduler(mock_process_manager, default_config)

        # At 100 Hz, dt_us = 10000 µs
        assert scheduler.dt_us == 10000

        scheduler.step(1)
        assert scheduler.time_us == 10000  # Exactly 10000 µs
        assert isinstance(scheduler.time_us, int)

    def test_time_derived_from_time_us(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """Float time should be derived from integer time_us."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.step(1)

        # time should be time_us / 1_000_000
        assert scheduler.time == scheduler.time_us / 1_000_000
        assert scheduler.time == 0.01

    def test_no_accumulation_drift(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """Time should not drift over many frames due to accumulation."""
        scheduler = Scheduler(mock_process_manager, default_config)

        # Run 10000 frames at 100 Hz = 100 seconds
        scheduler.step(10000)

        # With integer math: time_us = 10000 * 10000 = 100_000_000 µs = 100 seconds
        assert scheduler.time_us == 100_000_000
        assert scheduler.frame == 10000

        # Float time should be exactly 100.0 (no drift)
        assert scheduler.time == 100.0

    def test_time_multiplication_not_accumulation(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """Time should use multiplication (frame * dt) not accumulation."""
        scheduler = Scheduler(mock_process_manager, default_config)

        # Step 1000 frames one at a time
        for _ in range(1000):
            scheduler.step(1)

        # Should be exactly frame * dt_us, not accumulated
        expected_time_us = scheduler.frame * scheduler.dt_us
        assert scheduler.time_us == expected_time_us
        assert scheduler.time_us == 10_000_000  # 10 seconds

    def test_different_rates_integer_dt(self, mock_process_manager: MagicMock) -> None:
        """Different valid rates should produce integer dt_us."""
        rates_and_expected_dt = [
            (1.0, 1_000_000),  # 1 Hz -> 1,000,000 µs
            (10.0, 100_000),  # 10 Hz -> 100,000 µs
            (50.0, 20_000),  # 50 Hz -> 20,000 µs
            (100.0, 10_000),  # 100 Hz -> 10,000 µs
            (200.0, 5_000),  # 200 Hz -> 5,000 µs
            (500.0, 2_000),  # 500 Hz -> 2,000 µs
            (1000.0, 1_000),  # 1000 Hz -> 1,000 µs
        ]

        for rate_hz, expected_dt_us in rates_and_expected_dt:
            config = ExecutionConfig(rate_hz=rate_hz)
            scheduler = Scheduler(mock_process_manager, config)
            assert scheduler.dt_us == expected_dt_us, f"Failed for rate_hz={rate_hz}"

    def test_reproducibility_across_runs(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """Multiple runs should produce identical time sequences."""
        results: list[list[int]] = []

        for _ in range(3):
            scheduler = Scheduler(mock_process_manager, default_config)
            times: list[int] = []
            for _ in range(100):
                scheduler.step(1)
                times.append(scheduler.time_us)
            results.append(times)

        # All runs should be identical
        assert results[0] == results[1] == results[2]
