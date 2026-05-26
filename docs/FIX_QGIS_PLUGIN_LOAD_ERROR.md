# Fix QGIS Plugin Load Error

Error:

```text
ModuleNotFoundError: No module named 'sigmai/qgis_plugin'
```

Cause:

QGIS is trying to load the project path `sigmai/qgis_plugin` as if it were a Python package. That cannot work because:

- `sigmai` has a hyphen, which is not a valid Python package name.
- `sigmai/qgis_plugin` is a nested project path, not the plugin package name.
- QGIS plugins must live directly under the QGIS plugins folder.

Correct plugin folder name:

```text
sigmai
```

Correct installed structure:

```text
%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/sigmai/
  metadata.txt
  __init__.py
  plugin.py
  bridge_server.py
  command_registry.py
  validators.py
  security.py
  qgis_actions/
  icons/
```

## Option A - Install from ZIP

From the project folder, run:

```text
python tools/package_qgis_plugin_zip.py
```

Then in QGIS:

1. Open `Plugins > Manage and Install Plugins`.
2. Choose `Install from ZIP`.
3. Select:

```text
sigmai/test_outputs/sigmai.zip
```

4. Enable the plugin named `SIGMAI`.

## Option B - Manual Copy

Copy the contents of:

```text
sigmai/qgis_plugin/
```

into:

```text
%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/sigmai/
```

Do not copy the whole `sigmai` folder into QGIS plugins.

Do not name the plugin folder:

```text
sigmai
qgis_plugin
sigmai/qgis_plugin
```

## Cleanup Bad Install

If QGIS has a broken entry, close QGIS and remove incorrectly copied folders such as:

```text
%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/sigmai
%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/qgis_plugin
```

Then install the correct `sigmai` folder or ZIP.
