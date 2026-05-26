# SIGMAI Developer Mode

Developer Mode is an explicit, high-risk mode for QGIS plugin development and controlled PyQGIS debugging.

It is disabled by default.

## UI Activation

In the SIGMAI QGIS panel, Developer Mode appears as a red DEV button.

To enable it, the user must:

1. Click the red DEV button.
2. Read the warning:
   `Esse modo tem riscos de corromper o seu QGIS. Use com cuidado, pois mexe direto no Python da ferramenta.`
3. Type `SIM`.

To disable it, click the same button again.

## What It Enables

When enabled, SIGMAI exposes:

- `get_dev_mode_status`
- `dev_execute_qgis_python`

`dev_execute_qgis_python` runs explicit QGIS/PyQGIS code inside the active QGIS process.

The command still requires:

- DEV mode enabled in the QGIS UI;
- bearer token authentication;
- local-only bridge;
- `confirm_dev_python: "SIM"`;
- structured JSON request;
- logging.

## What Remains Blocked

Developer Mode is not a general Windows shell.

The initial implementation blocks common OS/network execution markers:

- `subprocess`
- `os.system`
- `popen`
- `startfile`
- `shutil.rmtree`
- `socket`
- `requests.`
- `urllib.request`

The purpose is QGIS and PyQGIS automation, not arbitrary system control.

## Intended Uses

- Inspect QGIS runtime state.
- Test plugin imports.
- Prototype PyQGIS snippets.
- Debug Processing providers.
- Verify menu/toolbar/plugin behavior.
- Create controlled plugin development experiments.

## Risks

Developer Mode can:

- mutate the current QGIS project;
- alter layer state;
- change plugin runtime state;
- crash QGIS if unsafe code is executed;
- corrupt unsaved project work.

Use it only in a test project or after saving backups.
