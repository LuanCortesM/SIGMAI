# Direct Codex Connection

SIGMAI supports direct local discovery so Codex can connect without copying the token every time.

## Ideal Flow

1. Install SIGMAI in QGIS.
2. Enable the plugin once.
3. Open the SIGMAI panel.
4. Enable `Start bridge automatically when QGIS starts`.
5. Keep `Write local session file for AI clients` enabled.
6. Start the bridge.
7. In Codex, run:

```text
python codex_plugin/client/sigmai_client.py status
python codex_plugin/client/sigmai_client.py capabilities
python tools/sigmai_autotest.py --run-integration
```

No manual token is needed when the session file is readable.

## Session File Location

Preferred Windows path:

```text
%LOCALAPPDATA%\SIGMAI\current_bridge_session.json
```

Fallback:

```text
%TEMP%\SIGMAI\current_bridge_session.json
```

The file contains only local connection information:

```json
{
  "schema_version": "0.2",
  "host": "127.0.0.1",
  "port": 8765,
  "token": "...",
  "started_at": "...",
  "qgis_version": "...",
  "plugin_version": "...",
  "pid": 1234,
  "session_id": "..."
}
```

## Discovery Priority

Clients resolve connection settings in this order:

1. CLI parameters such as `--token`, `--host`, `--port`.
2. Environment variables:
   - `SIGMAI_SESSION_FILE`
   - `SIGMAI_TOKEN`
   - `SIGMAI_HOST`
   - `SIGMAI_PORT`
3. Local session file.
4. Defaults: `127.0.0.1:8765`.

## Security

- The bridge still binds only to `127.0.0.1`.
- Bearer token is still required.
- No remote access is enabled.
- No arbitrary Python execution is enabled.
- Session files are ignored by git.
- Disabling `Write local session file for AI clients` forces manual token usage.
