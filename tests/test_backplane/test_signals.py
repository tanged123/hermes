"""Tests for signal types and registry."""

from __future__ import annotations

import pytest

from hermes.backplane.signals import (
    SignalDescriptor,
    SignalFlags,
    SignalRegistry,
    SignalType,
)


class TestSignalType:
    """Tests for SignalType enum."""

    def test_signal_types_exist(self) -> None:
        """All expected signal types should exist."""
        assert SignalType.F64 == 0
        assert SignalType.F32 == 1
        assert SignalType.I64 == 2
        assert SignalType.I32 == 3
        assert SignalType.BOOL == 4

    def test_signal_type_values(self) -> None:
        """Signal types should have expected integer values."""
        # Values map to struct format characters
        assert SignalType.F64 == 0
        assert SignalType.F32 == 1
        assert SignalType.I64 == 2
        assert SignalType.I32 == 3
        assert SignalType.BOOL == 4


class TestSignalFlags:
    """Tests for SignalFlags enum."""

    def test_flag_values(self) -> None:
        """Flags should have correct bit values."""
        assert SignalFlags.NONE == 0
        assert SignalFlags.WRITABLE == 1
        assert SignalFlags.PUBLISHED == 2

    def test_flags_can_be_combined(self) -> None:
        """Flags should be combinable with bitwise OR."""
        combined = SignalFlags.WRITABLE | SignalFlags.PUBLISHED
        assert combined == 3


class TestSignalDescriptor:
    """Tests for SignalDescriptor dataclass."""

    def test_create_descriptor(self) -> None:
        """Should create descriptor with all fields."""
        desc = SignalDescriptor(
            name="test.signal",
            type=SignalType.F64,
            flags=SignalFlags.WRITABLE,
            unit="m/s",
            description="Test signal",
        )
        assert desc.name == "test.signal"
        assert desc.type == SignalType.F64
        assert desc.flags == SignalFlags.WRITABLE
        assert desc.unit == "m/s"
        assert desc.description == "Test signal"

    def test_descriptor_defaults(self) -> None:
        """Should use sensible defaults."""
        desc = SignalDescriptor(name="simple")
        assert desc.name == "simple"
        assert desc.type == SignalType.F64
        assert desc.flags == SignalFlags.NONE
        assert desc.unit == ""
        assert desc.description == ""

    def test_descriptor_is_frozen(self) -> None:
        """Descriptors should be immutable."""
        desc = SignalDescriptor(name="test")
        with pytest.raises(AttributeError):
            desc.name = "changed"  # type: ignore[misc]


class TestSignalRegistry:
    """Tests for SignalRegistry."""

    def test_register_signal(self) -> None:
        """Should register signal and return qualified name."""
        registry = SignalRegistry()
        desc = SignalDescriptor(name="position")
        qualified = registry.register("vehicle", desc)
        assert qualified == "vehicle.position"

    def test_get_signal(self) -> None:
        """Should retrieve registered signal."""
        registry = SignalRegistry()
        desc = SignalDescriptor(name="velocity", type=SignalType.F32)
        registry.register("module", desc)

        retrieved = registry.get("module.velocity")
        assert retrieved.type == SignalType.F32

    def test_get_nonexistent_signal(self) -> None:
        """Should raise KeyError for nonexistent signal."""
        registry = SignalRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent.signal")

    def test_list_module_signals(self) -> None:
        """Should list all signals for a module."""
        registry = SignalRegistry()
        registry.register("mod", SignalDescriptor(name="a"))
        registry.register("mod", SignalDescriptor(name="b"))
        registry.register("other", SignalDescriptor(name="c"))

        mod_signals = registry.list_module("mod")
        assert "mod.a" in mod_signals
        assert "mod.b" in mod_signals
        assert len(mod_signals) == 2

    def test_all_signals(self) -> None:
        """Should return all registered signals."""
        registry = SignalRegistry()
        registry.register("a", SignalDescriptor(name="x"))
        registry.register("b", SignalDescriptor(name="y"))

        all_sigs = registry.all_signals()
        assert len(all_sigs) == 2
        assert "a.x" in all_sigs
        assert "b.y" in all_sigs
