# QGIS Plugin Testing

Use this skill when a developer asks to test a QGIS plugin in a real QGIS environment.

## Workflow

1. Call `status`.
2. Call `get_capabilities`.
3. Call `get_qgis_environment`.
4. Call `list_installed_plugins`.
5. Call `inspect_plugin`.
6. Call `validate_metadata_txt`.
7. Call `check_plugin_structure`, `check_plugin_imports`, `check_plugin_resources`, and `check_plugin_icon`.
8. Call `check_plugin_runtime_status`, and only then inspect menu/toolbar/provider registration if available.
9. Call `generate_plugin_report`.
10. Call `collect_plugin_logs` and `get_recent_errors`.
11. Report what was verified and what still needs manual QGIS confirmation.

## Rules

- Do not import or execute plugin code unless a safe bridge command supports it.
- Keep findings tied to file paths, metadata fields, and bridge evidence.
- For packaging or updates, run dry-run first and keep rollback available.
