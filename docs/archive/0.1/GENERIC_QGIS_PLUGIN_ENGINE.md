# SIGMAI Generic QGIS Plugin Engine

SIGMAI can not safely support the whole QGIS plugin ecosystem by hard-coding one adapter per plugin. The generic plugin engine therefore uses a layered model:

1. Inspect every installed plugin through metadata and static structure.
2. Detect likely entrypoints, Processing providers, UI actions and risk markers.
3. Expose Processing algorithms as dry-run plans first.
4. Allow real generic execution only when risk classification, confirmations and output validation pass.
5. Keep UI-only or risky plugins in inspect-only mode until a dedicated adapter is generated.

This engine never executes arbitrary plugin Python. It does not call plugin methods directly, does not click UI actions, and does not bypass SIGMAI permissions.

## Capability Modes

| Mode | Generic support | Notes |
|---|---|---|
| Metadata inspection | Yes | Safe for all installed plugins. |
| Static entrypoint inspection | Yes | Detects classFactory, initGui, actions, providers, dialogs and risk markers. |
| Processing algorithm manifest | Yes | Requires algorithm to be registered in QGIS Processing. |
| Processing dry-run plan | Yes | Reports missing parameters, outputs and risk. |
| Processing real run | Conditional | Requires low risk or explicit confirmations. |
| Direct plugin Python call | No | Blocked by design. |
| UI action invocation | No | Requires a dedicated adapter. |

## Acceptance Rule

The engine is considered functionally accepted only after at least 10 different trusted installed plugins are inspected successfully and any Processing algorithms among them can produce safe dry-run plans.

Current local regression found fewer than 10 installed plugin folders, so the engine is implemented but not yet fully accepted by the user's 10-plugin criterion.

