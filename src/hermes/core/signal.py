"""Signal types and signal bus implementation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hermes.core.module import ModuleAdapter


class SignalType(Enum):
    """Signal data types."""

    SCALAR = "f64"
    VEC3 = "vec3"
    QUAT = "quat"


@dataclass(frozen=True, slots=True)
class SignalDescriptor:
    """Metadata for a signal."""

    name: str
    type: SignalType = SignalType.SCALAR
    unit: str = ""
    writable: bool = True
    description: str = ""


@dataclass(slots=True)
class Wire:
    """Connection between two signals.

    Transfers values from source to destination each frame:
        dst = src * gain + offset
    """

    src_module: str
    src_signal: str
    dst_module: str
    dst_signal: str
    gain: float = 1.0
    offset: float = 0.0


class SignalBus:
    """Routes signals between modules.

    The SignalBus is Hermes's central nervous system. It:
    - Maintains a registry of all modules
    - Routes signals between modules based on wiring configuration
    - Provides unified access via qualified names (module.signal)
    """

    def __init__(self) -> None:
        self._modules: dict[str, ModuleAdapter] = {}
        self._wires: list[Wire] = []

    @property
    def modules(self) -> dict[str, ModuleAdapter]:
        """Registered modules."""
        return self._modules

    @property
    def wires(self) -> list[Wire]:
        """Configured wires."""
        return self._wires

    def register_module(self, module: ModuleAdapter) -> None:
        """Add a module to the bus.

        Args:
            module: Module adapter to register

        Raises:
            ValueError: If module name already registered
        """
        if module.name in self._modules:
            raise ValueError(f"Module already registered: {module.name}")
        self._modules[module.name] = module

    def add_wire(self, wire: Wire) -> None:
        """Add a signal wire.

        Args:
            wire: Wire configuration

        Raises:
            ValueError: If source or destination module not found
        """
        self._validate_wire(wire)
        self._wires.append(wire)

    def route(self) -> None:
        """Transfer all wired signals (src -> dst).

        Called each frame after all modules have stepped.
        Applies gain and offset transformations.
        """
        for wire in self._wires:
            src = self._modules[wire.src_module]
            dst = self._modules[wire.dst_module]
            value = src.get(wire.src_signal)
            dst.set(wire.dst_signal, value * wire.gain + wire.offset)

    def get(self, qualified_name: str) -> float:
        """Get signal by qualified name (module.signal).

        Args:
            qualified_name: Full signal path (e.g., "icarus.Vehicle.position.z")

        Returns:
            Signal value

        Raises:
            ValueError: If name format invalid
            KeyError: If module or signal not found
        """
        module_name, signal_name = self._parse_qualified(qualified_name)
        return self._modules[module_name].get(signal_name)

    def set(self, qualified_name: str, value: float) -> None:
        """Set signal by qualified name.

        Args:
            qualified_name: Full signal path
            value: Value to set

        Raises:
            ValueError: If name format invalid
            KeyError: If module or signal not found
        """
        module_name, signal_name = self._parse_qualified(qualified_name)
        self._modules[module_name].set(signal_name, value)

    def get_schema(self) -> dict[str, Any]:
        """Return full schema for all modules.

        Returns a dictionary suitable for JSON serialization containing
        module information, signals, and wiring.
        """
        return {
            "modules": {
                name: {
                    "signals": {
                        sig.name: {"type": sig.type.value, "unit": sig.unit}
                        for sig in mod.signals.values()
                    }
                }
                for name, mod in self._modules.items()
            },
            "wiring": [
                {
                    "src": f"{w.src_module}.{w.src_signal}",
                    "dst": f"{w.dst_module}.{w.dst_signal}",
                    "gain": w.gain,
                    "offset": w.offset,
                }
                for w in self._wires
                if w.gain != 1.0 or w.offset != 0.0
            ]
            + [
                {
                    "src": f"{w.src_module}.{w.src_signal}",
                    "dst": f"{w.dst_module}.{w.dst_signal}",
                }
                for w in self._wires
                if w.gain == 1.0 and w.offset == 0.0
            ],
        }

    def get_all_signals(self) -> list[str]:
        """Return all qualified signal names.

        Returns:
            List of all signals as "module.signal" strings
        """
        result = []
        for module_name, module in self._modules.items():
            for signal_name in module.signals:
                result.append(f"{module_name}.{signal_name}")
        return result

    def _validate_wire(self, wire: Wire) -> None:
        """Validate wire references exist."""
        if wire.src_module not in self._modules:
            raise ValueError(f"Source module not found: {wire.src_module}")
        if wire.dst_module not in self._modules:
            raise ValueError(f"Destination module not found: {wire.dst_module}")

        src_mod = self._modules[wire.src_module]
        if wire.src_signal not in src_mod.signals:
            raise ValueError(f"Source signal not found: {wire.src_module}.{wire.src_signal}")

        dst_mod = self._modules[wire.dst_module]
        if wire.dst_signal not in dst_mod.signals:
            raise ValueError(f"Destination signal not found: {wire.dst_module}.{wire.dst_signal}")

    def _parse_qualified(self, qualified_name: str) -> tuple[str, str]:
        """Parse qualified name into (module, signal).

        The module name is the first dot-separated component.
        The signal name is everything after the first dot.

        Examples:
            "icarus.Vehicle.position.z" -> ("icarus", "Vehicle.position.z")
            "gnc.mode" -> ("gnc", "mode")
        """
        parts = qualified_name.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid qualified name '{qualified_name}': expected 'module.signal'")
        return parts[0], parts[1]
