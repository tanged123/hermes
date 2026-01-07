"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest

from hermes.backplane.signals import SignalDescriptor, SignalType


@pytest.fixture
def sample_signals() -> list[SignalDescriptor]:
    """Create sample signal descriptors for testing."""
    return [
        SignalDescriptor(name="position.x", type=SignalType.F64),
        SignalDescriptor(name="position.y", type=SignalType.F64),
        SignalDescriptor(name="position.z", type=SignalType.F64),
        SignalDescriptor(name="velocity.x", type=SignalType.F64),
        SignalDescriptor(name="velocity.y", type=SignalType.F64),
        SignalDescriptor(name="velocity.z", type=SignalType.F64),
    ]
