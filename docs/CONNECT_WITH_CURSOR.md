# Connecting Cursor to QGIS

SIGMAI exposes a standard MCP stdio server, so Cursor connects the same way as any other MCP client. The SIGMAI panel builds the block for you: step 2, choose **Cursor**, press **Copiar configuração**.

Configuration file: `~/.cursor/mcp.json` (`%USERPROFILE%\.cursor\mcp.json` on Windows). You can also reach it through **Settings ▸ MCP ▸ Add new MCP server**.

```json
{
  "mcpServers": {
    "sigmai": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/sigmai/mcp/sigmai_mcp.py"],
      "env": { "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1" }
    }
  }
}
```

Both paths must be absolute. The process Cursor launches inherits neither your shell's `PATH` nor a predictable working directory, which is why a bare `python` or a relative script path fails silently.

Start the bridge in QGIS first (step 1 of the panel), then reload Cursor's MCP servers.

For diagnosis, the troubleshooting section of [CONNECT_WITH_CLAUDE.md](CONNECT_WITH_CLAUDE.md#when-it-does-not-connect) applies unchanged — the failure modes belong to the transport, not to the client.
