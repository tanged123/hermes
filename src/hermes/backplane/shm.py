"""Shared memory management for signal data.

This module provides the SharedMemoryManager class for creating and
accessing POSIX shared memory segments used for inter-process signal
communication.

Memory Layout:
    ┌─────────────────────────────────────────────────────────┐
    │ Header (64 bytes)                                        │
    │   - magic: u32 ("HERM")                                 │
    │   - version: u32 (currently 3)                          │
    │   - frame: u64                                          │
    │   - time_ns: u64 (nanoseconds for determinism)          │
    │   - signal_count: u32                                   │
    │   - reserved: [u8; 36]                                  │
    ├─────────────────────────────────────────────────────────┤
    │ Signal Directory (variable)                              │
    │   - [SignalEntry] × signal_count                        │
    ├─────────────────────────────────────────────────────────┤
    │ String Table (variable)                                  │
    │   - null-terminated signal names                        │
    ├─────────────────────────────────────────────────────────┤
    │ Data Region (aligned to 64 bytes)                       │
    │   - Signal values packed contiguously                   │
    └─────────────────────────────────────────────────────────┘

Determinism:
    Time is stored as integer nanoseconds (u64) rather than floating-point
    seconds to ensure reproducibility across runs and platforms.
"""

from __future__ import annotations

import contextlib
import mmap
import struct
from typing import TYPE_CHECKING

import posix_ipc

if TYPE_CHECKING:
    from hermes.backplane.signals import SignalDescriptor


class SharedMemoryManager:
    """Manages a shared memory segment for signal data.

    This class handles creation, attachment, and access to a POSIX
    shared memory segment containing simulation signals. The segment
    can be accessed by multiple processes for efficient IPC.

    Example:
        # Creator (main process)
        shm = SharedMemoryManager("/hermes_sim")
        shm.create(signals)

        # Attacher (module process)
        shm = SharedMemoryManager("/hermes_sim")
        shm.attach()
        value = shm.get_signal("module.signal")
    """

    MAGIC = 0x4845524D  # "HERM" in ASCII
    VERSION = 3  # v3: time_ns (nanoseconds) as u64
    HEADER_SIZE = 64
    HEADER_FORMAT = "<I I Q Q I"  # magic, version, frame, time_ns, signal_count
    HEADER_STRUCT_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(self, name: str) -> None:
        """Initialize shared memory manager.

        Args:
            name: Shared memory segment name (e.g., "/hermes_sim")
        """
        self._name = name
        self._shm: posix_ipc.SharedMemory | None = None
        self._mmap: mmap.mmap | None = None
        self._signal_offsets: dict[str, int] = {}
        self._signal_count: int = 0
        self._data_offset: int = 0

    @property
    def name(self) -> str:
        """Shared memory segment name."""
        return self._name

    @property
    def is_attached(self) -> bool:
        """Whether currently attached to shared memory."""
        return self._mmap is not None

    def create(self, signals: list[SignalDescriptor]) -> None:
        """Create and initialize shared memory segment.

        Args:
            signals: List of signal descriptors to allocate space for

        Raises:
            RuntimeError: If already attached
            posix_ipc.ExistentialError: If segment already exists
        """
        if self._mmap is not None:
            raise RuntimeError("Already attached to shared memory")

        # Calculate sizes
        self._signal_count = len(signals)

        # Build string table and calculate offsets
        string_table = b""
        signal_entries: list[tuple[int, int]] = []  # (name_offset, data_offset)
        data_offset = 0

        for sig in signals:
            name_bytes = sig.name.encode("utf-8") + b"\x00"
            signal_entries.append((len(string_table), data_offset))
            string_table += name_bytes
            data_offset += 8  # All signals stored as f64 for now

        # Calculate segment size with alignment
        directory_size = self._signal_count * 16  # 16 bytes per entry
        string_table_size = len(string_table)
        data_size = self._signal_count * 8

        # Align data region to 64 bytes
        header_and_meta = self.HEADER_SIZE + directory_size + string_table_size
        self._data_offset = (header_and_meta + 63) & ~63  # Round up to 64
        total_size = self._data_offset + data_size

        # Create shared memory
        self._shm = posix_ipc.SharedMemory(
            self._name,
            posix_ipc.O_CREX,  # Create exclusive
            size=total_size,
        )

        # Map the memory
        self._mmap = mmap.mmap(self._shm.fd, total_size)

        # Write header
        self._mmap.seek(0)
        header = struct.pack(
            self.HEADER_FORMAT,
            self.MAGIC,
            self.VERSION,
            0,  # frame
            0,  # time_ns (nanoseconds as integer)
            self._signal_count,
        )
        self._mmap.write(header)
        self._mmap.write(b"\x00" * (self.HEADER_SIZE - self.HEADER_STRUCT_SIZE))

        # Write signal directory
        for _i, (name_off, data_off) in enumerate(signal_entries):
            entry = struct.pack("<I I", name_off, data_off)
            self._mmap.write(entry)
            self._mmap.write(b"\x00" * 8)  # Pad to 16 bytes

        # Write string table
        self._mmap.write(string_table)

        # Zero data region
        self._mmap.seek(self._data_offset)
        self._mmap.write(b"\x00" * data_size)

        # Build signal offset lookup
        for i, sig in enumerate(signals):
            self._signal_offsets[sig.name] = self._data_offset + i * 8

    def attach(self) -> None:
        """Attach to existing shared memory segment.

        Raises:
            RuntimeError: If already attached
            posix_ipc.ExistentialError: If segment doesn't exist
        """
        if self._mmap is not None:
            raise RuntimeError("Already attached to shared memory")

        # Open existing segment
        self._shm = posix_ipc.SharedMemory(self._name, posix_ipc.O_RDWR)
        self._mmap = mmap.mmap(self._shm.fd, 0)  # Map entire segment

        # Validate header
        self._mmap.seek(0)
        header_data = self._mmap.read(self.HEADER_STRUCT_SIZE)
        magic, version, _, _, signal_count = struct.unpack(self.HEADER_FORMAT, header_data)

        if magic != self.MAGIC:
            raise ValueError(f"Invalid shared memory magic: {magic:#x}")
        if version != self.VERSION:
            raise ValueError(f"Unsupported version: {version}")

        self._signal_count = signal_count

        # Calculate _data_offset by finding end of string table
        string_table_start = self.HEADER_SIZE + signal_count * 16
        self._mmap.seek(self.HEADER_SIZE)
        max_string_end = 0
        for i in range(signal_count):
            entry_data = self._mmap.read(16)
            name_off, _ = struct.unpack("<I I", entry_data[:8])

            # Find end of this string
            self._mmap.seek(string_table_start + name_off)
            while self._mmap.read(1) != b"\x00":
                pass
            max_string_end = max(max_string_end, self._mmap.tell())
            self._mmap.seek(self.HEADER_SIZE + (i + 1) * 16)

        self._data_offset = (max_string_end + 63) & ~63

        # Now build proper offset lookup
        self._mmap.seek(self.HEADER_SIZE)
        for _i in range(signal_count):
            entry_data = self._mmap.read(16)
            name_off, data_off = struct.unpack("<I I", entry_data[:8])

            # Read signal name
            pos = self._mmap.tell()
            self._mmap.seek(string_table_start + name_off)
            name_bytes = b""
            while True:
                c = self._mmap.read(1)
                if c == b"\x00" or c == b"":
                    break
                name_bytes += c
            self._mmap.seek(pos)

            signal_name = name_bytes.decode("utf-8")
            self._signal_offsets[signal_name] = self._data_offset + data_off

    def detach(self) -> None:
        """Detach from shared memory segment."""
        if self._mmap is not None:
            self._mmap.close()
            self._mmap = None
        if self._shm is not None:
            self._shm.close_fd()
            self._shm = None
        self._signal_offsets.clear()

    def destroy(self) -> None:
        """Destroy the shared memory segment.

        Should only be called by the creator after all attachers detach.
        """
        self.detach()
        with contextlib.suppress(posix_ipc.ExistentialError):
            posix_ipc.unlink_shared_memory(self._name)

    def get_signal(self, name: str) -> float:
        """Read a signal value from shared memory.

        Args:
            name: Signal name

        Returns:
            Signal value as float

        Raises:
            RuntimeError: If not attached
            KeyError: If signal not found
        """
        if self._mmap is None:
            raise RuntimeError("Not attached to shared memory")
        if name not in self._signal_offsets:
            raise KeyError(f"Signal not found: {name}")

        offset = self._signal_offsets[name]
        self._mmap.seek(offset)
        (value,) = struct.unpack("<d", self._mmap.read(8))
        return float(value)

    def set_signal(self, name: str, value: float) -> None:
        """Write a signal value to shared memory.

        Args:
            name: Signal name
            value: Value to write

        Raises:
            RuntimeError: If not attached
            KeyError: If signal not found
        """
        if self._mmap is None:
            raise RuntimeError("Not attached to shared memory")
        if name not in self._signal_offsets:
            raise KeyError(f"Signal not found: {name}")

        offset = self._signal_offsets[name]
        self._mmap.seek(offset)
        self._mmap.write(struct.pack("<d", value))

    # Nanoseconds per second (for time conversions)
    NANOSECONDS_PER_SECOND: int = 1_000_000_000

    def get_frame(self) -> int:
        """Get current frame number from header."""
        if self._mmap is None:
            raise RuntimeError("Not attached to shared memory")
        self._mmap.seek(8)  # Offset of frame field
        (frame,) = struct.unpack("<Q", self._mmap.read(8))
        return int(frame)

    def set_frame(self, frame: int) -> None:
        """Set frame number in header."""
        if self._mmap is None:
            raise RuntimeError("Not attached to shared memory")
        self._mmap.seek(8)
        self._mmap.write(struct.pack("<Q", frame))

    def get_time_ns(self) -> int:
        """Get current simulation time in nanoseconds from header.

        This is the authoritative time value for deterministic simulations.
        """
        if self._mmap is None:
            raise RuntimeError("Not attached to shared memory")
        self._mmap.seek(16)  # Offset of time_ns field
        (time_ns,) = struct.unpack("<Q", self._mmap.read(8))
        return int(time_ns)

    def set_time_ns(self, time_ns: int) -> None:
        """Set simulation time in nanoseconds in header."""
        if self._mmap is None:
            raise RuntimeError("Not attached to shared memory")
        self._mmap.seek(16)
        self._mmap.write(struct.pack("<Q", time_ns))

    def get_time(self) -> float:
        """Get current simulation time in seconds from header.

        This is derived from `get_time_ns()` for API convenience.
        For deterministic comparisons, use `get_time_ns()` instead.
        """
        return self.get_time_ns() / self.NANOSECONDS_PER_SECOND

    def set_time(self, time: float) -> None:
        """Set simulation time in seconds in header.

        Converts to nanoseconds internally. For precise control,
        use `set_time_ns()` instead.
        """
        self.set_time_ns(round(time * self.NANOSECONDS_PER_SECOND))

    def signal_names(self) -> list[str]:
        """Get list of all signal names."""
        return list(self._signal_offsets.keys())

    def __enter__(self) -> SharedMemoryManager:
        return self

    def __exit__(self, *args: object) -> None:
        self.detach()
