# Connect With Claude

Claude-compatible clients should use the local MCP wrapper:

```text
python mcp_server\sigmai_mcp_server.py
```

The wrapper discovers the active local session and calls the QGIS Bridge on `127.0.0.1`.

If MCP setup is unavailable, use the pairing code flow:

```text
python tools\sigmai.py connect SG-4821-KQ9M
```
