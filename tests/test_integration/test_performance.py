"""Performance profiling tests for Hermes core components.

These tests measure and validate performance characteristics:
1. Shared memory read/write latency
2. Barrier synchronization overhead
3. Scheduler throughput
4. Signal access patterns

Note: These tests verify performance meets reasonable thresholds.
Actual numbers will vary by hardware. The thresholds are set
conservatively to catch regressions, not to guarantee specific perf.
"""

from __future__ import annotations

import statistics
import time
import uuid
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.backplane.sync import FrameBarrier
from hermes.core.config import ExecutionConfig, ExecutionMode
from hermes.core.scheduler import Scheduler


def measure_latency_ns(
    func: Callable[[], None], iterations: int = 1000, warmup: int = 100
) -> dict[str, float]:
    """Measure function latency in nanoseconds.

    Returns dict with min, max, mean, median, std_dev, p99 latencies.
    """
    # Warmup
    for _ in range(warmup):
        func()

    # Measure
    latencies: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        func()
        end = time.perf_counter_ns()
        latencies.append(end - start)

    latencies_sorted = sorted(latencies)
    p99_idx = int(len(latencies) * 0.99)

    return {
        "min_ns": min(latencies),
        "max_ns": max(latencies),
        "mean_ns": statistics.mean(latencies),
        "median_ns": statistics.median(latencies),
        "std_dev_ns": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "p99_ns": latencies_sorted[p99_idx],
        "iterations": iterations,
    }


def measure_throughput(func: Callable[[], None], duration_seconds: float = 1.0) -> dict[str, float]:
    """Measure function throughput (operations per second)."""
    count = 0
    start = time.perf_counter()
    end_time = start + duration_seconds

    while time.perf_counter() < end_time:
        func()
        count += 1

    elapsed = time.perf_counter() - start
    return {
        "operations": count,
        "elapsed_seconds": elapsed,
        "ops_per_second": count / elapsed,
    }


class TestSharedMemoryPerformance:
    """Performance tests for SharedMemoryManager."""

    @pytest.fixture
    def shm_name(self) -> str:
        return f"/hermes_perf_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def signals(self) -> list[SignalDescriptor]:
        """Create signals for testing."""
        return [SignalDescriptor(name=f"signal_{i:03d}", type=SignalType.F64) for i in range(10)]

    def test_signal_read_latency(self, shm_name: str, signals: list[SignalDescriptor]) -> None:
        """Signal reads should have sub-microsecond median latency."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)
            shm.set_signal("signal_000", 42.0)

            stats = measure_latency_ns(lambda: shm.get_signal("signal_000"))

            print("\nSignal read latency:")
            print(f"  Min: {stats['min_ns']} ns")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  Mean: {stats['mean_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")
            print(f"  Max: {stats['max_ns']} ns")

            # Median should be under 10 microseconds (very conservative)
            assert stats["median_ns"] < 10_000, "Signal read too slow"

        finally:
            shm.destroy()

    def test_signal_write_latency(self, shm_name: str, signals: list[SignalDescriptor]) -> None:
        """Signal writes should have sub-microsecond median latency."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)
            value = 0.0

            def write_signal() -> None:
                nonlocal value
                shm.set_signal("signal_000", value)
                value += 1.0

            stats = measure_latency_ns(write_signal)

            print("\nSignal write latency:")
            print(f"  Min: {stats['min_ns']} ns")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  Mean: {stats['mean_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")
            print(f"  Max: {stats['max_ns']} ns")

            # Median should be under 10 microseconds
            assert stats["median_ns"] < 10_000, "Signal write too slow"

        finally:
            shm.destroy()

    def test_frame_time_update_latency(
        self, shm_name: str, signals: list[SignalDescriptor]
    ) -> None:
        """Frame/time header updates should be fast."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)
            frame = 0

            def update_header() -> None:
                nonlocal frame
                shm.set_frame(frame)
                shm.set_time_ns(frame * 10_000_000)
                frame += 1

            stats = measure_latency_ns(update_header)

            print("\nFrame/time update latency:")
            print(f"  Min: {stats['min_ns']} ns")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  Mean: {stats['mean_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")

            # Median should be under 10 microseconds
            assert stats["median_ns"] < 10_000, "Header update too slow"

        finally:
            shm.destroy()

    def test_many_signals_access_pattern(self, shm_name: str) -> None:
        """Accessing many signals should scale reasonably."""
        signal_counts = [10, 50, 100, 200]
        results: list[tuple[int, float]] = []

        for count in signal_counts:
            signals = [
                SignalDescriptor(name=f"sig_{i:04d}", type=SignalType.F64) for i in range(count)
            ]

            shm = SharedMemoryManager(shm_name)
            try:
                shm.create(signals)

                # Write all signals
                for i in range(count):
                    shm.set_signal(f"sig_{i:04d}", float(i))

                # Measure reading all signals
                # Bind loop variables via default args to avoid late binding
                def read_all(shm: SharedMemoryManager = shm, count: int = count) -> None:
                    for i in range(count):
                        shm.get_signal(f"sig_{i:04d}")

                stats = measure_latency_ns(read_all, iterations=100, warmup=10)
                per_signal_ns = stats["median_ns"] / count
                results.append((count, per_signal_ns))

                print(
                    f"\n{count} signals: {stats['median_ns']:.0f} ns total, "
                    f"{per_signal_ns:.0f} ns/signal"
                )

            finally:
                shm.destroy()

        # Per-signal access time should not increase dramatically with count
        # (should be O(1) lookup, not O(n))
        first_per_signal = results[0][1]
        last_per_signal = results[-1][1]

        # Allow 3x degradation (accounts for cache effects)
        assert last_per_signal < first_per_signal * 3, "Signal access does not scale well"

    def test_signal_throughput(self, shm_name: str, signals: list[SignalDescriptor]) -> None:
        """Measure signal read/write throughput."""
        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)
            shm.set_signal("signal_000", 0.0)

            # Read throughput
            read_stats = measure_throughput(
                lambda: shm.get_signal("signal_000"),
                duration_seconds=0.5,
            )

            # Write throughput
            value = [0.0]  # Use list for closure

            def write() -> None:
                shm.set_signal("signal_000", value[0])
                value[0] += 1.0

            write_stats = measure_throughput(write, duration_seconds=0.5)

            print("\nSignal throughput:")
            print(f"  Reads: {read_stats['ops_per_second']:,.0f} ops/sec")
            print(f"  Writes: {write_stats['ops_per_second']:,.0f} ops/sec")

            # Should achieve at least 100k ops/sec
            assert read_stats["ops_per_second"] > 100_000, "Read throughput too low"
            assert write_stats["ops_per_second"] > 100_000, "Write throughput too low"

        finally:
            shm.destroy()


class TestBarrierPerformance:
    """Performance tests for FrameBarrier."""

    @pytest.fixture
    def barrier_name(self) -> str:
        return f"/hermes_barrier_perf_{uuid.uuid4().hex[:8]}"

    def test_signal_step_latency(self, barrier_name: str) -> None:
        """signal_step() should have low latency."""
        barrier = FrameBarrier(barrier_name, count=1)
        try:
            barrier.create()

            # Need to drain the semaphore after each signal
            def signal_and_drain() -> None:
                barrier.signal_step()
                barrier.wait_step(timeout=0.001)

            stats = measure_latency_ns(signal_and_drain, iterations=1000)

            print("\nBarrier signal+wait latency:")
            print(f"  Min: {stats['min_ns']} ns")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  Mean: {stats['mean_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")

            # Median should be under 100 microseconds
            assert stats["median_ns"] < 100_000, "Barrier signal too slow"

        finally:
            barrier.destroy()

    def test_full_cycle_latency(self, barrier_name: str) -> None:
        """Full step/done cycle should have reasonable latency."""
        barrier = FrameBarrier(barrier_name, count=1)
        try:
            barrier.create()

            def full_cycle() -> None:
                barrier.signal_step()
                barrier.wait_step(timeout=0.01)
                barrier.signal_done()
                barrier.wait_all_done(timeout=0.01)

            stats = measure_latency_ns(full_cycle, iterations=500, warmup=50)

            print("\nFull barrier cycle latency:")
            print(f"  Min: {stats['min_ns']} ns")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  Mean: {stats['mean_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")

            # Full cycle median should be under 500 microseconds
            assert stats["median_ns"] < 500_000, "Full barrier cycle too slow"

        finally:
            barrier.destroy()

    def test_barrier_throughput(self, barrier_name: str) -> None:
        """Measure barrier cycle throughput."""
        barrier = FrameBarrier(barrier_name, count=1)
        try:
            barrier.create()

            def full_cycle() -> None:
                barrier.signal_step()
                barrier.wait_step(timeout=0.01)
                barrier.signal_done()
                barrier.wait_all_done(timeout=0.01)

            stats = measure_throughput(full_cycle, duration_seconds=0.5)

            print(f"\nBarrier throughput: {stats['ops_per_second']:,.0f} cycles/sec")

            # Should achieve at least 1000 cycles/sec
            # (enough for 1000 Hz simulation rate)
            assert stats["ops_per_second"] > 1000, "Barrier throughput too low"

        finally:
            barrier.destroy()


class TestSchedulerPerformance:
    """Performance tests for Scheduler."""

    @pytest.fixture
    def mock_pm(self) -> MagicMock:
        """Create a minimal mock ProcessManager."""
        pm = MagicMock()
        pm.stage_all = MagicMock()
        pm.step_all = MagicMock()
        pm.update_time = MagicMock()
        return pm

    def test_step_latency(self, mock_pm: MagicMock) -> None:
        """Scheduler.step() should have low overhead."""
        config = ExecutionConfig(rate_hz=1000.0, mode=ExecutionMode.AFAP)
        scheduler = Scheduler(mock_pm, config)

        stats = measure_latency_ns(lambda: scheduler.step(1), iterations=10000)

        print("\nScheduler step latency:")
        print(f"  Min: {stats['min_ns']} ns")
        print(f"  Median: {stats['median_ns']:.0f} ns")
        print(f"  Mean: {stats['mean_ns']:.0f} ns")
        print(f"  P99: {stats['p99_ns']} ns")

        # With mocked PM, step should be very fast
        assert stats["median_ns"] < 50_000, "Scheduler step too slow"

    def test_step_throughput(self, mock_pm: MagicMock) -> None:
        """Measure scheduler step throughput."""
        config = ExecutionConfig(rate_hz=1000.0, mode=ExecutionMode.AFAP)
        scheduler = Scheduler(mock_pm, config)

        stats = measure_throughput(lambda: scheduler.step(1), duration_seconds=0.5)

        print(f"\nScheduler throughput: {stats['ops_per_second']:,.0f} steps/sec")

        # Should achieve at least 10k steps/sec with mock PM
        assert stats["ops_per_second"] > 10_000, "Scheduler throughput too low"

    def test_time_calculation_overhead(self, mock_pm: MagicMock) -> None:
        """Time calculations should add minimal overhead."""
        config = ExecutionConfig(rate_hz=1000.0, mode=ExecutionMode.AFAP)
        scheduler = Scheduler(mock_pm, config)

        # Measure time property access
        def access_time() -> None:
            _ = scheduler.time
            _ = scheduler.time_ns
            _ = scheduler.frame

        stats = measure_latency_ns(access_time, iterations=10000)

        print("\nTime property access latency:")
        print(f"  Median: {stats['median_ns']:.0f} ns")

        # Property access should be essentially instant
        assert stats["median_ns"] < 1_000, "Time access too slow"

    def test_high_frequency_simulation(self, mock_pm: MagicMock) -> None:
        """Verify scheduler can support high frequency rates."""
        # Test if we can achieve 10kHz rate (100 microsecond steps)
        config = ExecutionConfig(rate_hz=10000.0, mode=ExecutionMode.AFAP)
        scheduler = Scheduler(mock_pm, config)

        # Run 10000 steps and measure total time
        start = time.perf_counter()
        scheduler.step(10000)
        elapsed = time.perf_counter() - start

        steps_per_second = 10000 / elapsed
        time_per_step_us = (elapsed / 10000) * 1_000_000

        print("\nHigh frequency test (10kHz target):")
        print(f"  Achieved: {steps_per_second:,.0f} steps/sec")
        print(f"  Time per step: {time_per_step_us:.2f} µs")

        # Should easily exceed 10kHz with mocked PM
        assert steps_per_second > 10000, "Cannot achieve 10kHz rate"


class TestIntegratedPerformance:
    """Performance tests with real components integrated."""

    def test_shm_update_in_loop(self) -> None:
        """Measure realistic SHM update pattern in simulation loop."""
        shm_name = f"/hermes_loop_perf_{uuid.uuid4().hex[:8]}"
        signals = [
            SignalDescriptor(name=f"module.signal_{i}", type=SignalType.F64) for i in range(20)
        ]

        shm = SharedMemoryManager(shm_name)
        try:
            shm.create(signals)

            frame = 0

            def simulation_step() -> None:
                nonlocal frame
                # Update header
                shm.set_frame(frame)
                shm.set_time_ns(frame * 10_000_000)

                # Update some signals (simulating module outputs)
                for i in range(5):
                    shm.set_signal(f"module.signal_{i}", float(frame + i))

                # Read some signals (simulating module inputs)
                for i in range(5, 10):
                    _ = shm.get_signal(f"module.signal_{i}")

                frame += 1

            stats = measure_latency_ns(simulation_step, iterations=1000)

            print("\nIntegrated simulation step latency:")
            print(f"  Min: {stats['min_ns']} ns")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  Mean: {stats['mean_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")

            # Realistic step should be under 100 microseconds
            assert stats["median_ns"] < 100_000, "Integrated step too slow"

            throughput = measure_throughput(simulation_step, duration_seconds=0.5)
            print(f"  Throughput: {throughput['ops_per_second']:,.0f} steps/sec")

            # Should support at least 1kHz
            assert throughput["ops_per_second"] > 1000, "Cannot achieve 1kHz"

        finally:
            shm.destroy()

    def test_scheduler_with_real_shm(self) -> None:
        """Measure scheduler performance with real SHM updates."""
        from hermes.core.config import HermesConfig, ModuleConfig, ModuleType, SignalConfig
        from hermes.core.process import ProcessManager

        # Create minimal config
        config = HermesConfig(
            modules={
                "test": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script="/dev/null",  # Won't actually run
                    signals=[SignalConfig(name="x", type="f64")],
                )
            },
            execution=ExecutionConfig(
                mode=ExecutionMode.AFAP,
                rate_hz=1000.0,
            ),
        )

        pm = ProcessManager(config)
        pm.initialize()

        try:
            # Measure update_time performance with real SHM
            frame = [0]

            def update() -> None:
                pm.update_time(frame[0], frame[0] * 1_000_000)
                frame[0] += 1

            stats = measure_latency_ns(update, iterations=1000)

            print("\nReal SHM update_time latency:")
            print(f"  Median: {stats['median_ns']:.0f} ns")
            print(f"  P99: {stats['p99_ns']} ns")

            throughput = measure_throughput(update, duration_seconds=0.5)
            print(f"  Throughput: {throughput['ops_per_second']:,.0f} updates/sec")

            assert stats["median_ns"] < 50_000, "Real SHM update too slow"

        finally:
            pm.terminate_all()


class TestMemoryEfficiency:
    """Tests for memory usage patterns."""

    def test_shm_size_scales_linearly(self) -> None:
        """Shared memory size should scale linearly with signal count."""
        import os

        results: list[tuple[int, int]] = []

        for count in [10, 50, 100, 500]:
            shm_name = f"/hermes_mem_{uuid.uuid4().hex[:8]}"
            signals = [
                SignalDescriptor(name=f"s_{i:04d}", type=SignalType.F64) for i in range(count)
            ]

            shm = SharedMemoryManager(shm_name)
            try:
                shm.create(signals)

                # Get actual shared memory size
                stat_path = f"/dev/shm{shm_name}"
                if os.path.exists(stat_path):
                    size = os.path.getsize(stat_path)
                    results.append((count, size))
                    print(f"\n{count} signals: {size} bytes ({size / count:.1f} bytes/signal)")

            finally:
                shm.destroy()

        if len(results) >= 2:
            # Check that size growth is roughly linear
            # (bytes per signal should be relatively constant)
            bytes_per_signal = [size / count for count, size in results]
            min_bps = min(bytes_per_signal)
            max_bps = max(bytes_per_signal)

            # Allow 2x variation (due to alignment, headers)
            assert max_bps < min_bps * 2, "Memory scaling not linear"
