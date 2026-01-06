"""IPC message formats for module control.

This module defines the message types used for control communication
between the Hermes scheduler and module processes via named pipes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class MessageType(str, Enum):
    """Control message types."""

    # Lifecycle commands
    STAGE = "stage"  # Prepare for execution
    RESET = "reset"  # Reset to initial conditions
    TERMINATE = "terminate"  # Graceful shutdown

    # Runtime control
    STEP = "step"  # Execute one frame
    PAUSE = "pause"  # Pause execution
    RESUME = "resume"  # Resume execution

    # Responses
    ACK = "ack"  # Command acknowledged
    ERROR = "error"  # Error occurred
    READY = "ready"  # Module ready for commands


@dataclass
class ControlMessage:
    """Control message sent via named pipe.

    Attributes:
        type: Message type
        payload: Optional JSON-serializable payload
    """

    type: MessageType
    payload: dict[str, object] | None = None

    def to_bytes(self) -> bytes:
        """Serialize message to bytes for pipe transmission.

        Format: JSON with newline terminator
        """
        data: dict[str, object] = {"type": self.type.value}
        if self.payload:
            data["payload"] = self.payload
        return json.dumps(data).encode("utf-8") + b"\n"

    @classmethod
    def from_bytes(cls, data: bytes) -> ControlMessage:
        """Deserialize message from bytes.

        Args:
            data: Raw bytes from pipe

        Returns:
            Parsed message

        Raises:
            ValueError: If message format invalid
        """
        text = data.decode("utf-8").strip()
        parsed = json.loads(text)

        msg_type = MessageType(parsed["type"])
        payload = parsed.get("payload")

        return cls(type=msg_type, payload=payload)


@dataclass
class Command:
    """High-level command structure for module control.

    Used by the ProcessManager to send commands to modules.
    """

    action: str
    params: dict[str, object] | None = None

    def to_message(self) -> ControlMessage:
        """Convert to ControlMessage for transmission."""
        try:
            msg_type = MessageType(self.action)
        except ValueError:
            msg_type = MessageType.STEP  # Default
            params: dict[str, object] = {"action": self.action}
            if self.params:
                params.update(self.params)
            return ControlMessage(type=msg_type, payload=params)

        return ControlMessage(type=msg_type, payload=self.params)
