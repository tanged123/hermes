"""Tests for binary telemetry encoding."""

from __future__ import annotations

import struct
import uuid

import pytest

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalType
from hermes.server.telemetry import TelemetryEncoder


@pytest.fixture
def shm_with_signals() -> SharedMemoryManager:
    """Create shared memory with test signals."""
    shm_name = f"/hermes_test_{uuid.uuid4().hex[:8]}"
    signals = [
        SignalDescriptor(name="sensor.x", type=SignalType.F64),
        SignalDescriptor(name="sensor.y", type=SignalType.F64),
        SignalDescriptor(name="sensor.z", type=SignalType.F64),
        SignalDescriptor(name="controller.output", type=SignalType.F64),
    ]

    shm = SharedMemoryManager(shm_name)
    shm.create(signals)

    yield shm

    shm.destroy()


class TestTelemetryEncoderConstants:
    """Tests for TelemetryEncoder constants."""

    def test_magic_value(self) -> None:
        """Magic should be 0x48455254 ('HERT' as big-endian ASCII)."""
        assert TelemetryEncoder.MAGIC == 0x48455254
        # Little-endian stores bytes in reverse order: "TREH"
        magic_bytes = struct.pack("<I", TelemetryEncoder.MAGIC)
        assert magic_bytes == b"TREH"
        # Big-endian would give "HERT"
        magic_bytes_be = struct.pack(">I", TelemetryEncoder.MAGIC)
        assert magic_bytes_be == b"HERT"

    def test_header_size(self) -> None:
        """Header should be 24 bytes."""
        assert TelemetryEncoder.HEADER_SIZE == 24
        # Verify struct format matches
        assert struct.calcsize(TelemetryEncoder.HEADER_FORMAT) == 24


class TestTelemetryEncoderCreation:
    """Tests for TelemetryEncoder creation."""

    def test_create_with_signals(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should create encoder with signal list."""
        encoder = TelemetryEncoder(shm_with_signals, ["sensor.x", "sensor.y"])

        assert encoder.signals == ["sensor.x", "sensor.y"]
        assert encoder.signal_count == 2

    def test_create_with_empty_signals(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should create encoder with empty signal list."""
        encoder = TelemetryEncoder(shm_with_signals, [])

        assert encoder.signals == []
        assert encoder.signal_count == 0

    def test_signals_list_is_copy(self, shm_with_signals: SharedMemoryManager) -> None:
        """Modifying original list should not affect encoder."""
        original = ["sensor.x", "sensor.y"]
        encoder = TelemetryEncoder(shm_with_signals, original)

        original.append("sensor.z")

        assert encoder.signals == ["sensor.x", "sensor.y"]
        assert encoder.signal_count == 2


class TestTelemetryEncoderEncode:
    """Tests for TelemetryEncoder.encode()."""

    def test_encode_empty_signals(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should encode frame with no signal values."""
        encoder = TelemetryEncoder(shm_with_signals, [])

        shm_with_signals.set_frame(42)
        shm_with_signals.set_time_ns(1_500_000_000)  # 1.5 seconds

        data = encoder.encode()

        assert len(data) == TelemetryEncoder.HEADER_SIZE
        magic, frame, time, count = struct.unpack(TelemetryEncoder.HEADER_FORMAT, data)

        assert magic == TelemetryEncoder.MAGIC
        assert frame == 42
        assert time == pytest.approx(1.5)
        assert count == 0

    def test_encode_single_signal(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should encode frame with single signal value."""
        encoder = TelemetryEncoder(shm_with_signals, ["sensor.x"])

        shm_with_signals.set_frame(100)
        shm_with_signals.set_time_ns(2_000_000_000)  # 2.0 seconds
        shm_with_signals.set_signal("sensor.x", 42.5)

        data = encoder.encode()

        assert len(data) == TelemetryEncoder.HEADER_SIZE + 8
        frame, time, values = TelemetryEncoder.decode(data)

        assert frame == 100
        assert time == pytest.approx(2.0)
        assert values == [pytest.approx(42.5)]

    def test_encode_multiple_signals(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should encode frame with multiple signal values in order."""
        encoder = TelemetryEncoder(shm_with_signals, ["sensor.x", "sensor.y", "controller.output"])

        shm_with_signals.set_frame(200)
        shm_with_signals.set_time_ns(3_500_000_000)  # 3.5 seconds
        shm_with_signals.set_signal("sensor.x", 1.0)
        shm_with_signals.set_signal("sensor.y", 2.0)
        shm_with_signals.set_signal("controller.output", 3.0)

        data = encoder.encode()

        assert len(data) == TelemetryEncoder.HEADER_SIZE + 3 * 8
        frame, time, values = TelemetryEncoder.decode(data)

        assert frame == 200
        assert time == pytest.approx(3.5)
        assert len(values) == 3
        assert values[0] == pytest.approx(1.0)
        assert values[1] == pytest.approx(2.0)
        assert values[2] == pytest.approx(3.0)

    def test_encode_preserves_signal_order(self, shm_with_signals: SharedMemoryManager) -> None:
        """Signal values should be in subscription order."""
        # Subscribe in different order than creation
        encoder = TelemetryEncoder(shm_with_signals, ["controller.output", "sensor.z", "sensor.x"])

        shm_with_signals.set_signal("sensor.x", 10.0)
        shm_with_signals.set_signal("sensor.z", 30.0)
        shm_with_signals.set_signal("controller.output", 50.0)

        data = encoder.encode()
        _, _, values = TelemetryEncoder.decode(data)

        # Order should match subscription order
        assert values == [pytest.approx(50.0), pytest.approx(30.0), pytest.approx(10.0)]

    def test_encode_unknown_signal_raises(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should raise KeyError for unknown signal."""
        encoder = TelemetryEncoder(shm_with_signals, ["nonexistent.signal"])

        with pytest.raises(KeyError, match="nonexistent.signal"):
            encoder.encode()


class TestTelemetryEncoderDecode:
    """Tests for TelemetryEncoder.decode() static method."""

    def test_decode_valid_frame(self) -> None:
        """Should decode valid binary frame."""
        # Manually construct a frame
        header = struct.pack(
            TelemetryEncoder.HEADER_FORMAT,
            TelemetryEncoder.MAGIC,
            123,  # frame
            4.5,  # time
            2,  # count
        )
        payload = struct.pack("<2d", 100.0, 200.0)
        data = header + payload

        frame, time, values = TelemetryEncoder.decode(data)

        assert frame == 123
        assert time == pytest.approx(4.5)
        assert len(values) == 2
        assert values[0] == pytest.approx(100.0)
        assert values[1] == pytest.approx(200.0)

    def test_decode_empty_values(self) -> None:
        """Should decode frame with no values."""
        header = struct.pack(
            TelemetryEncoder.HEADER_FORMAT,
            TelemetryEncoder.MAGIC,
            0,  # frame
            0.0,  # time
            0,  # count
        )

        frame, time, values = TelemetryEncoder.decode(header)

        assert frame == 0
        assert time == 0.0
        assert values == []

    def test_decode_too_short_raises(self) -> None:
        """Should raise ValueError for data shorter than header."""
        data = b"\x00" * 20  # Less than 24 bytes

        with pytest.raises(ValueError, match="Frame too short"):
            TelemetryEncoder.decode(data)

    def test_decode_invalid_magic_raises(self) -> None:
        """Should raise ValueError for invalid magic number."""
        header = struct.pack(
            TelemetryEncoder.HEADER_FORMAT,
            0xDEADBEEF,  # Wrong magic
            0,
            0.0,
            0,
        )

        with pytest.raises(ValueError, match="Invalid magic"):
            TelemetryEncoder.decode(header)

    def test_decode_truncated_payload_raises(self) -> None:
        """Should raise ValueError when payload is truncated."""
        header = struct.pack(
            TelemetryEncoder.HEADER_FORMAT,
            TelemetryEncoder.MAGIC,
            0,
            0.0,
            3,  # Claims 3 values, but we provide none
        )

        with pytest.raises(ValueError, match="Frame truncated"):
            TelemetryEncoder.decode(header)


class TestTelemetryEncoderFrameSize:
    """Tests for TelemetryEncoder.frame_size()."""

    def test_frame_size_empty(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should return header size for empty signals."""
        encoder = TelemetryEncoder(shm_with_signals, [])

        assert encoder.frame_size() == TelemetryEncoder.HEADER_SIZE

    def test_frame_size_with_signals(self, shm_with_signals: SharedMemoryManager) -> None:
        """Should return header size plus value bytes."""
        encoder = TelemetryEncoder(shm_with_signals, ["sensor.x", "sensor.y", "sensor.z"])

        expected = TelemetryEncoder.HEADER_SIZE + 3 * 8
        assert encoder.frame_size() == expected

    def test_frame_size_matches_encode_output(self, shm_with_signals: SharedMemoryManager) -> None:
        """frame_size() should match actual encoded size."""
        encoder = TelemetryEncoder(shm_with_signals, ["sensor.x", "controller.output"])

        data = encoder.encode()

        assert len(data) == encoder.frame_size()


class TestTelemetryEncoderRoundtrip:
    """Tests for encode/decode roundtrip."""

    def test_roundtrip_preserves_data(self, shm_with_signals: SharedMemoryManager) -> None:
        """Encode then decode should preserve all data."""
        encoder = TelemetryEncoder(
            shm_with_signals, ["sensor.x", "sensor.y", "sensor.z", "controller.output"]
        )

        # Set up test data
        expected_frame = 999
        expected_time_ns = 12_345_678_901
        expected_time_seconds = expected_time_ns / 1_000_000_000.0
        expected_values = [1.1, 2.2, 3.3, 4.4]

        shm_with_signals.set_frame(expected_frame)
        shm_with_signals.set_time_ns(expected_time_ns)
        for i, sig in enumerate(encoder.signals):
            shm_with_signals.set_signal(sig, expected_values[i])

        # Roundtrip
        data = encoder.encode()
        frame, time, values = TelemetryEncoder.decode(data)

        # Verify
        assert frame == expected_frame
        assert time == pytest.approx(expected_time_seconds)
        assert len(values) == len(expected_values)
        for i, expected in enumerate(expected_values):
            assert values[i] == pytest.approx(expected)

    def test_multiple_encodes_independent(self, shm_with_signals: SharedMemoryManager) -> None:
        """Multiple encodes should produce independent frames."""
        encoder = TelemetryEncoder(shm_with_signals, ["sensor.x"])

        # First encode
        shm_with_signals.set_frame(1)
        shm_with_signals.set_time_ns(1_000_000_000)
        shm_with_signals.set_signal("sensor.x", 10.0)
        data1 = encoder.encode()

        # Change values
        shm_with_signals.set_frame(2)
        shm_with_signals.set_time_ns(2_000_000_000)
        shm_with_signals.set_signal("sensor.x", 20.0)
        data2 = encoder.encode()

        # Decode both - they should be different
        frame1, time1, values1 = TelemetryEncoder.decode(data1)
        frame2, time2, values2 = TelemetryEncoder.decode(data2)

        assert frame1 == 1
        assert time1 == pytest.approx(1.0)
        assert values1[0] == pytest.approx(10.0)

        assert frame2 == 2
        assert time2 == pytest.approx(2.0)
        assert values2[0] == pytest.approx(20.0)
