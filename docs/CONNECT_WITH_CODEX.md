# Connecting Codex to QGIS

Codex CLI reads MCP servers from `~/.codex/config.toml`. The SIGMAI panel produces the block: step 2, choose **Codex CLI**, press **Copiar configuração**, and append it to the file.

```toml
[mcp_servers.sigmai]
command = "/absolute/path/to/python"
args = ["/absolute/path/to/sigmai/mcp/sigmai_mcp.py"]

[mcp_servers.sigmai.env]
PYTHONUNBUFFERED = "1"
PYTHONUTF8 = "1"
```

Note the TOML section name is `mcp_servers` with an underscore, unlike the JSON clients' `mcpServers`. Everything else — absolute paths, the bridge running first — is the same.

## Without MCP

If you would rather not configure MCP, the repository ships a direct client:

```bash
python tools/sigmai.py connect SG-4821-KQ9M
```

The pairing code is shown in the SIGMAI panel. This path exists for scripting and debugging; the MCP server is the supported route for AI assistants, because it is the one that carries tool schemas, annotations and the audit report back to the model.

See also [DIRECT_CODEX_CONNECTION.md](CONNECT_WITH_CODEX.md) and, for diagnosis, the troubleshooting section of [CONNECT_WITH_CLAUDE.md](CONNECT_WITH_CLAUDE.md#when-it-does-not-connect).
