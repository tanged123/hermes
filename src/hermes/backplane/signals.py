"""Signal types and registry for shared memory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SignalType(IntEnum):
    """Signal data types for shared memory layout."""

    F64 = 0  # 64-bit float (default)
    F32 = 1  # 32-bit float
    I64 = 2  # 64-bit signed integer
    I32 = 3  # 32-bit signed integer
    BOOL = 4  # Boolean (stored as u8)


class SignalFlags(IntEnum):
    """Signal property flags."""

    NONE = 0
    WRITABLE = 1 << 0  # Can be modified via scripting API
    PUBLISHED = 1 << 1  # Included in telemetry streams


@dataclass(frozen=True)
class SignalDescriptor:
    """Metadata for a signal in shared memory.

    Attributes:
        name: Local signal name (without module prefix)
        type: Data type for memory layout
        flags: Property flags (writable, published, etc.)
        unit: Physical unit string (e.g., "m", "rad/s")
        description: Human-readable description
    """

    name: str
    type: SignalType = SignalType.F64
    flags: int = SignalFlags.NONE
    unit: str = ""
    description: str = ""


class SignalRegistry:
    """Registry of all signals in the simulation.

    Tracks signals by qualified name (module.signal) and provides
    lookup by module for efficient iteration.
    """

    def __init__(self) -> None:
        self._signals: dict[str, SignalDescriptor] = {}
        self._by_module: dict[str, list[str]] = {}

    def register(self, module: str, signal: SignalDescriptor) -> str:
        """Register a signal, returns qualified name.

        Args:
            module: Module name
            signal: Signal descriptor

        Returns:
            Qualified name (module.signal)
        """
        qualified = f"{module}.{signal.name}"
        self._signals[qualified] = signal
        self._by_module.setdefault(module, []).append(qualified)
        return qualified

    def get(self, qualified_name: str) -> SignalDescriptor:
        """Get signal descriptor by qualified name.

        Args:
            qualified_name: Full signal path (module.signal)

        Returns:
            Signal descriptor

        Raises:
            KeyError: If signal not found
        """
        return self._signals[qualified_name]

    def list_module(self, module: str) -> list[str]:
        """List all signals for a module.

        Args:
            module: Module name

        Returns:
            List of qualified signal names
        """
        return self._by_module.get(module, [])

    def all_signals(self) -> dict[str, SignalDescriptor]:
        """Get all registered signals."""
        return dict(self._signals)

    def __len__(self) -> int:
        return len(self._signals)

    def __contains__(self, qualified_name: str) -> bool:
        return qualified_name in self._signals
