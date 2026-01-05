"""Hermes - System Test and Execution Platform."""

__version__ = "0.1.0"

from hermes.core.module import ModuleAdapter
from hermes.core.signal import SignalBus, SignalDescriptor, Wire
from hermes.core.scheduler import Scheduler, SchedulerConfig, ExecutionMode
from hermes.core.config import HermesConfig

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
