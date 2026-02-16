"""Process lifecycle management for Hermes modules.

This module provides the ProcessManager and ModuleProcess classes for
spawning, controlling, and terminating module subprocesses. Also supports
in-process (inproc) modules that run as Python objects within the main process.

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

import importlib
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

from hermes.exceptions import ModuleConfigError, ModuleError, ProcessError

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager
    from hermes.backplane.sync import FrameBarrier
    from hermes.core.config import HermesConfig, ModuleConfig
    from hermes.modules.icarus_module import IcarusModule

log = structlog.get_logger()


@runtime_checkable
class InprocModuleProtocol(Protocol):
    """Protocol for in-process module instances."""

    def stage(self) -> None: ...
    def step(self, dt: float) -> None: ...
    def reset(self) -> None: ...


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
            ModuleError: If process already started
            ModuleError: If executable not found
            ModuleConfigError: If module type is not supported
        """
        from hermes.core.config import ModuleType

        if self._process is not None:
            raise ModuleError(self._name, "already loaded")

        if self._config.type == ModuleType.PROCESS:
            self._start_executable()
        elif self._config.type == ModuleType.SCRIPT:
            self._start_script()
        else:
            raise ModuleConfigError(f"Unsupported module type: {self._config.type}")

        log.info("Module loaded", module=self._name, pid=self.pid)

    def _start_executable(self) -> None:
        """Start an external executable module."""
        if self._config.executable is None:
            raise ModuleConfigError(f"No executable for module {self._name}")

        exe_path = Path(self._config.executable)
        if not exe_path.exists():
            raise ModuleError(self._name, f"Executable not found: {exe_path}")

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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _start_script(self) -> None:
        """Start a Python script module."""
        if self._config.script is None:
            raise ModuleConfigError(f"No script for module {self._name}")

        script_path = Path(self._config.script)
        if not script_path.exists():
            raise ModuleError(self._name, f"Script not found: {script_path}")

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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stage(self) -> None:
        """Signal module to stage (prepare for execution).

        The module should initialize, validate configuration, and
        apply initial conditions.
        """
        if self._state != ModuleState.INIT:
            raise ModuleError(self._name, f"Cannot stage module in state {self._state}")

        # For now, staging is handled via environment/args at startup
        # Future: send STAGE command via named pipe
        self._state = ModuleState.STAGED
        log.debug("Module staged", module=self._name)

    def mark_running(self) -> None:
        """Transition module to RUNNING state when execution begins."""
        if self._state == ModuleState.STAGED:
            self._state = ModuleState.RUNNING
            log.debug("Module running", module=self._name)

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


class InprocModule:
    """Manages an in-process Python module.

    Wraps a Python object implementing InprocModuleProtocol,
    providing the same lifecycle interface as ModuleProcess
    but executing within the main process.
    """

    def __init__(
        self,
        name: str,
        instance: InprocModuleProtocol,
    ) -> None:
        self._name = name
        self._instance = instance
        self._state = ModuleState.INIT

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> ModuleState:
        return self._state

    @property
    def instance(self) -> InprocModuleProtocol:
        return self._instance

    def stage(self) -> None:
        """Stage the in-process module."""
        if self._state != ModuleState.INIT:
            raise ModuleError(self._name, f"Cannot stage module in state {self._state}")
        self._instance.stage()
        self._state = ModuleState.STAGED
        log.debug("Inproc module staged", module=self._name)

    def step(self, dt: float) -> None:
        """Step the in-process module."""
        if self._state == ModuleState.STAGED:
            self._state = ModuleState.RUNNING
        self._instance.step(dt)

    def reset(self) -> None:
        """Reset the in-process module."""
        self._instance.reset()
        self._state = ModuleState.INIT

    def introspect(self) -> dict[str, Any] | None:
        """Return module introspection payload if the instance supports it."""
        introspect = getattr(self._instance, "introspect", None)
        if callable(introspect):
            result = introspect()
            if isinstance(result, dict):
                return result
        return None

    def terminate(self) -> None:
        """Terminate the in-process module (no-op for inproc)."""
        self._state = ModuleState.DONE

    def get_info(self) -> ModuleInfo:
        return ModuleInfo(
            name=self._name,
            pid=None,
            state=self._state,
            shm_name="",
        )


def _create_inproc_module(
    name: str,
    config: ModuleConfig,
    shm: SharedMemoryManager,
) -> InprocModule:
    """Create an in-process module from configuration.

    Args:
        name: Module name
        config: Module configuration (script field is dotted import path)
        shm: Shared memory manager

    Returns:
        InprocModule wrapping the instantiated Python object
    """
    if config.inproc_module is None:
        raise ModuleConfigError(f"'inproc_module' required for inproc module {name}")

    module_path = config.inproc_module
    log.info("Loading inproc module", name=name, script=module_path)

    # Import the module
    mod = importlib.import_module(module_path)

    # Find the module class - look for known classes or use convention
    instance: InprocModuleProtocol | None = None

    # Convention: module exposes a class with stage/step/reset
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if (
            isinstance(attr, type)
            and attr_name != "InprocModuleProtocol"
            and isinstance(attr, type)
            and hasattr(attr, "stage")
            and hasattr(attr, "step")
            and hasattr(attr, "reset")
        ):
            # Try to construct with known signatures
            signal_names = [s.name for s in config.signals]
            try:
                instance = attr(
                    module_name=name,
                    shm=shm,
                    signals=signal_names,
                )
            except TypeError:
                # Try without signals arg (e.g., MockPhysicsModule)
                try:
                    instance = attr(
                        module_name=name,
                        shm=shm,
                    )
                except TypeError:
                    continue
            break

    if instance is None:
        raise ModuleConfigError(
            f"No valid module class found in {module_path}. "
            "Expected a class with stage(), step(dt), reset() methods."
        )

    return InprocModule(name=name, instance=instance)


class ProcessManager:
    """Coordinates all module processes.

    Manages the lifecycle of multiple module processes, including
    shared memory setup, synchronization, and orderly shutdown.
    Supports both subprocess (process/script) and in-process (inproc) modules.
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
        self._inproc_modules: dict[str, InprocModule] = {}
        self._shm_name = f"/hermes_{os.getpid()}"
        self._barrier_name = f"/hermes_barrier_{os.getpid()}"

    @property
    def config(self) -> HermesConfig:
        """Hermes configuration."""
        return self._config

    @property
    def shm(self) -> SharedMemoryManager | None:
        """Shared memory manager."""
        return self._shm

    @property
    def modules(self) -> dict[str, ModuleProcess]:
        """Loaded subprocess modules."""
        return self._modules

    @property
    def inproc_modules(self) -> dict[str, InprocModule]:
        """Loaded in-process modules."""
        return self._inproc_modules

    def initialize(self) -> None:
        """Create shared resources and load all modules.

        This sets up:
        1. Shared memory segment with all signals
        2. Synchronization barrier (for subprocess modules)
        3. Module processes / in-process modules

        If any step fails, previously created resources are cleaned up.
        """
        from hermes.backplane.shm import SharedMemoryManager
        from hermes.backplane.signals import SignalDescriptor, SignalFlags, SignalType
        from hermes.backplane.sync import FrameBarrier
        from hermes.core.config import ModuleType

        log.info("Initializing process manager")

        # Pre-create icarus modules for signal discovery (before shm allocation)
        icarus_modules: dict[str, IcarusModule] = {}
        for module_name, module_config in self._config.modules.items():
            if module_config.type == ModuleType.ICARUS:
                from hermes.modules.icarus_module import IcarusModule

                if module_config.config is None:
                    raise ModuleConfigError(f"'config' required for icarus module {module_name}")
                icarus_mod = IcarusModule(
                    module_name=module_name,
                    config_path=module_config.config,
                    prefix=module_name,
                )
                icarus_modules[module_name] = icarus_mod

        # Collect all signals from configuration
        signals: list[SignalDescriptor] = []
        for module_name, module_config in self._config.modules.items():
            # Icarus signals come from the simulator schema, not config
            if module_name in icarus_modules:
                signals.extend(icarus_modules[module_name].get_signal_descriptors())
                continue

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
        try:
            self._shm.create(signals)
            log.info("Shared memory created", name=self._shm_name, signals=len(signals))
        except Exception:
            self._shm = None
            raise

        # Count subprocess modules for barrier
        module_count = len(self._config.modules)
        if module_count < 1:
            self._shm.destroy()
            self._shm = None
            raise ProcessError("Cannot initialize ProcessManager with zero modules")

        subprocess_count = sum(
            1
            for mc in self._config.modules.values()
            if mc.type in (ModuleType.PROCESS, ModuleType.SCRIPT)
        )

        # Create synchronization barrier only if subprocess modules exist
        if subprocess_count > 0:
            self._barrier = FrameBarrier(self._barrier_name, subprocess_count)
            try:
                self._barrier.create()
                log.info(
                    "Barrier created",
                    name=self._barrier_name,
                    count=subprocess_count,
                )
            except Exception:
                self._shm.destroy()
                self._shm = None
                self._barrier = None
                raise

        # Create module instances
        try:
            for name, module_config in self._config.modules.items():
                if name in icarus_modules:
                    icarus_mod = icarus_modules[name]
                    icarus_mod.bind_shm(self._shm)
                    self._inproc_modules[name] = InprocModule(name=name, instance=icarus_mod)
                elif module_config.type == ModuleType.INPROC:
                    inproc = _create_inproc_module(name, module_config, self._shm)
                    self._inproc_modules[name] = inproc
                else:
                    module = ModuleProcess(
                        name=name,
                        config=module_config,
                        shm_name=self._shm_name,
                        barrier_name=self._barrier_name,
                    )
                    self._modules[name] = module
        except Exception:
            if self._barrier:
                self._barrier.destroy()
                self._barrier = None
            self._shm.destroy()
            self._shm = None
            self._modules.clear()
            self._inproc_modules.clear()
            raise

    def load_all(self) -> None:
        """Start all subprocess module processes."""
        for name in self._config.get_module_names():
            if name in self._modules:
                self._modules[name].load()

    def stage_all(self) -> None:
        """Stage all modules for execution."""
        for name in self._config.get_module_names():
            if name in self._modules:
                self._modules[name].stage()
            elif name in self._inproc_modules:
                self._inproc_modules[name].stage()

    def step_all(self, timeout: float = 30.0) -> None:
        """Execute one simulation frame across all modules.

        For subprocess modules, uses barrier synchronization.
        For inproc modules, calls step() directly in execution order.

        Args:
            timeout: Maximum seconds to wait for subprocess modules

        Raises:
            ProcessError: If not initialized
            TimeoutError: If subprocess modules don't complete within timeout
        """
        if self._shm is None:
            raise ProcessError("ProcessManager not initialized")

        major_dt = self._config.get_major_frame_dt()

        # Step subprocess modules via barrier (if any exist)
        if self._modules:
            if self._barrier is None:
                raise ProcessError("ProcessManager barrier not initialized")

            for module in self._modules.values():
                module.mark_running()

            self._barrier.signal_step()

            if not self._barrier.wait_all_done(timeout=timeout):
                log.error(
                    "Timeout waiting for modules to complete step",
                    timeout=timeout,
                )
                raise TimeoutError(f"Modules did not complete within {timeout}s")

        # Step inproc modules in execution order
        for name in self._config.get_module_names():
            if name in self._inproc_modules:
                self._inproc_modules[name].step(major_dt)

    def reset_all(self) -> None:
        """Reset all modules to initial state and re-stage them.

        Calls reset() on each inproc module, which restores initial
        conditions and resets signal values. Modules are then re-staged
        so they are ready for execution.

        Raises:
            ProcessError: If subprocess modules are present, since they
                cannot be reset without pipe IPC (not yet implemented).
        """
        if self._modules:
            subprocess_names = list(self._modules.keys())
            raise ProcessError(
                f"Cannot reset subprocess modules {subprocess_names}: "
                "named-pipe IPC not yet implemented. "
                "Reset is only supported for inproc/icarus modules."
            )

        # Reset in reverse execution order (mirrors terminate_all)
        for name in reversed(self._config.get_module_names()):
            if name in self._inproc_modules:
                self._inproc_modules[name].reset()
                log.debug("Inproc module reset", module=name)

        # Re-stage in execution order (mirrors stage_all)
        for name in self._config.get_module_names():
            if name in self._inproc_modules:
                self._inproc_modules[name].stage()

        log.info("All modules reset and re-staged")

    def update_time(self, frame: int, time_ns: int) -> None:
        """Update frame number and simulation time in shared memory.

        Args:
            frame: Current frame number
            time_ns: Current simulation time in nanoseconds
        """
        if self._shm is None:
            raise ProcessError("ProcessManager not initialized")

        self._shm.set_frame(frame)
        self._shm.set_time_ns(time_ns)

    def terminate_all(self) -> None:
        """Gracefully terminate all modules."""
        # Terminate in reverse order
        for name in reversed(self._config.get_module_names()):
            if name in self._modules:
                self._modules[name].terminate()
            elif name in self._inproc_modules:
                self._inproc_modules[name].terminate()

        # Clean up IPC resources
        if self._barrier:
            self._barrier.destroy()
            self._barrier = None

        if self._shm:
            self._shm.destroy()
            self._shm = None

        log.info("All modules terminated")

    def get_module(self, name: str) -> ModuleProcess | None:
        """Get a subprocess module by name."""
        return self._modules.get(name)

    def get_inproc_module(self, name: str) -> InprocModule | None:
        """Get an in-process module by name."""
        return self._inproc_modules.get(name)

    def get_module_instance(self, name: str) -> InprocModuleProtocol | None:
        """Get module instance by name for in-process modules."""
        inproc = self._inproc_modules.get(name)
        if inproc is None:
            return None
        return inproc.instance

    def __enter__(self) -> ProcessManager:
        """Context manager entry - initialize resources."""
        self.initialize()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit - clean up resources."""
        self.terminate_all()
