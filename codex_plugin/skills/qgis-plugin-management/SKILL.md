# QGIS Plugin Management

Use this skill when installing, updating, reloading, disabling, packaging, or auditing QGIS plugins through SIGMAI.

## Workflow

1. Call `status`.
2. Call `get_capabilities`.
3. Call `list_installed_plugins`.
4. Call `inspect_plugin` and `generate_plugin_report`.
5. For packaging, call `package_plugin_zip` with `dry_run=true` before creating the zip.
6. For install/update operations, call dry-run first, review destination and backup plan, then require explicit confirmation.
7. For runtime enable/disable/reload, warn that restart may still be required.

## Safety

- Never uninstall or overwrite without backup.
- Never update `sigmai` through `update_plugin_from_folder`.
- Never use arbitrary Python execution.
- Keep the report and manifest in the final answer.
