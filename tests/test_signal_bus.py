"""Tests for SignalBus."""

import pytest

from hermes.core.signal import SignalBus, Wire
from tests.conftest import MockAdapter


class TestSignalBusRegistration:
    """Tests for module registration."""

    def test_register_module(self, signal_bus: SignalBus) -> None:
        adapter = MockAdapter("test", {"value": 42.0})
        signal_bus.register_module(adapter)
        assert "test" in signal_bus.modules

    def test_register_duplicate_raises(self, signal_bus: SignalBus) -> None:
        adapter1 = MockAdapter("test", {"a": 1.0})
        adapter2 = MockAdapter("test", {"b": 2.0})
        signal_bus.register_module(adapter1)

        with pytest.raises(ValueError, match="already registered"):
            signal_bus.register_module(adapter2)


class TestSignalAccess:
    """Tests for signal get/set via qualified names."""

    def test_get_signal(self, populated_bus: SignalBus) -> None:
        value = populated_bus.get("test.position.z")
        assert value == 100.0

    def test_set_signal(self, populated_bus: SignalBus) -> None:
        populated_bus.set("test.position.z", 200.0)
        assert populated_bus.get("test.position.z") == 200.0

    def test_get_invalid_format_raises(self, populated_bus: SignalBus) -> None:
        with pytest.raises(ValueError, match="Invalid qualified name"):
            populated_bus.get("noseparator")

    def test_get_unknown_module_raises(self, populated_bus: SignalBus) -> None:
        with pytest.raises(KeyError):
            populated_bus.get("unknown.signal")

    def test_get_unknown_signal_raises(self, populated_bus: SignalBus) -> None:
        with pytest.raises(KeyError):
            populated_bus.get("test.nonexistent")


class TestWiring:
    """Tests for signal wiring and routing."""

    def test_add_wire(self, signal_bus: SignalBus) -> None:
        src = MockAdapter("src", {"out": 42.0})
        dst = MockAdapter("dst", {"in": 0.0})
        signal_bus.register_module(src)
        signal_bus.register_module(dst)

        wire = Wire("src", "out", "dst", "in")
        signal_bus.add_wire(wire)

        assert len(signal_bus.wires) == 1

    def test_wire_invalid_src_module_raises(self, signal_bus: SignalBus) -> None:
        dst = MockAdapter("dst", {"in": 0.0})
        signal_bus.register_module(dst)

        wire = Wire("unknown", "out", "dst", "in")
        with pytest.raises(ValueError, match="Source module not found"):
            signal_bus.add_wire(wire)

    def test_wire_invalid_dst_module_raises(self, signal_bus: SignalBus) -> None:
        src = MockAdapter("src", {"out": 42.0})
        signal_bus.register_module(src)

        wire = Wire("src", "out", "unknown", "in")
        with pytest.raises(ValueError, match="Destination module not found"):
            signal_bus.add_wire(wire)

    def test_route_transfers_value(self, signal_bus: SignalBus) -> None:
        src = MockAdapter("src", {"out": 42.0})
        dst = MockAdapter("dst", {"in": 0.0})
        signal_bus.register_module(src)
        signal_bus.register_module(dst)
        signal_bus.add_wire(Wire("src", "out", "dst", "in"))

        signal_bus.route()

        assert dst.get("in") == 42.0

    def test_route_applies_gain(self, signal_bus: SignalBus) -> None:
        src = MockAdapter("src", {"out": 10.0})
        dst = MockAdapter("dst", {"in": 0.0})
        signal_bus.register_module(src)
        signal_bus.register_module(dst)
        signal_bus.add_wire(Wire("src", "out", "dst", "in", gain=2.0))

        signal_bus.route()

        assert dst.get("in") == 20.0

    def test_route_applies_offset(self, signal_bus: SignalBus) -> None:
        src = MockAdapter("src", {"out": 10.0})
        dst = MockAdapter("dst", {"in": 0.0})
        signal_bus.register_module(src)
        signal_bus.register_module(dst)
        signal_bus.add_wire(Wire("src", "out", "dst", "in", offset=5.0))

        signal_bus.route()

        assert dst.get("in") == 15.0

    def test_route_applies_gain_then_offset(self, signal_bus: SignalBus) -> None:
        src = MockAdapter("src", {"out": 10.0})
        dst = MockAdapter("dst", {"in": 0.0})
        signal_bus.register_module(src)
        signal_bus.register_module(dst)
        signal_bus.add_wire(Wire("src", "out", "dst", "in", gain=2.0, offset=5.0))

        signal_bus.route()

        # Should be (10 * 2) + 5 = 25
        assert dst.get("in") == 25.0


class TestSchema:
    """Tests for schema generation."""

    def test_get_schema_structure(self, populated_bus: SignalBus) -> None:
        schema = populated_bus.get_schema()

        assert "modules" in schema
        assert "wiring" in schema
        assert "test" in schema["modules"]

    def test_get_schema_signals(self, populated_bus: SignalBus) -> None:
        schema = populated_bus.get_schema()

        signals = schema["modules"]["test"]["signals"]
        assert "position.x" in signals
        assert signals["position.x"]["type"] == "f64"

    def test_get_all_signals(self, populated_bus: SignalBus) -> None:
        all_signals = populated_bus.get_all_signals()

        assert "test.position.x" in all_signals
        assert "test.velocity.z" in all_signals
        assert len(all_signals) == 6
