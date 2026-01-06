"""Python API for interacting with running simulations.

This module provides the SimulationAPI class for external scripts to
connect to and interact with running Hermes simulations via shared memory.

Example:
    from hermes.scripting import SimulationAPI

    with SimulationAPI("/hermes_sim") as sim:
        # Wait for simulation to start
        sim.wait_frame(10)

        # Inject a value
        sim.set("module.signal", 100.0)

        # Sample results
        value = sim.get("module.output")
        print(f"Output: {value}")

Determinism:
    Time is tracked internally as integer nanoseconds. Use `get_time_ns()`
    and `wait_time_ns()` for deterministic comparisons. The float-based
    `get_time()` and `wait_time()` methods are provided for convenience.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class SimulationAPI:
    """Python API for interacting with running simulations.

    Connects to a Hermes simulation via shared memory and provides
    methods for reading and writing signal values.
    """

    def __init__(self, shm_name: str) -> None:
        """Initialize simulation API.

        Args:
            shm_name: Shared memory segment name (e.g., "/hermes_sim")
        """
        from hermes.backplane.shm import SharedMemoryManager

        self._shm_name = shm_name
        self._shm = SharedMemoryManager(shm_name)
        self._attached = False

    def connect(self) -> None:
        """Connect to the simulation's shared memory.

        Raises:
            RuntimeError: If already connected
            posix_ipc.ExistentialError: If simulation not running
        """
        if self._attached:
            raise RuntimeError("Already connected")
        self._shm.attach()
        self._attached = True

    def disconnect(self) -> None:
        """Disconnect from the simulation."""
        if self._attached:
            self._shm.detach()
            self._attached = False

    def get(self, signal: str) -> float:
        """Get signal value by qualified name.

        Args:
            signal: Full signal path (module.signal)

        Returns:
            Current signal value

        Raises:
            RuntimeError: If not connected
            KeyError: If signal not found
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")
        return self._shm.get_signal(signal)

    def set(self, signal: str, value: float) -> None:
        """Set signal value by qualified name.

        Args:
            signal: Full signal path (module.signal)
            value: Value to set

        Raises:
            RuntimeError: If not connected
            KeyError: If signal not found
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")
        self._shm.set_signal(signal, value)

    def get_frame(self) -> int:
        """Get current simulation frame number.

        Returns:
            Current frame number

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")
        return self._shm.get_frame()

    def get_time(self) -> float:
        """Get current simulation time in seconds.

        This is derived from `get_time_ns()` for API convenience.
        For deterministic comparisons, use `get_time_ns()` instead.

        Returns:
            Current simulation time in seconds

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")
        return self._shm.get_time()

    def get_time_ns(self) -> int:
        """Get current simulation time in nanoseconds.

        This is the authoritative time value for deterministic simulations.
        Use this for exact comparisons and reproducibility.

        Returns:
            Current simulation time in nanoseconds

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")
        return self._shm.get_time_ns()

    def wait_frame(self, target: int, timeout: float = 10.0) -> bool:
        """Wait until simulation reaches target frame.

        Args:
            target: Target frame number
            timeout: Maximum seconds to wait

        Returns:
            True if target reached, False if timeout

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")

        start = time.time()
        while self.get_frame() < target:
            if time.time() - start > timeout:
                return False
            time.sleep(0.001)
        return True

    def wait_time(self, target: float, timeout: float = 10.0) -> bool:
        """Wait until simulation reaches target time in seconds.

        Note: Uses floating-point comparison. For deterministic behavior,
        use `wait_time_ns()` instead.

        Args:
            target: Target simulation time in seconds
            timeout: Maximum wall-clock seconds to wait

        Returns:
            True if target reached, False if timeout

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")

        start = time.time()
        while self.get_time() < target:
            if time.time() - start > timeout:
                return False
            time.sleep(0.001)
        return True

    def wait_time_ns(self, target_ns: int, timeout: float = 10.0) -> bool:
        """Wait until simulation reaches target time in nanoseconds.

        This is the deterministic version - uses integer comparison for
        exact reproducibility.

        Args:
            target_ns: Target simulation time in nanoseconds
            timeout: Maximum wall-clock seconds to wait

        Returns:
            True if target reached, False if timeout

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")

        start = time.time()
        while self.get_time_ns() < target_ns:
            if time.time() - start > timeout:
                return False
            time.sleep(0.001)
        return True

    def inject(self, values: dict[str, float]) -> None:
        """Inject multiple values at once.

        Args:
            values: Dictionary mapping signal names to values

        Raises:
            RuntimeError: If not connected
            KeyError: If any signal not found
        """
        for signal, value in values.items():
            self.set(signal, value)

    def sample(self, signals: list[str]) -> dict[str, float]:
        """Sample multiple signals at once.

        Args:
            signals: List of signal names

        Returns:
            Dictionary mapping signal names to values

        Raises:
            RuntimeError: If not connected
            KeyError: If any signal not found
        """
        return {s: self.get(s) for s in signals}

    def list_signals(self) -> list[str]:
        """Get list of all available signals.

        Returns:
            List of qualified signal names

        Raises:
            RuntimeError: If not connected
        """
        if not self._attached:
            raise RuntimeError("Not connected to simulation")
        return self._shm.signal_names()

    def __enter__(self) -> SimulationAPI:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.disconnect()
