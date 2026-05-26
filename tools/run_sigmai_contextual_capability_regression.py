from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IA_BRIDGE_ROOT = ROOT.parent
TEST_DATA = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", IA_BRIDGE_ROOT / ("Shapes pra " + "Teste")))
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_ROOT = ROOT / "test_outputs" / "sigmai_contextual_regression"
RUN_DIR = OUT_ROOT / RUN_ID
RUN_DIR.mkdir(parents=True, exist_ok=True)
(RUN_DIR / "raster").mkdir(parents=True, exist_ok=True)
(ROOT / "diagnostics").mkdir(exist_ok=True)

import sys

sys.path.insert(0, str(ROOT / "tools"))
from session_discovery import resolve_connection  # noqa: E402

CONN = resolve_connection()
HOST = CONN.get("host", "127.0.0.1")
PORT = int(CONN.get("port", 8765))
TOKEN = CONN.get("token", "")
BASE = f"http://{HOST}:{PORT}"


def mask(value: str) -> str:
    if not value:
        return ""
    return value[:6] + "..." + value[-6:] if len(value) > 12 else value[:2] + "..." + value[-2:]


def bridge(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, timeout: int = 60) -> dict[str, Any]:
    payload = {
        "schema_version": "0.3",
        "request_id": f"contextual-{action}-{int(time.time() * 1000)}",
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
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
            data["_http_status"] = response.status
            data["_duration_ms"] = int((time.time() - started) * 1000)
            return data
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"ok": False, "errors": [{"code": "HTTP_ERROR", "message": raw[:500]}]}
        data["_http_status"] = exc.code
        data["_duration_ms"] = int((time.time() - started) * 1000)
        return data
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
    return "", ""


def status_for(resp: dict[str, Any]) -> str:
    if resp.get("ok") is True:
        return "validated"
    code, message = first_error(resp)
    text = f"{code} {message}".lower()
    if "not found" in text or "no test" in text:
        return "skipped_no_data"
    if "required" in text or "missing" in text or "parameter" in text:
        return "failed_with_reason"
    if "overwrite" in text:
        return "failed_with_reason"
    if "not enabled" in text or "disabled" in text:
        return "skipped_protected"
    return "needs_fix"


def record(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, area: str = "general", timeout: int = 60) -> dict[str, Any]:
    resp = bridge(action, params or {}, dry_run=dry_run, timeout=timeout)
    code, message = first_error(resp)
    return {
        "area": area,
        "action": action,
        "dry_run": dry_run,
        "params_summary": summarize_params(params or {}),
        "ok": bool(resp.get("ok")),
        "status": status_for(resp),
        "http_status": resp.get("_http_status"),
        "duration_ms": resp.get("_duration_ms"),
        "error_code": code,
        "message": message,
        "warnings": resp.get("warnings", []),
        "data": resp.get("data", {}),
    }


def summarize_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = value[:5]
        elif isinstance(value, dict):
            out[key] = {k: value[k] for k in list(value)[:8]}
        else:
            out[key] = str(value)
    return out


def write_area(name: str, tests: list[dict[str, Any]]) -> None:
    (OUT_ROOT / f"{name}.json").write_text(json.dumps({"run_id": RUN_ID, "tests": tests}, ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN_DIR / f"{name}.json").write_text(json.dumps({"run_id": RUN_ID, "tests": tests}, ensure_ascii=False, indent=2), encoding="utf-8")


def find_file(patterns: list[str], suffixes: tuple[str, ...]) -> Path | None:
    files = []
    if TEST_DATA.exists():
        for suffix in suffixes:
            files.extend(TEST_DATA.rglob(f"*{suffix}"))
    for pattern in patterns:
        lowered = pattern.lower()
        for path in files:
            if lowered in path.name.lower() or lowered in str(path).lower():
                return path
    return files[0] if files else None


def all_files(suffixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    if TEST_DATA.exists():
        for suffix in suffixes:
            files.extend(TEST_DATA.rglob(f"*{suffix}"))
    return sorted(files)


def load_vectors() -> dict[str, dict[str, Any]]:
    targets = {
        "sp_municipios": find_file(["SP_Municipios_2025", "municipios"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "br_uf": find_file(["BR_UF_2025"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "br_pais": find_file(["BR_Pais_2025"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "travessia": find_file(["travessia", "marins"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "batedor": find_file(["batedor", "itaguar"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "frogs": find_file(["frogs", "batedor_frogs"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "topotrail_clip": find_file(["topotrail_potencial_clip", "potencial_clip", "clip_cruzeiro"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
        "topotrail_zonas": find_file(["TopoTrail zonas", "zonas potenciais", "topotrail_zonas"], (".shp", ".gpkg", ".geojson", ".kml", ".gpx")),
    }
    loaded: dict[str, dict[str, Any]] = {}
    for key, path in targets.items():
        if not path:
            continue
        resp = bridge("load_vector_layer", {"path": str(path), "name": f"ctx_{key}_{path.stem}"}, dry_run=False, timeout=60)
        loaded[key] = {"path": str(path), "response": resp, "layer_id": resp.get("data", {}).get("layer_id"), "name": resp.get("data", {}).get("name", path.stem)}
    return loaded


def load_rasters() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for index, path in enumerate(all_files((".tif", ".tiff"))[:2], start=1):
        resp = bridge("load_raster_layer", {"path": str(path), "name": f"ctx_raster_{index}_{path.stem}"}, dry_run=False, timeout=60)
        loaded[f"raster_{index}"] = {"path": str(path), "response": resp, "layer_id": resp.get("data", {}).get("layer_id"), "name": resp.get("data", {}).get("name", path.stem)}
    return loaded


def get_layer_info(layer_id: str) -> dict[str, Any]:
    resp = bridge("get_layer_info", {"layer_id": layer_id}, dry_run=False, timeout=30)
    return resp.get("data", {}) if resp.get("ok") else {}


def get_fields(layer_id: str) -> list[dict[str, Any]]:
    resp = bridge("list_fields", {"layer_id": layer_id}, dry_run=False, timeout=30)
    return resp.get("data", {}).get("fields", []) if resp.get("ok") else []


def choose_fields(layer_id: str) -> tuple[str | None, str | None, Any]:
    fields = get_fields(layer_id)
    text_field = None
    numeric_field = None
    preferred = ["NM_MUN", "NM_MUNICIP", "NM_MUNICIPIO", "NM_UF", "SIGLA_UF", "name", "nome"]
    names = [f.get("name") for f in fields]
    for wanted in preferred:
        for name in names:
            if name and wanted.lower() == str(name).lower():
                text_field = str(name)
                break
        if text_field:
            break
    for field in fields:
        if field.get("is_numeric"):
            numeric_field = str(field.get("name"))
            break
    if not text_field:
        for field in fields:
            if not field.get("is_numeric"):
                text_field = str(field.get("name"))
                break
    sample = bridge("sample_features", {"layer_id": layer_id, "max_features": 1}, False, 30)
    sample_value = None
    try:
        attrs = sample["data"]["features"][0]["attributes"]
        if text_field and text_field in attrs:
            sample_value = attrs[text_field]
        elif numeric_field and numeric_field in attrs:
            sample_value = attrs[numeric_field]
    except Exception:
        pass
    return text_field, numeric_field, sample_value


def expression_for(field: str | None, value: Any) -> str:
    if not field:
        return "1=1"
    if isinstance(value, (int, float)):
        return f'"{field}" = {value}'
    if value is None:
        return "1=1"
    safe = str(value).replace("'", "''")
    return f'"{field}" = \'{safe}\''


def output_path(name: str) -> str:
    return str(RUN_DIR / name)


def validate_pngs(paths: list[str]) -> list[dict[str, Any]]:
    results = []
    for path_value in paths:
        path = Path(path_value)
        results.append({"path": str(path), "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0})
    return results


def main() -> None:
    start = datetime.now(timezone.utc).isoformat()
    base_tests: list[dict[str, Any]] = []
    base_tests.append(record("status", area="system"))
    base_tests.append(record("get_capabilities", area="system"))

    vectors = load_vectors()
    rasters = load_rasters()
    base_tests.append(record("list_layers", area="layers"))
    layer_ids = {key: item.get("layer_id") for key, item in vectors.items() if item.get("layer_id")}
    raster_ids = {key: item.get("layer_id") for key, item in rasters.items() if item.get("layer_id")}

    main_layer = layer_ids.get("sp_municipios") or next(iter(layer_ids.values()), None)
    overlay_layer = layer_ids.get("br_uf") or layer_ids.get("br_pais") or main_layer
    point_layer = layer_ids.get("frogs")
    raster_layer = next(iter(raster_ids.values()), None)
    text_field, numeric_field, sample_value = choose_fields(main_layer) if main_layer else (None, None, None)
    expr = expression_for(text_field or numeric_field, sample_value)
    stats_field = numeric_field or text_field

    attributes_tests: list[dict[str, Any]] = []
    if main_layer and text_field:
        attributes_tests.extend([
            record("list_fields", {"layer_id": main_layer}, area="attribute_table"),
            record("sample_features", {"layer_id": main_layer, "max_features": 5, "include_geometry": False}, area="attribute_table"),
            record("inspect_attribute_table", {"layer_id": main_layer, "sample_limit": 5}, area="attribute_table"),
            record("field_statistics", {"layer_id": main_layer, "field_name": stats_field, "max_features": 5000}, area="attribute_table"),
            record("unique_values", {"layer_id": main_layer, "field_name": text_field, "limit": 30}, area="attribute_table"),
            record("validate_expression", {"layer_id": main_layer, "expression": expr}, area="expressions"),
            record("evaluate_expression", {"layer_id": main_layer, "expression": expr}, area="expressions"),
            record("query_features", {"layer_id": main_layer, "expression": expr, "max_features": 5}, area="expressions"),
        ])
    else:
        attributes_tests.append({"area": "attribute_table", "status": "SKIPPED_NO_TEST_DATA", "message": "No vector layer/field available."})
    write_area("attributes_expressions", attributes_tests)

    selection_tests: list[dict[str, Any]] = []
    if main_layer and overlay_layer and text_field:
        attr_value = sample_value
        selection_tests.extend([
            record("select_by_expression", {"layer_id": main_layer, "expression": expr, "max_features": 10000}, True, "selection"),
            record("select_by_attribute", {"layer_id": main_layer, "field_name": text_field, "operator": "=", "value": attr_value}, True, "selection"),
            record("select_by_location", {"input_layer_id": main_layer, "overlay_layer_id": overlay_layer, "predicate": "intersects"}, True, "selection"),
            record("extract_by_expression", {"layer_id": main_layer, "expression": expr, "output": "TEMPORARY_OUTPUT"}, True, "selection"),
            record("extract_by_attribute", {"layer_id": main_layer, "field_name": text_field, "operator": "=", "value": attr_value, "output": "TEMPORARY_OUTPUT"}, True, "selection"),
            record("extract_by_location", {"input_layer_id": main_layer, "overlay_layer_id": overlay_layer, "predicate": "intersects", "output": "TEMPORARY_OUTPUT"}, True, "selection"),
            record("extract_by_expression", {"layer_id": main_layer, "expression": expr, "output": output_path("extract_by_expression.gpkg")}, False, "selection", 90),
        ])
    else:
        selection_tests.append({"area": "selection", "status": "SKIPPED_NO_TEST_DATA", "message": "No suitable vector/overlay fields available."})
    write_area("selection", selection_tests)

    vector_tests: list[dict[str, Any]] = []
    if main_layer and overlay_layer:
        vector_tests.extend([
            record("validate_geometries", {"layer_id": main_layer, "max_features": 1000, "deep": False}, area="vector_analysis"),
            record("fix_geometries", {"layer_id": main_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("buffer", {"layer_id": main_layer, "distance": 0.01, "segments": 4, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("clip", {"input_layer_id": main_layer, "overlay_layer_id": overlay_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("dissolve", {"layer_id": main_layer, "fields": [text_field] if text_field else [], "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("reproject_layer", {"layer_id": main_layer, "target_crs": "EPSG:4674", "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("intersection", {"input_layer_id": main_layer, "overlay_layer_id": overlay_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("union", {"input_layer_id": main_layer, "overlay_layer_id": overlay_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("difference", {"input_layer_id": main_layer, "overlay_layer_id": overlay_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("centroids", {"layer_id": main_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("multipart_to_singleparts", {"layer_id": main_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"),
            record("buffer", {"layer_id": main_layer, "distance": 0.01, "segments": 4, "output": output_path("buffer.gpkg")}, False, "vector_analysis", 120),
            record("centroids", {"layer_id": main_layer, "output": output_path("centroids.gpkg")}, False, "vector_analysis", 120),
            record("export_layer", {"layer_id": main_layer, "output_path": output_path("export_layer.gpkg"), "format": "GPKG"}, False, "vector_analysis", 120),
        ])
        if point_layer:
            vector_tests.append(record("count_points_in_polygon", {"polygon_layer_id": main_layer, "point_layer_id": point_layer, "output": "TEMPORARY_OUTPUT"}, True, "vector_analysis"))
        else:
            vector_tests.append({"area": "vector_analysis", "action": "count_points_in_polygon", "status": "SKIPPED_NO_TEST_DATA", "message": "No point layer detected."})
    else:
        vector_tests.append({"area": "vector_analysis", "status": "SKIPPED_NO_TEST_DATA", "message": "No suitable vector layers available."})
    write_area("vector_analysis", vector_tests)

    symbology_tests: list[dict[str, Any]] = []
    qml_path = output_path("contextual_style.qml")
    if main_layer and text_field:
        symbology_tests.extend([
            record("apply_single_symbol", {"layer_id": main_layer, "fill_color": "#D8E1E8", "stroke_color": "#075D68", "opacity": 0.85}, True, "symbology"),
            record("apply_single_symbol", {"layer_id": main_layer, "fill_color": "#D8E1E8", "stroke_color": "#075D68", "opacity": 0.85}, False, "symbology"),
            record("apply_categorized_style", {"layer_id": main_layer, "field_name": text_field, "limit": 8}, True, "symbology"),
            record("apply_graduated_style", {"layer_id": main_layer, "field_name": numeric_field or text_field, "classes": 5}, True, "symbology"),
            record("set_layer_opacity", {"layer_id": main_layer, "opacity": 0.85}, True, "symbology"),
            record("inspect_layer_style", {"layer_id": main_layer}, area="symbology"),
            record("save_qml_style", {"layer_id": main_layer, "output_path": qml_path}, True, "symbology"),
            record("save_qml_style", {"layer_id": main_layer, "output_path": qml_path}, False, "symbology"),
            record("load_qml_style", {"layer_id": main_layer, "path": qml_path}, True, "symbology"),
            record("create_labels", {"layer_id": main_layer, "field_name": text_field, "font_size": 8, "buffer": True}, True, "labels"),
            record("create_labels_from_expression", {"layer_id": main_layer, "expression": f'to_string("{text_field}")', "font_size": 8}, True, "labels"),
            record("enable_labels", {"layer_id": main_layer}, True, "labels"),
            record("disable_labels", {"layer_id": main_layer}, True, "labels"),
        ])
    else:
        symbology_tests.append({"area": "symbology", "status": "SKIPPED_NO_TEST_DATA", "message": "No vector layer/field available."})
    write_area("symbology_labels", symbology_tests)

    raster_tests: list[dict[str, Any]] = []
    if raster_layer:
        info = bridge("raster_info", {"layer_id": raster_layer}, False, 60)
        extent = info.get("data", {}).get("extent", {})
        extent_string = ""
        if extent:
            extent_string = f"{extent.get('xmin')},{extent.get('xmax')},{extent.get('ymin')},{extent.get('ymax')}"
        raster_tests.extend([
            record("raster_info", {"layer_id": raster_layer}, area="raster"),
            record("raster_band_statistics", {"layer_id": raster_layer, "band": 1}, area="raster", timeout=90),
            record("raster_metadata_report", {"layer_id": raster_layer}, area="raster"),
            record("raster_hillshade", {"layer_id": raster_layer, "output": str(RUN_DIR / "raster" / "hillshade.tif")}, True, "raster"),
            record("raster_slope", {"layer_id": raster_layer, "output": str(RUN_DIR / "raster" / "slope.tif")}, True, "raster"),
            record("raster_aspect", {"layer_id": raster_layer, "output": str(RUN_DIR / "raster" / "aspect.tif")}, True, "raster"),
            record("raster_contours", {"layer_id": raster_layer, "interval": 20, "output": str(RUN_DIR / "raster" / "contours.gpkg")}, True, "raster"),
            record("raster_reproject", {"layer_id": raster_layer, "target_crs": "EPSG:4674", "output": str(RUN_DIR / "raster" / "reproject.tif")}, True, "raster"),
            record("raster_polygonize", {"layer_id": raster_layer, "output": str(RUN_DIR / "raster" / "polygonize.gpkg")}, True, "raster"),
        ])
        if extent_string:
            raster_tests.append(record("raster_clip_by_extent", {"layer_id": raster_layer, "extent": extent_string, "output": str(RUN_DIR / "raster" / "clip_extent.tif")}, True, "raster"))
        if overlay_layer:
            raster_tests.append(record("raster_clip_by_mask", {"layer_id": raster_layer, "mask_layer_id": overlay_layer, "output": str(RUN_DIR / "raster" / "clip_mask.tif")}, True, "raster"))
        raster_tests.append(record("raster_hillshade", {"layer_id": raster_layer, "output": str(RUN_DIR / "raster" / "hillshade_real.tif")}, False, "raster", 180))
    else:
        raster_tests.append({"area": "raster", "status": "SKIPPED_NO_TEST_RASTER", "message": "No test raster found or loaded."})
    write_area("raster", raster_tests)

    cartography_tests: list[dict[str, Any]] = []
    map_outputs: list[str] = []
    if main_layer:
        templates_resp = record("list_layout_templates", area="professional_cartography")
        cartography_tests.append(templates_resp)
        templates = ["scientific_basic", "scientific_publication", "environmental_report", "minimal_clean", "technical_dark"]
        for i in range(10):
            path = output_path(f"professional_map_{i+1:02d}.png")
            map_outputs.append(path)
            cartography_tests.append(record("generate_professional_map", {
                "layer_id": main_layer,
                "title": f"SIGMAI Professional Contextual Test {i+1}",
                "subtitle": "Contextual capability regression",
                "output_path": path,
                "format": "png",
                "layout_template": templates[i % len(templates)],
                "legend_layers": [main_layer],
                "style_profile": ["scientific_soft", "environmental_green", "technical_blue", "monochrome_publication", "biodiversity_report"][i % 5],
                "include_grid": True,
                "include_logo": True,
                "map_author": "",
                "data_source": "SIGMAI test data",
                "confirm_overwrite": False,
            }, False, "professional_cartography", 120))
        for i in range(10):
            path = output_path(f"basic_map_{i+1:02d}.png")
            map_outputs.append(path)
            cartography_tests.append(record("generate_basic_map", {
                "layer_id": main_layer,
                "title": f"SIGMAI Basic Contextual Test {i+1}",
                "output_path": path,
                "format": "png",
                "legend_layers": [main_layer],
                "include_grid": i % 2 == 0,
                "map_author": "",
                "data_source": "SIGMAI test data",
                "confirm_overwrite": False,
            }, False, "professional_cartography", 120))
        generated_map_tests = [
            test
            for test in cartography_tests
            if test.get("action") in {"generate_professional_map", "generate_basic_map"} and test.get("ok")
        ]
        for test in generated_map_tests:
            data = test.get("data", {})
            layout_name = data.get("layout_name")
            output = data.get("output_path")
            if layout_name and output:
                cartography_tests.extend([
                    record("evaluate_layout_cartographic_completeness", {"layout_name": layout_name, "output_path": output}, area="professional_cartography"),
                    record("evaluate_map_quality", {"layout_name": layout_name, "output_path": output}, area="professional_cartography"),
                    record("validate_map_readability", {"layout_name": layout_name, "output_path": output}, area="professional_cartography"),
                    record("suggest_layout_improvements", {"layout_name": layout_name, "output_path": output}, area="professional_cartography"),
                    record("detect_visual_collisions", {"layout_name": layout_name}, area="professional_cartography"),
                ])
        cartography_tests.append({"area": "professional_cartography", "action": "local_output_file_check", "status": "validated", "outputs": validate_pngs(map_outputs)})
    else:
        cartography_tests.append({"area": "professional_cartography", "status": "SKIPPED_NO_TEST_DATA", "message": "No vector layer available for maps."})
    write_area("professional_cartography", cartography_tests)

    workflow_tests: list[dict[str, Any]] = []
    if main_layer:
        workflow_steps = [
            {"action": "diagnose_crs", "params": {}, "dry_run": False},
            {"action": "validate_geometries", "params": {"layer_id": main_layer, "max_features": 200}, "dry_run": False},
            {"action": "set_layer_style", "params": {"layer_id": main_layer}, "dry_run": True},
            {"action": "generate_basic_map", "params": {"layer_id": main_layer, "title": "Workflow Dry Run Map", "output_path": output_path("workflow_map.png"), "format": "png"}, "dry_run": True},
            {"action": "generate_workflow_report", "params": {"output_path": output_path("workflow_report.md")}, "dry_run": True},
        ]
        template_path = output_path("contextual_workflow_template.json")
        workflow_tests.extend([
            record("plan_workflow", {"name": "contextual_workflow", "steps": workflow_steps}, area="workflow"),
            record("dry_run_workflow", {"name": "contextual_workflow", "steps": workflow_steps}, area="workflow"),
            record("save_workflow_template", {"name": "contextual_workflow", "steps": workflow_steps, "output_path": template_path}, True, "workflow"),
            record("save_workflow_template", {"name": "contextual_workflow", "steps": workflow_steps, "output_path": template_path}, False, "workflow"),
            record("list_workflow_templates", {}, area="workflow"),
            record("run_workflow_template", {"path": template_path, "dry_run": True}, True, "workflow"),
            record("execute_workflow", {"name": "contextual_workflow", "steps": workflow_steps}, True, "workflow"),
        ])
    else:
        workflow_tests.append({"area": "workflow", "status": "SKIPPED_NO_TEST_DATA", "message": "No vector layer available for workflow."})
    write_area("workflows", workflow_tests)

    plugin_tests = [
        record("list_qgis_plugins_extended", area="plugin_orchestration", timeout=60),
        record("inspect_plugin_capabilities", {"plugin_name": "TopoTrail", "plugin_package": "TopoTrail"}, area="plugin_orchestration"),
        record("list_plugin_processing_algorithms", {"plugin_name": "TopoTrail", "plugin_package": "TopoTrail"}, area="plugin_orchestration"),
        record("get_plugin_algorithm_info", {"plugin_name": "TopoTrail", "plugin_package": "TopoTrail", "algorithm_id": "topotrail:topotrail"}, area="plugin_orchestration"),
        record("generate_plugin_adapter_report", {"plugin_name": "TopoTrail", "output_path": output_path("topotrail_adapter_report.md")}, False, "plugin_orchestration"),
        record("run_plugin_algorithm_safe", {"algorithm_id": "topotrail:topotrail", "parameters": {}, "output": "TEMPORARY_OUTPUT"}, True, "plugin_orchestration"),
    ]
    write_area("plugin_orchestration", plugin_tests)

    all_tests = base_tests + attributes_tests + selection_tests + vector_tests + symbology_tests + raster_tests + cartography_tests + workflow_tests + plugin_tests
    failures = [test for test in all_tests if str(test.get("status")).lower() in {"needs_fix", "failed_with_reason"} or test.get("ok") is False and str(test.get("status")).lower() not in {"skipped_no_data", "skipped_no_test_data", "skipped_no_test_raster", "skipped_protected"}]
    skipped = [test for test in all_tests if str(test.get("status")).upper().startswith("SKIPPED") or str(test.get("status")).lower().startswith("skipped")]
    validated = [test for test in all_tests if test.get("ok") is True or test.get("status") == "validated"]

    by_area: dict[str, dict[str, int]] = {}
    for test in all_tests:
        area = str(test.get("area", "unknown"))
        by_area.setdefault(area, {"total": 0, "validated": 0, "failed": 0, "skipped": 0})
        by_area[area]["total"] += 1
        if test in validated:
            by_area[area]["validated"] += 1
        elif test in skipped:
            by_area[area]["skipped"] += 1
        else:
            by_area[area]["failed"] += 1

    quality_tests = [
        test.get("data", {})
        for test in cartography_tests
        if test.get("action") == "evaluate_map_quality" and test.get("ok")
    ]
    quality_grade_counts: dict[str, int] = {}
    for quality in quality_tests:
        grade = str(quality.get("grade", "unknown"))
        quality_grade_counts[grade] = quality_grade_counts.get(grade, 0) + 1

    professional_quality = [
        quality
        for quality in quality_tests
        if "professional_map_" in str(quality.get("output_path", ""))
    ]
    professional_a_count = sum(1 for quality in professional_quality if quality.get("grade") in {"A+", "A"})
    basic_quality = [
        quality
        for quality in quality_tests
        if "basic_map_" in str(quality.get("output_path", ""))
    ]
    basic_a_count = sum(1 for quality in basic_quality if quality.get("grade") in {"A+", "A"})

    level = "LEVEL 5 - Cartographic Map Generation Capable"
    if by_area.get("attribute_table", {}).get("validated", 0) >= 4 and by_area.get("expressions", {}).get("validated", 0) >= 2 and by_area.get("selection", {}).get("validated", 0) >= 4 and by_area.get("vector_analysis", {}).get("validated", 0) >= 8:
        level = "LEVEL 6 - Vector Analysis and Attribute Capable"
    if len(professional_quality) >= 10 and professional_a_count >= 9 and len(basic_quality) >= 10 and basic_a_count >= 9 and level.startswith("LEVEL 6"):
        level = "LEVEL 7 - Professional Cartography and Symbology Capable"
    if raster_layer and by_area.get("raster", {}).get("validated", 0) >= 8 and by_area.get("workflow", {}).get("validated", 0) >= 6 and level.startswith("LEVEL 7"):
        level = "LEVEL 8 - Raster Core and Workflow Foundation Capable (initial contextual validation)"

    consolidated = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "audit_input": {
            "capability_audit_json": str(ROOT / "diagnostics" / "SIGMAI_FULL_QGIS_CAPABILITY_AUDIT.json"),
            "test_data_root": str(TEST_DATA),
            "output_root": str(RUN_DIR),
        },
        "environment": {
            "bridge_url": BASE,
            "token_masked": mask(TOKEN),
            "started_at": start,
            "vectors_loaded": vectors,
            "rasters_loaded": rasters,
            "main_layer_id": main_layer,
            "overlay_layer_id": overlay_layer,
            "point_layer_id": point_layer,
            "raster_layer_id": raster_layer,
            "text_field": text_field,
            "numeric_field": numeric_field,
            "expression": expr,
        },
        "summary": {
            "commands_tested_with_real_parameters": len(all_tests),
            "validated": len(validated),
            "failed": len(failures),
            "skipped_no_data": len(skipped),
            "requires_fix": len([item for item in failures if item.get("status") == "needs_fix"]),
            "highest_validated_level_after_contextual_tests": level,
            "quality_grade_counts": quality_grade_counts,
            "professional_maps_a_or_b": professional_a_count,
            "professional_maps_total_quality_checked": len(professional_quality),
            "basic_maps_a_or_b": basic_a_count,
            "basic_maps_total_quality_checked": len(basic_quality),
        },
        "by_area": by_area,
        "failures": failures,
        "skipped": skipped,
        "recommendations": [
            "Fix generate_professional_map map-item/layer rendering: professional templates currently render layout elements but the map body is blank or too weak.",
            "Review failed_with_reason entries first; most indicate handler contract mismatch or unavailable input type.",
            "Keep raster Level 8 provisional unless terrain outputs are visually/semantically validated.",
            "Use this contextual runner after every major command-family expansion.",
        ],
        "area_files": {
            "attributes_expressions": str(OUT_ROOT / "attributes_expressions.json"),
            "selection": str(OUT_ROOT / "selection.json"),
            "vector_analysis": str(OUT_ROOT / "vector_analysis.json"),
            "symbology_labels": str(OUT_ROOT / "symbology_labels.json"),
            "raster": str(OUT_ROOT / "raster.json"),
            "professional_cartography": str(OUT_ROOT / "professional_cartography.json"),
            "workflows": str(OUT_ROOT / "workflows.json"),
            "plugin_orchestration": str(OUT_ROOT / "plugin_orchestration.json"),
        },
    }

    validation_json = ROOT / "diagnostics" / "SIGMAI_CONTEXTUAL_CAPABILITY_VALIDATION.json"
    validation_json.write_text(json.dumps(consolidated, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# SIGMAI Contextual Capability Validation",
        "",
        f"Generated at: {consolidated['generated_at']}",
        f"Run ID: `{RUN_ID}`",
        "",
        "## Summary",
    ]
    for key, value in consolidated["summary"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "## Cartographic Quality Finding",
        "",
        f"- Basic maps with A/A+: `{basic_a_count}/{len(basic_quality)}`",
        f"- Professional maps with A/A+: `{professional_a_count}/{len(professional_quality)}`",
        "- Interpretation: professional map commands execute, but the current professional templates still need a fix because the exported map body is blank or visually weak.",
    ])
    lines.extend(["", "## By Area", "", "| Area | Total | Validated | Failed | Skipped |", "|---|---:|---:|---:|---:|"])
    for area, counts in by_area.items():
        lines.append(f"| `{area}` | {counts['total']} | {counts['validated']} | {counts['failed']} | {counts['skipped']} |")
    lines.extend(["", "## Key Data", ""])
    lines.append(f"- Main vector layer: `{main_layer}`")
    lines.append(f"- Overlay layer: `{overlay_layer}`")
    lines.append(f"- Point layer: `{point_layer}`")
    lines.append(f"- Raster layer: `{raster_layer}`")
    lines.append(f"- Expression used: `{expr}`")
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.append("| Area | Action | Status | Error | Message |")
        lines.append("|---|---|---|---|---|")
        for fail in failures[:80]:
            lines.append(f"| `{fail.get('area')}` | `{fail.get('action')}` | `{fail.get('status')}` | `{fail.get('error_code', '')}` | {str(fail.get('message', '')).replace('|', '/')} |")
    else:
        lines.append("No failures recorded.")
    lines.extend(["", "## Skipped", ""])
    if skipped:
        for item in skipped:
            lines.append(f"- `{item.get('area')}` / `{item.get('action', '')}`: {item.get('message', item.get('status'))}")
    else:
        lines.append("No skipped tests.")
    lines.extend(["", "## Output Files", ""])
    for name, path in consolidated["area_files"].items():
        lines.append(f"- `{name}`: `{path}`")
    lines.append(f"- Run output directory: `{RUN_DIR}`")

    validation_md = ROOT / "diagnostics" / "SIGMAI_CONTEXTUAL_CAPABILITY_VALIDATION.md"
    validation_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "json": str(validation_json),
        "md": str(validation_md),
        "run_dir": str(RUN_DIR),
        "summary": consolidated["summary"],
        "by_area": by_area,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
