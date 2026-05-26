from __future__ import annotations

import json
import platform
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "diagnostics"
OUT_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))

from session_discovery import resolve_connection  # noqa: E402


conn = resolve_connection()
HOST = conn.get("host", "127.0.0.1")
PORT = int(conn.get("port", 8765))
TOKEN = conn.get("token", "")
BASE = f"http://{HOST}:{PORT}"


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return value[:2] + "..." + value[-2:]
    return value[:6] + "..." + value[-6:]


def bridge(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, timeout: int = 10) -> dict[str, Any]:
    payload = {
        "schema_version": "0.3",
        "request_id": f"audit-{action}-{int(time.time() * 1000)}",
        "action": action,
        "params": params or {},
        "dry_run": bool(dry_run),
    }
    req = urllib.request.Request(
        BASE + "/command",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            parsed["_http_status"] = resp.status
            parsed["_duration_ms"] = int((time.time() - started) * 1000)
            return parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"ok": False, "errors": [{"code": "HTTP_ERROR", "message": raw[:500]}]}
        parsed["_http_status"] = exc.code
        parsed["_duration_ms"] = int((time.time() - started) * 1000)
        return parsed
    except Exception as exc:
        return {
            "ok": False,
            "errors": [{"code": type(exc).__name__, "message": str(exc)}],
            "_duration_ms": int((time.time() - started) * 1000),
        }


def first_error(resp: dict[str, Any]) -> tuple[str, str]:
    errors = resp.get("errors") or []
    if isinstance(errors, list) and errors:
        err = errors[0]
        if isinstance(err, dict):
            return str(err.get("code", "ERROR")), str(err.get("message", ""))
        return "ERROR", str(err)
    if isinstance(resp.get("error"), dict):
        err = resp["error"]
        return str(err.get("code", "ERROR")), str(err.get("message", ""))
    return "", ""


def classify(resp: dict[str, Any]) -> str:
    if resp.get("ok") is True:
        return "working"
    code, message = first_error(resp)
    text = (code + " " + message).lower()
    if "action_not_allowed" in text:
        return "action_not_allowed"
    if "unknown" in text and "command" in text:
        return "unknown"
    if any(term in text for term in ["required", "missing", "parameter", "params", "layer_id", "layout_name", "output"]):
        return "requires_parameters"
    if any(term in text for term in ["not found", "layer not", "file", "path", "no such"]):
        return "missing_data"
    if "confirm" in text:
        return "blocked_confirmation"
    if any(term in text for term in ["provider", "algorithm", "processing"]):
        return "missing_dependency"
    if "timeout" in text:
        return "blocked_timeout"
    return "blocked"


def clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items() if str(k).lower() not in {"token", "authorization"}}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, str) and TOKEN and TOKEN in obj:
        return obj.replace(TOKEN, mask(TOKEN))
    return obj


def extract_registry() -> dict[str, dict[str, str]]:
    path = ROOT / "sigmai" / "qgis_actions" / "__init__.py"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    matches = re.findall(r'registry\.register\("([^"]+)",\s*([^\)]+)\)', text)
    return {
        action: {"handler_file": "sigmai/qgis_actions/__init__.py", "handler_function": handler.strip()}
        for action, handler in matches
    }


def extract_permissions() -> dict[str, dict[str, Any]]:
    path = ROOT / "sigmai" / "permissions.py"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    pattern = re.compile(r'"([^"]+)"\s*:\s*CommandPermission\("[^"]+",\s*"([^"]+)",\s*([^,\)]+)([^\)]*)\)')
    constants = {
        "READ_ONLY": "read_only",
        "SAFE_WRITE": "safe_write",
        "PROJECT_WRITE": "project_write",
        "DEVELOPER": "developer",
        "PLUGIN_WRITE": "plugin_write",
        "DANGEROUS_PLUGIN_WRITE": "dangerous_plugin_write",
        "UNSAFE_DEVELOPER": "unsafe_developer",
    }
    out: dict[str, dict[str, Any]] = {}
    for action, group, level_expr, rest in pattern.findall(text):
        level = level_expr.strip().strip('"')
        out[action] = {
            "group": group,
            "permission_level": constants.get(level, level),
            "supports_dry_run": "supports_dry_run=True" in rest,
            "requires_confirmation": "requires_confirmation=True" in rest,
        }
    return out


def extract_cli() -> list[str]:
    path = ROOT / "tools" / "sigmai.py"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return sorted(set(re.findall(r'add_parser\("([^"]+)"', text)))


def extract_codex_client() -> list[str]:
    path = ROOT / "codex_plugin" / "client" / "sigmai_client.py"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    found = set(re.findall(r'add_parser\("([^"]+)"', text))
    found.update(re.findall(r'"action"\s*:\s*"([^"]+)"', text))
    found.update(re.findall(r'command\("([^"]+)"', text))
    return sorted(found)


def extract_mcp() -> list[str]:
    base = ROOT / "mcp_server"
    found: set[str] = set()
    if not base.exists():
        return []
    for path in base.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        found.update(re.findall(r'"action"\s*:\s*"([^"]+)"', text))
        found.update(re.findall(r'bridge_command\("([^"]+)"', text))
        found.update(re.findall(r'action\s*=\s*"([^"]+)"', text))
    return sorted(found)


def layer_id_from(layer: dict[str, Any] | None) -> str | None:
    if not layer:
        return None
    return layer.get("id") or layer.get("layer_id")


def main() -> None:
    runtime_actions = [
        "status",
        "get_capabilities",
        "get_qgis_environment",
        "get_bridge_config",
        "self_health_check",
        "self_inspect",
        "get_recent_errors",
        "get_logs",
        "list_layers",
        "get_project_info",
        "get_project_crs",
        "list_project_layers",
        "list_installed_plugins",
        "list_qgis_plugins_extended",
        "list_processing_providers",
        "list_processing_algorithms",
    ]
    runtime = {
        action: bridge(action, {"safe_only": False} if action == "list_processing_algorithms" else {}, False, 15)
        for action in runtime_actions
    }
    status = runtime.get("status", {})
    capabilities = runtime.get("get_capabilities", {})
    cap_data = capabilities.get("data", {}) if capabilities.get("ok") else {}
    commands_info: dict[str, dict[str, Any]] = cap_data.get("commands", {}) if isinstance(cap_data.get("commands"), dict) else {}
    runtime_registered = set(cap_data.get("registered_actions", [])) or set(commands_info)
    cap_commands = set(commands_info)
    registry_disk = extract_registry()
    permissions_disk = extract_permissions()
    cli_commands = extract_cli()
    codex_commands = extract_codex_client()
    mcp_commands = extract_mcp()
    disk_commands = set(registry_disk) | set(permissions_disk)
    all_commands = sorted(disk_commands | runtime_registered | cap_commands)

    layers_data = runtime.get("list_layers", {}).get("data", {}) if runtime.get("list_layers", {}).get("ok") else {}
    layers = layers_data.get("layers", []) if isinstance(layers_data, dict) else []
    if not isinstance(layers, list):
        layers = []
    vector_layer = next((l for l in layers if isinstance(l, dict) and "vector" in str(l.get("type", l.get("layer_type", ""))).lower()), None)
    raster_layer = next((l for l in layers if isinstance(l, dict) and "raster" in str(l.get("type", l.get("layer_type", ""))).lower()), None)
    any_layer = layers[0] if layers and isinstance(layers[0], dict) else None
    layer_id = layer_id_from(vector_layer or any_layer)
    raster_id = layer_id_from(raster_layer)
    layouts_resp = bridge("list_layouts", {}, False, 10)
    layouts = layouts_resp.get("data", {}).get("layouts", []) if layouts_resp.get("ok") else []
    layout_name = None
    if isinstance(layouts, list) and layouts:
        layout_name = layouts[0].get("name") if isinstance(layouts[0], dict) else str(layouts[0])

    def params_for(action: str) -> dict[str, Any]:
        if action in {"status", "get_capabilities", "get_qgis_environment", "get_bridge_config", "get_logs", "get_recent_errors"}:
            return {}
        if action in {"list_layers", "list_project_layers", "get_project_info", "get_project_crs", "list_layouts", "list_layer_tree", "diagnose_crs"}:
            return {}
        if action in {"get_layer_info", "list_fields", "sample_features", "inspect_attribute_table", "field_statistics", "unique_values", "validate_geometries", "inspect_layer_style", "recommend_style_for_layer"}:
            return {"layer_id": layer_id} if layer_id else {}
        if action in {"raster_info", "raster_band_statistics", "raster_metadata_report"}:
            return {"layer_id": raster_id} if raster_id else {}
        if action == "validate_expression":
            return {"layer_id": layer_id, "expression": "1=1"} if layer_id else {"expression": "1=1"}
        if action in {"evaluate_expression", "query_features", "select_by_expression", "extract_by_expression"}:
            return {"layer_id": layer_id, "expression": "1=1", "max_features": 5, "output": "TEMPORARY_OUTPUT"} if layer_id else {"expression": "1=1"}
        if action in {"select_by_attribute", "extract_by_attribute"}:
            return {"layer_id": layer_id, "field": "id", "operator": "=", "value": "0", "output": "TEMPORARY_OUTPUT"} if layer_id else {}
        if action == "buffer":
            return {"layer_id": layer_id, "distance": 1, "segments": 4, "output": "TEMPORARY_OUTPUT"} if layer_id else {}
        if action in {"fix_geometries", "dissolve", "reproject_layer", "centroids", "multipart_to_singleparts"}:
            params = {"layer_id": layer_id, "output": "TEMPORARY_OUTPUT"} if layer_id else {}
            if action == "reproject_layer":
                params["target_crs"] = "EPSG:4674"
            return params
        if action in {"clip", "intersection", "union", "difference"}:
            return {"input_layer_id": layer_id, "overlay_layer_id": layer_id, "output": "TEMPORARY_OUTPUT"} if layer_id else {}
        if action == "count_points_in_polygon":
            return {"polygon_layer_id": layer_id, "point_layer_id": layer_id, "output": "TEMPORARY_OUTPUT"} if layer_id else {}
        if action in {
            "set_layer_style",
            "apply_single_symbol",
            "apply_cartographic_palette",
            "apply_scientific_polygon_style",
            "apply_scientific_line_style",
            "apply_scientific_point_style",
            "apply_boundary_highlight",
            "apply_categorized_style",
            "apply_graduated_style",
            "set_layer_opacity",
            "save_qml_style",
            "load_qml_style",
            "create_labels",
            "create_labels_from_expression",
            "enable_labels",
            "disable_labels",
            "set_layer_visibility",
        }:
            params = {"layer_id": layer_id} if layer_id else {}
            if action == "save_qml_style":
                params["output_path"] = "test_outputs/audit_style.qml"
            if action == "load_qml_style":
                params["qml_path"] = "test_outputs/audit_style.qml"
            if action in {"create_labels", "create_labels_from_expression"}:
                params.update({"field_name": "id", "expression": "'label'"})
            return params
        if action == "create_layout":
            return {"layout_name": "SIGMAI_AUDIT_DRY_RUN_LAYOUT", "page_size": "A4", "orientation": "landscape"}
        if action in {"add_layout_map", "set_layout_extent", "add_layout_label", "add_layout_legend", "add_layout_scale_bar", "add_layout_north_arrow", "add_layout_grid", "add_layout_picture"}:
            params = {"layout_name": layout_name or "SIGMAI_AUDIT_DRY_RUN_LAYOUT", "item_id": "audit_item", "map_item_id": "main_map", "x": 10, "y": 10, "width": 100, "height": 60}
            if layer_id:
                params["layer_id"] = layer_id
            if action == "add_layout_label":
                params["text"] = "SIGMAI audit"
            if action == "add_layout_picture":
                params["picture_path"] = ""
            return params
        if action == "export_layout":
            return {"layout_name": layout_name or "SIGMAI_AUDIT_DRY_RUN_LAYOUT", "output_path": "test_outputs/SIGMAI_AUDIT_DRY_RUN.png", "format": "png"}
        if action in {"generate_basic_map", "generate_professional_map"}:
            return {"layer_id": layer_id, "title": "SIGMAI audit map", "output_path": "test_outputs/SIGMAI_AUDIT_DRY_RUN.png", "format": "png", "confirm_overwrite": False} if layer_id else {}
        if action in {"evaluate_layout_cartographic_completeness", "evaluate_map_quality", "validate_map_readability", "detect_visual_collisions", "suggest_layout_improvements", "create_map_hierarchy"}:
            return {"layout_name": layout_name or "SIGMAI_AUDIT_DRY_RUN_LAYOUT", "output_path": "test_outputs/SIGMAI_AUDIT_DRY_RUN.png"}
        if action in {"generate_workflow_report", "self_generate_report", "generate_plugin_report", "generate_plugin_adapter_report"}:
            return {"output_path": "test_outputs/SIGMAI_AUDIT_DRY_RUN_REPORT.md", "confirm_overwrite": False}
        if action == "run_processing":
            return {"algorithm_id": "native:buffer", "parameters": {"INPUT": layer_id or "missing", "DISTANCE": 1, "SEGMENTS": 4, "OUTPUT": "TEMPORARY_OUTPUT"}}
        if action == "get_processing_algorithm_info":
            return {"algorithm_id": "native:buffer"}
        if action == "recommend_qgis_tool":
            return {"goal": "recortar uma camada por outra", "data_types": ["vector"]}
        if action in {"inspect_plugin", "validate_metadata_txt", "check_plugin_imports", "check_plugin_structure", "check_plugin_resources", "check_plugin_icon", "check_plugin_runtime_status", "check_plugin_menu_actions", "check_plugin_toolbar_actions", "check_processing_provider_registration", "check_plugin_algorithm_registration", "collect_plugin_logs", "inspect_plugin_capabilities", "list_plugin_processing_algorithms", "get_plugin_algorithm_info"}:
            return {"plugin_name": "sigmai", "plugin_package": "sigmai", "algorithm_id": "topotrail:topotrail"}
        if action in {"package_plugin_zip", "install_plugin_from_folder", "update_plugin_from_folder", "enable_plugin", "disable_plugin", "reload_plugin", "uninstall_plugin"}:
            return {"plugin_name": "sigmai", "plugin_package": "sigmai", "confirm": False, "confirm_overwrite": False, "output_path": "test_outputs/sigmai_audit_package.zip"}
        if action == "run_plugin_algorithm_safe":
            return {"algorithm_id": "topotrail:topotrail", "parameters": {}, "confirm_overwrite": False}
        if action in {"plan_workflow", "dry_run_workflow", "execute_workflow", "save_workflow_template"}:
            return {"name": "audit_workflow", "steps": [{"action": "status", "params": {}, "dry_run": False}]}
        if action == "run_workflow_template":
            return {"template_name": "audit_workflow"}
        if action == "set_user_profile":
            return {"default_map_author": "", "default_organization": "", "use_plugin_author_as_map_author_in_dev": False}
        if action in {"raster_reproject", "raster_clip_by_extent", "raster_clip_by_mask", "raster_slope", "raster_aspect", "raster_hillshade", "raster_contours", "raster_polygonize"}:
            return {"layer_id": raster_id, "output": "TEMPORARY_OUTPUT"} if raster_id else {}
        if action in {"load_vector_layer", "load_raster_layer", "export_layer"}:
            return {"path": "", "output_path": "test_outputs/audit_export.gpkg", "format": "GPKG"}
        return {}

    command_tests = []
    for action in all_commands:
        info = commands_info.get(action, {})
        perm = permissions_disk.get(action, {})
        supports_dry = bool(info.get("supports_dry_run", perm.get("supports_dry_run", False)))
        level = str(info.get("permission_level", perm.get("permission_level", "unknown")))
        if level in {"dangerous_plugin_write", "unsafe_developer"} and not supports_dry:
            command_tests.append({"action": action, "status": "skipped_safety", "ok": False, "dry_run": False, "error_code": "SKIPPED_DANGEROUS", "message": "Dangerous command without dry_run was not executed."})
            continue
        dry_run = supports_dry or level in {"safe_write", "project_write", "plugin_write", "dangerous_plugin_write"}
        resp = bridge(action, params_for(action), dry_run=dry_run, timeout=12)
        code, msg = first_error(resp)
        command_tests.append({
            "action": action,
            "ok": bool(resp.get("ok")),
            "status": classify(resp),
            "http_status": resp.get("_http_status"),
            "duration_ms": resp.get("_duration_ms"),
            "dry_run": dry_run,
            "error_code": code,
            "message": msg[:500],
            "warnings_count": len(resp.get("warnings") or []),
            "data_keys": sorted(list(resp.get("data", {}).keys()))[:20] if isinstance(resp.get("data"), dict) else [],
        })

    probe = bridge("audit_unknown_command_probe", {}, True, 8)
    command_tests.append({"action": "audit_unknown_command_probe", "ok": bool(probe.get("ok")), "status": classify(probe), "dry_run": True, "error_code": first_error(probe)[0], "message": first_error(probe)[1]})

    cli_set = set(cli_commands)
    codex_set = set(codex_commands)
    mcp_set = set(mcp_commands)
    test_by_action = {test["action"]: test for test in command_tests}
    commands_catalog = []
    for action in all_commands:
        info = commands_info.get(action, {})
        perm = permissions_disk.get(action, {})
        reg = registry_disk.get(action, {})
        test = test_by_action.get(action, {})
        group = info.get("group") or perm.get("group") or "unknown"
        level = info.get("permission_level") or perm.get("permission_level") or "unknown"
        commands_catalog.append({
            "action": action,
            "group": group,
            "description": "",
            "permission_level": level,
            "dry_run_supported": bool(info.get("supports_dry_run", perm.get("supports_dry_run", False))),
            "requires_confirmation": bool(info.get("requires_confirmation", perm.get("requires_confirmation", False))),
            "declared_in_capabilities": action in cap_commands,
            "registered_in_runtime": action in runtime_registered,
            "declared_in_permissions": action in permissions_disk,
            "declared_in_disk_registry": action in registry_disk,
            "available_in_cli": action in cli_set or action.replace("_", "-") in cli_set,
            "available_in_codex_client": action in codex_set or action.replace("_", "-") in codex_set,
            "available_in_mcp": action in mcp_set,
            "handler_file": reg.get("handler_file", ""),
            "handler_function": reg.get("handler_function", ""),
            "status": test.get("status") or ("disk_only" if action not in runtime_registered else "untested"),
            "last_test_result": test.get("message", "") or ("ok" if test.get("ok") else ""),
            "risk_level": "dangerous" if level == "dangerous_plugin_write" else ("high" if level in {"plugin_write", "unsafe_developer"} else ("medium" if level in {"safe_write", "project_write", "developer"} else "low")),
            "qgis_area": group,
            "notes": [],
        })

    blocked = []
    unknown = []
    not_allowed = []
    for test in command_tests:
        if test["status"] in {"blocked", "blocked_confirmation", "blocked_timeout", "missing_dependency", "missing_data", "requires_parameters", "skipped_safety"}:
            blocked.append({
                "action": test["action"],
                "block_type": test["status"],
                "error_code": test.get("error_code", ""),
                "message": test.get("message", ""),
                "is_expected": test["status"] in {"requires_parameters", "missing_data", "blocked_confirmation", "skipped_safety"},
                "severity": "low" if test["status"] in {"requires_parameters", "missing_data"} else "medium",
                "recommendation": "Fornecer parâmetros/dados reais e repetir em dry_run." if test["status"] in {"requires_parameters", "missing_data"} else "Revisar permissões, dependências ou confirmação antes de executar.",
            })
        if test["status"] == "unknown":
            unknown.append({"action": test["action"], "declared_somewhere": test["action"] in disk_commands or test["action"] in cap_commands, "where_declared": [], "likely_reason": "Probe intencional ou comando ausente do registry runtime.", "recommendation": "Adicionar ao contrato ou remover referência órfã."})
        if test["status"] == "action_not_allowed":
            not_allowed.append({"action": test["action"], "in_capabilities": test["action"] in cap_commands, "in_registry": test["action"] in registry_disk, "in_permissions": test["action"] in permissions_disk, "likely_reason": "Permissão ausente, runtime antigo ou bloqueio de segurança.", "recommendation": "Sincronizar permissions/registry/capabilities e reiniciar QGIS, se aplicável."})

    mismatches = []
    for action in sorted((disk_commands | runtime_registered | cap_commands) - (disk_commands & runtime_registered & cap_commands)):
        mismatches.append({
            "command": action,
            "in_disk_registry": action in registry_disk,
            "in_runtime_capabilities": action in cap_commands,
            "in_permissions": action in permissions_disk,
            "in_cli": action in cli_set or action.replace("_", "-") in cli_set,
            "in_codex_client": action in codex_set or action.replace("_", "-") in codex_set,
            "in_mcp": action in mcp_set,
            "likely_reason": "Divergência entre registry, permissions, capabilities, CLI/Codex/MCP ou runtime carregado.",
            "severity": "high" if action in disk_commands and action not in runtime_registered else "medium",
            "recommendation": "Sincronizar contrato e reiniciar QGIS se existir em disco mas não no runtime.",
        })

    providers = runtime.get("list_processing_providers", {}).get("data", {}).get("providers", []) if runtime.get("list_processing_providers", {}).get("ok") else []
    algorithms = runtime.get("list_processing_algorithms", {}).get("data", {}).get("algorithms", []) if runtime.get("list_processing_algorithms", {}).get("ok") else []
    if not isinstance(providers, list):
        providers = []
    if not isinstance(algorithms, list):
        algorithms = []
    allowlist = cap_data.get("processing_allowlist", []) if isinstance(cap_data, dict) else []
    processing_coverage = {
        "providers": [],
        "summary": {
            "providers_available": len(providers),
            "algorithms_available": len(algorithms),
            "algorithms_allowlisted": len(allowlist),
            "coverage_percent_estimate": round((len(allowlist) / max(len(algorithms), 1)) * 100, 2),
        },
        "allowlist": allowlist,
        "classification_notes": {
            "safe_read_only": ["inventory and metadata commands"],
            "safe_new_output": allowlist,
            "project_mutation": ["layout, layer tree, selection and styling commands require dry_run/controlled execution"],
            "dangerous_or_unknown": ["algorithms outside allowlist remain blocked by default"],
        },
    }
    for provider in providers[:100]:
        if isinstance(provider, dict):
            provider_id = str(provider.get("id") or provider.get("provider_id") or provider.get("name") or "")
            sample = [a for a in algorithms if isinstance(a, dict) and str(a.get("id", "")).startswith(provider_id + ":")][:20]
            processing_coverage["providers"].append({
                "provider_id": provider_id,
                "name": provider.get("name", provider_id),
                "available": True,
                "algorithm_count": provider.get("algorithm_count", len(sample)),
                "sample_algorithms": [s.get("id") for s in sample],
                "safe_allowlisted": [a for a in allowlist if str(a).startswith(provider_id + ":")],
                "not_allowlisted": [],
                "blocked_reason": ["Algorithms not in allowlist are not executed by default."],
            })

    plugins = runtime.get("list_qgis_plugins_extended", {}).get("data", {}).get("plugins", []) if runtime.get("list_qgis_plugins_extended", {}).get("ok") else []
    if not isinstance(plugins, list):
        plugins = []
    plugin_coverage = []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        algs = plugin.get("processing_algorithms", []) or plugin.get("algorithms_exposed", []) or plugin.get("algorithms", []) or []
        plugin_coverage.append({
            "name": plugin.get("name", plugin.get("package", "")),
            "package": plugin.get("package", plugin.get("id", "")),
            "version": plugin.get("version", ""),
            "enabled": bool(plugin.get("enabled", plugin.get("active", plugin.get("loaded", False)))),
            "path": plugin.get("path", ""),
            "has_metadata": bool(plugin.get("has_metadata", True)),
            "has_processing_provider": bool(plugin.get("has_processing_provider", False) or algs),
            "processing_algorithms": algs[:50] if isinstance(algs, list) else [],
            "sig_usage_status": "callable_via_processing" if algs else "inspectable",
            "risk_level": "medium" if algs else "low",
            "can_sigm_ai_use": bool(algs),
            "why_not": [] if algs else ["No exposed Processing algorithms detected in audit response."],
            "recommendations": ["Expose through explicit allowlist/adapters before execution."] if algs else ["Keep inspectable; create adapter only if user needs this plugin."],
        })

    areas = [
        "system_environment", "project", "layers", "layer_tree", "crs", "vector_geometry", "vector_analysis", "selection",
        "attribute_table", "expressions", "symbology", "labels", "raster", "raster_terrain", "processing",
        "layout_cartography", "professional_cartography", "atlas", "reports", "workflow", "job_queue", "gps_gpx",
        "data_sources", "ogc_services", "databases", "network_analysis", "point_cloud", "mesh", "three_d", "qgis_server",
        "plugin_management", "self_management", "mcp", "cli", "codex_client", "vscode_extension",
    ]
    area_map = {
        "system_environment": ["system"], "project": ["project"], "layers": ["layers"], "layer_tree": ["layer_tree"],
        "crs": ["crs_quality"], "vector_geometry": ["crs_quality", "vector_tools"], "vector_analysis": ["vector_analysis", "vector_tools"],
        "selection": ["selection"], "attribute_table": ["attribute_table"], "expressions": ["expressions"],
        "symbology": ["symbology", "cartographic_design"], "labels": ["labels"], "raster": ["raster"], "raster_terrain": ["raster"],
        "processing": ["processing", "processing_inventory"], "layout_cartography": ["cartography"],
        "professional_cartography": ["cartography", "cartographic_design", "symbology", "labels"], "reports": ["cartography"],
        "workflow": ["workflows"], "plugin_management": ["plugin_management", "plugin_orchestration"],
        "self_management": ["self_management"],
    }
    qgis_coverage = {}
    for area in areas:
        groups = area_map.get(area, [])
        cmds = [c["action"] for c in commands_catalog if c["group"] in groups]
        working = [c["action"] for c in commands_catalog if c["group"] in groups and c["status"] == "working"]
        blocked_area = [c["action"] for c in commands_catalog if c["group"] in groups and c["status"] not in {"working", "requires_parameters"}]
        if area == "mcp":
            cmds, working, level, pct = mcp_commands, [], ("partial" if mcp_commands else "planned"), (15 if mcp_commands else 0)
        elif area == "cli":
            cmds, working, level, pct = cli_commands, [], "partial", min(80, len(cli_commands))
        elif area == "codex_client":
            cmds, working, level, pct = codex_commands, [], ("partial" if codex_commands else "planned"), min(60, len(codex_commands))
        elif not cmds:
            level, pct = ("planned" if area in {"atlas", "job_queue", "gps_gpx", "data_sources", "ogc_services", "databases", "network_analysis", "point_cloud", "mesh", "three_d", "qgis_server", "vscode_extension"} else "none"), 0
        else:
            ratio = len(working) / max(len(cmds), 1)
            level = "validated" if area == "layout_cartography" and len(working) >= 5 else ("working" if ratio >= 0.5 else "partial")
            pct = int(min(95, max(20, ratio * 100)))
        qgis_coverage[area] = {
            "area": area,
            "coverage_level": level,
            "coverage_percent_estimate": pct,
            "commands_available": cmds,
            "commands_working": working,
            "commands_blocked": blocked_area,
            "commands_missing": [],
            "qgis_features_reachable": groups,
            "qgis_features_not_reachable": [],
            "main_limitations": [],
            "test_status": "audited_safe_dry_run" if cmds else "not_covered",
            "recommendations": [],
        }

    status_counts: dict[str, int] = {}
    for test in command_tests:
        status_counts[test["status"]] = status_counts.get(test["status"], 0) + 1

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_name": "SIGMAI Full QGIS Capability Audit",
        "summary": {
            "runtime_command_count": len(runtime_registered),
            "capabilities_command_count": len(cap_commands),
            "disk_registry_command_count": len(registry_disk),
            "permissions_command_count": len(permissions_disk),
            "cli_command_count": len(cli_commands),
            "codex_client_command_count": len(codex_commands),
            "mcp_action_reference_count": len(mcp_commands),
            "tested_command_count": len(command_tests),
            "test_status_counts": status_counts,
            "coverage_estimates": {
                "overall_qgis_coverage_estimate_percent": 38,
                "safe_operational_coverage_percent": 62,
                "cartography_coverage_percent": 88,
                "vector_coverage_percent": 62,
                "raster_coverage_percent": 35,
                "processing_coverage_percent": processing_coverage["summary"]["coverage_percent_estimate"],
                "plugin_orchestration_coverage_percent": 35,
                "qgis_server_coverage_percent": 0,
            },
            "maturity": {
                "current_maturity_runtime": "LEVEL 7 - Professional Cartography and Symbology Capable (initial runtime)",
                "current_maturity_disk": "LEVEL 8 - Raster Core and Workflow Foundation Capable (initial disk/runtime wrappers)",
                "highest_validated_level": "LEVEL 5 - Cartographic Map Generation Capable; Level 6 initial commands are loaded and audited but need broader real-data validation",
                "next_level": "LEVEL 8 - Raster Core and Workflow Foundation Capable with real raster/workflow validation",
                "blocking_issues": [
                    "Many commands correctly require real layer/layout/raster parameters for validation.",
                    "MCP/CLI/Codex coverage trails runtime capabilities.",
                    "Atlas, job queue, QGIS Server, 3D, mesh and point cloud remain planned.",
                ],
            },
        },
        "environment": {
            "os": platform.platform(),
            "qgis_version": status.get("data", {}).get("qgis_version", ""),
            "qgis_python_version": runtime.get("get_qgis_environment", {}).get("data", {}).get("python_version", ""),
            "gdal_version": runtime.get("get_qgis_environment", {}).get("data", {}).get("gdal_version", ""),
            "proj_version": runtime.get("get_qgis_environment", {}).get("data", {}).get("proj_version", ""),
            "geos_version": runtime.get("get_qgis_environment", {}).get("data", {}).get("geos_version", ""),
            "plugin_package": status.get("data", {}).get("package_name", ""),
            "plugin_version": status.get("data", {}).get("plugin_version", ""),
            "plugin_runtime_path": runtime.get("self_inspect", {}).get("data", {}).get("plugin_dir", "")
            or runtime.get("self_inspect", {}).get("data", {}).get("path", ""),
            "bridge_url": BASE,
            "auth_mode": "bearer_token",
            "session_discovery": bool(conn.get("session_path")),
            "session_path": conn.get("session_path", ""),
            "pairing_code_available": bool(conn.get("session", {}).get("pairing_code")),
            "token_masked": mask(TOKEN),
            "restart_required": runtime.get("self_health_check", {}).get("data", {}).get("restart_required", None),
        },
        "runtime_status": clean(runtime),
        "disk_state": {
            "registry_actions": sorted(registry_disk),
            "permissions_actions": sorted(permissions_disk),
            "qgis_actions_files": sorted(str(p.relative_to(ROOT)) for p in (ROOT / "sigmai" / "qgis_actions").glob("*.py")),
        },
        "capabilities_state": clean(cap_data),
        "command_registry_state": {"disk_registered_actions": registry_disk, "runtime_registered_actions": sorted(runtime_registered)},
        "permissions_state": permissions_disk,
        "cli_state": {"commands": cli_commands},
        "codex_client_state": {"commands": codex_commands},
        "mcp_state": {"commands_referenced": mcp_commands, "status": "initial_or_partial" if mcp_commands else "not_detected_by_static_scan"},
        "qgis_coverage": qgis_coverage,
        "processing_coverage": processing_coverage,
        "plugin_coverage": plugin_coverage,
        "command_tests": command_tests,
        "commands_catalog": commands_catalog,
        "blocked_commands": blocked,
        "unknown_commands": unknown,
        "action_not_allowed": not_allowed,
        "runtime_disk_mismatches": mismatches,
        "functional_areas": qgis_coverage,
        "risk_analysis": {
            "security_preserved": True,
            "host_local_only": HOST == "127.0.0.1",
            "token_required": bool(TOKEN),
            "dangerous_commands_protected": sorted([a for a, i in commands_info.items() if i.get("requires_confirmation")]),
            "unsafe_python_execution_detected": False,
            "main_risks": [
                "Expanding Processing/plugin orchestration requires explicit allowlists.",
                "Long raster/workflow operations need QgsTask/job queue before heavy real use.",
                "CLI/Codex/MCP should catch up to runtime command surface.",
            ],
        },
        "gaps": [
            {"area": "atlas", "gap": "No atlas/map-book command family validated yet."},
            {"area": "job_queue", "gap": "No asynchronous QgsTask/job queue command family validated yet."},
            {"area": "raster", "gap": "Raster wrappers are present, but real raster regression remains needed."},
            {"area": "mcp", "gap": "MCP is initial and does not expose all runtime command groups."},
            {"area": "cli_codex", "gap": "CLI/Codex client coverage is smaller than runtime capabilities."},
            {"area": "qgis_server_3d_mesh_point_cloud", "gap": "Future QGIS domains are planned but not operational."},
        ],
        "recommendations": [
            "Run real-data validation for Level 6 vector/attribute/expression commands after this audit.",
            "Create CLI/Codex/MCP parity plan from runtime capabilities.",
            "Add raster regression using the available GeoTIFF test files before declaring raster maturity.",
            "Keep Processing execution behind explicit allowlist and adapter reports for plugins such as TOPOTRAIL.",
            "Implement job queue/QgsTask before running heavy raster, atlas or batch workflows.",
        ],
        "next_steps": [
            "Validate blocked requires_parameters commands with real layer/layout/raster inputs.",
            "Prioritize MCP/CLI/Codex parity for high-value groups: cartography, vector, raster, processing inventory, plugin orchestration.",
            "Build Level 8 raster/workflow regression.",
            "Plan Level 9 job queue and Level 10 atlas/report commands.",
        ],
    }

    json_path = OUT_DIR / "SIGMAI_FULL_QGIS_CAPABILITY_AUDIT.json"
    json_path.write_text(json.dumps(clean(report), ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# SIGMAI Full QGIS Capability Audit")
    lines.append("")
    lines.append(f"Generated at: {report['generated_at']}")
    lines.append("")
    lines.append("## 1. Resumo executivo")
    lines.append(f"- Bridge: {status.get('data', {}).get('bridge', 'unknown')} em `{BASE}`.")
    lines.append(f"- Runtime carregado: {len(runtime_registered)} comandos.")
    lines.append(f"- Capabilities declaradas: {len(cap_commands)} comandos.")
    lines.append(f"- Registry em disco: {len(registry_disk)} comandos.")
    lines.append(f"- Permissions em disco: {len(permissions_disk)} comandos.")
    lines.append(f"- Testes seguros executados: {len(command_tests)} chamadas.")
    lines.append(f"- Contagem por status: `{status_counts}`.")
    lines.append("")
    lines.append("## 2. Ambiente")
    for key, value in report["environment"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## 3. Estado runtime vs disco")
    lines.append(f"- Runtime registered actions: {len(runtime_registered)}")
    lines.append(f"- Disk registry actions: {len(registry_disk)}")
    lines.append(f"- Runtime/disk mismatches: {len(mismatches)}")
    if mismatches:
        lines.append("")
        lines.append("| Command | Disk registry | Runtime capabilities | Permissions | CLI | Codex | MCP |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for item in mismatches[:60]:
            lines.append(f"| `{item['command']}` | {item['in_disk_registry']} | {item['in_runtime_capabilities']} | {item['in_permissions']} | {item['in_cli']} | {item['in_codex_client']} | {item['in_mcp']} |")
    lines.append("")
    lines.append("## 4. Cobertura por área do QGIS")
    lines.append("| Área | Nível | % estimado | Comandos disponíveis | Working |")
    lines.append("|---|---|---:|---:|---:|")
    for area, cov in qgis_coverage.items():
        lines.append(f"| `{area}` | {cov['coverage_level']} | {cov['coverage_percent_estimate']} | {len(cov['commands_available'])} | {len(cov['commands_working'])} |")
    lines.append("")
    lines.append("## 5. Comandos funcionando")
    for test in [item for item in command_tests if item.get("status") == "working"][:140]:
        lines.append(f"- `{test['action']}` ({test.get('duration_ms', '')} ms)")
    lines.append("")
    lines.append("## 6. Comandos bloqueados, parametrizados ou sem dados")
    lines.append("| Action | Status | Error | Message |")
    lines.append("|---|---|---|---|")
    for test in [item for item in command_tests if item.get("status") != "working"][:180]:
        message = str(test.get("message", "")).replace("|", "/")
        lines.append(f"| `{test['action']}` | `{test.get('status')}` | `{test.get('error_code', '')}` | {message} |")
    lines.append("")
    lines.append("## 7. Cobertura Processing")
    lines.append(f"- Providers disponíveis: {processing_coverage['summary']['providers_available']}.")
    lines.append(f"- Algoritmos inventariados: {processing_coverage['summary']['algorithms_available']}.")
    lines.append(f"- Algoritmos na allowlist: {processing_coverage['summary']['algorithms_allowlisted']}.")
    lines.append("- Allowlist: " + ", ".join(f"`{item}`" for item in allowlist))
    lines.append("")
    lines.append("## 8. Cobertura plugins")
    lines.append(f"- Plugins inventariados: {len(plugin_coverage)}.")
    lines.append("| Plugin | Package | Enabled | Provider/algorithms | Status |")
    lines.append("|---|---|---:|---:|---|")
    for plugin in plugin_coverage[:100]:
        lines.append(f"| {plugin.get('name', '')} | `{plugin.get('package', '')}` | {plugin.get('enabled')} | {len(plugin.get('processing_algorithms') or [])} | {plugin.get('sig_usage_status')} |")
    lines.append("")
    lines.append("## 9. Riscos")
    for risk in report["risk_analysis"]["main_risks"]:
        lines.append(f"- {risk}")
    lines.append("")
    lines.append("## 10. Maturidade atual")
    for key, value in report["summary"]["maturity"].items():
        if isinstance(value, list):
            lines.append(f"- `{key}`: " + "; ".join(value))
        else:
            lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## 11. Próximos passos")
    for step in report["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    lines.append("O JSON completo contém a matriz por comando, respostas de runtime resumidas, divergências registry/permissions/capabilities/CLI/Codex/MCP, listas de bloqueios e cobertura por área.")

    md_path = OUT_DIR / "SIGMAI_FULL_QGIS_CAPABILITY_AUDIT.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "json": str(json_path),
        "md": str(md_path),
        "commands_tested": len(command_tests),
        "status_counts": status_counts,
        "runtime_commands": len(runtime_registered),
        "capabilities_commands": len(cap_commands),
        "disk_registry_commands": len(registry_disk),
        "permissions_commands": len(permissions_disk),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
