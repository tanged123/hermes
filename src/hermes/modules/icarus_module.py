"""Icarus 6DOF physics module integration.

Wraps an icarus.Simulator instance as a Hermes in-process module.
Signal discovery happens at construction time (before shm creation)
so that all ~90 Icarus signals can be included in the shared memory layout.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog

from hermes.backplane.signals import SignalDescriptor, SignalFlags, SignalType

if TYPE_CHECKING:
    from hermes.backplane.shm import SharedMemoryManager

log = structlog.get_logger()


class IcarusModule:
    """Hermes module wrapping an Icarus 6DOF simulator.

    Construction creates and stages the Icarus simulator so that
    signal names can be discovered before Hermes shm is allocated.
    """

    def __init__(
        self,
        module_name: str,
        config_path: Path,
        prefix: str | None = None,
    ) -> None:
        """Create and stage the Icarus simulator for signal discovery.

        Args:
            module_name: Hermes module name (used as signal prefix)
            config_path: Path to Icarus YAML config (e.g. rocket_ascent.yaml)
            prefix: Signal prefix override; defaults to module_name
        """
        try:
            import icarus as _icarus
        except ImportError as exc:
            raise ImportError(
                "icarus package not installed. Install it or use a Nix shell with icarus available."
            ) from exc

        self._name = module_name
        self._prefix = prefix or module_name
        self._config_path = Path(config_path)
        self._shm: SharedMemoryManager | None = None

        # Create and stage simulator for signal discovery
        self._sim = _icarus.Simulator(str(self._config_path))
        self._sim.stage()

        # Parse schema to classify signals
        schema: dict[str, object] = self._sim.schema_json
        self._input_signals: list[str] = []
        self._output_signals: list[str] = []
        self._parse_schema(schema)

        log.info(
            "Icarus module created",
            module=self._name,
            inputs=len(self._input_signals),
            outputs=len(self._output_signals),
            total_signals=self._sim.signal_count,
        )

    def _parse_schema(self, schema: dict[str, object]) -> None:
        """Classify signals from Icarus schema as inputs or outputs.

        Inputs: component inputs without ``wired_to`` (externally controllable).
        Outputs: all component outputs.
        """
        components = cast(list[dict[str, object]], schema.get("components", []))
        for comp in components:
            # Unwired inputs are controllable from Hermes
            inputs = cast(list[dict[str, str]], comp.get("inputs", []))
            for inp in inputs:
                if not inp.get("wired_to"):
                    self._input_signals.append(inp["name"])

            # All outputs are published to Hermes shm
            outputs = cast(list[dict[str, str]], comp.get("outputs", []))
            for out in outputs:
                self._output_signals.append(out["name"])

    def bind_shm(self, shm: SharedMemoryManager) -> None:
        """Bind shared memory after it has been created.

        Args:
            shm: The shared memory manager with signals already allocated.
        """
        self._shm = shm

    def get_signal_descriptors(self) -> list[SignalDescriptor]:
        """Return signal descriptors for shm allocation.

        All Icarus signals are f64.  Inputs are writable; outputs are
        published (read-only from Hermes' perspective).
        """
        descriptors: list[SignalDescriptor] = []

        schema: dict[str, object] = self._sim.schema_json
        components = cast(list[dict[str, object]], schema.get("components", []))

        # Build a unit lookup from schema
        unit_map: dict[str, str] = {}
        for comp in components:
            for sig_list_key in ("inputs", "outputs"):
                sig_list = cast(list[dict[str, str]], comp.get(sig_list_key, []))
                for sig in sig_list:
                    unit_map[sig["name"]] = sig.get("unit", "")

        for sig_name in self._input_signals:
            descriptors.append(
                SignalDescriptor(
                    name=f"{self._prefix}.{sig_name}",
                    type=SignalType.F64,
                    flags=SignalFlags.WRITABLE | SignalFlags.PUBLISHED,
                    unit=unit_map.get(sig_name, ""),
                )
            )

        for sig_name in self._output_signals:
            descriptors.append(
                SignalDescriptor(
                    name=f"{self._prefix}.{sig_name}",
                    type=SignalType.F64,
                    flags=SignalFlags.PUBLISHED,
                    unit=unit_map.get(sig_name, ""),
                )
            )

        return descriptors

    @property
    def input_signals(self) -> list[str]:
        """Unwired input signal names (Icarus-local names)."""
        return list(self._input_signals)

    @property
    def output_signals(self) -> list[str]:
        """Output signal names (Icarus-local names)."""
        return list(self._output_signals)

    def stage(self) -> None:
        """Sync initial Icarus values to Hermes shm.

        The Icarus simulator is already staged (done in __init__).
        This just copies initial output values into shared memory.
        """
        if self._shm is None:
            raise RuntimeError("shm not bound; call bind_shm() first")

        # Sync outputs: icarus → shm
        for sig_name in self._output_signals:
            val = cast(float, self._sim.get(sig_name))
            self._shm.set_signal(f"{self._prefix}.{sig_name}", val)

        # Sync inputs: shm → icarus (in case wires set initial values)
        for sig_name in self._input_signals:
            val = self._shm.get_signal(f"{self._prefix}.{sig_name}")
            self._sim.set(sig_name, val)

        log.debug("Icarus module staged", module=self._name)

    def step(self, dt: float) -> None:
        """Advance Icarus physics by dt seconds.

        1. Read input signals from shm → Icarus
        2. Step Icarus
        3. Write output signals from Icarus → shm
        """
        if self._shm is None:
            raise RuntimeError("shm not bound; call bind_shm() first")

        # Inputs: shm → icarus
        for sig_name in self._input_signals:
            val = self._shm.get_signal(f"{self._prefix}.{sig_name}")
            self._sim.set(sig_name, val)

        # Step physics
        self._sim.step(dt)

        # Outputs: icarus → shm
        for sig_name in self._output_signals:
            val = cast(float, self._sim.get(sig_name))
            self._shm.set_signal(f"{self._prefix}.{sig_name}", val)

    def reset(self) -> None:
        """Reset Icarus to initial conditions and re-sync outputs."""
        self._sim.reset()

        if self._shm is not None:
            for sig_name in self._output_signals:
                val = cast(float, self._sim.get(sig_name))
                self._shm.set_signal(f"{self._prefix}.{sig_name}", val)

        log.debug("Icarus module reset", module=self._name)
