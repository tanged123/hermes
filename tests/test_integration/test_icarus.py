"""Integration tests for Icarus 6DOF module."""

from __future__ import annotations

from pathlib import Path

import pytest

icarus = pytest.importorskip("icarus")

from hermes.backplane.shm import SharedMemoryManager  # noqa: E402
from hermes.backplane.signals import SignalFlags  # noqa: E402
from hermes.modules.icarus_module import IcarusModule  # noqa: E402

# Path to the rocket_ascent config bundled with the Icarus reference
ROCKET_ASCENT_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "references"
    / "icarus"
    / "config"
    / "examples"
    / "rocket_ascent.yaml"
)


@pytest.fixture()
def icarus_module() -> IcarusModule:
    """Create an IcarusModule pointed at rocket_ascent.yaml."""
    return IcarusModule(
        module_name="rocket",
        config_path=ROCKET_ASCENT_CONFIG,
    )


@pytest.fixture()
def shm_with_icarus(icarus_module: IcarusModule) -> SharedMemoryManager:
    """Create shm populated with icarus signal descriptors."""
    import os

    shm_name = f"/hermes_test_icarus_{os.getpid()}"
    shm = SharedMemoryManager(shm_name)
    descriptors = icarus_module.get_signal_descriptors()
    shm.create(descriptors)
    icarus_module.bind_shm(shm)
    yield shm  # type: ignore[misc]
    shm.destroy()


class TestIcarusSignalDiscovery:
    """Test that Icarus signals are correctly discovered."""

    def test_creates_simulator(self, icarus_module: IcarusModule) -> None:
        assert icarus_module._sim is not None

    def test_discovers_output_signals(self, icarus_module: IcarusModule) -> None:
        outputs = icarus_module.output_signals
        assert len(outputs) == 90
        assert "Rocket.Vehicle.position.x" in outputs

    def test_discovers_unwired_inputs(self, icarus_module: IcarusModule) -> None:
        inputs = icarus_module.input_signals
        assert len(inputs) >= 1
        assert "Rocket.Engine.throttle_cmd" in inputs

    def test_signal_descriptors_prefixed(self, icarus_module: IcarusModule) -> None:
        descriptors = icarus_module.get_signal_descriptors()
        names = [d.name for d in descriptors]
        # All should be prefixed with module name
        assert all(n.startswith("rocket.") for n in names)
        assert "rocket.Rocket.Engine.throttle_cmd" in names
        assert "rocket.Rocket.Vehicle.position.x" in names

    def test_input_descriptors_writable(self, icarus_module: IcarusModule) -> None:
        descriptors = icarus_module.get_signal_descriptors()
        input_descs = [d for d in descriptors if "throttle_cmd" in d.name]
        assert len(input_descs) == 1
        assert input_descs[0].flags & SignalFlags.WRITABLE


class TestIcarusLifecycle:
    """Test stage/step/reset lifecycle."""

    def test_stage_syncs_outputs(
        self,
        icarus_module: IcarusModule,
        shm_with_icarus: SharedMemoryManager,
    ) -> None:
        icarus_module.stage()
        # After staging, position should be non-zero (on Earth's surface)
        alt_sig = "rocket.Rocket.Vehicle.position.x"
        val = shm_with_icarus.get_signal(alt_sig)
        # ECEF x position on equator should be ~6.37e6 m
        assert abs(val) > 1e6

    def test_step_advances_state(
        self,
        icarus_module: IcarusModule,
        shm_with_icarus: SharedMemoryManager,
    ) -> None:
        icarus_module.stage()

        # Set throttle to full
        shm_with_icarus.set_signal("rocket.Rocket.Engine.throttle_cmd", 1.0)

        alt_before = shm_with_icarus.get_signal("rocket.Rocket.Vehicle.position_lla.alt")

        # Step several times
        for _ in range(100):
            icarus_module.step(0.01)

        alt_after = shm_with_icarus.get_signal("rocket.Rocket.Vehicle.position_lla.alt")
        # Rocket should have gained altitude
        assert alt_after > alt_before

    def test_reset_restores_state(
        self,
        icarus_module: IcarusModule,
        shm_with_icarus: SharedMemoryManager,
    ) -> None:
        icarus_module.stage()

        shm_with_icarus.set_signal("rocket.Rocket.Engine.throttle_cmd", 1.0)
        for _ in range(100):
            icarus_module.step(0.01)

        alt_after_step = shm_with_icarus.get_signal("rocket.Rocket.Vehicle.position_lla.alt")

        icarus_module.reset()

        alt_after_reset = shm_with_icarus.get_signal("rocket.Rocket.Vehicle.position_lla.alt")
        # Should be back near initial altitude (0 m)
        assert abs(alt_after_reset) < abs(alt_after_step)
