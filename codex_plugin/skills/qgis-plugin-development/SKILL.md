# QGIS Plugin Development

Use this skill when developing or debugging QGIS plugins with help from SIGMAI.

## Workflow

1. Use SIGMAI to inspect the runtime QGIS state instead of guessing from files alone.
2. Call `status` to confirm QGIS is reachable.
3. Call `get_capabilities`.
4. Call `get_qgis_environment`.
5. Use `inspect_plugin`, `validate_metadata_txt`, `check_plugin_structure`, `check_plugin_imports`, `check_plugin_resources`, and `check_plugin_icon` for plugin evidence.
6. Use `check_plugin_runtime_status`, `check_plugin_menu_actions`, `check_plugin_toolbar_actions`, and `check_processing_provider_registration` when QGIS runtime evidence matters.
7. Use `generate_plugin_report` before recommending publication or larger changes.
8. Use `get_logs` after failures.
9. Use `list_layers` and `get_project_info` when plugin behavior depends on the open project.
10. Keep plugin file edits separate from bridge commands.

## Safety

- The bridge is for structured diagnostics and approved QGIS actions.
- Do not add a generic Python execution command to solve a one-off debugging problem.
- Never modify a plugin without backup, dry-run, and explicit confirmation.
- Never update `sigmai` through normal plugin update commands; use Self-Management Mode.
