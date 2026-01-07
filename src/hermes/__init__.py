"""Hermes - Simulation Orchestration Platform.

A multi-process simulation framework with POSIX IPC for inter-module
communication. Supports language-agnostic modules (C, C++, Python, Rust)
coordinated via shared memory, semaphores, and named pipes.
"""

__version__ = "0.1.1"

# Backplane (IPC infrastructure)
from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalFlags, SignalRegistry, SignalType
from hermes.backplane.sync import FrameBarrier

# Configuration
from hermes.core.config import HermesConfig

# Protocol messages
from hermes.protocol.messages import Command, ControlMessage, MessageType

# Scripting API
from hermes.scripting.api import SimulationAPI

__all__ = [
    # Version
    "__version__",
    # Configuration
    "HermesConfig",
    # Backplane
    "SharedMemoryManager",
    "SignalRegistry",
    "SignalDescriptor",
    "SignalType",
    "SignalFlags",
    "FrameBarrier",
    # Protocol
    "MessageType",
    "ControlMessage",
    "Command",
    # Scripting
    "SimulationAPI",
]
