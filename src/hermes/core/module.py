"""Module adapter protocol definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from hermes.core.signal import SignalDescriptor


@runtime_checkable
class ModuleAdapter(Protocol):
    """Interface for simulation modules.

    All simulation modules (Icarus, GNC software, test injectors, etc.)
    must implement this protocol to be managed by Hermes.
    """

    @property
    def name(self) -> str:
        """Unique module identifier."""
        ...

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        """Available signals with metadata.

        Returns a dictionary mapping local signal names (without module prefix)
        to their descriptors.
        """
        ...

    def stage(self) -> None:
        """Prepare for execution.

        Called once before the simulation run loop starts.
        Modules should validate configuration, resolve dependencies,
        and apply initial conditions.
        """
        ...

    def step(self, dt: float) -> None:
        """Advance module by dt seconds.

        Called each simulation frame in the order determined by
        the scheduler. Modules should:
        1. Read inputs (set by SignalBus routing)
        2. Compute dynamics
        3. Write outputs
        """
        ...

    def reset(self) -> None:
        """Return to initial conditions.

        Called to restart the simulation from t=0 without
        recreating the module.
        """
        ...

    def get(self, signal: str) -> float:
        """Get signal value by local name (without module prefix).

        Args:
            signal: Local signal name (e.g., "Vehicle.position.z")

        Returns:
            Current signal value

        Raises:
            KeyError: If signal not found
        """
        ...

    def set(self, signal: str, value: float) -> None:
        """Set signal value by local name.

        Args:
            signal: Local signal name
            value: Value to set

        Raises:
            KeyError: If signal not found or not writable
        """
        ...

    def get_bulk(self, signals: list[str]) -> list[float]:
        """Get multiple signal values efficiently.

        Default implementation calls get() for each signal.
        Adapters may override for better performance.

        Args:
            signals: List of local signal names

        Returns:
            List of values in same order as input
        """
        ...

    def close(self) -> None:
        """Release resources.

        Called when the module is being destroyed.
        Clean up file handles, network connections, etc.
        """
        ...
