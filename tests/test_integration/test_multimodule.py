"""Integration tests for multi-module wire routing (Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes.core.config import HermesConfig
from hermes.core.process import ProcessManager
from hermes.core.scheduler import Scheduler


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    """Write YAML config to a temp file and return its path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_text)
    return config_file


class TestInjectionModule:
    """Tests for the injection module."""

    def test_injection_stage_zeros_signals(self, tmp_path: Path) -> None:
        """Staging should initialize all signals to zero."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd_a
        type: f64
        writable: true
      - name: cmd_b
        type: f64
        writable: true
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            assert pm.shm.get_signal("inputs.cmd_a") == 0.0
            assert pm.shm.get_signal("inputs.cmd_b") == 0.0

    def test_injection_values_persist(self, tmp_path: Path) -> None:
        """Written values should persist across steps."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("inputs.cmd", 42.0)
            sched.step()
            assert pm.shm.get_signal("inputs.cmd") == 42.0
            sched.step()
            assert pm.shm.get_signal("inputs.cmd") == 42.0

    def test_injection_reset_zeros(self, tmp_path: Path) -> None:
        """Reset should zero all signals."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("inputs.cmd", 99.0)

            # Reset via inproc module directly
            inproc = pm.get_inproc_module("inputs")
            assert inproc is not None
            inproc.reset()
            assert pm.shm.get_signal("inputs.cmd") == 0.0


class TestMockPhysicsModule:
    """Tests for the mock physics module."""

    def test_physics_computes_output(self, tmp_path: Path) -> None:
        """Output should follow: output = input * 2 + state."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("physics.input", 5.0)
            sched.step()  # dt=0.01

            # state = 0 + 5.0 * 0.01 = 0.05
            # output = 5.0 * 2.0 + 0.05 = 10.05
            assert pm.shm.get_signal("physics.state") == pytest.approx(0.05)
            assert pm.shm.get_signal("physics.output") == pytest.approx(10.05)

    def test_physics_state_accumulates(self, tmp_path: Path) -> None:
        """State should accumulate across steps."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("physics.input", 10.0)
            sched.step()  # state = 10 * 0.01 = 0.1
            sched.step()  # state = 0.1 + 10 * 0.01 = 0.2

            assert pm.shm.get_signal("physics.state") == pytest.approx(0.2)


class TestWireRouting:
    """Tests for wire routing between modules."""

    def test_basic_wire_routing(self, tmp_path: Path) -> None:
        """Wire should transfer value with gain/offset."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: inputs.cmd
    dst: physics.input
    gain: 2.0
    offset: 10.0
execution:
  mode: single_frame
  rate_hz: 100.0
  schedule:
    - inputs
    - physics
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("inputs.cmd", 5.0)
            sched.step()

            # Wire: 5.0 * 2.0 + 10.0 = 20.0
            assert pm.shm.get_signal("physics.input") == pytest.approx(20.0)

    def test_wire_default_gain_offset(self, tmp_path: Path) -> None:
        """Wire with default gain=1, offset=0 should pass through."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: inputs.cmd
    dst: physics.input
execution:
  mode: single_frame
  rate_hz: 100.0
  schedule:
    - inputs
    - physics
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("inputs.cmd", 7.5)
            sched.step()

            assert pm.shm.get_signal("physics.input") == pytest.approx(7.5)

    def test_multiple_wires(self, tmp_path: Path) -> None:
        """Multiple wires should all transfer correctly."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd_a
        type: f64
        writable: true
      - name: cmd_b
        type: f64
        writable: true
  phys_a:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
  phys_b:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: inputs.cmd_a
    dst: phys_a.input
    gain: 3.0
  - src: inputs.cmd_b
    dst: phys_b.input
    offset: 1.0
execution:
  mode: single_frame
  rate_hz: 100.0
  schedule:
    - inputs
    - phys_a
    - phys_b
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("inputs.cmd_a", 4.0)
            pm.shm.set_signal("inputs.cmd_b", 2.0)
            sched.step()

            # Wire A: 4.0 * 3.0 + 0.0 = 12.0
            assert pm.shm.get_signal("phys_a.input") == pytest.approx(12.0)
            # Wire B: 2.0 * 1.0 + 1.0 = 3.0
            assert pm.shm.get_signal("phys_b.input") == pytest.approx(3.0)

    def test_invalid_wire_source_raises(self, tmp_path: Path) -> None:
        """Invalid wire source should raise during stage."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: nonexistent.signal
    dst: physics.input
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        with pytest.raises(ValueError, match="Wire source module not found"):
            HermesConfig.from_yaml(config_path)

    def test_invalid_wire_signal_raises(self, tmp_path: Path) -> None:
        """Wire referencing nonexistent signal should raise during stage."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: inputs.nonexistent
    dst: physics.input
execution:
  mode: single_frame
  rate_hz: 100.0
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            with pytest.raises(ValueError, match="source signal not found"):
                sched.stage()

    def test_end_to_end_injection_to_physics(self, tmp_path: Path) -> None:
        """Full pipeline: inject value, wire to physics, compute output."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: thrust_cmd
        type: f64
        writable: true
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: inputs.thrust_cmd
    dst: physics.input
    gain: 0.5
execution:
  mode: single_frame
  rate_hz: 100.0
  schedule:
    - inputs
    - physics
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            # Inject thrust command
            pm.shm.set_signal("inputs.thrust_cmd", 100.0)

            # Step 1: wire routes first (physics.input = 100 * 0.5 = 50),
            # then physics steps with input=50
            # state = 0 + 50 * 0.01 = 0.5, output = 50 * 2 + 0.5 = 100.5
            sched.step()
            assert pm.shm.get_signal("physics.input") == pytest.approx(50.0)
            assert pm.shm.get_signal("physics.output") == pytest.approx(100.5)

            # Step 2: wire routes again, state accumulates
            # state = 0.5 + 50 * 0.01 = 1.0, output = 50 * 2 + 1.0 = 101.0
            sched.step()
            assert pm.shm.get_signal("physics.output") == pytest.approx(101.0)

    def test_reset_preserves_wire_config(self, tmp_path: Path) -> None:
        """Reset should re-initialize modules but wires stay configured."""
        config_path = _write_config(
            tmp_path,
            """
version: "0.2"
modules:
  inputs:
    type: inproc
    inproc_module: hermes.modules.injection
    signals:
      - name: cmd
        type: f64
        writable: true
  physics:
    type: inproc
    inproc_module: hermes.modules.mock_physics
    signals:
      - name: input
        type: f64
        writable: true
      - name: output
        type: f64
      - name: state
        type: f64
wiring:
  - src: inputs.cmd
    dst: physics.input
execution:
  mode: single_frame
  rate_hz: 100.0
  schedule:
    - inputs
    - physics
""",
        )
        config = HermesConfig.from_yaml(config_path)
        with ProcessManager(config) as pm:
            sched = Scheduler(pm, config.execution)
            sched.stage()

            assert pm.shm is not None
            pm.shm.set_signal("inputs.cmd", 10.0)
            sched.step()
            assert pm.shm.get_signal("physics.input") == pytest.approx(10.0)

            # Reset scheduler - wires should still work
            sched.reset()
            pm.shm.set_signal("inputs.cmd", 20.0)
            sched.step()
            assert pm.shm.get_signal("physics.input") == pytest.approx(20.0)
