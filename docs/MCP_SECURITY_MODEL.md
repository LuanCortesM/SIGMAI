# MCP Security Model

- MCP server connects only to `127.0.0.1`.
- MCP server does not accept remote network commands.
- MCP server does not expose the bearer token to the model.
- MCP server uses local session discovery.
- QGIS Bridge still validates bearer token.
- Destructive commands still require confirmation in the Bridge protocol.
- MCP blocks dangerous self-management/plugin write actions such as `self_apply_update`, `self_stage_update`, `self_rollback`, `install_plugin_from_folder`, `update_plugin_from_folder`, `uninstall_plugin`, `enable_plugin`, `disable_plugin` and `reload_plugin`.
- MCP exposes read-only actions directly and mutation-capable actions only through dry-run wrappers unless a future dedicated adapter adds a narrower confirmation flow.
- The MCP tool manifest masks token information and only reports whether a token was discovered.
- No arbitrary Python execution is exposed.
- No `0.0.0.0` binding.
- Bridge logs remain auditable.
