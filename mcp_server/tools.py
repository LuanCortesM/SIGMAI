from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .session_discovery import resolve_connection
except ImportError:
    from session_discovery import resolve_connection

ROOT = Path(__file__).resolve().parents[1]

READ_ONLY_ACTIONS = {
    "status",
    "get_capabilities",
    "get_qgis_environment",
    "get_bridge_config",
    "get_logs",
    "get_recent_errors",
    "get_project_info",
    "get_project_crs",
    "list_project_layers",
    "list_layers",
    "get_layer_info",
    "list_layouts",
    "list_layout_templates",
    "evaluate_layout_cartographic_completeness",
    "evaluate_map_quality",
    "choose_style_profile",
    "validate_map_readability",
    "detect_visual_collisions",
    "suggest_layout_improvements",
    "diagnose_crs",
    "validate_geometries",
    "list_fields",
    "sample_features",
    "inspect_attribute_table",
    "field_statistics",
    "unique_values",
    "validate_expression",
    "evaluate_expression",
    "query_features",
    "inspect_layer_style",
    "list_layer_tree",
    "list_processing_providers",
    "list_processing_algorithms",
    "get_processing_algorithm_info",
    "recommend_qgis_tool",
    "list_qgis_plugins_extended",
    "inspect_plugin_capabilities",
    "list_plugin_processing_algorithms",
    "get_plugin_algorithm_info",
    "build_plugin_capability_manifest",
    "dry_run_plugin_algorithm_generic",
    "generate_plugin_adapter_report",
    "search_qgis_plugin_repository",
    "inspect_qgis_plugin_zip",
    "inspect_plugin",
    "validate_metadata_txt",
    "list_installed_plugins",
    "self_inspect",
    "self_health_check",
    "self_restart_required",
    "list_jobs",
    "get_job_status",
    "get_job_result",
    "job_logs",
    "list_workflow_templates",
    "dry_run_workflow",
    "list_ogc_connections",
    "inspect_ogc_service",
    "validate_service_url",
    "test_service_connection",
    "inspect_data_source",
    "broken_data_source_report",
    "list_gpx_layers",
    "summarize_gpx_track",
    "gpx_track_length",
    "gpx_track_extent",
    "list_database_connections",
    "inspect_database_connection",
}

DRY_RUN_ACTIONS = {
    "generate_basic_map",
    "generate_professional_map",
    "generate_workflow_report",
    "create_layout",
    "add_layout_map",
    "set_layout_extent",
    "add_layout_label",
    "add_layout_legend",
    "add_layout_scale_bar",
    "add_layout_north_arrow",
    "add_layout_grid",
    "add_layout_picture",
    "set_layer_style",
    "apply_single_symbol",
    "apply_categorized_style",
    "apply_graduated_style",
    "create_labels",
    "create_labels_from_expression",
    "enable_labels",
    "disable_labels",
    "set_layer_visibility",
    "move_layer_order",
    "create_layer_group",
    "move_layer_to_group",
    "select_by_expression",
    "select_by_attribute",
    "select_by_location",
    "extract_by_expression",
    "extract_by_attribute",
    "extract_by_location",
    "buffer",
    "clip",
    "dissolve",
    "reproject_layer",
    "fix_geometries",
    "intersection",
    "union",
    "difference",
    "centroids",
    "multipart_to_singleparts",
    "count_points_in_polygon",
    "run_processing",
    "run_plugin_algorithm_safe",
    "run_plugin_algorithm_generic_safe",
    "load_vector_layer",
    "load_raster_layer",
    "load_gpx",
    "load_wms_layer",
    "load_wfs_layer",
    "load_xyz_tile_layer",
    "load_arcgis_rest_layer",
    "load_postgis_layer",
    "repair_data_source_path",
    "raster_hillshade",
    "raster_slope",
    "raster_aspect",
    "raster_contours",
    "raster_reproject",
    "raster_clip_by_extent",
    "raster_clip_by_mask",
    "raster_polygonize",
    "plan_workflow",
    "execute_workflow",
    "save_workflow_template",
    "run_workflow_template",
    "start_job",
    "run_processing_job",
    "run_workflow_job",
    "run_raster_job",
    "run_map_export_job",
    "create_atlas",
    "configure_atlas_coverage_layer",
    "set_atlas_filter_expression",
    "set_atlas_sort_expression",
    "export_atlas_pdf",
    "export_atlas_images",
    "create_report",
    "add_report_section",
    "export_report_html",
    "export_report_pdf",
    "generate_analysis_report",
    "generate_workflow_report_pdf",
}

BLOCKED_MCP_ACTIONS = {
    "self_apply_update",
    "self_stage_update",
    "self_rollback",
    "install_plugin_from_folder",
    "update_plugin_from_folder",
    "uninstall_plugin",
    "enable_plugin",
    "disable_plugin",
    "reload_plugin",
    "download_qgis_plugin_zip",
    "install_plugin_from_zip",
    "install_qgis_plugin_from_repository",
}


def _masked_connection() -> dict[str, Any]:
    connection = resolve_connection()
    token = connection.get("token") or ""
    return {
        "host": connection.get("host"),
        "port": connection.get("port"),
        "session_path": connection.get("session_path", ""),
        "has_token": bool(token),
        "token_masked": f"{token[:4]}...{token[-4:]}" if len(token) >= 8 else "***" if token else "",
    }


def bridge_call(action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    connection = resolve_connection()
    if not connection["token"]:
        return {"ok": False, "error": "No SIGMAI session found."}
    if connection.get("host") not in ("127.0.0.1", "localhost", "::1"):
        return {"ok": False, "error": "MCP refuses non-local SIGMAI hosts."}
    payload = {"schema_version": "0.3", "action": action, "params": params or {}, "dry_run": bool(dry_run)}
    request = urllib.request.Request(
        f"http://{connection['host']}:{connection['port']}/command",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {connection['token']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _action_params(arguments: dict[str, Any] | None) -> dict[str, Any]:
    arguments = arguments or {}
    params = arguments.get("params")
    if isinstance(params, dict):
        return params
    return {k: v for k, v in arguments.items() if k not in {"action", "dry_run", "params"}}


def sigmai_tool_manifest(arguments=None) -> dict[str, Any]:
    return {
        "ok": True,
        "server": "SIGMAI MCP local JSON-lines wrapper",
        "security": {
            "local_only": True,
            "uses_session_discovery": True,
            "token_exposed_to_model": False,
            "bridge_still_enforces_permissions": True,
            "dangerous_actions_blocked_by_mcp": sorted(BLOCKED_MCP_ACTIONS),
        },
        "connection": _masked_connection(),
        "tools": [
            {
                "name": name,
                "description": spec["description"],
                "action": spec.get("action"),
                "mode": spec.get("mode", "direct"),
            }
            for name, spec in TOOL_SPECS.items()
        ],
    }


def sigmai_health(arguments=None) -> dict[str, Any]:
    status = bridge_call("status")
    health = bridge_call("self_health_check")
    return {
        "ok": bool(status.get("ok")) and bool(health.get("ok")),
        "connection": _masked_connection(),
        "status": status,
        "self_health_check": health,
    }


def sigmai_command(arguments=None) -> dict[str, Any]:
    arguments = arguments or {}
    action = str(arguments.get("action", "")).strip()
    if not action:
        return {"ok": False, "error": "Missing action."}
    if action in BLOCKED_MCP_ACTIONS:
        return {
            "ok": False,
            "error": "MCP_BLOCKED_ACTION",
            "action": action,
            "message": "This action must be run through the SIGMAI CLI/UI with explicit confirmation.",
        }
    params = _action_params(arguments)
    dry_run_requested = bool(arguments.get("dry_run", False))
    if action in READ_ONLY_ACTIONS:
        return bridge_call(action, params, dry_run=False)
    if action in DRY_RUN_ACTIONS:
        return bridge_call(action, params, dry_run=True if not dry_run_requested else dry_run_requested)
    return {
        "ok": False,
        "error": "MCP_ACTION_NOT_ALLOWLISTED",
        "action": action,
        "message": "Add a dedicated MCP wrapper or allowlist entry before exposing this action to AI clients.",
    }


def sigmai_status(arguments=None): return bridge_call("status")
def sigmai_get_capabilities(arguments=None): return bridge_call("get_capabilities")
def sigmai_get_qgis_environment(arguments=None): return bridge_call("get_qgis_environment")
def sigmai_list_layers(arguments=None): return bridge_call("list_layers")
def sigmai_get_layer_info(arguments): return bridge_call("get_layer_info", {"layer_id": arguments.get("layer_id", "")})
def sigmai_load_vector_layer(arguments): return bridge_call("load_vector_layer", arguments or {}, dry_run=True)
def sigmai_list_layouts(arguments=None): return bridge_call("list_layouts")
def sigmai_inspect_plugin(arguments): return bridge_call("inspect_plugin", {"plugin_name": arguments.get("plugin_name", "sigmai")})
def sigmai_validate_metadata(arguments): return bridge_call("validate_metadata_txt", {"plugin_name": arguments.get("plugin_name", "sigmai")})


def sigmai_list_layers(arguments=None): return bridge_call("list_layers")
def sigmai_generate_basic_map_dry_run(arguments=None): return bridge_call("generate_basic_map", _action_params(arguments), dry_run=True)
def sigmai_generate_professional_map_dry_run(arguments=None): return bridge_call("generate_professional_map", _action_params(arguments), dry_run=True)
def sigmai_plan_workflow(arguments=None): return bridge_call("plan_workflow", _action_params(arguments), dry_run=True)
def sigmai_dry_run_workflow(arguments=None): return bridge_call("dry_run_workflow", _action_params(arguments))
def sigmai_plugin_inventory(arguments=None): return bridge_call("list_qgis_plugins_extended", _action_params(arguments))
def sigmai_search_qgis_plugin_repository(arguments=None): return bridge_call("search_qgis_plugin_repository", _action_params(arguments))
def sigmai_processing_providers(arguments=None): return bridge_call("list_processing_providers", _action_params(arguments))
def sigmai_processing_algorithms(arguments=None): return bridge_call("list_processing_algorithms", _action_params(arguments))


TOOL_SPECS = {
    "sigmai_tool_manifest": {
        "description": "Return the local SIGMAI MCP tool manifest without exposing the bearer token.",
        "mode": "local",
    },
    "sigmai_health": {
        "description": "Check SIGMAI Bridge status and self health through local session discovery.",
        "mode": "read_only",
    },
    "sigmai_command": {
        "description": "Controlled command proxy for read-only and dry-run SIGMAI actions.",
        "mode": "allowlisted_proxy",
    },
    "sigmai_status": {"description": "Get SIGMAI Bridge status.", "action": "status", "mode": "read_only"},
    "sigmai_get_capabilities": {"description": "Get SIGMAI capabilities.", "action": "get_capabilities", "mode": "read_only"},
    "sigmai_get_qgis_environment": {"description": "Get QGIS environment details.", "action": "get_qgis_environment", "mode": "read_only"},
    "sigmai_list_layers": {"description": "List QGIS project layers.", "action": "list_layers", "mode": "read_only"},
    "sigmai_get_layer_info": {"description": "Inspect one QGIS layer by id.", "action": "get_layer_info", "mode": "read_only"},
    "sigmai_list_layouts": {"description": "List QGIS layouts.", "action": "list_layouts", "mode": "read_only"},
    "sigmai_generate_basic_map_dry_run": {"description": "Dry-run a basic map generation request.", "action": "generate_basic_map", "mode": "dry_run"},
    "sigmai_generate_professional_map_dry_run": {"description": "Dry-run a professional map generation request.", "action": "generate_professional_map", "mode": "dry_run"},
    "sigmai_plan_workflow": {"description": "Plan a workflow without mutating project data.", "action": "plan_workflow", "mode": "dry_run"},
    "sigmai_dry_run_workflow": {"description": "Validate/dry-run a SIGMAI workflow.", "action": "dry_run_workflow", "mode": "read_only"},
    "sigmai_plugin_inventory": {"description": "List installed QGIS plugins and safe orchestration metadata.", "action": "list_qgis_plugins_extended", "mode": "read_only"},
    "sigmai_search_qgis_plugin_repository": {"description": "Search the official QGIS plugin repository. Requires confirm_network=true in the arguments.", "action": "search_qgis_plugin_repository", "mode": "read_only"},
    "sigmai_processing_providers": {"description": "List QGIS Processing providers.", "action": "list_processing_providers", "mode": "read_only"},
    "sigmai_processing_algorithms": {"description": "List QGIS Processing algorithms through SIGMAI.", "action": "list_processing_algorithms", "mode": "read_only"},
    "sigmai_inspect_plugin": {"description": "Inspect a QGIS plugin by package name.", "action": "inspect_plugin", "mode": "read_only"},
    "sigmai_validate_metadata": {"description": "Validate a QGIS plugin metadata.txt file.", "action": "validate_metadata_txt", "mode": "read_only"},
}


TOOLS = {
    "sigmai_tool_manifest": sigmai_tool_manifest,
    "sigmai_health": sigmai_health,
    "sigmai_command": sigmai_command,
    "sigmai_status": sigmai_status,
    "sigmai_get_capabilities": sigmai_get_capabilities,
    "sigmai_get_qgis_environment": sigmai_get_qgis_environment,
    "sigmai_list_layers": sigmai_list_layers,
    "sigmai_get_layer_info": sigmai_get_layer_info,
    "sigmai_list_layouts": sigmai_list_layouts,
    "sigmai_generate_basic_map_dry_run": sigmai_generate_basic_map_dry_run,
    "sigmai_generate_professional_map_dry_run": sigmai_generate_professional_map_dry_run,
    "sigmai_plan_workflow": sigmai_plan_workflow,
    "sigmai_dry_run_workflow": sigmai_dry_run_workflow,
    "sigmai_plugin_inventory": sigmai_plugin_inventory,
    "sigmai_search_qgis_plugin_repository": sigmai_search_qgis_plugin_repository,
    "sigmai_processing_providers": sigmai_processing_providers,
    "sigmai_processing_algorithms": sigmai_processing_algorithms,
    "sigmai_inspect_plugin": sigmai_inspect_plugin,
    "sigmai_validate_metadata": sigmai_validate_metadata,
    "sigmai_status": sigmai_status,
    "sigmai_get_capabilities": sigmai_get_capabilities,
    "sigmai_get_qgis_environment": sigmai_get_qgis_environment,
    "sigmai_list_layers": sigmai_list_layers,
    "sigmai_get_layer_info": sigmai_get_layer_info,
    "sigmai_load_vector_layer": sigmai_load_vector_layer,
    "sigmai_list_layouts": sigmai_list_layouts,
    "sigmai_inspect_plugin": sigmai_inspect_plugin,
    "sigmai_validate_metadata": sigmai_validate_metadata,
}
