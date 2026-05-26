# QGIS Export Map

Use this skill when the user asks to export an existing QGIS layout to PDF or PNG.

## Workflow

1. Call `status`.
2. Call `get_project_info` to list available layouts.
3. Confirm the `layout_name`, format, and output path.
4. If the output file exists, require explicit overwrite confirmation.
5. Send an `export_layout` command.
6. Report the exported path from the bridge response.
