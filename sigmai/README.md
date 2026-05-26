# SIGMAI for QGIS
### Secure GIS-AI Interface

This folder contains the QGIS-side plugin.

Public name: SIGMAI. Technical QGIS package folder: `sigmai`.

Author: MACIEL, L. S. C.  
Email: herpetomantiqueira@gmail.com

## Plugin Authorship Vs Map Authorship

MACIEL, L. S. C. is the plugin author. SIGMAI-generated maps do not automatically use the plugin author as the map author.

Use `map_author`, SIGMAI user profile settings or QGIS project metadata to credit the generated cartographic product.

## What It Does

- Starts and stops a local bridge on `127.0.0.1:8765`.
- Requires a bearer token generated for the current session.
- Accepts structured JSON commands on `/command`.
- Executes a small whitelist of QGIS and Processing actions.
- Logs every request and result to `sigmai/logs/sigmai.jsonl`.
- Reports command capabilities and permission levels.
- Provides high-level GIS commands for CRS diagnosis, geometry validation, fix geometries, buffer, clip, dissolve, reprojection and layer export.
- Provides basic Developer Mode and Plugin Management inspection commands.

## Install for Manual Testing

Copy or symlink this `sigmai` folder into the QGIS profile plugin directory.

On Windows, a typical target is:

```text
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\sigmai
```

Then open QGIS, enable the plugin, and use the `SIGMAI` menu item.

## Manual Test

1. Open QGIS.
2. Enable SIGMAI.
3. Click `Start Bridge`.
4. Copy the token from the dialog.
5. From this repository, run:

```text
python codex_plugin/client/sigmai_client.py status --token TOKEN
python codex_plugin/client/sigmai_client.py capabilities --token TOKEN
python codex_plugin/client/sigmai_client.py environment --token TOKEN
python codex_plugin/client/sigmai_client.py list-layers --token TOKEN
python codex_plugin/client/sigmai_client.py list-plugins --token TOKEN
```

## Security Notes

- The bridge refuses non-localhost HTTP clients.
- Normal mode does not expose unrestricted Python execution.
- Developer Mode is disabled by default and requires explicit user activation before QGIS/PyQGIS development access is available.
- Existing output files are not overwritten unless `confirm_overwrite: true` is provided.
- The token is local session authentication, not cloud authentication.
