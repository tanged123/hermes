"""Tests for Scheduler."""

import pytest

from hermes.core.signal import SignalBus
from hermes.core.scheduler import Scheduler, SchedulerConfig, ExecutionMode
from tests.conftest import MockAdapter


class TestSchedulerBasics:
    """Basic scheduler tests."""

    def test_initial_state(self) -> None:
        bus = SignalBus()
        config = SchedulerConfig(dt=0.01)
        scheduler = Scheduler(bus, config)

        assert scheduler.time == 0.0
        assert scheduler.frame == 0
        assert scheduler.dt == 0.01
        assert not scheduler.is_running
        assert not scheduler.is_staged

    def test_stage_calls_module_stage(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        scheduler = Scheduler(bus, SchedulerConfig())
        scheduler.stage()

        assert adapter._staged
        assert scheduler.is_staged

    def test_step_without_stage_raises(self) -> None:
        bus = SignalBus()
        scheduler = Scheduler(bus, SchedulerConfig())

        with pytest.raises(RuntimeError, match="not staged"):
            scheduler.step()


class TestSchedulerStep:
    """Tests for step execution."""

    def test_step_advances_time(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        config = SchedulerConfig(dt=0.01)
        scheduler = Scheduler(bus, config)
        scheduler.stage()

        scheduler.step()

        assert scheduler.time == pytest.approx(0.01)
        assert scheduler.frame == 1

    def test_step_calls_module_step(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        scheduler = Scheduler(bus, SchedulerConfig())
        scheduler.stage()

        scheduler.step()
        scheduler.step()
        scheduler.step()

        assert adapter.step_count == 3

    def test_multiple_steps_accumulate_time(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        config = SchedulerConfig(dt=0.1)
        scheduler = Scheduler(bus, config)
        scheduler.stage()

        for _ in range(10):
            scheduler.step()

        assert scheduler.time == pytest.approx(1.0)
        assert scheduler.frame == 10


class TestSchedulerReset:
    """Tests for reset functionality."""

    def test_reset_clears_time(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        scheduler = Scheduler(bus, SchedulerConfig())
        scheduler.stage()

        for _ in range(100):
            scheduler.step()

        scheduler.reset()

        assert scheduler.time == 0.0
        assert scheduler.frame == 0

    def test_reset_calls_module_reset(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        scheduler = Scheduler(bus, SchedulerConfig())
        scheduler.stage()

        for _ in range(10):
            scheduler.step()

        scheduler.reset()

        assert adapter.step_count == 0


class TestSchedulerModes:
    """Tests for execution modes."""

    def test_pause_changes_mode(self) -> None:
        bus = SignalBus()
        config = SchedulerConfig(mode=ExecutionMode.AS_FAST_AS_POSSIBLE)
        scheduler = Scheduler(bus, config)

        scheduler.pause()

        assert scheduler._config.mode == ExecutionMode.PAUSED

    def test_resume_changes_mode(self) -> None:
        bus = SignalBus()
        config = SchedulerConfig(mode=ExecutionMode.PAUSED)
        scheduler = Scheduler(bus, config)

        scheduler.resume(ExecutionMode.REAL_TIME)

        assert scheduler._config.mode == ExecutionMode.REAL_TIME


@pytest.mark.asyncio
class TestSchedulerRun:
    """Tests for async run loop."""

    async def test_run_stops_at_end_time(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        config = SchedulerConfig(dt=0.1, end_time=1.0)
        scheduler = Scheduler(bus, config)
        scheduler.stage()

        await scheduler.run()

        assert scheduler.time >= 1.0
        assert scheduler.frame == 10

    async def test_run_calls_callback(self) -> None:
        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        config = SchedulerConfig(dt=0.1, end_time=0.5)
        scheduler = Scheduler(bus, config)
        scheduler.stage()

        callback_frames: list[int] = []

        async def callback(frame: int, time: float) -> None:
            callback_frames.append(frame)

        await scheduler.run(callback=callback)

        assert len(callback_frames) == 5
        assert callback_frames == [1, 2, 3, 4, 5]

    async def test_stop_halts_run(self) -> None:
        import asyncio

        adapter = MockAdapter("test", {"value": 0.0})
        bus = SignalBus()
        bus.register_module(adapter)

        config = SchedulerConfig(dt=0.01)  # No end_time
        scheduler = Scheduler(bus, config)
        scheduler.stage()

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.05)
            scheduler.stop()

        asyncio.create_task(stop_after_delay())
        await scheduler.run()

        assert not scheduler.is_running
        assert scheduler.frame > 0
