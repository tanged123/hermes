"""WebSocket server and protocol implementation.

This module provides the WebSocket server for Hermes that enables:
- Real-time telemetry streaming to connected clients
- Control commands (pause, resume, reset, step, set)
- Signal subscription with wildcards
"""

from hermes.server.protocol import (
    Command,
    CommandAction,
    EventType,
    ServerMessage,
    ServerMessageType,
    make_ack,
    make_error,
    make_event,
    make_schema,
)
from hermes.server.telemetry import TelemetryEncoder
from hermes.server.websocket import ClientState, HermesServer, ServerConfig

__all__ = [
    # Protocol
    "Command",
    "CommandAction",
    "EventType",
    "ServerMessage",
    "ServerMessageType",
    "make_ack",
    "make_error",
    "make_event",
    "make_schema",
    # Telemetry
    "TelemetryEncoder",
    # WebSocket
    "ClientState",
    "HermesServer",
    "ServerConfig",
]
