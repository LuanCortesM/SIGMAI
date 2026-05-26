# SIGMAI for VS Code

The VS Code extension is planned but not implemented in the MVP.

The future extension should use the same core protocol as Codex:

- Connect to `127.0.0.1:8765`.
- Ask the user for the local token from QGIS.
- Send structured JSON commands.
- Display logs, layers, CRS diagnostics, and workflow results.
- Read `get_capabilities` before enabling UI actions.
- Support both Developer Mode and User Cartography Mode.
