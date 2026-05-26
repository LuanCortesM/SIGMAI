# QGIS Create Map

Use this skill when a user asks for a map in natural language.

## Workflow

1. Call `status`.
2. Call `get_capabilities`.
3. Call `get_project_info`.
4. Call `list_layers`.
5. Confirm the target layer id from bridge results.
6. Check CRS and layer validity.
7. Use `list_layouts`.
8. Use `create_layout` with `dry_run: true` if a new layout is needed.
9. Ask confirmation before any project-modifying command.
10. Use `export_layout` with overwrite protection.
11. Generate a workflow report.

## Rules

- Do not invent layer ids or layout names.
- Do not claim styling/layout items were created unless the bridge executed those commands.
- Explain cartographic choices in plain language.
