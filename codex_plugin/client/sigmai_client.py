from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ROOT = Path(__file__).resolve().parents[2]


class SigmaiClientError(RuntimeError):
    pass


def project_path(value: str) -> str:
    if not value or value == "TEMPORARY_OUTPUT":
        return value
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((ROOT / path).resolve())


def session_file_candidates() -> list[Path]:
    candidates = []
    env_file = os.environ.get("SIGMAI_SESSION_FILE")
    if env_file:
        candidates.append(Path(env_file))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for app_name in ["SIGMAI"]:
            candidates.append(Path(local_app_data) / app_name / "sessions" / "current_bridge_session.json")
            session_dir = Path(local_app_data) / app_name / "sessions"
            candidates.extend(sorted(session_dir.glob("SG-*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if session_dir.exists() else [])
        candidates.append(Path(local_app_data) / "SIGMAI" / "current_bridge_session.json")
    temp = os.environ.get("TEMP")
    if temp:
        for app_name in ["SIGMAI"]:
            candidates.append(Path(temp) / app_name / "sessions" / "current_bridge_session.json")
            session_dir = Path(temp) / app_name / "sessions"
            candidates.extend(sorted(session_dir.glob("SG-*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if session_dir.exists() else [])
            candidates.append(Path(temp) / app_name / "current_bridge_session.json")
        candidates.append(Path(temp) / "sigmai" / "current_bridge_session.json")
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins" / "sigmai" / "diagnostics" / "current_bridge_session.json")
    return candidates


def read_session_file() -> dict[str, Any]:
    for path in session_file_candidates():
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                data["_session_path"] = str(path)
                return data
        except Exception:
            continue
    return {}


class SigmaiClient:
    def __init__(self, host: str | None = None, port: int | None = None, token: str | None = None, timeout: float = 120, pairing_code: str | None = None, session_file: str | None = None):
        session = read_session_file()
        if session_file:
            try:
                session = json.loads(Path(session_file).read_text(encoding="utf-8"))
            except Exception:
                session = {}
        if pairing_code:
            wanted = pairing_code.upper()
            for path in session_file_candidates():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if path.stem.upper() == wanted or str(data.get("session_id", "")).upper() == wanted:
                        session = data
                        break
                except Exception:
                    pass
        self.host = host or os.environ.get("SIGMAI_HOST") or session.get("host", DEFAULT_HOST)
        self.port = int(port or os.environ.get("SIGMAI_PORT") or session.get("port", DEFAULT_PORT))
        self.token = token or os.environ.get("SIGMAI_TOKEN", "") or os.environ.get("SIGMAI_TOKEN", "") or session.get("token", "")
        self.session_path = session.get("_session_path", "")
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise SigmaiClientError("Missing token. Pass --token, set SIGMAI_TOKEN, or start QGIS Bridge with session file enabled.")
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/command",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._open_json(request)

    def status_endpoint(self) -> dict[str, Any]:
        if not self.token:
            raise SigmaiClientError("Missing token. Pass --token, set SIGMAI_TOKEN, or start QGIS Bridge with session file enabled.")
        request = urllib.request.Request(
            f"{self.base_url}/status",
            headers={"Authorization": f"Bearer {self.token}"},
            method="GET",
        )
        return self._open_json(request)

    def _open_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError as json_exc:
                raise SigmaiClientError(f"HTTP {exc.code}: {body}") from json_exc
        except urllib.error.URLError as exc:
            raise SigmaiClientError(f"Could not connect to SIGMAI: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SIGMAI local client")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--pairing-code", default=os.environ.get("SIGMAI_PAIRING_CODE"))
    parser.add_argument("--session-file", default=os.environ.get("SIGMAI_SESSION_FILE"))
    subcommands = parser.add_subparsers(dest="command_name", required=True)

    subcommands.add_parser("status")
    subcommands.add_parser("capabilities")
    subcommands.add_parser("environment")
    subcommands.add_parser("bridge-status")
    subcommands.add_parser("list-layers")
    subcommands.add_parser("list-layouts")
    subcommands.add_parser("list-plugins")
    subcommands.add_parser("diagnose-crs")
    subcommands.add_parser("self-inspect")
    subcommands.add_parser("self-health-check")
    subcommands.add_parser("project-info")

    layer_info = subcommands.add_parser("layer-info")
    layer_info.add_argument("--layer-id", required=True)
    validate_geometries = subcommands.add_parser("validate-geometries")
    validate_geometries.add_argument("--layer-id", required=True)
    validate_geometries.add_argument("--max-features", type=int, default=10000)
    fix_geometries = subcommands.add_parser("fix-geometries")
    fix_geometries.add_argument("--layer-id", required=True)
    fix_geometries.add_argument("--output", default="TEMPORARY_OUTPUT")
    fix_geometries.add_argument("--dry-run", action="store_true")
    buffer_cmd = subcommands.add_parser("buffer")
    buffer_cmd.add_argument("--layer-id", required=True)
    buffer_cmd.add_argument("--distance", type=float, required=True)
    buffer_cmd.add_argument("--segments", type=int, default=8)
    buffer_cmd.add_argument("--dissolve", action="store_true")
    buffer_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    buffer_cmd.add_argument("--dry-run", action="store_true")
    clip_cmd = subcommands.add_parser("clip")
    clip_cmd.add_argument("--input-layer-id", required=True)
    clip_cmd.add_argument("--overlay-layer-id", required=True)
    clip_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    clip_cmd.add_argument("--dry-run", action="store_true")
    dissolve_cmd = subcommands.add_parser("dissolve")
    dissolve_cmd.add_argument("--layer-id", required=True)
    dissolve_cmd.add_argument("--field", action="append", default=[])
    dissolve_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    dissolve_cmd.add_argument("--dry-run", action="store_true")
    reproject = subcommands.add_parser("reproject-layer")
    reproject.add_argument("--layer-id", required=True)
    reproject.add_argument("--target-crs", required=True)
    reproject.add_argument("--output", default="TEMPORARY_OUTPUT")
    reproject.add_argument("--dry-run", action="store_true")
    export_layer = subcommands.add_parser("export-layer")
    export_layer.add_argument("--layer-id", required=True)
    export_layer.add_argument("--output-path", required=True)
    export_layer.add_argument("--format", default="GPKG")
    export_layer.add_argument("--confirm-overwrite", action="store_true")
    export_layer.add_argument("--dry-run", action="store_true")
    add_map = subcommands.add_parser("add-layout-map")
    add_map.add_argument("--layout", required=True)
    add_map.add_argument("--layer-id", required=True)
    add_map.add_argument("--item-id", default="main_map")
    add_map.add_argument("--dry-run", action="store_true")
    extent = subcommands.add_parser("set-layout-extent")
    extent.add_argument("--layout", required=True)
    extent.add_argument("--map-item", default="main_map")
    extent.add_argument("--layer-id", default="")
    extent.add_argument("--margin-percent", type=float, default=5)
    extent.add_argument("--dry-run", action="store_true")
    label = subcommands.add_parser("add-layout-label")
    label.add_argument("--layout", required=True)
    label.add_argument("--text", required=True)
    label.add_argument("--item-id", default="label")
    label.add_argument("--dry-run", action="store_true")
    legend = subcommands.add_parser("add-layout-legend")
    legend.add_argument("--layout", required=True)
    legend.add_argument("--map-item", default="main_map")
    legend.add_argument("--layer-id", action="append", default=[])
    legend.add_argument("--dry-run", action="store_true")
    scale = subcommands.add_parser("add-layout-scale-bar")
    scale.add_argument("--layout", required=True)
    scale.add_argument("--map-item", default="main_map")
    scale.add_argument("--dry-run", action="store_true")
    north = subcommands.add_parser("add-layout-north-arrow")
    north.add_argument("--layout", required=True)
    north.add_argument("--dry-run", action="store_true")
    grid = subcommands.add_parser("add-layout-grid")
    grid.add_argument("--layout", required=True)
    grid.add_argument("--map-item", default="main_map")
    grid.add_argument("--interval-x", type=float, default=None)
    grid.add_argument("--interval-y", type=float, default=None)
    grid.add_argument("--dry-run", action="store_true")
    picture = subcommands.add_parser("add-layout-picture")
    picture.add_argument("--layout", required=True)
    picture.add_argument("--path", required=True)
    picture.add_argument("--item-id", default="picture")
    picture.add_argument("--dry-run", action="store_true")
    style = subcommands.add_parser("set-layer-style")
    style.add_argument("--layer-id", required=True)
    style.add_argument("--fill-color", default="#D8E1E8")
    style.add_argument("--stroke-color", default="#075D68")
    style.add_argument("--stroke-width", type=float, default=0.4)
    style.add_argument("--opacity", type=float, default=0.85)
    style.add_argument("--dry-run", action="store_true")
    basic_map = subcommands.add_parser("basic-map")
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
    subcommands.add_parser("layout-templates")
    professional_map = subcommands.add_parser("professional-map")
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
    subcommands.add_parser("layer-tree")
    set_visibility = subcommands.add_parser("set-layer-visibility")
    set_visibility.add_argument("--layer-id", required=True)
    set_visibility.add_argument("--visible", action="store_true")
    set_visibility.add_argument("--hidden", action="store_true")
    set_visibility.add_argument("--dry-run", action="store_true")
    move_order = subcommands.add_parser("move-layer-order")
    move_order.add_argument("--layer-id", required=True)
    move_order.add_argument("--index", type=int, required=True)
    move_order.add_argument("--dry-run", action="store_true")
    list_fields = subcommands.add_parser("list-fields")
    list_fields.add_argument("--layer-id", required=True)
    sample_features = subcommands.add_parser("sample-features")
    sample_features.add_argument("--layer-id", required=True)
    sample_features.add_argument("--max-features", type=int, default=10)
    field_stats = subcommands.add_parser("field-statistics")
    field_stats.add_argument("--layer-id", required=True)
    field_stats.add_argument("--field", required=True)
    unique = subcommands.add_parser("unique-values")
    unique.add_argument("--layer-id", required=True)
    unique.add_argument("--field", required=True)
    unique.add_argument("--limit", type=int, default=100)
    validate_expr = subcommands.add_parser("validate-expression")
    validate_expr.add_argument("--expression", required=True)
    validate_expr.add_argument("--layer-id", default="")
    query = subcommands.add_parser("query-features")
    query.add_argument("--layer-id", required=True)
    query.add_argument("--expression", required=True)
    query.add_argument("--max-features", type=int, default=100)
    select_expr = subcommands.add_parser("select-by-expression")
    select_expr.add_argument("--layer-id", required=True)
    select_expr.add_argument("--expression", required=True)
    select_expr.add_argument("--dry-run", action="store_true")
    extract_expr = subcommands.add_parser("extract-by-expression")
    extract_expr.add_argument("--layer-id", required=True)
    extract_expr.add_argument("--expression", required=True)
    extract_expr.add_argument("--output", default="TEMPORARY_OUTPUT")
    extract_expr.add_argument("--dry-run", action="store_true")
    intersection = subcommands.add_parser("intersection")
    intersection.add_argument("--input-layer-id", required=True)
    intersection.add_argument("--overlay-layer-id", required=True)
    intersection.add_argument("--output", default="TEMPORARY_OUTPUT")
    intersection.add_argument("--dry-run", action="store_true")
    centroids_cmd = subcommands.add_parser("centroids")
    centroids_cmd.add_argument("--layer-id", required=True)
    centroids_cmd.add_argument("--output", default="TEMPORARY_OUTPUT")
    centroids_cmd.add_argument("--dry-run", action="store_true")
    workflow_report = subcommands.add_parser("workflow-report")
    workflow_report.add_argument("--output", required=True)
    workflow_report.add_argument("--confirm-overwrite", action="store_true")
    workflow_report.add_argument("--dry-run", action="store_true")
    evaluate_layout = subcommands.add_parser("evaluate-layout")
    evaluate_layout.add_argument("--layout", required=True)
    evaluate_layout.add_argument("--output", default="")
    map_quality = subcommands.add_parser("map-quality")
    map_quality.add_argument("--layout", required=True)
    map_quality.add_argument("--output", default="")
    subcommands.add_parser("processing-providers")
    processing_algorithms = subcommands.add_parser("processing-algorithms")
    processing_algorithms.add_argument("--provider", default="")
    processing_algorithms.add_argument("--filter", default="")
    processing_algorithms.add_argument("--all", action="store_true")
    algorithm_info = subcommands.add_parser("processing-algorithm-info")
    algorithm_info.add_argument("algorithm_id")
    recommend = subcommands.add_parser("recommend-qgis-tool")
    recommend.add_argument("goal")
    subcommands.add_parser("plugins-extended")
    plugin_manifest = subcommands.add_parser("plugin-manifest")
    plugin_manifest.add_argument("--plugin-name", default="")
    plugin_manifest.add_argument("--max-algorithms", type=int, default=100)
    plugin_manifest.add_argument("--active-only", action="store_true")
    plugin_algorithm_plan = subcommands.add_parser("plugin-algorithm-plan")
    plugin_algorithm_plan.add_argument("algorithm_id")
    plugin_algorithm_plan.add_argument("--parameters-json", default="{}")
    plugin_algorithm_run = subcommands.add_parser("plugin-algorithm-run")
    plugin_algorithm_run.add_argument("algorithm_id")
    plugin_algorithm_run.add_argument("--parameters-json", default="{}")
    plugin_algorithm_run.add_argument("--confirm-network", action="store_true")
    plugin_algorithm_run.add_argument("--confirm-generic-plugin-run", action="store_true")
    plugin_algorithm_run.add_argument("--confirm-overwrite", action="store_true")
    plugin_algorithm_run.add_argument("--dry-run", action="store_true")
    subcommands.add_parser("get-user-profile")
    set_profile = subcommands.add_parser("set-user-profile")
    set_profile.add_argument("--map-author", default="")
    set_profile.add_argument("--map-author-email", default="")
    set_profile.add_argument("--organization", default="")
    set_profile.add_argument("--default-credit-line", default="")
    set_profile.add_argument("--dry-run", action="store_true")
    clear_profile = subcommands.add_parser("clear-user-profile")
    clear_profile.add_argument("--dry-run", action="store_true")
    load_raster = subcommands.add_parser("load-raster")
    load_raster.add_argument("--path", required=True)
    load_raster.add_argument("--name", default="")
    load_raster.add_argument("--dry-run", action="store_true")
    raster_info = subcommands.add_parser("raster-info")
    raster_info.add_argument("--layer-id", required=True)
    raster_stats = subcommands.add_parser("raster-band-statistics")
    raster_stats.add_argument("--layer-id", required=True)
    raster_stats.add_argument("--band", type=int, default=1)
    raster_report = subcommands.add_parser("raster-metadata-report")
    raster_report.add_argument("--layer-id", required=True)
    raster_hillshade = subcommands.add_parser("raster-hillshade")
    raster_hillshade.add_argument("--layer-id", required=True)
    raster_hillshade.add_argument("--output", default="TEMPORARY_OUTPUT")
    raster_hillshade.add_argument("--confirm-overwrite", action="store_true")
    raster_hillshade.add_argument("--dry-run", action="store_true")
    raster_slope = subcommands.add_parser("raster-slope")
    raster_slope.add_argument("--layer-id", required=True)
    raster_slope.add_argument("--output", default="TEMPORARY_OUTPUT")
    raster_slope.add_argument("--confirm-overwrite", action="store_true")
    raster_slope.add_argument("--dry-run", action="store_true")

    logs = subcommands.add_parser("get-logs")
    logs.add_argument("--tail", type=int, default=200)

    errors = subcommands.add_parser("recent-errors")
    errors.add_argument("--tail", type=int, default=200)

    inspect_plugin = subcommands.add_parser("inspect-plugin")
    inspect_plugin.add_argument("--plugin-name", required=True)

    validate_metadata = subcommands.add_parser("validate-metadata")
    validate_metadata.add_argument("--plugin-name", required=True)
    plugin_structure = subcommands.add_parser("plugin-structure")
    plugin_structure.add_argument("--plugin-name", required=True)
    plugin_imports = subcommands.add_parser("plugin-imports")
    plugin_imports.add_argument("--plugin-name", required=True)
    plugin_resources = subcommands.add_parser("plugin-resources")
    plugin_resources.add_argument("--plugin-name", required=True)
    plugin_icon = subcommands.add_parser("plugin-icon")
    plugin_icon.add_argument("--plugin-name", required=True)
    plugin_report = subcommands.add_parser("plugin-report")
    plugin_report.add_argument("--plugin-name", required=True)
    plugin_report.add_argument("--output-path", default="")
    package_plugin = subcommands.add_parser("package-plugin")
    package_plugin.add_argument("--plugin-name", required=True)
    package_plugin.add_argument("--output-path", required=True)
    package_plugin.add_argument("--confirm-overwrite", action="store_true")
    package_plugin.add_argument("--dry-run", action="store_true")
    plugin_repo_search = subcommands.add_parser("plugin-repo-search")
    plugin_repo_search.add_argument("--query", default="")
    plugin_repo_search.add_argument("--qgis-version", default="")
    plugin_repo_search.add_argument("--limit", type=int, default=20)
    plugin_repo_search.add_argument("--confirm-network", action="store_true")
    plugin_repo_download = subcommands.add_parser("plugin-repo-download")
    plugin_repo_download.add_argument("--plugin-name", required=True)
    plugin_repo_download.add_argument("--output-path", required=True)
    plugin_repo_download.add_argument("--qgis-version", default="")
    plugin_repo_download.add_argument("--confirm-network", action="store_true")
    plugin_repo_download.add_argument("--confirm", action="store_true")
    plugin_repo_download.add_argument("--confirm-overwrite", action="store_true")
    plugin_repo_download.add_argument("--dry-run", action="store_true")
    inspect_plugin_zip = subcommands.add_parser("inspect-plugin-zip")
    inspect_plugin_zip.add_argument("--zip-path", required=True)
    install_plugin_zip = subcommands.add_parser("install-plugin-zip")
    install_plugin_zip.add_argument("--zip-path", required=True)
    install_plugin_zip.add_argument("--plugin-name", default="")
    install_plugin_zip.add_argument("--confirm", action="store_true")
    install_plugin_zip.add_argument("--update", action="store_true")
    install_plugin_zip.add_argument("--dry-run", action="store_true")
    install_plugin_repo = subcommands.add_parser("install-plugin-repository")
    install_plugin_repo.add_argument("--plugin-name", required=True)
    install_plugin_repo.add_argument("--qgis-version", default="")
    install_plugin_repo.add_argument("--confirm-network", action="store_true")
    install_plugin_repo.add_argument("--confirm", action="store_true")
    install_plugin_repo.add_argument("--update", action="store_true")
    install_plugin_repo.add_argument("--dry-run", action="store_true")
    self_backup = subcommands.add_parser("self-backup")
    self_backup.add_argument("--dry-run", action="store_true")
    self_validate = subcommands.add_parser("self-validate-update")
    self_validate.add_argument("--source-folder", required=True)
    self_stage = subcommands.add_parser("self-stage-update")
    self_stage.add_argument("--source-folder", required=True)
    self_stage.add_argument("--confirm", action="store_true")
    self_stage.add_argument("--dry-run", action="store_true")
    self_apply = subcommands.add_parser("self-apply-update")
    self_apply.add_argument("--confirm", action="store_true")
    self_apply.add_argument("--dry-run", action="store_true")
    self_rollback = subcommands.add_parser("self-rollback")
    self_rollback.add_argument("--backup-path", required=True)
    self_rollback.add_argument("--confirm", action="store_true")
    self_rollback.add_argument("--dry-run", action="store_true")

    raw = subcommands.add_parser("command")
    raw.add_argument("--json", required=True, help="Raw SIGMAI command JSON.")
    return parser


def payload_for_args(args: argparse.Namespace) -> dict[str, Any] | None:
    name = args.command_name
    if name == "status":
        return {"action": "status"}
    if name == "capabilities":
        return {"action": "get_capabilities"}
    if name == "environment":
        return {"action": "get_qgis_environment"}
    if name == "list-layers":
        return {"action": "list_layers"}
    if name == "list-layouts":
        return {"action": "list_layouts"}
    if name == "list-plugins":
        return {"action": "list_installed_plugins"}
    if name == "diagnose-crs":
        return {"action": "diagnose_crs"}
    if name == "self-inspect":
        return {"action": "self_inspect"}
    if name == "self-health-check":
        return {"action": "self_health_check"}
    if name == "project-info":
        return {"action": "get_project_info"}
    if name == "layer-info":
        return {"action": "get_layer_info", "params": {"layer_id": args.layer_id}}
    if name == "validate-geometries":
        return {"action": "validate_geometries", "params": {"layer_id": args.layer_id, "max_features": args.max_features}}
    if name == "fix-geometries":
        return {"action": "fix_geometries", "params": {"layer_id": args.layer_id, "output": args.output}, "dry_run": args.dry_run}
    if name == "buffer":
        return {"action": "buffer", "params": {"layer_id": args.layer_id, "distance": args.distance, "segments": args.segments, "dissolve": args.dissolve, "output": args.output}, "dry_run": args.dry_run}
    if name == "clip":
        return {"action": "clip", "params": {"input_layer_id": args.input_layer_id, "overlay_layer_id": args.overlay_layer_id, "output": args.output}, "dry_run": args.dry_run}
    if name == "dissolve":
        return {"action": "dissolve", "params": {"layer_id": args.layer_id, "fields": args.field, "output": args.output}, "dry_run": args.dry_run}
    if name == "reproject-layer":
        return {"action": "reproject_layer", "params": {"layer_id": args.layer_id, "target_crs": args.target_crs, "output": args.output}, "dry_run": args.dry_run}
    if name == "export-layer":
        return {"action": "export_layer", "params": {"layer_id": args.layer_id, "output_path": project_path(args.output_path), "format": args.format, "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "add-layout-map":
        return {"action": "add_layout_map", "params": {"layout_name": args.layout, "layer_id": args.layer_id, "item_id": args.item_id}, "dry_run": args.dry_run}
    if name == "set-layout-extent":
        params = {"layout_name": args.layout, "map_item_id": args.map_item, "margin_percent": args.margin_percent}
        if args.layer_id:
            params["layer_id"] = args.layer_id
        return {"action": "set_layout_extent", "params": params, "dry_run": args.dry_run}
    if name == "add-layout-label":
        return {"action": "add_layout_label", "params": {"layout_name": args.layout, "text": args.text, "item_id": args.item_id}, "dry_run": args.dry_run}
    if name == "add-layout-legend":
        params = {"layout_name": args.layout, "linked_map_item_id": args.map_item, "filter_to_map_layers": True}
        if args.layer_id:
            params["legend_layers"] = args.layer_id
        return {"action": "add_layout_legend", "params": params, "dry_run": args.dry_run}
    if name == "add-layout-scale-bar":
        return {"action": "add_layout_scale_bar", "params": {"layout_name": args.layout, "linked_map_item_id": args.map_item}, "dry_run": args.dry_run}
    if name == "add-layout-north-arrow":
        return {"action": "add_layout_north_arrow", "params": {"layout_name": args.layout}, "dry_run": args.dry_run}
    if name == "add-layout-grid":
        return {"action": "add_layout_grid", "params": {"layout_name": args.layout, "map_item_id": args.map_item, "interval_x": args.interval_x, "interval_y": args.interval_y}, "dry_run": args.dry_run}
    if name == "add-layout-picture":
        return {"action": "add_layout_picture", "params": {"layout_name": args.layout, "path": project_path(args.path), "item_id": args.item_id}, "dry_run": args.dry_run}
    if name == "set-layer-style":
        return {"action": "set_layer_style", "params": {"layer_id": args.layer_id, "fill_color": args.fill_color, "stroke_color": args.stroke_color, "stroke_width": args.stroke_width, "opacity": args.opacity}, "dry_run": args.dry_run}
    if name == "basic-map":
        params = {"layer_id": args.layer_id, "title": args.title, "output_path": project_path(args.output), "format": args.format, "include_grid": args.include_grid, "logo_path": project_path(args.logo_path) if args.logo_path else "", "confirm_overwrite": args.confirm_overwrite, "layout_template": args.layout_template, "map_author": args.map_author, "organization": args.organization, "data_source": args.data_source}
        if args.legend_layer:
            params["legend_layers"] = args.legend_layer
        return {"action": "generate_basic_map", "params": params, "dry_run": args.dry_run}
    if name == "layout-templates":
        return {"action": "list_layout_templates"}
    if name == "professional-map":
        params = {"layer_id": args.layer_id, "title": args.title, "subtitle": args.subtitle, "output_path": project_path(args.output), "format": args.format, "layout_template": args.layout_template, "style_profile": args.style_profile, "confirm_overwrite": args.confirm_overwrite, "map_author": args.map_author, "organization": args.organization, "data_source": args.data_source}
        if args.legend_layer:
            params["legend_layers"] = args.legend_layer
        return {"action": "generate_professional_map", "params": params, "dry_run": args.dry_run}
    if name == "layer-tree":
        return {"action": "list_layer_tree"}
    if name == "set-layer-visibility":
        return {"action": "set_layer_visibility", "params": {"layer_id": args.layer_id, "visible": not args.hidden}, "dry_run": args.dry_run}
    if name == "move-layer-order":
        return {"action": "move_layer_order", "params": {"layer_id": args.layer_id, "index": args.index}, "dry_run": args.dry_run}
    if name == "list-fields":
        return {"action": "list_fields", "params": {"layer_id": args.layer_id}}
    if name == "sample-features":
        return {"action": "sample_features", "params": {"layer_id": args.layer_id, "max_features": args.max_features}}
    if name == "field-statistics":
        return {"action": "field_statistics", "params": {"layer_id": args.layer_id, "field_name": args.field}}
    if name == "unique-values":
        return {"action": "unique_values", "params": {"layer_id": args.layer_id, "field_name": args.field, "limit": args.limit}}
    if name == "validate-expression":
        params = {"expression": args.expression}
        if args.layer_id:
            params["layer_id"] = args.layer_id
        return {"action": "validate_expression", "params": params}
    if name == "query-features":
        return {"action": "query_features", "params": {"layer_id": args.layer_id, "expression": args.expression, "max_features": args.max_features}}
    if name == "select-by-expression":
        return {"action": "select_by_expression", "params": {"layer_id": args.layer_id, "expression": args.expression}, "dry_run": args.dry_run}
    if name == "extract-by-expression":
        return {"action": "extract_by_expression", "params": {"layer_id": args.layer_id, "expression": args.expression, "output": project_path(args.output)}, "dry_run": args.dry_run}
    if name == "intersection":
        return {"action": "intersection", "params": {"input_layer_id": args.input_layer_id, "overlay_layer_id": args.overlay_layer_id, "output": args.output}, "dry_run": args.dry_run}
    if name == "centroids":
        return {"action": "centroids", "params": {"layer_id": args.layer_id, "output": args.output}, "dry_run": args.dry_run}
    if name == "workflow-report":
        return {"action": "generate_workflow_report", "params": {"output_path": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "evaluate-layout":
        params = {"layout_name": args.layout}
        if args.output:
            params["output_path"] = project_path(args.output)
        return {"action": "evaluate_layout_cartographic_completeness", "params": params}
    if name == "map-quality":
        params = {"layout_name": args.layout}
        if args.output:
            params["output_path"] = project_path(args.output)
        return {"action": "evaluate_map_quality", "params": params}
    if name == "processing-providers":
        return {"action": "list_processing_providers"}
    if name == "processing-algorithms":
        return {"action": "list_processing_algorithms", "params": {"provider": args.provider, "filter": args.filter, "safe_only": not args.all}}
    if name == "processing-algorithm-info":
        return {"action": "get_processing_algorithm_info", "params": {"algorithm_id": args.algorithm_id}}
    if name == "recommend-qgis-tool":
        return {"action": "recommend_qgis_tool", "params": {"goal": args.goal}}
    if name == "plugins-extended":
        return {"action": "list_qgis_plugins_extended"}
    if name == "plugin-manifest":
        params = {"max_algorithms": args.max_algorithms, "include_inactive": not args.active_only}
        if args.plugin_name:
            params["plugin_name"] = args.plugin_name
        return {"action": "build_plugin_capability_manifest", "params": params}
    if name == "plugin-algorithm-plan":
        return {"action": "dry_run_plugin_algorithm_generic", "params": {"algorithm_id": args.algorithm_id, "parameters": json.loads(args.parameters_json)}}
    if name == "plugin-algorithm-run":
        return {"action": "run_plugin_algorithm_generic_safe", "params": {"algorithm_id": args.algorithm_id, "parameters": json.loads(args.parameters_json), "confirm_network": args.confirm_network, "confirm_generic_plugin_run": args.confirm_generic_plugin_run, "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "get-user-profile":
        return {"action": "get_user_profile"}
    if name == "set-user-profile":
        return {"action": "set_user_profile", "params": {"default_map_author": args.map_author, "default_map_author_email": args.map_author_email, "default_organization": args.organization, "default_credit_line": args.default_credit_line}, "dry_run": args.dry_run}
    if name == "clear-user-profile":
        return {"action": "clear_user_profile", "dry_run": args.dry_run}
    if name == "load-raster":
        params = {"path": project_path(args.path)}
        if args.name:
            params["name"] = args.name
        return {"action": "load_raster_layer", "params": params, "dry_run": args.dry_run}
    if name == "raster-info":
        return {"action": "raster_info", "params": {"layer_id": args.layer_id}}
    if name == "raster-band-statistics":
        return {"action": "raster_band_statistics", "params": {"layer_id": args.layer_id, "band": args.band}}
    if name == "raster-metadata-report":
        return {"action": "raster_metadata_report", "params": {"layer_id": args.layer_id}}
    if name == "raster-hillshade":
        return {"action": "raster_hillshade", "params": {"layer_id": args.layer_id, "output": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "raster-slope":
        return {"action": "raster_slope", "params": {"layer_id": args.layer_id, "output": project_path(args.output), "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "get-logs":
        return {"action": "get_logs", "params": {"tail": args.tail}}
    if name == "recent-errors":
        return {"action": "get_recent_errors", "params": {"tail": args.tail}}
    if name == "inspect-plugin":
        return {"action": "inspect_plugin", "params": {"plugin_name": args.plugin_name}}
    if name == "validate-metadata":
        return {"action": "validate_metadata_txt", "params": {"plugin_name": args.plugin_name}}
    if name == "plugin-structure":
        return {"action": "check_plugin_structure", "params": {"plugin_name": args.plugin_name}}
    if name == "plugin-imports":
        return {"action": "check_plugin_imports", "params": {"plugin_name": args.plugin_name}}
    if name == "plugin-resources":
        return {"action": "check_plugin_resources", "params": {"plugin_name": args.plugin_name}}
    if name == "plugin-icon":
        return {"action": "check_plugin_icon", "params": {"plugin_name": args.plugin_name}}
    if name == "plugin-report":
        params = {"plugin_name": args.plugin_name}
        if args.output_path:
            params["output_path"] = project_path(args.output_path)
        return {"action": "generate_plugin_report", "params": params}
    if name == "package-plugin":
        return {"action": "package_plugin_zip", "params": {"plugin_name": args.plugin_name, "output_path": project_path(args.output_path), "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "plugin-repo-search":
        return {"action": "search_qgis_plugin_repository", "params": {"query": args.query, "qgis_version": args.qgis_version, "limit": args.limit, "confirm_network": args.confirm_network}}
    if name == "plugin-repo-download":
        return {"action": "download_qgis_plugin_zip", "params": {"plugin_name": args.plugin_name, "output_path": project_path(args.output_path), "qgis_version": args.qgis_version, "confirm_network": args.confirm_network, "confirm_plugin_write": args.confirm, "confirm_overwrite": args.confirm_overwrite}, "dry_run": args.dry_run}
    if name == "inspect-plugin-zip":
        return {"action": "inspect_qgis_plugin_zip", "params": {"zip_path": project_path(args.zip_path)}}
    if name == "install-plugin-zip":
        return {"action": "install_plugin_from_zip", "params": {"zip_path": project_path(args.zip_path), "plugin_name": args.plugin_name, "confirm_plugin_write": args.confirm, "update": args.update}, "dry_run": args.dry_run}
    if name == "install-plugin-repository":
        return {"action": "install_qgis_plugin_from_repository", "params": {"plugin_name": args.plugin_name, "qgis_version": args.qgis_version, "confirm_network": args.confirm_network, "confirm_plugin_write": args.confirm, "update": args.update}, "dry_run": args.dry_run}
    if name == "self-backup":
        return {"action": "self_backup", "dry_run": args.dry_run}
    if name == "self-validate-update":
        return {"action": "self_validate_update", "params": {"source_folder": project_path(args.source_folder)}}
    if name == "self-stage-update":
        return {"action": "self_stage_update", "params": {"source_folder": project_path(args.source_folder), "confirm": args.confirm}, "dry_run": args.dry_run}
    if name == "self-apply-update":
        return {"action": "self_apply_update", "params": {"confirm_self_apply_update": args.confirm}, "dry_run": args.dry_run}
    if name == "self-rollback":
        return {"action": "self_rollback", "params": {"backup_path": project_path(args.backup_path), "confirm": args.confirm, "confirm_rollback": args.confirm}, "dry_run": args.dry_run}
    if name == "command":
        parsed = json.loads(args.json)
        if not isinstance(parsed, dict):
            raise SigmaiClientError("--json must decode to a JSON object.")
        return parsed
    if name == "bridge-status":
        return None
    raise SigmaiClientError(f"Unsupported command: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = SigmaiClient(host=args.host, port=args.port, token=args.token, pairing_code=args.pairing_code, session_file=args.session_file)
    try:
        payload = payload_for_args(args)
        response = client.status_endpoint() if payload is None else client.command(payload)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0 if response.get("ok", True) else 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
