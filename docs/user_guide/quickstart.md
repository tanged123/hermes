# Quickstart Guide

Get up and running with Hermes in minutes.

## Prerequisites

Hermes uses Nix for reproducible builds. Install [Nix](https://nixos.org/download.html) first:

```bash
# Linux/macOS
sh <(curl -L https://nixos.org/nix/install) --daemon

# Enable flakes (add to ~/.config/nix/nix.conf)
experimental-features = nix-command flakes
```

## Installation

```bash
# Clone the repository
git clone https://github.com/tanged123/hermes.git
cd hermes

# Enter development environment
nix develop

# Verify installation
python -c "import hermes; print(hermes.__version__)"
```

## Your First Simulation

### 1. Create a Configuration File

Create `my_sim.yaml`:

```yaml
version: "0.2"

modules:
  vehicle:
    type: script
    script: ./vehicle.py
    signals:
      - name: position.x
        type: f64
        unit: m
      - name: position.y
        type: f64
        unit: m
      - name: velocity.x
        type: f64
        unit: m/s
      - name: velocity.y
        type: f64
        unit: m/s

execution:
  mode: afap
  rate_hz: 100.0
  end_time: 10.0

server:
  enabled: false
```

### 2. Create a Module Script

Create `vehicle.py`:

```python
#!/usr/bin/env python3
"""Simple vehicle module that integrates position."""

import os
import sys

# Import Hermes (adjust path as needed)
sys.path.insert(0, "src")

from hermes.backplane.shm import SharedMemoryManager
from hermes.backplane.sync import FrameBarrier


def main() -> int:
    # Get IPC names from environment
    module_name = os.environ.get("HERMES_MODULE_NAME", "vehicle")
    shm_name = os.environ["HERMES_SHM_NAME"]
    barrier_name = os.environ["HERMES_BARRIER_NAME"]

    # Attach to shared memory and barrier
    shm = SharedMemoryManager(shm_name)
    shm.attach()

    barrier = FrameBarrier(barrier_name, 1)
    barrier.attach()

    # Initial state
    x, y = 0.0, 0.0
    vx, vy = 1.0, 0.5
    dt = 0.01

    print(f"[{module_name}] Started")

    try:
        while True:
            # Wait for scheduler
            if not barrier.wait_step(timeout=5.0):
                break

            # Integrate position
            x += vx * dt
            y += vy * dt

            # Write to shared memory
            shm.set_signal(f"{module_name}.position.x", x)
            shm.set_signal(f"{module_name}.position.y", y)
            shm.set_signal(f"{module_name}.velocity.x", vx)
            shm.set_signal(f"{module_name}.velocity.y", vy)

            # Signal completion
            barrier.signal_done()

    finally:
        shm.detach()
        print(f"[{module_name}] Stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### 3. Validate Configuration

```bash
python -m hermes.cli.main validate my_sim.yaml
```

Expected output:
```
info     Configuration valid                modules=1 mode=afap wires=0
  Module: vehicle (script)
    Signal: position.x (f64)
    Signal: position.y (f64)
    Signal: velocity.x (f64)
    Signal: velocity.y (f64)
```

### 4. Run the Simulation

```bash
python -m hermes.cli.main run my_sim.yaml
```

Expected output:
```
info     Loading configuration             path=my_sim.yaml
info     Configuration loaded              modules=1 mode=afap
info     Staging simulation
info     Running simulation                mode=afap rate_hz=100.0 end_time=10.0
[vehicle] Started
info     Frame                             frame=100 time=1.000s
info     Frame                             frame=200 time=2.000s
...
info     Simulation complete               frames=1000 time=10.000s
[vehicle] Stopped
```

## Using the Scripting API

You can inspect and inject values into a running simulation:

```python
from hermes.scripting.api import SimulationAPI

# Connect to running simulation
with SimulationAPI("/hermes_12345") as sim:  # Use actual SHM name
    # Read current state
    x = sim.get("vehicle.position.x")
    print(f"Position X: {x}")

    # Wait for specific frame
    sim.wait_frame(500)

    # Sample multiple signals
    state = sim.sample([
        "vehicle.position.x",
        "vehicle.position.y",
    ])
    print(f"Position: ({state['vehicle.position.x']}, {state['vehicle.position.y']})")
```

## Execution Modes

### AFAP (As Fast As Possible)

Best for batch runs and Monte Carlo simulations:

```yaml
execution:
  mode: afap
  rate_hz: 100.0
  end_time: 60.0  # Run for 60 simulated seconds
```

### Realtime

Paced to wall-clock time for hardware-in-the-loop:

```yaml
execution:
  mode: realtime
  rate_hz: 100.0
  # No end_time - runs until stopped
```

### Single Frame

Manual stepping for debugging:

```yaml
execution:
  mode: single_frame
  rate_hz: 100.0
```

Then use the scripting API to step manually:

```python
scheduler.step(1)   # Advance one frame
scheduler.step(10)  # Advance ten frames
```

## WebSocket Server

Enable the WebSocket server for real-time telemetry streaming:

```yaml
server:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  telemetry_hz: 60.0
```

Connect with a WebSocket client to:
- Receive signal schema on connect
- Subscribe to signals (supports wildcards: `*`, `module.*`)
- Receive binary telemetry at the configured rate
- Send control commands (pause, resume, step, reset)
- Inject signal values

See the [WebSocket Guide](websocket.md) for full protocol details.

## Signal Wiring

Connect signals between modules:

```yaml
modules:
  sensor:
    type: script
    script: ./sensor.py
    signals:
      - name: measurement
        type: f64

  controller:
    type: script
    script: ./controller.py
    signals:
      - name: input
        type: f64
        writable: true

wiring:
  - src: sensor.measurement
    dst: controller.input
    gain: 1.0
    offset: 0.0
```

## Next Steps

- Read the [Architecture Guide](architecture.md) for detailed class documentation
- Read the [WebSocket Guide](websocket.md) for real-time telemetry streaming
- See `examples/` for more configuration examples
- Check `tests/` for usage patterns

## Troubleshooting

### "Shared memory not found"

The simulation must be running for the scripting API to connect. Start the simulation first.

### "Module timed out"

Check that your module script:
1. Attaches to the barrier correctly
2. Calls `barrier.wait_step()` in its main loop
3. Calls `barrier.signal_done()` after each step

### "Permission denied on semaphore"

POSIX IPC resources may be left over from a crashed run. Clean them up:

```bash
# List semaphores
ls /dev/shm/

# Remove orphaned resources
rm /dev/shm/hermes_*
```

Or use `ipcs` and `ipcrm` on systems without /dev/shm.
