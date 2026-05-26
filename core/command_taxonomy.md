# SIGMAI Command Taxonomy

SIGMAI commands are grouped by intent, risk, and target QGIS subsystem.

Public name: SIGMAI.

## 1. System and Environment

Implemented now:

- `status`
- `get_capabilities`
- `get_qgis_environment`
- `get_bridge_config`
- `get_logs`
- `get_recent_errors`

Purpose: let agents understand the runtime before taking action.

## 2. QGIS Project

Implemented now:

- `get_project_info`
- `get_project_crs`
- `list_project_layers`

Planned:

- `set_project_crs`
- `save_project`
- `save_project_as`
- `generate_project_report`

## 3. Layers

Implemented now:

- `list_layers`
- `get_layer_info`
- `load_vector_layer`
- `export_layer`

Planned:

- `inspect_layer`
- `check_layer_validity`
- `get_layer_fields`
- `get_layer_extent`
- `get_layer_crs`
- `set_layer_crs`
- `rename_layer`
- `remove_layer`
- `load_raster_layer`

## 4. CRS and Data Quality

Implemented now:

- `diagnose_crs`
- `validate_geometries`
- `fix_geometries`

Planned:

- `detect_missing_crs`
- `detect_crs_mismatch`
- `suggest_project_crs`
- `reproject_to_project_crs`
- `detect_invalid_geometries`
- `generate_data_quality_report`

## 5. Processing Toolbox

Implemented now:

- `run_processing`

Allowlisted algorithms:

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

Planned:

- `list_processing_providers`
- `list_processing_algorithms`
- `get_processing_algorithm_info`
- `run_safe_processing`
- `get_processing_history`
- `validate_processing_params`

## 6. Vector Tools

Implemented now:

- `buffer`
- `clip`
- `dissolve`
- `reproject_layer`

Planned high-level commands:

- `intersection`
- `union`
- `difference`
- `spatial_join`
- `select_by_attribute`
- `select_by_location`
- `calculate_field`
- `create_centroids`
- `multipart_to_singleparts`

## 7. Raster Tools

Planned:

- `raster_info`
- `raster_reproject`
- `raster_clip`
- `raster_slope`
- `raster_aspect`
- `raster_hillshade`
- `raster_calculator`
- `raster_reclassify`
- `raster_polygonize`
- `raster_contours`

## 8. Symbology

Planned:

- `apply_single_symbol`
- `apply_categorized_style`
- `apply_graduated_style`
- `apply_raster_style`
- `set_layer_opacity`
- `set_layer_visibility`
- `save_qml_style`
- `load_qml_style`

## 9. Cartographic Layout

Implemented now:

- `list_layouts`
- `create_layout`
- `add_layout_map`
- `set_layout_extent`
- `add_layout_label`
- `add_layout_legend`
- `add_layout_scale_bar`
- `add_layout_north_arrow`
- `add_layout_grid`
- `add_layout_picture`
- `set_layer_style`
- `export_layout`
- `generate_basic_map`
- `evaluate_layout_cartographic_completeness`
- `generate_workflow_report`

Planned:

- `delete_layout`
- `set_layout_page_size`
- `move_layer_order`
- `generate_print_map`

## 10. Plugin Management

Implemented now:

- `list_installed_plugins`
- `inspect_plugin`
- `validate_metadata_txt`
- `check_plugin_structure`
- `check_plugin_imports`
- `check_plugin_resources`
- `check_plugin_icon`
- `check_plugin_runtime_status`
- `check_plugin_menu_actions`
- `check_plugin_toolbar_actions`
- `check_processing_provider_registration`
- `check_plugin_algorithm_registration`
- `collect_plugin_logs`
- `generate_plugin_report`
- `package_plugin_zip`
- `install_plugin_from_folder`
- `update_plugin_from_folder`
- `enable_plugin`
- `disable_plugin`
- `reload_plugin`
- `uninstall_plugin`

Planned:

- `create_plugin_skeleton`
- `run_plugin_unit_tests`
- `run_plugin_smoke_tests`
- `generate_plugin_publication_checklist`

## 11. Self Management

Implemented now:

- `self_inspect`
- `self_health_check`
- `self_backup`
- `self_validate_update`
- `self_stage_update`
- `self_apply_update`
- `self_restart_required`
- `self_rollback`
- `self_generate_report`

Purpose: update or repair the running SIGMAI plugin through staging, backup, confirmation, and restart-aware rollback.

## 12. Tests and Diagnostics

Implemented now:

- `get_recent_errors`

Planned:

- `run_health_check`
- `run_project_diagnostics`
- `run_plugin_diagnostics`
- `run_bridge_self_test`
- `run_manual_test_step`
- `generate_test_report`
- `generate_bug_report`
- `collect_environment_snapshot`

## 13. Composite Workflows

Planned:

- `plan_workflow`
- `dry_run_workflow`
- `execute_workflow`
- `get_workflow_status`
- `generate_workflow_report`
