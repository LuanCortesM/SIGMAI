# SIGMAI MCP Server

SIGMAI includes a local MCP-oriented wrapper in `mcp_server/`.

Run:

```text
python mcp_server\sigmai_mcp_server.py
```

The dependency-free transport reads JSON lines from stdin and writes JSON lines to stdout. It is a safe MCP-compatible foundation; a formal MCP SDK transport can be added later without changing SIGMAI commands.

Core tools:

- `sigmai_tool_manifest`
- `sigmai_health`
- `sigmai_status`
- `sigmai_get_capabilities`
- `sigmai_get_qgis_environment`
- `sigmai_list_layers`
- `sigmai_get_layer_info`
- `sigmai_list_layouts`
- `sigmai_generate_basic_map_dry_run`
- `sigmai_generate_professional_map_dry_run`
- `sigmai_plan_workflow`
- `sigmai_dry_run_workflow`
- `sigmai_plugin_inventory`
- `sigmai_processing_providers`
- `sigmai_processing_algorithms`
- `sigmai_inspect_plugin`
- `sigmai_validate_metadata`
- `sigmai_command`

Legacy `sigmai_*` aliases remain for compatibility.

Security:

- Uses local session discovery.
- Connects only to localhost SIGMAI sessions.
- Does not expose the bearer token to the model.
- Dangerous self-management/plugin write actions are blocked at MCP level.
- SIGMAI Bridge still enforces token, permissions, dry-run and confirmation rules.

Example:

```json
{"tool":"sigmai_status","arguments":{}}
```
