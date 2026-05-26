# Commands

SIGMAI commands are structured JSON objects sent to the local QGIS bridge.

HTTP endpoint:

```text
POST http://127.0.0.1:8765/command
Authorization: Bearer TOKEN
Content-Type: application/json
```

## Required Shape

```json
{
  "schema_version": "0.2",
  "request_id": "req-1",
  "action": "list_layers",
  "params": {},
  "dry_run": false
}
```

`params` is optional for commands that do not need parameters.

## Core Commands

- `status`: bridge and QGIS runtime status.
- `get_capabilities`: list available command groups and safety metadata.
- `get_qgis_environment`: QGIS, Python, profile, plugins, Processing providers, and project environment.
- `get_bridge_config`: local bridge configuration.
- `get_recent_errors`: recent error-like audit log entries.
- `list_layers`: list current project layers.
- `list_project_layers`: alias for project layer listing.
- `get_project_info`: project path, CRS, layer count, layouts.
- `get_project_crs`: current project CRS.
- `get_layer_info`: detailed metadata for one layer.
- `list_layouts`: list print layouts.
- `create_layout`: create a basic layout, supports dry-run.
- `run_processing`: run an allowed Processing algorithm with structured parameters.
- `export_layout`: export a named layout to PDF or PNG.
- `get_logs`: return recent bridge logs.
- `list_installed_plugins`: discover QGIS plugins.
- `inspect_plugin`: inspect one plugin folder.
- `validate_metadata_txt`: validate core QGIS plugin metadata fields.
- `collect_plugin_logs`: collect bridge logs related to a plugin.

## Safety Rules

- Commands are not Python code.
- Unknown actions are rejected.
- Dangerous keys such as `exec`, `eval`, `shell`, and `subprocess` are rejected anywhere in the payload.
- Output file overwrite requires `confirm_overwrite: true`.
- The bridge must bind only to `127.0.0.1`.
- Modifying commands should support `dry_run` where practical.
