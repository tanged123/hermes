"""WebSocket server for Hermes telemetry and control.

This module provides the HermesServer class that enables external clients
(like Daedalus) to connect, receive telemetry, and send control commands.

Architecture:
    ┌─────────────────────────────────────────┐
    │              HermesServer               │
    ├─────────────────────────────────────────┤
    │  ┌─────────────┐    ┌────────────────┐  │
    │  │   Clients   │    │   Telemetry    │  │
    │  │   (set)     │    │   Encoder      │  │
    │  └─────────────┘    └────────────────┘  │
    │         │                   │           │
    │         ▼                   ▼           │
    │  ┌─────────────────────────────────────┐│
    │  │        Shared Memory                ││
    │  └─────────────────────────────────────┘│
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
import websockets
from websockets.asyncio.server import Server, ServerConnection, serve

from hermes.server.protocol import (
    Command,
    EventType,
    ServerMessage,
    make_ack,
    make_error,
    make_event,
    make_schema,
)
from hermes.server.telemetry import TelemetryEncoder

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager
    from hermes.core.scheduler import Scheduler


log = structlog.get_logger()


@dataclass
class ServerConfig:
    """Configuration for HermesServer.

    Attributes:
        host: Host to bind to
        port: Port to listen on
        telemetry_hz: Telemetry broadcast rate in Hz
    """

    host: str = "0.0.0.0"
    port: int = 8765
    telemetry_hz: float = 60.0


@dataclass
class ClientState:
    """Per-client state tracking.

    Attributes:
        ws: WebSocket connection
        encoder: Optional telemetry encoder for this client's subscription
        remote: Remote address for logging
    """

    ws: ServerConnection
    encoder: TelemetryEncoder | None = None
    remote: str = ""


CommandHandler = Callable[[ClientState, Command], Coroutine[Any, Any, ServerMessage | None]]


class HermesServer:
    """WebSocket server for Hermes telemetry and control.

    Handles client connections, schema distribution, command processing,
    and telemetry streaming.

    Example:
        server = HermesServer(shm, scheduler)
        await server.start()  # Runs forever
    """

    def __init__(
        self,
        shm: SharedMemoryManager,
        scheduler: Scheduler | None = None,
        config: ServerConfig | None = None,
    ) -> None:
        """Initialize the Hermes server.

        Args:
            shm: Shared memory manager to read telemetry from
            scheduler: Optional scheduler for control commands
            config: Server configuration
        """
        self._shm = shm
        self._scheduler = scheduler
        self._config = config or ServerConfig()

        self._clients: dict[ServerConnection, ClientState] = {}
        self._server: Server | None = None
        self._running = False
        self._telemetry_task: asyncio.Task[None] | None = None

        # Command handlers registered by action name
        self._handlers: dict[str, CommandHandler] = {}
        self._register_default_handlers()

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        """Whether the server is currently running."""
        return self._running

    def _register_default_handlers(self) -> None:
        """Register default command handlers."""
        self._handlers["subscribe"] = self._handle_subscribe

        # Control commands require scheduler
        self._handlers["pause"] = self._handle_pause
        self._handlers["resume"] = self._handle_resume
        self._handlers["reset"] = self._handle_reset
        self._handlers["step"] = self._handle_step
        self._handlers["set"] = self._handle_set

    async def start(self) -> None:
        """Start the WebSocket server.

        Runs until stop() is called or the server is shut down.
        """
        self._running = True
        log.info(
            "Starting WebSocket server",
            host=self._config.host,
            port=self._config.port,
        )

        async with serve(
            self._handle_client,
            self._config.host,
            self._config.port,
        ) as server:
            self._server = server
            log.info("Server listening", port=self._config.port)
            await server.serve_forever()

    async def start_background(self) -> None:
        """Start server and telemetry loop as background tasks.

        Returns immediately; use stop() to shut down.
        """
        self._running = True

        # Create server
        self._server = await serve(
            self._handle_client,
            self._config.host,
            self._config.port,
        )
        log.info(
            "Server started",
            host=self._config.host,
            port=self._config.port,
        )

    async def stop(self) -> None:
        """Stop the server gracefully."""
        log.info("Stopping server")
        self._running = False

        # Cancel telemetry task
        if self._telemetry_task is not None:
            self._telemetry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._telemetry_task
            self._telemetry_task = None

        # Close server
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, ws: ServerConnection) -> None:
        """Handle a new client connection."""
        remote = str(ws.remote_address) if ws.remote_address else "unknown"
        state = ClientState(ws=ws, remote=remote)
        self._clients[ws] = state

        log.info("Client connected", remote=remote, clients=len(self._clients))

        try:
            # Send schema on connect
            await self._send_schema(state)

            # Process messages
            async for message in ws:
                if isinstance(message, str):
                    await self._handle_message(state, message)
                else:
                    # Binary messages not expected from client
                    log.warning("Unexpected binary message", remote=remote)

        except websockets.exceptions.ConnectionClosed as e:
            log.info("Client connection closed", remote=remote, code=e.code)
        except Exception as e:
            log.error("Client handler error", remote=remote, error=str(e))
        finally:
            del self._clients[ws]
            log.info("Client disconnected", remote=remote, clients=len(self._clients))

    async def _send_schema(self, client: ClientState) -> None:
        """Send signal schema to a client."""
        # Build schema from shared memory signals
        signals = self._shm.signal_names()

        # Group signals by module prefix
        modules: dict[str, dict[str, Any]] = {}
        for sig_name in signals:
            # Parse module.signal format
            if "." in sig_name:
                module, signal = sig_name.rsplit(".", 1)
            else:
                module = "_default"
                signal = sig_name

            if module not in modules:
                modules[module] = {"signals": []}

            modules[module]["signals"].append({"name": signal, "type": "f64"})

        msg = make_schema(modules)
        await client.ws.send(msg.to_json())
        log.debug("Sent schema", remote=client.remote, modules=list(modules.keys()))

    async def _handle_message(self, client: ClientState, message: str) -> None:
        """Handle a text message from a client."""
        try:
            cmd = Command.from_json(message)
            log.debug("Received command", remote=client.remote, action=cmd.action)

            # Validate command
            try:
                cmd.validate()
            except ValueError as e:
                await client.ws.send(make_error(str(e)).to_json())
                return

            # Find and execute handler
            handler = self._handlers.get(cmd.action)
            if handler is None:
                await client.ws.send(make_error(f"Unknown action: {cmd.action}").to_json())
                return

            response = await handler(client, cmd)
            if response is not None:
                await client.ws.send(response.to_json())

        except ValueError as e:
            log.warning("Invalid message", remote=client.remote, error=str(e))
            await client.ws.send(make_error(str(e)).to_json())

    # Command handlers

    async def _handle_subscribe(self, client: ClientState, cmd: Command) -> ServerMessage | None:
        """Handle subscribe command."""
        signals = cmd.params.get("signals", [])

        # Expand wildcards
        expanded = self._expand_signal_patterns(signals)

        # Create encoder for this client
        client.encoder = TelemetryEncoder(self._shm, expanded)

        log.info(
            "Client subscribed",
            remote=client.remote,
            signals=len(expanded),
        )

        return make_ack("subscribe", {"count": len(expanded), "signals": expanded})

    async def _handle_pause(self, _client: ClientState, _cmd: Command) -> ServerMessage | None:
        """Handle pause command."""
        if self._scheduler is None:
            return make_error("No scheduler attached")

        self._scheduler.pause()
        await self._broadcast_event(EventType.PAUSED)
        return make_ack("pause")

    async def _handle_resume(self, _client: ClientState, _cmd: Command) -> ServerMessage | None:
        """Handle resume command."""
        if self._scheduler is None:
            return make_error("No scheduler attached")

        self._scheduler.resume()
        await self._broadcast_event(EventType.RUNNING)
        return make_ack("resume")

    async def _handle_reset(self, _client: ClientState, _cmd: Command) -> ServerMessage | None:
        """Handle reset command."""
        if self._scheduler is None:
            return make_error("No scheduler attached")

        self._scheduler.reset()
        await self._broadcast_event(EventType.RESET)
        return make_ack("reset")

    async def _handle_step(self, _client: ClientState, cmd: Command) -> ServerMessage | None:
        """Handle step command."""
        if self._scheduler is None:
            return make_error("No scheduler attached")

        count = cmd.params.get("count", 1)
        self._scheduler.step(count)
        return make_ack("step", {"count": count, "frame": self._scheduler.frame})

    async def _handle_set(self, _client: ClientState, cmd: Command) -> ServerMessage | None:
        """Handle set command."""
        signal = cmd.params["signal"]
        value = cmd.params["value"]

        try:
            self._shm.set_signal(signal, float(value))
            return make_ack("set", {"signal": signal, "value": value})
        except KeyError:
            return make_error(f"Unknown signal: {signal}")
        except (TypeError, ValueError) as e:
            return make_error(f"Invalid value: {e}")

    def _expand_signal_patterns(self, patterns: list[str]) -> list[str]:
        """Expand signal patterns to full signal names.

        Patterns:
            - "*" matches all signals
            - "module.*" matches all signals from module
            - "module.signal" matches exact signal
        """
        all_signals = self._shm.signal_names()
        result: list[str] = []

        for pattern in patterns:
            if pattern == "*":
                result.extend(all_signals)
            elif pattern.endswith(".*"):
                prefix = pattern[:-1]  # "module." without the "*"
                result.extend(s for s in all_signals if s.startswith(prefix))
            else:
                # Exact match
                if pattern in all_signals:
                    result.append(pattern)

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for s in result:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return unique

    async def _broadcast_event(self, event: EventType) -> None:
        """Broadcast state change event to all clients."""
        msg = make_event(event)
        await self._broadcast_json(msg.to_json())

    async def _broadcast_json(self, json_str: str) -> None:
        """Broadcast JSON message to all clients."""
        if not self._clients:
            return

        await asyncio.gather(
            *(client.ws.send(json_str) for client in self._clients.values()),
            return_exceptions=True,
        )

    async def broadcast_telemetry(self) -> None:
        """Broadcast binary telemetry to subscribed clients."""
        for client in self._clients.values():
            if client.encoder is not None:
                try:
                    frame = client.encoder.encode()
                    await client.ws.send(frame)
                except Exception as e:
                    log.warning(
                        "Telemetry send failed",
                        remote=client.remote,
                        error=str(e),
                    )

    async def telemetry_loop(self, rate_hz: float | None = None) -> None:
        """Background task that broadcasts telemetry at fixed rate.

        Args:
            rate_hz: Telemetry rate in Hz (default from config)
        """
        hz = rate_hz or self._config.telemetry_hz
        interval = 1.0 / hz

        log.info("Starting telemetry loop", rate_hz=hz)

        while self._running:
            await asyncio.sleep(interval)
            await self.broadcast_telemetry()

    def start_telemetry_loop(self, rate_hz: float | None = None) -> asyncio.Task[None]:
        """Start telemetry loop as a background task.

        Args:
            rate_hz: Telemetry rate in Hz (default from config)

        Returns:
            The created task
        """
        self._telemetry_task = asyncio.create_task(self.telemetry_loop(rate_hz))
        return self._telemetry_task
