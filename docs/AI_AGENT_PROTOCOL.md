# AI Agent Protocol

Agents must treat SIGMAI as the source of truth for QGIS state.

## First Commands

Always start with:

```json
{ "schema_version": "0.2", "action": "status" }
```

Then:

```json
{ "schema_version": "0.2", "action": "get_capabilities" }
```

## Response Envelope

```json
{
  "schema_version": "0.2",
  "request_id": "req-1",
  "ok": true,
  "action": "get_capabilities",
  "data": {},
  "warnings": [],
  "errors": [],
  "meta": {
    "timestamp": "2026-05-17T16:00:00Z",
    "duration_ms": 0,
    "permission_level": "read_only"
  }
}
```

## Agent Rules

- Never invent `layer_id`, layout names, plugin names, CRS, or Processing algorithm ids.
- Never modify data before inspecting CRS and layer validity.
- Use `dry_run: true` for modifying commands when supported.
- Ask the user before destructive actions or overwrites.
- Prefer high-level commands over generic `run_processing`.
- Generate a workflow report for multi-step tasks.

## Workflow Format

Workflows are documented as lists of commands:

```json
{
  "workflow_name": "create_basic_map",
  "steps": [
    { "action": "status" },
    { "action": "get_capabilities" },
    { "action": "list_layers" },
    { "action": "get_project_info" },
    { "action": "list_layouts" },
    { "action": "export_layout" }
  ]
}
```

The current protocol documents workflows. A future executor should add `job_id`, progress, dry-run, and workflow reports.
## Cartography Protocol Guidance

For map creation, agents must not treat `create_layout` as a complete map. The safe sequence is:

1. `create_layout`
2. `set_layer_style`
3. `add_layout_map`
4. `set_layout_extent`
5. `add_layout_label`
6. `add_layout_legend`
7. `add_layout_scale_bar`
8. `add_layout_north_arrow`
9. `export_layout`
10. `generate_workflow_report`

For ordinary user requests, prefer `generate_basic_map` because it orchestrates the sequence and returns a cartographic assessment.

