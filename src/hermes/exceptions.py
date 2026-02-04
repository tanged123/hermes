"""Hermes exception hierarchy.

This module defines the exception classes used throughout Hermes.
All exceptions inherit from HermesError for easy catching.

Exception Hierarchy:
    HermesError
    ├── ConfigError
    │   ├── ModuleConfigError
    │   └── WireConfigError
    ├── IPCError
    │   ├── SharedMemoryError
    │   └── SemaphoreError
    ├── ProcessError
    │   └── ModuleError
    ├── SignalError
    └── ProtocolError
"""

from __future__ import annotations


class HermesError(Exception):
    """Base exception for all Hermes errors."""


class ConfigError(HermesError):
    """Configuration-related errors."""


class ModuleConfigError(ConfigError):
    """Module configuration errors (missing fields, invalid paths)."""


class WireConfigError(ConfigError):
    """Wire configuration errors (invalid references)."""


class IPCError(HermesError):
    """IPC communication errors."""


class SharedMemoryError(IPCError):
    """Shared memory specific errors."""


class SemaphoreError(IPCError):
    """Semaphore/barrier specific errors."""


class ProcessError(HermesError):
    """Module process errors."""


class ModuleError(ProcessError):
    """Module-specific errors with module name context."""

    def __init__(self, module: str, message: str) -> None:
        """Initialize module error.

        Args:
            module: Name of the module that encountered the error
            message: Error description
        """
        self.module = module
        super().__init__(f"[{module}] {message}")


class SignalError(HermesError):
    """Signal routing errors."""


class ProtocolError(HermesError):
    """WebSocket protocol errors."""
