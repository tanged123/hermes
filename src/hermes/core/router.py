"""Wire router for inter-module signal routing.

Transfers signal values between modules via shared memory,
applying optional gain and offset transforms.

Transform: dst_value = src_value * gain + offset
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager
    from hermes.core.config import WireConfig


@dataclass
class CompiledWire:
    """Pre-validated wire for fast routing."""

    src: str
    dst: str
    gain: float
    offset: float


class WireRouter:
    """Routes signals between modules via shared memory.

    Wires are executed after all modules step, transferring
    values from source signals to destination signals with
    optional gain and offset transforms.
    """

    def __init__(self, shm: SharedMemoryManager) -> None:
        self._shm = shm
        self._wires: list[CompiledWire] = []

    def add_wire(self, config: WireConfig) -> None:
        """Add a wire from configuration.

        Args:
            config: Wire configuration with src, dst, gain, offset
        """
        self._wires.append(
            CompiledWire(
                src=config.src,
                dst=config.dst,
                gain=config.gain,
                offset=config.offset,
            )
        )

    def validate(self) -> None:
        """Validate all wires against shared memory registry.

        Raises:
            ValueError: If source or destination signal not found
        """
        signal_names = set(self._shm.signal_names())

        for wire in self._wires:
            if wire.src not in signal_names:
                raise ValueError(f"Wire source signal not found: {wire.src}")
            if wire.dst not in signal_names:
                raise ValueError(f"Wire destination signal not found: {wire.dst}")

    def route(self) -> None:
        """Execute all wire transfers."""
        for wire in self._wires:
            value = self._shm.get_signal(wire.src)
            transformed = value * wire.gain + wire.offset
            self._shm.set_signal(wire.dst, transformed)

    @property
    def wire_count(self) -> int:
        """Number of configured wires."""
        return len(self._wires)

    def clear(self) -> None:
        """Remove all wires."""
        self._wires.clear()
