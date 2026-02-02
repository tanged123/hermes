"""Injection module for test signal input.

Provides a simple module that holds writable signal values.
Values persist between steps - no internal dynamics.
External systems can write to these signals via shared memory
or WebSocket commands, and wires route them to physics modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager


class InjectionModule:
    """Simple module that holds writable signal values.

    Values persist between steps - no internal dynamics.
    External systems can write to these signals via shared memory
    or WebSocket commands, and wires route them to physics modules.
    """

    def __init__(
        self,
        module_name: str,
        shm: SharedMemoryManager,
        signals: list[str],
    ) -> None:
        """Initialize injection module.

        Args:
            module_name: Hermes module name (used as signal prefix)
            shm: Shared memory manager
            signals: List of signal names (local, without module prefix)
        """
        self._name = module_name
        self._shm = shm
        self._signals = signals

    def stage(self) -> None:
        """Stage module - write initial zeros to all signals."""
        for signal in self._signals:
            self._shm.set_signal(f"{self._name}.{signal}", 0.0)

    def step(self, dt: float) -> None:
        """Step module - no-op, values persist."""

    def reset(self) -> None:
        """Reset all signals to zero."""
        for signal in self._signals:
            self._shm.set_signal(f"{self._name}.{signal}", 0.0)
