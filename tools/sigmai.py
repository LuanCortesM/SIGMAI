from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from session_discovery import resolve_connection


ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str) -> str:
    if not value or value == "TEMPORARY_OUTPUT":
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return str(path.resolve())


def bridge_command(action: str, params: dict[str, Any] | None = None, pairing_code: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    connection = resolve_connection(pairing_code=pairing_code)
    if not connection["token"]:
        raise RuntimeError("No SIGMAI session found. Start QGIS Bridge or pass a pairing code.")
    payload = {"schema_version": "0.3", "action": action, "params": params or {}, "dry_run": dry_run}
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
    except urllib.error.URLError as exc:
        return {
            "schema_version": "0.2",
            "ok": False,
            "action": action,
            "data": None,
            "warnings": [],
            "errors": [
                {
                    "code": "BRIDGE_UNAVAILABLE",
                    "message": "Could not connect to SIGMAI Bridge. Open QGIS and start SIGMAI before running this command.",
                    "details": {"reason": str(exc.reason) if hasattr(exc, "reason") else str(exc)},
                }
            ],
        }


def print_json(data: Any) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    return 0 if not isinstance(data, dict) or data.get("ok", True) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SIGMAI simple CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    connect = sub.add_parser("connect")
    connect.add_argument("pairing_code")
    sub.add_parser("status")
    sub.add_parser("capabilities")
    sub.add_parser("layers")
    sub.add_parser("qgis-info")
    sub.add_parser("diagnose-crs")
    sub.add_parser("plugins")
    sub.add_parser("test")
    sub.add_parser("open-qgis")
    sub.add_parser("install-plugin")
    inspect_plugin = sub.add_parser("inspect-plugin")
    inspect_plugin.add_argument("plugin_name")
    plugin_structure = sub.add_parser("plugin-structure")
    plugin_structure.add_argument("plugin_name")
    plugin_imports = sub.add_parser("plugin-imports")
    plugin_imports.add_argument("plugin_name")
    plugin_resources = sub.add_parser("plugin-resources")
    plugin_resources.add_argument("plugin_name")
    plugin_icon = sub.add_parser("plugin-icon")
    plugin_icon.add_argument("plugin_name")
    plugin_report = sub.add_parser("plugin-report")
    plugin_report.add_argument("plugin_name")
    plugin_report.add_argument("--output-path", default="")
    package_plugin = sub.add_parser("package-plugin")
    package_plugin.add_argument("plugin_name")
    package_plugin.add_argument("output_path")
    package_plugin.add_argument("--confirm-overwrite", action="store_true")
    package_plugin.add_argument("--dry-run", action="store_true")
    plugin_repo_search = sub.add_parser("plugin-repo-search")
    plugin_repo_search.add_argument("query", nargs="?", default="")
    plugin_repo_search.add_argument("--qgis-version", default="")
    plugin_repo_search.add_argument("--limit", type=int, default=20)
    plugin_repo_search.add_argument("--confirm-network", action="store_true")
    plugin_repo_download = sub.add_parser("plugin-repo-download")
    plugin_repo_download.add_argument("plugin_name")
    plugin_repo_download.add_argument("output_path")
    plugin_repo_download.add_argument("--qgis-version", default="")
    plugin_repo_download.add_argument("--confirm-network", action="store_true")
    plugin_repo_download.add_argument("--confirm", action="store_true")
    plugin_repo_download.add_argument("--confirm-overwrite", action="store_true")
    plugin_repo_download.add_argument("--dry-run", action="store_true")
    inspect_plugin_zip = sub.add_parser("inspect-plugin-zip")
    inspect_plugin_zip.add_argument("zip_path")
    install_plugin_zip = sub.add_parser("install-plugin-zip")
    install_plugin_zip.add_argument("zip_path")
    install_plugin_zip.add_argument("--plugin-name", default="")
    install_plugin_zip.add_argument("--confirm", action="store_true")
    install_plugin_zip.add_argument("--update", action="store_true")
    install_plugin_zip.add_argument("--dry-run", action="store_true")
    install_plugin_repo = sub.add_parser("install-plugin-repository")
    install_plugin_repo.add_argument("plugin_name")
    install_plugin_repo.add_argument("--qgis-version", default="")
    install_plugin_repo.add_argument("--confirm-network", action="store_true")
    install_plugin_repo.add_argument("--confirm", action="store_true")
    install_plugin_repo.add_argument("--update", action="store_true")
    install_plugin_repo.add_argument("--dry-run", action="store_true")
    validate_geometries = sub.add_parser("validate-geometries")
    validate_geometries.add_argument("layer_id")
    validate_geometries.add_argument("--max-features", type=int, default=10000)
    fix_geometries = sub.add_parser("fix-geometries")
    fix_geometries.add_argument("layer_id")
    fix_geometries.add_argument("--output", default="TEMPORARY_OUTPUT")
    fix_geometries.add_argument("--dry-run", action="store_true")
    buffer_cmd = sub.add_parser("buffer")
    buffer_cmd.add_argument("layer_id")
    buffer_cmd.add_argument("--distance", type=float, required=True)
    buffer_cmd.add_argument("--segments", type=int, default=8)
    buffer_cmd.add_argument("--dissolve", action="store_true")
    buffer_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    buffer_cmd.add_argument("--dry-run", action="store_true")
    clip_cmd = sub.add_parser("clip")
    clip_cmd.add_argument("input_layer_id")
    clip_cmd.add_argument("overlay_layer_id")
    clip_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    clip_cmd.add_argument("--dry-run", action="store_true")
    dissolve_cmd = sub.add_parser("dissolve")
    dissolve_cmd.add_argument("layer_id")
    dissolve_cmd.add_argument("--field", action="append", default=[])
    dissolve_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    dissolve_cmd.add_argument("--dry-run", action="store_true")
    reproject = sub.add_parser("reproject-layer")
    reproject.add_argument("layer_id")
    reproject.add_argument("--target-crs", required=True)
    reproject.add_argument("--output", default="TEMPORARY_OUTPUT")
    reproject.add_argument("--dry-run", action="store_true")
    export_layer = sub.add_parser("export-layer")
    export_layer.add_argument("layer_id")
    export_layer.add_argument("output_path")
    export_layer.add_argument("--format", default="GPKG")
    export_layer.add_argument("--confirm-overwrite", action="store_true")
    export_layer.add_argument("--dry-run", action="store_true")
    add_map = sub.add_parser("add-layout-map")
    add_map.add_argument("--layout", required=True)
    add_map.add_argument("--layer-id", required=True)
    add_map.add_argument("--item-id", default="main_map")
    add_map.add_argument("--dry-run", action="store_true")
    extent = sub.add_parser("set-layout-extent")
    extent.add_argument("--layout", required=True)
    extent.add_argument("--map-item", default="main_map")
    extent.add_argument("--layer-id", default="")
    extent.add_argument("--margin-percent", type=float, default=5)
    extent.add_argument("--dry-run", action="store_true")
    label = sub.add_parser("add-layout-label")
    label.add_argument("--layout", required=True)
    label.add_argument("--text", required=True)
    label.add_argument("--item-id", default="label")
    label.add_argument("--dry-run", action="store_true")
    legend = sub.add_parser("add-layout-legend")
    legend.add_argument("--layout", required=True)
    legend.add_argument("--map-item", default="main_map")
    legend.add_argument("--layer-id", action="append", default=[])
    legend.add_argument("--dry-run", action="store_true")
    scale = sub.add_parser("add-layout-scale-bar")
    scale.add_argument("--layout", required=True)
    scale.add_argument("--map-item", default="main_map")
    scale.add_argument("--dry-run", action="store_true")
    north = sub.add_parser("add-layout-north-arrow")
    north.add_argument("--layout", required=True)
    north.add_argument("--dry-run", action="store_true")
    grid = sub.add_parser("add-layout-grid")
    grid.add_argument("--layout", required=True)
    grid.add_argument("--map-item", default="main_map")
    grid.add_argument("--interval-x", type=float, default=None)
    grid.add_argument("--interval-y", type=float, default=None)
    grid.add_argument("--dry-run", action="store_true")
    picture = sub.add_parser("add-layout-picture")
    picture.add_argument("--layout", required=True)
    picture.add_argument("--path", required=True)
    picture.add_argument("--item-id", default="picture")
    picture.add_argument("--dry-run", action="store_true")
    style = sub.add_parser("set-layer-style")
    style.add_argument("--layer-id", required=True)
    style.add_argument("--fill-color", default="#D8E1E8")
    style.add_argument("--stroke-color", default="#075D68")
    style.add_argument("--stroke-width", type=float, default=0.4)
    style.add_argument("--opacity", type=float, default=0.85)
    style.add_argument("--dry-run", action="store_true")
    basic_map = sub.add_parser("basic-map")
    basic_map.add_argument("--layer-id", required=True)
    basic_map.add_argument("--title", default="SIGMAI Test Map")
    basic_map.add_argument("--output", required=True)
    basic_map.add_argument("--format", default="pdf")
    basic_map.add_argument("--include-grid", action="store_true")
    basic_map.add_argument("--logo-path", default="")
    basic_map.add_argument("--legend-layer", action="append", default=[])
    basic_map.add_argument("--layout-template", default="basic")
    basic_map.add_argument("--map-author", default="")
    basic_map.add_argument("--organization", default="")
    basic_map.add_argument("--data-source", default="")
    basic_map.add_argument("--confirm-overwrite", action="store_true")
    basic_map.add_argument("--dry-run", action="store_true")
    sub.add_parser("layout-templates")
    professional_map = sub.add_parser("professional-map")
    professional_map.add_argument("--layer-id", required=True)
    professional_map.add_argument("--title", default="SIGMAI Professional Map")
    professional_map.add_argument("--subtitle", default="SIGMAI - Secure GIS-AI Interface")
    professional_map.add_argument("--output", required=True)
    professional_map.add_argument("--format", default="pdf")
    professional_map.add_argument("--layout-template", default="scientific_publication")
    professional_map.add_argument("--style-profile", default="scientific_soft")
    professional_map.add_argument("--legend-layer", action="append", default=[])
    professional_map.add_argument("--map-author", default="")
    professional_map.add_argument("--organization", default="")
    professional_map.add_argument("--data-source", default="")
    professional_map.add_argument("--confirm-overwrite", action="store_true")
    professional_map.add_argument("--dry-run", action="store_true")
    quality = sub.add_parser("map-quality")
    quality.add_argument("--layout", required=True)
    quality.add_argument("--output", default="")
    sub.add_parser("processing-providers")
    processing_algorithms = sub.add_parser("processing-algorithms")
    processing_algorithms.add_argument("--provider", default="")
    processing_algorithms.add_argument("--filter", default="")
    processing_algorithms.add_argument("--all", action="store_true")
    algorithm_info = sub.add_parser("processing-algorithm-info")
    algorithm_info.add_argument("algorithm_id")
    recommend = sub.add_parser("recommend-qgis-tool")
    recommend.add_argument("goal")
    sub.add_parser("plugins-extended")
    plugin_manifest = sub.add_parser("plugin-manifest")
    plugin_manifest.add_argument("--plugin-name", default="")
    plugin_manifest.add_argument("--max-algorithms", type=int, default=100)
    plugin_manifest.add_argument("--active-only", action="store_true")
    plugin_algorithm_plan = sub.add_parser("plugin-algorithm-plan")
    plugin_algorithm_plan.add_argument("algorithm_id")
    plugin_algorithm_plan.add_argument("--parameters-json", default="{}")
    plugin_algorithm_run = sub.add_parser("plugin-algorithm-run")
    plugin_algorithm_run.add_argument("algorithm_id")
    plugin_algorithm_run.add_argument("--parameters-json", default="{}")
    plugin_algorithm_run.add_argument("--confirm-network", action="store_true")
    plugin_algorithm_run.add_argument("--confirm-generic-plugin-run", action="store_true")
    plugin_algorithm_run.add_argument("--confirm-overwrite", action="store_true")
    plugin_algorithm_run.add_argument("--dry-run", action="store_true")
    sub.add_parser("get-user-profile")
    set_profile = sub.add_parser("set-user-profile")
    set_profile.add_argument("--map-author", default="")
    set_profile.add_argument("--map-author-email", default="")
    set_profile.add_argument("--organization", default="")
    set_profile.add_argument("--default-credit-line", default="")
    set_profile.add_argument("--dry-run", action="store_true")
    clear_profile = sub.add_parser("clear-user-profile")
    clear_profile.add_argument("--dry-run", action="store_true")
    sub.add_parser("dev-status")
    dev_python = sub.add_parser("dev-python")
    dev_python.add_argument("--code", default="")
    dev_python.add_argument("--code-file", default="")
    dev_python.add_argument("--confirm-dev-python", default="")
    dev_python.add_argument("--dry-run", action="store_true")
    load_raster = sub.add_parser("load-raster")
    load_raster.add_argument("path")
    load_raster.add_argument("--name", default="")
    load_raster.add_argument("--dry-run", action="store_true")
    raster_info = sub.add_parser("raster-info")
    raster_info.add_argument("--layer-id", required=True)
    raster_stats = sub.add_parser("raster-band-statistics")
    raster_stats.add_argument("--layer-id", required=True)
    raster_stats.add_argument("--band", type=int, default=1)
    raster_report = sub.add_parser("raster-metadata-report")
    raster_report.add_argument("--layer-id", required=True)
    raster_hillshade = sub.add_parser("raster-hillshade")
    raster_hillshade.add_argument("--layer-id", required=True)
    raster_hillshade.add_argument("--output", default="TEMPORARY_OUTPUT")
    raster_hillshade.add_argument("--confirm-overwrite", action="store_true")
    raster_hillshade.add_argument("--dry-run", action="store_true")
    raster_slope = sub.add_parser("raster-slope")
    raster_slope.add_argument("--layer-id", required=True)
    raster_slope.add_argument("--output", default="TEMPORARY_OUTPUT")
    raster_slope.add_argument("--confirm-overwrite", action="store_true")
    raster_slope.add_argument("--dry-run", action="store_true")
    raster_contours = sub.add_parser("raster-contours")
    raster_contours.add_argument("--layer-id", required=True)
    raster_contours.add_argument("--interval", type=float, default=10.0)
    raster_contours.add_argument("--output", default="TEMPORARY_OUTPUT")
    raster_contours.add_argument("--confirm-overwrite", action="store_true")
    raster_contours.add_argument("--dry-run", action="store_true")
    sub.add_parser("layer-tree")
    dup_layers = sub.add_parser("duplicate-layers")
    dup_layers.add_argument("--mode", choices=["source_and_name", "source", "name"], default="source_and_name")
    remove_layer = sub.add_parser("remove-layer")
    remove_layer.add_argument("--layer-id", required=True)
    remove_layer.add_argument("--dry-run", action="store_true")
    remove_by_name = sub.add_parser("remove-layers-by-name")
    remove_by_name.add_argument("--name", required=True)
    remove_by_name.add_argument("--match", choices=["exact", "contains"], default="exact")
    remove_by_name.add_argument("--dry-run", action="store_true")
    remove_by_source = sub.add_parser("remove-layers-by-source")
    remove_by_source.add_argument("--source-path", required=True)
    remove_by_source.add_argument("--dry-run", action="store_true")
    clear_tmp = sub.add_parser("clear-sigmai-temporary-layers")
    clear_tmp.add_argument("--name-prefix", default="SIGMAI")
    clear_tmp.add_argument("--source-contains", default="test_outputs")
    clear_tmp.add_argument("--include-topotrail-test-layers", action="store_true")
    clear_tmp.add_argument("--dry-run", action="store_true")
    dedup = sub.add_parser("deduplicate-layers")
    dedup.add_argument("--mode", choices=["source_and_name", "source", "name"], default="source_and_name")
    dedup.add_argument("--keep", choices=["first", "last"], default="first")
    dedup.add_argument("--dry-run", action="store_true")
    set_visibility = sub.add_parser("set-layer-visibility")
    set_visibility.add_argument("--layer-id", required=True)
    set_visibility.add_argument("--visible", action="store_true")
    set_visibility.add_argument("--hidden", action="store_true")
    set_visibility.add_argument("--dry-run", action="store_true")
    move_order = sub.add_parser("move-layer-order")
    move_order.add_argument("--layer-id", required=True)
    move_order.add_argument("--index", type=int, required=True)
    move_order.add_argument("--dry-run", action="store_true")
    list_fields = sub.add_parser("list-fields")
    list_fields.add_argument("--layer-id", required=True)
    sample_features = sub.add_parser("sample-features")
    sample_features.add_argument("--layer-id", required=True)
    sample_features.add_argument("--max-features", type=int, default=10)
    field_stats = sub.add_parser("field-statistics")
    field_stats.add_argument("--layer-id", required=True)
    field_stats.add_argument("--field", required=True)
    unique = sub.add_parser("unique-values")
    unique.add_argument("--layer-id", required=True)
    unique.add_argument("--field", required=True)
    unique.add_argument("--limit", type=int, default=100)
    validate_expr = sub.add_parser("validate-expression")
    validate_expr.add_argument("--expression", required=True)
    validate_expr.add_argument("--layer-id", default="")
    query = sub.add_parser("query-features")
    query.add_argument("--layer-id", required=True)
    query.add_argument("--expression", required=True)
    query.add_argument("--max-features", type=int, default=100)
    select_expr = sub.add_parser("select-by-expression")
    select_expr.add_argument("--layer-id", required=True)
    select_expr.add_argument("--expression", required=True)
    select_expr.add_argument("--dry-run", action="store_true")
    extract_expr = sub.add_parser("extract-by-expression")
    extract_expr.add_argument("--layer-id", required=True)
    extract_expr.add_argument("--expression", required=True)
    extract_expr.add_argument("--output", default="TEMPORARY_OUTPUT")
    extract_expr.add_argument("--dry-run", action="store_true")
    intersection = sub.add_parser("intersection")
    intersection.add_argument("input_layer_id")
    intersection.add_argument("overlay_layer_id")
    intersection.add_argument("--output", default="TEMPORARY_OUTPUT")
    intersection.add_argument("--dry-run", action="store_true")
    centroids_cmd = sub.add_parser("centroids")
    centroids_cmd.add_argument("layer_id")
    centroids_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    centroids_cmd.add_argument("--dry-run", action="store_true")
    workflow_report = sub.add_parser("workflow-report")
    workflow_report.add_argument("--output", required=True)
    workflow_report.add_argument("--confirm-overwrite", action="store_true")
    workflow_report.add_argument("--dry-run", action="store_true")
    evaluate_layout = sub.add_parser("evaluate-layout")
    evaluate_layout.add_argument("--layout", required=True)
    evaluate_layout.add_argument("--output", default="")
    sub.add_parser("self-inspect")
    sub.add_parser("self-health-check")
    self_backup = sub.add_parser("self-backup")
    self_backup.add_argument("--dry-run", action="store_true")
    self_validate = sub.add_parser("self-validate-update")
    self_validate.add_argument("source_folder")
    self_stage = sub.add_parser("self-stage-update")
    self_stage.add_argument("source_folder")
    self_stage.add_argument("--confirm", action="store_true")
    self_stage.add_argument("--dry-run", action="store_true")
    self_apply = sub.add_parser("self-apply-update")
    self_apply.add_argument("--confirm", action="store_true")
    self_apply.add_argument("--dry-run", action="store_true")
    self_rollback = sub.add_parser("self-rollback")
    self_rollback.add_argument("backup_path")
    self_rollback.add_argument("--confirm", action="store_true")
    self_rollback.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.cmd == "connect":
        return print_json(bridge_command("status", pairing_code=args.pairing_code))
    if args.cmd == "status":
        return print_json(bridge_command("status"))
    if args.cmd == "capabilities":
        return print_json(bridge_command("get_capabilities"))
    if args.cmd == "layers":
        return print_json(bridge_command("list_layers"))
    if args.cmd == "qgis-info":
        return print_json(bridge_command("get_qgis_environment"))
    if args.cmd == "diagnose-crs":
        return print_json(bridge_command("diagnose_crs"))
    if args.cmd == "plugins":
        return print_json(bridge_command("list_installed_plugins"))
    if args.cmd == "inspect-plugin":
        return print_json(bridge_command("inspect_plugin", {"plugin_name": args.plugin_name}))
    if args.cmd == "plugin-structure":
        return print_json(bridge_command("check_plugin_structure", {"plugin_name": args.plugin_name}))
    if args.cmd == "plugin-imports":
        return print_json(bridge_command("check_plugin_imports", {"plugin_name": args.plugin_name}))
    if args.cmd == "plugin-resources":
        return print_json(bridge_command("check_plugin_resources", {"plugin_name": args.plugin_name}))
    if args.cmd == "plugin-icon":
        return print_json(bridge_command("check_plugin_icon", {"plugin_name": args.plugin_name}))
    if args.cmd == "plugin-report":
        params = {"plugin_name": args.plugin_name}
        if args.output_path:
            params["output_path"] = project_path(args.output_path)
        return print_json(bridge_command("generate_plugin_report", params))
    if args.cmd == "package-plugin":
        return print_json(bridge_command("package_plugin_zip", {"plugin_name": args.plugin_name, "output_path": project_path(args.output_path), "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "plugin-repo-search":
        return print_json(bridge_command("search_qgis_plugin_repository", {"query": args.query, "qgis_version": args.qgis_version, "limit": args.limit, "confirm_network": args.confirm_network}))
    if args.cmd == "plugin-repo-download":
        return print_json(bridge_command("download_qgis_plugin_zip", {"plugin_name": args.plugin_name, "output_path": project_path(args.output_path), "qgis_version": args.qgis_version, "confirm_network": args.confirm_network, "confirm_plugin_write": args.confirm, "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "inspect-plugin-zip":
        return print_json(bridge_command("inspect_qgis_plugin_zip", {"zip_path": project_path(args.zip_path)}))
    if args.cmd == "install-plugin-zip":
        params = {"zip_path": project_path(args.zip_path), "plugin_name": args.plugin_name, "update": args.update, "confirm_plugin_write": args.confirm}
        return print_json(bridge_command("install_plugin_from_zip", params, dry_run=args.dry_run))
    if args.cmd == "install-plugin-repository":
        return print_json(bridge_command("install_qgis_plugin_from_repository", {"plugin_name": args.plugin_name, "qgis_version": args.qgis_version, "confirm_network": args.confirm_network, "confirm_plugin_write": args.confirm, "update": args.update}, dry_run=args.dry_run))
    if args.cmd == "validate-geometries":
        return print_json(bridge_command("validate_geometries", {"layer_id": args.layer_id, "max_features": args.max_features}))
    if args.cmd == "fix-geometries":
        return print_json(bridge_command("fix_geometries", {"layer_id": args.layer_id, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "buffer":
        return print_json(bridge_command("buffer", {"layer_id": args.layer_id, "distance": args.distance, "segments": args.segments, "dissolve": args.dissolve, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "clip":
        return print_json(bridge_command("clip", {"input_layer_id": args.input_layer_id, "overlay_layer_id": args.overlay_layer_id, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "dissolve":
        return print_json(bridge_command("dissolve", {"layer_id": args.layer_id, "fields": args.field, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "reproject-layer":
        return print_json(bridge_command("reproject_layer", {"layer_id": args.layer_id, "target_crs": args.target_crs, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "export-layer":
        return print_json(bridge_command("export_layer", {"layer_id": args.layer_id, "output_path": project_path(args.output_path), "format": args.format, "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "add-layout-map":
        return print_json(bridge_command("add_layout_map", {"layout_name": args.layout, "layer_id": args.layer_id, "item_id": args.item_id}, dry_run=args.dry_run))
    if args.cmd == "set-layout-extent":
        params = {"layout_name": args.layout, "map_item_id": args.map_item, "margin_percent": args.margin_percent}
        if args.layer_id:
            params["layer_id"] = args.layer_id
        return print_json(bridge_command("set_layout_extent", params, dry_run=args.dry_run))
    if args.cmd == "add-layout-label":
        return print_json(bridge_command("add_layout_label", {"layout_name": args.layout, "text": args.text, "item_id": args.item_id}, dry_run=args.dry_run))
    if args.cmd == "add-layout-legend":
        params = {"layout_name": args.layout, "linked_map_item_id": args.map_item, "filter_to_map_layers": True}
        if args.layer_id:
            params["legend_layers"] = args.layer_id
        return print_json(bridge_command("add_layout_legend", params, dry_run=args.dry_run))
    if args.cmd == "add-layout-scale-bar":
        return print_json(bridge_command("add_layout_scale_bar", {"layout_name": args.layout, "linked_map_item_id": args.map_item}, dry_run=args.dry_run))
    if args.cmd == "add-layout-north-arrow":
        return print_json(bridge_command("add_layout_north_arrow", {"layout_name": args.layout}, dry_run=args.dry_run))
    if args.cmd == "add-layout-grid":
        return print_json(bridge_command("add_layout_grid", {"layout_name": args.layout, "map_item_id": args.map_item, "interval_x": args.interval_x, "interval_y": args.interval_y}, dry_run=args.dry_run))
    if args.cmd == "add-layout-picture":
        return print_json(bridge_command("add_layout_picture", {"layout_name": args.layout, "path": project_path(args.path), "item_id": args.item_id}, dry_run=args.dry_run))
    if args.cmd == "set-layer-style":
        return print_json(bridge_command("set_layer_style", {"layer_id": args.layer_id, "fill_color": args.fill_color, "stroke_color": args.stroke_color, "stroke_width": args.stroke_width, "opacity": args.opacity}, dry_run=args.dry_run))
    if args.cmd == "basic-map":
        params = {"layer_id": args.layer_id, "title": args.title, "output_path": project_path(args.output), "format": args.format, "include_grid": args.include_grid, "logo_path": project_path(args.logo_path) if args.logo_path else "", "confirm_overwrite": args.confirm_overwrite, "layout_template": args.layout_template, "map_author": args.map_author, "organization": args.organization, "data_source": args.data_source}
        if args.legend_layer:
            params["legend_layers"] = args.legend_layer
        return print_json(bridge_command("generate_basic_map", params, dry_run=args.dry_run))
    if args.cmd == "layout-templates":
        return print_json(bridge_command("list_layout_templates"))
    if args.cmd == "professional-map":
        params = {"layer_id": args.layer_id, "title": args.title, "subtitle": args.subtitle, "output_path": project_path(args.output), "format": args.format, "layout_template": args.layout_template, "style_profile": args.style_profile, "confirm_overwrite": args.confirm_overwrite, "map_author": args.map_author, "organization": args.organization, "data_source": args.data_source}
        if args.legend_layer:
            params["legend_layers"] = args.legend_layer
        return print_json(bridge_command("generate_professional_map", params, dry_run=args.dry_run))
    if args.cmd == "map-quality":
        params = {"layout_name": args.layout}
        if args.output:
            params["output_path"] = project_path(args.output)
        return print_json(bridge_command("evaluate_map_quality", params))
    if args.cmd == "processing-providers":
        return print_json(bridge_command("list_processing_providers"))
    if args.cmd == "processing-algorithms":
        return print_json(bridge_command("list_processing_algorithms", {"provider": args.provider, "filter": args.filter, "safe_only": not args.all}))
    if args.cmd == "processing-algorithm-info":
        return print_json(bridge_command("get_processing_algorithm_info", {"algorithm_id": args.algorithm_id}))
    if args.cmd == "recommend-qgis-tool":
        return print_json(bridge_command("recommend_qgis_tool", {"goal": args.goal}))
    if args.cmd == "plugins-extended":
        return print_json(bridge_command("list_qgis_plugins_extended"))
    if args.cmd == "plugin-manifest":
        params = {"max_algorithms": args.max_algorithms, "include_inactive": not args.active_only}
        if args.plugin_name:
            params["plugin_name"] = args.plugin_name
        return print_json(bridge_command("build_plugin_capability_manifest", params))
    if args.cmd == "plugin-algorithm-plan":
        return print_json(bridge_command("dry_run_plugin_algorithm_generic", {"algorithm_id": args.algorithm_id, "parameters": json.loads(args.parameters_json)}))
    if args.cmd == "plugin-algorithm-run":
        return print_json(bridge_command("run_plugin_algorithm_generic_safe", {"algorithm_id": args.algorithm_id, "parameters": json.loads(args.parameters_json), "confirm_network": args.confirm_network, "confirm_generic_plugin_run": args.confirm_generic_plugin_run, "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "get-user-profile":
        return print_json(bridge_command("get_user_profile"))
    if args.cmd == "set-user-profile":
        return print_json(bridge_command("set_user_profile", {"default_map_author": args.map_author, "default_map_author_email": args.map_author_email, "default_organization": args.organization, "default_credit_line": args.default_credit_line}, dry_run=args.dry_run))
    if args.cmd == "clear-user-profile":
        return print_json(bridge_command("clear_user_profile", dry_run=args.dry_run))
    if args.cmd == "dev-status":
        return print_json(bridge_command("get_dev_mode_status"))
    if args.cmd == "dev-python":
        code = args.code
        if args.code_file:
            code = Path(args.code_file).read_text(encoding="utf-8")
        return print_json(bridge_command("dev_execute_qgis_python", {"code": code, "confirm_dev_python": args.confirm_dev_python}, dry_run=args.dry_run))
    if args.cmd == "load-raster":
        params = {"path": project_path(args.path)}
        if args.name:
            params["name"] = args.name
        return print_json(bridge_command("load_raster_layer", params, dry_run=args.dry_run))
    if args.cmd == "raster-info":
        return print_json(bridge_command("raster_info", {"layer_id": args.layer_id}))
    if args.cmd == "raster-band-statistics":
        return print_json(bridge_command("raster_band_statistics", {"layer_id": args.layer_id, "band": args.band}))
    if args.cmd == "raster-metadata-report":
        return print_json(bridge_command("raster_metadata_report", {"layer_id": args.layer_id}))
    if args.cmd == "raster-hillshade":
        return print_json(bridge_command("raster_hillshade", {"layer_id": args.layer_id, "output": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "raster-slope":
        return print_json(bridge_command("raster_slope", {"layer_id": args.layer_id, "output": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "raster-contours":
        return print_json(bridge_command("raster_contours", {"layer_id": args.layer_id, "interval": args.interval, "output": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "layer-tree":
        return print_json(bridge_command("list_layer_tree"))
    if args.cmd == "duplicate-layers":
        return print_json(bridge_command("list_duplicate_layers", {"mode": args.mode}))
    if args.cmd == "remove-layer":
        return print_json(bridge_command("remove_layer", {"layer_id": args.layer_id}, dry_run=args.dry_run))
    if args.cmd == "remove-layers-by-name":
        return print_json(bridge_command("remove_layers_by_name", {"name": args.name, "match": args.match}, dry_run=args.dry_run))
    if args.cmd == "remove-layers-by-source":
        return print_json(bridge_command("remove_layers_by_source_path", {"source_path": project_path(args.source_path)}, dry_run=args.dry_run))
    if args.cmd == "clear-sigmai-temporary-layers":
        return print_json(
            bridge_command(
                "clear_sigmai_temporary_layers",
                {"name_prefix": args.name_prefix, "source_contains": args.source_contains, "include_topotrail_test_layers": args.include_topotrail_test_layers},
                dry_run=args.dry_run,
            )
        )
    if args.cmd == "deduplicate-layers":
        return print_json(bridge_command("deduplicate_layers", {"mode": args.mode, "keep": args.keep}, dry_run=args.dry_run))
    if args.cmd == "set-layer-visibility":
        return print_json(bridge_command("set_layer_visibility", {"layer_id": args.layer_id, "visible": not args.hidden}, dry_run=args.dry_run))
    if args.cmd == "move-layer-order":
        return print_json(bridge_command("move_layer_order", {"layer_id": args.layer_id, "index": args.index}, dry_run=args.dry_run))
    if args.cmd == "list-fields":
        return print_json(bridge_command("list_fields", {"layer_id": args.layer_id}))
    if args.cmd == "sample-features":
        return print_json(bridge_command("sample_features", {"layer_id": args.layer_id, "max_features": args.max_features}))
    if args.cmd == "field-statistics":
        return print_json(bridge_command("field_statistics", {"layer_id": args.layer_id, "field_name": args.field}))
    if args.cmd == "unique-values":
        return print_json(bridge_command("unique_values", {"layer_id": args.layer_id, "field_name": args.field, "limit": args.limit}))
    if args.cmd == "validate-expression":
        params = {"expression": args.expression}
        if args.layer_id:
            params["layer_id"] = args.layer_id
        return print_json(bridge_command("validate_expression", params))
    if args.cmd == "query-features":
        return print_json(bridge_command("query_features", {"layer_id": args.layer_id, "expression": args.expression, "max_features": args.max_features}))
    if args.cmd == "select-by-expression":
        return print_json(bridge_command("select_by_expression", {"layer_id": args.layer_id, "expression": args.expression}, dry_run=args.dry_run))
    if args.cmd == "extract-by-expression":
        return print_json(bridge_command("extract_by_expression", {"layer_id": args.layer_id, "expression": args.expression, "output": project_path(args.output)}, dry_run=args.dry_run))
    if args.cmd == "intersection":
        return print_json(bridge_command("intersection", {"input_layer_id": args.input_layer_id, "overlay_layer_id": args.overlay_layer_id, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "centroids":
        return print_json(bridge_command("centroids", {"layer_id": args.layer_id, "output": args.output}, dry_run=args.dry_run))
    if args.cmd == "workflow-report":
        return print_json(bridge_command("generate_workflow_report", {"output_path": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, dry_run=args.dry_run))
    if args.cmd == "evaluate-layout":
        params = {"layout_name": args.layout}
        if args.output:
            params["output_path"] = project_path(args.output)
        return print_json(bridge_command("evaluate_layout_cartographic_completeness", params))
    if args.cmd == "self-inspect":
        return print_json(bridge_command("self_inspect"))
    if args.cmd == "self-health-check":
        return print_json(bridge_command("self_health_check"))
    if args.cmd == "self-backup":
        return print_json(bridge_command("self_backup", dry_run=args.dry_run))
    if args.cmd == "self-validate-update":
        return print_json(bridge_command("self_validate_update", {"source_folder": project_path(args.source_folder)}))
    if args.cmd == "self-stage-update":
        return print_json(bridge_command("self_stage_update", {"source_folder": project_path(args.source_folder), "confirm": args.confirm}, dry_run=args.dry_run))
    if args.cmd == "self-apply-update":
        return print_json(bridge_command("self_apply_update", {"confirm_self_apply_update": args.confirm}, dry_run=args.dry_run))
    if args.cmd == "self-rollback":
        return print_json(bridge_command("self_rollback", {"backup_path": project_path(args.backup_path), "confirm": args.confirm, "confirm_rollback": args.confirm}, dry_run=args.dry_run))
    if args.cmd == "test":
        return subprocess.call([sys.executable, str(ROOT / "tools" / "sigmai_autotest.py"), "--run-integration"], cwd=str(ROOT))
    if args.cmd == "open-qgis":
        return subprocess.call([sys.executable, str(ROOT / "tools" / "launch_qgis_for_tests.py")], cwd=str(ROOT))
    if args.cmd == "install-plugin":
        return subprocess.call([sys.executable, str(ROOT / "tools" / "install_qgis_plugin.py")], cwd=str(ROOT))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
