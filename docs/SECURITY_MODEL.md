# Security Model

SIGMAI is a local automation bridge. It must be secure by default.

## Core Controls

- HTTP server binds only to `127.0.0.1`.
- Bearer token required.
- Command whitelist.
- Structured JSON only.
- No arbitrary Python execution in normal mode.
- Dangerous tokens are rejected.
- Existing output overwrite requires `confirm_overwrite: true`.
- Commands are logged.
- Responses include `schema_version`, `request_id`, and `permission_level`.

## Permission Levels

1. `read_only`
   - status, capabilities, layers, project info, logs, plugin inspection.

2. `safe_write`
   - controlled layout/export/style/temporary Processing operations.

3. `project_write`
   - future project save, layer removal, CRS changes, loading data.

4. `developer`
   - future packaging, test runners, skeleton generation.

5. `unsafe_developer`
   - explicit QGIS/PyQGIS execution for plugin development.
   - disabled by default.
   - requires the red DEV button in the QGIS UI and typed confirmation `SIM`.
   - still blocks common OS shell/network markers such as `subprocess`, `os.system`, `popen`, `socket`, `requests.` and `urllib.request`.

## Developer Mode

SIGMAI has an explicit Developer Mode for controlled QGIS plugin development.

This mode is intentionally separated from the normal secure bridge. It must be activated in the QGIS UI and displays this warning:

`Esse modo tem riscos de corromper o seu QGIS. Use com cuidado, pois mexe direto no Python da ferramenta.`

Activation requires typing:

`SIM`

When enabled, the command `dev_execute_qgis_python` can execute QGIS/PyQGIS code in the active QGIS process. The command still requires bearer token authentication, local-only access, structured JSON, logging and `confirm_dev_python: "SIM"`.

Developer Mode can corrupt the active QGIS session or project. It is intended for plugin development, testing and debugging only.

## Confirmation Rules

Actions that overwrite, remove, save, or delete must require explicit confirmation.

## Audit Rules

Every accepted command should log:

- timestamp;
- request origin;
- request id;
- action;
- success or failure;
- error code when applicable.
