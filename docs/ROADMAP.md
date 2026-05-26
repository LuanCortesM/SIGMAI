# SIGMAI Roadmap

Public name: SIGMAI - Secure GIS-AI Interface.

## Phase 1 - Protocol Foundation

Status: implemented and expanded.

- Structured command and response schemas.
- Command taxonomy.
- Capabilities.
- Permission levels.

## Phase 2 - QGIS Runtime

Status: implemented, with ongoing QGIS real-world validation.

- Local server.
- Token.
- Command registry.
- Basic QGIS actions.
- Logs.

## Phase 3 - Developer Mode

Status: basic plugin inspection implemented.

Next:

- static import checks;
- menu/toolbar action inspection;
- Processing provider diagnostics;
- plugin packaging;
- publication checklist.

## Phase 4 - User Cartography Mode

Status: basic layout listing/creation/export exists. High-level GIS commands for CRS, geometry quality and vector processing are implemented. Atomic cartographic commands are now present and need real QGIS validation after plugin update/reload.

Implemented:

- `diagnose_crs`
- `validate_geometries`
- `fix_geometries`
- `buffer`
- `clip`
- `dissolve`
- `reproject_layer`
- `export_layer`

Next:

- validate `generate_basic_map` in QGIS real environment;
- reject likely blank maps through `evaluate_layout_cartographic_completeness`;
- add layout grid/graticule;
- add layer ordering and feature highlighting;
- add categorized/graduated symbology and labels.

Status update:

- Level 5 cartographic map generation was validated with CRS-safe layout extents and 200/200 rendered maps.
- Level 6 vector/attribute/expression commands are implemented and validated after QGIS reload.
- Level 7 professional cartography is validated with professional map regression and public map authorship checks.
- Level 8 raster core and workflow foundation are validated through deep regressions.
- Level 9 job queue is validated as a safe foundation for read-only and dry-run background jobs; real long-running mutations still require future QgsTask-safe execution.
- Level 10 atlas/report foundation is validated with protected export blocks where full atlas/report rendering is not yet implemented.
- Level 11 data sources, OGC, GPS/GPX and database foundation is validated with local and protected runtime tests.
- Level 12 plugin orchestration foundation is validated with plugin inventory, adapter reports and allowlist-based blocking.
- Level 13 MCP formal foundation is validated with a tool manifest, token masking, read-only/dry-run wrappers and explicit blocking of dangerous plugin/self-management actions.
- Level 14 broad QGIS ecosystem coverage is implemented as roadmap governance, public release checklist and automatic maturity evaluation; it does not mean every QGIS subsystem is fully implemented.
- Public cartographic products now separate plugin authorship from generated map authorship.

## Phase 5 - Safe Processing Profiles

Next:

- list providers and algorithms;
- algorithm info;
- allowlists;
- vector and raster high-level commands.

Implemented in development tree:

- `list_processing_providers`
- `list_processing_algorithms`
- `get_processing_algorithm_info`
- `recommend_qgis_tool`
- `load_raster_layer`
- `raster_info`
- `raster_band_statistics`
- `raster_metadata_report`
- `raster_reproject`
- `raster_clip_by_extent`
- `raster_clip_by_mask`
- `raster_slope`
- `raster_aspect`
- `raster_hillshade`
- `raster_contours`
- `raster_polygonize`

Documentation-driven expansion targets from QGIS 3.44:

- selection commands;
- attribute table commands;
- QGIS expression validation/evaluation;
- layer tree ordering/visibility;
- raster information and terrain tools;
- atlas/report commands;
- job queue using QGIS task patterns;
- GPS/GPX commands;
- database/OGC data source commands;
- point cloud, mesh and 3D planning;
- QGIS Server readiness checks.

## Phase 6 - Workflow Engine

Next:

- dry-run workflows;
- execute workflows;
- progress and job ids;
- workflow reports.

## Phase 7 - VS Code Extension

Next:

- TypeScript extension scaffold;
- token manager;
- QGIS connection panel;
- plugin validation UI;
- command runner;
- logs panel.

## Phase 8 - Publication

Next:

- QGIS Plugin Repository readiness;
- Codex Plugin packaging;
- VS Code Marketplace;
- public docs.
## Phase 2.1 Completed: Atomic Cartography Foundation

Implemented in the development tree:

- `add_layout_map`
- `set_layout_extent`
- `add_layout_label`
- `add_layout_legend`
- `add_layout_scale_bar`
- `add_layout_north_arrow`
- `add_layout_grid`
- `add_layout_picture`
- `set_layer_style`
- `generate_basic_map`
- `generate_workflow_report`

Next cartography work:

- layer ordering;
- feature-level highlighting;
- categorized/graduated styling;
- map templates.

## Phase 2.2 Completed: CRS-Safe Cartographic Regression

Validated after restarting QGIS with the corrected SIGMAI plugin loaded:

- 30-map reduced regression: 30/30 rendered, 0 blank/bad.
- 200-map stress regression: 200/200 bridge OK, 200/200 rendered, 0 blank/bad.
- Automatic layouts now work with mixed `EPSG:4674` and `EPSG:31983` layers.
- `add_layout_map` and `set_layout_extent` use project-CRS transformed extents.
- PNG visual analysis is part of the cartographic acceptance path.

SIGMAI is now classified as `LEVEL 5 - Cartographic Map Generation Capable`.

Next refinements:

- metric scale bar strategy for geographic CRS projects;
- `legend_layers` / `linked_layer_ids` filtering;
- better north arrow/legend placement presets;
- scientific publication map templates.

## Phase 2.3 In Progress: Level 6 Foundation

This phase consolidates Level 5 and starts `LEVEL 6 - Vector Analysis and Attribute Capable`.

Implemented in the development tree and installed through self-management, pending QGIS/plugin restart for runtime validation:

- cartographic legend filtering and scale warnings;
- layer tree commands: `list_layer_tree`, `set_layer_visibility`, `move_layer_order`, `create_layer_group`, `move_layer_to_group`;
- attribute commands: `list_fields`, `sample_features`, `inspect_attribute_table`, `field_statistics`, `unique_values`;
- expression commands: `validate_expression`, `evaluate_expression`, `query_features`;
- selection commands: `select_by_expression`, `select_by_attribute`, `select_by_location`, `extract_by_expression`, `extract_by_attribute`, `extract_by_location`;
- vector analysis commands: `intersection`, `union`, `difference`, `centroids`, `multipart_to_singleparts`, `count_points_in_polygon`.

Validation target:

- keep 30/30 and 200/200 cartographic regressions with zero blank maps;
- pass `tools/run_sigmai_vector_attribute_regression.py` after SIGMAI is reloaded in QGIS.

## Phase 2.4 In Progress: Professional Cartography and QGIS Orchestration

Implemented in the development tree and applied to the installed plugin through self-management, pending QGIS/plugin restart:

- `list_layout_templates`;
- `generate_professional_map`;
- `evaluate_map_quality`;
- cartographic design helpers;
- `list_processing_providers`;
- `list_processing_algorithms`;
- `get_processing_algorithm_info`;
- `recommend_qgis_tool`;
- `list_qgis_plugins_extended`;
- safe plugin algorithm adapter stubs.

Regression runner:

- `tools/run_sigmai_professional_map_regression.py --limit 50`.

