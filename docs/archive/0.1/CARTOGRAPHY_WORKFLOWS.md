# SIGMAI Cartography Workflows

## Plugin Authorship Vs Generated Map Authorship

Cartographic workflows must not assume that the plugin author is the author of the generated map.

Use these fields when generating maps:

- `map_author`
- `map_author_email`
- `organization`
- `data_source`
- `created_with`

If no map author is supplied, SIGMAI uses a generic credit line such as `Elaborado com SIGMAI - Secure GIS-AI Interface/QGIS.`

## Purpose

SIGMAI now supports atomic cartographic layout commands. These commands let an AI agent build a map step by step instead of exporting an empty layout.

## Atomic Workflow

1. `create_layout`
2. `set_layer_style`
3. `add_layout_map`
4. `set_layout_extent`
5. `add_layout_label`
6. `add_layout_legend`
7. `add_layout_scale_bar`
8. `add_layout_north_arrow`
9. `add_layout_grid` when coordinates/graticule are useful
10. `add_layout_picture` when a logo or image belongs on the map
11. `export_layout`
12. `evaluate_layout_cartographic_completeness`
13. `generate_workflow_report`

## High-Level Workflow

Use `generate_basic_map` for normal user requests. It creates a layout, adds a map item, title, legend, scale bar, north arrow, optional grid, optional logo, source label, exports the file, and returns a cartographic assessment.

## Important Notes

- `create_layout` alone creates a page/base and may be blank.
- `add_layout_map` inserts the visible map body.
- `set_layout_extent` prevents blank exports by setting the spatial extent.
- `set_layer_style` improves contrast and makes vector layers readable.

## Cleaner Default Legends

For user-facing map generation, agents should pass the main layer id through `legend_layers`:

```json
{
  "action": "generate_basic_map",
  "params": {
    "layer_id": "...",
    "legend_layers": ["..."],
    "layout_template": "scientific_basic"
  }
}
```

This prevents unrelated project layers from appearing in the layout legend. If a multi-layer legend is intended, list those layer ids explicitly.

## Scale Bar CRS Warning

When the project/map CRS is geographic, SIGMAI can still export a map, but it warns that metric scale bars may be approximate. For publication maps, prefer a projected CRS appropriate to the study area before final export.
- `add_layout_grid` adds a map grid/graticule when the QGIS layout map grid API is available.
- `add_layout_picture` inserts local PNG/JPG/SVG assets such as the SIGMAI logo.
- `evaluate_layout_cartographic_completeness` checks map item, extent, expected map elements and output size before declaring a map usable.
- `generate_workflow_report` makes the process auditable.

## Current Limitations

- Advanced label placement is not implemented.
- Feature-level highlighting is not implemented.
- Layer ordering commands are not implemented.
- Grid support depends on the QGIS layout map grid API available in the running QGIS version and returns warnings when a specific style option is unsupported.

## CRS-Safe Automatic Layouts

Post-restart validation confirmed that automatic layout extent handling is CRS-safe. When `add_layout_map`, `set_layout_extent` or `generate_basic_map` use a layer extent, SIGMAI transforms the layer extent to the current project CRS before applying it to the layout map item.

This is required because QGIS layouts interpret map extents in the map item's CRS. If a layer in `EPSG:31983` is used while the project is in `EPSG:4674`, applying the raw UTM extent directly can export a visually blank map.

Regression evidence:

- reduced 30-map battery: 30 rendered, 0 blank;
- full 200-map battery: 200 rendered, 0 blank;
- automatic modes passed for both `EPSG:4674` and `EPSG:31983` layers.

Current workflow recommendation:

1. Prefer `generate_basic_map` for normal map generation.
2. Use atomic commands for debugging or precise control.
3. Always keep visual PNG assessment enabled when validating cartographic outputs.
4. For metric scale bars, prefer projected CRS or emit a warning when the project CRS is geographic.
