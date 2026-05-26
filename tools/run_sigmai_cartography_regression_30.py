from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_plugin.client.sigmai_client import SigmaiClient


DEFAULT_OUT = ROOT / "test_outputs" / "sigmai_cartography_regression_after_restart"
REQUIRED_LAYER_NAMES = [
    "SP_Municipios_2025",
    "Cruzeiro limite municipal",
    "Cruzeiro limite EPSG31983",
    "TopoTrail potencial clip Cruzeiro",
    "TopoTrail zonas potenciais 4 cartas",
]
MANUAL_CRUZEIRO_EXTENT = {"xmin": -45.14, "ymin": -22.68, "xmax": -44.88, "ymax": -22.44}


def command(client: SigmaiClient, action: str, params: dict[str, Any] | None = None, request_id: str = "", dry_run: bool = False) -> dict[str, Any]:
    return client.command(
        {
            "schema_version": "0.2",
            "request_id": request_id or f"regression-{action}",
            "action": action,
            "params": params or {},
            "dry_run": dry_run,
        }
    )


def _png_rgba(path: Path) -> tuple[int, int, bytes] | None:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk)
        elif ctype == b"IDAT":
            compressed.extend(chunk)
        elif ctype == b"IEND":
            break
    if not width or not height or bit_depth != 8 or interlace != 0:
        return None
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        return None
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    rows = []
    i = 0
    prev = bytearray(stride)
    for _y in range(height):
        filter_type = raw[i]
        i += 1
        row = bytearray(raw[i : i + stride])
        i += stride
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = prev[x]
            up_left = prev[x - channels] if x >= channels else 0
            if filter_type == 1:
                row[x] = (row[x] + left) & 255
            elif filter_type == 2:
                row[x] = (row[x] + up) & 255
            elif filter_type == 3:
                row[x] = (row[x] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                row[x] = (row[x] + (left if pa <= pb and pa <= pc else up if pb <= pc else up_left)) & 255
        rows.append(bytes(row))
        prev = row
    rgba = bytearray(width * height * 4)
    offset = 0
    for row in rows:
        for x in range(0, len(row), channels):
            if color_type == 0:
                r = g = b = row[x]
                a = 255
            elif color_type == 2:
                r, g, b = row[x], row[x + 1], row[x + 2]
                a = 255
            elif color_type == 4:
                r = g = b = row[x]
                a = row[x + 1]
            else:
                r, g, b, a = row[x], row[x + 1], row[x + 2], row[x + 3]
            rgba[offset : offset + 4] = bytes((r, g, b, a))
            offset += 4
    return width, height, bytes(rgba)


def image_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "NO_OUTPUT", "readable": False, "nonwhite_ratio": 0.0, "color_ratio": 0.0, "output_size": 0}
    parsed = _png_rgba(path)
    if parsed is None:
        return {"status": "UNREADABLE", "readable": False, "nonwhite_ratio": 0.0, "color_ratio": 0.0, "output_size": path.stat().st_size}
    width, height, pixels = parsed
    x0, x1 = int(width * 0.03), int(width * 0.68)
    y0, y1 = int(height * 0.14), int(height * 0.90)
    step = max(1, min(width, height) // 280)
    sampled = nonwhite = colorful = dark = 0
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            idx = (y * width + x) * 4
            r, g, b, a = pixels[idx], pixels[idx + 1], pixels[idx + 2], pixels[idx + 3]
            if a == 0:
                continue
            sampled += 1
            if not (r > 245 and g > 245 and b > 245):
                nonwhite += 1
            if max(r, g, b) - min(r, g, b) > 18 and not (r > 245 and g > 245 and b > 245):
                colorful += 1
            if r < 80 and g < 80 and b < 80:
                dark += 1
    nonwhite_ratio = nonwhite / sampled if sampled else 0.0
    color_ratio = colorful / sampled if sampled else 0.0
    dark_ratio = dark / sampled if sampled else 0.0
    status = "PASS_RENDERED" if nonwhite_ratio > 0.025 and (color_ratio > 0.002 or dark_ratio > 0.002) else "FAIL_BLANK_OR_NEAR_BLANK"
    return {
        "status": status,
        "readable": True,
        "width": width,
        "height": height,
        "sampled": sampled,
        "nonwhite_ratio": round(nonwhite_ratio, 6),
        "color_ratio": round(color_ratio, 6),
        "dark_ratio": round(dark_ratio, 6),
        "output_size": path.stat().st_size,
    }


def _layer_info(client: SigmaiClient, layer: dict[str, Any]) -> dict[str, Any]:
    resp = command(client, "get_layer_info", {"layer_id": layer["id"]}, f"regression-layer-info-{layer['id']}")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    return data or {}


def _extract_step(steps: list[dict[str, Any]], action: str) -> dict[str, Any]:
    for step in steps:
        if step.get("action") == action:
            return step
    return {}


def _project_crs_from_response(response: dict[str, Any]) -> str | None:
    data = response.get("data") or {}
    if not isinstance(data, dict):
        return None
    for key in ("authid", "crs", "project_crs"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("authid") or value.get("crs")
            if nested:
                return str(nested)
    return None


def run(limit: int = 30, out_dir: Path | None = None, run_id: str | None = None) -> dict[str, Any]:
    out = out_dir or DEFAULT_OUT / f"regression_{limit}"
    out.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    client = SigmaiClient(timeout=240)
    status = command(client, "status", {}, "regression-status")
    capabilities = command(client, "get_capabilities", {}, "regression-capabilities")
    health = command(client, "self_health_check", {}, "regression-self-health")
    project_crs_resp = command(client, "get_project_crs", {}, "regression-project-crs")
    project_crs = _project_crs_from_response(project_crs_resp)
    layers_resp = command(client, "list_layers", {}, "regression-list-layers")
    layers = layers_resp.get("data", {}).get("layers", [])
    selected: list[dict[str, Any]] = []
    for wanted in REQUIRED_LAYER_NAMES:
        match = next((layer for layer in layers if layer.get("name") == wanted), None)
        if match is None:
            match = next((layer for layer in layers if wanted in layer.get("name", "")), None)
        if match:
            selected.append(match)
    if len(selected) < len(REQUIRED_LAYER_NAMES):
        missing = sorted(set(REQUIRED_LAYER_NAMES) - {layer.get("name") for layer in selected})
        raise RuntimeError(f"Missing required layers in QGIS project: {missing}")
    layer_details = {layer["id"]: _layer_info(client, layer) for layer in selected}
    styles = [
        {"fill_color": "#00A86B", "stroke_color": "#062A3A", "stroke_width": 0.35, "opacity": 0.65},
        {"fill_color": "#D8E1E8", "stroke_color": "#075D68", "stroke_width": 0.55, "opacity": 0.85},
        {"fill_color": "#F5A623", "stroke_color": "#041B26", "stroke_width": 0.40, "opacity": 0.55},
        {"fill_color": "#20E39A", "stroke_color": "#003B5C", "stroke_width": 0.25, "opacity": 0.45},
        {"fill_color": "#D94A4A", "stroke_color": "#062A3A", "stroke_width": 0.60, "opacity": 0.50},
    ]
    modes = ["basic_auto", "atomic_auto", "atomic_manual"]
    records = []
    for i in range(limit):
        layer = selected[i % len(selected)]
        mode = modes[i % len(modes)]
        output = out / f"regression_{i:03d}_{mode}.png"
        layout_name = f"SIGMAI_REGRESSION_{run_id}_{i:03d}_{mode}"
        started = time.time()
        steps: list[dict[str, Any]] = []
        bridge_ok = False
        response: dict[str, Any] = {}
        try:
            if mode == "basic_auto":
                response = command(
                    client,
                    "generate_basic_map",
                    {
                        "layer_id": layer["id"],
                        "layout_name": layout_name,
                        "title": f"SIGMAI regressão {i:03d} - {layer['name']}",
                        "output_path": str(output),
                        "format": "png",
                        "include_legend": True,
                        "include_scale_bar": True,
                        "include_north_arrow": True,
                        "include_grid": i % 2 == 0,
                        "include_source": True,
                        "apply_default_style": True,
                        "confirm_overwrite": True,
                    },
                    f"regression-{i:03d}-basic",
                )
                bridge_ok = bool(response.get("ok"))
                data = response.get("data") or {}
                steps = data.get("steps") if isinstance(data.get("steps"), list) else []
            else:
                steps.append(command(client, "create_layout", {"layout_name": layout_name}, f"regression-{i:03d}-create"))
                steps.append(command(client, "set_layer_style", {"layer_id": layer["id"], "style_type": "single_symbol", **styles[i % len(styles)]}, f"regression-{i:03d}-style"))
                steps.append(command(client, "add_layout_map", {"layout_name": layout_name, "layer_id": layer["id"], "item_id": "main_map", "x": 10, "y": 25, "width": 180, "height": 145, "margin_percent": 5}, f"regression-{i:03d}-map"))
                extent_params: dict[str, Any]
                if mode == "atomic_manual":
                    extent_params = {"layout_name": layout_name, "map_item_id": "main_map", "extent": MANUAL_CRUZEIRO_EXTENT}
                else:
                    extent_params = {"layout_name": layout_name, "map_item_id": "main_map", "layer_id": layer["id"], "margin_percent": 5}
                steps.append(command(client, "set_layout_extent", extent_params, f"regression-{i:03d}-extent"))
                steps.append(command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "title", "text": f"SIGMAI regressão {i:03d}", "x": 10, "y": 8, "width": 260, "height": 12, "font_size": 15, "bold": True, "align": "center"}, f"regression-{i:03d}-title"))
                steps.append(command(client, "add_layout_legend", {"layout_name": layout_name, "item_id": "legend", "title": "Legenda", "x": 200, "y": 25, "width": 75, "height": 90, "linked_map_item_id": "main_map"}, f"regression-{i:03d}-legend"))
                steps.append(command(client, "add_layout_scale_bar", {"layout_name": layout_name, "item_id": "scale_bar", "linked_map_item_id": "main_map", "x": 15, "y": 175, "width": 65, "height": 10, "units": "km"}, f"regression-{i:03d}-scale"))
                steps.append(command(client, "add_layout_north_arrow", {"layout_name": layout_name, "item_id": "north_arrow", "x": 180, "y": 28, "width": 15, "height": 20}, f"regression-{i:03d}-north"))
                steps.append(command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "source", "text": "Generated by SIGMAI - Secure GIS-AI Interface | Author: MACIEL, L. S. C.", "x": 10, "y": 190, "width": 260, "height": 8, "font_size": 8}, f"regression-{i:03d}-source"))
                steps.append(command(client, "export_layout", {"layout_name": layout_name, "format": "png", "path": str(output), "confirm_overwrite": True}, f"regression-{i:03d}-export"))
                bridge_ok = all(step.get("ok") for step in steps)
                response = {"ok": bridge_ok, "steps": steps}
            metrics = image_metrics(output)
            add_map = _extract_step(steps, "add_layout_map")
            set_extent = _extract_step(steps, "set_layout_extent")
            record = {
                "index": i,
                "mode": mode,
                "layer_name": layer.get("name"),
                "layer_id": layer.get("id"),
                "layer_crs": layer.get("crs"),
                "project_crs": project_crs,
                "original_layer_extent": layer_details.get(layer["id"], {}).get("extent"),
                "transformed_extent": (set_extent.get("data") or {}).get("extent") or (add_map.get("data") or {}).get("extent"),
                "map_item_crs": project_crs,
                "output_path": str(output),
                "bridge_ok": bridge_ok,
                "image_metrics": metrics,
                "visual_status": metrics.get("status"),
                "cartographic_grade": ((response.get("data") or {}).get("cartographic_assessment") or {}).get("grade"),
                "failure_reason": None
                if bridge_ok and metrics.get("status") == "PASS_RENDERED"
                else "COMMAND_FAILED"
                if not bridge_ok
                else "OUTPUT_BLANK"
                if output.exists()
                else "EXPORT_FAILED",
                "elapsed_seconds": round(time.time() - started, 3),
                "response_summary": {
                    "errors": response.get("errors"),
                    "warnings": response.get("warnings"),
                    "items_created": (response.get("data") or {}).get("items_created") if isinstance(response.get("data"), dict) else None,
                },
            }
        except Exception as exc:
            record = {
                "index": i,
                "mode": mode,
                "layer_name": layer.get("name"),
                "layer_id": layer.get("id"),
                "layer_crs": layer.get("crs"),
                "project_crs": project_crs,
                "output_path": str(output),
                "bridge_ok": False,
                "image_metrics": {"status": "EXCEPTION", "nonwhite_ratio": 0.0, "color_ratio": 0.0, "output_size": 0},
                "visual_status": "EXCEPTION",
                "failure_reason": repr(exc),
                "elapsed_seconds": round(time.time() - started, 3),
            }
        records.append(record)
        print(json.dumps({"index": record["index"], "mode": mode, "layer": layer.get("name"), "crs": layer.get("crs"), "bridge_ok": record["bridge_ok"], **record["image_metrics"]}, ensure_ascii=False))
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "total": len(records),
        "bridge_ok": sum(1 for r in records if r.get("bridge_ok")),
        "render_pass": sum(1 for r in records if r.get("visual_status") == "PASS_RENDERED"),
        "blank_or_bad": sum(1 for r in records if r.get("visual_status") != "PASS_RENDERED"),
        "project_crs": project_crs,
        "status_ok": status.get("ok"),
        "self_health_ok": health.get("ok"),
        "restart_required": ((health.get("data") or {}).get("restart_required")),
        "cartography_commands_available": sorted(
            name for name, info in (capabilities.get("data", {}).get("commands") or {}).items() if (info or {}).get("group") == "cartography"
        ),
        "by_mode": {},
        "by_layer": {},
        "by_crs": {},
    }
    for record in records:
        for bucket, value in [("by_mode", record["mode"]), ("by_layer", record["layer_name"]), ("by_crs", record["layer_crs"])]:
            slot = summary[bucket].setdefault(value, {"total": 0, "pass": 0, "bad": 0})
            slot["total"] += 1
            if record.get("visual_status") == "PASS_RENDERED":
                slot["pass"] += 1
            else:
                slot["bad"] += 1
    result = {"summary": summary, "records": records}
    (out / f"regression_{limit}_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# SIGMAI Cartography Regression 30 After Restart",
        "",
        "## Summary",
        "",
        f"- total: {summary['total']}",
        f"- bridge_ok: {summary['bridge_ok']}",
        f"- render_pass: {summary['render_pass']}",
        f"- blank_or_bad: {summary['blank_or_bad']}",
        f"- project_crs: {summary['project_crs']}",
        f"- restart_required: {summary['restart_required']}",
        "",
        "## By Mode",
        "",
    ]
    for key, value in summary["by_mode"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Layer", ""])
    for key, value in summary["by_layer"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By CRS", ""])
    for key, value in summary["by_crs"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Failures", ""])
    failures = [record for record in records if record.get("visual_status") != "PASS_RENDERED"]
    if not failures:
        lines.append("- None.")
    for record in failures:
        lines.append(
            f"- #{record['index']} {record['mode']} {record['layer_name']} {record['layer_crs']} -> "
            f"{record.get('failure_reason')} metrics={record.get('image_metrics')} output={record.get('output_path')}"
        )
    (out / f"regression_{limit}_report.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    out_dir = Path(args.output_dir).resolve() if args.output_dir else None
    result = run(args.limit, out_dir=out_dir, run_id=args.run_id or None)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["bridge_ok"] == result["summary"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
