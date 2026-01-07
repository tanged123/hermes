"""End-to-end integration tests with real module scripts.

These tests verify the full simulation pipeline:
1. Config loading
2. Process spawning
3. Shared memory communication
4. Barrier synchronization
5. Scheduler execution
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.backplane.sync import FrameBarrier
from hermes.core.config import (
    ExecutionConfig,
    ExecutionMode,
    HermesConfig,
    ModuleConfig,
    ModuleType,
    SignalConfig,
)
from hermes.core.process import ModuleState, ProcessManager
from hermes.core.scheduler import Scheduler


class TestConfigToExecution:
    """Test loading config and setting up execution."""

    def test_config_to_process_manager(self, tmp_path: Path) -> None:
        """Config should properly initialize ProcessManager."""
        # Create a simple config
        config = HermesConfig(
            modules={
                "test_module": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script=str(tmp_path / "dummy.py"),
                    signals=[
                        SignalConfig(name="output", type="f64"),
                    ],
                )
            },
            execution=ExecutionConfig(
                mode=ExecutionMode.AFAP,
                rate_hz=100.0,
                end_time=0.1,
            ),
        )

        # Create dummy script
        (tmp_path / "dummy.py").write_text("# Dummy module\nimport time\ntime.sleep(0.1)")

        pm = ProcessManager(config)
        try:
            pm.initialize()

            # Verify shared memory was created
            assert pm.shm is not None
            assert pm.shm.is_attached

            # Verify module was registered
            assert "test_module" in pm.modules
            assert pm.modules["test_module"].state == ModuleState.INIT

        finally:
            pm.terminate_all()

    def test_yaml_config_loading(self, tmp_path: Path) -> None:
        """YAML config should load and validate correctly."""
        yaml_content = """\
version: "0.2"
modules:
  sensor:
    type: script
    script: ./sensor.py
    signals:
      - name: temperature
        type: f64
        unit: C
      - name: pressure
        type: f64
        unit: Pa
  controller:
    type: script
    script: ./controller.py
    signals:
      - name: command
        type: f64
        writable: true
execution:
  mode: afap
  rate_hz: 50.0
  end_time: 1.0
  schedule:
    - sensor
    - controller
"""
        config_file = tmp_path / "sim.yaml"
        config_file.write_text(yaml_content)

        # Create dummy scripts
        (tmp_path / "sensor.py").write_text("# Sensor module")
        (tmp_path / "controller.py").write_text("# Controller module")

        config = HermesConfig.from_yaml(config_file)

        assert len(config.modules) == 2
        assert "sensor" in config.modules
        assert "controller" in config.modules
        assert config.execution.rate_hz == 50.0
        assert config.execution.end_time == 1.0
        assert config.get_module_names() == ["sensor", "controller"]


class TestModuleLifecycle:
    """Tests for module process lifecycle."""

    def test_module_state_transitions(self, tmp_path: Path) -> None:
        """Module should transition through expected states."""
        # Create a simple script that exits immediately
        script = tmp_path / "simple_module.py"
        script.write_text(
            textwrap.dedent("""
            import sys
            import os
            # Module that just exits
            sys.exit(0)
        """)
        )

        config = HermesConfig(
            modules={
                "simple": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script=str(script),
                    signals=[],
                )
            }
        )

        pm = ProcessManager(config)
        try:
            pm.initialize()
            module = pm.modules["simple"]

            # Initial state after initialize
            assert module.state == ModuleState.INIT

            # After staging
            module.stage()
            assert module.state == ModuleState.STAGED

            # After mark_running
            module.mark_running()
            assert module.state == ModuleState.RUNNING

        finally:
            pm.terminate_all()


class TestSharedMemoryIntegration:
    """Integration tests for shared memory with real processes."""

    def test_shm_persist_across_attach_detach(self) -> None:
        """Data should persist when detaching and reattaching."""
        import uuid

        shm_name = f"/hermes_persist_{uuid.uuid4().hex[:8]}"
        signals = [
            SignalDescriptor(name="sig1", type=SignalType.F64),
            SignalDescriptor(name="sig2", type=SignalType.F64),
        ]

        creator = SharedMemoryManager(shm_name)
        try:
            creator.create(signals)

            # Write data
            creator.set_signal("sig1", 100.0)
            creator.set_signal("sig2", 200.0)
            creator.set_frame(42)
            creator.set_time_ns(1_234_567_890)

            # Detach creator
            creator.detach()

            # Reattach
            reader = SharedMemoryManager(shm_name)
            reader.attach()

            # Data should be preserved
            assert reader.get_signal("sig1") == 100.0
            assert reader.get_signal("sig2") == 200.0
            assert reader.get_frame() == 42
            assert reader.get_time_ns() == 1_234_567_890

            reader.detach()

        finally:
            creator.destroy()

    def test_shm_with_many_signals(self) -> None:
        """Should handle many signals efficiently."""
        import uuid

        shm_name = f"/hermes_many_{uuid.uuid4().hex[:8]}"

        # Create 100 signals
        signals = [
            SignalDescriptor(name=f"signal_{i:03d}", type=SignalType.F64) for i in range(100)
        ]

        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)

            # Write all signals
            for i in range(100):
                shm.set_signal(f"signal_{i:03d}", float(i * 10))

            # Read all signals back
            for i in range(100):
                value = shm.get_signal(f"signal_{i:03d}")
                assert value == float(i * 10)

            # Verify signal count
            assert len(shm.signal_names()) == 100

        finally:
            shm.destroy()


class TestBarrierSynchronization:
    """Integration tests for barrier synchronization."""

    def test_barrier_multiple_complete_cycles(self) -> None:
        """Barrier should handle many complete step/done cycles."""
        import uuid

        barrier_name = f"/hermes_cycles_{uuid.uuid4().hex[:8]}"

        barrier = FrameBarrier(barrier_name, count=1)
        try:
            barrier.create()

            # Run 1000 cycles
            for i in range(1000):
                barrier.signal_step()
                assert barrier.wait_step(timeout=1.0), f"Failed wait_step at cycle {i}"
                barrier.signal_done()
                assert barrier.wait_all_done(timeout=1.0), f"Failed wait_done at cycle {i}"

        finally:
            barrier.destroy()

    def test_barrier_with_fork(self) -> None:
        """Barrier should synchronize across fork."""
        import uuid

        barrier_name = f"/hermes_fork_{uuid.uuid4().hex[:8]}"

        barrier = FrameBarrier(barrier_name, count=1)
        try:
            barrier.create()

            pid = os.fork()
            if pid == 0:
                # Child process
                try:
                    child_barrier = FrameBarrier(barrier_name, 1)
                    child_barrier.attach()

                    # Wait for parent to signal
                    if not child_barrier.wait_step(timeout=5.0):
                        os._exit(1)

                    # Signal done
                    child_barrier.signal_done()
                    child_barrier.close()
                    os._exit(0)
                except Exception:
                    os._exit(2)
            else:
                # Parent process
                import time

                time.sleep(0.1)  # Give child time to attach

                barrier.signal_step()
                result = barrier.wait_all_done(timeout=5.0)

                _, status = os.waitpid(pid, 0)
                assert os.WEXITSTATUS(status) == 0
                assert result is True

        finally:
            barrier.destroy()


class TestSchedulerIntegration:
    """Integration tests for scheduler with real components."""

    def test_scheduler_with_real_shm(self, tmp_path: Path) -> None:
        """Scheduler should update real shared memory correctly."""
        config = HermesConfig(
            modules={
                "test": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script=str(tmp_path / "test.py"),
                    signals=[SignalConfig(name="x", type="f64")],
                )
            },
            execution=ExecutionConfig(
                mode=ExecutionMode.AFAP,
                rate_hz=100.0,
                end_time=0.1,
            ),
        )

        # Create dummy script
        (tmp_path / "test.py").write_text("# Test module")

        pm = ProcessManager(config)
        try:
            pm.initialize()

            # Manually check SHM state
            shm = pm.shm
            assert shm is not None

            # Update time via process manager
            pm.update_time(0, 0)
            assert shm.get_frame() == 0
            assert shm.get_time_ns() == 0

            pm.update_time(10, 100_000_000)  # 100ms
            assert shm.get_frame() == 10
            assert shm.get_time_ns() == 100_000_000

        finally:
            pm.terminate_all()

    @pytest.mark.asyncio
    async def test_scheduler_run_with_mock_pm(self) -> None:
        """Scheduler run() should execute expected number of frames."""
        from unittest.mock import MagicMock

        mock_pm = MagicMock()
        config = ExecutionConfig(
            mode=ExecutionMode.AFAP,
            rate_hz=100.0,
            end_time=0.05,  # 5 frames
        )

        scheduler = Scheduler(mock_pm, config)

        frames_seen: list[tuple[int, int]] = []

        async def track_frames(frame: int, _time: float) -> None:
            frames_seen.append((frame, scheduler.time_ns))

        await scheduler.run(callback=track_frames)

        # Should have at least 5 frames
        assert len(frames_seen) >= 5

        # Verify deterministic time progression
        for _, (frame, time_ns) in enumerate(frames_seen):
            expected_ns = frame * 10_000_000  # 100 Hz = 10ms per frame
            assert time_ns == expected_ns, f"Frame {frame} has wrong time_ns"


class TestDeterministicExecution:
    """Tests verifying deterministic execution properties."""

    def test_identical_runs_produce_identical_results(self) -> None:
        """Multiple runs with same config should produce identical results."""
        from unittest.mock import MagicMock

        config = ExecutionConfig(
            mode=ExecutionMode.AFAP,
            rate_hz=60.0,  # Non-trivial rate
            end_time=1.0,  # 60 frames
        )

        results: list[list[tuple[int, int]]] = []

        for _ in range(3):
            mock_pm = MagicMock()
            scheduler = Scheduler(mock_pm, config)

            run_results: list[tuple[int, int]] = []
            for _ in range(60):
                scheduler.step(1)
                run_results.append((scheduler.frame, scheduler.time_ns))

            results.append(run_results)

        # All runs should be identical
        assert results[0] == results[1] == results[2]

    def test_non_divisible_rate_still_deterministic(self) -> None:
        """Rates that don't divide evenly into 1 billion should still be deterministic."""
        from unittest.mock import MagicMock

        # 333 Hz doesn't divide evenly into 1 billion
        config = ExecutionConfig(rate_hz=333.0, mode=ExecutionMode.AFAP)

        results = []
        for _ in range(5):
            mock_pm = MagicMock()
            scheduler = Scheduler(mock_pm, config)
            scheduler.step(10000)
            results.append((scheduler.frame, scheduler.time_ns))

        # All runs should produce identical results
        assert len(set(results)) == 1

    def test_time_never_goes_backwards(self) -> None:
        """Time should monotonically increase."""
        from unittest.mock import MagicMock

        mock_pm = MagicMock()
        config = ExecutionConfig(rate_hz=1000.0, mode=ExecutionMode.AFAP)
        scheduler = Scheduler(mock_pm, config)

        prev_time_ns = -1
        for _ in range(10000):
            scheduler.step(1)
            assert scheduler.time_ns > prev_time_ns, "Time went backwards!"
            prev_time_ns = scheduler.time_ns
