# SIGMAI MCP Server

This folder contains a local MCP-oriented SIGMAI bridge wrapper.

The current implementation is dependency-free and exposes a JSON-lines tool runner. It is designed so a formal MCP SDK transport can be added later without changing SIGMAI commands.

Primary tools:

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

Legacy `sigmai_*` aliases are kept for compatibility.

Example:

```json
{"tool":"sigmai_status","arguments":{}}
```

Security:

- Uses local session discovery.
- Connects only to `127.0.0.1`/localhost.
- Does not expose the bearer token to the model.
- Blocks dangerous plugin/self-management actions from MCP.
- Leaves final token, permission, dry-run and confirmation enforcement inside the SIGMAI Bridge.
