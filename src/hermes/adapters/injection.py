"""Injection adapter for test signal injection."""

from __future__ import annotations

from hermes.core.signal import SignalDescriptor, SignalType


class InjectionAdapter:
    """Adapter for injecting test signals.

    This adapter provides a simple value store that can be wired
    to other modules for testing purposes. Values persist between
    steps until explicitly changed.

    Example:
        adapter = InjectionAdapter("injection", ["force.x", "force.y", "force.z"])
        adapter.set("force.x", 100.0)
        # Value persists across steps
    """

    def __init__(self, name: str, signals: list[str]) -> None:
        """Create injection adapter.

        Args:
            name: Module name for Hermes signal bus
            signals: List of signal names to create
        """
        self._name = name
        self._values: dict[str, float] = {s: 0.0 for s in signals}
        self._signals = {
            s: SignalDescriptor(name=s, type=SignalType.SCALAR, writable=True)
            for s in signals
        }

    @property
    def name(self) -> str:
        """Module name."""
        return self._name

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        """Available signals with metadata."""
        return self._signals

    def stage(self) -> None:
        """Prepare for execution (no-op for injection)."""
        pass

    def step(self, dt: float) -> None:
        """Advance by dt seconds (values persist, no computation)."""
        pass

    def reset(self) -> None:
        """Reset all values to zero."""
        self._values = {s: 0.0 for s in self._values}

    def get(self, signal: str) -> float:
        """Get signal value.

        Args:
            signal: Signal name

        Returns:
            Current value

        Raises:
            KeyError: If signal not found
        """
        if signal not in self._values:
            raise KeyError(f"Signal not found: {signal}")
        return self._values[signal]

    def set(self, signal: str, value: float) -> None:
        """Set signal value.

        Args:
            signal: Signal name
            value: Value to set

        Raises:
            KeyError: If signal not found
        """
        if signal not in self._values:
            raise KeyError(f"Signal not found: {signal}")
        self._values[signal] = value

    def get_bulk(self, signals: list[str]) -> list[float]:
        """Get multiple signal values."""
        return [self.get(s) for s in signals]

    def close(self) -> None:
        """Release resources (no-op)."""
        pass

    def __repr__(self) -> str:
        return f"InjectionAdapter(name={self._name!r}, signals={list(self._signals.keys())})"
