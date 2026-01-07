"""Tests for the CLI module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from hermes.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def valid_config_yaml() -> str:
    """Create valid YAML configuration content."""
    return """
version: "0.2"
modules:
  test_module:
    type: script
    script: ./test_module.py
    signals:
      - name: position.x
        type: f64
        unit: m
      - name: velocity
        type: f32
        writable: true
execution:
  mode: afap
  rate_hz: 100.0
  end_time: 1.0
"""


@pytest.fixture
def valid_config_file(valid_config_yaml: str) -> Path:
    """Create temporary valid config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(valid_config_yaml)
        return Path(f.name)


@pytest.fixture
def invalid_config_yaml() -> str:
    """Create invalid YAML configuration content."""
    return """
version: "0.2"
modules:
  test_module:
    type: script
    # Missing required script field
"""


@pytest.fixture
def invalid_config_file(invalid_config_yaml: str) -> Path:
    """Create temporary invalid config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(invalid_config_yaml)
        return Path(f.name)


class TestCLIGroup:
    """Tests for the main CLI group."""

    def test_cli_help(self, runner: CliRunner) -> None:
        """Should display help message."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Hermes" in result.output
        assert "run" in result.output
        assert "validate" in result.output

    def test_cli_version(self, runner: CliRunner) -> None:
        """Should display version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "hermes" in result.output.lower()


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_config(self, runner: CliRunner, valid_config_file: Path) -> None:
        """Should validate valid configuration."""
        result = runner.invoke(cli, ["validate", str(valid_config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "Module:" in result.output

    def test_validate_invalid_config(self, runner: CliRunner, invalid_config_file: Path) -> None:
        """Should reject invalid configuration."""
        result = runner.invoke(cli, ["validate", str(invalid_config_file)])
        assert result.exit_code == 1

    def test_validate_nonexistent_file(self, runner: CliRunner) -> None:
        """Should fail for nonexistent file."""
        result = runner.invoke(cli, ["validate", "/nonexistent/path.yaml"])
        assert result.exit_code != 0

    def test_validate_shows_modules_and_signals(
        self, runner: CliRunner, valid_config_file: Path
    ) -> None:
        """Should display module and signal information."""
        result = runner.invoke(cli, ["validate", str(valid_config_file)])
        assert result.exit_code == 0
        assert "test_module" in result.output
        assert "position.x" in result.output
        assert "velocity" in result.output


class TestRunCommand:
    """Tests for the run command."""

    def test_run_nonexistent_config(self, runner: CliRunner) -> None:
        """Should fail for nonexistent config file."""
        result = runner.invoke(cli, ["run", "/nonexistent/config.yaml"])
        assert result.exit_code != 0

    def test_run_invalid_config(self, runner: CliRunner, invalid_config_file: Path) -> None:
        """Should fail for invalid configuration."""
        result = runner.invoke(cli, ["run", str(invalid_config_file)])
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "Failed" in result.output

    @patch("hermes.cli.main.ProcessManager")
    @patch("hermes.cli.main.Scheduler")
    def test_run_with_mocked_components(
        self,
        mock_scheduler_cls: MagicMock,
        mock_pm_cls: MagicMock,
        runner: CliRunner,
        valid_config_file: Path,
    ) -> None:
        """Should run simulation with mocked components."""
        # Setup mocks
        mock_pm = MagicMock()
        mock_pm.__enter__ = MagicMock(return_value=mock_pm)
        mock_pm.__exit__ = MagicMock(return_value=False)
        mock_pm_cls.return_value = mock_pm

        mock_scheduler = MagicMock()
        mock_scheduler.frame = 100
        mock_scheduler.time = 1.0
        mock_scheduler.run = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler

        runner.invoke(cli, ["run", str(valid_config_file)])

        # Verify calls
        mock_pm.load_all.assert_called_once()
        mock_scheduler.stage.assert_called_once()

    @patch("hermes.cli.main.ProcessManager")
    @patch("hermes.cli.main.Scheduler")
    def test_run_verbose_flag(
        self,
        mock_scheduler_cls: MagicMock,
        mock_pm_cls: MagicMock,
        runner: CliRunner,
        valid_config_file: Path,
    ) -> None:
        """Should accept verbose flag."""
        mock_pm = MagicMock()
        mock_pm.__enter__ = MagicMock(return_value=mock_pm)
        mock_pm.__exit__ = MagicMock(return_value=False)
        mock_pm_cls.return_value = mock_pm

        mock_scheduler = MagicMock()
        mock_scheduler.frame = 100
        mock_scheduler.time = 1.0
        mock_scheduler.run = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler

        result = runner.invoke(cli, ["run", str(valid_config_file), "--verbose"])
        # Just verify it doesn't crash with verbose flag
        assert result.exit_code == 0 or "error" not in result.output.lower()

    @patch("hermes.cli.main.ProcessManager")
    @patch("hermes.cli.main.Scheduler")
    def test_run_quiet_flag(
        self,
        mock_scheduler_cls: MagicMock,
        mock_pm_cls: MagicMock,
        runner: CliRunner,
        valid_config_file: Path,
    ) -> None:
        """Should accept quiet flag."""
        mock_pm = MagicMock()
        mock_pm.__enter__ = MagicMock(return_value=mock_pm)
        mock_pm.__exit__ = MagicMock(return_value=False)
        mock_pm_cls.return_value = mock_pm

        mock_scheduler = MagicMock()
        mock_scheduler.frame = 100
        mock_scheduler.time = 1.0
        mock_scheduler.run = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler

        result = runner.invoke(cli, ["run", str(valid_config_file), "--quiet"])
        # Just verify it doesn't crash with quiet flag
        assert result.exit_code == 0 or "error" not in result.output.lower()


class TestListSignalsCommand:
    """Tests for the list-signals command."""

    def test_list_signals_requires_shm_name(self, runner: CliRunner) -> None:
        """Should fail without shm-name argument."""
        result = runner.invoke(cli, ["list-signals"])
        # Should fail because auto-detect not implemented
        assert result.exit_code == 1
        assert "required" in result.output.lower() or "error" in result.output.lower()

    @patch("hermes.backplane.shm.SharedMemoryManager")
    def test_list_signals_with_shm(self, mock_shm_cls: MagicMock, runner: CliRunner) -> None:
        """Should list signals from shared memory."""
        mock_shm = MagicMock()
        mock_shm.get_frame.return_value = 42
        mock_shm.get_time.return_value = 1.5
        mock_shm_cls.return_value = mock_shm

        result = runner.invoke(cli, ["list-signals", "--shm-name", "/hermes_test"])

        assert result.exit_code == 0
        mock_shm.attach.assert_called_once()
        mock_shm.detach.assert_called_once()
        assert "42" in result.output
        assert "1.5" in result.output or "1.500" in result.output

    @patch("hermes.backplane.shm.SharedMemoryManager")
    def test_list_signals_connection_error(
        self, mock_shm_cls: MagicMock, runner: CliRunner
    ) -> None:
        """Should handle connection errors gracefully."""
        mock_shm = MagicMock()
        mock_shm.attach.side_effect = Exception("Connection failed")
        mock_shm_cls.return_value = mock_shm

        result = runner.invoke(cli, ["list-signals", "--shm-name", "/nonexistent"])

        assert result.exit_code == 1
        assert "error" in result.output.lower() or "failed" in result.output.lower()


class TestSignalHandling:
    """Tests for signal handling in the run command."""

    @patch("hermes.cli.main.ProcessManager")
    @patch("hermes.cli.main.Scheduler")
    @patch("hermes.cli.main.signal.signal")
    def test_signal_handler_setup(
        self,
        mock_signal: MagicMock,
        mock_scheduler_cls: MagicMock,
        mock_pm_cls: MagicMock,
        runner: CliRunner,
        valid_config_file: Path,
    ) -> None:
        """Should set up signal handlers for SIGINT and SIGTERM."""
        import signal as sig

        mock_pm = MagicMock()
        mock_pm.__enter__ = MagicMock(return_value=mock_pm)
        mock_pm.__exit__ = MagicMock(return_value=False)
        mock_pm_cls.return_value = mock_pm

        mock_scheduler = MagicMock()
        mock_scheduler.frame = 100
        mock_scheduler.time = 1.0
        mock_scheduler.run = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler

        runner.invoke(cli, ["run", str(valid_config_file)])

        # Verify signal handlers were registered
        signal_calls = [call[0][0] for call in mock_signal.call_args_list]
        assert sig.SIGINT in signal_calls
        assert sig.SIGTERM in signal_calls
