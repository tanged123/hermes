"""Command-line interface for Hermes simulation platform.

Provides commands for running and managing simulations from the command line.
"""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import click
import structlog

from hermes import __version__
from hermes.core.config import HermesConfig
from hermes.core.process import ProcessManager
from hermes.core.scheduler import Scheduler

# Configure structlog for console output
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=True),
    ],
)
log = structlog.get_logger()


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
def run(config_path: Path, verbose: bool, quiet: bool) -> None:
    """Run simulation from configuration file.

    CONFIG_PATH: Path to YAML configuration file
    """
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

    # Set up signal handling for graceful shutdown
    scheduler: Scheduler | None = None

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal scheduler
        log.info("Received signal, stopping simulation", signal=signum)
        if scheduler is not None:
            scheduler.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Run simulation
    try:
        with ProcessManager(config) as pm:
            pm.load_all()

            scheduler = Scheduler(pm, config.execution)
            log.info("Staging simulation")
            scheduler.stage()

            log.info(
                "Running simulation",
                mode=config.execution.mode.value,
                rate_hz=config.execution.rate_hz,
                end_time=config.execution.end_time,
            )

            # Create telemetry callback
            async def telemetry_callback(frame: int, time: float) -> None:
                if not quiet and frame % 100 == 0:
                    log.info("Frame", frame=frame, time=f"{time:.3f}s")

            # Run the simulation
            asyncio.run(scheduler.run(callback=telemetry_callback))

            log.info(
                "Simulation complete",
                frames=scheduler.frame,
                time=f"{scheduler.time:.3f}s",
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
