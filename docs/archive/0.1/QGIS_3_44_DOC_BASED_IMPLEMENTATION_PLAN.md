# QGIS 3.44 Doc-Based Implementation Plan

The local QGIS 3.44 documentation analysis identified practical API families for SIGMAI growth.

## Cartography

Use `QgsPrintLayout`, `QgsLayoutItemMap`, `QgsLayoutItemLabel`, `QgsLayoutItemLegend`, `QgsLayoutItemScaleBar`, `QgsLayoutItemPicture` and `QgsLayoutExporter`. A layout is not a map until a map item has extent, layer visibility and styling.

### CRS-safe layout extent rule

When a layer extent is used to define a layout map item extent, transform it from the layer CRS to the project/layout CRS first. QGIS layout map items interpret extents in their own CRS. Applying raw `EPSG:31983` coordinates to a project/layout in `EPSG:4674` can export a blank page even though the layer is valid.

SIGMAI's cartography implementation follows this rule for `add_layout_map`, `set_layout_extent` and `generate_basic_map`, and then validates the exported PNG visually.

Validated result after QGIS restart:

- 30-map regression: 30/30 rendered.
- 200-map regression: 200/200 rendered.
- Blank maps: 0.

## Vectors and Expressions

Prioritize read-only attribute inspection, bounded feature samples, expression validation and safe selection/extract commands. Expressions are preferred over arbitrary Python because they are native, auditable and limited by QGIS expression semantics.

## Raster

Start with raster metadata, band statistics, clipping and terrain algorithms through safe Processing profiles. Long raster tasks should move to the job queue phase.

## Workflows and Jobs

Use explicit step lists, named outputs, dry-run validation and workflow reports. `QgsTask` should be used carefully: do not touch `QgsProject`, map layers or GUI objects unsafely from background tasks.

## Atlas and Reports

Atlas/report support should build on the cartography commands first, then add coverage layers, batch exports and map-book style reports.

## Safety

Never expose the full token in reports, never bind outside `127.0.0.1`, and never turn Processing into an unrestricted command execution escape hatch.
