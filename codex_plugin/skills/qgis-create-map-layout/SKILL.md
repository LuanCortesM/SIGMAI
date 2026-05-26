# QGIS Create Map Layout

Use this skill when the user asks for a map layout workflow. Use this skill when the user asks for a safe map layout workflow through SIGMAI.

## Workflow

1. Call `status`.
2. Call `get_project_info` to list layouts.
3. If no suitable layout exists, explain that advanced layout automation should be requested through cartography commands and provide the exact missing requirement.
4. If a layout exists, use `export_layout` after validating the output path and overwrite confirmation.

## Safety

- Never overwrite exported maps without explicit confirmation.
- Do not pretend a layout was created if the bridge only exported an existing one.

