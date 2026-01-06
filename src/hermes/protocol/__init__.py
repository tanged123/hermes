"""Protocol definitions for module communication.

This package defines the interfaces and message formats for
communication between Hermes core and module processes.
"""

from hermes.protocol.messages import Command, ControlMessage, MessageType

__all__ = [
    "MessageType",
    "ControlMessage",
    "Command",
]
