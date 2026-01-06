"""Process lifecycle management for Hermes modules.

This module provides the ProcessManager and ModuleProcess classes for
spawning, controlling, and terminating module subprocesses.

Module Lifecycle:
    load()        stage()       step()...      terminate()
      │             │              │               │
      ▼             ▼              ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐     ┌─────────┐
│  INIT   │──▶│ STAGED  │──▶│ RUNNING │────▶│  DONE   │
└─────────┘   └─────────┘   └─────────┘     └─────────┘
      │                           │
      └───────── reset() ─────────┘
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager
    from hermes.backplane.sync import FrameBarrier
    from hermes.core.config import HermesConfig, ModuleConfig

log = structlog.get_logger()


class ModuleState(Enum):
    """Module lifecycle states."""

    INIT = "init"  # Process started, not yet staged
    STAGED = "staged"  # Ready for execution
    RUNNING = "running"  # Actively executing frames
    PAUSED = "paused"  # Execution paused
    DONE = "done"  # Terminated normally
    ERROR = "error"  # Terminated with error


@dataclass
class ModuleInfo:
    """Runtime information about a module."""

    name: str
    pid: int | None
    state: ModuleState
    shm_name: str
    signals: list[str] = field(default_factory=list)


class ModuleProcess:
    """Manages a single module subprocess.

    Handles the lifecycle of a module process including spawning,
    communication via named pipes, and synchronization via semaphores.
    """

    def __init__(
        self,
        name: str,
        config: ModuleConfig,
        shm_name: str,
        barrier_name: str,
    ) -> None:
        """Initialize module process manager.

        Args:
            name: Module name
            config: Module configuration
            shm_name: Shared memory segment name
            barrier_name: Frame barrier name
        """
        self._name = name
        self._config = config
        self._shm_name = shm_name
        self._barrier_name = barrier_name
        self._process: subprocess.Popen[bytes] | None = None
        self._state = ModuleState.INIT

    @property
    def name(self) -> str:
        """Module name."""
        return self._name

    @property
    def state(self) -> ModuleState:
        """Current module state."""
        return self._state

    @property
    def pid(self) -> int | None:
        """Process ID if running."""
        return self._process.pid if self._process else None

    @property
    def is_alive(self) -> bool:
        """Whether the process is still running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def load(self) -> None:
        """Start the module process.

        Raises:
            RuntimeError: If process already started
            FileNotFoundError: If executable not found
        """
        from hermes.core.config import ModuleType

        if self._process is not None:
            raise RuntimeError(f"Module {self._name} already loaded")

        if self._config.type == ModuleType.PROCESS:
            self._start_executable()
        elif self._config.type == ModuleType.SCRIPT:
            self._start_script()
        else:
            raise ValueError(f"Unsupported module type: {self._config.type}")

        log.info("Module loaded", module=self._name, pid=self.pid)

    def _start_executable(self) -> None:
        """Start an external executable module."""
        if self._config.executable is None:
            raise ValueError(f"No executable for module {self._name}")

        exe_path = Path(self._config.executable)
        if not exe_path.exists():
            raise FileNotFoundError(f"Executable not found: {exe_path}")

        args = [str(exe_path), self._shm_name]
        if self._config.config:
            args.append(str(self._config.config))

        env = os.environ.copy()
        env["HERMES_MODULE_NAME"] = self._name
        env["HERMES_SHM_NAME"] = self._shm_name
        env["HERMES_BARRIER_NAME"] = self._barrier_name

        self._process = subprocess.Popen(
            args,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _start_script(self) -> None:
        """Start a Python script module."""
        if self._config.script is None:
            raise ValueError(f"No script for module {self._name}")

        script_path = Path(self._config.script)
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")

        args = [sys.executable, str(script_path), self._shm_name]
        if self._config.config:
            args.append(str(self._config.config))

        env = os.environ.copy()
        env["HERMES_MODULE_NAME"] = self._name
        env["HERMES_SHM_NAME"] = self._shm_name
        env["HERMES_BARRIER_NAME"] = self._barrier_name

        self._process = subprocess.Popen(
            args,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def stage(self) -> None:
        """Signal module to stage (prepare for execution).

        The module should initialize, validate configuration, and
        apply initial conditions.
        """
        if self._state != ModuleState.INIT:
            raise RuntimeError(f"Cannot stage module in state {self._state}")

        # For now, staging is handled via environment/args at startup
        # Future: send STAGE command via named pipe
        self._state = ModuleState.STAGED
        log.debug("Module staged", module=self._name)

    def terminate(self, timeout: float = 5.0) -> None:
        """Gracefully terminate the module.

        Args:
            timeout: Seconds to wait before force killing
        """
        if self._process is None:
            return

        log.info("Terminating module", module=self._name)

        # Try graceful termination first
        self._process.terminate()
        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("Module did not terminate, killing", module=self._name)
            self._process.kill()
            self._process.wait()

        self._state = ModuleState.DONE
        self._process = None

    def kill(self) -> None:
        """Forcefully kill the module process."""
        if self._process is None:
            return

        log.warning("Killing module", module=self._name)
        self._process.kill()
        self._process.wait()
        self._state = ModuleState.DONE
        self._process = None

    def get_info(self) -> ModuleInfo:
        """Get current module information."""
        return ModuleInfo(
            name=self._name,
            pid=self.pid,
            state=self._state,
            shm_name=self._shm_name,
        )


class ProcessManager:
    """Coordinates all module processes.

    Manages the lifecycle of multiple module processes, including
    shared memory setup, synchronization, and orderly shutdown.
    """

    def __init__(self, config: HermesConfig) -> None:
        """Initialize process manager.

        Args:
            config: Hermes configuration
        """
        self._config = config
        self._shm: SharedMemoryManager | None = None
        self._barrier: FrameBarrier | None = None
        self._modules: dict[str, ModuleProcess] = {}
        self._shm_name = f"/hermes_{os.getpid()}"
        self._barrier_name = f"/hermes_barrier_{os.getpid()}"

    @property
    def shm(self) -> SharedMemoryManager | None:
        """Shared memory manager."""
        return self._shm

    @property
    def modules(self) -> dict[str, ModuleProcess]:
        """Loaded modules."""
        return self._modules

    def initialize(self) -> None:
        """Create shared resources and load all modules.

        This sets up:
        1. Shared memory segment with all signals
        2. Synchronization barrier
        3. Module processes
        """
        from hermes.backplane.shm import SharedMemoryManager
        from hermes.backplane.signals import SignalDescriptor, SignalFlags, SignalType
        from hermes.backplane.sync import FrameBarrier

        log.info("Initializing process manager")

        # Collect all signals from configuration
        signals: list[SignalDescriptor] = []
        for module_name, module_config in self._config.modules.items():
            for sig_cfg in module_config.signals:
                # Convert config signal type to backplane SignalType
                sig_type = SignalType.F64  # Default
                if sig_cfg.type == "f32":
                    sig_type = SignalType.F32
                elif sig_cfg.type == "i64":
                    sig_type = SignalType.I64
                elif sig_cfg.type == "i32":
                    sig_type = SignalType.I32
                elif sig_cfg.type == "bool":
                    sig_type = SignalType.BOOL

                flags: int = SignalFlags.NONE
                if sig_cfg.writable:
                    flags |= SignalFlags.WRITABLE
                if sig_cfg.published:
                    flags |= SignalFlags.PUBLISHED

                signals.append(
                    SignalDescriptor(
                        name=f"{module_name}.{sig_cfg.name}",
                        type=sig_type,
                        flags=flags,
                        unit=sig_cfg.unit,
                    )
                )

        # Create shared memory
        self._shm = SharedMemoryManager(self._shm_name)
        self._shm.create(signals)
        log.info("Shared memory created", name=self._shm_name, signals=len(signals))

        # Create synchronization barrier
        module_count = len(self._config.modules)
        self._barrier = FrameBarrier(self._barrier_name, module_count)
        self._barrier.create()
        log.info("Barrier created", name=self._barrier_name, count=module_count)

        # Load each module process
        for name, module_config in self._config.modules.items():
            module = ModuleProcess(
                name=name,
                config=module_config,
                shm_name=self._shm_name,
                barrier_name=self._barrier_name,
            )
            self._modules[name] = module

    def load_all(self) -> None:
        """Start all module processes."""
        for name in self._config.get_module_names():
            if name in self._modules:
                self._modules[name].load()

    def stage_all(self) -> None:
        """Stage all modules for execution."""
        for name in self._config.get_module_names():
            if name in self._modules:
                self._modules[name].stage()

    def step_all(self) -> None:
        """Execute one simulation frame across all modules.

        Uses barrier synchronization:
        1. Signal all modules to execute their step
        2. Wait for all modules to complete
        """
        if self._barrier is None:
            raise RuntimeError("ProcessManager not initialized")

        # Signal all modules to step
        self._barrier.signal_step()

        # Wait for all modules to complete
        self._barrier.wait_all_done()

    def update_time(self, frame: int, time: float) -> None:
        """Update frame number and simulation time in shared memory.

        Args:
            frame: Current frame number
            time: Current simulation time in seconds
        """
        if self._shm is None:
            raise RuntimeError("ProcessManager not initialized")

        self._shm.set_frame(frame)
        self._shm.set_time(time)

    def terminate_all(self) -> None:
        """Gracefully terminate all modules."""
        # Terminate in reverse order
        for name in reversed(self._config.get_module_names()):
            if name in self._modules:
                self._modules[name].terminate()

        # Clean up IPC resources
        if self._barrier:
            self._barrier.destroy()
            self._barrier = None

        if self._shm:
            self._shm.destroy()
            self._shm = None

        log.info("All modules terminated")

    def get_module(self, name: str) -> ModuleProcess | None:
        """Get a module by name."""
        return self._modules.get(name)

    def __enter__(self) -> ProcessManager:
        """Context manager entry - initialize resources."""
        self.initialize()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit - clean up resources."""
        self.terminate_all()
