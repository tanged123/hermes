"""Icarus adapter using pybind11 Python bindings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hermes.core.signal import SignalDescriptor, SignalType

if TYPE_CHECKING:
    pass


class IcarusAdapter:
    """Adapter for Icarus 6DOF simulation via pybind11 bindings.

    This adapter wraps the Icarus Python bindings (built with pybind11)
    to provide a ModuleAdapter interface for Hermes orchestration.

    Example:
        adapter = IcarusAdapter("icarus", "config.yaml")
        adapter.stage()
        adapter.step(0.01)
        altitude = adapter.get("Vehicle.position.z")
    """

    def __init__(
        self,
        name: str,
        config_path: str | Path,
    ) -> None:
        """Create Icarus adapter.

        Args:
            name: Module name for Hermes signal bus
            config_path: Path to Icarus YAML configuration file

        Raises:
            ImportError: If icarus module not found
            icarus.ConfigError: If configuration loading fails
        """
        self._name = name
        self._config_path = Path(config_path)

        # Import icarus pybind11 module
        try:
            import icarus
        except ImportError as e:
            raise ImportError(
                "Icarus Python bindings not found. "
                "Ensure icarus is built with BUILD_INTERFACES=ON and "
                "the module is in PYTHONPATH."
            ) from e

        # Create simulator from config
        self._sim = icarus.Simulator(str(self._config_path))
        self._icarus = icarus  # Keep reference for exception types

        # Build signal descriptors from schema
        self._signals: dict[str, SignalDescriptor] = {}
        self._build_signals()

    @property
    def name(self) -> str:
        """Module name."""
        return self._name

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        """Available signals with metadata."""
        return self._signals

    @property
    def simulator(self):
        """Access to underlying Icarus Simulator (for advanced use)."""
        return self._sim

    def stage(self) -> None:
        """Stage the simulation.

        Validates wiring, applies initial conditions, and prepares
        the simulation for execution.
        """
        self._sim.stage()

    def step(self, dt: float) -> None:
        """Advance simulation by dt seconds.

        Args:
            dt: Timestep in seconds. If 0, uses configured dt.
        """
        if dt == 0 or dt == self._sim.dt:
            self._sim.step()
        else:
            self._sim.step(dt)

    def reset(self) -> None:
        """Reset simulation to initial state."""
        self._sim.reset()

    def get(self, signal: str) -> float:
        """Get signal value by name.

        Args:
            signal: Signal name (e.g., "Vehicle.position.z")

        Returns:
            Current signal value

        Raises:
            KeyError: If signal not found
        """
        try:
            return self._sim.get(signal)
        except self._icarus.SignalNotFoundError as e:
            raise KeyError(f"Signal not found: {signal}") from e

    def set(self, signal: str, value: float) -> None:
        """Set signal value by name.

        Args:
            signal: Signal name
            value: Value to set

        Raises:
            KeyError: If signal not found
        """
        try:
            self._sim.set(signal, value)
        except self._icarus.SignalNotFoundError as e:
            raise KeyError(f"Signal not found: {signal}") from e

    def get_bulk(self, signals: list[str]) -> list[float]:
        """Get multiple signal values efficiently.

        Args:
            signals: List of signal names

        Returns:
            List of values in same order
        """
        return [self.get(s) for s in signals]

    def get_time(self) -> float:
        """Get current simulation time (MET)."""
        return self._sim.time

    def close(self) -> None:
        """Release resources."""
        # Python GC handles cleanup
        self._sim = None  # type: ignore

    def _build_signals(self) -> None:
        """Build signal descriptors from Icarus schema."""
        # Get all signal names from the simulator
        for signal_name in self._sim.signals:
            # Parse signal type from schema if available
            # For now, assume all are scalar f64
            self._signals[signal_name] = SignalDescriptor(
                name=signal_name,
                type=SignalType.SCALAR,
                unit="",  # Could parse from schema_json
                writable=True,
            )

    def __repr__(self) -> str:
        return (
            f"IcarusAdapter(name={self._name!r}, "
            f"config={self._config_path!r}, "
            f"signals={len(self._signals)})"
        )
