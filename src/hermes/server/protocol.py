"""WebSocket protocol messages for client-server communication.

This module defines the JSON message protocol used between Hermes
and connected clients (e.g., Daedalus visualization).

Message Types:
    Server → Client:
        - schema: Full signal schema on connect
        - event: State changes (paused, running, reset)
        - error: Error responses
        - ack: Command acknowledgments

    Client → Server:
        - cmd: Control commands with action and params
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ServerMessageType(str, Enum):
    """Types of messages sent from server to client."""

    SCHEMA = "schema"  # Signal schema on connect
    EVENT = "event"  # State change events
    ERROR = "error"  # Error responses
    ACK = "ack"  # Command acknowledgments


class EventType(str, Enum):
    """Types of state change events."""

    RUNNING = "running"
    PAUSED = "paused"
    RESET = "reset"
    STOPPED = "stopped"


class CommandAction(str, Enum):
    """Valid command actions from client."""

    PAUSE = "pause"
    RESUME = "resume"
    RESET = "reset"
    STEP = "step"
    SET = "set"
    SUBSCRIBE = "subscribe"


@dataclass
class ServerMessage:
    """Message sent from server to client.

    Attributes:
        type: Message type (schema, event, error, ack)
        payload: Message-specific data
    """

    type: ServerMessageType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize message to JSON string."""
        return json.dumps({"type": self.type.value, **self.payload})

    def to_bytes(self) -> bytes:
        """Serialize message to bytes for transmission."""
        return self.to_json().encode("utf-8")


@dataclass
class Command:
    """Command received from client.

    Attributes:
        action: Command action (pause, resume, reset, step, set, subscribe)
        params: Action-specific parameters
    """

    action: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: str) -> Command:
        """Parse command from JSON string.

        Args:
            data: JSON string containing command

        Returns:
            Parsed command

        Raises:
            ValueError: If JSON is invalid or missing required fields
        """
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValueError("Command must be a JSON object")

            action = parsed.get("action")
            if action is None:
                raise ValueError("Command missing 'action' field")

            params = parsed.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("Command 'params' must be an object")

            return cls(action=str(action), params=params)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

    def validate(self) -> None:
        """Validate command action and params.

        Raises:
            ValueError: If action is unknown or params are invalid
        """
        try:
            CommandAction(self.action)
        except ValueError:
            raise ValueError(f"Unknown action: {self.action}") from None

        # Validate action-specific params
        match self.action:
            case "step":
                if "count" in self.params:
                    count = self.params["count"]
                    if not isinstance(count, int) or count < 1:
                        raise ValueError("step 'count' must be a positive integer")

            case "set":
                if "signal" not in self.params:
                    raise ValueError("set command requires 'signal' param")
                if "value" not in self.params:
                    raise ValueError("set command requires 'value' param")

            case "subscribe":
                if "signals" not in self.params:
                    raise ValueError("subscribe command requires 'signals' param")
                signals = self.params["signals"]
                if not isinstance(signals, list):
                    raise ValueError("subscribe 'signals' must be a list")


# Factory functions for creating server messages


def make_schema(modules: dict[str, dict[str, Any]]) -> ServerMessage:
    """Create schema message with signal definitions.

    Args:
        modules: Dict of module name -> signal definitions

    Returns:
        Schema message ready for transmission
    """
    return ServerMessage(
        type=ServerMessageType.SCHEMA,
        payload={"modules": modules},
    )


def make_event(event: EventType | str) -> ServerMessage:
    """Create state change event message.

    Args:
        event: Event type (running, paused, reset, stopped)

    Returns:
        Event message ready for transmission
    """
    event_value = event.value if isinstance(event, EventType) else event
    return ServerMessage(
        type=ServerMessageType.EVENT,
        payload={"event": event_value},
    )


def make_error(message: str, code: int | None = None) -> ServerMessage:
    """Create error response message.

    Args:
        message: Error description
        code: Optional error code

    Returns:
        Error message ready for transmission
    """
    payload: dict[str, Any] = {"message": message}
    if code is not None:
        payload["code"] = code
    return ServerMessage(type=ServerMessageType.ERROR, payload=payload)


def make_ack(action: str, details: dict[str, Any] | None = None) -> ServerMessage:
    """Create command acknowledgment message.

    Args:
        action: Command action being acknowledged
        details: Optional additional details

    Returns:
        Ack message ready for transmission
    """
    payload: dict[str, Any] = {"action": action}
    if details:
        payload.update(details)
    return ServerMessage(type=ServerMessageType.ACK, payload=payload)
