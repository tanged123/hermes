"""Data backplane for inter-process communication.

This package provides the IPC infrastructure for Hermes:
- Shared memory for signal data
- Semaphores for frame synchronization
- Signal registry and routing
"""

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.signals import SignalDescriptor, SignalFlags, SignalRegistry, SignalType
from hermes.backplane.sync import FrameBarrier

__all__ = [
    "SharedMemoryManager",
    "SignalRegistry",
    "SignalDescriptor",
    "SignalType",
    "SignalFlags",
    "FrameBarrier",
]
