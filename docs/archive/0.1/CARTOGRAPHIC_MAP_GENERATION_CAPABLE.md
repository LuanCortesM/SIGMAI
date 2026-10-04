# SIGMAI Cartographic Map Generation Capable

SIGMAI reaches the Cartographic Map Generation Capable level when it can create a real QGIS layout with a visible map body, valid extent, readable layer style, title, legend, scale, north indication, source/authorship, export output, and workflow report.

## Atomic Commands

- `create_layout`: creates the layout page/base.
- `add_layout_map`: inserts the visible `QgsLayoutItemMap`.
- `set_layout_extent`: sets the map extent and reduces blank export risk.
- `set_layer_style`: applies a readable single-symbol style.
- `add_layout_label`: adds title, source, authorship and notes.
- `add_layout_legend`: adds a linked legend.
- `add_layout_scale_bar`: adds a linked scale bar.
- `add_layout_north_arrow`: adds a north indication with a safe text fallback.
- `add_layout_grid`: enables a grid/graticule when the QGIS map grid API supports it.
- `add_layout_picture`: inserts local PNG/JPG/SVG images such as the SIGMAI logo.
- `export_layout`: exports PDF or PNG.
- `evaluate_layout_cartographic_completeness`: grades the result from A to D.

## Orchestrators

- `generate_basic_map`: builds and exports a basic cartographic map.
- `generate_workflow_report`: records the environment, layers, outputs, security posture and authorship.

## Blank Map Protection

`create_layout` alone can export a blank page. SIGMAI avoids that by requiring a map item, valid extent, visible style and output size checks before classifying the result as usable.

## Current Target

The immediate acceptance target is grade `A` or `B` from `evaluate_layout_cartographic_completeness` in a real QGIS run.

## CRS-Safe Layout Extent Handling

Validated after QGIS restart on 2026-05-22.

SIGMAI must never apply a layer extent directly to `QgsLayoutItemMap` when the layer CRS differs from the project/layout CRS. The safe strategy is:

- read the original layer extent in the layer CRS;
- transform that extent to the current project CRS with `QgsCoordinateTransform`;
- set the layout map item CRS to the project CRS;
- apply the transformed extent to the map item;
- export PNG and run visual assessment to reject likely blank maps.

This fixed the previous blank-map failure where the project was in `EPSG:4674` and several test layers were in `EPSG:31983`.

## Regression Evidence

Post-restart cartography regression:

- 30-map reduced battery: 30/30 bridge OK, 30/30 rendered, 0 blank/bad.
- 200-map stress battery: 200/200 bridge OK, 200/200 rendered, 0 blank/bad.
- Tested CRS mix: `EPSG:4674` and `EPSG:31983`.
- Tested modes: `basic_auto`, `atomic_auto`, `atomic_manual`.
- Tested layers: `SP_Municipios_2025`, `Cruzeiro limite municipal`, `Cruzeiro limite EPSG31983`, `TopoTrail potencial clip Cruzeiro`, `TopoTrail zonas potenciais 4 cartas`.

Current maturity result: `LEVEL 5 - Cartographic Map Generation Capable`.

## Remaining Visual Improvements

The maps are no longer blank, but the next cartographic refinement phase should address:

- scale bars showing `0 km` in geographic/project CRS contexts;
- legends including unrelated project layers;
- north arrow placement colliding with map/legend in some layouts;
- richer scientific layout templates for publication-quality products.

## Level 5 Consolidation Refinements

Implemented in the next development phase:

- `add_layout_legend` accepts `legend_layers`, `linked_layer_ids` and `filter_to_map_layers` so maps can show only the relevant layer in the legend.
- `generate_basic_map` defaults the legend to the main layer and accepts `legend_layers`, `layout_template`, `scale_strategy` and `prefer_projected_scale`.
- `add_layout_scale_bar` returns a warning when the linked map/project CRS is geographic, because metric scale bars can be approximate in degree-based CRS contexts.
- North arrow placement was adjusted to reduce collisions with map and legend items in the default layout.

The goal is to keep the proven blank-map protection while making default maps cleaner and easier to read.
