# QGIS Real Environment Test

Use this checklist after installing the plugin in QGIS.

## 1. Install Plugin

Copy:

```text
sigmai/qgis_plugin
```

to:

```text
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\sigmai
```

## 2. Start Bridge

1. Open QGIS.
2. Enable SIGMAI.
3. Open the SIGMAI panel.
4. Click `Start Bridge`.
5. Copy the token.

## 3. Terminal Tests

```text
python codex_plugin/client/sigmai_client.py status --token TOKEN
python codex_plugin/client/sigmai_client.py capabilities --token TOKEN
python codex_plugin/client/sigmai_client.py environment --token TOKEN
python codex_plugin/client/sigmai_client.py list-layers --token TOKEN
python codex_plugin/client/sigmai_client.py list-layouts --token TOKEN
python codex_plugin/client/sigmai_client.py list-plugins --token TOKEN
python codex_plugin/client/sigmai_client.py inspect-plugin --plugin-name sigmai --token TOKEN
python codex_plugin/client/sigmai_client.py validate-metadata --plugin-name sigmai --token TOKEN
python codex_plugin/client/sigmai_client.py recent-errors --token TOKEN
```

## 4. Export Layout Test

Create or open a project with a layout, then run an export command with a new output path.

If the file exists, confirm overwrite explicitly before using `confirm_overwrite: true`.

## 5. Stop and Restart Test

1. Stop the bridge in the panel.
2. Close QGIS.
3. Reopen QGIS.
4. Start the bridge again.
5. Confirm the port is available.
