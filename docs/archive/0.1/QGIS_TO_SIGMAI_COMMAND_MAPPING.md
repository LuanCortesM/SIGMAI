# QGIS to SIGMAI Command Mapping

## Project QGIS

| QGIS Function | API/Algorithm | SIGMAI Command | Permission | Dry-run | Status | Risks |
|---|---|---|---|---|---|---|
| Project info | `QgsProject.instance()` | `get_project_info` | `read_only` | no | implemented | none for read-only |
| Project CRS | `QgsProject.instance().crs()` | `get_project_crs` | `read_only` | no | implemented | none |
| Save project | `QgsProject.write()` | `save_project` | `project_write` | yes | planned | data/project mutation |

## Layers

| QGIS Function | API/Algorithm | SIGMAI Command | Permission | Dry-run | Status | Risks |
|---|---|---|---|---|---|---|
| List layers | `QgsProject.instance().mapLayers()` | `list_layers` | `read_only` | no | implemented | none |
| Layer info | `QgsMapLayer` methods | `get_layer_info` | `read_only` | no | implemented | feature count can be slow |
| Load vector | `QgsVectorLayer`, `QgsProject.addMapLayer` | `load_vector_layer` | `project_write` | yes | planned | invalid paths, project mutation |
| Remove layer | `QgsProject.removeMapLayer` | `remove_layer` | `project_write` | yes | planned | destructive project change |

## CRS

| QGIS Function | API/Algorithm | SIGMAI Command | Permission | Dry-run | Status | Risks |
|---|---|---|---|---|---|---|
| Get layer CRS | `layer.crs()` | `get_layer_crs` | `read_only` | no | planned | none |
| Diagnose CRS | `QgsCoordinateReferenceSystem` | `diagnose_crs` | `read_only` | no | planned | interpretation risk |
| Reproject | `native:reprojectlayer` | `reproject_layer` | `safe_write` | yes | planned | output overwrite, unit assumptions |

## Processing

| QGIS Function | API/Algorithm | SIGMAI Command | Permission | Dry-run | Status | Risks |
|---|---|---|---|---|---|---|
| Run generic algorithm | `processing.run` | `run_processing` | `safe_write` | yes | implemented | needs allowlist |
| List algorithms | `QgsApplication.processingRegistry()` | `list_processing_algorithms` | `read_only` | no | planned | provider availability |
| Algorithm info | `registry.algorithmById()` | `get_processing_algorithm_info` | `read_only` | no | planned | version differences |

## Vectors

| Function | API/Algorithm | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| Buffer | `native:buffer` | `buffer` | `safe_write` | yes | planned |
| Clip | `native:clip` | `clip` | `safe_write` | yes | planned |
| Dissolve | `native:dissolve` | `dissolve` | `safe_write` | yes | planned |
| Intersection | `native:intersection` | `intersection` | `safe_write` | yes | planned |
| Union | `native:union` | `union` | `safe_write` | yes | planned |
| Difference | `native:difference` | `difference` | `safe_write` | yes | planned |
| Fix geometries | `native:fixgeometries` | `fix_geometries` | `safe_write` | yes | planned |

## Raster

| Function | API/Algorithm | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| Raster info | `QgsRasterLayer` | `raster_info` | `read_only` | no | planned |
| Reproject raster | `gdal:warpreproject` | `raster_reproject` | `safe_write` | yes | planned, needs GDAL provider validation |
| Slope | GDAL/native provider candidate | `raster_slope` | `safe_write` | yes | planned, needs provider validation |

## Symbology

| Function | API | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| Single symbol | `QgsSingleSymbolRenderer` | `apply_single_symbol` | `safe_write` | yes | planned/disabled |
| Categorized | `QgsCategorizedSymbolRenderer` | `apply_categorized_style` | `safe_write` | yes | planned |
| Graduated | `QgsGraduatedSymbolRenderer` | `apply_graduated_style` | `safe_write` | yes | planned |

## Layout

| Function | API | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| List layouts | `layoutManager().layouts()` | `list_layouts` | `read_only` | no | implemented |
| Create layout | `QgsPrintLayout` | `create_layout` | `safe_write` | yes | implemented basic |
| Export layout | `QgsLayoutExporter` | `export_layout` | `safe_write` | yes | implemented |
| Add title | `QgsLayoutItemLabel` | `add_title` | `safe_write` | yes | planned |
| Add map | `QgsLayoutItemMap` | `add_map_item` | `safe_write` | yes | planned |
| Add legend | `QgsLayoutItemLegend` | `add_legend` | `safe_write` | yes | planned |
| Add scale bar | `QgsLayoutItemScaleBar` | `add_scale_bar` | `safe_write` | yes | planned |

## Plugins

| Function | API | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| List installed | plugin folders, `qgis.utils` | `list_installed_plugins` | `read_only` | no | implemented |
| Inspect plugin | filesystem + metadata | `inspect_plugin` | `read_only` | no | implemented |
| Validate metadata | `configparser` | `validate_metadata_txt` | `read_only` | no | implemented |
| Package plugin | `zipfile` | `package_plugin_zip` | `developer` | yes | planned |

## Logs

| Function | API | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| Bridge logs | JSONL file | `get_logs` | `read_only` | no | implemented |
| Recent errors | bridge log filter | `get_recent_errors` | `read_only` | no | implemented |
| QGIS logs | `QgsMessageLog` | `collect_qgis_logs` | `read_only` | no | planned |

## Tests and Export

| Function | API/Tool | SIGMAI Command | Permission | Dry-run | Status |
|---|---|---|---|---|---|
| Bridge self-test | internal registry | `run_bridge_self_test` | `read_only` | no | planned |
| Workflow report | command audit log | `generate_workflow_report` | `read_only` | no | planned |
| Export layer | Processing or writer API | `export_layer` | `safe_write` | yes | planned |
