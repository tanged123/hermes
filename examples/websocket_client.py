#!/usr/bin/env python3
"""WebSocket client example for Hermes telemetry.

This script demonstrates how to connect to a running Hermes simulation
via WebSocket and receive real-time telemetry data.

Usage:
    1. Start the simulation: python -m hermes.cli.main run examples/websocket_telemetry.yaml
    2. Run this client: python examples/websocket_client.py

The client will:
    1. Connect and receive the signal schema
    2. Subscribe to all signals
    3. Resume the simulation
    4. Print telemetry frames as they arrive
"""

from __future__ import annotations

import asyncio
import json
import struct
import sys


async def main(host: str = "127.0.0.1", port: int = 8765) -> int:
    """Connect to Hermes WebSocket server and receive telemetry."""
    # Import websockets here to give helpful error if missing
    try:
        import websockets
    except ImportError:
        print("Error: websockets package required. Install with: pip install websockets")
        return 1

    uri = f"ws://{host}:{port}"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            # 1. Receive schema on connect
            schema_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            schema = json.loads(schema_msg)

            print("\n=== Signal Schema ===")
            print(f"Type: {schema['type']}")
            for module_name, module_info in schema.get("modules", {}).items():
                print(f"\nModule: {module_name}")
                for signal in module_info.get("signals", []):
                    print(f"  - {signal['name']} ({signal['type']})")

            # 2. Subscribe to signals (specific patterns or all)
            # Build smart subscription: prefer interesting signals if available
            all_signals = [
                f"{mod}.{sig['name']}"
                for mod, info in schema.get("modules", {}).items()
                for sig in info.get("signals", [])
            ]

            # Default: subscribe to everything
            subscribe_patterns: list[str] = ["*"]

            # If icarus-style signals exist, pick the interesting ones
            interesting_suffixes = [
                "position_lla.alt",
                "velocity_body.x",
                "total_mass",
                "Engine.thrust",
                "Engine.throttle_cmd",
                "FuelTank.fuel_mass",
                "euler_zyx.pitch",
            ]
            interesting = [
                s for s in all_signals if any(s.endswith(sfx) for sfx in interesting_suffixes)
            ]
            if interesting:
                subscribe_patterns = interesting

            print("\n=== Subscribing to signals ===")
            await ws.send(
                json.dumps(
                    {
                        "action": "subscribe",
                        "params": {"signals": subscribe_patterns},
                    }
                )
            )
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            subscribed_signals: list[str] = ack.get("signals", [])
            print(f"Subscribed to {ack.get('count', 0)} signals:")
            for s in subscribed_signals:
                print(f"  - {s}")

            # 3. Resume simulation
            print("\n=== Resuming simulation ===")
            await ws.send(json.dumps({"action": "resume"}))

            # Receive ack and event (order may vary, telemetry may arrive too)
            json_messages_received = 0
            while json_messages_received < 2:
                data = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if isinstance(data, bytes):
                    # Skip binary telemetry for now
                    continue
                msg = json.loads(data)
                json_messages_received += 1
                if msg["type"] == "ack":
                    print(f"Acknowledged: {msg['action']}")
                elif msg["type"] == "event":
                    print(f"Event: {msg['event']}")

            # 4. Inject a signal if the multi-module config is loaded
            # Try icarus throttle first, then multi_module thrust_cmd
            inject_signal = (
                "inputs.throttle" if "inputs.throttle" in all_signals else "inputs.thrust_cmd"
            )
            if inject_signal in all_signals:
                inject_value = 1.0 if "throttle" in inject_signal else 100.0
                print(f"\n=== Injecting {inject_signal} = {inject_value} ===")
                await ws.send(
                    json.dumps(
                        {
                            "action": "set",
                            "params": {"signal": inject_signal, "value": inject_value},
                        }
                    )
                )
                # Drain the ack/error (may be interleaved with telemetry)
                while True:
                    data = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    if isinstance(data, str):
                        msg = json.loads(data)
                        if msg.get("type") == "ack" and msg.get("action") == "set":
                            print(f"Acknowledged: set {msg.get('signal')} = {msg.get('value')}")
                            break
                        if msg.get("type") == "error":
                            print(f"Error: {msg.get('message')}")
                            break

            # 5. Receive telemetry frames
            # Build short display names from subscribed signals
            short_names = [s.rsplit(".", 1)[-1] if "." in s else s for s in subscribed_signals]

            print("\n=== Receiving telemetry (Ctrl+C to stop) ===")
            # Print header row
            header_vals = "  ".join(f"{n:>12s}" for n in short_names[:8])
            print(f"{'Frame':>6s} | {'Time':>8s} | {header_vals}")
            print("-" * (20 + 14 * min(len(short_names), 8)))

            frame_count = 0
            while True:
                try:
                    data = await asyncio.wait_for(ws.recv(), timeout=1.0)

                    if isinstance(data, bytes):
                        # Decode binary telemetry frame
                        # Header: magic (u32) + frame (u64) + time (f64) + count (u32) = 24 bytes
                        if len(data) >= 24:
                            magic, frame, time_s, count = struct.unpack("<IQdI", data[:24])

                            if magic == 0x48455254:  # "HERT"
                                # Decode values
                                values = list(struct.unpack(f"<{count}d", data[24:]))

                                # Print every 10th frame to avoid flooding
                                if frame_count % 10 == 0:
                                    vals_str = "  ".join(f"{v:>12.3f}" for v in values[:8])
                                    print(f"{frame:6d} | {time_s:8.3f} | {vals_str}")

                                frame_count += 1
                            else:
                                print(f"Invalid magic: 0x{magic:08X}")
                    else:
                        # JSON message
                        msg = json.loads(data)
                        print(f"[{msg['type']}] {msg}")

                except TimeoutError:
                    print("(waiting for telemetry...)")

    except ConnectionRefusedError:
        print(f"Error: Could not connect to {uri}")
        print(
            "Make sure the simulation is running with: python -m hermes.cli.main run examples/websocket_telemetry.yaml"
        )
        return 1
    except KeyboardInterrupt:
        print("\n\nClient stopped.")
        return 0
    except Exception as e:
        # Check for clean WebSocket close
        error_str = str(e)
        if "1001" in error_str or "going away" in error_str:
            print("\n\nServer disconnected (simulation stopped).")
            return 0
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
