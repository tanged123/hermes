#!/usr/bin/env python3
"""Mock module for testing Hermes simulation.

This script demonstrates how to write a Python script module that
participates in the Hermes simulation loop via shared memory and
barrier synchronization.

Usage:
    python mock_module.py <shm_name> [config_path]

Environment variables:
    HERMES_MODULE_NAME: Module name
    HERMES_SHM_NAME: Shared memory segment name
    HERMES_BARRIER_NAME: Barrier semaphore name
"""

from __future__ import annotations

import os
import sys

# Add parent src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.sync import FrameBarrier


def main() -> int:
    """Run the mock module."""
    # Get configuration from environment/args
    module_name = os.environ.get("HERMES_MODULE_NAME", "mock_module")
    shm_name = os.environ.get("HERMES_SHM_NAME")
    barrier_name = os.environ.get("HERMES_BARRIER_NAME")

    if not shm_name and len(sys.argv) > 1:
        shm_name = sys.argv[1]

    if not shm_name or not barrier_name:
        print(f"Usage: {sys.argv[0]} <shm_name>", file=sys.stderr)
        print("Or set HERMES_SHM_NAME and HERMES_BARRIER_NAME environment variables")
        return 1

    print(f"[{module_name}] Starting...")
    print(f"[{module_name}] SHM: {shm_name}")
    print(f"[{module_name}] Barrier: {barrier_name}")

    # Attach to shared memory
    shm = SharedMemoryManager(shm_name)
    shm.attach()

    # Attach to barrier
    barrier = FrameBarrier(barrier_name, 1)  # Count doesn't matter for attach
    barrier.attach()

    # Simulation state
    x = 0.0
    y = 0.0
    vx = 1.0  # 1 m/s in x direction
    vy = 0.5  # 0.5 m/s in y direction

    print(f"[{module_name}] Ready, entering simulation loop")

    try:
        while True:
            # Wait for step signal from scheduler
            if not barrier.wait_step(timeout=5.0):
                print(f"[{module_name}] Timeout waiting for step")
                break

            # Get timestep from shared memory
            frame = shm.get_frame()
            _ = shm.get_time()  # Available for future use
            dt = 0.01  # 100 Hz default

            # Simple integration
            x += vx * dt
            y += vy * dt

            # Write signals to shared memory
            shm.set_signal(f"{module_name}.position.x", x)
            shm.set_signal(f"{module_name}.position.y", y)
            shm.set_signal(f"{module_name}.velocity.x", vx)
            shm.set_signal(f"{module_name}.velocity.y", vy)

            # Signal completion
            barrier.signal_done()

            # Log every 100 frames
            if frame % 100 == 0:
                print(f"[{module_name}] Frame {frame}: pos=({x:.2f}, {y:.2f})")

    except KeyboardInterrupt:
        print(f"[{module_name}] Interrupted")
    finally:
        shm.detach()
        print(f"[{module_name}] Shutdown complete")

    return 0


if __name__ == "__main__":
    sys.exit(main())
