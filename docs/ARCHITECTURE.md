# SIGMAI Architecture

SIGMAI - Secure GIS-AI Interface is a translation layer between AI agents and QGIS. It exposes QGIS through structured, auditable commands instead of free-form Python.

Public name and plugin identity: SIGMAI.

Author: MACIEL, L. S. C.  
Associated project: Herpeto Mantiqueira.

## Layers

1. **Core Protocol**
   - Schemas, taxonomy, examples, response envelopes, error model.
   - Independent from QGIS, Codex, VS Code, or any single client.

2. **QGIS Runtime**
   - Runs inside QGIS.
   - Owns PyQGIS, Processing, layouts, layers, CRS, plugins, and logs.
   - Accepts localhost HTTP commands with bearer token.

3. **Developer Tools**
   - Plugin inspection, metadata validation, logs, smoke-test planning, packaging roadmap.
   - Does not require arbitrary Python execution.

4. **Cartography Tools**
   - Layouts, map exports, future style and map composition commands.
   - Uses high-level commands so users do not need to know PyQGIS.

5. **Processing Tools**
   - Generic `run_processing` exists with an allowlist.
   - Higher-level commands are implemented for CRS diagnosis, geometry validation, fix geometries, buffer, clip, dissolve, reprojection and layer export.

6. **AI Agent Skills**
   - Codex skills teach agents when to inspect, plan, dry-run, confirm, execute, and report.

7. **Future VS Code Integration**
   - Developer-facing UI for connection, plugin validation, logs, packaging, and command workflows.

## Current Expansion

Protocol version `0.2` adds:

- `get_capabilities`
- `get_qgis_environment`
- `get_bridge_config`
- `get_recent_errors`
- `list_layouts`
- `create_layout`
- `list_installed_plugins`
- `inspect_plugin`
- `validate_metadata_txt`
- `collect_plugin_logs`
- `schema_version`
- `request_id`
- `dry_run`
- response `permission_level`

## Design Rule

AI agents should ask the bridge what is available before acting:

1. `status`
2. `get_capabilities`
3. inspect project/layers/environment
4. dry-run modifying commands
5. request confirmation for destructive operations
6. execute structured commands
7. generate workflow report
