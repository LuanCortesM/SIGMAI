# Test Plan With Shapes

Test data folder:

```text
%SIGMAI_TEST_DATA_DIR%
```

Detected datasets:

- `Estados/BR_UF_2025.shp` - complete polygon shapefile with `.prj`
- `Municipios/SP_Municipios_2025.shp` - complete polygon shapefile with `.prj`
- `Pais/BR_Pais_2025.shp` - complete polygon shapefile with `.prj`
- Four `.tif` rasters
- Two `.gpx` files
- One `.kml` file

Outputs must be written to:

```text
sigmai/test_outputs/
```

Do not modify original test files.

## 1. list_layers

- Objective: confirm loaded test layers are visible to the bridge.
- Input layer: load `Estados`, `Municipios`, and `Pais` in QGIS.
- Command: `list_layers`
- Expected result: layers returned with id, name, type, CRS, validity.
- Validation: compare QGIS Layers panel with bridge JSON.

## 2. get_layer_info

- Objective: inspect one real layer.
- Suggested layer: `SP_Municipios_2025`.
- Command: `get_layer_info`
- Params: `{ "layer_id": "ID_FROM_LIST_LAYERS" }`
- Expected result: polygon type, CRS, extent, fields, valid=true.
- Validation: compare with QGIS Layer Properties.

## 3. diagnose_crs

- Status: planned command.
- Objective: detect project/layer CRS mismatches.
- Suggested layers: all shapefiles.
- Expected result: all three shapefiles have `.prj`; CRS should be detected inside QGIS.
- Validation: compare with QGIS Layer Properties > Source CRS.

## 4. validate_geometries

- Status: planned command.
- Suggested layer: `SP_Municipios_2025`.
- Expected Processing candidate: `native:checkvalidity` or direct PyQGIS geometry scan.
- Output: `test_outputs/municipios_validity.gpkg`
- Validation: inspect invalid count and output layers.

## 5. fix_geometries

- Status: planned command.
- Processing algorithm: `native:fixgeometries`
- Input: `SP_Municipios_2025`
- Output: `test_outputs/municipios_fixed.gpkg`
- Expected result: valid output layer.
- Requires: `safe_write`, dry-run first.

## 6. buffer

- Status: planned high-level command, available through `run_processing` today.
- Processing algorithm: `native:buffer`
- Input: `SP_Municipios_2025` or selected municipality layer.
- Params: distance, segments, dissolve, temporary output or GPKG.
- Output: `test_outputs/municipios_buffer.gpkg`
- Validation: output polygon layer exists and has expected extent expansion.

## 7. clip

- Status: planned high-level command.
- Processing algorithm: `native:clip`
- Input: `Municipios`
- Overlay: `Estados` or `Pais`
- Output: `test_outputs/municipios_clip.gpkg`
- Validation: feature count and extent are within overlay.

## 8. dissolve

- Status: planned high-level command.
- Processing algorithm: `native:dissolve`
- Input: `SP_Municipios_2025`
- Field: choose a real field after `get_layer_info`.
- Output: `test_outputs/municipios_dissolve.gpkg`
- Validation: output feature count is lower or equal.

## 9. reproject_layer

- Status: planned high-level command.
- Processing algorithm: `native:reprojectlayer`
- Input: `SP_Municipios_2025`
- Target CRS: `EPSG:3857` for testing only.
- Output: `test_outputs/municipios_3857.gpkg`
- Validation: output CRS is EPSG:3857.

## 10. export_layer

- Status: planned command.
- Input: `Estados`
- Output: `test_outputs/estados_export.gpkg`
- Validation: output loads in QGIS and preserves attributes.

## 11. apply_single_symbol

- Status: planned and currently disabled in capabilities.
- Input: `Pais`
- Expected command: `apply_single_symbol`
- Validation: layer renderer changes in QGIS.

## 12. apply_categorized_style

- Status: planned.
- Input: `Estados`
- Field: choose real categorical field after inspection.
- Validation: categories appear in layer symbology.

## 13. create_layout

- Status: implemented basic command.
- Command: `create_layout`
- Params: `{ "layout_name": "SIGMAI_Test_Map" }`
- First run: `dry_run: true`
- Expected result: dry-run says layout would be created; real run creates layout.

## 14. generate_basic_map

- Status: planned workflow.
- Input: `Pais`, `Estados`, `Municipios`
- Expected steps: list layers, inspect CRS, style layers, create layout, add map item, legend, scale bar, north arrow, export.

## 15. export_layout

- Status: implemented.
- Input: existing layout.
- Output: `test_outputs/sigmai_test_map.pdf`
- Requires: no overwrite unless `confirm_overwrite: true`.
- Validation: PDF exists and opens.

## 16. generate_workflow_report

- Status: planned.
- Expected content: commands run, request ids, inputs, outputs, CRS checks, warnings, errors.

