"""Mock physics module for testing wire routing.

Provides a simple physics module with deterministic dynamics
for testing multi-module wiring without external dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager


class MockPhysicsModule:
    """Simple physics module with basic dynamics.

    Computes: output = input * 2 + state
    State accumulates: state += input * dt
    """

    def __init__(
        self,
        module_name: str,
        shm: SharedMemoryManager,
    ) -> None:
        """Initialize mock physics module.

        Args:
            module_name: Hermes module name (used as signal prefix)
            shm: Shared memory manager
        """
        self._name = module_name
        self._shm = shm
        self._state = 0.0

    def stage(self) -> None:
        """Initialize signals to zero."""
        self._state = 0.0
        self._shm.set_signal(f"{self._name}.input", 0.0)
        self._shm.set_signal(f"{self._name}.output", 0.0)
        self._shm.set_signal(f"{self._name}.state", 0.0)

    def step(self, dt: float) -> None:
        """Execute physics step."""
        input_val = self._shm.get_signal(f"{self._name}.input")

        # Simple dynamics
        self._state += input_val * dt
        output = input_val * 2.0 + self._state

        self._shm.set_signal(f"{self._name}.output", output)
        self._shm.set_signal(f"{self._name}.state", self._state)

    def reset(self) -> None:
        """Reset to initial state."""
        self._state = 0.0
        self._shm.set_signal(f"{self._name}.input", 0.0)
        self._shm.set_signal(f"{self._name}.output", 0.0)
        self._shm.set_signal(f"{self._name}.state", 0.0)
