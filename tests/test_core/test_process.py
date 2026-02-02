"""Tests for process lifecycle management."""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hermes.core.config import HermesConfig, ModuleConfig, ModuleType, SignalConfig
from hermes.core.process import ModuleInfo, ModuleProcess, ModuleState, ProcessManager


class TestModuleState:
    """Tests for ModuleState enum."""

    def test_all_states_exist(self) -> None:
        """All expected states should exist."""
        assert ModuleState.INIT.value == "init"
        assert ModuleState.STAGED.value == "staged"
        assert ModuleState.RUNNING.value == "running"
        assert ModuleState.PAUSED.value == "paused"
        assert ModuleState.DONE.value == "done"
        assert ModuleState.ERROR.value == "error"


class TestModuleInfo:
    """Tests for ModuleInfo dataclass."""

    def test_module_info_creation(self) -> None:
        """Should create ModuleInfo with all fields."""
        info = ModuleInfo(
            name="test_module",
            pid=12345,
            state=ModuleState.RUNNING,
            shm_name="/hermes_test",
            signals=["position.x", "velocity.y"],
        )
        assert info.name == "test_module"
        assert info.pid == 12345
        assert info.state == ModuleState.RUNNING
        assert info.shm_name == "/hermes_test"
        assert info.signals == ["position.x", "velocity.y"]

    def test_module_info_defaults(self) -> None:
        """Should use default empty list for signals."""
        info = ModuleInfo(
            name="test",
            pid=None,
            state=ModuleState.INIT,
            shm_name="/hermes",
        )
        assert info.signals == []


class TestModuleProcess:
    """Tests for ModuleProcess class."""

    @pytest.fixture
    def script_module_config(self) -> ModuleConfig:
        """Create a script module config."""
        return ModuleConfig(
            type=ModuleType.SCRIPT,
            script="./test_module.py",
            signals=[SignalConfig(name="output")],
        )

    @pytest.fixture
    def process_module_config(self) -> ModuleConfig:
        """Create a process module config."""
        return ModuleConfig(
            type=ModuleType.PROCESS,
            executable="./test_module",
            signals=[SignalConfig(name="output")],
        )

    def test_initial_state(self, script_module_config: ModuleConfig) -> None:
        """Should start in INIT state."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        assert module.name == "test"
        assert module.state == ModuleState.INIT
        assert module.pid is None
        assert module.is_alive is False

    def test_load_already_loaded_raises(self, script_module_config: ModuleConfig) -> None:
        """Should raise if trying to load twice."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        # Manually set process to simulate already loaded
        module._process = MagicMock()

        with pytest.raises(RuntimeError, match="already loaded"):
            module.load()

    def test_stage_from_init(self, script_module_config: ModuleConfig) -> None:
        """Should transition from INIT to STAGED."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        # Simulate process started
        module._process = MagicMock()

        module.stage()
        assert module.state == ModuleState.STAGED

    def test_stage_invalid_state_raises(self, script_module_config: ModuleConfig) -> None:
        """Should raise if staging from non-INIT state."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        module._state = ModuleState.STAGED

        with pytest.raises(RuntimeError, match="Cannot stage"):
            module.stage()

    def test_terminate_no_process(self, script_module_config: ModuleConfig) -> None:
        """Should do nothing if no process."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        # Should not raise
        module.terminate()
        assert module.state == ModuleState.INIT

    def test_terminate_graceful(self, script_module_config: ModuleConfig) -> None:
        """Should gracefully terminate process."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        mock_process = MagicMock()
        module._process = mock_process

        module.terminate(timeout=1.0)

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_with(timeout=1.0)
        assert module.state == ModuleState.DONE
        assert module._process is None

    def test_terminate_force_kill_on_timeout(self, script_module_config: ModuleConfig) -> None:
        """Should force kill if graceful terminate times out."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        mock_process = MagicMock()
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 1.0), None]
        module._process = mock_process

        module.terminate(timeout=1.0)

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert module.state == ModuleState.DONE

    def test_kill_no_process(self, script_module_config: ModuleConfig) -> None:
        """Should do nothing if no process."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        module.kill()
        assert module.state == ModuleState.INIT

    def test_kill_forceful(self, script_module_config: ModuleConfig) -> None:
        """Should forcefully kill process."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        mock_process = MagicMock()
        module._process = mock_process

        module.kill()

        mock_process.kill.assert_called_once()
        mock_process.wait.assert_called_once()
        assert module.state == ModuleState.DONE
        assert module._process is None

    def test_get_info(self, script_module_config: ModuleConfig) -> None:
        """Should return ModuleInfo with current state."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        module._process = mock_process

        info = module.get_info()

        assert info.name == "test"
        assert info.pid == 12345
        assert info.state == ModuleState.INIT
        assert info.shm_name == "/hermes_test"

    def test_is_alive_property(self, script_module_config: ModuleConfig) -> None:
        """Should return True if process is running."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        module._process = mock_process

        assert module.is_alive is True

        mock_process.poll.return_value = 0  # Exited
        assert module.is_alive is False

    def test_load_script_file_not_found(self, script_module_config: ModuleConfig) -> None:
        """Should raise FileNotFoundError for missing script."""
        module = ModuleProcess(
            name="test",
            config=script_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        with pytest.raises(FileNotFoundError, match="Script not found"):
            module.load()

    def test_load_executable_file_not_found(self, process_module_config: ModuleConfig) -> None:
        """Should raise FileNotFoundError for missing executable."""
        module = ModuleProcess(
            name="test",
            config=process_module_config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        with pytest.raises(FileNotFoundError, match="Executable not found"):
            module.load()

    def test_load_script_with_actual_file(self) -> None:
        """Should start script subprocess with actual file."""
        # Create a temporary script that exits immediately
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import sys; sys.exit(0)\n")
            script_path = f.name

        try:
            config = ModuleConfig(
                type=ModuleType.SCRIPT,
                script=script_path,
            )
            module = ModuleProcess(
                name="test",
                config=config,
                shm_name="/hermes_test",
                barrier_name="/hermes_barrier_test",
            )
            module.load()

            assert module.pid is not None
            assert module._process is not None

            # Wait for process to exit
            module._process.wait(timeout=5.0)
        finally:
            module.terminate()
            Path(script_path).unlink()

    def test_load_unsupported_module_type(self) -> None:
        """Should raise ValueError for unsupported module type as subprocess."""
        config = ModuleConfig(
            type=ModuleType.INPROC,
            inproc_module="hermes.modules.injection",
        )
        module = ModuleProcess(
            name="test",
            config=config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        with pytest.raises(ValueError, match="Unsupported module type"):
            module.load()

    def test_start_script_no_script_raises(self) -> None:
        """Should raise ValueError if script config has no script path."""
        # Use a mock to simulate missing script
        config = ModuleConfig(type=ModuleType.SCRIPT, script="./test.py")
        module = ModuleProcess(
            name="test",
            config=config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        # Use unittest.mock to patch the config attribute
        mock_config = MagicMock()
        mock_config.script = None
        mock_config.config = None
        module._config = mock_config

        with pytest.raises(ValueError, match="No script"):
            module._start_script()

    def test_start_executable_no_executable_raises(self) -> None:
        """Should raise ValueError if process config has no executable."""
        config = ModuleConfig(type=ModuleType.PROCESS, executable="./test")
        module = ModuleProcess(
            name="test",
            config=config,
            shm_name="/hermes_test",
            barrier_name="/hermes_barrier_test",
        )
        # Use unittest.mock to patch the config attribute
        mock_config = MagicMock()
        mock_config.executable = None
        mock_config.config = None
        module._config = mock_config

        with pytest.raises(ValueError, match="No executable"):
            module._start_executable()


class TestProcessManager:
    """Tests for ProcessManager class."""

    @pytest.fixture
    def minimal_config(self) -> HermesConfig:
        """Create minimal config for testing."""
        return HermesConfig(
            modules={
                "test_module": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script="./test_script.py",
                    signals=[
                        SignalConfig(name="position.x", type="f64"),
                        SignalConfig(name="velocity", type="f32", writable=True),
                    ],
                )
            }
        )

    @pytest.fixture
    def shm_name_prefix(self) -> str:
        """Generate unique prefix for IPC resources."""
        return f"hermes_test_{uuid.uuid4().hex[:8]}"

    def test_properties(self, minimal_config: HermesConfig) -> None:
        """Should expose shm and modules properties."""
        pm = ProcessManager(minimal_config)
        assert pm.shm is None
        assert pm.modules == {}

    def test_initialize_creates_resources(self, minimal_config: HermesConfig) -> None:
        """Should create shared memory and barrier on initialize."""
        pm = ProcessManager(minimal_config)
        try:
            pm.initialize()

            assert pm.shm is not None
            assert pm._barrier is not None
            assert "test_module" in pm.modules
        finally:
            pm.terminate_all()

    def test_get_module(self, minimal_config: HermesConfig) -> None:
        """Should return module by name."""
        pm = ProcessManager(minimal_config)
        try:
            pm.initialize()

            module = pm.get_module("test_module")
            assert module is not None
            assert module.name == "test_module"

            assert pm.get_module("nonexistent") is None
        finally:
            pm.terminate_all()

    def test_step_all_without_init_raises(self, minimal_config: HermesConfig) -> None:
        """Should raise if stepping before initialization."""
        pm = ProcessManager(minimal_config)
        with pytest.raises(RuntimeError, match="not initialized"):
            pm.step_all()

    def test_update_time_without_init_raises(self, minimal_config: HermesConfig) -> None:
        """Should raise if updating time before initialization."""
        pm = ProcessManager(minimal_config)
        with pytest.raises(RuntimeError, match="not initialized"):
            pm.update_time(0, 0)

    def test_context_manager(self, minimal_config: HermesConfig) -> None:
        """Should work as context manager."""
        with ProcessManager(minimal_config) as pm:
            assert pm.shm is not None
            assert pm._barrier is not None

        # After exit, resources should be cleaned up
        assert pm._shm is None
        assert pm._barrier is None

    def test_initialize_signal_types(self) -> None:
        """Should handle all signal types during initialization."""
        config = HermesConfig(
            modules={
                "test": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script="./test.py",
                    signals=[
                        SignalConfig(name="f64_sig", type="f64"),
                        SignalConfig(name="f32_sig", type="f32"),
                        SignalConfig(name="i64_sig", type="i64"),
                        SignalConfig(name="i32_sig", type="i32"),
                        SignalConfig(name="bool_sig", type="bool"),
                        SignalConfig(name="default_sig"),  # Should be f64
                    ],
                )
            }
        )
        pm = ProcessManager(config)
        try:
            pm.initialize()
            assert pm.shm is not None
            # All signals should be registered
            signal_names = pm.shm.signal_names()
            assert "test.f64_sig" in signal_names
            assert "test.f32_sig" in signal_names
            assert "test.i64_sig" in signal_names
            assert "test.i32_sig" in signal_names
            assert "test.bool_sig" in signal_names
            assert "test.default_sig" in signal_names
        finally:
            pm.terminate_all()

    def test_update_time_writes_to_shm(self, minimal_config: HermesConfig) -> None:
        """Should update frame and time in shared memory."""
        pm = ProcessManager(minimal_config)
        try:
            pm.initialize()
            pm.update_time(frame=42, time_ns=1_500_000_000)

            assert pm.shm is not None
            assert pm.shm.get_frame() == 42
            assert pm.shm.get_time_ns() == 1_500_000_000
        finally:
            pm.terminate_all()

    def test_terminate_all_cleans_up(self, minimal_config: HermesConfig) -> None:
        """Should clean up all resources."""
        pm = ProcessManager(minimal_config)
        pm.initialize()

        pm.terminate_all()

        assert pm._shm is None
        assert pm._barrier is None

    def test_terminate_all_idempotent(self, minimal_config: HermesConfig) -> None:
        """Should be safe to call terminate_all multiple times."""
        pm = ProcessManager(minimal_config)
        pm.initialize()

        pm.terminate_all()
        pm.terminate_all()  # Should not raise

        assert pm._shm is None
        assert pm._barrier is None


class TestProcessManagerWithRealModule:
    """Integration tests for ProcessManager with actual module scripts."""

    @pytest.fixture
    def test_script(self) -> Path:
        """Create a test script that communicates via IPC."""
        script_content = '''#!/usr/bin/env python3
"""Test module that immediately exits."""
import sys
sys.exit(0)
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script_content)
            path = Path(f.name)

        yield path
        path.unlink()

    def test_load_all_starts_processes(self, test_script: Path) -> None:
        """Should start all module processes."""
        config = HermesConfig(
            modules={
                "test_module": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script=str(test_script),
                )
            }
        )
        pm = ProcessManager(config)
        try:
            pm.initialize()
            pm.load_all()

            module = pm.get_module("test_module")
            assert module is not None
            assert module.pid is not None
        finally:
            pm.terminate_all()

    def test_stage_all_stages_modules(self, test_script: Path) -> None:
        """Should stage all modules."""
        config = HermesConfig(
            modules={
                "test_module": ModuleConfig(
                    type=ModuleType.SCRIPT,
                    script=str(test_script),
                )
            }
        )
        pm = ProcessManager(config)
        try:
            pm.initialize()
            pm.load_all()
            pm.stage_all()

            module = pm.get_module("test_module")
            assert module is not None
            assert module.state == ModuleState.STAGED
        finally:
            pm.terminate_all()
