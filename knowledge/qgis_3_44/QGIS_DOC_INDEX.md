# QGIS 3.44 Documentation Index for SIGMAI

Source documentation copied locally to `local QGIS documentation mirror/qgis_3_44/` and ignored by Git. This index summarizes only the files relevant to SIGMAI.

| QGIS doc file | Topic | Relevance to SIGMAI | Related SIGMAI commands | Observations |
|---|---|---|---|---|
| `docs/pyqgis_developer_cookbook/composer.html` / `_sources/.../composer.rst.txt` | Map rendering and printing, layout API | Critical | `create_layout`, `add_layout_map`, `set_layout_extent`, `add_layout_label`, `add_layout_legend`, `add_layout_scale_bar`, `add_layout_north_arrow`, `export_layout`, `generate_basic_map` | Shows `QgsPrintLayout`, `QgsLayoutItemMap`, `QgsLayoutItemLabel`, `QgsLayoutItemLegend`, `QgsLayoutItemScaleBar`, `QgsLayoutExporter`; map items need position, size and extent before export. |
| `docs/user_manual/print_layout/overview_layout.html` | Print layout overview | Critical | all layout commands | User-facing layout concepts: page, items, map body, legend, labels, scale bars, output. |
| `docs/user_manual/print_layout/layout_items/layout_map.html` | Layout map item | Critical | `add_layout_map`, `set_layout_extent` | Relevant for avoiding blank maps: layer set, map extent, item size, map frame, map rendering. |
| `docs/user_manual/print_layout/layout_items/layout_label.html` | Layout labels | High | `add_layout_label` | Title, subtitle, credits, CRS/source notes. |
| `docs/user_manual/print_layout/layout_items/layout_legend.html` | Layout legend | High | `add_layout_legend` | Legend should be linked to a map item when possible. |
| `docs/user_manual/print_layout/layout_items/layout_scale_bar.html` | Scale bar | High | `add_layout_scale_bar` | Scale depends on map CRS/units; warn for geographic CRS. |
| `docs/user_manual/print_layout/layout_items/layout_image.html` | Images/pictures | Medium | `add_layout_north_arrow` | North arrow can use picture/SVG; SIGMAI currently has textual fallback. |
| `docs/user_manual/print_layout/create_output.html` | Layout export | Critical | `export_layout`, `generate_basic_map` | PDF/image export must be validated for non-empty output. |
| `docs/pyqgis_developer_cookbook/vector.html` | Vector layers, renderers, symbols | Critical | `set_layer_style`, `apply_single_symbol`, `apply_categorized_style`, `apply_graduated_style` | Documents renderer types and `QgsSingleSymbolRenderer`, `QgsCategorizedSymbolRenderer`, `QgsGraduatedSymbolRenderer`. |
| `docs/user_manual/style_library/symbol_selector.html` | Symbol styling concepts | High | style commands | Useful for style parameters exposed to AI clients. |
| `docs/user_manual/working_with_vector/vector_properties.html` | Vector properties | High | `get_layer_info`, style commands | Layer CRS, fields, symbology, source metadata. |
| `docs/pyqgis_developer_cookbook/processing.html` | Processing plugin/provider | High | plugin management, provider checks | Shows `hasProcessingProvider=yes`, `QgsApplication.processingRegistry().addProvider/removeProvider`. |
| `docs/user_manual/processing/console.html` | Running Processing from Python | Critical | `run_processing`, high-level vector/raster commands | Shows `processing.run`, `processing.runAndLoadResults`, `algorithmHelp`, parameter types and output behavior. |
| `docs/user_manual/processing_algs/qgis/vectorgeometry.html` | Native vector geometry algorithms | Critical | `buffer`, `fix_geometries`, `reproject_layer`, future geometry tools | Algorithm docs for geometry transformations. |
| `docs/user_manual/processing_algs/qgis/vectoroverlay.html` | Native overlay algorithms | Critical | `clip`, `intersection`, `union`, `difference` | Needed for allowlist and safe parameter mapping. |
| `docs/user_manual/processing_algs/qgis/vectorgeneral.html` | General vector algorithms | High | `export_layer`, `reproject_layer`, layer tools | General conversions and manipulation. |
| `docs/user_manual/processing_algs/qgis/fixgeometry.html` | Geometry check/fix | High | `validate_geometries`, `fix_geometries` | QGIS-native geometry validation should be preferred for deep full-dataset checks. |
| `docs/user_manual/processing_algs/qgis/rasterterrainanalysis.html` | Raster terrain algorithms | High | future `raster_slope`, `raster_hillshade`, `raster_aspect` | Basis for raster analysis allowlist. |
| `docs/user_manual/processing_algs/gdal/rasteranalysis.html` | GDAL raster analysis | High | future raster commands | Raster calculator and terrain-like GDAL tools. |
| `docs/user_manual/processing_algs/gdal/rasterprojections.html` | GDAL raster reprojection | High | future `raster_reproject` | Reprojection/warp commands require strict output validation. |
| `docs/user_manual/processing_algs/gdal/rasterextraction.html` | GDAL raster clip/extract | High | future `raster_clip` | Clip by extent/mask layer. |
| `docs/user_manual/working_with_projections/working_with_projections.html` | CRS/projections | Critical | `diagnose_crs`, `reproject_layer`, layout scale warnings | Needed to distinguish geographic vs projected CRS for metric operations. |
| `docs/pyqgis_developer_cookbook/crs.html` | PyQGIS CRS API | Critical | `diagnose_crs`, `reproject_layer`, `set_layout_extent` | CRS creation, validation, transforms. |
| `docs/pyqgis_developer_cookbook/geometry.html` | Geometry API | High | `validate_geometries`, future geometry diagnostics | Use cautiously; deep geometry validation can block QGIS. |
| `docs/pyqgis_developer_cookbook/raster.html` | Raster layer API | High | future raster commands | Raster metadata, renderer, providers. |
| `docs/pyqgis_developer_cookbook/plugins/plugins.html` | Plugin structure | Critical | `inspect_plugin`, `validate_metadata_txt`, `package_plugin_zip` | QGIS plugin lifecycle, metadata and loading patterns. |
| `docs/pyqgis_developer_cookbook/plugins/releasing.html` | Plugin releasing | High | `package_plugin_zip`, publication checklist | Relevant to package validation. |
| `docs/pyqgis_developer_cookbook/settings.html` | QgsSettings | Medium | auto-start/session settings | Use `QgsSettings.value/setValue` for plugin preferences. |
| `docs/pyqgis_developer_cookbook/tasks.html` | QgsTask/background work | High | future job queue | Long operations should use tasks/feedback; avoid blocking QGIS main thread. |
| `docs/pyqgis_developer_cookbook/communicating.html` | Logs/messages/progress | Medium | logs/audit | Useful for QGIS message log integration and user feedback. |

