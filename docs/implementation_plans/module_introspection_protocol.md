# Module Introspection Protocol

> **Created**: 2026-02-16
> **Status**: Proposal
> **Affects**: Hermes WebSocket Protocol, IcarusModule, Daedalus Topology View

---

## 1. Problem

Daedalus's topology view shows Hermes modules as opaque boxes. When a module wraps a complex physics engine like Icarus (~90 signals, ~12 internal components, internal signal routing), all that structure is invisible. The user sees a single "rocket" box with `... 90 more` signals.

Icarus **already exposes** rich internal structure via `Simulator.schema_json` → `DataDictionary`:
- Components with names and types (`Rocket.Engine: JetEngine`, `Rocket.Body: Vehicle6DOF`)
- Per-component inputs, outputs, parameters, config
- Internal wiring (`wired_to` on each input)
- Signal metadata (units, descriptions, state/derivative relationships)

But Hermes **discards all of it**. When building the WebSocket schema for Icarus modules, it flattens everything to a bare signal list:

```python
# websocket.py lines 267-273 — ALL component structure lost here
if mod_config.type == ModuleType.ICARUS:
    prefix = f"{mod_name}."
    for sig_name in shm_signal_names:
        if sig_name.startswith(prefix):
            local_name = sig_name[len(prefix):]
            sig_list.append({"name": local_name, "type": "f64"})
```

This is a **plumbing gap**, not an architecture gap. The data exists at every layer — it just isn't piped to the WebSocket client.

---

## 2. What Icarus Already Provides

After `Simulator.stage()`, `schema_json` returns:

```json
{
  "summary": {
    "total_outputs": 78,
    "total_inputs": 14,
    "total_parameters": 24,
    "total_config": 8,
    "integrable_states": 13,
    "unwired_inputs": 1
  },
  "components": [
    {
      "name": "Rocket.Engine",
      "type": "SolidRocketEngine",
      "outputs": [
        {"name": "Rocket.Engine.thrust", "unit": "N", "description": "Net thrust force"},
        {"name": "Rocket.Engine.mass_flow", "unit": "kg/s", "description": "Propellant mass flow rate"},
        {"name": "Rocket.Engine.chamber_pressure", "unit": "Pa", "description": "Chamber pressure",
         "is_state": true}
      ],
      "inputs": [
        {"name": "Rocket.Engine.throttle_cmd", "unit": "", "description": "Throttle command [0,1]",
         "wired_to": ""}
      ],
      "parameters": [
        {"name": "Rocket.Engine.max_thrust", "unit": "N", "description": "Maximum thrust",
         "value": 75000.0, "optimizable": true}
      ],
      "config": [
        {"name": "Rocket.Engine.num_nozzles", "description": "Number of nozzles",
         "value": 1}
      ]
    },
    {
      "name": "Rocket.Body",
      "type": "Vehicle6DOF",
      "outputs": [
        {"name": "Rocket.Body.position.x", "unit": "m", "description": "X position (ECI)"},
        {"name": "Rocket.Body.velocity.x", "unit": "m/s", "description": "X velocity (ECI)"},
        ...
      ],
      "inputs": [
        {"name": "Rocket.Body.force.x", "unit": "N", "description": "Applied force X",
         "wired_to": "Rocket.Engine.thrust_body.x"},
        ...
      ],
      ...
    },
    ...
  ]
}
```

Key fields per signal:
- `name`: Full qualified path (`Entity.Component.signal`)
- `unit`: Physical unit string
- `description`: Human-readable text
- `wired_to`: Source signal path (empty string if unwired — these are externally controllable)
- `is_state`: Boolean, true if this signal is an integrable state variable
- `value` (parameters only): Current numeric value
- `optimizable` (parameters only): Whether the trim solver can vary this

---

## 3. Proposed Solution

### 3.1 New WebSocket Action: `introspect`

Add a new action that returns the internal structure of a module. This is a **query** — it does not modify simulation state.

**Client → Server:**
```json
{"action": "introspect", "params": {"module": "rocket"}}
```

**Server → Client (success):**
```json
{
  "type": "ack",
  "action": "introspect",
  "module": "rocket",
  "module_type": "icarus",
  "components": [
    {
      "name": "Rocket.Engine",
      "type": "SolidRocketEngine",
      "outputs": [
        {"name": "Rocket.Engine.thrust", "unit": "N", "description": "Net thrust force",
         "is_state": false}
      ],
      "inputs": [
        {"name": "Rocket.Engine.throttle_cmd", "unit": "", "description": "Throttle command [0,1]",
         "wired_to": ""}
      ],
      "parameters": [
        {"name": "Rocket.Engine.max_thrust", "unit": "N", "value": 75000.0,
         "optimizable": true}
      ]
    },
    ...
  ],
  "internal_wiring": [
    {"src": "Rocket.Engine.thrust", "dst": "Rocket.Body.force.x"},
    {"src": "Rocket.Body.position.x", "dst": "Rocket.Gravity.position.x"},
    ...
  ],
  "execution_order": ["Rocket.Engine", "Rocket.FuelTank", "Rocket.Gravity", "Rocket.Aero", "Rocket.Body"],
  "summary": {
    "total_components": 5,
    "total_outputs": 78,
    "total_inputs": 14,
    "integrable_states": 13
  }
}
```

**Server → Client (module doesn't support introspection):**
```json
{
  "type": "error",
  "message": "Module 'inputs' does not support introspection (type: inproc)"
}
```

### 3.2 Schema Enhancement: `supports_introspection` hint

Extend the schema message so Daedalus knows which modules can be introspected *before* asking:

```json
{
  "type": "schema",
  "modules": {
    "inputs": {
      "signals": [...],
      "module_type": "inproc"
    },
    "rocket": {
      "signals": [...],
      "module_type": "icarus",
      "supports_introspection": true,
      "component_count": 5
    }
  },
  "wiring": [...]
}
```

New optional fields per module:
- `module_type`: String identifying the module backend (`"inproc"`, `"script"`, `"icarus"`)
- `supports_introspection`: Boolean, true if `introspect` action will work
- `component_count`: Integer hint for UI (how many sub-components exist)

---

## 4. What Needs to Change

### 4.1 Hermes Changes

#### A. Module Interface: Add `introspect()` method

**File**: New method on module base / `IcarusModule`

```python
# hermes/modules/icarus_module.py

def introspect(self) -> dict[str, Any] | None:
    """Return internal component structure, or None if not supported."""
    schema = self._sim.schema_json

    # Build internal wiring from input wired_to fields
    internal_wiring = []
    components = schema.get("components", [])
    for comp in components:
        for inp in comp.get("inputs", []):
            wired_to = inp.get("wired_to", "")
            if wired_to:
                internal_wiring.append({
                    "src": wired_to,
                    "dst": inp["name"]
                })

    return {
        "module_type": "icarus",
        "components": components,
        "internal_wiring": internal_wiring,
        "execution_order": self._get_execution_order(),
        "summary": schema.get("summary", {})
    }
```

For non-Icarus modules (`InprocModule`, `ScriptModule`), `introspect()` returns `None`.

#### B. WebSocket Server: Handle `introspect` action

**File**: `hermes/server/websocket.py`

Add to the command dispatcher (alongside `subscribe`, `pause`, etc.):

```python
async def _handle_introspect(self, client: ClientState, params: dict) -> None:
    module_name = params.get("module")
    if not module_name:
        await self._send_error(client, "Missing 'module' parameter")
        return

    module = self._pm.get_module(module_name)
    if module is None:
        await self._send_error(client, f"Unknown module: {module_name}")
        return

    result = module.introspect() if hasattr(module, 'introspect') else None
    if result is None:
        await self._send_error(
            client,
            f"Module '{module_name}' does not support introspection"
        )
        return

    response = {
        "type": "ack",
        "action": "introspect",
        "module": module_name,
        **result
    }
    await client.ws.send(json.dumps(response))
```

#### C. Schema Builder: Include module type hints

**File**: `hermes/server/websocket.py` — `_build_rich_schema()`

```python
# Current (line 283):
modules[mod_name] = {"signals": sig_list}

# New:
module_entry: dict[str, Any] = {"signals": sig_list}
module_entry["module_type"] = mod_config.type.value  # "inproc", "script", "icarus"

# Check if module supports introspection
module_instance = self._pm.get_module(mod_name)
if hasattr(module_instance, 'introspect') and module_instance.introspect() is not None:
    module_entry["supports_introspection"] = True
    schema_data = module_instance.introspect()
    module_entry["component_count"] = len(schema_data.get("components", []))

modules[mod_name] = module_entry
```

#### D. ProcessManager: Expose module instances

**File**: `hermes/core/process_manager.py` (or wherever modules are stored)

The WebSocket server needs access to module instances to call `introspect()`. This may require adding a `get_module(name)` accessor to the process manager if one doesn't exist.

### 4.2 Icarus Changes

**None required.** Icarus already provides everything via:
- `Simulator.schema_json` → `DataDictionary` with full component structure
- `Simulator.Registry()` → Signal metadata with wiring status
- `SignalRouter.GetRoutes()` → Internal wiring table

The only optional enhancement:

#### Expose execution order

If `execution_order` isn't directly available from `schema_json`, add it:

```python
# icarus_module.py
def _get_execution_order(self) -> list[str]:
    """Get component execution order from the Icarus scheduler."""
    # If Icarus exposes this via schema_json or Registry:
    return [comp["name"] for comp in self._sim.schema_json.get("components", [])]
    # Components in schema_json are typically already in execution order
```

### 4.3 Daedalus Changes (Future — Consuming Side)

Not part of this Hermes proposal, but for context — what Daedalus would do with introspection data:

1. **On schema received**: Check `supports_introspection` per module
2. **On double-click module node**: Send `{"action": "introspect", "params": {"module": "rocket"}}`
3. **On introspection ack**: Build a sub-topology graph from `components` + `internal_wiring`
4. **Render**: Open a sub-view (zoomed-in or overlay) showing the internal component graph
5. **Live values**: Components' signals already flow through normal telemetry — just need to map internal signal paths to buffer indices

---

## 5. Protocol Summary

### New Action

| Action | Direction | Purpose |
|:-------|:----------|:--------|
| `introspect` | Client → Server | Query internal structure of a module |

### New Schema Fields

| Field | Type | On | Purpose |
|:------|:-----|:---|:--------|
| `module_type` | string | module entry | Backend type (`"icarus"`, `"inproc"`, etc.) |
| `supports_introspection` | bool | module entry | Whether `introspect` action will work |
| `component_count` | int | module entry | Sub-component count (UI hint) |

### Response Schema: `introspect` ack

```
{
  type: "ack",
  action: "introspect",
  module: string,
  module_type: string,
  components: [
    {
      name: string,
      type: string,
      outputs: [{name, unit, description, is_state}],
      inputs: [{name, unit, description, wired_to}],
      parameters: [{name, unit, value, optimizable}]  // optional
    }
  ],
  internal_wiring: [{src: string, dst: string}],
  execution_order: [string],             // optional
  summary: {total_components, total_outputs, total_inputs, integrable_states}
}
```

---

## 6. Implementation Effort

| Layer | Change | Effort | Risk |
|:------|:-------|:-------|:-----|
| **Icarus** | None | Zero | None — data already exposed |
| **IcarusModule** | Add `introspect()` method | Small — wraps existing `schema_json` | Low — read-only query |
| **WebSocket Server** | Handle `introspect` action | Small — ~30 lines | Low — follows existing action pattern |
| **Schema Builder** | Add `module_type`, `supports_introspection` | Small — 5 lines | Low — backward compatible (new optional fields) |
| **ProcessManager** | Expose module instances to WS server | Small — accessor method | Low |
| **Daedalus** | Consume introspection data in topology view | Medium — new sub-graph rendering | Medium — Phase 4+ work |

**Total Hermes effort**: ~100 lines of Python across 3-4 files. No breaking changes.

---

## 7. Backward Compatibility

All changes are **additive**:
- `introspect` is a new action — old clients never send it, old servers reject it with "Unknown action"
- `module_type`, `supports_introspection`, `component_count` are new optional fields in the schema — old clients ignore unknown fields
- Modules that don't implement `introspect()` return `None` → server sends an error response
- The schema `signals` array is unchanged — all existing telemetry/subscription behavior is unaffected

---

## 8. Example Flow

```
Client connects
  ← schema: {modules: {rocket: {signals: [...], supports_introspection: true, component_count: 5}}}

Client subscribes
  → {"action": "subscribe", "params": {"signals": ["*"]}}
  ← ack

User double-clicks "rocket" node in Daedalus topology
  → {"action": "introspect", "params": {"module": "rocket"}}
  ← {
       type: "ack",
       action: "introspect",
       module: "rocket",
       components: [
         {name: "Rocket.Engine", type: "SolidRocketEngine",
          outputs: [{name: "Rocket.Engine.thrust", unit: "N", ...}],
          inputs: [{name: "Rocket.Engine.throttle_cmd", wired_to: ""}]},
         {name: "Rocket.Body", type: "Vehicle6DOF",
          outputs: [...],
          inputs: [{name: "Rocket.Body.force.x", wired_to: "Rocket.Engine.thrust_body.x"}]},
         ...
       ],
       internal_wiring: [
         {src: "Rocket.Engine.thrust", dst: "Rocket.Body.force.x"},
         {src: "Rocket.Body.position.x", dst: "Rocket.Gravity.position.x"},
         ...
       ],
       execution_order: ["Rocket.Engine", "Rocket.FuelTank", "Rocket.Gravity", "Rocket.Aero", "Rocket.Body"]
     }

Daedalus renders sub-topology:
  ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
  │ Rocket.Engine│──────→│ Rocket.Body  │──────→│ Rocket.Aero  │
  │ thrust: 75kN │       │ pos: 1200m   │       │ drag: 500N   │
  └──────────────┘       └──────────────┘       └──────────────┘
         ↑                      │
    throttle_cmd               ↓
    (from Hermes)        ┌──────────────┐
                         │Rocket.Gravity│
                         │ g: -9.81m/s² │
                         └──────────────┘
```
