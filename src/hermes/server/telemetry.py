"""Binary telemetry encoding for WebSocket streaming.

This module provides efficient binary encoding of signal data from
shared memory for transmission to connected clients.

Binary Frame Format:
    Header (24 bytes):
        - magic: u32 (4 bytes) - 0x48455254 ("HERT")
        - frame: u64 (8 bytes) - Frame number
        - time: f64 (8 bytes) - Simulation time in seconds
        - count: u32 (4 bytes) - Number of signal values

    Payload:
        - values: f64[] (8 bytes × count) - Signal values in subscription order

    Total: 24 + 8×N bytes per frame
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager


class TelemetryEncoder:
    """Encodes telemetry frames from shared memory to binary format.

    Reads signal values from shared memory and packs them into a compact
    binary format suitable for WebSocket transmission.

    Example:
        encoder = TelemetryEncoder(shm, ["sensor.x", "sensor.y", "controller.output"])
        binary_frame = encoder.encode()
        await websocket.send(binary_frame)
    """

    MAGIC: int = 0x48455254  # "HERT" in little-endian ASCII
    HEADER_FORMAT: str = "<I Q d I"  # magic, frame, time, count
    HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 24 bytes

    # Nanoseconds per second for time conversion
    NANOSECONDS_PER_SECOND: float = 1_000_000_000.0

    def __init__(self, shm: SharedMemoryManager, signals: list[str]) -> None:
        """Initialize telemetry encoder.

        Args:
            shm: Shared memory manager to read from
            signals: List of signal names to include in frames
        """
        self._shm = shm
        self._signals = list(signals)  # Copy to ensure immutability

    @property
    def signals(self) -> list[str]:
        """Signal names included in telemetry frames."""
        return list(self._signals)

    @property
    def signal_count(self) -> int:
        """Number of signals per frame."""
        return len(self._signals)

    def encode(self) -> bytes:
        """Encode current state from shared memory to binary frame.

        Reads the current frame number, simulation time, and all subscribed
        signal values from shared memory and packs them into binary format.

        Returns:
            Binary frame data ready for WebSocket transmission

        Raises:
            RuntimeError: If shared memory is not attached
            KeyError: If any subscribed signal is not found
        """
        # Read header data from shared memory
        frame = self._shm.get_frame()
        time_ns = self._shm.get_time_ns()
        time_seconds = time_ns / self.NANOSECONDS_PER_SECOND
        count = len(self._signals)

        # Pack header
        header = struct.pack(
            self.HEADER_FORMAT,
            self.MAGIC,
            frame,
            time_seconds,
            count,
        )

        # Pack signal values
        if count > 0:
            values = [self._shm.get_signal(sig) for sig in self._signals]
            payload = struct.pack(f"<{count}d", *values)
        else:
            payload = b""

        return header + payload

    @classmethod
    def decode(cls, data: bytes) -> tuple[int, float, list[float]]:
        """Decode binary frame to frame number, time, and values.

        This is primarily for testing and debugging.

        Args:
            data: Binary frame data

        Returns:
            Tuple of (frame_number, time_seconds, signal_values)

        Raises:
            ValueError: If data is invalid or corrupted
        """
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"Frame too short: {len(data)} < {cls.HEADER_SIZE}")

        # Unpack header
        magic, frame, time_seconds, count = struct.unpack(
            cls.HEADER_FORMAT,
            data[: cls.HEADER_SIZE],
        )

        if magic != cls.MAGIC:
            raise ValueError(f"Invalid magic: {magic:#x}, expected {cls.MAGIC:#x}")

        # Validate payload size
        expected_size = cls.HEADER_SIZE + count * 8
        if len(data) < expected_size:
            raise ValueError(f"Frame truncated: {len(data)} < {expected_size}")

        # Unpack values
        if count > 0:
            values = list(
                struct.unpack(
                    f"<{count}d",
                    data[cls.HEADER_SIZE : cls.HEADER_SIZE + count * 8],
                )
            )
        else:
            values = []

        return int(frame), float(time_seconds), values

    def frame_size(self) -> int:
        """Calculate the size of encoded frames.

        Returns:
            Size in bytes of frames produced by this encoder
        """
        return self.HEADER_SIZE + len(self._signals) * 8
