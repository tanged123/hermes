"""Tests for configuration parsing and validation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hermes.core.config import (
    ExecutionConfig,
    ExecutionMode,
    HermesConfig,
    ModuleConfig,
    ModuleType,
    SignalConfig,
    WireConfig,
)


class TestModuleType:
    """Tests for ModuleType enum."""

    def test_module_types_exist(self) -> None:
        """All expected module types should exist."""
        assert ModuleType.PROCESS.value == "process"
        assert ModuleType.INPROC.value == "inproc"
        assert ModuleType.SCRIPT.value == "script"


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_execution_modes_exist(self) -> None:
        """All expected execution modes should exist."""
        assert ExecutionMode.REALTIME.value == "realtime"
        assert ExecutionMode.AFAP.value == "afap"
        assert ExecutionMode.SINGLE_FRAME.value == "single_frame"


class TestSignalConfig:
    """Tests for SignalConfig model."""

    def test_signal_config_defaults(self) -> None:
        """Should use sensible defaults."""
        sig = SignalConfig(name="test")
        assert sig.name == "test"
        assert sig.type == "f64"
        assert sig.unit == ""
        assert sig.writable is False
        assert sig.published is True

    def test_signal_config_full(self) -> None:
        """Should accept all fields."""
        sig = SignalConfig(
            name="position",
            type="f32",
            unit="m",
            writable=True,
            published=False,
        )
        assert sig.name == "position"
        assert sig.type == "f32"
        assert sig.unit == "m"
        assert sig.writable is True
        assert sig.published is False


class TestModuleConfig:
    """Tests for ModuleConfig model."""

    def test_process_module_requires_executable(self) -> None:
        """Process modules must have executable."""
        with pytest.raises(ValueError, match="executable"):
            ModuleConfig(type=ModuleType.PROCESS)

    def test_script_module_requires_script(self) -> None:
        """Script modules must have script path."""
        with pytest.raises(ValueError, match="script"):
            ModuleConfig(type=ModuleType.SCRIPT)

    def test_process_module_with_executable(self) -> None:
        """Process modules should accept executable."""
        mod = ModuleConfig(type=ModuleType.PROCESS, executable="./test")
        assert mod.executable == Path("./test")

    def test_script_module_with_script(self) -> None:
        """Script modules should accept script."""
        mod = ModuleConfig(type=ModuleType.SCRIPT, script="./test.py")
        assert mod.script == Path("./test.py")


class TestWireConfig:
    """Tests for WireConfig model."""

    def test_wire_config_requires_qualified_names(self) -> None:
        """Wire src/dst must be qualified (module.signal)."""
        with pytest.raises(ValueError, match="module.signal"):
            WireConfig(src="nope", dst="also_nope")

    def test_wire_config_valid(self) -> None:
        """Valid wire configuration."""
        wire = WireConfig(
            src="module_a.output",
            dst="module_b.input",
            gain=2.0,
            offset=1.0,
        )
        assert wire.src == "module_a.output"
        assert wire.dst == "module_b.input"
        assert wire.gain == 2.0
        assert wire.offset == 1.0


class TestExecutionConfig:
    """Tests for ExecutionConfig model."""

    def test_execution_config_defaults(self) -> None:
        """Should use sensible defaults."""
        cfg = ExecutionConfig()
        assert cfg.mode == ExecutionMode.AFAP
        assert cfg.rate_hz == 100.0
        assert cfg.end_time is None
        assert cfg.schedule == []


class TestHermesConfig:
    """Tests for HermesConfig model."""

    def test_minimal_config(self) -> None:
        """Should accept minimal configuration."""
        cfg = HermesConfig(
            modules={"test": ModuleConfig(type=ModuleType.SCRIPT, script="./test.py")}
        )
        assert "test" in cfg.modules
        assert cfg.version == "0.2"

    def test_wire_validation_src_module(self) -> None:
        """Wire source must reference valid module."""
        with pytest.raises(ValueError, match="source module not found"):
            HermesConfig(
                modules={"test": ModuleConfig(type=ModuleType.SCRIPT, script="./test.py")},
                wiring=[WireConfig(src="nonexistent.signal", dst="test.signal")],
            )

    def test_wire_validation_dst_module(self) -> None:
        """Wire destination must reference valid module."""
        with pytest.raises(ValueError, match="destination module not found"):
            HermesConfig(
                modules={"test": ModuleConfig(type=ModuleType.SCRIPT, script="./test.py")},
                wiring=[WireConfig(src="test.signal", dst="nonexistent.signal")],
            )

    def test_schedule_validation(self) -> None:
        """Schedule must reference valid modules."""
        with pytest.raises(ValueError, match="unknown module"):
            HermesConfig(
                modules={"test": ModuleConfig(type=ModuleType.SCRIPT, script="./test.py")},
                execution=ExecutionConfig(schedule=["nonexistent"]),
            )

    def test_from_yaml(self) -> None:
        """Should load configuration from YAML file."""
        yaml_content = """
version: "0.2"
modules:
  vehicle:
    type: script
    script: ./vehicle.py
    signals:
      - name: position
        type: f64
        unit: m
execution:
  mode: afap
  rate_hz: 50.0
  end_time: 10.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            cfg = HermesConfig.from_yaml(Path(f.name))

            assert "vehicle" in cfg.modules
            assert cfg.modules["vehicle"].type == ModuleType.SCRIPT
            assert cfg.execution.mode == ExecutionMode.AFAP
            assert cfg.execution.rate_hz == 50.0
            assert cfg.execution.end_time == 10.0

    def test_get_dt(self) -> None:
        """Should calculate timestep correctly."""
        cfg = HermesConfig(
            modules={"t": ModuleConfig(type=ModuleType.SCRIPT, script="./t.py")},
            execution=ExecutionConfig(rate_hz=100.0),
        )
        assert cfg.get_dt() == 0.01

    def test_get_module_names_default_order(self) -> None:
        """Without schedule, returns modules in dict order."""
        cfg = HermesConfig(
            modules={
                "a": ModuleConfig(type=ModuleType.SCRIPT, script="./a.py"),
                "b": ModuleConfig(type=ModuleType.SCRIPT, script="./b.py"),
            }
        )
        names = cfg.get_module_names()
        assert names == ["a", "b"]

    def test_get_module_names_with_schedule(self) -> None:
        """With schedule, returns modules in schedule order."""
        cfg = HermesConfig(
            modules={
                "a": ModuleConfig(type=ModuleType.SCRIPT, script="./a.py"),
                "b": ModuleConfig(type=ModuleType.SCRIPT, script="./b.py"),
            },
            execution=ExecutionConfig(schedule=["b", "a"]),
        )
        names = cfg.get_module_names()
        assert names == ["b", "a"]
