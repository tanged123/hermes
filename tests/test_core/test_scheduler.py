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
        scheduler._time = 1.5

        scheduler.stage()

        assert scheduler.frame == 0
        assert scheduler.time == 0.0

    def test_stage_updates_shm_time(
        self, mock_process_manager: MagicMock, default_config: ExecutionConfig
    ) -> None:
        """stage() should update shared memory time."""
        scheduler = Scheduler(mock_process_manager, default_config)
        scheduler.stage()

        mock_process_manager.update_time.assert_called_with(0, 0.0)


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
        scheduler._time = 1.5

        scheduler.reset()

        assert scheduler.frame == 0
        assert scheduler.time == 0.0


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
