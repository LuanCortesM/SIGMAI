# SIGMAI High-Level GIS Commands

SIGMAI exposes safe GIS commands so AI agents do not need to call generic Processing directly for common spatial workflows.

## Implemented

- `diagnose_crs`: read-only CRS diagnosis for the project and loaded layers.
- `validate_geometries`: read-only geometry validation for vector layers.
- `fix_geometries`: safe write command using `native:fixgeometries`.
- `buffer`: safe write command using `native:buffer`.
- `clip`: safe write command using `native:clip`.
- `dissolve`: safe write command using `native:dissolve`.
- `reproject_layer`: safe write command using `native:reprojectlayer`.
- `export_layer`: safe write command for vector exports.

## Export Formats

- `GPKG`
- `GeoJSON`
- `Shapefile` / `SHP`

Raster export is planned for a later phase.

## Processing Allowlist

Generic `run_processing` is restricted to:

- `native:buffer`
- `native:clip`
- `native:dissolve`
- `native:fixgeometries`
- `native:reprojectlayer`
- `native:multiparttosingleparts`
- `native:centroids`
- `native:intersection`
- `native:union`
- `native:difference`
- `native:extractbyattribute`
- `native:extractbylocation`

Prefer high-level commands whenever available.
## Cartographic Map Generation Commands

SIGMAI separates layout creation from cartographic composition:

- `create_layout` creates the print layout page/base.
- `add_layout_map` inserts a visible map item.
- `set_layout_extent` sets the spatial extent and helps avoid blank exports.
- `set_layer_style` applies a readable default vector style.

## Level 6 Vector, Attribute and Expression Commands

Layer tree:

- `list_layer_tree`
- `set_layer_visibility`
- `move_layer_order`
- `create_layer_group`
- `move_layer_to_group`

Attributes:

- `list_fields`
- `sample_features`
- `inspect_attribute_table`
- `field_statistics`
- `unique_values`

Expressions:

- `validate_expression`
- `evaluate_expression`
- `query_features`

Selection and extraction:

- `select_by_expression`
- `select_by_attribute`
- `select_by_location`
- `extract_by_expression`
- `extract_by_attribute`
- `extract_by_location`

Vector analysis:

- `intersection`
- `union`
- `difference`
- `centroids`
- `multipart_to_singleparts`
- `count_points_in_polygon`
- `add_layout_label` adds title, source, credits and technical notes.
- `add_layout_legend` adds a legend.
- `add_layout_scale_bar` adds a scale bar.
- `add_layout_north_arrow` adds a north indication.
- `add_layout_grid` adds a map grid/graticule when supported by the QGIS layout API.
- `add_layout_picture` adds local image assets such as the SIGMAI logo.
- `generate_basic_map` orchestrates a complete basic map.
- `evaluate_layout_cartographic_completeness` grades the result as A/B/C/D and helps reject likely blank exports.
- `generate_workflow_report` writes an auditable Markdown report.

For common user requests, prefer `generate_basic_map`. For debugging or advanced cartographic control, use the atomic commands step by step.

## CRS-Safe Cartography Validation

The cartography commands were validated in QGIS after restart with mixed CRS layers:

- project CRS: `EPSG:4674`;
- projected test layers: `EPSG:31983`;
- reduced regression: 30/30 maps rendered;
- full stress regression: 200/200 maps rendered;
- blank/bad maps: 0.

Implementation rule for map commands: layer extents must be transformed to the project/layout CRS before being applied to `QgsLayoutItemMap`. Visual PNG assessment is used to prevent a technically successful export from being classified as a valid map when the map body is blank.

Known next refinements:

- improve scale bar behavior for geographic CRS;
- allow legends to be restricted to selected layer ids;
- improve default placement of north arrow and legend;
- add richer scientific templates.
