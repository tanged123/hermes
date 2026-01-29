"""Configuration schema and loading for Hermes simulations.

This module defines the Pydantic models for YAML configuration files.
Configuration is a first-class citizen in Hermes - no recompilation needed.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ModuleType(str, Enum):
    """Module execution types."""

    PROCESS = "process"  # External executable (C, C++, Rust, etc.)
    INPROC = "inproc"  # In-process (pybind11, future)
    SCRIPT = "script"  # Python script as subprocess


class ExecutionMode(str, Enum):
    """Scheduler execution modes."""

    REALTIME = "realtime"  # Paced to wall-clock (HIL, visualization)
    AFAP = "afap"  # As fast as possible (batch, Monte Carlo)
    SINGLE_FRAME = "single_frame"  # Manual stepping (debug, scripted)


class SignalConfig(BaseModel):
    """Configuration for a module signal."""

    name: str
    """Signal name (local, without module prefix)."""

    type: str = "f64"
    """Data type: f64, f32, i64, i32, bool."""

    unit: str = ""
    """Physical unit string (e.g., 'm', 'rad/s')."""

    writable: bool = False
    """Whether signal can be modified via scripting API."""

    published: bool = True
    """Whether signal is included in telemetry streams."""


class ModuleConfig(BaseModel):
    """Configuration for a single module."""

    type: ModuleType
    """Module type: process, inproc, or script."""

    executable: Path | None = None
    """For process type: path to module executable."""

    script: Path | None = None
    """For script type: path to Python script."""

    inproc_module: str | None = None
    """For inproc type: dotted Python import path (e.g., 'hermes.modules.injection')."""

    config: Path | None = None
    """Path to module-specific configuration file."""

    signals: list[SignalConfig] = Field(default_factory=list)
    """Signal definitions (optional, can be discovered at runtime)."""

    options: dict[str, Any] = Field(default_factory=dict)
    """Additional module-specific options."""

    @field_validator("executable", "script", "config", mode="before")
    @classmethod
    def _coerce_path(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return None
        return Path(v)

    @model_validator(mode="after")
    def _validate_type_fields(self) -> ModuleConfig:
        """Ensure required fields are present for module type."""
        if self.type == ModuleType.PROCESS and self.executable is None:
            raise ValueError("'executable' required for process modules")
        if self.type == ModuleType.SCRIPT and self.script is None:
            raise ValueError("'script' required for script modules")
        if self.type == ModuleType.INPROC and self.inproc_module is None:
            raise ValueError("'inproc_module' required for inproc modules (dotted import path)")
        return self


class WireConfig(BaseModel):
    """Configuration for a signal wire (connection between modules)."""

    src: str
    """Source signal (qualified name: module.signal)."""

    dst: str
    """Destination signal (qualified name: module.signal)."""

    gain: float = 1.0
    """Multiplicative gain applied to signal."""

    offset: float = 0.0
    """Additive offset applied after gain."""

    @field_validator("src", "dst")
    @classmethod
    def _validate_qualified_name(cls, v: str) -> str:
        if "." not in v:
            raise ValueError(f"Expected 'module.signal' format: {v}")
        return v


# Nanoseconds per second constant for time conversions
_NANOSECONDS_PER_SECOND: int = 1_000_000_000


class ScheduleEntry(BaseModel):
    """Single entry in execution schedule.

    Supports both bare string and object formats for backwards compatibility::

        # Bare string (inherits execution.rate_hz)
        schedule: [inputs, physics]

        # Object with per-module rate
        schedule:
          - name: inputs
            rate_hz: 200.0
          - name: physics
            rate_hz: 1000.0
    """

    name: str
    """Module name."""

    rate_hz: float | None = None
    """Module execution rate in Hz. None = inherit from execution.rate_hz."""

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_string(cls, value: Any) -> dict[str, Any]:
        """Allow bare string format for backwards compatibility."""
        if isinstance(value, str):
            return {"name": value}
        return value


class ExecutionConfig(BaseModel):
    """Execution and scheduling settings.

    Time values are stored as floats for configuration convenience, but
    converted to integer nanoseconds at runtime for determinism.

    Any positive rate_hz is allowed. Rates that don't divide evenly into
    1 billion nanoseconds (e.g., 600 Hz) will have their timestep rounded,
    introducing bounded error that does not accumulate over time.
    """

    mode: ExecutionMode = ExecutionMode.AFAP
    """Execution mode: realtime, afap, or single_frame."""

    rate_hz: float = 100.0
    """Simulation rate in Hz. Any positive value is allowed."""

    end_time: float | None = None
    """Simulation end time in seconds. None = run until stopped."""

    schedule: list[ScheduleEntry] = Field(default_factory=list)
    """Execution schedule with optional per-module rates. Empty = registration order."""

    @field_validator("rate_hz")
    @classmethod
    def _validate_rate_hz(cls, v: float) -> float:
        """Validate that rate_hz is positive."""
        if v <= 0:
            raise ValueError("rate_hz must be positive")
        return v

    @model_validator(mode="after")
    def _validate_multi_rate(self) -> ExecutionConfig:
        """Validate that module rates are integer multiples of major frame rate."""
        if not self.schedule:
            return self

        major_rate = self.get_major_frame_rate_hz()

        for entry in self.schedule:
            entry_rate = entry.rate_hz if entry.rate_hz is not None else self.rate_hz
            if entry_rate <= 0:
                raise ValueError(f"Module '{entry.name}' rate must be positive")
            ratio = entry_rate / major_rate
            if abs(ratio - round(ratio)) > 1e-6:
                raise ValueError(
                    f"Module '{entry.name}' rate {entry_rate} Hz is not an "
                    f"integer multiple of major frame rate {major_rate} Hz"
                )

        return self

    def get_major_frame_rate_hz(self) -> float:
        """Get major frame rate (slowest module rate).

        Returns the minimum rate across all schedule entries. If no schedule
        or no entries have explicit rates, returns execution rate_hz.
        """
        if not self.schedule:
            return self.rate_hz

        rates = [
            entry.rate_hz if entry.rate_hz is not None else self.rate_hz for entry in self.schedule
        ]
        return min(rates)

    def get_dt_ns(self) -> int:
        """Get major frame timestep in nanoseconds.

        Returns:
            Timestep as integer nanoseconds for deterministic simulation.
            Rounded to nearest nanosecond for rates that don't divide evenly.
        """
        return round(_NANOSECONDS_PER_SECOND / self.get_major_frame_rate_hz())

    def get_end_time_ns(self) -> int | None:
        """Get end time in nanoseconds.

        Returns:
            End time as integer nanoseconds, or None if no end time set.
        """
        if self.end_time is None:
            return None
        return round(self.end_time * _NANOSECONDS_PER_SECOND)


class ServerConfig(BaseModel):
    """WebSocket server settings (Phase 2)."""

    enabled: bool = False
    """Whether to start WebSocket server."""

    host: str = "0.0.0.0"
    """Server bind address."""

    port: int = 8765
    """Server port."""

    telemetry_hz: float = 60.0
    """Telemetry streaming rate in Hz."""


class HermesConfig(BaseModel):
    """Root Hermes configuration."""

    version: str = "0.2"
    """Configuration schema version."""

    modules: dict[str, ModuleConfig]
    """Module configurations keyed by module name."""

    wiring: list[WireConfig] = Field(default_factory=list)
    """Signal wiring between modules."""

    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    """Execution settings."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    """WebSocket server settings."""

    @model_validator(mode="after")
    def _validate_references(self) -> HermesConfig:
        """Validate that wiring and schedule reference valid modules."""
        module_names = set(self.modules.keys())

        # Validate wiring references
        for wire in self.wiring:
            src_module = wire.src.split(".", 1)[0]
            dst_module = wire.dst.split(".", 1)[0]
            if src_module not in module_names:
                raise ValueError(f"Wire source module not found: {src_module}")
            if dst_module not in module_names:
                raise ValueError(f"Wire destination module not found: {dst_module}")

        # Validate schedule references
        for entry in self.execution.schedule:
            if entry.name not in module_names:
                raise ValueError(f"Schedule references unknown module: {entry.name}")

        return self

    @classmethod
    def from_yaml(cls, path: Path | str) -> HermesConfig:
        """Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            Parsed configuration

        Raises:
            FileNotFoundError: If file doesn't exist
            pydantic.ValidationError: If configuration invalid
        """
        import yaml

        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)

        config = cls.model_validate(data)

        # Resolve relative paths in module configs relative to config file
        config_dir = path.parent.resolve()
        for module in config.modules.values():
            if module.executable is not None and not module.executable.is_absolute():
                module.executable = config_dir / module.executable
            if module.script is not None and not module.script.is_absolute():
                module.script = config_dir / module.script
            if module.config is not None and not module.config.is_absolute():
                module.config = config_dir / module.config

        return config

    def get_dt(self) -> float:
        """Get timestep in seconds."""
        return 1.0 / self.execution.rate_hz

    def get_module_names(self) -> list[str]:
        """Get module names in execution order."""
        if self.execution.schedule:
            return [entry.name for entry in self.execution.schedule]
        return list(self.modules.keys())
