"""Hermes - Simulation Orchestration Platform."""

__version__ = "0.1.0"

from hermes.core.config import HermesConfig
from hermes.core.module import ModuleAdapter
from hermes.core.scheduler import ExecutionMode, Scheduler, SchedulerConfig
from hermes.core.signal import SignalBus, SignalDescriptor, Wire

__all__ = [
    "ModuleAdapter",
    "SignalBus",
    "SignalDescriptor",
    "Wire",
    "Scheduler",
    "SchedulerConfig",
    "ExecutionMode",
    "HermesConfig",
]
