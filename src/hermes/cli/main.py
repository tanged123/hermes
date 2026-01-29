"""Command-line interface for Hermes simulation platform.

Provides commands for running and managing simulations from the command line.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import click
import structlog

from hermes import __version__
from hermes.core.config import HermesConfig
from hermes.core.process import ProcessManager
from hermes.core.scheduler import Scheduler
from hermes.server import HermesServer
from hermes.server import ServerConfig as WsServerConfig

log = structlog.get_logger()


def _configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure structlog with appropriate log level filtering."""
    import logging

    if quiet:
        min_level = logging.WARNING
    elif verbose:
        min_level = logging.DEBUG
    else:
        min_level = logging.INFO

    def _filter_by_level(
        _logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        if getattr(logging, method_name.upper(), 0) < min_level:
            raise structlog.DropEvent
        return event_dict

    structlog.configure(
        processors=[
            _filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
    )


@click.group()
@click.version_option(version=__version__, prog_name="hermes")
def cli() -> None:
    """Hermes - Simulation Orchestration Platform.

    Run and manage simulations from YAML configuration files.
    """


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress progress output",
)
@click.option(
    "--no-server",
    is_flag=True,
    help="Run without WebSocket server",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=None,
    help="WebSocket server port (overrides config)",
)
def run(config_path: Path, verbose: bool, quiet: bool, no_server: bool, port: int | None) -> None:
    """Run simulation from configuration file.

    CONFIG_PATH: Path to YAML configuration file
    """
    _configure_logging(verbose=verbose, quiet=quiet)

    # Load configuration
    log.info("Loading configuration", path=str(config_path))
    try:
        config = HermesConfig.from_yaml(config_path)
    except Exception as e:
        log.error("Failed to load configuration", error=str(e))
        raise SystemExit(1) from e

    log.info(
        "Configuration loaded",
        modules=len(config.modules),
        mode=config.execution.mode.value,
    )

    # Run simulation
    try:
        with ProcessManager(config) as pm:
            pm.load_all()

            sched = Scheduler(pm, config.execution)
            log.info("Staging simulation")
            sched.stage()

            # Determine server settings
            server_enabled = config.server.enabled and not no_server
            server_port = port if port is not None else config.server.port

            log.info(
                "Running simulation",
                mode=config.execution.mode.value,
                rate_hz=config.execution.rate_hz,
                end_time=config.execution.end_time,
                server=server_enabled,
            )

            async def main() -> None:
                # Set up signal handling for graceful shutdown
                # Must be inside async context to get the running loop
                shutdown_event = asyncio.Event()
                loop = asyncio.get_running_loop()

                def handle_signal(signum: int, _frame: object) -> None:
                    log.info("Received signal, stopping simulation", signal=signum)
                    loop.call_soon_threadsafe(shutdown_event.set)

                signal.signal(signal.SIGINT, handle_signal)
                signal.signal(signal.SIGTERM, handle_signal)

                tasks: list[asyncio.Task[Any]] = []
                server: HermesServer | None = None

                try:
                    # Start WebSocket server if enabled
                    if server_enabled and pm.shm is not None:
                        ws_config = WsServerConfig(
                            host=config.server.host,
                            port=server_port,
                            telemetry_hz=config.server.telemetry_hz,
                        )
                        server = HermesServer(pm.shm, sched, ws_config, hermes_config=config)
                        await server.start_background()
                        tasks.append(server.start_telemetry_loop())
                        log.info("WebSocket server started", port=server_port)

                    # Create telemetry callback
                    async def telemetry_callback(frame: int, time: float) -> None:
                        if not quiet and frame % 100 == 0:
                            log.info("Frame", frame=frame, time=f"{time:.3f}s")

                    # Run simulation until complete or shutdown signal
                    async def run_with_shutdown() -> None:
                        sim_task = asyncio.create_task(sched.run(callback=telemetry_callback))
                        shutdown_task = asyncio.create_task(shutdown_event.wait())

                        done, pending = await asyncio.wait(
                            [sim_task, shutdown_task],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await task

                        # Stop scheduler if shutdown was signaled
                        if shutdown_task in done:
                            sched.stop()

                    await run_with_shutdown()

                finally:
                    # Cleanup
                    for task in tasks:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task

                    if server is not None:
                        await server.stop()

            asyncio.run(main())

            log.info(
                "Simulation complete",
                frames=sched.frame,
                time=f"{sched.time:.3f}s",
            )
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception as e:
        log.error("Simulation failed", error=str(e))
        if verbose:
            import traceback

            traceback.print_exc()
        raise SystemExit(1) from e


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
def validate(config_path: Path) -> None:
    """Validate configuration file.

    CONFIG_PATH: Path to YAML configuration file

    Exits with code 0 if valid, 1 if invalid.
    """
    try:
        config = HermesConfig.from_yaml(config_path)
        log.info(
            "Configuration valid",
            modules=len(config.modules),
            wires=len(config.wiring),
            mode=config.execution.mode.value,
        )

        # List modules
        for name, module in config.modules.items():
            click.echo(f"  Module: {name} ({module.type.value})")
            for sig in module.signals:
                click.echo(f"    Signal: {sig.name} ({sig.type})")

    except Exception as e:
        log.error("Configuration invalid", error=str(e))
        raise SystemExit(1) from e


@cli.command("list-signals")
@click.option(
    "--shm-name",
    "-s",
    default=None,
    help="Shared memory segment name (default: auto-detect)",
)
def list_signals(shm_name: str | None) -> None:
    """List signals from a running simulation.

    Connects to the shared memory segment and lists all registered signals.
    """
    from hermes.backplane.shm import SharedMemoryManager

    if shm_name is None:
        log.error("Shared memory name required (auto-detect not yet implemented)")
        raise SystemExit(1)

    try:
        shm = SharedMemoryManager(shm_name)
        shm.attach()

        click.echo(f"Connected to: {shm_name}")
        click.echo(f"Frame: {shm.get_frame()}")
        click.echo(f"Time: {shm.get_time():.3f}s")

        # List signals (would need signal registry access)
        click.echo("\nSignals: (registry access not yet implemented)")

        shm.detach()
    except Exception as e:
        log.error("Failed to connect", error=str(e))
        raise SystemExit(1) from e


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
