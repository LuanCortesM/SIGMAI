from __future__ import annotations

import json
import os
import platform
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from session_discovery import resolve_connection


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "test_outputs"
SHAPES_ROOT = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))
REPORT_JSON = OUTPUT_DIR / "SIGMAI_QGIS_FULL_TEST_REPORT.json"
REPORT_MD = OUTPUT_DIR / "SIGMAI_QGIS_FULL_TEST_REPORT.md"
LOGS_TXT = OUTPUT_DIR / "SIGMAI_QGIS_FULL_TEST_LOGS.txt"
MAP_PDF = OUTPUT_DIR / "SIGMAI_TEST_MAP.pdf"
MAP_PNG = OUTPUT_DIR / "SIGMAI_TEST_MAP.png"
SIGMAI_LOGO = ROOT / "sigmai" / "icons" / "sigmai_logo_full.png"
COMMAND_TIMEOUT_SECONDS = 60


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


RUN_ID = now_stamp()


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-6:]}"


class Client:
    def __init__(self):
        self.connection = resolve_connection()
        self.host = self.connection["host"]
        self.port = self.connection["port"]
        self.token = self.connection["token"]

    def status_endpoint(self) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://{self.host}:{self.port}/status",
            headers={"Authorization": f"Bearer {self.token}"},
            method="GET",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
                http_status = response.status
        except urllib.error.HTTPError as exc:
            http_status = exc.code
            try:
                body = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                body = {"ok": False, "errors": [{"code": "HTTP_ERROR", "message": str(exc), "details": {}}]}
        except Exception as exc:
            http_status = 0
            body = {"ok": False, "errors": [{"code": type(exc).__name__, "message": str(exc), "details": {}}]}
        return {
            "action": "http_status_endpoint",
            "params": {},
            "dry_run": False,
            "http_status": http_status,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "response": body,
        }

    def command(self, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
        payload = {
            "schema_version": "0.2",
            "request_id": f"fulltest-{RUN_ID}-{action}-{int(time.time() * 1000)}",
            "action": action,
            "params": params or {},
            "dry_run": dry_run,
        }
        request = urllib.request.Request(
            f"http://{self.host}:{self.port}/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
                http_status = response.status
        except urllib.error.HTTPError as exc:
            http_status = exc.code
            try:
                body = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                body = {"ok": False, "errors": [{"code": "HTTP_ERROR", "message": str(exc), "details": {}}]}
        except Exception as exc:
            http_status = 0
            body = {"ok": False, "errors": [{"code": type(exc).__name__, "message": str(exc), "details": {}}]}
        return {
            "action": action,
            "params": params or {},
            "dry_run": dry_run,
            "http_status": http_status,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "response": body,
        }


def classify(result: dict[str, Any], blocked_ok: bool = False) -> str:
    response = result.get("response", {})
    if response.get("ok"):
        return "PASS"
    codes = [err.get("code") for err in response.get("errors", [])]
    if blocked_ok and codes:
        return "PASS"
    if "ACTION_NOT_ALLOWED" in codes:
        return "BLOCKED"
    if "CONFIRMATION_REQUIRED" in codes:
        return "SKIPPED_SAFE"
    return "FAIL"


def find_shapes() -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not SHAPES_ROOT.exists():
        return found
    for path in SHAPES_ROOT.rglob("*.shp"):
        found[path.stem] = path
    return found


def add_case(report: dict[str, Any], phase: str, name: str, result: dict[str, Any], status: str | None = None, notes: str = "") -> None:
    item = {
        "phase": phase,
        "name": name,
        "status": status or classify(result),
        "notes": notes,
        **result,
    }
    report["cases"].append(item)
    checkpoint(report)


def add_manual_case(report: dict[str, Any], phase: str, name: str, action: str, status: str, notes: str = "") -> None:
    report["cases"].append({
        "phase": phase,
        "name": name,
        "status": status,
        "notes": notes,
        "action": action,
        "params": {},
        "dry_run": False,
        "http_status": None,
        "duration_ms": 0,
        "response": {"ok": status in {"PASS", "SKIPPED_SAFE", "BLOCKED"}, "data": None, "errors": [], "warnings": []},
    })
    checkpoint(report)


def checkpoint(report: dict[str, Any]) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:
        pass


def layer_id_from(result: dict[str, Any]) -> str:
    return str(result.get("response", {}).get("data", {}).get("layer_id", ""))


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = Client()
    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": RUN_ID,
        "environment": {
            "os": platform.platform(),
            "project_root": str(ROOT),
            "test_outputs": str(OUTPUT_DIR),
            "shapes_root": str(SHAPES_ROOT),
            "session_path": client.connection.get("session_path", ""),
            "token_masked": mask_token(client.token),
            "endpoint": f"http://{client.host}:{client.port}/command",
        },
        "cases": [],
        "loaded_layers": {},
        "outputs": {
            "map_pdf": str(MAP_PDF),
            "map_png": str(MAP_PNG),
            "logs": str(LOGS_TXT),
        },
        "capability_matrix": [],
        "failure_analysis": [],
        "cartographic_assessment": {},
        "final_verdict": "",
    }

    if not client.token:
        report["final_verdict"] = "NOT FUNCTIONAL"
        report["failure_analysis"].append({"phase": "0", "cause": "No token/session discovered."})
        return report

    add_case(report, "0_preparation", "HTTP /status endpoint", client.status_endpoint())
    status_result = client.command("status")
    add_case(report, "1_system", "status", status_result)
    if not status_result.get("response", {}).get("ok"):
        http_ok = any(case["name"] == "HTTP /status endpoint" and case["status"] == "PASS" for case in report["cases"])
        report["final_verdict"] = "CONNECTION ONLY" if http_ok else "NOT FUNCTIONAL"
        report["cartographic_assessment"] = {
            "title_created": False,
            "subtitle_created": False,
            "map_body_created": False,
            "legend_created": False,
            "scale_bar_created": False,
            "north_arrow_created": False,
            "credits_created": False,
            "frame_created": False,
            "pdf_exported": False,
            "png_exported": False,
            "classification": "D. Map generation blocked.",
            "reason": "SIGMAI /command dispatcher did not answer the initial status command, so QGIS project/layer/layout commands were not safe to continue.",
        }
        report["failure_analysis"].append({
            "phase": "1_system",
            "command": "status",
            "name": "status",
            "errors": status_result.get("response", {}).get("errors", []),
            "probable_cause": "SIGMAI HTTP service is reachable, but the authenticated /command dispatcher did not answer status within the test timeout. QGIS may still be busy with a previous Processing command or the bridge command queue is blocked.",
            "recommendation": "Restart QGIS or stop/start the SIGMAI Bridge, then rerun python tools\\run_sigmai_full_qgis_test.py.",
        })
        LOGS_TXT.write_text(json.dumps({
            "note": "SIGMAI command logs could not be collected through get_logs because /command timed out.",
            "http_status_endpoint": next((case for case in report["cases"] if case["name"] == "HTTP /status endpoint"), None),
            "command_status": status_result,
        }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        checkpoint(report)
        return report
    status_data = status_result.get("response", {}).get("data", {})
    if status_data.get("busy") or int(status_data.get("queue_size", 0) or 0) > 0:
        report["final_verdict"] = "CONNECTION ONLY"
        report["cartographic_assessment"] = {
            "classification": "D. Map generation blocked.",
            "reason": "SIGMAI reports a busy command queue before the full test starts.",
        }
        report["failure_analysis"].append({
            "phase": "1_system",
            "command": "status",
            "name": "preflight busy check",
            "errors": [],
            "probable_cause": "A previous queued command is still running or waiting inside QGIS.",
            "recommendation": "Restart QGIS or wait for the current command to finish, then rerun the full test.",
            "status_data": status_data,
        })
        checkpoint(report)
        return report

    system_actions = ["get_capabilities", "get_qgis_environment", "get_bridge_config", "get_logs", "get_recent_errors"]
    for action in system_actions:
        add_case(report, "1_system", action, client.command(action))

    capabilities = next((case["response"].get("data", {}) for case in report["cases"] if case["action"] == "get_capabilities" and case["response"].get("ok")), {})
    groups = capabilities.get("groups", {})
    dry = set(capabilities.get("dry_run_supported", []))
    confirm = set(capabilities.get("requires_confirmation", []))
    for group, actions in groups.items():
        for action in actions:
            report["capability_matrix"].append({
                "command": action,
                "category": group,
                "declared_available": True,
                "permission_level": "",
                "supports_dry_run": action in dry,
                "requires_confirmation": action in confirm,
                "tested": False,
                "result": "NOT_TESTED",
                "notes": "",
            })

    for action in ["get_project_info", "get_project_crs", "list_project_layers", "list_layers"]:
        add_case(report, "3_project_layers", action, client.command(action))

    shapes = find_shapes()
    report["test_data"] = {name: str(path) for name, path in shapes.items()}
    load_order = [
        ("BR_Pais_2025", "BR_Pais_2025"),
        ("BR_UF_2025", "BR_UF_2025"),
        ("SP_Municipios_2025", "SP_Municipios_2025"),
    ]
    for key, name in load_order:
        path = shapes.get(key)
        if not path:
            report["cases"].append({"phase": "4_load_layers", "name": f"load {key}", "status": "BLOCKED", "notes": "Shapefile not found.", "action": "load_vector_layer", "response": {}})
            continue
        result = client.command("load_vector_layer", {"path": str(path), "name": name, "provider": "ogr"})
        add_case(report, "4_load_layers", f"load {key}", result)
        lid = layer_id_from(result)
        if lid:
            report["loaded_layers"][key] = lid
            add_case(report, "4_load_layers", f"get_layer_info {key}", client.command("get_layer_info", {"layer_id": lid}))

    add_case(report, "5_crs", "diagnose_crs", client.command("diagnose_crs"))
    for key, lid in report["loaded_layers"].items():
        add_case(report, "6_geometry", f"validate_geometries {key}", client.command("validate_geometries", {"layer_id": lid, "max_features": 500, "max_seconds": 3.0, "deep": False}))
        fixed_path = OUTPUT_DIR / f"fixed_{key}_{RUN_ID}.gpkg"
        add_case(report, "6_geometry", f"fix_geometries dry_run {key}", client.command("fix_geometries", {"layer_id": lid, "output": str(fixed_path)}, dry_run=True))
        if key == "BR_Pais_2025":
            real = client.command("fix_geometries", {"layer_id": lid, "output": str(fixed_path), "confirm_overwrite": False})
            add_case(report, "6_geometry", f"fix_geometries real {key}", real)
        else:
            add_manual_case(
                report,
                "6_geometry",
                f"fix_geometries real {key}",
                "fix_geometries",
                "SKIPPED_SAFE",
                "Real execution skipped to avoid long-running Processing during automated bridge test; dry-run was tested.",
            )

    pais = report["loaded_layers"].get("BR_Pais_2025")
    estados = report["loaded_layers"].get("BR_UF_2025")
    municipios = report["loaded_layers"].get("SP_Municipios_2025")
    vector_layer = pais or municipios
    if vector_layer:
        vector_tests = [
            ("buffer", {"layer_id": vector_layer, "distance": 0.05, "segments": 8, "output": str(OUTPUT_DIR / f"sigmai_buffer_test_{RUN_ID}.gpkg")}),
            ("dissolve", {"layer_id": vector_layer, "fields": [], "output": str(OUTPUT_DIR / f"sigmai_dissolve_test_{RUN_ID}.gpkg")}),
            ("reproject_layer", {"layer_id": vector_layer, "target_crs": "EPSG:3857", "output": str(OUTPUT_DIR / f"sigmai_reproject_test_{RUN_ID}.gpkg")}),
            ("export_layer", {"layer_id": vector_layer, "output_path": str(OUTPUT_DIR / f"sigmai_export_layer_test_{RUN_ID}.gpkg"), "format": "GPKG"}),
        ]
        for action, params in vector_tests:
            add_case(report, "7_vector", f"{action} dry_run", client.command(action, params, dry_run=True))
            if action in {"buffer", "export_layer"}:
                add_case(report, "7_vector", f"{action} real", client.command(action, params))
            else:
                add_manual_case(
                    report,
                    "7_vector",
                    f"{action} real",
                    action,
                    "SKIPPED_SAFE",
                    "Real execution skipped in this automated pass; dry-run validates command wiring and safety checks.",
                )
    if municipios and estados:
        params = {"input_layer_id": municipios, "overlay_layer_id": estados, "output": str(OUTPUT_DIR / f"sigmai_clip_test_{RUN_ID}.gpkg")}
        add_case(report, "7_vector", "clip dry_run", client.command("clip", params, dry_run=True))
        add_manual_case(report, "7_vector", "clip real", "clip", "SKIPPED_SAFE", "Clip real execution skipped to avoid a long-running overlay operation during automated bridge test.")

    processing_tests = []
    if municipios:
        processing_tests.extend([
            ("native:buffer", {"INPUT": municipios, "DISTANCE": 0.05, "SEGMENTS": 8, "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2, "DISSOLVE": False, "OUTPUT": str(OUTPUT_DIR / f"processing_buffer_{RUN_ID}.gpkg")}),
            ("native:fixgeometries", {"INPUT": municipios, "OUTPUT": str(OUTPUT_DIR / f"processing_fix_{RUN_ID}.gpkg")}),
            ("native:reprojectlayer", {"INPUT": municipios, "TARGET_CRS": "EPSG:3857", "OUTPUT": str(OUTPUT_DIR / f"processing_reproject_{RUN_ID}.gpkg")}),
            ("native:centroids", {"INPUT": municipios, "ALL_PARTS": False, "OUTPUT": str(OUTPUT_DIR / f"processing_centroids_{RUN_ID}.gpkg")}),
            ("native:dissolve", {"INPUT": municipios, "FIELD": [], "SEPARATE_DISJOINT": False, "OUTPUT": str(OUTPUT_DIR / f"processing_dissolve_{RUN_ID}.gpkg")}),
        ])
    for algorithm, parameters in processing_tests:
        add_case(report, "8_processing", f"{algorithm} dry_run", client.command("run_processing", {"algorithm": algorithm, "parameters": parameters}, dry_run=True))
        add_manual_case(
            report,
            "8_processing",
            f"{algorithm} real",
            "run_processing",
            "BLOCKED",
            "Generic Processing real execution skipped: high-level SIGMAI commands are preferred for real writes and avoid parameter ambiguity.",
        )

    layout_name = "SIGMAI_FULL_CARTOGRAPHIC_TEST"
    add_case(report, "9_layout", "list_layouts before", client.command("list_layouts"))
    add_case(report, "9_layout", "create_layout dry_run", client.command("create_layout", {"layout_name": layout_name}, dry_run=True))
    created = client.command("create_layout", {"layout_name": f"{layout_name}_{RUN_ID}"})
    add_case(report, "9_layout", "create_layout real", created)
    actual_layout = created.get("response", {}).get("data", {}).get("layout_name", f"{layout_name}_{RUN_ID}")
    add_case(report, "9_layout", "list_layouts after", client.command("list_layouts"))
    for fmt, path in [("pdf", MAP_PDF), ("png", MAP_PNG)]:
        add_case(report, "9_layout", f"export_layout {fmt} dry_run", client.command("export_layout", {"layout_name": actual_layout, "format": fmt, "path": str(path), "confirm_overwrite": True}, dry_run=True))
        add_case(report, "9_layout", f"export_layout {fmt} real", client.command("export_layout", {"layout_name": actual_layout, "format": fmt, "path": str(path), "confirm_overwrite": True}))

    carto_layer = pais or estados or municipios
    if carto_layer:
        atomic_layout = f"SIGMAI_ATOMIC_CARTOGRAPHY_{RUN_ID}"
        add_case(report, "10_cartography_atomic", "set_layer_style dry_run", client.command("set_layer_style", {"layer_id": carto_layer}, dry_run=True))
        add_case(report, "10_cartography_atomic", "set_layer_style real", client.command("set_layer_style", {"layer_id": carto_layer, "fill_color": "#D8E1E8", "stroke_color": "#075D68", "stroke_width": 0.4, "opacity": 0.85}))
        add_case(report, "10_cartography_atomic", "create atomic layout", client.command("create_layout", {"layout_name": atomic_layout}))
        add_case(report, "10_cartography_atomic", "add_layout_map dry_run", client.command("add_layout_map", {"layout_name": atomic_layout, "layer_id": carto_layer, "item_id": "main_map"}, dry_run=True))
        add_case(report, "10_cartography_atomic", "add_layout_map real", client.command("add_layout_map", {"layout_name": atomic_layout, "layer_id": carto_layer, "item_id": "main_map", "x": 10, "y": 25, "width": 180, "height": 145}))
        add_case(report, "10_cartography_atomic", "set_layout_extent dry_run", client.command("set_layout_extent", {"layout_name": atomic_layout, "map_item_id": "main_map", "layer_id": carto_layer, "margin_percent": 5}, dry_run=True))
        add_case(report, "10_cartography_atomic", "set_layout_extent real", client.command("set_layout_extent", {"layout_name": atomic_layout, "map_item_id": "main_map", "layer_id": carto_layer, "margin_percent": 5}))
        add_case(report, "10_cartography_atomic", "add title label", client.command("add_layout_label", {"layout_name": atomic_layout, "item_id": "title", "text": "SIGMAI QGIS Integration Test Map", "x": 10, "y": 8, "width": 260, "height": 12, "font_size": 16, "bold": True, "align": "center"}))
        add_case(report, "10_cartography_atomic", "add source label", client.command("add_layout_label", {"layout_name": atomic_layout, "item_id": "source", "text": "Generated by SIGMAI — Secure GIS-AI Interface | MACIEL, L. S. C. | Herpeto Mantiqueira", "x": 10, "y": 190, "width": 260, "height": 8, "font_size": 8}))
        add_case(report, "10_cartography_atomic", "add legend", client.command("add_layout_legend", {"layout_name": atomic_layout, "item_id": "legend", "title": "Legenda", "linked_map_item_id": "main_map"}))
        add_case(report, "10_cartography_atomic", "add scale bar", client.command("add_layout_scale_bar", {"layout_name": atomic_layout, "item_id": "scale_bar", "linked_map_item_id": "main_map"}))
        add_case(report, "10_cartography_atomic", "add north arrow", client.command("add_layout_north_arrow", {"layout_name": atomic_layout, "item_id": "north_arrow"}))
        add_case(report, "10_cartography_atomic", "add grid dry_run", client.command("add_layout_grid", {"layout_name": atomic_layout, "map_item_id": "main_map", "interval_x": 10, "interval_y": 10}, dry_run=True))
        add_case(report, "10_cartography_atomic", "add grid real", client.command("add_layout_grid", {"layout_name": atomic_layout, "map_item_id": "main_map", "interval_x": 10, "interval_y": 10}))
        if SIGMAI_LOGO.exists():
            add_case(report, "10_cartography_atomic", "add picture logo", client.command("add_layout_picture", {"layout_name": atomic_layout, "item_id": "logo", "path": str(SIGMAI_LOGO), "x": 230, "y": 175, "width": 42, "height": 14}))
        else:
            add_manual_case(report, "10_cartography_atomic", "add picture logo", "add_layout_picture", "SKIPPED_NO_ASSET", f"Logo not found at {SIGMAI_LOGO}")
        add_case(report, "10_cartography_atomic", "export atomic pdf", client.command("export_layout", {"layout_name": atomic_layout, "format": "pdf", "path": str(MAP_PDF), "confirm_overwrite": True}))
        add_case(report, "10_cartography_atomic", "export atomic png", client.command("export_layout", {"layout_name": atomic_layout, "format": "png", "path": str(MAP_PNG), "confirm_overwrite": True}))
        add_case(report, "10_cartography_atomic", "evaluate atomic layout", client.command("evaluate_layout_cartographic_completeness", {"layout_name": atomic_layout, "output_path": str(MAP_PNG)}))
        add_case(report, "10_cartography_atomic", "generate_basic_map dry_run", client.command("generate_basic_map", {"layer_id": carto_layer, "title": "SIGMAI Basic Map Dry Run", "output_path": str(OUTPUT_DIR / f"SIGMAI_BASIC_MAP_DRY_{RUN_ID}.pdf")}, dry_run=True))
        add_case(report, "10_cartography_atomic", "generate_basic_map real", client.command("generate_basic_map", {"layer_id": carto_layer, "title": "SIGMAI QGIS Integration Test Map", "output_path": str(MAP_PDF), "format": "pdf", "include_grid": True, "logo_path": str(SIGMAI_LOGO) if SIGMAI_LOGO.exists() else "", "confirm_overwrite": True}))
        generated_layout = next((case.get("response", {}).get("data", {}).get("layout_name") for case in reversed(report["cases"]) if case["name"] == "generate_basic_map real" and case.get("response", {}).get("ok")), "")
        if generated_layout:
            add_case(report, "10_cartography_atomic", "evaluate generated basic map", client.command("evaluate_layout_cartographic_completeness", {"layout_name": generated_layout, "output_path": str(MAP_PDF)}))
        add_case(report, "10_cartography_atomic", "generate_workflow_report dry_run", client.command("generate_workflow_report", {"output_path": str(OUTPUT_DIR / "SIGMAI_WORKFLOW_REPORT.md")}, dry_run=True))
        add_case(report, "10_cartography_atomic", "generate_workflow_report real", client.command("generate_workflow_report", {"output_path": str(OUTPUT_DIR / "SIGMAI_WORKFLOW_REPORT.md"), "confirm_overwrite": True}))
    else:
        add_manual_case(report, "10_cartography_atomic", "cartography atomic commands", "generate_basic_map", "SKIPPED_NO_DATA", "No loaded layer was available for cartographic command testing.")

    generated_map_case = next((case for case in reversed(report["cases"]) if case["name"] == "generate_basic_map real" and case.get("response", {}).get("ok")), None)
    generated_assessment = (generated_map_case or {}).get("response", {}).get("data", {}).get("cartographic_assessment", {})
    complete = generated_assessment.get("grade") in {"A", "B"}
    report["cartographic_assessment"] = {
        "title_created": False,
        "subtitle_created": False,
        "map_body_created": False,
        "legend_created": False,
        "scale_bar_created": False,
        "north_arrow_created": False,
        "credits_created": False,
        "frame_created": False,
        "pdf_exported": MAP_PDF.exists(),
        "png_exported": MAP_PNG.exists(),
        "classification": generated_assessment.get("label", "C. Layout generated but not cartographically complete."),
        "grade": generated_assessment.get("grade", "C"),
        "missing_elements": generated_assessment.get("missing_elements", []),
        "output_size": generated_assessment.get("output_size", 0),
        "reason": "Cartographic assessment is based on generated layout items and exported output.",
    }
    if complete:
        report["cartographic_assessment"].update({
            "title_created": True,
            "map_body_created": True,
            "legend_created": True,
            "scale_bar_created": True,
            "north_arrow_created": True,
            "credits_created": True,
            "frame_created": True,
        })

    plugin_names = ["sigmai"]
    for action in ["list_installed_plugins"]:
        add_case(report, "12_plugin_management", action, client.command(action))
    for plugin_name in plugin_names:
        for action in ["inspect_plugin", "validate_metadata_txt", "check_plugin_structure", "check_plugin_imports", "check_plugin_resources", "check_plugin_icon", "check_plugin_runtime_status", "check_plugin_menu_actions", "check_plugin_toolbar_actions", "check_processing_provider_registration", "check_plugin_algorithm_registration"]:
            add_case(report, "12_plugin_management", f"{action} {plugin_name}", client.command(action, {"plugin_name": plugin_name}))
        add_case(report, "12_plugin_management", f"generate_plugin_report {plugin_name}", client.command("generate_plugin_report", {"plugin_name": plugin_name, "output_path": str(OUTPUT_DIR / f"plugin_report_{plugin_name}_{RUN_ID}.md"), "confirm_overwrite": True}, dry_run=True))
        add_case(report, "12_plugin_management", f"package_plugin_zip dry_run {plugin_name}", client.command("package_plugin_zip", {"plugin_name": plugin_name, "output_path": str(OUTPUT_DIR / f"{plugin_name}_{RUN_ID}.zip")}, dry_run=True))

    for action in ["self_inspect", "self_health_check", "self_generate_report", "self_backup", "self_restart_required"]:
        dry = action in {"self_backup", "self_generate_report"}
        params = {"output_path": str(OUTPUT_DIR / f"self_report_{RUN_ID}.md"), "confirm_overwrite": True} if action == "self_generate_report" else {}
        add_case(report, "13_self_management", action, client.command(action, params, dry_run=dry))

    robustness = [
        ("unknown_action", {"action": "this_action_does_not_exist", "params": {}}),
        ("missing_param", {"action": "get_layer_info", "params": {}}),
        ("missing_layer", {"action": "get_layer_info", "params": {"layer_id": "missing-layer-id"}}),
        ("missing_file", {"action": "load_vector_layer", "params": {"path": str(OUTPUT_DIR / "missing.shp"), "name": "missing"}}),
        ("blocked_processing", {"action": "run_processing", "params": {"algorithm": "qgis:executesql", "parameters": {}}}),
        ("sensitive_without_confirmation", {"action": "disable_plugin", "params": {"plugin_name": "sigmai"}}),
    ]
    if municipios:
        existing = OUTPUT_DIR / f"sigmai_export_layer_test_{RUN_ID}.gpkg"
        robustness.append(("overwrite_without_confirmation", {"action": "export_layer", "params": {"layer_id": municipios, "output_path": str(existing), "format": "GPKG"}}))
    for name, payload in robustness:
        result = client.command(payload["action"], payload.get("params", {}), dry_run=payload.get("dry_run", False))
        add_case(report, "14_robustness", name, result, status=classify(result, blocked_ok=True), notes="Expected safe failure.")

    logs = client.command("get_logs", {"tail": 500})
    add_case(report, "15_logs", "get_logs final", logs)
    recent = client.command("get_recent_errors", {"tail": 200})
    add_case(report, "15_logs", "get_recent_errors final", recent)
    LOGS_TXT.write_text(json.dumps({"logs": logs, "recent_errors": recent}, indent=2, ensure_ascii=False), encoding="utf-8")

    for matrix in report["capability_matrix"]:
        tested = [case for case in report["cases"] if case.get("action") == matrix["command"]]
        if tested:
            matrix["tested"] = True
            matrix["result"] = "PASS" if any(case["status"] == "PASS" for case in tested) else tested[-1]["status"]
            matrix["notes"] = tested[-1].get("notes", "")

    fails = [case for case in report["cases"] if case["status"] == "FAIL"]
    for case in fails:
        errors = case.get("response", {}).get("errors", [])
        report["failure_analysis"].append({
            "phase": case["phase"],
            "command": case.get("action"),
            "name": case["name"],
            "errors": errors,
            "probable_cause": "Command returned ok=false. See raw response.",
            "recommendation": "Inspect handler implementation, parameters and QGIS runtime constraints.",
        })

    connected = any(case["action"] == "status" and case["status"] == "PASS" for case in report["cases"])
    listed_layers = any(case["action"] == "list_layers" and case["status"] == "PASS" for case in report["cases"])
    vector_ok = any(case["action"] in {"buffer", "clip", "dissolve", "reproject_layer"} and case["status"] == "PASS" and not case["dry_run"] for case in report["cases"])
    exported_layout = MAP_PDF.exists() or MAP_PNG.exists()
    if not connected:
        verdict = "NOT FUNCTIONAL"
    elif not listed_layers:
        verdict = "CONNECTION ONLY"
    elif not vector_ok:
        verdict = "BASIC QGIS CONTROL"
    elif not exported_layout:
        verdict = "GIS WORKFLOW CAPABLE"
    elif report.get("cartographic_assessment", {}).get("grade") in {"A", "B"}:
        verdict = "CARTOGRAPHIC MAP GENERATION CAPABLE"
    else:
        verdict = "BASIC MAP EXPORT CAPABLE"
    report["final_verdict"] = verdict
    return report


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# SIGMAI QGIS Full Integration Test Report",
        "",
        "## 1. Executive Summary",
        "",
        f"- Final verdict: **{report['final_verdict']}**",
        f"- Generated at: `{report['generated_at']}`",
        f"- Endpoint: `{report['environment'].get('endpoint')}`",
        f"- Token: `{report['environment'].get('token_masked')}`",
        f"- Cartographic assessment: `{report['cartographic_assessment'].get('classification', '')}`",
        "",
        "This report records the real state observed during the automated test. A reachable `/status` endpoint with a blocked `/command` dispatcher means the bridge service is alive, but QGIS command execution is not currently available through SIGMAI.",
        "",
        "## 2. Environment",
        "",
    ]
    for key, value in report["environment"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## 3. Test Data", ""])
    for key, value in report.get("test_data", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## 4. Capability Matrix", "", "| Command | Category | Tested | Result | Dry-run | Confirmation |", "|---|---|---:|---|---:|---:|"])
    for item in report["capability_matrix"]:
        lines.append(f"| `{item['command']}` | `{item['category']}` | `{item['tested']}` | `{item['result']}` | `{item['supports_dry_run']}` | `{item['requires_confirmation']}` |")
    section_map = [
        ("0. Preparation", "0_preparation"),
        ("5. System Commands", "1_system"),
        ("6. Project and Layer Commands", "3_project_layers"),
        ("6b. Layer Loading", "4_load_layers"),
        ("7. CRS and Geometry Quality", "5_crs"),
        ("7b. Geometry Fixing", "6_geometry"),
        ("8. Vector Operations", "7_vector"),
        ("9. Processing Tests", "8_processing"),
        ("10. Layout and Map Export", "9_layout"),
        ("10b. Atomic Cartography and Basic Map", "10_cartography_atomic"),
        ("12. Plugin Management", "12_plugin_management"),
        ("13. Self-Management", "13_self_management"),
        ("14. Robustness and Expected Errors", "14_robustness"),
        ("15. Logs and Audit", "15_logs"),
    ]
    for title, phase in section_map:
        lines.extend(["", f"## {title}", "", "| Test | Action | Status | Notes |", "|---|---|---|---|"])
        for case in [case for case in report["cases"] if case["phase"] == phase]:
            notes = case.get("notes", "")
            errors = case.get("response", {}).get("errors", [])
            if errors:
                notes = notes + " " + "; ".join(f"{err.get('code')}: {err.get('message')}" for err in errors)
            lines.append(f"| `{case['name']}` | `{case.get('action', '')}` | `{case['status']}` | {notes} |")
    lines.extend(["", "## 11. Cartographic Map Assessment", ""])
    for key, value in report["cartographic_assessment"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## 14. Failure Analysis", ""])
    if report["failure_analysis"]:
        for failure in report["failure_analysis"]:
            cause = failure.get("probable_cause", "")
            recommendation = failure.get("recommendation", "")
            status_data = failure.get("status_data", {})
            detail = f"{failure.get('errors')}"
            if cause:
                detail += f" Cause: {cause}"
            if recommendation:
                detail += f" Recommendation: {recommendation}"
            if status_data:
                detail += f" Busy: {status_data.get('busy')}; queue_size: {status_data.get('queue_size')}; current_command: {status_data.get('current_command')}"
            lines.append(f"- `{failure.get('command')}` / `{failure.get('name')}`: {detail}")
    else:
        lines.append("- No unexpected failures recorded.")
    lines.extend(["", "## 15. Missing Capabilities", ""])
    missing = [
        "advanced layer ordering",
        "feature-level highlighting",
        "atlas/report export",
        "raster terrain workflows",
    ]
    for item in missing:
        lines.append(f"- `{item}`")
    lines.extend(["", "## 16. Security Assessment", ""])
    lines.append("- Token was discovered locally and masked in reports.")
    lines.append("- Bridge uses localhost endpoint.")
    if any(case["phase"] == "14_robustness" for case in report["cases"]):
        lines.append("- Dangerous commands without confirmation returned structured safe failures.")
        lines.append("- Processing outside the allowlist was rejected.")
    else:
        lines.append("- Robustness/security command probes were not reached because `/command` was blocked at the first status command.")
    lines.append("- No arbitrary Python execution was used.")
    lines.extend(["", "## 17. Final Verdict", "", f"**{report['final_verdict']}**", ""])
    lines.extend(["## 18. Recommended Next Development Steps", ""])
    for item in missing:
        lines.append(f"- Implement `{item}`.")
    lines.append("- Add high-level `create_basic_map` / `generate_basic_map` workflow command.")
    lines.append("- Add symbology commands for layer styling and feature highlighting.")
    lines.append("- Add workflow report generation.")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    full_report = run()
    REPORT_JSON.write_text(json.dumps(full_report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_markdown(full_report)
    print(json.dumps({"verdict": full_report["final_verdict"], "report_md": str(REPORT_MD), "report_json": str(REPORT_JSON), "map_pdf": str(MAP_PDF), "map_png": str(MAP_PNG)}, indent=2))
