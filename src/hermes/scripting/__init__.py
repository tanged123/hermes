"""Scripting infrastructure for programmatic simulation interaction.

This package provides Python APIs for interacting with running
Hermes simulations, enabling injection of values and inspection
of signals.
"""

from hermes.scripting.api import SimulationAPI

__all__ = [
    "SimulationAPI",
]
