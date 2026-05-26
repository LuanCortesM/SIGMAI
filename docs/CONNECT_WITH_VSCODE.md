# Connect With VS Code

VS Code integration should:

1. Read `%LOCALAPPDATA%\SIGMAI\sessions\current_bridge_session.json`.
2. If multiple sessions exist, ask for the pairing code.
3. Call the local bridge at `127.0.0.1`.
4. Never expose the bearer token in UI except in an advanced debug panel.

Current manual CLI:

```text
python tools\sigmai.py status
python tools\sigmai.py layers
python tools\sigmai.py test
```
