# Autotest and Autoinstall

This workflow automates as much as possible while keeping SIGMAI secure.

## Scenario A - Do Everything Possible

```text
python tools/sigmai_autotest.py --full --launch-qgis
```

What it does:

1. Detects QGIS.
2. Installs or updates the QGIS plugin.
3. Opens QGIS.
4. Runs unit tests.
5. Waits for the bridge.
6. Runs integration tests if the bridge becomes available.

If QGIS opens but the bridge does not start, enable the plugin and click `Start Bridge`.

## Scenario B - QGIS Opened but Bridge Did Not Start

1. In QGIS, enable the SIGMAI plugin.
2. Click `Start Bridge`.
3. Copy the token.
4. Run:

```text
python tools/sigmai_autotest.py --wait-bridge --run-integration --token TOKEN
```

## Scenario C - Plugin Is Already Running

```text
python tools/sigmai_autotest.py --run-integration --token TOKEN
```

If the plugin wrote a session file, the token may be read automatically.

## Scenario D - Only Install Plugin

```text
python tools/sigmai_autotest.py --install-plugin
```

or:

```text
python tools/install_qgis_plugin.py
```

If QGIS reports `No module named 'sigmai/qgis_plugin'`, the plugin was installed from the wrong folder. Use:

```text
python tools/package_qgis_plugin_zip.py
```

Then install `test_outputs/sigmai.zip` from QGIS Plugin Manager. See `docs/FIX_QGIS_PLUGIN_LOAD_ERROR.md`.

## Scenario E - Only Validate Environment

```text
python tools/detect_qgis_installation.py
```

## Bridge Session Token

When the QGIS plugin starts the bridge, it writes a local session file in the installed plugin folder:

```text
%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/sigmai/diagnostics/current_bridge_session.json
```

It also writes a shared local session file intended for Codex automation:

```text
%TEMP%/sigmai/current_bridge_session.json
```

This file is ignored by git and should not be shared.

## Safety

- The bridge remains bound to `127.0.0.1`.
- Bearer token is still required.
- Integration tests use `dry_run` for supported modifying commands.
- Original files in `SIGMAI test data folder` are not modified.
- Outputs go to `test_outputs/`.

