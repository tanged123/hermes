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


# Microseconds per second constant for time conversions
_MICROSECONDS_PER_SECOND: int = 1_000_000


class ExecutionConfig(BaseModel):
    """Execution and scheduling settings.

    Time values are stored as floats for configuration convenience, but
    converted to integer microseconds at runtime for determinism.
    """

    mode: ExecutionMode = ExecutionMode.AFAP
    """Execution mode: realtime, afap, or single_frame."""

    rate_hz: float = 100.0
    """Simulation rate in Hz. Must produce an integer microsecond timestep."""

    end_time: float | None = None
    """Simulation end time in seconds. None = run until stopped."""

    schedule: list[str] = Field(default_factory=list)
    """Explicit execution order. Empty = registration order."""

    @field_validator("rate_hz")
    @classmethod
    def _validate_rate_hz(cls, v: float) -> float:
        """Validate that rate_hz produces an integer microsecond timestep."""
        if v <= 0:
            raise ValueError("rate_hz must be positive")
        # Check that 1/rate_hz produces an integer number of microseconds
        dt_us = _MICROSECONDS_PER_SECOND / v
        if abs(dt_us - round(dt_us)) > 1e-9:
            raise ValueError(
                f"rate_hz={v} does not produce an integer microsecond timestep. "
                f"dt would be {dt_us:.6f} µs. Use a rate that divides 1,000,000 evenly "
                f"(e.g., 1, 2, 4, 5, 8, 10, 20, 25, 40, 50, 100, 125, 200, 250, 500, 1000)."
            )
        return v

    def get_dt_us(self) -> int:
        """Get timestep in microseconds.

        Returns:
            Timestep as integer microseconds for deterministic simulation.
        """
        return round(_MICROSECONDS_PER_SECOND / self.rate_hz)

    def get_end_time_us(self) -> int | None:
        """Get end time in microseconds.

        Returns:
            End time as integer microseconds, or None if no end time set.
        """
        if self.end_time is None:
            return None
        return round(self.end_time * _MICROSECONDS_PER_SECOND)


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
        for name in self.execution.schedule:
            if name not in module_names:
                raise ValueError(f"Schedule references unknown module: {name}")

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
            return self.execution.schedule
        return list(self.modules.keys())
