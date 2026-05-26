# QGIS Debugging

Use this skill when investigating errors, failed commands, plugin problems, or QGIS runtime state.

## Workflow

1. Call `status`.
2. Call `get_capabilities`.
3. Call `get_qgis_environment`.
4. Call `get_recent_errors`.
5. Call `get_logs`.
6. If plugin-specific, call `inspect_plugin` and `collect_plugin_logs`.
7. Produce a concise diagnosis with next tests.

## Rules

- Keep command evidence separate from hypotheses.
- Do not hide bridge errors; preserve error codes and messages.
