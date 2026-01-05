"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest

from hermes.core.signal import SignalBus, SignalDescriptor, SignalType
from hermes.core.module import ModuleAdapter


class MockAdapter:
    """Mock module adapter for testing."""

    def __init__(
        self,
        name: str,
        signals: dict[str, float] | None = None,
    ) -> None:
        self._name = name
        self._values: dict[str, float] = signals or {}
        self._signals = {
            name: SignalDescriptor(name=name, type=SignalType.SCALAR)
            for name in self._values
        }
        self._staged = False
        self._step_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def signals(self) -> dict[str, SignalDescriptor]:
        return self._signals

    @property
    def step_count(self) -> int:
        return self._step_count

    def stage(self) -> None:
        self._staged = True

    def step(self, dt: float) -> None:
        self._step_count += 1

    def reset(self) -> None:
        self._step_count = 0

    def get(self, signal: str) -> float:
        if signal not in self._values:
            raise KeyError(f"Signal not found: {signal}")
        return self._values[signal]

    def set(self, signal: str, value: float) -> None:
        if signal not in self._values:
            raise KeyError(f"Signal not found: {signal}")
        self._values[signal] = value

    def get_bulk(self, signals: list[str]) -> list[float]:
        return [self.get(s) for s in signals]

    def close(self) -> None:
        pass


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Create a mock adapter with test signals."""
    return MockAdapter(
        "test",
        signals={
            "position.x": 0.0,
            "position.y": 0.0,
            "position.z": 100.0,
            "velocity.x": 1.0,
            "velocity.y": 0.0,
            "velocity.z": -9.8,
        },
    )


@pytest.fixture
def signal_bus() -> SignalBus:
    """Create an empty signal bus."""
    return SignalBus()


@pytest.fixture
def populated_bus(mock_adapter: MockAdapter) -> SignalBus:
    """Create a signal bus with a registered mock adapter."""
    bus = SignalBus()
    bus.register_module(mock_adapter)
    return bus
