"""Core configuration and process management for Hermes."""

from hermes.core.config import (
    ExecutionConfig,
    ExecutionMode,
    HermesConfig,
    ModuleConfig,
    ModuleType,
    ServerConfig,
    SignalConfig,
    WireConfig,
)
from hermes.core.process import ModuleInfo, ModuleProcess, ModuleState, ProcessManager

__all__ = [
    # Configuration
    "HermesConfig",
    "ModuleConfig",
    "ModuleType",
    "SignalConfig",
    "WireConfig",
    "ExecutionConfig",
    "ExecutionMode",
    "ServerConfig",
    # Process management
    "ProcessManager",
    "ModuleProcess",
    "ModuleState",
    "ModuleInfo",
]
