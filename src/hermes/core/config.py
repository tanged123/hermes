"""Configuration schema and loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ModuleConfig(BaseModel):
    """Configuration for a single module."""

    adapter: str
    """Adapter type: "icarus", "script", "injection", etc."""

    config: str | None = None
    """Path to module-specific configuration file."""

    lib_path: str | None = None
    """For icarus adapter: path to libicarus.so."""

    script: str | None = None
    """For script adapter: path to Python module."""

    signals: list[str] | None = None
    """For injection adapter: list of signal names to create."""

    options: dict[str, Any] = Field(default_factory=dict)
    """Additional adapter-specific options."""


class WireConfig(BaseModel):
    """Configuration for a signal wire."""

    src: str
    """Source signal (qualified name: module.signal)."""

    dst: str
    """Destination signal (qualified name: module.signal)."""

    gain: float = 1.0
    """Multiplicative gain applied to signal."""

    offset: float = 0.0
    """Additive offset applied after gain."""


class ExecutionConfig(BaseModel):
    """Execution settings."""

    mode: str = "afap"
    """Execution mode: "afap" (as fast as possible), "realtime", "paused"."""

    rate_hz: float = 100.0
    """Simulation rate in Hz."""

    end_time: float | None = None
    """Simulation end time in seconds. None = run until stopped."""


class ServerConfig(BaseModel):
    """WebSocket server settings."""

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

        return cls(**data)

    def get_dt(self) -> float:
        """Get timestep in seconds."""
        return 1.0 / self.execution.rate_hz
