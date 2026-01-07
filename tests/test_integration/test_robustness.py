"""Robustness and correctness tests for Hermes core components.

These tests verify:
1. Deterministic behavior across multiple runs
2. Resource cleanup on normal and error paths
3. Edge cases and boundary conditions
4. Error propagation and recovery
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.backplane.sync import FrameBarrier
from hermes.core.config import ExecutionConfig, ExecutionMode
from hermes.core.scheduler import Scheduler


class TestSchedulerDeterminismExtended:
    """Extended determinism tests for the scheduler."""

    @pytest.fixture
    def mock_pm(self) -> MagicMock:
        """Create mock ProcessManager."""
        pm = MagicMock()
        pm.stage_all = MagicMock()
        pm.step_all = MagicMock()
        pm.update_time = MagicMock()
        return pm

    def test_determinism_large_frame_count(self, mock_pm: MagicMock) -> None:
        """Time should remain deterministic over very large frame counts."""
        config = ExecutionConfig(rate_hz=1000.0, mode=ExecutionMode.AFAP)
        scheduler = Scheduler(mock_pm, config)

        # Run 1 million frames (1000 seconds at 1000 Hz)
        scheduler.step(1_000_000)

        # Should be exactly 1_000_000 * 1_000_000 ns = 1e12 ns = 1000 seconds
        assert scheduler.time_ns == 1_000_000_000_000
        assert scheduler.frame == 1_000_000
        assert scheduler.time == 1000.0

    def test_determinism_multiple_schedulers_same_config(self, mock_pm: MagicMock) -> None:
        """Multiple schedulers with same config should produce identical results."""
        config = ExecutionConfig(rate_hz=333.0, mode=ExecutionMode.AFAP)

        schedulers = [Scheduler(mock_pm, config) for _ in range(5)]

        # Step each scheduler the same number of times
        for sched in schedulers:
            sched.step(10000)

        # All should have identical time_ns
        times = [s.time_ns for s in schedulers]
        assert len(set(times)) == 1, "All schedulers should have same time_ns"

        # All should have identical frame counts
        frames = [s.frame for s in schedulers]
        assert len(set(frames)) == 1, "All schedulers should have same frame count"

    def test_determinism_step_by_step_vs_batch(self, mock_pm: MagicMock) -> None:
        """Stepping one at a time vs batch should produce identical results."""
        config = ExecutionConfig(rate_hz=60.0, mode=ExecutionMode.AFAP)

        # Scheduler 1: step one at a time
        sched1 = Scheduler(mock_pm, config)
        for _ in range(1000):
            sched1.step(1)

        # Scheduler 2: step in batches
        sched2 = Scheduler(mock_pm, config)
        sched2.step(1000)

        assert sched1.time_ns == sched2.time_ns
        assert sched1.frame == sched2.frame

    def test_determinism_after_reset(self, mock_pm: MagicMock) -> None:
        """After reset, time sequence should be identical to fresh start."""
        config = ExecutionConfig(rate_hz=100.0, mode=ExecutionMode.AFAP)

        # First run
        sched1 = Scheduler(mock_pm, config)
        times1 = []
        for _ in range(100):
            sched1.step(1)
            times1.append(sched1.time_ns)

        # Second run with reset
        sched2 = Scheduler(mock_pm, config)
        sched2.step(50)  # Run partway
        sched2.reset()  # Reset
        times2 = []
        for _ in range(100):
            sched2.step(1)
            times2.append(sched2.time_ns)

        assert times1 == times2

    def test_various_rates_determinism(self, mock_pm: MagicMock) -> None:
        """Various rates should all be deterministic over many frames."""
        rates = [1.0, 10.0, 30.0, 60.0, 100.0, 120.0, 240.0, 500.0, 1000.0]

        for rate in rates:
            config = ExecutionConfig(rate_hz=rate, mode=ExecutionMode.AFAP)

            # Run twice with same config
            results = []
            for _ in range(2):
                sched = Scheduler(mock_pm, config)
                sched.step(1000)
                results.append((sched.frame, sched.time_ns))

            assert results[0] == results[1], f"Rate {rate} Hz not deterministic"


class TestSharedMemoryRobustness:
    """Robustness tests for SharedMemoryManager."""

    @pytest.fixture
    def shm_name(self) -> str:
        """Generate unique shared memory name."""
        return f"/hermes_robust_test_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def test_signals(self) -> list[SignalDescriptor]:
        """Create test signals."""
        return [
            SignalDescriptor(name="sig1", type=SignalType.F64),
            SignalDescriptor(name="sig2", type=SignalType.F32),
            SignalDescriptor(name="sig3", type=SignalType.I64),
        ]

    def test_time_ns_boundary_values(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Time should handle large nanosecond values without overflow."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # Test various large time values
            test_values = [
                0,
                1,
                1_000_000_000,  # 1 second
                60_000_000_000,  # 1 minute
                3_600_000_000_000,  # 1 hour
                86_400_000_000_000,  # 1 day
                31_536_000_000_000_000,  # 1 year
                2**62,  # Large value within u64 range
            ]

            for val in test_values:
                shm.set_time_ns(val)
                assert shm.get_time_ns() == val, f"Failed for value {val}"

        finally:
            shm.destroy()

    def test_frame_boundary_values(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Frame counter should handle large values."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            test_values = [
                0,
                1,
                1000,
                1_000_000,
                1_000_000_000,
                2**32 - 1,  # Max u32
                2**32,  # Just past u32
                2**62,  # Large value
            ]

            for val in test_values:
                shm.set_frame(val)
                assert shm.get_frame() == val, f"Failed for frame {val}"

        finally:
            shm.destroy()

    def test_signal_values_precision(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Signal values should maintain floating point precision."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            # Test various floating point values
            test_values = [
                0.0,
                1.0,
                -1.0,
                3.141592653589793,  # Pi
                2.718281828459045,  # e
                1e-10,  # Very small
                1e10,  # Very large
                float("inf"),
                float("-inf"),
            ]

            for val in test_values:
                shm.set_signal("sig1", val)
                retrieved = shm.get_signal("sig1")
                assert retrieved == val, f"Failed for value {val}"

        finally:
            shm.destroy()

    def test_concurrent_read_write(
        self, shm_name: str, test_signals: list[SignalDescriptor]
    ) -> None:
        """Creator and attacher should see consistent data."""
        creator = SharedMemoryManager(shm_name)
        try:
            creator.create(test_signals)

            # Attach second manager
            attacher = SharedMemoryManager(shm_name)
            attacher.attach()

            try:
                # Write from creator, read from attacher
                creator.set_signal("sig1", 42.0)
                creator.set_frame(100)
                creator.set_time_ns(1_000_000_000)

                assert attacher.get_signal("sig1") == 42.0
                assert attacher.get_frame() == 100
                assert attacher.get_time_ns() == 1_000_000_000

                # Write from attacher, read from creator
                attacher.set_signal("sig2", 123.456)
                assert creator.get_signal("sig2") == pytest.approx(123.456, rel=1e-6)

            finally:
                attacher.detach()
        finally:
            creator.destroy()

    def test_empty_signals_list(self, shm_name: str) -> None:
        """Should handle empty signals list gracefully."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create([])  # Empty list

            # Basic operations should still work
            shm.set_frame(10)
            assert shm.get_frame() == 10

            shm.set_time_ns(500)
            assert shm.get_time_ns() == 500

            # No signals to read
            assert shm.signal_names() == []

        finally:
            shm.destroy()

    def test_destroy_idempotent(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Destroy should be safe to call multiple times."""
        shm = SharedMemoryManager(shm_name)
        shm.create(test_signals)

        # First destroy
        shm.destroy()
        assert shm.is_attached is False

        # Second destroy should not raise
        shm.destroy()
        assert shm.is_attached is False

    def test_detach_idempotent(self, shm_name: str, test_signals: list[SignalDescriptor]) -> None:
        """Detach should be safe to call multiple times."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(test_signals)

            shm.detach()
            assert shm.is_attached is False

            # Second detach should not raise
            shm.detach()
            assert shm.is_attached is False
        finally:
            # Clean up underlying shm
            import contextlib

            import posix_ipc

            with contextlib.suppress(posix_ipc.ExistentialError):
                posix_ipc.unlink_shared_memory(shm_name)


class TestFrameBarrierRobustness:
    """Robustness tests for FrameBarrier."""

    @pytest.fixture
    def barrier_name(self) -> str:
        """Generate unique barrier name."""
        return f"/hermes_barrier_robust_{uuid.uuid4().hex[:8]}"

    def test_invalid_count_zero(self, barrier_name: str) -> None:
        """Should reject count of zero."""
        with pytest.raises(ValueError, match="at least 1"):
            FrameBarrier(barrier_name, 0)

    def test_invalid_count_negative(self, barrier_name: str) -> None:
        """Should reject negative count."""
        with pytest.raises(ValueError, match="at least 1"):
            FrameBarrier(barrier_name, -1)

    def test_destroy_idempotent(self, barrier_name: str) -> None:
        """Destroy should be safe to call multiple times."""
        barrier = FrameBarrier(barrier_name, 1)
        barrier.create()

        barrier.destroy()
        # Second destroy should not raise
        barrier.destroy()

    def test_close_idempotent(self, barrier_name: str) -> None:
        """Close should be safe to call multiple times."""
        creator = FrameBarrier(barrier_name, 1)
        creator.create()

        try:
            client = FrameBarrier(barrier_name, 1)
            client.attach()

            client.close()
            # Second close should not raise
            client.close()
        finally:
            creator.destroy()

    def test_rapid_signal_cycles(self, barrier_name: str) -> None:
        """Should handle rapid signal/wait cycles."""
        barrier = FrameBarrier(barrier_name, 1)
        try:
            barrier.create()

            # Run many rapid cycles
            for _ in range(100):
                barrier.signal_step()
                assert barrier.wait_step(timeout=1.0) is True
                barrier.signal_done()
                assert barrier.wait_all_done(timeout=1.0) is True

        finally:
            barrier.destroy()


class TestResourceCleanup:
    """Tests verifying proper resource cleanup."""

    def test_process_manager_cleanup_on_init_failure(self) -> None:
        """ProcessManager should clean up if initialization fails partway."""
        from hermes.core.config import HermesConfig, ModuleConfig, ModuleType
        from hermes.core.process import ProcessManager

        # Create config with nonexistent script to trigger failure during load
        config = HermesConfig(
            modules={
                "test": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script="/nonexistent/script.py",
                )
            }
        )

        pm = ProcessManager(config)

        # Initialize should succeed (doesn't load scripts yet)
        pm.initialize()

        try:
            # Verify resources were created
            assert pm._shm is not None
            assert pm._barrier is not None

        finally:
            # Cleanup
            pm.terminate_all()

        # After terminate, resources should be cleaned up
        assert pm._shm is None
        assert pm._barrier is None

    def test_scheduler_state_after_run_completes(self) -> None:
        """Scheduler should have correct state after run() completes."""
        mock_pm = MagicMock()
        config = ExecutionConfig(mode=ExecutionMode.AFAP, rate_hz=100.0, end_time=0.1)
        scheduler = Scheduler(mock_pm, config)

        import asyncio

        asyncio.run(scheduler.run())

        # After run completes, running should be False
        assert scheduler.running is False
        # Time should have reached or exceeded end_time
        assert scheduler.time >= 0.1

    @pytest.mark.asyncio
    async def test_scheduler_cleanup_on_callback_error(self) -> None:
        """Scheduler should clean up properly if callback raises."""
        mock_pm = MagicMock()
        config = ExecutionConfig(mode=ExecutionMode.AFAP, rate_hz=100.0, end_time=1.0)
        scheduler = Scheduler(mock_pm, config)

        async def failing_callback(frame: int, _time: float) -> None:
            if frame >= 5:
                raise RuntimeError("Callback error")

        with pytest.raises(RuntimeError, match="Callback error"):
            await scheduler.run(callback=failing_callback)

        # After error, running should be False
        assert scheduler.running is False


class TestErrorPropagation:
    """Tests for proper error propagation."""

    def test_shm_operations_when_not_attached(self) -> None:
        """All SHM operations should fail cleanly when not attached."""
        shm = SharedMemoryManager("/test_not_attached")

        with pytest.raises(RuntimeError, match="Not attached"):
            shm.get_signal("test")

        with pytest.raises(RuntimeError, match="Not attached"):
            shm.set_signal("test", 1.0)

        with pytest.raises(RuntimeError, match="Not attached"):
            shm.get_frame()

        with pytest.raises(RuntimeError, match="Not attached"):
            shm.set_frame(1)

        with pytest.raises(RuntimeError, match="Not attached"):
            shm.get_time_ns()

        with pytest.raises(RuntimeError, match="Not attached"):
            shm.set_time_ns(1)

    def test_barrier_operations_when_not_created(self) -> None:
        """All barrier operations should fail cleanly when not created."""
        barrier = FrameBarrier("/test_not_created", 1)

        with pytest.raises(RuntimeError, match="not created"):
            barrier.signal_step()

        with pytest.raises(RuntimeError, match="not created"):
            barrier.wait_step()

        with pytest.raises(RuntimeError, match="not created"):
            barrier.signal_done()

        with pytest.raises(RuntimeError, match="not created"):
            barrier.wait_all_done()

    def test_scheduler_step_invalid_count(self) -> None:
        """Scheduler.step() should reject invalid counts."""
        mock_pm = MagicMock()
        config = ExecutionConfig(rate_hz=100.0)
        scheduler = Scheduler(mock_pm, config)

        with pytest.raises(ValueError, match="positive"):
            scheduler.step(0)

        with pytest.raises(ValueError, match="positive"):
            scheduler.step(-5)

    def test_unknown_signal_raises_keyerror(self) -> None:
        """Accessing unknown signal should raise KeyError."""
        shm_name = f"/hermes_keyerror_test_{uuid.uuid4().hex[:8]}"
        signals = [SignalDescriptor(name="exists", type=SignalType.F64)]

        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)

            # Known signal works
            shm.set_signal("exists", 1.0)
            assert shm.get_signal("exists") == 1.0

            # Unknown signal raises KeyError
            with pytest.raises(KeyError, match="not_exists"):
                shm.get_signal("not_exists")

            with pytest.raises(KeyError, match="not_exists"):
                shm.set_signal("not_exists", 1.0)

        finally:
            shm.destroy()


class TestEdgeCases:
    """Edge case tests for various components."""

    def test_time_conversion_precision(self) -> None:
        """Float/nanosecond conversion should maintain precision."""
        shm_name = f"/hermes_precision_test_{uuid.uuid4().hex[:8]}"
        signals = [SignalDescriptor(name="test", type=SignalType.F64)]

        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)

            # Set time via float
            shm.set_time(1.5)
            assert shm.get_time_ns() == 1_500_000_000
            assert shm.get_time() == 1.5

            # Set time via nanoseconds
            shm.set_time_ns(2_500_000_000)
            assert shm.get_time() == 2.5

        finally:
            shm.destroy()

    def test_very_high_rate_determinism(self) -> None:
        """Very high rates should still be deterministic."""
        mock_pm = MagicMock()
        config = ExecutionConfig(rate_hz=10000.0, mode=ExecutionMode.AFAP)

        results = []
        for _ in range(3):
            sched = Scheduler(mock_pm, config)
            sched.step(100000)
            results.append((sched.frame, sched.time_ns, sched.time))

        # All runs identical
        assert results[0] == results[1] == results[2]

    def test_very_low_rate_determinism(self) -> None:
        """Very low rates should still be deterministic."""
        mock_pm = MagicMock()
        config = ExecutionConfig(rate_hz=0.1, mode=ExecutionMode.AFAP)

        results = []
        for _ in range(3):
            sched = Scheduler(mock_pm, config)
            sched.step(10)  # 100 seconds worth
            results.append((sched.frame, sched.time_ns, sched.time))

        # All runs identical
        assert results[0] == results[1] == results[2]

        # Verify correctness: 10 frames at 0.1 Hz = 100 seconds
        assert results[0][0] == 10  # 10 frames
        assert results[0][1] == 100_000_000_000  # 100 seconds in ns
        assert results[0][2] == 100.0  # 100 seconds
